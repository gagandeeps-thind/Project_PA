"""Start tab rules: the activity catalog, telemetry series cleaning and stats, personal records,
group challenge progress, and the motivation quotes. Pure functions except `connection_ids`
and `group_progress`, which read the database."""
import random
from collections import defaultdict
from typing import Any, Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from services import player_safety
from services.exercises import CATALOG as CAMERA_CATALOG

MAX_POINTS = 720
CHANNELS = ("hr", "power", "speed", "elevation")
RANGES = {"hr": (25.0, 250.0), "power": (0.0, 3000.0), "elevation": (-500.0, 9000.0)}
UNITS = {"distance_m": "m", "duration_s": "s", "reps": "reps"}
ELEVATION_HYSTERESIS_M = 1.0

# (key, name, kind, metric, instantaneous speed cap in m/s). Speed caps bound both the speed
# series and a session's average speed (distance / duration).
_CARDIO = (
    ("run", "Run", "gps", "distance_m", 12.5),
    ("walk", "Walk", "gps", "distance_m", 3.5),
    ("hike", "Hike", "gps", "distance_m", 3.5),
    ("trail", "Trail run", "gps", "distance_m", 10.0),
    ("cycle", "Ride", "gps", "distance_m", 25.0),
    ("indoor_cycle", "Indoor ride", "sensor", "distance_m", 25.0),
    ("swim", "Swim", "sensor", "distance_m", 3.0),
    ("row", "Row", "sensor", "distance_m", 7.0),
    ("elliptical", "Elliptical", "sensor", "duration_s", 6.0),
    ("stairs", "Stair climb", "sensor", "duration_s", 3.0),
    ("hiit", "HIIT", "sensor", "duration_s", 10.0),
    ("strength", "Strength", "sensor", "duration_s", 5.0),
    ("yoga", "Yoga", "sensor", "duration_s", 2.0),
)

ACTIVITIES: list[dict[str, Any]] = [
    {"key": e["key"], "name": e["name"], "kind": "camera",
     "metric": "duration_s" if e["kind"] == "hold" else "reps", "max_speed_mps": 0.0, "gps": False}
    for e in CAMERA_CATALOG
] + [
    {"key": key, "name": name, "kind": kind, "metric": metric, "max_speed_mps": cap, "gps": kind == "gps"}
    for key, name, kind, metric, cap in _CARDIO
]
BY_KEY = {a["key"]: a for a in ACTIVITIES}
METRICS = ("distance_m", "duration_s", "reps", "sessions")

QUOTES: tuple[tuple[str, str], ...] = (
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
    ("Well done is better than well said.", "Benjamin Franklin"),
    ("Energy and persistence conquer all things.", "Benjamin Franklin"),
    ("A journey of a thousand miles begins with a single step.", "Lao Tzu"),
    ("We are what we repeatedly do.", "Will Durant"),
    ("The body achieves what the mind believes.", "Osiris"),
    ("Start where you are. Use what you have. Do what you can.", "Arthur Ashe"),
    ("Strength does not come from winning. Your struggles develop your strengths.", "Arnold Schwarzenegger"),
    ("Act as if what you do makes a difference. It does.", "William James"),
    ("Small daily improvements are the key to staggering long-term results.", "Osiris"),
    ("Fall seven times, stand up eight.", "Japanese proverb"),
    ("The only bad workout is the one that didn't happen.", "Osiris"),
    ("Motivation gets you going. Habit keeps you going.", "Jim Ryun"),
    ("Discipline is choosing between what you want now and what you want most.", "Osiris"),
    ("He conquers who endures.", "Persius"),
    ("Courage is grace under pressure.", "Ernest Hemingway"),
    ("What we achieve inwardly will change outer reality.", "Plutarch"),
    ("No man ever steps in the same river twice.", "Heraclitus"),
    ("First say to yourself what you would be; then do what you have to do.", "Epictetus"),
    ("Waste no more time arguing what a good man should be. Be one.", "Marcus Aurelius"),
    ("The impediment to action advances action. What stands in the way becomes the way.", "Marcus Aurelius"),
    ("Every rep is a vote for the person you are becoming.", "Osiris"),
    ("Sweat now, shine later.", "Osiris"),
    ("Run the mile you are in.", "Osiris"),
    ("Your only competition is who you were yesterday.", "Osiris"),
    ("Pain is temporary. Pride is forever.", "Osiris"),
    ("Earn your domain, one step at a time.", "Osiris"),
    ("Rise, Osirian. The day is yours to claim.", "Osiris"),
    ("Slow progress is still progress.", "Osiris"),
)


