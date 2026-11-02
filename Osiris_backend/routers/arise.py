# ruff: noqa: B008  (FastAPI dependencies are declared as argument defaults)
"""Arise tab: public routes, domains (claim, Exceed workout, photo) and attacks.

Arise never moves crystals: the v1 vault/siege economy in routers/legacy_game.py is untouched.
"""
import base64
import binascii
import json
import secrets
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import spatial_utils
from core.clock import _now_naive_utc
from core.errors import _api_error
from core.security import get_active_player
from database import get_db
from growth_social import _display_name
from routers.challenges import register_course
from routers.runs import _get_player_run
from schemas import (
    AriseAttackResult,
    AriseClaim,
    AriseDomain,
    AriseDomainPhoto,
    AriseDomains,
    AriseRoute,
    AriseRoutePublish,
    AriseWorkout,
    AriseWorkoutResult,
    CourseCreate,
)
from services import arise
from services.challenge_store import _run_points
from services.exercises import CATALOG

router = APIRouter()

KM_PER_DEG_LAT = 111.195
ARISE = "arise"
MAX_PHOTO_BYTES = 300_000
PACE_WINDOW = timedelta(days=30)
MIN_PACE_RUN_M = 400.0
REP_EXERCISES = [e["key"] for e in CATALOG if e.get("kind") == "reps"]


# --- routes -------------------------------------------------------------------------

def _route(db: Session, course: models.Course) -> AriseRoute:
    return AriseRoute(
        id=course.id, name=course.name, activity_type=course.activity_type, distance_m=course.distance_m,
        benchmark_seconds=course.benchmark_seconds, hide_ends=course.hide_ends,
        owner_name=_display_name(db, course.owner_id), line=json.loads(course.public_route_json or "[]"),
    )


