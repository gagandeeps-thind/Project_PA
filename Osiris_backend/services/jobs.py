"""Background jobs run by the scheduler in main.py: XP decay, telemetry and route-point
retention, and challenge settlement."""
import logging
import os
from datetime import timedelta

import database
import models
from core.clock import _now_naive_utc
from services.challenge_store import _refresh_challenge_status
from services.progression import get_rank

logger = logging.getLogger(__name__)


# --- Background Tasks (Cron Logic) ---

def process_daily_decay():
    """Background task triggered daily. Deducts XP and ends streaks if last activity is > 24 hours."""
    # We have to open a manual database session here because this runs outside of normal HTTP requests
    db = database.SessionLocal()
    try:
        users = db.query(models.User).all()
        for user in users:
            now = _now_naive_utc()
            hours_since_activity = (now - user.last_activity_date).total_seconds() / 3600

            # If they haven't logged in/completed an activity in over a day
            if hours_since_activity > 24:
                user.streak = 0
                # Deduct 5% of XP daily as a penalty
                penalty = int(user.xp * 0.05)
                user.xp = max(0, user.xp - penalty)

            # Re-evaluate rank in case their XP dropped below a tier threshold, or they hit 30-day inactivity
            user.rank = get_rank(user.xp, user.last_activity_date)
        # Save all changes to the database
        db.commit()
    finally:
        db.close()


def process_telemetry_ttl():
    """v2.11 nightly job — deletes raw `TelemetryData` sample blobs older than the TTL.
    `TelemetrySession` metadata stays so analytics queries against
    'how many workouts per activity_type per week' still work indefinitely; only the
    expensive raw samples expire.

    Default TTL: 90 days. Override with `OSIRIS_TELEMETRY_TTL_DAYS=<N>`. Set to 0 or
    negative to disable the job entirely (no expiry — useful for low-volume pilots that
    want to keep all raw data for ML training)."""
    ttl_days = int(os.environ.get("OSIRIS_TELEMETRY_TTL_DAYS", "90"))
    if ttl_days <= 0:
        return  # disabled
    cutoff = _now_naive_utc() - timedelta(days=ttl_days)
    db = database.SessionLocal()
    try:
        # Find session ids whose creation predates the cutoff. Joining via session_id keeps
        # the delete cheap on SQLite (a single IN-list).
        old_session_ids = [
            row.id for row in
            db.query(models.TelemetrySession.id).filter(models.TelemetrySession.created_at < cutoff).all()
        ]
        if old_session_ids:
            deleted = (
                db.query(models.TelemetryData)
                .filter(models.TelemetryData.session_id.in_(old_session_ids))
                .delete(synchronize_session=False)
            )
            db.commit()
            logger.info("telemetry-ttl", extra={"ctx": {"deleted": deleted, "ttl_days": ttl_days,
                                                     "sessions": len(old_session_ids)}})
    finally:
        db.close()


# Raw GPS samples are personal location history (Security plan §2: keep raw telemetry only as
# long as needed). They must outlive the longest challenge window (720 h) plus its submission
# grace, because a run can be linked to an attempt until the challenge closes; 45 days does.
ROUTE_POINT_RETENTION_DAYS = int(os.environ.get("OSIRIS_ROUTE_POINT_TTL_DAYS", "45"))


def process_route_point_ttl() -> int:
    """Nightly job: delete raw RoutePoint rows of closed runs that finished before the
    retention window. The RunSession summary (distance, duration, verification status, route
    hash) and its VerificationDecision stay, as do courses, which keep their own trimmed
    route. Runs whose challenge attempt awaits human review keep their evidence until it is
    decided. Returns the number of points deleted; 0 or a negative TTL disables the job."""
    if ROUTE_POINT_RETENTION_DAYS <= 0:
        return 0
    cutoff = _now_naive_utc() - timedelta(days=ROUTE_POINT_RETENTION_DAYS)
    db = database.SessionLocal()
    try:
        under_review = db.query(models.ChallengeAttempt.run_session_id).filter(
            models.ChallengeAttempt.status == "review_required",
            models.ChallengeAttempt.run_session_id.isnot(None),
        )
        expired_runs = db.query(models.RunSession.id).filter(
            models.RunSession.status == "closed",
            models.RunSession.finished_at < cutoff,
            models.RunSession.id.notin_(under_review),
        )
        deleted = (
            db.query(models.RoutePoint)
            .filter(models.RoutePoint.run_session_id.in_(expired_runs))
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            logger.info("route-point-ttl", extra={"ctx": {"deleted": deleted, "retention_days": ROUTE_POINT_RETENTION_DAYS}})
        return deleted
    finally:
        db.close()


def process_challenge_settlement():
    """R2 hourly job — closes challenges past their window and settles them once the
    submission grace period has passed and no attempt awaits review. Reads also advance
    status lazily; this job makes sure untouched challenges settle too."""
    db = database.SessionLocal()
    try:
        now = _now_naive_utc()
        live = db.query(models.Challenge).filter(models.Challenge.status.in_(("open", "closed"))).all()
        changed = False
        for ch in live:
            changed |= _refresh_challenge_status(db, ch, now)
        if changed:
            db.commit()
    finally:
        db.close()
