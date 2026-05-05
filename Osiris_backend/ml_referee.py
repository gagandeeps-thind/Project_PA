"""ML Referee — server-side verification of client-submitted activity proofs.

The frontend (Flutter) records an activity locally — accelerometer samples plus, for
camera-verified exercises, a pose summary extracted from MediaPipe on-device. This module
inspects that proof and returns a `verified` flag, `confidence` score, and `verified_score`
the rest of the backend should treat as authoritative.

Phase-1 MVP uses pure-Python heuristics (peak detection on accelerometer magnitude,
range-of-motion thresholds for pose). Phase 2 will swap the cadence/rhythm logic for a
trained Scikit-learn model fed on real pilot data.

Confidence threshold = 0.85 (per GDD Epic 2.2). Anything below that returns
`verified=False` and a `verified_score` of 0, regardless of declared score.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
import math


CONFIDENCE_THRESHOLD = 0.85


# Per-activity heuristic profiles. Numbers tuned from common fitness research:
#   - cadence_min/max_hz : expected reps-per-second band for human execution
#   - max_rate_per_sec   : sanity cap on declared score given duration (with 20% slack)
#   - is_hold            : true for plank/hold, where score == seconds and motion should be flat
ACTIVITY_PROFILES: Dict[str, Dict] = {
    "pushups": {"cadence_min_hz": 0.3, "cadence_max_hz": 1.5, "max_rate_per_sec": 1.0, "is_hold": False},
    "squats":  {"cadence_min_hz": 0.3, "cadence_max_hz": 1.5, "max_rate_per_sec": 1.0, "is_hold": False},
    "burpees": {"cadence_min_hz": 0.15, "cadence_max_hz": 0.6, "max_rate_per_sec": 0.6, "is_hold": False},
    "sprint":  {"cadence_min_hz": 2.5, "cadence_max_hz": 4.5, "max_rate_per_sec": 5.0, "is_hold": False},
    "run":     {"cadence_min_hz": 2.0, "cadence_max_hz": 3.5, "max_rate_per_sec": 4.0, "is_hold": False},
    "walk":    {"cadence_min_hz": 1.5, "cadence_max_hz": 2.5, "max_rate_per_sec": 3.0, "is_hold": False},
    "plank":   {"cadence_min_hz": 0.0, "cadence_max_hz": 0.2, "max_rate_per_sec": 999.0, "is_hold": True},
    "hold":    {"cadence_min_hz": 0.0, "cadence_max_hz": 0.2, "max_rate_per_sec": 999.0, "is_hold": True},
}


@dataclass
class CheckResult:
    """Outcome of a single sub-check (accelerometer / pose / plausibility)."""
    passed: bool
    reason: str
    confidence: float  # 0.0 - 1.0


@dataclass
class VerificationOutcome:
    """Aggregated verdict returned to the caller."""
    verified: bool
    confidence: float
    verified_score: int
    flags: List[str] = field(default_factory=list)
    activity_type: str = ""


# --- Sub-checks ---

def check_accelerometer_pattern(samples, activity_type: str) -> CheckResult:
    """Detects whether the accelerometer trace looks like a human performing the declared
    activity. Rejects (a) no rhythm, (b) cadence outside human range, (c) erratic timing,
    or (d) for holds, excessive motion."""
    if not samples or len(samples) < 10:
        return CheckResult(False, "Too few accelerometer samples (<10)", 0.0)

    profile = ACTIVITY_PROFILES.get(activity_type)
    if not profile:
        return CheckResult(True, f"No profile for {activity_type}; skipped accel check", 0.5)

    # Magnitude series of (ax, ay, az). Includes gravity (~9.8 m/s²) — peaks ride above it.
    magnitudes = [math.sqrt(s.ax * s.ax + s.ay * s.ay + s.az * s.az) for s in samples]
    mean_mag = sum(magnitudes) / len(magnitudes)

    # Holds (plank): expect very low variance — user is steady.
    if profile["is_hold"]:
        variance = sum((m - mean_mag) ** 2 for m in magnitudes) / len(magnitudes)
        if variance > 4.0:
            return CheckResult(False, f"Excessive motion variance during hold ({variance:.2f})", 0.0)
        return CheckResult(True, "Steady hold confirmed", 0.9)

    # Periodic activities: simple peak detection via threshold crossing.
    threshold = mean_mag + 1.5  # magnitude bump that signals the contractile phase of a rep
    peak_times_ms: List[int] = []
    above = False
    for i, m in enumerate(magnitudes):
        if m > threshold and not above:
            peak_times_ms.append(samples[i].t_ms)
            above = True
        elif m < mean_mag and above:
            above = False

    if len(peak_times_ms) < 2:
        return CheckResult(False, "No periodic motion detected", 0.0)

    duration_ms = samples[-1].t_ms - samples[0].t_ms
    if duration_ms <= 0:
        return CheckResult(False, "Invalid sample timestamps (non-monotonic)", 0.0)

    cadence_hz = (len(peak_times_ms) - 1) * 1000.0 / duration_ms
    if cadence_hz < profile["cadence_min_hz"] or cadence_hz > profile["cadence_max_hz"]:
        return CheckResult(
            False,
            f"Cadence {cadence_hz:.2f} Hz outside expected band "
            f"[{profile['cadence_min_hz']}, {profile['cadence_max_hz']}] for {activity_type}",
            0.0,
        )

    # Rhythm consistency: stdev of inter-peak intervals as a fraction of the mean.
    intervals = [peak_times_ms[i + 1] - peak_times_ms[i] for i in range(len(peak_times_ms) - 1)]
    if not intervals:
        return CheckResult(True, f"Cadence {cadence_hz:.2f} Hz", 0.85)
    mean_interval = sum(intervals) / len(intervals)
    if mean_interval <= 0:
        return CheckResult(False, "Degenerate inter-peak intervals", 0.0)
    stdev_interval = (sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)) ** 0.5
    rhythm_score = max(0.0, 1.0 - (stdev_interval / mean_interval))  # 1.0 = perfectly regular
    if rhythm_score < 0.3:
        return CheckResult(False, "Rhythm too irregular — likely non-human input", 0.0)

    # Final confidence interpolates 0.7 → 1.0 based on rhythm regularity.
    confidence = 0.7 + 0.3 * rhythm_score
    return CheckResult(True, f"Cadence {cadence_hz:.2f} Hz, rhythm {rhythm_score:.2f}", confidence)


def check_pose_summary(pose, activity_type: str) -> CheckResult:
    """Validates the on-device MediaPipe summary. For pushups/squats we require a credible
    range-of-motion (ROM) and a deep-enough min-angle to count as full reps."""
    if pose is None:
        # Pose is optional for non-camera activities (run, walk, sprint).
        if activity_type in ("pushups", "squats"):
            return CheckResult(False, "Pose summary required for camera-verified activities", 0.0)
        return CheckResult(True, "Pose check not applicable", 1.0)

    if activity_type not in ("pushups", "squats"):
        return CheckResult(True, "Pose ignored for non-camera activity", 1.0)

    if pose.min_joint_angle_deg is None or pose.max_joint_angle_deg is None:
        return CheckResult(False, "Pose summary missing joint angles", 0.0)

    rom = pose.max_joint_angle_deg - pose.min_joint_angle_deg
    if rom < 60:
        return CheckResult(False, f"Range of motion only {rom:.0f}° — incomplete reps", 0.0)
    if pose.min_joint_angle_deg > 100:
        return CheckResult(False, "Reps not deep enough (min joint angle > 100°)", 0.0)
    return CheckResult(True, f"Pose ROM {rom:.0f}° accepted", 0.9)


def check_score_plausibility(activity_type: str, declared_score: int, duration_seconds: float) -> CheckResult:
    """Sanity-bounds the declared score against the activity's max human rate."""
    profile = ACTIVITY_PROFILES.get(activity_type)
    if not profile or duration_seconds <= 0:
        return CheckResult(True, "Skipped plausibility (no profile or zero duration)", 0.7)
    if profile["is_hold"]:
        # For holds, declared_score is seconds — must not exceed wall-clock duration.
        if declared_score > duration_seconds * 1.05:
            return CheckResult(False, f"Declared hold {declared_score}s exceeds elapsed {duration_seconds:.0f}s", 0.0)
        return CheckResult(True, "Hold duration plausible", 1.0)
    max_plausible = profile["max_rate_per_sec"] * duration_seconds * 1.2
    if declared_score > max_plausible:
        return CheckResult(
            False,
            f"Declared {declared_score} reps exceeds max plausible {max_plausible:.0f} for {duration_seconds:.0f}s",
            0.0,
        )
    return CheckResult(True, "Score plausible vs duration", 1.0)


