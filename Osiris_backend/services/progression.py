"""Player progression: rank, title, avatar class, attribute stats, XP and badges, activity log."""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

import models
from core.clock import _now_naive_utc
from schemas import ActivityProof



def get_avatar_class(preferred_path: str) -> str:
    """
    Maps user's chosen path to a physical class (Dynamic 2D Sprite logic)
    to avoid the BMI body-shaming flaw.
    """
    path = preferred_path.lower()
    if path == "strength":
        return "Tank"      # Vanguard/Heavy
    elif path == "cardio":
        return "Assassin"  # Striker/Fast
    else:
        return "Mage"      # Balanced/Support

def get_rank(xp: int, last_activity_date: Optional[datetime] = None) -> str:
    """Calculates Grade/Title based on Master GDD Tier System.
    NOTE: inactivity comparison uses server-side 'now' intentionally — decay is a system-owned
    concept; relying on a possibly-drifted device clock here would be exploitable."""
    if last_activity_date:
        days_inactive = (_now_naive_utc() - last_activity_date).total_seconds() / 86400
        if days_inactive > 30:
            # Harsh punishment for 30+ days of inactivity
            return "F - The Dishonored"

    if xp < 500: return "D - Beginner"
    if xp < 1000: return "C - Intermediate"
    if xp < 2500: return "B - Advanced"
    if xp < 5000: return "A - Saint"
    if xp < 7500: return "S - King"
    if xp < 10000: return "SS - Emperor"
    return "SSS - God"

def get_title(cumulative_area: float) -> str:
    """Calculates Map Title based on total km2 owned."""
    if cumulative_area >= 100.0: return "Sovereign"
    if cumulative_area >= 20.0: return "High Lord"
    if cumulative_area >= 5.0: return "Lord"
    if cumulative_area >= 1.0: return "Warden"
    return "Unawakened"


# --- Epic 6: Party Attribute Stats ---
# Maps a verified activity's defense_type to the User column it feeds.
DEFENSE_TYPE_TO_STAT = {
    "pushups": "str_stat",
    "squats": "str_stat",
    "sprint": "agi_stat",
    "burpees": "agi_stat",
    "run": "end_stat",
    "walk": "end_stat",
    "plank": "con_stat",
    "hold": "con_stat",
}

def increment_stat_from_activity(user: models.User, defense_type: str, score: int) -> Optional[str]:
    """Adds `score` to the matching attribute column on `user` based on activity type.
    Returns the stat column name touched, or None if the activity type isn't mapped."""
    if score <= 0:
        return None
    stat_col = DEFENSE_TYPE_TO_STAT.get((defense_type or "").lower())
    if stat_col is None:
        return None
    setattr(user, stat_col, (getattr(user, stat_col) or 0) + score)
    return stat_col

def record_activity(
    db: Session,
    user: models.User,
    activity_type: str,
    score: int,
    occurred_at: datetime,
    source: str,
    related_id: Optional[int] = None,
    verified: bool = False,
    confidence: float = 1.0,
    proof: Optional["ActivityProof"] = None,
) -> Optional[models.ActivityLog]:
    """Single entry point for the activity history table. Three writes happen here:

    1. **Lifetime stat increment** on the User row (cheap aggregate read path).
    2. **`ActivityLog` row** for the 30-day rolling Party-Stats window.
    3. **`TelemetrySession` + per-sensor `TelemetryData` rows** if a `proof` is attached —
       gives the ML training pipeline raw sensor data linked back to the gameplay outcome.

    Returns the new ActivityLog row (uncommitted) or None when score is non-positive."""
    if score <= 0:
        return None
    stat_col = increment_stat_from_activity(user, activity_type, score)
    log = models.ActivityLog(
        user_id=user.id,
        activity_type=(activity_type or "").lower(),
        score=score,
        stat_column=stat_col,
        confidence=confidence,
        verified=1 if verified else 0,
        source=source,
        related_id=related_id,
        occurred_at=occurred_at,
    )
    db.add(log)

    # If the caller also gave us the raw proof, archive sensor data linked to this log row.
    if proof is not None:
        db.flush()  # need log.id before linking telemetry rows
        _persist_telemetry(db, user.id, log.id, proof, occurred_at, verified, confidence)

    return log


def _persist_telemetry(
    db: Session,
    user_id: int,
    activity_log_id: int,
    proof: "ActivityProof",
    occurred_at: datetime,
    verified: bool,
    confidence: float,
) -> None:
    """Writes one TelemetrySession (metadata) + N TelemetryData rows (one per non-empty
    sensor channel). Pose, when present, is stored as a single-element JSON array under
    sensor_type='pose'."""
    session = models.TelemetrySession(
        user_id=user_id,
        activity_log_id=activity_log_id,
        activity_type=(proof.activity_type or "").lower(),
        declared_score=proof.declared_score,
        duration_seconds=proof.duration_seconds,
        confidence=confidence,
        verified=1 if verified else 0,
        sample_count_accel=len(proof.accelerometer),
        sample_count_gyro=len(proof.gyroscope),
        sample_count_mag=len(proof.magnetometer),
        sample_count_gps=len(proof.gps),
        sample_count_barometer=len(proof.barometer),
        has_pose=proof.pose is not None,
        occurred_at=occurred_at,
    )
    db.add(session)
    db.flush()  # session.id needed for child rows

    # Per-sensor archives. Empty channels skipped to avoid noise rows.
    sensor_blobs = [
        ("accel",        [s.model_dump() for s in proof.accelerometer]),
        ("gyro",         [s.model_dump() for s in proof.gyroscope]),
        ("magnetometer", [s.model_dump() for s in proof.magnetometer]),
        ("gps",          [s.model_dump() for s in proof.gps]),
        ("barometer",    [s.model_dump() for s in proof.barometer]),
    ]
    for sensor_type, samples in sensor_blobs:
        if not samples:
            continue
        db.add(models.TelemetryData(
            session_id=session.id,
            sensor_type=sensor_type,
            sample_count=len(samples),
            samples_json=json.dumps(samples, default=str),
        ))
    if proof.pose is not None:
        db.add(models.TelemetryData(
            session_id=session.id,
            sensor_type="pose",
            sample_count=1,
            samples_json=json.dumps(proof.pose.model_dump(), default=str),
        ))

def get_party_role(user: models.User) -> tuple[str, str]:
    """Returns (role, leading_stat_name) based on the user's highest attribute.
    Ties broken by the order STR > AGI > END > CON (favors melee on equal stats)."""
    stats = [
        ("str_stat", user.str_stat or 0, "Vanguard"),
        ("agi_stat", user.agi_stat or 0, "Striker"),
        ("end_stat", user.end_stat or 0, "Scout"),
        ("con_stat", user.con_stat or 0, "Strategist"),
    ]
    leading = max(stats, key=lambda s: s[1])
    return leading[2], leading[0]


def _award_badge(db: Session, user_id: int, badge_code: str) -> bool:
    """Idempotently grant a badge. Returns True only when newly awarded."""
    exists = db.query(models.UserBadge).filter(
        models.UserBadge.user_id == user_id, models.UserBadge.badge_code == badge_code,
    ).first()
    if exists:
        return False
    db.add(models.UserBadge(user_id=user_id, badge_code=badge_code))
    return True


def _adjust_xp(user: models.User, delta: int) -> None:
    user.xp = max(0, (user.xp or 0) + delta)
    user.rank = get_rank(user.xp, user.last_activity_date)
