"""Deterministic verification rules for the first-release running loop.

The verifier intentionally uses explainable rules. It produces metrics and reason codes;
it does not trust client-declared distance, duration, or score.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Iterable, Sequence


# Sustained speed, measured over at least SPEED_WINDOW_SECONDS so GPS noise between 1 s fixes
# does not fail an honest run; a single segment may reach MAX_SEGMENT_SPEED_KMH.
MAX_SPEED_KMH = 25.0
SPEED_WINDOW_SECONDS = 5.0
MAX_SEGMENT_SPEED_KMH = 40.0
MAX_POINT_GAP_SECONDS = 300.0
MIN_POINTS = 3
MIN_DURATION_SECONDS = 60.0
MIN_DISTANCE_METERS = 100.0
MAX_ACCEPTED_ACCURACY_METERS = 100.0
RULES_VERSION = "run-rules-v2"

# Moving time and climbing, for display; they never change the verdict. The app applies the same
# auto-pause rule live, so the two figures agree: slower than MOVING_MIN_MPS for
# AUTO_PAUSE_AFTER_SECONDS straight counts as stopped, and climbs shorter than CLIMB_STEP_M are
# GPS altitude noise.
MOVING_MIN_MPS = 0.5
AUTO_PAUSE_AFTER_SECONDS = 10.0
# A reported speed under MOVING_MIN_MPS is a stop only if the position also moved no more than GPS
# jitter: the fix's accuracy radius, at least JITTER_FLOOR_M. Some phones report 0 while moving.
JITTER_FLOOR_M = 5.0
CLIMB_STEP_M = 3.0


@dataclass(frozen=True)
class VerificationResult:
    status: str
    reason_codes: list[str]
    metrics: dict[str, float | int | str]
    route_hash: str


def _distance_m(a: dict, b: dict) -> float:
    radius = 6_371_000.0
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlng = math.radians(b["lng"] - a["lng"])
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(hav)))


def _max_sustained_speed_kmh(timestamps: Sequence[float], cumulative: list[float]) -> float:
    """Highest average speed over any stretch of at least SPEED_WINDOW_SECONDS, ending at each
    point and starting at the latest point that still makes the stretch that long. A route
    shorter than the window is measured end to end."""
    if len(timestamps) < 2:
        return 0.0
    window_ms = SPEED_WINDOW_SECONDS * 1000
    total_ms = timestamps[-1] - timestamps[0]
    if total_ms < window_ms:
        return (cumulative[-1] - cumulative[0]) / (total_ms / 1000.0) * 3.6 if total_ms > 0 else 0.0
    best = 0.0
    start = 0
    for end in range(1, len(timestamps)):
        while start + 1 < end and timestamps[end] - timestamps[start + 1] >= window_ms:
            start += 1
        span_ms = timestamps[end] - timestamps[start]
        if span_ms >= window_ms:
            best = max(best, (cumulative[end] - cumulative[start]) / (span_ms / 1000.0) * 3.6)
    return best


def canonical_route_hash(points: Iterable[dict]) -> str:
    payload = json.dumps(list(points), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def moving_seconds(timestamps: Sequence[float], cumulative: list[float],
                   speeds: Sequence[float | None] | None = None,
                   accuracies: Sequence[float | None] | None = None) -> float:
    """Elapsed time minus stops: a run of slow segments counts as a stop once it lasts
    AUTO_PAUSE_AFTER_SECONDS, from its first slow segment. A point's own speed (Doppler, from the
    phone) is preferred over the segment's, which GPS position jitter inflates when standing still."""
    moving = 0.0
    still = 0.0
    for i in range(1, len(timestamps)):
        dt = (timestamps[i] - timestamps[i - 1]) / 1000.0
        if dt <= 0:
            continue
        segment = cumulative[i] - cumulative[i - 1]
        reported = speeds[i] if speeds else None
        if reported is None:
            slow = segment / dt < MOVING_MIN_MPS
        else:
            jitter = max((accuracies[i] if accuracies else None) or 0.0, JITTER_FLOOR_M)
            slow = reported < MOVING_MIN_MPS and segment <= jitter
        if not slow:
            if still < AUTO_PAUSE_AFTER_SECONDS:
                moving += still
            still = 0.0
            moving += dt
        else:
            still += dt
    return moving + (still if still < AUTO_PAUSE_AFTER_SECONDS else 0.0)


