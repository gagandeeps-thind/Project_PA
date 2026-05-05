"""Unit tests for ml_referee.

No pytest dependency — run directly:

    cd Osiris_backend
    python tests/test_ml_referee.py

Each test calls a referee function with synthetic data and asserts the verdict matches
expectation. Failures print the offending case and raise SystemExit(1) so this can be wired
into a future CI pipeline.
"""
import math
import os
import sys
from dataclasses import dataclass
from typing import List

# Make the parent directory (Osiris_backend) importable when run as a script.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ml_referee  # noqa: E402


# --- Test fixtures ---

@dataclass
class FakeSample:
    t_ms: int
    ax: float
    ay: float
    az: float


@dataclass
class FakePose:
    rep_count: int
    min_joint_angle_deg: float = None
    max_joint_angle_deg: float = None
    avg_rep_duration_ms: float = None


def synth_rhythmic(reps: int, period_ms: int, amplitude: float = 5.0, baseline_z: float = 9.8) -> List[FakeSample]:
    """Builds a synthetic accelerometer trace with `reps` rhythmic peaks at `period_ms` apart.
    Each peak is a half-sine bump on the z-axis above gravity."""
    samples_per_rep = max(20, period_ms // 50)  # ~50ms sampling
    samples: List[FakeSample] = []
    t = 0
    for _ in range(reps):
        for i in range(samples_per_rep):
            phase = i / samples_per_rep
            # Bump centered mid-rep
            bump = amplitude * math.sin(math.pi * phase) if 0.3 < phase < 0.7 else 0.0
            samples.append(FakeSample(t, 0.0, 0.0, baseline_z + bump))
            t += period_ms // samples_per_rep
    return samples


def synth_steady(seconds: float, jitter: float = 0.05) -> List[FakeSample]:
    """Builds a near-flat trace for plank/hold testing."""
    n = int(seconds * 20)  # 20 Hz
    samples: List[FakeSample] = []
    for i in range(n):
        t = i * 50
        # Tiny gravity jitter — should pass low-variance gate.
        samples.append(FakeSample(t, jitter * 0.1, jitter * 0.1, 9.8 + jitter * 0.2))
    return samples


def synth_shaky_hold(seconds: float) -> List[FakeSample]:
    """A 'hold' trace where the user is actually moving — should fail the variance gate."""
    n = int(seconds * 20)
    samples: List[FakeSample] = []
    for i in range(n):
        t = i * 50
        # ±3 m/s² wobble — well above the 4.0 variance threshold.
        wobble = 3.0 if i % 2 == 0 else -3.0
        samples.append(FakeSample(t, wobble, 0.0, 9.8 + wobble))
    return samples


# --- Tests ---

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("Legitimate 30 push-ups passes verification")
def test_pushups_pass():
    samples = synth_rhythmic(reps=30, period_ms=1000)        # 1 Hz cadence (in band)
    pose = FakePose(rep_count=30, min_joint_angle_deg=80, max_joint_angle_deg=170)
    out = ml_referee.verify_activity("pushups", 30, 30.0, samples, pose)
    assert out.verified, f"expected verified, got flags={out.flags}"
    assert out.verified_score == 30
    assert out.confidence >= 0.85


@case("Push-ups with cadence too fast (3 Hz) is rejected")
def test_pushups_cadence_fail():
    samples = synth_rhythmic(reps=30, period_ms=333)         # ~3 Hz, outside 0.3-1.5 band
    pose = FakePose(rep_count=30, min_joint_angle_deg=80, max_joint_angle_deg=170)
    out = ml_referee.verify_activity("pushups", 30, 10.0, samples, pose)
    assert not out.verified, "should reject high-cadence pushups"
    assert any("ACCEL" in f for f in out.flags), f"expected ACCEL flag, got {out.flags}"


@case("Push-ups with shallow ROM is rejected")
def test_pushups_pose_fail():
    samples = synth_rhythmic(reps=30, period_ms=1000)
    pose = FakePose(rep_count=30, min_joint_angle_deg=140, max_joint_angle_deg=170)  # only 30° ROM
    out = ml_referee.verify_activity("pushups", 30, 30.0, samples, pose)
    assert not out.verified, "should reject shallow ROM"
    assert any("POSE" in f for f in out.flags), f"expected POSE flag, got {out.flags}"


@case("Implausible score (200 reps in 30s) is rejected")
def test_pushups_plausibility_fail():
    samples = synth_rhythmic(reps=30, period_ms=1000)
    pose = FakePose(rep_count=30, min_joint_angle_deg=80, max_joint_angle_deg=170)
    out = ml_referee.verify_activity("pushups", 200, 30.0, samples, pose)
    assert not out.verified, "should reject implausibly high count"
    assert any("PLAUSIBILITY" in f for f in out.flags)


@case("Steady plank (60s) passes")
def test_plank_pass():
    samples = synth_steady(60.0)
    out = ml_referee.verify_activity("plank", 60, 60.0, samples, None)
    assert out.verified, f"expected verified plank, got flags={out.flags}"


@case("Shaky 'plank' is rejected")
def test_plank_shaky_fail():
    samples = synth_shaky_hold(60.0)
    out = ml_referee.verify_activity("plank", 60, 60.0, samples, None)
    assert not out.verified, "should reject motion during hold"
    assert any("ACCEL" in f for f in out.flags)


@case("Legitimate 5-min run passes")
def test_run_pass():
    # 2.5 Hz cadence = 750 strides over 5 min — within run band.
    samples = synth_rhythmic(reps=750, period_ms=400, amplitude=5.0)
    out = ml_referee.verify_activity("run", 750, 300.0, samples, None)
    assert out.verified, f"expected verified run, got flags={out.flags}"


@case("Pushups with no accelerometer samples is rejected")
def test_no_samples_fail():
    out = ml_referee.verify_activity("pushups", 10, 10.0, [], FakePose(10, 80, 170))
    assert not out.verified
    assert any("Too few" in f for f in out.flags)


@case("Pushups missing pose summary is rejected")
def test_pushups_missing_pose():
    samples = synth_rhythmic(reps=20, period_ms=1000)
    out = ml_referee.verify_activity("pushups", 20, 20.0, samples, None)
    assert not out.verified
    assert any("POSE" in f for f in out.flags)


@case("Verified score is zero when verification fails")
def test_verified_score_zeroed():
    out = ml_referee.verify_activity("pushups", 200, 30.0, synth_rhythmic(30, 1000), FakePose(30, 80, 170))
    assert out.verified_score == 0


# --- Runner ---

def main():
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}\n        {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {name}\n        {type(e).__name__}: {e}")
    print()
    print(f"{len(CASES) - failed} / {len(CASES)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
