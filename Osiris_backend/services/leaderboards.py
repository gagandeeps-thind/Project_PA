"""Local ranking, team goal, and season scoring rules (growth release G3).

Pure functions only. Scoring is deliberately capped so a leaderboard rewards showing up
consistently, not overtraining: a day counts at most 10 km, and every active day earns a
flat bonus, so five easy days beat one exhausting one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Mapping

LEADERBOARD_RULES_VERSION = "leaderboard-rules-v1"

DAILY_COUNTED_M_CAP = 10_000
POINTS_PER_100M = 1
ACTIVE_DAY_BONUS = 10
MIN_COMMUNITY_SEASON_MEMBERS = 3

COMMUNITY_KINDS = (
    "running_club", "gym", "university", "trainer", "race", "cafe", "corporate", "other",
)

SCORING_EXPLAINER = (
    "1 point per 100 m of verified running or walking, counting at most 10 km a day, "
    "plus 10 points for every active day. Rest days never cost points."
)


@dataclass(frozen=True)
class Standing:
    key: int            # user id or community id
    points: int
    active_days: int
    distance_m: float
    rank: int


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "x"


def day_points(distance_m: float) -> int:
    if distance_m <= 0:
        return 0
    counted = min(distance_m, DAILY_COUNTED_M_CAP)
    return int(counted // 100) * POINTS_PER_100M + ACTIVE_DAY_BONUS


def score(days: Mapping[date, float]) -> tuple[int, int, float]:
    """(points, active_days, counted_distance_m) for one player's daily totals."""
    points = sum(day_points(m) for m in days.values())
    active = sum(1 for m in days.values() if m > 0)
    counted = sum(min(m, DAILY_COUNTED_M_CAP) for m in days.values() if m > 0)
    return points, active, counted


def rank(scores: Mapping[int, tuple[int, int, float]]) -> list[Standing]:
    """Competition ranking (1, 2, 2, 4) by points, then active days. Players with zero
    points are left out so an empty week does not display a last place."""
    rows = sorted(
        ((k, s) for k, s in scores.items() if s[0] > 0),
        key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]),
    )
    out: list[Standing] = []
    prev = None
    for i, (key, (points, active, dist)) in enumerate(rows, start=1):
        position = out[-1].rank if prev == (points, active) else i
        out.append(Standing(key=key, points=points, active_days=active, distance_m=dist, rank=position))
        prev = (points, active)
    return out


def team_progress_km(member_days: Mapping[int, Mapping[date, float]]) -> float:
    """Collective verified distance for a team goal, using the same daily cap."""
    total = 0.0
    for days in member_days.values():
        total += sum(min(m, DAILY_COUNTED_M_CAP) for m in days.values() if m > 0)
    return round(total / 1000.0, 1)


def community_season_scores(
    members: Mapping[int, list[int]], player_scores: Mapping[int, tuple[int, int, float]],
) -> dict[int, tuple[int, int, float]]:
    """Average points per season-entered member, so a 12-person club can beat a 300-person
    gym. Communities with fewer than three entered members are not ranked."""
    out: dict[int, tuple[int, int, float]] = {}
    for community_id, user_ids in members.items():
        entered = [player_scores[u] for u in user_ids if u in player_scores]
        if len(entered) < MIN_COMMUNITY_SEASON_MEMBERS:
            continue
        n = len(entered)
        out[community_id] = (
            round(sum(s[0] for s in entered) / n),
            round(sum(s[1] for s in entered) / n),
            sum(s[2] for s in entered) / n,
        )
    return out


# --- global boards (Social tab) ------------------------------------------------------

GLOBAL_BOARDS = ("distance", "pace", "reps", "rewards")
PACE_REFERENCE_M = 5_000.0
RIEGEL_EXPONENT = 1.06
PACE_MIN_DISTANCE_M = 1_000.0
REP_EXERCISES = ("pushup", "squat", "pullup", "plank")


def riegel_seconds(seconds: float, distance_m: float, reference_m: float = PACE_REFERENCE_M) -> float:
    """Riegel's endurance model, T2 = T1 * (D2 / D1) ** 1.06: the time this performance
    predicts over `reference_m`. It puts a fast 2 km and a steady 10 km on one scale, so the
    pace board ranks one number instead of trading distance against time."""
    if seconds <= 0 or distance_m <= 0:
        raise ValueError("seconds and distance must be positive")
    return seconds * (reference_m / distance_m) ** RIEGEL_EXPONENT


def rank_values(values: Mapping[int, float], *, ascending: bool) -> list[tuple[int, float, int]]:
    """Competition ranking (1, 2, 2, 4) as (key, value, rank). Ties break by key so the order
    is stable; zero values are left out of descending boards (nobody ranks last for nothing)."""
    rows = [(k, v) for k, v in values.items() if ascending or v > 0]
    rows.sort(key=lambda kv: (kv[1] if ascending else -kv[1], kv[0]))
    out: list[tuple[int, float, int]] = []
    for i, (key, value) in enumerate(rows, start=1):
        position = out[-1][2] if out and out[-1][1] == value else i
        out.append((key, value, position))
    return out
