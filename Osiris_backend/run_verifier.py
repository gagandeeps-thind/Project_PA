"""Deterministic verification rules for the first-release running loop.

The verifier intentionally uses explainable rules. It produces metrics and reason codes;
it does not trust client-declared distance, duration, or score.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Iterable


MAX_SPEED_KMH = 25.0
MAX_POINT_GAP_SECONDS = 300.0
MIN_POINTS = 3
MIN_DURATION_SECONDS = 60.0
MIN_DISTANCE_METERS = 100.0
MAX_ACCEPTED_ACCURACY_METERS = 100.0
RULES_VERSION = "run-rules-v1"


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


def canonical_route_hash(points: Iterable[dict]) -> str:
    payload = json.dumps(list(points), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    max_speed_kmh = 0.0
    max_gap_seconds = 0.0
    timestamps = [p["t_ms"] for p in normalized]
    if any(b <= a for a, b in zip(timestamps, timestamps[1:])):
        reasons.append("NON_MONOTONIC_TIMESTAMPS")

    for previous, current in zip(normalized, normalized[1:]):
        segment_distance = _distance_m(previous, current)
        distance_m += segment_distance
        gap_seconds = (current["t_ms"] - previous["t_ms"]) / 1000.0
        max_gap_seconds = max(max_gap_seconds, gap_seconds)
        if gap_seconds > 0:
            max_speed_kmh = max(max_speed_kmh, segment_distance / gap_seconds * 3.6)

    duration_seconds = 0.0
    if len(normalized) >= 2 and timestamps[-1] > timestamps[0]:
        duration_seconds = (timestamps[-1] - timestamps[0]) / 1000.0

    accuracies = [p["accuracy_m"] for p in normalized if p["accuracy_m"] is not None]
    average_accuracy = sum(accuracies) / len(accuracies) if accuracies else 0.0
    if max_speed_kmh > MAX_SPEED_KMH:
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
        "max_gap_seconds": round(max_gap_seconds, 2),
        "average_accuracy_m": round(average_accuracy, 2),
    }
    status = "accepted" if not reasons else "rejected"
    return VerificationResult(status, reasons, metrics, route_hash)

