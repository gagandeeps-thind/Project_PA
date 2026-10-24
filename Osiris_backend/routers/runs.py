"""Verified runs (API v2): create, start, upload route points, finish and read a run session."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import run_verifier
from core.clock import _now_naive_utc, _to_naive_utc
from core.errors import _api_error
from core.rate_limit import _rl_route
from core.security import get_active_player
from database import get_db
from schemas import RoutePointBatch, RunSessionCreate, RunSessionFinish, RunSessionStart, RunSessionSummary
from services import metrics, player_safety
from services.audit import _audit
from services.progression import _award_badge, get_rank, record_activity


router = APIRouter()


def _run_summary(session: models.RunSession, *, xp_awarded: int = 0, message: str = "Run session",
                 decision_metrics: Optional[dict] = None) -> RunSessionSummary:
    m = decision_metrics or {}
    return RunSessionSummary(
        id=session.id,
        activity_type=session.activity_type,
        status=session.status,
        verification_status=session.verification_status,
        point_count=session.point_count or 0,
        distance_m=round(session.distance_m or 0.0, 2),
        duration_seconds=round(session.duration_seconds or 0.0, 2),
        route_hash=session.route_hash,
        rejection_reason=session.rejection_reason,
        moving_seconds=m.get("moving_seconds"),
        elevation_gain_m=m.get("elevation_gain_m"),
        xp_awarded=xp_awarded,
        message=message,
    )


def _get_player_run(db: Session, run_id: int, player_id: int) -> models.RunSession:
    session = db.query(models.RunSession).filter(models.RunSession.id == run_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Run session not found")
    if session.user_id != player_id:
        raise HTTPException(status_code=403, detail="Run session belongs to another player")
    return session


@router.post("/api/v2/runs", response_model=RunSessionSummary, status_code=201)
def create_run_session(
    req: RunSessionCreate,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Create a run shell. The route is not accepted until it is finished and verified."""
    if player_safety.needs_location_consent(db, token_data["id"]):
        raise _api_error(403, "LOCATION_CONSENT_REQUIRED",
                         "Allow Osiris to use your location during runs before you start one")
    session = models.RunSession(
        user_id=token_data["id"],
        activity_type=req.activity_type.lower(),
        status="created",
        device_started_at=_to_naive_utc(req.device_started_at),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _run_summary(session, message="Run session created")


@router.post("/api/v2/runs/{run_id}/start", response_model=RunSessionSummary)
def start_run_session(
    run_id: int,
    req: RunSessionStart,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    session = _get_player_run(db, run_id, token_data["id"])
    if session.status == "active":
        return _run_summary(session, message="Run session already active")
    if session.status != "created":
        raise HTTPException(status_code=409, detail=f"Run session cannot start from status={session.status}")
    session.status = "active"
    session.started_at = _now_naive_utc()
    session.device_started_at = _to_naive_utc(req.device_started_at)
    session.updated_at = _now_naive_utc()
    db.commit()
    db.refresh(session)
    return _run_summary(session, message="Run session started")


@router.post("/api/v2/runs/{run_id}/points", response_model=RunSessionSummary)
def append_run_points(
    run_id: int,
    req: RoutePointBatch,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
    _rl: None = Depends(_rl_route),
):
    session = _get_player_run(db, run_id, token_data["id"])
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Route points can only be appended to an active run")
    existing_last = (
        db.query(models.RoutePoint)
        .filter(models.RoutePoint.run_session_id == run_id)
        .order_by(models.RoutePoint.sequence.desc())
        .first()
    )
    expected = (existing_last.sequence + 1) if existing_last else 0
    sequences = [point.sequence for point in req.points]
    if sequences != list(range(expected, expected + len(sequences))):
        raise HTTPException(status_code=409, detail=f"Route sequence must start at {expected} and be contiguous")
    for point in req.points:
        db.add(models.RoutePoint(
            run_session_id=run_id,
            sequence=point.sequence,
            t_ms=point.t_ms,
            lat=point.lat,
            lng=point.lng,
            accuracy_m=point.accuracy_m,
            speed_mps=point.speed_mps,
            altitude_m=point.altitude_m,
        ))
    session.point_count = (session.point_count or 0) + len(req.points)
    session.updated_at = _now_naive_utc()
    db.commit()
    db.refresh(session)
    return _run_summary(session, message=f"Accepted {len(req.points)} route points")


@router.post("/api/v2/runs/{run_id}/finish", response_model=RunSessionSummary)
def finish_run_session(
    run_id: int,
    req: RunSessionFinish,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    session = _get_player_run(db, run_id, token_data["id"])
    if session.status in ("submitted", "verifying", "closed"):
        if session.finish_idempotency_key == req.idempotency_key:
            return _run_summary(session, message="Run finish already processed")
        raise HTTPException(status_code=409, detail="Run session has already been finished")
    if session.status != "active":
        raise HTTPException(status_code=409, detail=f"Run session cannot finish from status={session.status}")

    points = (
        db.query(models.RoutePoint)
        .filter(models.RoutePoint.run_session_id == run_id)
        .order_by(models.RoutePoint.sequence.asc())
        .all()
    )
    if not points:
        raise HTTPException(status_code=400, detail="A run must contain route points before it can finish")

    session.status = "verifying"
    session.device_finished_at = _to_naive_utc(req.device_finished_at)
    session.finished_at = _now_naive_utc()
    session.finish_idempotency_key = req.idempotency_key
    session.updated_at = _now_naive_utc()
    db.flush()

    result = run_verifier.verify_route([
        {
            "sequence": point.sequence,
            "t_ms": point.t_ms,
            "lat": point.lat,
            "lng": point.lng,
            "accuracy_m": point.accuracy_m,
            "speed_mps": point.speed_mps,
            "altitude_m": point.altitude_m,
        }
        for point in points
    ], auto_pause_mps=req.auto_pause_mps)
    metrics.observe_run_verification(result.status, result.reason_codes)
    session.status = "closed"
    session.verification_status = result.status
    session.route_hash = result.route_hash
    session.distance_m = float(result.metrics["distance_m"])
    session.duration_seconds = float(result.metrics["duration_seconds"])
    session.rejection_reason = ",".join(result.reason_codes) if result.reason_codes else None
    decision = models.VerificationDecision(
        run_session_id=session.id,
        rules_version=run_verifier.RULES_VERSION,
        status=result.status,
        reason_codes_json=json.dumps(result.reason_codes),
        metrics_json=json.dumps(result.metrics),
    )
    db.add(decision)

    xp_awarded = 0
    if result.status == "accepted":
        user = db.query(models.User).filter(models.User.id == token_data["id"]).first()
        if user:
            xp_awarded = max(10, int(float(result.metrics["distance_m"]) // 100))
            user.xp += xp_awarded
            user.last_activity_date = session.finished_at
            user.rank = get_rank(user.xp, user.last_activity_date)
            record_activity(
                db, user, "run", max(1, int(float(result.metrics["distance_m"]) // 100)),
                session.finished_at, "run_session", related_id=session.id,
                verified=True, confidence=1.0,
            )
            _award_badge(db, user.id, "FIRST_VERIFIED_RUN")
            # Growth G1: daily quest / weekly goal rewards and funnel milestones.
            import growth_api  # deferred: growth_api imports this module
            xp_awarded += growth_api.on_run_accepted(db, user, session)["quest_xp"]
    _audit(
        db, actor_type="player", actor_id=token_data["id"], action="run.verified",
        entity_type="run_session", entity_id=session.id,
        details={"status": result.status, "reason_codes": result.reason_codes,
                 "rules_version": run_verifier.RULES_VERSION},
    )
    db.commit()
    db.refresh(session)
    message = "Run verified and accepted" if result.status == "accepted" else "Run rejected by verification rules"
    return _run_summary(session, xp_awarded=xp_awarded, message=message, decision_metrics=result.metrics)


@router.get("/api/v2/runs/{run_id}", response_model=RunSessionSummary)
def get_run_session(
    run_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    session = _get_player_run(db, run_id, token_data["id"])
    decision = db.query(models.VerificationDecision.metrics_json).filter(
        models.VerificationDecision.run_session_id == session.id).scalar()
    return _run_summary(session, message="Run session status", decision_metrics=json.loads(decision) if decision else None)
