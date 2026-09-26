"""Course and challenge domain rules for the R2 pilot (PRD-005/006/007, ADR-004/005).

Pure functions only: no database session, no HTTP. `main.py` loads rows, calls these,
and owns the transaction. Keeping the rules here lets them be unit-tested directly and
versioned independently of the endpoints.

Economy note (ADR-005): challenges in this release carry no crystal stakes. Rewards are
XP and badges only; `ENTRY_CRYSTALS` is pinned to 0 and part of the hashed terms so a
later paid release cannot silently reinterpret an old challenge.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

COURSE_RULES_VERSION = "course-rules-v1"
CHALLENGE_RULES_VERSION = "challenge-rules-v1"
RANK_LADDER_VERSION = "rank-ladder-v1"

# Course registration
MIN_COURSE_DISTANCE_M = 400.0
MAX_COURSE_DISTANCE_M = 42_195.0
MAX_COURSE_POINTS = 200
LOOP_THRESHOLD_M = 100.0
MAX_ACTIVE_COURSES_PER_USER = 10
# Privacy zone: the first and last stretch of the source run is cut off before the route
# becomes a course, so a course never starts at the owner's front door (Security §3).
PRIVACY_TRIM_M = 150.0
DUPLICATE_ENDPOINT_RADIUS_M = 50.0
DUPLICATE_DISTANCE_TOLERANCE = 0.10

# Public map privacy: markers snap to the centre of a ~550 m grid cell.
PUBLIC_GRID_DEG = 0.005

# Challenge terms
ENTRY_CRYSTALS = 0
REWARD_POLICY = "xp_badge"
ELIGIBILITY = "verified_runner"
PRIVACY_MODE = "generalized"
MIN_WINDOW_HOURS = 1
MAX_WINDOW_HOURS = 720
MAX_OPEN_CHALLENGES_PER_COURSE = 1
PARTICIPATION_XP = 10
DEFENSE_XP = 15
SUBMISSION_GRACE_HOURS = 1

# Attempt evaluation
ATTEMPT_ENDPOINT_RADIUS_M = 75.0
ATTEMPT_DISTANCE_TOLERANCE = 0.15
ATTEMPT_CORRIDOR_M = 50.0
MIN_COURSE_COVERAGE = 0.80
MAX_ATTEMPT_POINTS = 2000
# A time this far under the defender's benchmark goes to a human reviewer instead of
# being auto-awarded: the evidence chain is not yet strong enough to trust outliers.
REVIEW_OUTLIER_RATIO = 0.75
CLOCK_SKEW_TOLERANCE_S = 120.0

TERMS_FIELDS = (
    "course_id", "course_version", "rules_version", "target_seconds", "entry_crystals",
    "reward_policy", "win_xp", "participation_xp", "eligibility", "privacy_mode",
    "safety_notes", "opens_at", "closes_at",
)

BADGES = {
    "FIRST_VERIFIED_RUN": "First verified run",
    "FIRST_COURSE": "Registered a course",
    "FIRST_CHALLENGE_PUBLISHED": "Published a challenge",
    "FIRST_CHALLENGE_WIN": "Won a challenge",
    "FIRST_DEFENSE": "Defended a course",
}

# Performance ladder (Domain spec §4). Based on verified-activity XP only.
RANK_LADDER = (
    (35_000, "Divine"),
    (20_000, "Imperial"),
    (12_000, "Royal"),
    (7_000, "Saint"),
    (3_500, "Platinum"),
    (1_500, "Gold"),
    (500, "Silver"),
    (0, "Bronze"),
)

LatLng = tuple[float, float]


def distance_m(a: LatLng, b: LatLng) -> float:
    """Great-circle distance in metres."""
    radius = 6_371_000.0
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat = lat2 - lat1
    dlng = math.radians(b[1] - a[1])
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(hav)))


def _fast_distance_m(a: LatLng, b: LatLng) -> float:
    """Equirectangular approximation; accurate to well under 1% at corridor scales."""
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    y = math.radians(b[0] - a[0])
    return 6_371_000.0 * math.hypot(x, y)


def path_length_m(route: Sequence[LatLng]) -> float:
    return sum(distance_m(a, b) for a, b in zip(route, route[1:]))


def simplify_route(route: Sequence[LatLng], max_points: int = MAX_COURSE_POINTS) -> list[LatLng]:
    """Uniform-stride downsample that always keeps the first and last point."""
    pts = [(round(lat, 6), round(lng, 6)) for lat, lng in route]
    if len(pts) <= max_points:
        return pts
    step = (len(pts) - 1) / (max_points - 1)
    return [pts[round(i * step)] for i in range(max_points)]


@dataclass(frozen=True)
class TrimmedRoute:
    route: list[LatLng]
    distance_m: float
    elapsed_seconds: float


def trim_route(points: Sequence[tuple[float, float, int]], trim_m: float = PRIVACY_TRIM_M) -> TrimmedRoute:
    """Drop the first and last `trim_m` metres of a timed route.

    `points` are (lat, lng, t_ms) in sequence order. The result's elapsed time is measured
    between the first and last kept points, so the owner's benchmark covers exactly the
    course a challenger will run."""
    if len(points) < 2:
        return TrimmedRoute([], 0.0, 0.0)
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + distance_m((a[0], a[1]), (b[0], b[1])))
    total = cumulative[-1]
    kept = [p for p, d in zip(points, cumulative) if trim_m <= d <= total - trim_m]
    if len(kept) < 2:
        return TrimmedRoute([], 0.0, 0.0)
    route = [(p[0], p[1]) for p in kept]
    return TrimmedRoute(route, path_length_m(route), (kept[-1][2] - kept[0][2]) / 1000.0)


def _route_midpoint(route: Sequence[LatLng]) -> LatLng:
    """The point halfway along the route by distance."""
    total = path_length_m(route)
    if total <= 0:
        return route[0]
    half, walked = total / 2, 0.0
    for a, b in zip(route, route[1:]):
        seg = distance_m(a, b)
        if walked + seg >= half and seg > 0:
            f = (half - walked) / seg
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        walked += seg
    return route[-1]


def snap_to_grid(point: LatLng, grid_deg: float = PUBLIC_GRID_DEG) -> LatLng:
    lat = (math.floor(point[0] / grid_deg) + 0.5) * grid_deg
    lng = (math.floor(point[1] / grid_deg) + 0.5) * grid_deg
    return (round(lat, 6), round(lng, 6))


def public_marker(route: Sequence[LatLng]) -> LatLng:
    """Generalized public location for a course (ADR-004): the route midpoint snapped to a
    grid cell centre. Start and finish are never used — they are the points most likely to
    be a runner's home or workplace."""
    return snap_to_grid(_route_midpoint(route))