def elevation_gain_m(altitudes: Iterable[float | None]) -> float:
    """Total climb, ignoring rises under CLIMB_STEP_M from the lowest point since the last counted climb."""
    gain = 0.0
    base: float | None = None
    for alt in altitudes:
        if alt is None:
            continue
        if base is None or alt < base:
            base = alt
        elif alt - base >= CLIMB_STEP_M:
            gain += alt - base
            base = alt
    return gain


def verify_route(points: list[dict]) -> VerificationResult:
    normalized = [
        {
            "sequence": int(p["sequence"]),
            "t_ms": int(p["t_ms"]),
            "lat": round(float(p["lat"]), 7),
            "lng": round(float(p["lng"]), 7),
            "accuracy_m": None if p.get("accuracy_m") is None else round(float(p["accuracy_m"]), 2),
            "speed_mps": None if p.get("speed_mps") is None else round(float(p["speed_mps"]), 3),
            "altitude_m": None if p.get("altitude_m") is None else round(float(p["altitude_m"]), 2),
        }
        for p in points
    ]
    route_hash = canonical_route_hash(normalized)
    reasons: list[str] = []
    if len(normalized) < MIN_POINTS:
        reasons.append("INSUFFICIENT_ROUTE_POINTS")

    distance_m = 0.0
    max_segment_speed_kmh = 0.0
    max_gap_seconds = 0.0
    timestamps = [p["t_ms"] for p in normalized]
    if any(b <= a for a, b in zip(timestamps, timestamps[1:])):
        reasons.append("NON_MONOTONIC_TIMESTAMPS")

    # cumulative[i]: path length from the first point to point i.
    cumulative = [0.0]
    for previous, current in zip(normalized, normalized[1:]):
        segment_distance = _distance_m(previous, current)
        distance_m += segment_distance
        cumulative.append(distance_m)
        gap_seconds = (current["t_ms"] - previous["t_ms"]) / 1000.0
        max_gap_seconds = max(max_gap_seconds, gap_seconds)
        if gap_seconds > 0:
            max_segment_speed_kmh = max(max_segment_speed_kmh, segment_distance / gap_seconds * 3.6)
    max_speed_kmh = _max_sustained_speed_kmh(timestamps, cumulative)

    duration_seconds = 0.0
    if len(normalized) >= 2 and timestamps[-1] > timestamps[0]:
        duration_seconds = (timestamps[-1] - timestamps[0]) / 1000.0

    accuracies = [p["accuracy_m"] for p in normalized if p["accuracy_m"] is not None]
    average_accuracy = sum(accuracies) / len(accuracies) if accuracies else 0.0
    if max_speed_kmh > MAX_SPEED_KMH or max_segment_speed_kmh > MAX_SEGMENT_SPEED_KMH:
        reasons.append("IMPOSSIBLE_SPEED")
    if max_gap_seconds > MAX_POINT_GAP_SECONDS:
        reasons.append("ROUTE_GAP_TOO_LARGE")
    if duration_seconds < MIN_DURATION_SECONDS:
        reasons.append("DURATION_TOO_SHORT")
    if distance_m < MIN_DISTANCE_METERS:
        reasons.append("DISTANCE_TOO_SHORT")
    if average_accuracy > MAX_ACCEPTED_ACCURACY_METERS:
        reasons.append("GPS_ACCURACY_TOO_LOW")

    metrics: dict[str, float | int | str] = {
        "rules_version": RULES_VERSION,
        "point_count": len(normalized),
        "distance_m": round(distance_m, 2),
        "duration_seconds": round(duration_seconds, 2),
        "max_speed_kmh": round(max_speed_kmh, 2),
        "max_segment_speed_kmh": round(max_segment_speed_kmh, 2),
        "max_gap_seconds": round(max_gap_seconds, 2),
        "average_accuracy_m": round(average_accuracy, 2),
        "moving_seconds": round(moving_seconds(timestamps, cumulative, [p["speed_mps"] for p in normalized],
                                               [p["accuracy_m"] for p in normalized]), 2),
        "elevation_gain_m": round(elevation_gain_m(p["altitude_m"] for p in normalized), 1),
    }
    status = "accepted" if not reasons else "rejected"
    return VerificationResult(status, reasons, metrics, route_hash)

