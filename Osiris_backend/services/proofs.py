"""ML Referee proof checks: verification, replay protection and geofence checks."""
import hashlib
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

import ml_referee
import models
import spatial_utils
from schemas import ActivityProof, VerificationResult



# --- Epic 2: ML Referee helpers + endpoint ---

def _run_verification(proof: ActivityProof) -> VerificationResult:
    """Bridge between the Pydantic proof shape and the pure-Python ml_referee module."""
    outcome = ml_referee.verify_activity(
        activity_type=proof.activity_type,
        declared_score=proof.declared_score,
        duration_seconds=proof.duration_seconds,
        accelerometer_samples=proof.accelerometer,
        pose_summary=proof.pose,
    )
    return VerificationResult(
        verified=outcome.verified,
        confidence=outcome.confidence,
        verified_score=outcome.verified_score,
        activity_type=outcome.activity_type,
        flags=outcome.flags,
    )


def _proof_dedup_key(user_id: int, proof: ActivityProof) -> str:
    """Deterministic SHA-256 hash over the bits of an ActivityProof that uniquely identify a
    workout. Re-submitting the same proof produces the same key. Used by the replay-attack
    guard. Pose data is excluded from the hash so a re-extract with slightly different
    angles still collides — the accelerometer trace is the high-entropy fingerprint."""
    sample_repr = ";".join(
        f"{s.t_ms}:{s.ax:.3f}:{s.ay:.3f}:{s.az:.3f}" for s in proof.accelerometer
    )
    raw = (
        f"{user_id}|{proof.device_timestamp.isoformat()}|"
        f"{proof.activity_type.lower()}|{proof.declared_score}|"
        f"{proof.duration_seconds:.3f}|{sample_repr}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _consume_proof_or_409(db: Session, user_id: int, proof: Optional[ActivityProof], source: str) -> None:
    """Idempotency guard. Call AFTER `_enforce_proof` succeeds — if the same proof was already
    consumed by any prior action endpoint, raises 409 Conflict so the client can treat the
    earlier success as authoritative. No-ops when proof is None (legacy trust path)."""
    if proof is None:
        return
    key = _proof_dedup_key(user_id, proof)
    existing = db.query(models.ProofConsumed).filter(models.ProofConsumed.proof_key == key).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"This proof has already been consumed by '{existing.source}' at {existing.consumed_at.isoformat()}",
        )
    db.add(models.ProofConsumed(proof_key=key, user_id=user_id, source=source))


def _enforce_proof(proof: Optional[ActivityProof], expected_activity_type: Optional[str] = None) -> Optional[VerificationResult]:
    """If a proof is attached to an action request, run it through the referee. Returns the
    full VerificationResult (callers read verified_score + confidence) or raises 400 on
    rejection. Returns None when no proof was supplied (legacy trust path)."""
    if proof is None:
        return None
    if expected_activity_type and proof.activity_type.lower() != expected_activity_type.lower():
        raise HTTPException(
            status_code=400,
            detail=f"Proof activity_type '{proof.activity_type}' does not match expected '{expected_activity_type}'",
        )
    result = _run_verification(proof)
    if not result.verified:
        raise HTTPException(
            status_code=400,
            detail=f"ML Referee rejected proof (confidence {result.confidence:.2f}): {'; '.join(result.flags) or 'no flags'}",
        )
    return result


def _enforce_proof_gps_in_polygon(
    proof: Optional[ActivityProof],
    polygon: list,
    context: str,
) -> None:
    """Co-location guard: if the proof carries GPS samples, at least 80% of samples must fall
    inside `polygon`. Without this, a single fake sample or centroid trick could bypass location.

    Permissive on purpose: an empty GPS channel is treated as 'no check' so legacy clients
    that don't ship GPS yet still work.

    `polygon` is a list of {lat, lng} dicts (the JSON shape stored in Domain.geometry_json).
    Raises 400 with a referee-style flag on mismatch."""
    if proof is None or not proof.gps or not polygon:
        return
    inside_count = sum(
        1 for s in proof.gps if spatial_utils.point_in_polygon(s.lng, s.lat, polygon)
    )
    ratio = inside_count / len(proof.gps)
    if ratio >= 0.8 or (len(proof.gps) == 1 and inside_count == 1):
        return
    avg_lat = sum(s.lat for s in proof.gps) / len(proof.gps)
    avg_lng = sum(s.lng for s in proof.gps) / len(proof.gps)
    raise HTTPException(
        status_code=400,
        detail=(
            f"ML Referee rejected proof ({context}): only {ratio*100:.1f}% of GPS samples "
            f"(centroid {avg_lat:.6f}, {avg_lng:.6f}) fall inside expected polygon (80% required)."
        ),
    )


def _enforce_proof_gps_in_geofence(
    proof: Optional[ActivityProof],
    center_lat: float,
    center_lng: float,
    radius_m: float,
    context: str,
) -> None:
    """Geofence variant of the co-location guard for circular bounty zones. Requires at least 80%
    of samples to fall within the geofence radius + 20m GPS margin."""
    if proof is None or not proof.gps or radius_m <= 0:
        return
    allowed_radius_m = radius_m + 20.0
    inside_count = sum(
        1 for s in proof.gps
        if spatial_utils.haversine_distance(s.lat, s.lng, center_lat, center_lng) * 1000.0 <= allowed_radius_m
    )
    ratio = inside_count / len(proof.gps)
    if ratio >= 0.8 or (len(proof.gps) == 1 and inside_count == 1):
        return
    avg_lat = sum(s.lat for s in proof.gps) / len(proof.gps)
    avg_lng = sum(s.lng for s in proof.gps) / len(proof.gps)
    dist_km = spatial_utils.haversine_distance(avg_lat, avg_lng, center_lat, center_lng)
    raise HTTPException(
        status_code=400,
        detail=(
            f"ML Referee rejected proof ({context}): only {ratio*100:.1f}% of GPS samples "
            f"are within {allowed_radius_m:.0f}m geofence (centroid is {dist_km*1000:.0f}m away)."
        ),
    )