def course_rejection_reasons(distance: float) -> list[str]:
    reasons = []
    if distance < MIN_COURSE_DISTANCE_M:
        reasons.append("COURSE_TOO_SHORT")
    if distance > MAX_COURSE_DISTANCE_M:
        reasons.append("COURSE_TOO_LONG")
    return reasons


def is_duplicate_course(
    start: LatLng, finish: LatLng, distance: float,
    other_start: LatLng, other_finish: LatLng, other_distance: float,
) -> bool:
    """Same start, same finish, and similar length: the same course in practice."""
    if distance_m(start, other_start) > DUPLICATE_ENDPOINT_RADIUS_M:
        return False
    if distance_m(finish, other_finish) > DUPLICATE_ENDPOINT_RADIUS_M:
        return False
    return abs(distance - other_distance) <= DUPLICATE_DISTANCE_TOLERANCE * max(distance, other_distance)


def win_xp_for(distance: float) -> int:
    return 50 + int(distance / 100)


def build_terms(
    *, course_id: int, course_version: int, target_seconds: float, win_xp: int,
    safety_notes: str | None, opens_at: datetime, closes_at: datetime,
) -> dict:
    return {
        "course_id": course_id,
        "course_version": course_version,
        "rules_version": CHALLENGE_RULES_VERSION,
        "target_seconds": round(float(target_seconds), 2),
        "entry_crystals": ENTRY_CRYSTALS,
        "reward_policy": REWARD_POLICY,
        "win_xp": win_xp,
        "participation_xp": PARTICIPATION_XP,
        "eligibility": ELIGIBILITY,
        "privacy_mode": PRIVACY_MODE,
        "safety_notes": safety_notes or "",
        "opens_at": opens_at.replace(microsecond=0).isoformat(),
        "closes_at": closes_at.replace(microsecond=0).isoformat(),
    }