# --- Orchestration ---

def verify_activity(
    activity_type: str,
    declared_score: int,
    duration_seconds: float,
    accelerometer_samples,
    pose_summary,
) -> VerificationOutcome:
    """Runs all three sub-checks and aggregates a verdict.

    Confidence is multiplicative across checks — any failed check zeroes the confidence,
    which guarantees `verified=False`. This is intentional: a bypass on one check should not
    be redeemable by another."""
    flags: List[str] = []
    confidence = 1.0

    accel_result = check_accelerometer_pattern(accelerometer_samples, activity_type)
    if not accel_result.passed:
        flags.append(f"ACCEL: {accel_result.reason}")
    confidence *= accel_result.confidence

    pose_result = check_pose_summary(pose_summary, activity_type)
    if not pose_result.passed:
        flags.append(f"POSE: {pose_result.reason}")
    confidence *= pose_result.confidence

    plaus_result = check_score_plausibility(activity_type, declared_score, duration_seconds)
    if not plaus_result.passed:
        flags.append(f"PLAUSIBILITY: {plaus_result.reason}")
    confidence *= plaus_result.confidence

    verified = confidence >= CONFIDENCE_THRESHOLD
    verified_score = declared_score if verified else 0

    return VerificationOutcome(
        verified=verified,
        confidence=round(confidence, 3),
        verified_score=verified_score,
        flags=flags,
        activity_type=activity_type,
    )
