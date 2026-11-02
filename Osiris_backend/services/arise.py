"""Arise rules: pure functions, no database."""
import math
import random
from typing import Iterable, Optional, Sequence

from services import challenges as rules

LatLng = tuple[float, float]

LOOP_CLOSE_M = 50.0          # a recorded run claims a domain only if it ends this close to its start
MAX_LEVEL = 15
XP_PER_LEVEL = 700
BASE_REPS = 30
REPS_PER_LEVEL = 5
MAX_REPS = 100
MIN_SET_REPS = 5
REST_CHOICES_S = (10, 15, 20, 25, 30)
M_PER_DEG_LAT = 111_195.0


def public_line(full: Sequence[LatLng], trimmed: Sequence[LatLng], hide_ends: bool) -> list[list[float]]:
    """The line other players see: the privacy-trimmed route, or the whole run when the owner shows the ends."""
    source = trimmed if hide_ends else rules.simplify_route(list(full))
    return [[p[0], p[1]] for p in source]


# --- domains ------------------------------------------------------------------------

def is_loop(points: Sequence[LatLng]) -> bool:
    return len(points) >= 4 and rules.distance_m(points[0], points[-1]) <= LOOP_CLOSE_M


def area_sqkm(points: Sequence[LatLng]) -> float:
    """Shoelace area on a local equirectangular projection; fine for park-sized loops."""
    if len(points) < 3:
        return 0.0
    lat0 = math.radians(sum(p[0] for p in points) / len(points))
    xy = [(p[1] * M_PER_DEG_LAT * math.cos(lat0), p[0] * M_PER_DEG_LAT) for p in points]
    twice = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(xy, xy[1:] + xy[:1], strict=True))
    return abs(twice) / 2 / 1_000_000


def centroid(points: Sequence[LatLng]) -> LatLng:
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def encloses(loop: Sequence[LatLng], point: LatLng) -> bool:
    """Ray casting: whether `point` is inside the polygon the loop draws."""
    inside = False
    lat, lng = point
    for (y1, x1), (y2, x2) in zip(loop, list(loop[1:]) + [loop[0]], strict=True):
        if (y1 > lat) != (y2 > lat) and lng < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


# --- workouts -----------------------------------------------------------------------

def player_level(xp: int) -> int:
    return min(MAX_LEVEL, 1 + max(0, xp) // XP_PER_LEVEL)


def total_reps(level: int) -> int:
    return min(MAX_REPS, BASE_REPS + REPS_PER_LEVEL * (max(1, level) - 1))


def generate_workout(seed: int, level: int, exercise_keys: Sequence[str]) -> list[dict]:
    """3–6 sets from the camera-countable exercises, `total_reps(level)` reps in all, 10–30 s rest after each.
    The same seed always gives the same workout."""
    rng = random.Random(seed)  # noqa: S311  (seeded so a workout can be replayed; not security)
    total = total_reps(level)
    count = rng.randint(3, 6)
    keys = list(exercise_keys)
    picks = rng.sample(keys, min(count, len(keys)))
    picks += [rng.choice(keys) for _ in range(count - len(picks))]
    reps = [MIN_SET_REPS] * count
    for _ in range(total - MIN_SET_REPS * count):
        reps[rng.randrange(count)] += 1
    return [{"exercise_key": k, "reps": r, "rest_s": rng.choice(REST_CHOICES_S)} for k, r in zip(picks, reps, strict=True)]


def workout_done(sets: Sequence[dict], sessions: Iterable[tuple[int, str, int]]) -> bool:
    """Every set matched by a different verified session `(id, exercise_key, reps_valid)` of the same exercise."""
    unused = list(sessions)
    for s in sets:
        match = next((x for x in unused if x[1] == s["exercise_key"] and x[2] >= s["reps"]), None)
        if match is None:
            return False
        unused.remove(match)
    return True


# --- attacks ------------------------------------------------------------------------

def attack_reasons(loop: Sequence[LatLng], distance_m: float, duration_s: float, domain_centre: LatLng,
                   domain_distance_m: float, domain_duration_s: float) -> list[str]:
    """Why an attack run does not beat the defender: it must enclose the domain, cover at least the
    defender's distance and take less time."""
    reasons = []
    if not is_loop(loop) or not encloses(loop, domain_centre):
        reasons.append("NOT_ENCLOSING")
    if distance_m < domain_distance_m:
        reasons.append("TOO_SHORT")
    if duration_s >= domain_duration_s:
        reasons.append("TOO_SLOW")
    return reasons


def difficulty(best_pace_s_per_km: Optional[float], level: int, distance_m: float, duration_s: float,
               workout_reps: int) -> tuple[str, float]:
    """`suggested` when the player's best recent pace beats the defender's time over the defender's distance
    and the workout fits their level; otherwise `hard`, with a score that grows with the gap."""
    predicted = best_pace_s_per_km * distance_m / 1000 if best_pace_s_per_km else None
    cap = total_reps(level)
    if predicted is not None and predicted < duration_s and workout_reps <= cap:
        return "suggested", 0.0
    time_gap = (predicted - duration_s) / duration_s if predicted is not None and duration_s > 0 else 1.0
    rep_gap = max(0, workout_reps - cap) / cap
    return "hard", max(0.0, time_gap) + rep_gap


# --- heatmaps -----------------------------------------------------------------------

HEAT_CELL_DEG = 0.001          # ~110 m north-south
HEAT_TRIM_M = 200.0            # the first and last stretch of every run stays private
NIGHT_START_H, NIGHT_END_H = 20, 5


def _trimmed(points: Sequence[LatLng], trim_m: float) -> list[LatLng]:
    """The points more than `trim_m` along the run from both its start and its finish."""
    if len(points) < 2:
        return []
    along = [0.0]
    for a, b in zip(points, points[1:], strict=False):
        along.append(along[-1] + rules.distance_m(a, b))
    total = along[-1]
    return [p for p, d in zip(points, along, strict=True) if trim_m < d < total - trim_m]


def heat_cells(runs: Iterable[tuple[int, Sequence[LatLng]]], min_players: int,
               cell_deg: float = HEAT_CELL_DEG, trim_m: float = HEAT_TRIM_M) -> list[tuple[float, float, int]]:
    """(lat, lng, runs) per grid cell the runs pass through, without their ends. Cells fewer than
    `min_players` distinct players crossed are dropped, so a shared heatmap never traces one person."""
    cells: dict[tuple[int, int], tuple[set[int], int]] = {}
    for user_id, points in runs:
        for key in {(round(p[0] / cell_deg), round(p[1] / cell_deg)) for p in _trimmed(points, trim_m)}:
            players, count = cells.get(key, (set(), 0))
            players.add(user_id)
            cells[key] = (players, count + 1)
    return sorted(
        (round(k[0] * cell_deg, 6), round(k[1] * cell_deg, 6), count)
        for k, (players, count) in cells.items() if len(players) >= min_players
    )


def is_night(started_utc, lng: float) -> bool:
    """Whether a run started between 20:00 and 05:00 local solar time (UTC + longitude / 15 h)."""
    hour = (started_utc.hour + started_utc.minute / 60 + lng / 15) % 24
    return hour >= NIGHT_START_H or hour < NIGHT_END_H