def quote(exclude: Optional[int] = None, rng: Optional[random.Random] = None) -> dict[str, Any]:
    """A random quote, never the one the player saw last ([exclude])."""
    choices = [i for i in range(len(QUOTES)) if i != exclude]
    i = (rng or random).choice(choices)  # noqa: S311 - not security-sensitive
    text, author = QUOTES[i]
    return {"id": i, "text": text, "author": author}


def clean_series(series: dict[str, list[list[float]]], duration_s: float, max_speed: float) -> dict[str, list[list[float]]]:
    """Keeps well-formed, in-range points inside the session, sorted by time. Out-of-range
    points are dropped rather than rejecting the session: a sensor glitch should not lose a workout."""
    ranges = {**RANGES, "speed": (0.0, max_speed)}
    out: dict[str, list[list[float]]] = {}
    for channel in CHANNELS:
        low, high = ranges[channel]
        points = []
        for p in series.get(channel) or []:
            if len(p) != 2:
                continue
            t, v = float(p[0]), float(p[1])
            if 0.0 <= t <= duration_s + 1.0 and low <= v <= high:
                points.append([round(t, 1), round(v, 1)])
        points.sort(key=lambda p: p[0])
        if points:
            out[channel] = points
    return out


def elevation_gain(values: Iterable[float], hysteresis: float = ELEVATION_HYSTERESIS_M) -> float:
    """Sum of climbs, ignoring wobble smaller than [hysteresis] metres."""
    gain, ref = 0.0, None
    for v in values:
        if ref is None or v < ref:
            ref = v
        elif v - ref >= hysteresis:
            gain += v - ref
            ref = v
    return round(gain, 1)


def stats(series: dict[str, list[list[float]]]) -> dict[str, Optional[float]]:
    """Avg/min/max per channel, plus elevation gain; None where a channel has no points."""
    out: dict[str, Optional[float]] = {}
    for channel, prefix in (("hr", "hr"), ("power", "power"), ("speed", "speed"), ("elevation", "elev")):
        values = [p[1] for p in series.get(channel, [])]
        avg = round(sum(values) / len(values), 1) if values else None
        lo = min(values) if values else None
        hi = max(values) if values else None
        if prefix == "elev":
            out.update(elev_min=lo, elev_max=hi)
        elif prefix == "speed":
            out.update(speed_avg=avg, speed_max=hi)
        else:
            out.update({f"{prefix}_avg": avg, f"{prefix}_min": lo, f"{prefix}_max": hi})
    out["elevation_gain_m"] = elevation_gain(p[1] for p in series.get("elevation", []))
    return out


def metric_value(row: models.TrainingSession, metric: str) -> float:
    if metric == "sessions":
        return 1.0
    return float(getattr(row, metric) or 0.0)


def connection_ids(db: Session, uid: int) -> set[int]:
    """Players this one follows or is followed by, less anyone either side blocked."""
    rows = db.query(models.UserFollow.follower_id, models.UserFollow.followed_id).filter(
        (models.UserFollow.follower_id == uid) | (models.UserFollow.followed_id == uid)).all()
    ids = {a if b == uid else b for a, b in rows}
    return ids - player_safety.blocked_user_ids(db, uid) - {uid}


def group_progress(db: Session, challenges: list[models.GroupChallenge]) -> dict[int, dict[int, float]]:
    """challenge id -> {joined member id -> progress}. Only `mode=challenge` sessions of the
    challenge's activity inside its window count."""
    if not challenges:
        return {}
    members: dict[int, set[int]] = defaultdict(set)
    for cid, user_id in db.query(models.GroupChallengeMember.challenge_id, models.GroupChallengeMember.user_id).filter(
            models.GroupChallengeMember.challenge_id.in_([c.id for c in challenges]),
            models.GroupChallengeMember.status == "joined").all():
        members[cid].add(user_id)
    out: dict[int, dict[int, float]] = {}
    for ch in challenges:
        ids = members.get(ch.id, set())
        progress = {uid: 0.0 for uid in ids}
        if ids:
            column = func.count(models.TrainingSession.id) if ch.metric == "sessions" else func.sum(
                getattr(models.TrainingSession, ch.metric))
            rows = db.query(models.TrainingSession.user_id, column).filter(
                models.TrainingSession.user_id.in_(ids),
                models.TrainingSession.activity_key == ch.activity_key,
                models.TrainingSession.mode == "challenge",
                models.TrainingSession.started_at >= ch.starts_at,
                models.TrainingSession.started_at < ch.ends_at,
            ).group_by(models.TrainingSession.user_id).all()
            for uid, value in rows:
                progress[uid] = round(float(value or 0.0), 1)
        out[ch.id] = progress
    return out