@router.post("/api/v2/arise/routes", response_model=AriseRoute, status_code=201)
def publish_route(req: AriseRoutePublish, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Publish an accepted run as a route every player can see and run. Registers the course (same rules
    and privacy trim as /api/v2/courses), then makes it public. Publishing the same run again returns it."""
    run = _get_player_run(db, req.run_session_id, token_data["id"])
    summary = register_course(CourseCreate(run_id=run.id, name=req.name), db, token_data)
    course = db.query(models.Course).filter(models.Course.id == summary.id).one()
    full = [(p[0], p[1]) for p in _run_points(db, run.id)]
    trimmed = [(p[0], p[1]) for p in json.loads(course.route_json)]
    course.activity_type = run.activity_type or "run"
    course.hide_ends = req.hide_ends
    course.is_public = True
    course.public_route_json = json.dumps(arise.public_line(full, trimmed, req.hide_ends), separators=(",", ":"))
    db.commit()
    return _route(db, course)


def _near(rows, lat: float, lng: float, radius_km: float, position) -> list:
    """`rows` within `radius_km` of (lat, lng), nearest first, at most 100."""
    pairs = sorted(((spatial_utils.haversine_distance(lat, lng, *position(r)), r) for r in rows), key=lambda p: p[0])
    return [r for d, r in pairs if d <= radius_km][:100]


@router.get("/api/v2/arise/routes", response_model=List[AriseRoute])
def nearby_routes(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(10.0, gt=0, le=50),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Public routes whose marker is within `radius_km`, nearest first (at most 100)."""
    span = radius_km / KM_PER_DEG_LAT
    rows = db.query(models.Course).filter(
        models.Course.is_public.is_(True),
        models.Course.status == "active",
        models.Course.public_lat.between(lat - span, lat + span),
    ).all()
    return [_route(db, c) for c in _near(rows, lat, lng, radius_km, lambda c: (c.public_lat, c.public_lng))]


# --- domains ------------------------------------------------------------------------

def _loop(domain: models.Domain) -> list[tuple[float, float]]:
    return [(p["lat"], p["lng"]) for p in json.loads(domain.geometry_json or "[]")]


def _workout(raw: Optional[str]) -> Optional[AriseWorkout]:
    if not raw:
        return None
    sets = json.loads(raw)
    return AriseWorkout(sets=sets, total_reps=sum(s["reps"] for s in sets))


def _domain(db: Session, d: models.Domain, difficulty: Optional[str] = None) -> AriseDomain:
    loop = _loop(d)
    centre = arise.centroid(loop) if loop else (0.0, 0.0)
    has_photo = db.query(models.DomainPhoto.id).filter(models.DomainPhoto.domain_id == d.id).first() is not None
    return AriseDomain(
        id=d.id, owner_id=d.owner_id, owner_name=_display_name(db, d.owner_id), area_sqkm=d.area_sqkm or 0.0,
        distance_m=d.distance_m or 0.0, duration_s=d.duration_s or 0.0, centroid_lat=centre[0], centroid_lng=centre[1],
        geometry=[[p[0], p[1]] for p in loop], source_run_session_id=d.source_run_session_id,
        workout=_workout(d.defense_workout_json),
        photo_url=f"/api/v2/arise/domains/{d.id}/photo" if has_photo else None, difficulty=difficulty,
    )


def _accepted_loop(db: Session, run_id: int, player_id: int) -> tuple[models.RunSession, list[tuple[float, float]]]:
    run = _get_player_run(db, run_id, player_id)
    if run.status != "closed" or run.verification_status != "accepted":
        raise _api_error(409, "RUN_NOT_ACCEPTED", "Only a verified, accepted run counts")
    return run, [(p[0], p[1]) for p in _run_points(db, run.id)]


def _arise_domain(db: Session, domain_id: int) -> models.Domain:
    d = db.query(models.Domain).filter(models.Domain.id == domain_id, models.Domain.defense_type == ARISE).first()
    if d is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    return d


def _owned_domain(db: Session, domain_id: int, player_id: int) -> models.Domain:
    d = _arise_domain(db, domain_id)
    if d.owner_id != player_id:
        raise HTTPException(status_code=403, detail="Only the domain's owner can do this")
    return d


def _run_used(db: Session, run_id: int) -> bool:
    return (
        db.query(models.Domain.id).filter(models.Domain.source_run_session_id == run_id).first() is not None
        or db.query(models.AriseAttack.id).filter(models.AriseAttack.run_session_id == run_id).first() is not None
    )


@router.post("/api/v2/arise/domains", response_model=AriseDomain, status_code=201)
def claim_domain(req: AriseClaim, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Claim the area inside an accepted loop run (finish within 50 m of the start). Its distance and time
    become the bar attackers must beat. Each run claims or attacks once."""
    run, loop = _accepted_loop(db, req.run_session_id, token_data["id"])
    if not arise.is_loop(loop):
        raise _api_error(422, "NOT_A_LOOP", "Finish within 50 m of where you started to claim a domain")
    if _run_used(db, run.id):
        raise _api_error(409, "RUN_ALREADY_USED", "This run already claimed or attacked a domain")
    domain = models.Domain(
        owner_id=run.user_id, geometry_json=json.dumps([{"lat": p[0], "lng": p[1]} for p in loop]),
        area_sqkm=round(arise.area_sqkm(loop), 6), defense_score=0, defense_type=ARISE, vault_balance=0,
        distance_m=run.distance_m, duration_s=run.duration_seconds, source_run_session_id=run.id,
    )
    db.add(domain)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _api_error(409, "RUN_ALREADY_USED", "This run already claimed or attacked a domain") from None
    return _domain(db, domain)


@router.post("/api/v2/arise/domains/{domain_id}/workout", response_model=AriseWorkout)
def exceed(domain_id: int, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Exceed: a random workout for the owner's level. Doing every set with the camera makes it the domain's
    defense (see .../workout/complete). Asking again replaces the pending workout."""
    d = _owned_domain(db, domain_id, token_data["id"])
    user = db.query(models.User).filter(models.User.id == d.owner_id).one()
    sets = arise.generate_workout(secrets.randbits(31), arise.player_level(user.xp or 0), REP_EXERCISES)
    d.pending_workout_json = json.dumps(sets)
    d.pending_workout_issued_at = _now_naive_utc()
    db.commit()
    return _workout(d.pending_workout_json)


def _sessions_since(db: Session, user_id: int, since) -> list[tuple[int, str, int]]:
    rows = db.query(models.ExerciseSession).filter(
        models.ExerciseSession.user_id == user_id,
        models.ExerciseSession.status == "verified",
        models.ExerciseSession.created_at >= since,
    ).all()
    return [(r.id, r.exercise_key, r.reps_valid) for r in rows]


@router.post("/api/v2/arise/domains/{domain_id}/workout/complete", response_model=AriseWorkoutResult)
def complete_exceed(domain_id: int, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Attaches the pending workout once every set is matched by a verified camera set done since it was
    issued. Until then `completed` is false and the domain keeps only its run."""
    d = _owned_domain(db, domain_id, token_data["id"])
    if not d.pending_workout_json or d.pending_workout_issued_at is None:
        raise _api_error(409, "NO_PENDING_WORKOUT", "Ask for an Exceed workout first")
    done = arise.workout_done(json.loads(d.pending_workout_json), _sessions_since(db, d.owner_id, d.pending_workout_issued_at))
    if done:
        d.defense_workout_json = d.pending_workout_json
        d.pending_workout_json = None
        d.pending_workout_issued_at = None
        db.commit()
    return AriseWorkoutResult(completed=done, domain=_domain(db, d))


def _best_pace(db: Session, user_id: int) -> Optional[float]:
    """Seconds per km of the player's fastest accepted run of at least 400 m in the last 30 days."""
    rows = db.query(models.RunSession.distance_m, models.RunSession.duration_seconds).filter(
        models.RunSession.user_id == user_id,
        models.RunSession.verification_status == "accepted",
        models.RunSession.finished_at >= _now_naive_utc() - PACE_WINDOW,
        models.RunSession.distance_m >= MIN_PACE_RUN_M,
    ).all()
    paces = [dur / (dist / 1000) for dist, dur in rows if dist and dur]
    return min(paces) if paces else None


@router.get("/api/v2/arise/domains", response_model=AriseDomains)
def nearby_domains(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(10.0, gt=0, le=50),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Other players' Arise domains near a point, split into the ones the caller is likely to win and
    the hard ones (hardest first)."""
    me = token_data["id"]
    rows = db.query(models.Domain).filter(
        models.Domain.defense_type == ARISE, models.Domain.owner_id != me, models.Domain.geometry_json.isnot(None),
    ).all()
    near = _near(rows, lat, lng, radius_km, lambda d: arise.centroid(_loop(d)))
    user = db.query(models.User).filter(models.User.id == me).one()
    pace, level = _best_pace(db, me), arise.player_level(user.xp or 0)
    suggested, hard = [], []
    for d in near:
        workout = _workout(d.defense_workout_json)
        bucket, score = arise.difficulty(pace, level, d.distance_m or 0, d.duration_s or 0, workout.total_reps if workout else 0)
        (suggested if bucket == "suggested" else hard).append((score, _domain(db, d, bucket)))
    hard.sort(key=lambda pair: -pair[0])
    return AriseDomains(suggested=[x for _, x in suggested], hard=[x for _, x in hard])


def _transfer(db: Session, d: models.Domain, attack: models.AriseAttack, run: models.RunSession) -> None:
    d.owner_id = attack.attacker_id
    d.distance_m = run.distance_m
    d.duration_s = run.duration_seconds
    d.defense_workout_json = None
    d.pending_workout_json = None
    d.pending_workout_issued_at = None
    attack.status = "won"
    attack.resolved_at = _now_naive_utc()


def _attack_result(db: Session, attack: models.AriseAttack, d: models.Domain) -> AriseAttackResult:
    return AriseAttackResult(
        attack_id=attack.id, status=attack.status, reasons=json.loads(attack.reasons_json),
        workout=_workout(attack.workout_json) if attack.status == "needs_workout" else None, domain=_domain(db, d),
    )


@router.post("/api/v2/arise/domains/{domain_id}/attack", response_model=AriseAttackResult)
def attack_domain(domain_id: int, req: AriseClaim, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Attack with an accepted loop run that encloses the domain, is at least as long as the defender's run
    and faster. A domain with a defense workout also needs the same workout done (`needs_workout`)."""
    me = token_data["id"]
    d = _arise_domain(db, domain_id)
    if d.owner_id == me:
        raise _api_error(409, "OWN_DOMAIN", "You already hold this domain")
    run, loop = _accepted_loop(db, req.run_session_id, me)
    if _run_used(db, run.id):
        raise _api_error(409, "RUN_ALREADY_USED", "This run already claimed or attacked a domain")
    reasons = arise.attack_reasons(
        loop, run.distance_m or 0, run.duration_seconds or 0, arise.centroid(_loop(d)), d.distance_m or 0, d.duration_s or 0,
    )
    attack = models.AriseAttack(
        attacker_id=me, domain_id=d.id, run_session_id=run.id, reasons_json=json.dumps(reasons),
        status="failed" if reasons else "needs_workout", workout_json=d.defense_workout_json,
    )
    db.add(attack)
    if reasons:
        attack.resolved_at = _now_naive_utc()
    elif not d.defense_workout_json:
        _transfer(db, d, attack, run)
    db.commit()
    return _attack_result(db, attack, d)


@router.post("/api/v2/arise/attacks/{attack_id}/workout/complete", response_model=AriseAttackResult)
def complete_attack_workout(attack_id: int, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Wins the domain once the attacker has done every set of the defender's workout since the attack.
    Until then the attack stays `needs_workout`."""
    attack = db.query(models.AriseAttack).filter(models.AriseAttack.id == attack_id).first()
    if attack is None or attack.attacker_id != token_data["id"]:
        raise HTTPException(status_code=404, detail="Attack not found")
    d = _arise_domain(db, attack.domain_id)
    if attack.status == "needs_workout" and arise.workout_done(
        json.loads(attack.workout_json or "[]"), _sessions_since(db, attack.attacker_id, attack.created_at),
    ):
        run = db.query(models.RunSession).filter(models.RunSession.id == attack.run_session_id).one()
        _transfer(db, d, attack, run)
        db.commit()
    return _attack_result(db, attack, d)


# --- photos -------------------------------------------------------------------------

@router.put("/api/v2/arise/domains/{domain_id}/photo", response_model=AriseDomain)
def set_domain_photo(domain_id: int, req: AriseDomainPhoto, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """The owner's picture for the domain: a JPEG of at most 300 KB, sent as base64."""
    d = _owned_domain(db, domain_id, token_data["id"])
    try:
        jpeg = base64.b64decode(req.jpeg_base64, validate=True)
    except (binascii.Error, ValueError):
        raise _api_error(422, "BAD_PHOTO", "The photo must be base64-encoded") from None
    if len(jpeg) > MAX_PHOTO_BYTES:
        raise _api_error(413, "PHOTO_TOO_LARGE", "The photo must be at most 300 KB")
    if not jpeg.startswith(b"\xff\xd8"):
        raise _api_error(422, "BAD_PHOTO", "The photo must be a JPEG")
    photo = db.query(models.DomainPhoto).filter(models.DomainPhoto.domain_id == d.id).first()
    if photo is None:
        db.add(models.DomainPhoto(domain_id=d.id, jpeg=jpeg, updated_at=_now_naive_utc()))
    else:
        photo.jpeg = jpeg
        photo.updated_at = _now_naive_utc()
    db.commit()
    return _domain(db, d)


@router.get("/api/v2/arise/domains/{domain_id}/photo")
def get_domain_photo(domain_id: int, db: Session = Depends(get_db)):
    """Public on purpose: the defender adds the picture for every attacker to see, and the app loads it
    as a plain image URL."""
    photo = db.query(models.DomainPhoto).filter(models.DomainPhoto.domain_id == domain_id).first()
    if photo is None:
        raise HTTPException(status_code=404, detail="No photo")
    return Response(photo.jpeg, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=300"})