def terms_hash(terms: dict) -> str:
    assert set(terms) == set(TERMS_FIELDS), "terms must contain exactly TERMS_FIELDS"
    payload = json.dumps(terms, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AttemptEvaluation:
    status: str                 # accepted | rejected | review_required
    outcome: str | None         # won | lost | None (undecided until review)
    reason_codes: list[str]
    elapsed_seconds: float
    coverage: float


def course_coverage(course_route: Sequence[LatLng], attempt_route: Sequence[LatLng]) -> float:
    """Fraction of course points that have an attempt point within the corridor."""
    if not course_route or not attempt_route:
        return 0.0
    attempt = simplify_route(attempt_route, MAX_ATTEMPT_POINTS)
    hits = 0
    for cp in course_route:
        if any(_fast_distance_m(cp, ap) <= ATTEMPT_CORRIDOR_M for ap in attempt):
            hits += 1
    return hits / len(course_route)


def extract_course_segment(
    run_points: Sequence[tuple[float, float, int]],
    course_start: LatLng,
    course_finish: LatLng,
    course_distance: float,
) -> tuple[int, int] | None:
    """Indices (i_start, i_end) of the part of a run that covers the course.

    Timing runs from the point closest to the course start during the runner's first pass
    through the start zone, to the point closest to the course finish during the first pass
    through the finish zone after at least half the course distance (so loop courses, where
    start == finish, don't end immediately). Using the closest points rather than the zone
    edges keeps a challenger's timed distance equal to the benchmark's."""
    def _dist(i: int, target: LatLng) -> float:
        return distance_m((run_points[i][0], run_points[i][1]), target)

    radius = ATTEMPT_ENDPOINT_RADIUS_M
    first = next((i for i in range(len(run_points)) if _dist(i, course_start) <= radius), None)
    if first is None:
        return None
    last = first
    while last + 1 < len(run_points) and _dist(last + 1, course_start) <= radius:
        last += 1
    i_start = min(range(first, last + 1), key=lambda i: _dist(i, course_start))

    walked = 0.0
    for i in range(i_start + 1, len(run_points)):
        prev, cur = run_points[i - 1], run_points[i]
        walked += distance_m((prev[0], prev[1]), (cur[0], cur[1]))
        if walked >= course_distance / 2 and _dist(i, course_finish) <= radius:
            end = i
            while end + 1 < len(run_points) and _dist(end + 1, course_finish) <= radius:
                end += 1
            return i_start, min(range(i, end + 1), key=lambda j: _dist(j, course_finish))
    return None


def evaluate_attempt(
    *,
    course_route: Sequence[LatLng],
    course_distance: float,
    target_seconds: float,
    run_verification_status: str | None,
    run_points: Sequence[tuple[float, float, int]],
    run_duration: float,
    run_wall_clock_seconds: float | None,
) -> AttemptEvaluation:
    """Decide one attempt from the run's stored route evidence.

    `run_points` are (lat, lng, t_ms) in sequence order. Only the on-course segment is
    timed. Nothing the client declares about time or distance is used directly."""
    reasons: list[str] = []
    if run_verification_status != "accepted":
        reasons.append("RUN_NOT_ACCEPTED")
    # Device timestamps claiming more time than the server saw pass between start and
    # finish are fabricated.
    if run_wall_clock_seconds is not None and run_duration > run_wall_clock_seconds + CLOCK_SKEW_TOLERANCE_S:
        reasons.append("CLOCK_SKEW")

    segment = extract_course_segment(run_points, course_route[0], course_route[-1], course_distance)
    if segment is None:
        start_hit = any(
            distance_m((p[0], p[1]), course_route[0]) <= ATTEMPT_ENDPOINT_RADIUS_M for p in run_points
        )
        reasons.append("FINISH_OUTSIDE_COURSE" if start_hit else "START_OUTSIDE_COURSE")
        return AttemptEvaluation("rejected", None, reasons, 0.0, 0.0)

    i_start, i_end = segment
    seg_points = run_points[i_start:i_end + 1]
    seg_route = [(p[0], p[1]) for p in seg_points]
    elapsed = round((seg_points[-1][2] - seg_points[0][2]) / 1000.0, 2)
    seg_distance = path_length_m(seg_route)
    if abs(seg_distance - course_distance) > ATTEMPT_DISTANCE_TOLERANCE * course_distance:
        reasons.append("DISTANCE_MISMATCH")
    coverage = round(course_coverage(course_route, seg_route), 3)
    if coverage < MIN_COURSE_COVERAGE:
        reasons.append("ROUTE_OFF_COURSE")

    if reasons:
        return AttemptEvaluation("rejected", None, reasons, elapsed, coverage)
    if elapsed < target_seconds * REVIEW_OUTLIER_RATIO:
        return AttemptEvaluation("review_required", None, ["REVIEW_REQUIRED"], elapsed, coverage)
    outcome = "won" if elapsed < target_seconds else "lost"
    return AttemptEvaluation("accepted", outcome, [], elapsed, coverage)


def performance_rank(xp: int) -> str:
    for threshold, name in RANK_LADDER:
        if xp >= threshold:
            return name
    return "Bronze"


def next_rank_threshold(xp: int) -> int | None:
    higher = [t for t, _ in RANK_LADDER if t > xp]
    return min(higher) if higher else None
