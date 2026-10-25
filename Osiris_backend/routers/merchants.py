"""Merchant accounts, merchant analytics, admin merchant management and platform revenue."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
from core.clock import _now_naive_utc
from core.security import get_current_admin, get_current_user_token, get_password_hash
from database import get_db
from schemas import (
    AdminMerchantListItem,
    AdminMerchantToggleResponse,
    MerchantBountyAnalytics,
    MerchantCreate,
    MerchantProfile,
    MerchantResponse,
    PlatformRevenueSummary,
)
from services.accounts import _check_email_unique


router = APIRouter()


@router.get("/api/v1/platform/revenue", response_model=PlatformRevenueSummary)
def get_platform_revenue(db: Session = Depends(get_db), token_data: dict = Depends(get_current_admin)):
    """Aggregates the PlatformRevenue ledger so admins can audit total platform earnings and
    the breakdown by source. Read-only; safe to expose internally during MVP. Production will
    gate this behind an admin role."""
    rows = db.query(models.PlatformRevenue).all()
    total = sum(r.amount or 0 for r in rows)
    by_source: dict = {}
    for r in rows:
        by_source[r.source] = by_source.get(r.source, 0) + (r.amount or 0)
    return PlatformRevenueSummary(total_crystals=total, by_source=by_source, row_count=len(rows))


# --- Epic 1: Bounty Board Endpoints ---

@router.post("/api/v1/merchants/register", response_model=MerchantResponse)
def register_merchant(merchant: MerchantCreate, db: Session = Depends(get_db)):
    """Registers a B2B partner who can sponsor merchant_chest bounties at their storefront.
    Newly-registered merchants start `is_active=False` / `payment_status='payment_pending'`;
    they must complete the pilot-fee flow (or be activated by an admin) before they can
    create merchant_chest bounties."""
    _check_email_unique(db, merchant.email)
    new = models.Merchant(
        name=merchant.name,
        email=merchant.email,
        hashed_password=get_password_hash(merchant.password),
        business_type=merchant.business_type,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return new


# --- v2.9: Merchant payment + activation endpoints ---

@router.get("/api/v1/merchants/{merchant_id}", response_model=MerchantProfile)
def get_merchant_profile(
    merchant_id: int,
    token_data: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db),
):
    """Fetch a merchant's full profile (incl. activation + payment status). Accessible to
    the merchant themselves (same-id check) and to any admin. Used post-login by the
    Flutter app to refresh state and decide whether to show the 'pay your pilot fee' UI."""
    role = token_data["role"]
    caller_id = token_data["id"]
    if role == "merchant" and caller_id != merchant_id:
        raise HTTPException(status_code=403, detail="Merchants can only view their own profile")
    if role not in ("merchant", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


@router.get("/api/v1/merchants/{merchant_id}/bounties", response_model=List[MerchantBountyAnalytics])
def get_merchant_bounties(
    merchant_id: int,
    token_data: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db),
):
    """Returns every bounty owned by the merchant with completion + coupon-issued counts.
    Powers the merchant portal's analytics view. Auth: merchant must be the owner, or
    caller must be admin."""
    role = token_data["role"]
    caller_id = token_data["id"]
    if role == "merchant" and caller_id != merchant_id:
        raise HTTPException(status_code=403, detail="Merchants can only view their own bounties")
    if role not in ("merchant", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    bounties = (
        db.query(models.Bounty)
        .filter(models.Bounty.merchant_id == merchant_id)
        .order_by(models.Bounty.created_at.desc())
        .all()
    )

    out: List[MerchantBountyAnalytics] = []
    for b in bounties:
        coupon_count = (
            db.query(models.BountyCompletion)
            .filter(
                models.BountyCompletion.bounty_id == b.id,
                models.BountyCompletion.coupon_code_issued.isnot(None),
            )
            .count()
        )
        out.append(MerchantBountyAnalytics(
            id=b.id,
            title=b.title,
            bounty_type=b.bounty_type,
            target_lat=b.target_lat,
            target_lng=b.target_lng,
            is_active=bool(b.is_active),
            completions_count=b.completions_count or 0,
            completions_remaining=max(0, (b.max_completions or 0) - (b.completions_count or 0)),
            coupons_issued=coupon_count,
            xp_reward=b.xp_reward or 0,
            crystal_reward=b.crystal_reward or 0,
            created_at=b.created_at,
            expires_at=b.expires_at,
        ))
    return out


# --- v2.9: Admin merchant management (manual fallback for refunds / disputes / demos) ---

@router.get("/api/v1/admin/merchants", response_model=List[AdminMerchantListItem])
def admin_list_merchants(
    status: Optional[str] = None,           # 'pending' | 'active' | 'declined' | 'all' (default 'all')
    token_data: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Admin-only triage view. Filter by activation status; sorted newest-first."""
    q = db.query(models.Merchant)
    if status == "active":
        q = q.filter(models.Merchant.is_active == True)  # noqa: E712
    elif status == "pending":
        q = q.filter(models.Merchant.payment_status == "payment_pending")
    elif status == "declined":
        q = q.filter(models.Merchant.payment_status == "payment_declined")
    elif status not in (None, "all"):
        raise HTTPException(status_code=400, detail="status must be one of: pending, active, declined, all")
    rows = q.order_by(models.Merchant.created_at.desc()).all()
    return rows


@router.post("/api/v1/admin/merchants/{merchant_id}/activate", response_model=AdminMerchantToggleResponse)
def admin_activate_merchant(
    merchant_id: int,
    token_data: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Manual activation fallback. Use when payment was confirmed out-of-band (e.g., bank
    transfer for a pilot merchant) or to re-activate after a deactivate. Records a
    PlatformRevenue row only if the merchant wasn't already active."""
    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    already_active = bool(merchant.is_active)
    merchant.is_active = True
    merchant.payment_status = "payment_successful"
    merchant.last_payment_at = _now_naive_utc()
    if not already_active and (merchant.pilot_fee_cents or 0) > 0:
        db.add(models.PlatformRevenue(
            source="merchant_pilot_fee",
            amount=merchant.pilot_fee_cents,
            user_id=None,
            note=f"Manual admin activation of merchant {merchant.id}",
        ))
    db.commit()
    return AdminMerchantToggleResponse(
        merchant_id=merchant.id,
        is_active=True,
        payment_status=merchant.payment_status,
        message="Merchant activated by admin.",
    )


@router.post("/api/v1/admin/merchants/{merchant_id}/deactivate", response_model=AdminMerchantToggleResponse)
def admin_deactivate_merchant(
    merchant_id: int,
    token_data: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Manual deactivation. Use for refunds, policy violations, or to remove a merchant
    from the pilot. Does not write a PlatformRevenue row (no money flowed)."""
    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    merchant.is_active = False
    db.commit()
    return AdminMerchantToggleResponse(
        merchant_id=merchant.id,
        is_active=False,
        payment_status=merchant.payment_status,
        message="Merchant deactivated by admin.",
    )
