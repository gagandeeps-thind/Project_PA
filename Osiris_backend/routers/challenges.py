"""Courses, challenges, attempts and player progression (R2 API v2)."""
import hashlib
import json
from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import spatial_utils
from core.clock import _now_naive_utc
from core.errors import _api_error
from core.rate_limit import _rl_challenge
from core.security import get_active_player
from database import get_db
from routers.runs import _get_player_run
from schemas import (
    AttemptSubmit,
    AttemptSummary,
    BadgeOut,
    ChallengeCourseRoute,
    ChallengeCreate,
    ChallengePublic,
    CourseCreate,
    CourseSummary,
    ProgressionResponse,
)
from services import challenges as challenge_rules
from services import player_safety
from services.audit import _audit
from services.challenge_store import (
    ChallengeStats,
    _apply_attempt_outcome,
    _attempt_summary,
    _challenge_public,
    _course_route,
    _course_summary,
    _get_challenge,
    _open_challenge_ids,
    _refresh_challenge_status,
    _run_points,
)
from services.progression import _award_badge


router = APIRouter()


@router.post("/api/v2/courses", response_model=CourseSummary, status_code=201)
def register_course(
    req: CourseCreate,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Turn one accepted run into a course (PRD-005). Idempotent per run: registering the
    same run again returns the existing course. The first and last stretch of the run are
    trimmed off as a privacy zone before anything is stored."""
    player_id = token_data["id"]
    run = _get_player_run(db, req.run_id, player_id)
    if run.status != "closed" or run.verification_status != "accepted":
        raise _api_error(409, "RUN_NOT_ACCEPTED", "Only a verified, accepted run can become a course")
    existing = db.query(models.Course).filter(models.Course.source_run_session_id == run.id).first()
    if existing:
        return _course_summary(db, existing)

    trimmed = challenge_rules.trim_route(_run_points(db, run.id))
    reasons = challenge_rules.course_rejection_reasons(trimmed.distance_m)
    if not trimmed.route or trimmed.elapsed_seconds <= 0:
        reasons = reasons or ["COURSE_TOO_SHORT"]
    if reasons:
        raise _api_error(422, reasons[0], "Course must be between 0.4 km and 42.2 km after privacy trimming")

    active = db.query(models.Course).filter(
        models.Course.owner_id == player_id, models.Course.status == "active",
    ).count()
    if active >= challenge_rules.MAX_ACTIVE_COURSES_PER_USER:
        raise _api_error(409, "COURSE_LIMIT_REACHED", "You have reached the active course limit")

    route = challenge_rules.simplify_route(trimmed.route)
    start, finish = route[0], route[-1]
    # Coarse bounding pre-filter (~110 m) before the exact duplicate test.
    nearby = db.query(models.Course).filter(
        models.Course.status == "active",
        models.Course.start_lat.between(start[0] - 0.001, start[0] + 0.001),
    ).all()
    for other in nearby:
        if challenge_rules.is_duplicate_course(
            start, finish, trimmed.distance_m,
            (other.start_lat, other.start_lng), (other.finish_lat, other.finish_lng), other.distance_m,
        ):
            if other.owner_id == player_id:
                raise _api_error(409, "DUPLICATE_COURSE", "You already registered this course")
            raise _api_error(409, "COURSE_OVERLAP", "This course already exists; challenge it instead")

    marker = challenge_rules.public_marker(route)
    route_json = json.dumps([list(p) for p in route], separators=(",", ":"))
    course = models.Course(
        owner_id=player_id, source_run_session_id=run.id, version=1,
        rules_version=challenge_rules.COURSE_RULES_VERSION, name=req.name.strip(), status="active",
        distance_m=round(trimmed.distance_m, 2), benchmark_seconds=round(trimmed.elapsed_seconds, 2),
        is_loop=challenge_rules.distance_m(start, finish) <= challenge_rules.LOOP_THRESHOLD_M,
        start_lat=start[0], start_lng=start[1], finish_lat=finish[0], finish_lng=finish[1],
        route_json=route_json, route_hash=hashlib.sha256(route_json.encode("utf-8")).hexdigest(),
        public_lat=marker[0], public_lng=marker[1],
    )
    db.add(course)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.query(models.Course).filter(models.Course.source_run_session_id == run.id).first()
        if existing:
            return _course_summary(db, existing)
        raise
    _award_badge(db, player_id, "FIRST_COURSE")
    _audit(db, actor_type="player", actor_id=player_id, action="course.registered",
           entity_type="course", entity_id=course.id,
           details={"run_id": run.id, "distance_m": course.distance_m,
                    "rules_version": course.rules_version})
    db.commit()
    db.refresh(course)
    return _course_summary(db, course)


@router.get("/api/v2/courses", response_model=List[CourseSummary])
def list_my_courses(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """The player's courses, newest first, a page at a time."""
    courses = (
        db.query(models.Course)
        .filter(models.Course.owner_id == token_data["id"])
        .order_by(models.Course.created_at.desc(), models.Course.id.desc())
        .offset(offset).limit(limit)
        .all()
    )
    open_ids = _open_challenge_ids(db, [c.id for c in courses])
    return [_course_summary(db, c, open_ids) for c in courses]


@router.post("/api/v2/challenges", response_model=ChallengePublic, status_code=201)
def publish_challenge(
    req: ChallengeCreate,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
    _rl: None = Depends(_rl_challenge),
):
    """Publish an asynchronous challenge with immutable terms (PRD-006). The target is the
    owner's verified benchmark on the course; no crystals are staked (ADR-005)."""
    player_id = token_data["id"]
    prior = db.query(models.Challenge).filter(
        models.Challenge.publish_idempotency_key == req.idempotency_key,
    ).first()
    if prior is not None:
        if prior.creator_id != player_id:
            raise _api_error(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency key already used")
        course = db.query(models.Course).filter(models.Course.id == prior.course_id).first()
        return _challenge_public(db, prior, course, player_id)

    course = db.query(models.Course).filter(models.Course.id == req.course_id).first()
    if course is None:
        raise _api_error(404, "COURSE_NOT_FOUND", "Course not found")
    if course.owner_id != player_id:
        raise _api_error(403, "NOT_COURSE_OWNER", "Only the course owner can publish a challenge on it")
    if course.status != "active":
        raise _api_error(409, "COURSE_NOT_ACTIVE", "This course is not active")

    now = _now_naive_utc()
    open_on_course = db.query(models.Challenge).filter(
        models.Challenge.course_id == course.id, models.Challenge.status == "open",
    ).all()
    for ch in open_on_course:
        _refresh_challenge_status(db, ch, now)
    if any(ch.status == "open" for ch in open_on_course):
        db.commit()
        raise _api_error(409, "CHALLENGE_ALREADY_OPEN", "This course already has an open challenge")

    opens_at = now.replace(microsecond=0)
    closes_at = opens_at + timedelta(hours=req.window_hours)
    safety = req.safety_notes.strip() if req.safety_notes else None
    win_xp = challenge_rules.win_xp_for(course.distance_m)
    terms = challenge_rules.build_terms(
        course_id=course.id, course_version=course.version, target_seconds=course.benchmark_seconds,
        win_xp=win_xp, safety_notes=safety, opens_at=opens_at, closes_at=closes_at,
    )
    ch = models.Challenge(
        course_id=course.id, creator_id=player_id, title=req.title.strip(), status="open",
        rules_version=terms["rules_version"], course_version=course.version,
        target_seconds=terms["target_seconds"], entry_crystals=terms["entry_crystals"],
        reward_policy=terms["reward_policy"], win_xp=win_xp,
        participation_xp=terms["participation_xp"], eligibility=terms["eligibility"],
        privacy_mode=terms["privacy_mode"], safety_notes=safety,
        opens_at=opens_at, closes_at=closes_at, terms_hash=challenge_rules.terms_hash(terms),
        publish_idempotency_key=req.idempotency_key,
    )
    db.add(ch)
    db.flush()
    _award_badge(db, player_id, "FIRST_CHALLENGE_PUBLISHED")
    _audit(db, actor_type="player", actor_id=player_id, action="challenge.published",
           entity_type="challenge", entity_id=ch.id,
           details={"course_id": course.id, "terms_hash": ch.terms_hash, "window_hours": req.window_hours})
    db.commit()
    db.refresh(ch)
    return _challenge_public(db, ch, course, player_id)


@router.get("/api/v2/challenges/nearby", response_model=List[ChallengePublic])
def nearby_challenges(
    lat: float,
    lng: float,
    radius_km: float = 5.0,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Open challenges near a point, as generalized markers only (ADR-004). Distance is
    measured to the snapped marker and rounded, so it cannot be used to triangulate a
    route."""
    import math as _math
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise _api_error(422, "INVALID_LOCATION", "lat/lng out of range")
    radius_km = min(max(radius_km, 0.5), 50.0)
    dlat = radius_km / 111.0
    dlng = radius_km / (111.0 * max(0.01, _math.cos(_math.radians(lat))))
    rows = (
        db.query(models.Challenge, models.Course)
        .join(models.Course, models.Course.id == models.Challenge.course_id)
        .filter(
            models.Challenge.status == "open",
            models.Course.status == "active",
            models.Course.public_lat.between(lat - dlat, lat + dlat),
            models.Course.public_lng.between(lng - dlng, lng + dlng),
        )
        .all()
    )
    now = _now_naive_utc()
    changed = False
    out: List[ChallengePublic] = []
    hidden = player_safety.blocked_user_ids(db, token_data["id"])
    shown = []
    for ch, course in rows:
        changed |= _refresh_challenge_status(db, ch, now)
        if ch.status != "open" or ch.creator_id in hidden:
            continue
        dist = spatial_utils.haversine_distance(lat, lng, course.public_lat, course.public_lng)
        if dist > radius_km:
            continue
        shown.append((ch, course, dist))
    stats = ChallengeStats.load(db, [ch.id for ch, _, _ in shown], token_data["id"])
    for ch, course, dist in shown:
        out.append(_challenge_public(db, ch, course, token_data["id"], distance_km=round(dist, 1), stats=stats))
    if changed:
        db.commit()
    out.sort(key=lambda c: c.distance_km or 0.0)
    return out[:100]


@router.get("/api/v2/challenges/{challenge_id}", response_model=ChallengePublic)
def get_challenge(
    challenge_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    ch = _get_challenge(db, challenge_id)
    if _refresh_challenge_status(db, ch):
        db.commit()
    course = db.query(models.Course).filter(models.Course.id == ch.course_id).first()
    return _challenge_public(db, ch, course, token_data["id"])


@router.get("/api/v2/challenges/{challenge_id}/course", response_model=ChallengeCourseRoute)
def get_challenge_course(
    challenge_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """The exact course route, released only to the creator and to players who joined."""
    ch = _get_challenge(db, challenge_id)
    player_id = token_data["id"]
    if ch.creator_id != player_id:
        joined = db.query(models.ChallengeAttempt).filter(
            models.ChallengeAttempt.challenge_id == ch.id, models.ChallengeAttempt.user_id == player_id,
        ).first()
        if joined is None:
            raise _api_error(403, "JOIN_REQUIRED", "Join the challenge to see the course route")
    course = db.query(models.Course).filter(models.Course.id == ch.course_id).first()
    return ChallengeCourseRoute(
        challenge_id=ch.id, course_distance_m=round(course.distance_m, 2),
        start_radius_m=challenge_rules.ATTEMPT_ENDPOINT_RADIUS_M,
        route=[list(p) for p in _course_route(course)],
    )


@router.post("/api/v2/challenges/{challenge_id}/join", response_model=AttemptSummary)
def join_challenge(
    challenge_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
    _rl: None = Depends(_rl_challenge),
):
    """Join while the challenge is open (PRD-007). Idempotent: joining twice returns the same
    attempt. The attempt snapshots the terms hash it agreed to."""
    player_id = token_data["id"]
    ch = _get_challenge(db, challenge_id)
    if _refresh_challenge_status(db, ch):
        db.commit()
    existing = db.query(models.ChallengeAttempt).filter(
        models.ChallengeAttempt.challenge_id == ch.id, models.ChallengeAttempt.user_id == player_id,
    ).first()
    if existing:
        return _attempt_summary(existing, ch)
    if ch.status != "open":
        raise _api_error(409, "CHALLENGE_NOT_OPEN", f"Challenge is {ch.status}")
    if ch.creator_id == player_id:
        raise _api_error(409, "OWN_CHALLENGE", "You cannot join your own challenge")
    if player_safety.is_blocked_between(db, player_id, ch.creator_id):
        raise _api_error(403, "BLOCKED", "You can't join this challenge")
    verified_runs = db.query(models.RunSession).filter(
        models.RunSession.user_id == player_id, models.RunSession.verification_status == "accepted",
    ).count()
    if verified_runs < 1:
        raise _api_error(403, "NOT_ELIGIBLE", "Complete one verified run before joining challenges")
    attempt = models.ChallengeAttempt(
        challenge_id=ch.id, user_id=player_id, status="joined", terms_hash=ch.terms_hash,
    )
    db.add(attempt)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.query(models.ChallengeAttempt).filter(
            models.ChallengeAttempt.challenge_id == ch.id, models.ChallengeAttempt.user_id == player_id,
        ).first()
        return _attempt_summary(existing, ch)
    _audit(db, actor_type="player", actor_id=player_id, action="challenge.joined",
           entity_type="challenge_attempt", entity_id=attempt.id,
           details={"challenge_id": ch.id, "terms_hash": ch.terms_hash})
    import growth_api  # deferred: growth_api imports this module
    growth_api.emit_event(db, "challenge_joined", user_id=player_id, properties={"challenge_id": ch.id})
    db.commit()
    db.refresh(attempt)
    return _attempt_summary(attempt, ch)


@router.post("/api/v2/challenges/{challenge_id}/attempts", response_model=AttemptSummary)
def submit_attempt(
    challenge_id: int,
    req: AttemptSubmit,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
    _rl: None = Depends(_rl_challenge),
):
    """Link a finished run to the player's attempt and decide it from the stored route
    evidence. Idempotent for the same run; a rejected attempt may be retried with a new run
    while the challenge accepts submissions."""
    player_id = token_data["id"]
    ch = _get_challenge(db, challenge_id)
    if _refresh_challenge_status(db, ch):
        db.commit()
    attempt = db.query(models.ChallengeAttempt).filter(
        models.ChallengeAttempt.challenge_id == ch.id, models.ChallengeAttempt.user_id == player_id,
    ).first()
    if attempt is None:
        raise _api_error(409, "NOT_JOINED", "Join the challenge before submitting a run")
    if attempt.run_session_id == req.run_id and attempt.status != "joined":
        return _attempt_summary(attempt, ch)
    if attempt.status not in ("joined", "rejected"):
        raise _api_error(409, "ATTEMPT_ALREADY_DECIDED", "This attempt has already been submitted")
    if ch.status not in ("open", "closed"):
        raise _api_error(409, "CHALLENGE_NOT_OPEN", f"Challenge is {ch.status}")
    if attempt.terms_hash != ch.terms_hash:
        raise _api_error(409, "TERMS_CHANGED", "Challenge terms differ from the terms you joined")

    run = _get_player_run(db, req.run_id, player_id)
    if run.status != "closed":
        raise _api_error(409, "RUN_NOT_FINISHED", "Finish the run before submitting it")
    if run.created_at < attempt.joined_at:
        raise _api_error(409, "RUN_BEFORE_JOIN", "Only runs started after joining count")
    if run.finished_at is None or run.finished_at > ch.closes_at:
        raise _api_error(409, "RUN_AFTER_CLOSE", "The run finished after the challenge closed")
    used = db.query(models.ChallengeAttempt).filter(
        models.ChallengeAttempt.run_session_id == run.id, models.ChallengeAttempt.id != attempt.id,
    ).first()
    if used is not None:
        raise _api_error(409, "RUN_ALREADY_USED", "This run is already linked to another attempt")

    course = db.query(models.Course).filter(models.Course.id == ch.course_id).first()
    wall_clock = None
    if run.started_at and run.finished_at:
        wall_clock = (run.finished_at - run.started_at).total_seconds()
    ev = challenge_rules.evaluate_attempt(
        course_route=_course_route(course), course_distance=course.distance_m,
        target_seconds=ch.target_seconds, run_verification_status=run.verification_status,
        run_points=_run_points(db, run.id), run_duration=run.duration_seconds or 0.0,
        run_wall_clock_seconds=wall_clock,
    )
    attempt.run_session_id = run.id
    attempt.status = ev.status
    attempt.outcome = ev.outcome
    attempt.elapsed_seconds = ev.elapsed_seconds
    attempt.course_coverage = ev.coverage
    attempt.reason_codes_json = json.dumps(ev.reason_codes)
    attempt.submitted_at = _now_naive_utc()
    if ev.status == "accepted":
        _apply_attempt_outcome(db, attempt, ch)
    elif ev.status == "rejected":
        attempt.decided_at = attempt.submitted_at
    _audit(db, actor_type="player", actor_id=player_id, action="challenge.attempt_submitted",
           entity_type="challenge_attempt", entity_id=attempt.id,
           details={"challenge_id": ch.id, "run_id": run.id, "status": ev.status,
                    "outcome": ev.outcome, "reason_codes": ev.reason_codes,
                    "elapsed_seconds": ev.elapsed_seconds, "rules_version": ch.rules_version})
    db.commit()
    db.refresh(attempt)
    return _attempt_summary(attempt, ch)


@router.get("/api/v2/me/progression", response_model=ProgressionResponse)
def my_progression(
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Transparent progression: XP, versioned performance rank, badges, and the counts
    behind them."""
    player_id = token_data["id"]
    user = db.query(models.User).filter(models.User.id == player_id).first()
    xp = user.xp or 0
    badges = (
        db.query(models.UserBadge)
        .filter(models.UserBadge.user_id == player_id)
        .order_by(models.UserBadge.awarded_at.asc())
        .all()
    )
    defenses = (
        db.query(models.ChallengeAttempt)
        .join(models.Challenge, models.Challenge.id == models.ChallengeAttempt.challenge_id)
        .filter(models.Challenge.creator_id == player_id, models.ChallengeAttempt.outcome == "lost")
        .count()
    )
    outcomes: dict[str, int] = {
        outcome: n for outcome, n in
        db.query(models.ChallengeAttempt.outcome, func.count(models.ChallengeAttempt.id))
        .filter(models.ChallengeAttempt.user_id == player_id, models.ChallengeAttempt.outcome.in_(("won", "lost")))
        .group_by(models.ChallengeAttempt.outcome).all()
    }
    lifetime_m = db.query(func.sum(models.RunSession.distance_m)).filter(
        models.RunSession.user_id == player_id, models.RunSession.verification_status == "accepted").scalar()
    # Competition rank: one more than the number of active players with strictly more XP.
    global_rank = None if xp <= 0 else 1 + db.query(models.User).filter(
        models.User.xp > xp, models.User.suspended_at.is_(None)).count()
    return ProgressionResponse(
        xp=xp,
        performance_rank=challenge_rules.performance_rank(xp),
        rank_ladder_version=challenge_rules.RANK_LADDER_VERSION,
        rank_floor_xp=challenge_rules.rank_floor(xp),
        next_rank_xp=challenge_rules.next_rank_threshold(xp),
        verified_runs=db.query(models.RunSession).filter(
            models.RunSession.user_id == player_id, models.RunSession.verification_status == "accepted",
        ).count(),
        courses=db.query(models.Course).filter(models.Course.owner_id == player_id).count(),
        challenges_won=outcomes.get("won", 0),
        challenges_lost=outcomes.get("lost", 0),
        challenges_played=sum(outcomes.values()),
        lifetime_distance_km=round(float(lifetime_m or 0) / 1000.0, 1),
        global_rank=global_rank,
        defenses=defenses,
        badges=[
            BadgeOut(code=b.badge_code, label=challenge_rules.BADGES.get(b.badge_code, b.badge_code),
                     awarded_at=b.awarded_at)
            for b in badges
        ],
    )
