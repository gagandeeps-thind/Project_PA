"""Camera-verified bodyweight exercises: the catalog and the server-side plausibility rules.

The phone runs pose estimation (ML Kit BlazePose) and the rep engine on device; camera
frames and landmarks never leave it. The device uploads a summary: per-rep durations, the
reps it accepted, and its own reason codes. The server cannot see the video, so it does not
trust the device's verdict for rewards. It re-checks that the summary is physically
plausible under the same catalog the device used (tempo bounds, rate, totals) and caps the
daily XP an exercise can earn, so a forged summary is worth little.

This module is the single source of truth for the catalog. The app ships a copy as
`Osiris_customer/assets/exercise_catalog.json`; `scripts/export_exercise_catalog.py` writes
it and the exercise test suite fails when the two drift.

Pure functions only: no database session, no HTTP. `exercise_api.py` owns the transaction.
Rewards are XP only. Exercises never touch Mana Crystals.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any, Iterable, Sequence

RULES_VERSION = "exercise-rules-v2"
# Versions whose sets the server still accepts. The server-side checks (tempo bounds, rate,
# totals) are unchanged since v1; v2 only changed device-side thresholds. A set recorded
# offline before the app fetched v2 is therefore still judged fairly. Drop a version from this
# list once a change makes its sets incomparable.
ACCEPTED_RULES_VERSIONS = frozenset({"exercise-rules-v1", RULES_VERSION})

# Device-side landmark likelihood below which a joint counts as not visible.
MIN_LANDMARK_LIKELIHOOD = 0.5

# Joint triples are (a, vertex, c); the engine measures the angle at the vertex in degrees.
# Form rules of type "orientation" bound a body segment's tilt from the horizontal or vertical
# axis, so the movement must happen in the right position: elbow curls while standing are not
# push-ups, and standing straight is not a plank. Each limit sits about midway between the
# genuine posture's largest tilt and the nearest cheat posture, leaving room for a phone
# propped up to 15 degrees off level (v2; v1 limits failed genuine squats at 12 degrees).
# "min_pose_fps" is the slowest pose stream the engine counts reliably for the exercise
# (Osiris_customer/test/exercise/accuracy_eval_test.dart); below it the app warns the player.
# "ankle_spread" is the ankle distance in torso lengths (shoulder midpoint to hip midpoint),
# taken as the median over the rep's peak frames (v2; v1 used the max over hip widths, which
# jitter pushed over the limit for arms-only jumping jacks).
# Names follow ML Kit / BlazePose landmark names without the side prefix; the engine uses
# the side the camera sees best, or both sides for front-facing exercises.
CATALOG: tuple[dict[str, Any], ...] = (
    {
        "key": "pushup",
        "name": "Push-up",
        "kind": "reps",
        "camera": "side",
        "instructions": "Place the phone on the floor about 2 m to your side so your whole body is in view.",
        "metric": {"type": "angle", "joints": ["shoulder", "elbow", "wrist"], "sides": "best"},
        "rest": {"above": 150.0},
        "peak": {"below": 100.0},
        "form": [
            {"code": "body_line", "joints": ["shoulder", "hip", "ankle"], "min": 145.0},
            {"code": "body_position", "type": "orientation", "joints": ["shoulder", "hip"], "axis": "horizontal", "max_deg": 50.0},
        ],
        "min_rep_s": 0.6, "max_rep_s": 8.0, "max_reps_per_min": 60,
        "min_pose_fps": 5,
        "xp_per_rep": 1, "daily_xp_cap": 40,
    },
    {
        "key": "squat",
        "name": "Squat",
        "kind": "reps",
        "camera": "side",
        "instructions": "Stand side-on to the phone, about 2.5 m away, with your feet in view.",
        "metric": {"type": "angle", "joints": ["hip", "knee", "ankle"], "sides": "best"},
        "rest": {"above": 155.0},
        "peak": {"below": 110.0},
        "form": [
            {"code": "torso_upright", "joints": ["shoulder", "hip", "knee"], "min": 45.0},
            {"code": "body_position", "type": "orientation", "joints": ["shoulder", "hip"], "axis": "vertical", "max_deg": 65.0},
        ],
        "min_rep_s": 0.8, "max_rep_s": 10.0, "max_reps_per_min": 50,
        "min_pose_fps": 5,
        "xp_per_rep": 1, "daily_xp_cap": 40,
    },
    {
        "key": "lunge",
        "name": "Lunge",
        "kind": "reps",
        "camera": "side",
        "instructions": "Stand side-on to the phone, about 2.5 m away. Alternate legs; every lunge counts.",
        "metric": {"type": "angle", "joints": ["hip", "knee", "ankle"], "sides": "min"},
        "rest": {"above": 150.0},
        "peak": {"below": 115.0},
        "form": [{"code": "body_position", "type": "orientation", "joints": ["shoulder", "hip"], "axis": "vertical", "max_deg": 45.0}],
        "min_rep_s": 0.9, "max_rep_s": 10.0, "max_reps_per_min": 40,
        "min_pose_fps": 5,
        "xp_per_rep": 1, "daily_xp_cap": 30,
    },
    {
        "key": "situp",
        "name": "Sit-up",
        "kind": "reps",
        "camera": "side",
        "instructions": "Lie side-on to the phone with your knees bent, about 2 m away.",
        "metric": {"type": "angle", "joints": ["shoulder", "hip", "knee"], "sides": "best"},
        "rest": {"above": 115.0},
        "peak": {"below": 75.0},
        "form": [{"code": "body_position", "type": "orientation", "joints": ["hip", "ankle"], "axis": "horizontal", "max_deg": 45.0}],
        "min_rep_s": 0.8, "max_rep_s": 10.0, "max_reps_per_min": 50,
        "min_pose_fps": 5,
        "xp_per_rep": 1, "daily_xp_cap": 30,
    },
    {
        "key": "jumping_jack",
        "name": "Jumping jack",
        "kind": "reps",
        "camera": "front",
        "instructions": "Face the phone from about 3 m away so your hands above your head stay in view.",
        "metric": {"type": "angle", "joints": ["hip", "shoulder", "wrist"], "sides": "mean"},
        "rest": {"below": 50.0},
        "peak": {"above": 130.0},
        "form": [
            {"code": "legs_apart", "type": "ankle_spread", "min": 0.7, "at": "peak"},
            {"code": "body_position", "type": "orientation", "joints": ["shoulder", "hip"], "axis": "vertical", "max_deg": 45.0},
        ],
        "min_rep_s": 0.4, "max_rep_s": 4.0, "max_reps_per_min": 100,
        "min_pose_fps": 5,
        "xp_per_rep": 1, "daily_xp_cap": 30,
    },
    {
        "key": "high_knees",
        "name": "High knees",
        "kind": "reps",
        "camera": "side",
        "instructions": "Stand side-on to the phone, about 2.5 m away. Each knee lift counts.",
        "metric": {"type": "angle", "joints": ["shoulder", "hip", "knee"], "sides": "min"},
        "rest": {"above": 155.0},
        "peak": {"below": 115.0},
        "form": [{"code": "body_position", "type": "orientation", "joints": ["shoulder", "hip"], "axis": "vertical", "max_deg": 45.0}],
        "min_rep_s": 0.25, "max_rep_s": 3.0, "max_reps_per_min": 180,
        "min_pose_fps": 7,
        "xp_per_rep": 1, "daily_xp_cap": 25,
    },
    {
        "key": "plank",
        "name": "Plank",
        "kind": "hold",
        "camera": "side",
        "instructions": "Place the phone on the floor about 2 m to your side, then move into a plank.",
        "metric": {"type": "angle", "joints": ["shoulder", "hip", "ankle"], "sides": "best"},
        # The hold counts while the body line is straight; entering from outside it is required.
        "rest": {"below": 140.0},
        "peak": {"above": 160.0},
        "form": [{"code": "body_position", "type": "orientation", "joints": ["shoulder", "hip"], "axis": "horizontal", "max_deg": 50.0}],
        "min_rep_s": 0.0, "max_rep_s": 0.0, "max_reps_per_min": 0,
        "min_pose_fps": 5,
        "max_hold_s": 600, "xp_per_10s": 1, "daily_xp_cap": 30,
    },
)

BY_KEY: dict[str, dict[str, Any]] = {e["key"]: e for e in CATALOG}

# Every reason code either side may report. Unknown codes are refused, so a client cannot
# smuggle free text into the evidence store.
REASON_CODES = frozenset({
    # rep level (device)
    "too_fast", "too_slow", "form_break", "wrong_position", "low_visibility", "tracking_glitch", "partial_range",
    "unsteady_tracking",
    # session level (device and server)
    "no_valid_reps", "low_valid_ratio", "replay_suspected", "rate_implausible", "no_entry_transition",
    "static_pose", "hold_too_short",
    # server only
    "tempo_implausible", "duration_mismatch", "rules_version_mismatch", "client_rejected",
})

# Hard failures reject the session; soft flags send it to review without XP.
HARD_REASONS = frozenset({
    "no_valid_reps", "rate_implausible", "tempo_implausible", "duration_mismatch",
    "rules_version_mismatch", "client_rejected", "static_pose", "no_entry_transition", "hold_too_short",
})

REPLAY_MIN_REPS = 8
REPLAY_MAX_DURATION_CV = 0.03
MIN_VALID_RATIO = 0.6
MAX_SESSION_S = 1_800
MIN_HOLD_S = 5.0
# Global ceiling on exercise XP per local day, on top of each exercise's own cap.
DAILY_EXERCISE_XP_CAP = 120


@dataclass(frozen=True)
class SessionClaim:
    exercise_key: str
    rules_version: str
    duration_s: float
    reps_attempted: int
    reps_valid: int
    hold_s: float
    rep_durations_s: Sequence[float]
    client_verdict: str
    client_reasons: Sequence[str]


@dataclass(frozen=True)
class Decision:
    status: str                      # verified | review | rejected
    reasons: tuple[str, ...]
    credited_reps: int
    credited_hold_s: float
    base_xp: int                     # before the daily caps


def catalog_payload() -> dict[str, Any]:
    return {
        "rules_version": RULES_VERSION,
        "min_landmark_likelihood": MIN_LANDMARK_LIKELIHOOD,
        # Session-level rules the device applies exactly as `evaluate` does.
        "session_rules": {
            "min_valid_ratio": MIN_VALID_RATIO,
            "replay_min_reps": REPLAY_MIN_REPS,
            "replay_max_duration_cv": REPLAY_MAX_DURATION_CV,
            "min_hold_s": MIN_HOLD_S,
            "max_session_s": MAX_SESSION_S,
            "hard_reasons": sorted(HARD_REASONS),
        },
        "exercises": [dict(e) for e in CATALOG],
    }


def duration_cv(durations: Iterable[float]) -> float:
    values = [d for d in durations if d > 0]
    if len(values) < 2:
        return 1.0
    m = mean(values)
    return pstdev(values) / m if m > 0 else 1.0


def evaluate(claim: SessionClaim) -> Decision:
    """Server re-check of a device summary. Rejects anything the device itself rejected or
    that no human could have produced under the catalog's tempo rules."""
    ex = BY_KEY[claim.exercise_key]
    reasons: list[str] = [r for r in claim.client_reasons if r in REASON_CODES]
    if claim.rules_version not in ACCEPTED_RULES_VERSIONS:
        reasons.append("rules_version_mismatch")
    if claim.client_verdict == "rejected":
        reasons.append("client_rejected")

    credited_reps = 0
    credited_hold = 0.0
    if ex["kind"] == "hold":
        credited_hold = min(claim.hold_s, float(ex["max_hold_s"]), claim.duration_s)
        if claim.hold_s > claim.duration_s + 1.0:
            reasons.append("duration_mismatch")
        if credited_hold < MIN_HOLD_S:
            reasons.append("hold_too_short")
        base_xp = base_xp_for(claim.exercise_key, 0, claim.hold_s, claim.duration_s)
    else:
        durations = list(claim.rep_durations_s)
        if claim.reps_valid > claim.reps_attempted or len(durations) != claim.reps_valid:
            reasons.append("duration_mismatch")
        if sum(durations) > claim.duration_s + 1.0:
            reasons.append("duration_mismatch")
        if any(d < ex["min_rep_s"] or d > ex["max_rep_s"] for d in durations):
            reasons.append("tempo_implausible")
        if claim.duration_s > 0 and claim.reps_valid / (claim.duration_s / 60.0) > ex["max_reps_per_min"]:
            reasons.append("rate_implausible")
        if claim.reps_valid == 0:
            reasons.append("no_valid_reps")
        elif claim.reps_valid / max(claim.reps_attempted, 1) < MIN_VALID_RATIO:
            reasons.append("low_valid_ratio")
        if len(durations) >= REPLAY_MIN_REPS and duration_cv(durations) < REPLAY_MAX_DURATION_CV:
            reasons.append("replay_suspected")
        credited_reps = claim.reps_valid
        base_xp = base_xp_for(claim.exercise_key, credited_reps, 0.0, claim.duration_s)

    unique = tuple(dict.fromkeys(reasons))
    if any(r in HARD_REASONS for r in unique):
        status = "rejected"
    elif unique or claim.client_verdict == "review":
        status = "review"
    else:
        status = "verified"
    if status != "verified":
        return Decision(status, unique, 0, 0.0, 0)
    return Decision(status, unique, credited_reps, credited_hold, base_xp)


def base_xp_for(exercise_key: str, reps_valid: int, hold_s: float, duration_s: float) -> int:
    """XP a set is worth before the daily caps: per rep, or per full 10 s of hold (a hold is
    credited up to the exercise's maximum and never beyond the set's own duration)."""
    ex = BY_KEY[exercise_key]
    if ex["kind"] == "hold":
        credited = min(hold_s, float(ex["max_hold_s"]), duration_s)
        return int(credited // 10) * int(ex["xp_per_10s"])
    return reps_valid * int(ex["xp_per_rep"])


def capped_xp(base_xp: int, exercise_key: str, earned_today_exercise: int, earned_today_total: int) -> int:
    ex_left = max(0, int(BY_KEY[exercise_key]["daily_xp_cap"]) - earned_today_exercise)
    total_left = max(0, DAILY_EXERCISE_XP_CAP - earned_today_total)
    return max(0, min(base_xp, ex_left, total_left))
