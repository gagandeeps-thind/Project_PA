"""Camera-verified exercise endpoints (push-ups, squats, plank, ...).

The app runs pose estimation and rep counting on the device and uploads a summary per set.
The server re-checks the summary (`services.exercises.evaluate`), stores it, and grants
capped XP for verified sets. Imported at the end of `growth_api.py`; registers its router on
`main.app` when the import completes.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from growth_api import get_or_create_profile
from growth_safety import record_consent
from main import _api_error, _audit, _now_naive_utc, _rate_limit, app, get_active_player, get_db, get_rank
from services import exercises as exercise_rules
from services import metrics
from services import player_safety
from services import quests as quest_rules

router = APIRouter()

MAX_REPS = 2_000
MAX_LIST_LIMIT = 100

# A set takes seconds to perform; 30 uploads a minute still lets a phone drain an offline
# backlog quickly (the queue keeps a 429'd set and retries it) while capping row spam.
_rl_exercise = _rate_limit(30, 60, "exercise")


class ExerciseSessionIn(BaseModel):
    client_session_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    exercise_key: str = Field(max_length=32)
    rules_version: str = Field(max_length=32)
    started_at: Optional[datetime] = None
    duration_s: float = Field(ge=0, le=exercise_rules.MAX_SESSION_S)
    reps_attempted: int = Field(0, ge=0, le=MAX_REPS)
    reps_valid: int = Field(0, ge=0, le=MAX_REPS)
    hold_s: float = Field(0.0, ge=0, le=exercise_rules.MAX_SESSION_S)
    form_score: float = Field(0.0, ge=0, le=1)
    client_verdict: Literal["verified", "review", "rejected"]
    reason_codes: List[str] = Field(default_factory=list, max_length=20)
    rep_durations_s: List[float] = Field(default_factory=list, max_length=MAX_REPS)


class ExerciseSessionOut(BaseModel):
    id: int
    client_session_id: str
    exercise_key: str
    status: str
    reason_codes: List[str]
    reps_valid: int
    hold_s: float
    xp_awarded: int
    total_xp: int
    daily_xp_remaining: int
    duplicate: bool
    created_at: datetime


class ExerciseConsentIn(BaseModel):
    granted: bool
    # On withdrawal, also erase the exercise sets stored on the server. XP already earned stays.
    delete_data: bool = False


class ExerciseConsentOut(BaseModel):
    granted: bool
    policy_version: Optional[str]
    updated_at: Optional[datetime]
    deleted_sets: int = 0


class ExerciseHistoryOut(BaseModel):
    today_xp: int
    daily_xp_cap: int
    sessions: List[ExerciseSessionOut]


def _earned_today(db: Session, user_id: int, local_date: str) -> dict[str, int]:
    rows = db.query(models.ExerciseSession.exercise_key, func.coalesce(func.sum(models.ExerciseSession.xp_awarded), 0)).filter(
        models.ExerciseSession.user_id == user_id, models.ExerciseSession.local_date == local_date,
    ).group_by(models.ExerciseSession.exercise_key).all()
    return {key: int(xp) for key, xp in rows}


def _out(row: models.ExerciseSession, user: models.User, today_total: int, duplicate: bool) -> ExerciseSessionOut:
    return ExerciseSessionOut(
        id=row.id, client_session_id=row.client_session_id, exercise_key=row.exercise_key, status=row.status,
        reason_codes=json.loads(row.reason_codes_json), reps_valid=row.reps_valid, hold_s=row.hold_s,
        xp_awarded=row.xp_awarded, total_xp=user.xp or 0,
        daily_xp_remaining=max(0, exercise_rules.DAILY_EXERCISE_XP_CAP - today_total),
        duplicate=duplicate, created_at=row.created_at,
    )


CONSENT_KIND = "exercise_camera"


def _consent_out(db: Session, uid: int, deleted: int = 0) -> ExerciseConsentOut:
    rec = player_safety.latest_consent(db, uid, CONSENT_KIND)
    return ExerciseConsentOut(
        granted=bool(rec and rec.granted), policy_version=rec.policy_version if rec else None,
        updated_at=rec.created_at if rec else None, deleted_sets=deleted,
    )


@router.get("/api/v2/me/exercise-consent", response_model=ExerciseConsentOut)
def get_exercise_consent(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    return _consent_out(db, token_data["id"])


@router.put("/api/v2/me/exercise-consent", response_model=ExerciseConsentOut)
def set_exercise_consent(
    req: ExerciseConsentIn, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player),
):
    """Explicit, revocable consent to count exercises with the camera and keep the results
    (rep timings are health data). Each change is a new ledger row; withdrawal stops uploads
    and can erase the stored sets."""
    uid = token_data["id"]
    current = player_safety.latest_consent(db, uid, CONSENT_KIND)
    if current is None or current.granted != req.granted:
        record_consent(db, uid, CONSENT_KIND, req.granted)
        _audit(db, actor_type="player", actor_id=uid, entity_type="user", entity_id=uid,
               action="consent.exercise_camera." + ("granted" if req.granted else "withdrawn"))
    deleted = 0
    if not req.granted and req.delete_data:
        deleted = db.query(models.ExerciseSession).filter(models.ExerciseSession.user_id == uid).delete(
            synchronize_session=False)
        _audit(db, actor_type="player", actor_id=uid, entity_type="user", entity_id=uid,
               action="exercise.data_deleted", details={"sets": deleted})
    db.commit()
    return _consent_out(db, uid, deleted)


@router.get("/api/v2/exercises")
def list_exercises(_token: dict = Depends(get_active_player)):
    """The exercise catalog and thresholds the on-device rep engine runs with."""
    return exercise_rules.catalog_payload()


@router.post("/api/v2/exercise-sessions", response_model=ExerciseSessionOut, status_code=201)
def submit_exercise_session(
    req: ExerciseSessionIn, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player),
    _rl: None = Depends(_rl_exercise),
):
    """Store a device-verified set and grant capped XP if the server re-check agrees.
    Idempotent per `client_session_id`: a retry returns the stored result with 200."""
    uid = token_data["id"]
    if req.exercise_key not in exercise_rules.BY_KEY:
        raise _api_error(422, "UNKNOWN_EXERCISE", "This exercise is not in the catalog.")
    unknown = [c for c in req.reason_codes if c not in exercise_rules.REASON_CODES]
    if unknown:
        raise _api_error(422, "UNKNOWN_REASON_CODE", "Unknown reason code: " + unknown[0])

    user = db.query(models.User).filter(models.User.id == uid).first()
    profile = get_or_create_profile(db, user)
    local_date = quest_rules.local_date(_now_naive_utc(), profile.utc_offset_minutes).isoformat()

    existing = db.query(models.ExerciseSession).filter(
        models.ExerciseSession.user_id == uid, models.ExerciseSession.client_session_id == req.client_session_id,
    ).first()
    if existing is not None:
        today_total = sum(_earned_today(db, uid, existing.local_date).values())
        return JSONResponse(status_code=200, content=json.loads(_out(existing, user, today_total, True).model_dump_json()))
    # A retry of a set stored before withdrawal is answered above; nothing new is stored without consent.
    consent = player_safety.latest_consent(db, uid, CONSENT_KIND)
    if consent is None or not consent.granted:
        raise _api_error(403, "EXERCISE_CONSENT_REQUIRED",
                         "Allow camera exercise counting in the app before uploading sets.")

    decision = exercise_rules.evaluate(exercise_rules.SessionClaim(
        exercise_key=req.exercise_key, rules_version=req.rules_version, duration_s=req.duration_s,
        reps_attempted=req.reps_attempted, reps_valid=req.reps_valid, hold_s=req.hold_s,
        rep_durations_s=req.rep_durations_s, client_verdict=req.client_verdict, client_reasons=req.reason_codes,
    ))
    earned = _earned_today(db, uid, local_date)
    xp = exercise_rules.capped_xp(decision.base_xp, req.exercise_key,
                                  earned.get(req.exercise_key, 0), sum(earned.values()))
    started = req.started_at.replace(tzinfo=None) if req.started_at else None
    row = models.ExerciseSession(
        user_id=uid, client_session_id=req.client_session_id, exercise_key=req.exercise_key,
        rules_version=req.rules_version, device_started_at=started, duration_s=req.duration_s,
        reps_attempted=req.reps_attempted, reps_valid=req.reps_valid, hold_s=req.hold_s,
        form_score=req.form_score, client_verdict=req.client_verdict, status=decision.status,
        reason_codes_json=json.dumps(list(decision.reasons)),
        metrics_json=json.dumps({"rep_durations_s": [round(d, 3) for d in req.rep_durations_s]}),
        xp_awarded=xp, local_date=local_date,
    )
    db.add(row)
    if xp:
        user.xp = (user.xp or 0) + xp
        user.rank = get_rank(user.xp, user.last_activity_date)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent retry of the same set won the insert; report its stored result.
        db.rollback()
        existing = db.query(models.ExerciseSession).filter(
            models.ExerciseSession.user_id == uid, models.ExerciseSession.client_session_id == req.client_session_id,
        ).one()
        user = db.query(models.User).filter(models.User.id == uid).one()
        today_total = sum(_earned_today(db, uid, existing.local_date).values())
        return JSONResponse(status_code=200, content=json.loads(_out(existing, user, today_total, True).model_dump_json()))
    db.refresh(row)
    metrics.observe_exercise_verification(req.exercise_key, decision.status, list(decision.reasons))
    return _out(row, user, sum(earned.values()) + xp, False)


@router.get("/api/v2/me/exercise-sessions", response_model=ExerciseHistoryOut)
def my_exercise_sessions(
    limit: int = 20, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    user = db.query(models.User).filter(models.User.id == uid).first()
    profile = get_or_create_profile(db, user)
    db.commit()
    local_date = quest_rules.local_date(_now_naive_utc(), profile.utc_offset_minutes).isoformat()
    today_total = sum(_earned_today(db, uid, local_date).values())
    rows = db.query(models.ExerciseSession).filter(models.ExerciseSession.user_id == uid).order_by(
        models.ExerciseSession.id.desc()).limit(max(1, min(limit, MAX_LIST_LIMIT))).all()
    return ExerciseHistoryOut(
        today_xp=today_total, daily_xp_cap=exercise_rules.DAILY_EXERCISE_XP_CAP,
        sessions=[_out(r, user, today_total, False) for r in rows],
    )


app.include_router(router)
