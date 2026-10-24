"""Bounty board and merchant coupon redemption (legacy v1 game)."""
import secrets
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import spatial_utils
from core.clock import _now_naive_utc, _to_naive_utc
from core.security import get_active_player, get_active_player_or_admin, get_current_admin_or_merchant, get_current_user_token
from database import get_db
from schemas import (
    BountyCompleteRequest,
    BountyCompleteResponse,
    BountyCreate,
    BountySummary,
    CouponLookupResponse,
    CouponRedeemResponse,
)
from services import ledger
from services.progression import get_rank, record_activity
from services.proofs import _consume_proof_or_409, _enforce_proof, _enforce_proof_gps_in_geofence


router = APIRouter()


@router.post("/api/v1/bounties", response_model=BountySummary)
def create_bounty(bounty: BountyCreate, db: Session = Depends(get_db), token_data: dict = Depends(get_current_admin_or_merchant)):
    """Seed a bounty. Admins can create both 'daily' (system-issued) and 'merchant_chest'
    (any merchant). Merchants can only create 'merchant_chest' bounties keyed to their own
    merchant_id. Geofence radius is in metres; distance to caller is filled with 0 since
    the creator may not be on-site."""
    role = token_data["role"]
    # v2.10 RBAC tightening: merchants can only create their own merchant_chest bounties.
    if role == "merchant":
        if bounty.bounty_type != "merchant_chest":
            raise HTTPException(status_code=403, detail="Merchants can only create merchant_chest bounties")
        if token_data["id"] != bounty.merchant_id:
            raise HTTPException(status_code=403, detail="Merchant can only create bounties keyed to their own merchant_id")
    # Daily bounties are admin-only; this also lets admins seed merchant_chest bounties for any merchant.
    if bounty.bounty_type == "daily" and role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create daily bounties")

    if bounty.bounty_type == "merchant_chest" and bounty.merchant_id is None:
        raise HTTPException(status_code=400, detail="merchant_chest requires merchant_id")
    if bounty.merchant_id is not None:
        merchant_row = db.query(models.Merchant).filter(models.Merchant.id == bounty.merchant_id).first()
        if not merchant_row:
            raise HTTPException(status_code=404, detail="Merchant not found")
        # v2.9 gate: merchant_chest bounties require an active merchant. Daily/system bounties
        # may carry a merchant_id for attribution but don't require active status.
        if bounty.bounty_type == "merchant_chest" and not merchant_row.is_active:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Merchant {merchant_row.id} is not active "
                    f"(payment_status={merchant_row.payment_status}). "
                    "Complete the pilot-fee payment before creating merchant_chest bounties."
                ),
            )

    new = models.Bounty(
        title=bounty.title,
        description=bounty.description,
        bounty_type=bounty.bounty_type,
        merchant_id=bounty.merchant_id,
        target_lat=bounty.target_lat,
        target_lng=bounty.target_lng,
        radius_m=bounty.radius_m,
        activity_type=bounty.activity_type,
        target_score=bounty.target_score,
        xp_reward=bounty.xp_reward,
        crystal_reward=bounty.crystal_reward,
        coupon_text=bounty.coupon_text,
        max_completions=bounty.max_completions,
        expires_at=_to_naive_utc(bounty.expires_at) if bounty.expires_at else None,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return BountySummary(
        id=new.id,
        title=new.title,
        description=new.description,
        bounty_type=new.bounty_type,
        target_lat=new.target_lat,
        target_lng=new.target_lng,
        radius_m=new.radius_m,
        activity_type=new.activity_type,
        target_score=new.target_score,
        xp_reward=new.xp_reward,
        crystal_reward=new.crystal_reward,
        has_coupon=bool(new.coupon_text),
        completions_remaining=new.max_completions,
        distance_km=0.0,
    )


@router.get("/api/v1/bounties/nearby", response_model=List[BountySummary])
def get_nearby_bounties(lat: float, lng: float, radius_km: float = 5.0, db: Session = Depends(get_db),
                        token_data: dict = Depends(get_active_player_or_admin)):
    """Returns active, non-expired, non-full bounties within `radius_km` of (lat, lng), sorted
    nearest-first. MVP uses an in-memory haversine sweep; PostGIS will replace this with
    `ST_DWithin` in Phase 2."""
    now = _now_naive_utc()
    candidates = (
        db.query(models.Bounty)
        .filter(models.Bounty.is_active == 1)
        .filter(models.Bounty.completions_count < models.Bounty.max_completions)
        .all()
    )

    nearby: List[BountySummary] = []
    for b in candidates:
        if b.expires_at is not None and b.expires_at <= now:
            continue
        dist = spatial_utils.haversine_distance(lat, lng, b.target_lat, b.target_lng)
        if dist > radius_km:
            continue
        nearby.append(BountySummary(
            id=b.id,
            title=b.title,
            description=b.description,
            bounty_type=b.bounty_type,
            target_lat=b.target_lat,
            target_lng=b.target_lng,
            radius_m=b.radius_m,
            activity_type=b.activity_type,
            target_score=b.target_score,
            xp_reward=b.xp_reward,
            crystal_reward=b.crystal_reward,
            has_coupon=bool(b.coupon_text),
            completions_remaining=max(0, b.max_completions - b.completions_count),
            distance_km=round(dist, 4),
        ))

    nearby.sort(key=lambda x: x.distance_km)
    return nearby


@router.post("/api/v1/bounties/{bounty_id}/complete", response_model=BountyCompleteResponse)
def complete_bounty(bounty_id: int, req: BountyCompleteRequest, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    if token_data["id"] != req.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to complete bounty for this user")
    """Validates proximity + score, awards XP/crystals, increments the matching attribute stat,
    and (for merchant chests) issues a single-use coupon code. One claim per user per bounty."""
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")
    if not bounty.is_active:
        raise HTTPException(status_code=400, detail="Bounty is no longer active")
    if bounty.completions_count >= bounty.max_completions:
        raise HTTPException(status_code=400, detail="Bounty has reached its max completions")

    now = _now_naive_utc()
    if bounty.expires_at is not None and bounty.expires_at <= now:
        raise HTTPException(status_code=400, detail="Bounty has expired")

    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Single-claim-per-user enforcement
    if (
        db.query(models.BountyCompletion)
        .filter(
            models.BountyCompletion.bounty_id == bounty.id,
            models.BountyCompletion.user_id == user.id,
        )
        .first()
    ):
        raise HTTPException(status_code=400, detail="You have already claimed this bounty")

    # Proximity check — convert geofence radius from metres to km to match haversine units.
    dist_km = spatial_utils.haversine_distance(req.user_lat, req.user_lng, bounty.target_lat, bounty.target_lng)
    if dist_km * 1000.0 > (bounty.radius_m or 0):
        raise HTTPException(status_code=400, detail="You are outside the bounty's geofence")

    # ML Referee: if a proof is attached, the activity type must match the bounty's, and the
    # verified score replaces the client-supplied score before the gate check below.
    verification = _enforce_proof(req.score_proof, expected_activity_type=bounty.activity_type)
    if verification is not None:
        req.score = verification.verified_score
    # Co-location: GPS samples in the proof must land inside the bounty's geofence —
    # mirrors the proximity check we already do on req.user_lat/lng but against the
    # workout's own GPS trace rather than the moment-of-submission position.
    _enforce_proof_gps_in_geofence(
        req.score_proof,
        center_lat=bounty.target_lat,
        center_lng=bounty.target_lng,
        radius_m=bounty.radius_m or 0,
        context="bounty_complete",
    )
    # Replay-attack guard
    _consume_proof_or_409(db, user.id, req.score_proof, source="bounty_complete")

    # Score gate — bounties with target_score=0 are proximity-only (e.g., merchant chests).
    if bounty.target_score > 0 and req.score < bounty.target_score:
        raise HTTPException(status_code=400, detail=f"Score {req.score} did not meet target {bounty.target_score}")

    # Award rewards
    device_ts = _to_naive_utc(req.device_timestamp)
    user.xp += bounty.xp_reward
    if bounty.crystal_reward:
        ledger.apply_crystal_delta(
            db, user, bounty.crystal_reward, "bounty_reward",
            related_bounty_id=bounty.id,
            note=f"Reward for bounty {bounty.id}",
        )
    user.last_activity_date = device_ts
    user.rank = get_rank(user.xp, user.last_activity_date)
    activity_score = req.score or bounty.target_score
    log_row = record_activity(
        db,
        user,
        activity_type=bounty.activity_type,
        score=activity_score,
        occurred_at=device_ts,
        source="bounty_complete",
        related_id=bounty.id,
        verified=bool(verification and verification.verified),
        confidence=verification.confidence if verification else 1.0,
        proof=req.score_proof,
    )
    stat_touched = log_row.stat_column if log_row else None

    # Coupon issuance for merchant chests
    coupon_code = None
    if bounty.coupon_text:
        coupon_code = secrets.token_urlsafe(8).upper()

    completion = models.BountyCompletion(
        bounty_id=bounty.id,
        user_id=user.id,
        score_submitted=req.score,
        xp_awarded=bounty.xp_reward,
        crystals_awarded=bounty.crystal_reward,
        coupon_code_issued=coupon_code,
        completed_at=device_ts,
    )
    bounty.completions_count += 1

    db.add(completion)
    db.commit()

    return BountyCompleteResponse(
        bounty_id=bounty.id,
        completed=True,
        xp_awarded=bounty.xp_reward,
        crystals_awarded=bounty.crystal_reward,
        stat_incremented=stat_touched,
        coupon_code=coupon_code,
        coupon_text=bounty.coupon_text,
        new_rank=user.rank,
        message=f"Bounty cleared. +{bounty.xp_reward} XP" + (f", +{bounty.crystal_reward} crystals" if bounty.crystal_reward else "") + (f", coupon {coupon_code}" if coupon_code else "") + ".",
    )


def _load_coupon_for_merchant(
    db: Session,
    code: str,
    token_data: dict,
) -> tuple[models.BountyCompletion, models.Bounty]:
    """Shared lookup + authz for the coupon endpoints. Returns the completion row and its
    bounty, or raises:
      - 404 if the code doesn't exist
      - 403 if a merchant calls about another merchant's bounty
      - 403 if any non-{merchant,admin} role calls"""
    role = token_data["role"]
    if role not in ("merchant", "admin"):
        raise HTTPException(status_code=403, detail="Coupon redemption is merchant-only")

    completion = (
        db.query(models.BountyCompletion)
        .filter(models.BountyCompletion.coupon_code_issued == code)
        .first()
    )
    if not completion:
        raise HTTPException(status_code=404, detail="Coupon not found")

    bounty = db.query(models.Bounty).filter(models.Bounty.id == completion.bounty_id).first()
    if not bounty:
        # Bounty was deleted but completion lingered — degenerate state, treat as not found.
        raise HTTPException(status_code=404, detail="Bounty for this coupon no longer exists")

    if role == "merchant" and bounty.merchant_id != token_data["id"]:
        raise HTTPException(status_code=403, detail="This coupon belongs to a different merchant")

    return completion, bounty


@router.get("/api/v1/coupons/{code}", response_model=CouponLookupResponse)
def lookup_coupon(
    code: str,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_user_token),
):
    """Pre-redemption check. Use this to validate a code shown at the till before tapping
    the redeem button — surfaces 'already redeemed' and 'wrong merchant' before a write."""
    completion, bounty = _load_coupon_for_merchant(db, code, token_data)
    return CouponLookupResponse(
        coupon_code=code,
        bounty_id=bounty.id,
        bounty_title=bounty.title,
        merchant_id=bounty.merchant_id or 0,
        customer_user_id=completion.user_id,
        coupon_text=bounty.coupon_text,
        issued_at=completion.completed_at,
        redeemed_at=completion.coupon_redeemed_at,
        redeemed_by_merchant_id=completion.coupon_redeemed_by_merchant_id,
        is_redeemed=completion.coupon_redeemed_at is not None,
    )


@router.post("/api/v1/coupons/{code}/redeem", response_model=CouponRedeemResponse)
def redeem_coupon(
    code: str,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_user_token),
):
    """Stamps a coupon as redeemed at the till. RBAC: only the merchant who owns the
    bounty (or an admin) can redeem; a re-redeem returns 409 so the customer can't
    re-use the code at another visit."""
    completion, bounty = _load_coupon_for_merchant(db, code, token_data)

    if completion.coupon_redeemed_at is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Coupon already redeemed at {completion.coupon_redeemed_at.isoformat()} "
                f"by merchant {completion.coupon_redeemed_by_merchant_id}"
            ),
        )

    # Admin redemptions stamp the bounty's owning merchant (so the audit trail follows the
    # storefront, not the admin). Merchant redemptions stamp themselves.
    redeeming_merchant_id = token_data["id"] if token_data["role"] == "merchant" else (bounty.merchant_id or 0)
    redeemed_at = _now_naive_utc()
    completion.coupon_redeemed_at = redeemed_at
    completion.coupon_redeemed_by_merchant_id = redeeming_merchant_id
    db.commit()

    return CouponRedeemResponse(
        coupon_code=code,
        bounty_id=bounty.id,
        customer_user_id=completion.user_id,
        redeemed_at=redeemed_at,
        message=f"Coupon redeemed for bounty '{bounty.title}'.",
    )


# NOTE (v2.10): a previous duplicate `/api/v1/merchants/{id}/bounties` endpoint was removed
# here. The canonical implementation now lives near the merchant-profile endpoint and uses
# `MerchantBountyAnalytics` (richer payload: completions_count + coupons_issued; admins
# can also call it).
