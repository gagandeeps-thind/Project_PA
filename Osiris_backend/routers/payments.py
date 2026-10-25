"""Payments: merchant payment intents, provider webhooks, and player crystal top-ups.
Money path: every crystal movement goes through services.ledger.apply_crystal_delta."""
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from core.clock import _now_naive_utc, _to_naive_utc
from core.rate_limit import _rl_webhook
from core.security import get_active_player, get_current_merchant, verify_webhook_signature
from database import get_db
from schemas import (
    CrystalPackInfo,
    CrystalPurchaseIntentRequest,
    CrystalPurchaseIntentResponse,
    PaymentIntentResponse,
    PaymentWebhookRequest,
    PaymentWebhookResponse,
)
from services import ledger, stripe_gateway


router = APIRouter()


# --- Phase 3: player crystal top-up (one-way real-money purchase) ---
#
# Server-authoritative crystal packs. The client picks a `pack_id`; the SERVER decides the
# price and the crystal grant. The client never sends an amount — that's the whole point, it
# stops a tampered client buying 1,000,000 crystals for $0.01.
#
# NOTE: this purchase path is intentionally isolated behind server-authoritative packs,
# payment-provider confirmation, and ledgered fulfillment.
CRYSTAL_PACKS: dict[str, dict] = {
    "starter":    {"crystals": 500,  "amount_cents": 499,  "label": "Starter Pouch"},
    "adventurer": {"crystals": 1200, "amount_cents": 999,  "label": "Adventurer's Cache"},
    "champion":   {"crystals": 2600, "amount_cents": 1999, "label": "Champion's Hoard"},
}
CRYSTAL_PURCHASE_CURRENCY = "usd"


@router.post("/api/v1/merchants/{merchant_id}/payments/intent", response_model=PaymentIntentResponse)
def create_payment_intent(
    merchant_id: int,
    token_data: dict = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """Initiate the pilot-fee payment via Stripe. Creates a Stripe PaymentIntent for the
    merchant's `pilot_fee_cents` and returns its `client_secret` so the Flutter Stripe SDK can
    confirm the card on-device. Activation does NOT happen here — it happens when Stripe POSTs
    `payment_intent.succeeded` to /payments/stripe/webhook."""
    if token_data["id"] != merchant_id:
        raise HTTPException(status_code=403, detail="Merchants can only pay their own pilot fee")

    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    if merchant.is_active:
        raise HTTPException(status_code=400, detail="Merchant is already active; nothing to pay")

    try:
        intent = stripe_gateway.create_payment_intent(
            amount_cents=merchant.pilot_fee_cents,
            currency=CRYSTAL_PURCHASE_CURRENCY,
            description=f"Osiris merchant pilot fee — merchant {merchant.id}",
            metadata={"kind": "merchant_pilot_fee", "merchant_id": str(merchant.id)},
            idempotency_key=f"merchant_pilot_fee:{merchant.id}",
        )
    except stripe_gateway.StripeNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))

    merchant.payment_provider_id = intent.id
    merchant.payment_status = "payment_pending"
    db.commit()

    return PaymentIntentResponse(
        merchant_id=merchant.id,
        pilot_fee_cents=merchant.pilot_fee_cents,
        provider_payment_id=intent.id,
        payment_status=merchant.payment_status,
        client_secret=intent.client_secret,
        publishable_key=stripe_gateway.STRIPE_PUBLISHABLE_KEY,
        next_action="Confirm the PaymentIntent client_secret with the Stripe SDK in the app.",
    )


@router.post("/api/v1/payments/webhook", response_model=PaymentWebhookResponse)
def payment_webhook(
    body: bytes = Depends(verify_webhook_signature),
    db: Session = Depends(get_db),
    _rl: None = Depends(_rl_webhook),
):
    """Endpoint the payment provider POSTs to when a payment reaches a terminal state.
    NOT JWT-gated — providers don't carry our JWTs. Signature verification (`X-Provider-
    Signature` HMAC-SHA256 over the raw body) is performed via the `verify_webhook_signature`
    dependency, gated by the `OSIRIS_WEBHOOK_SECRET` env var (off in dev/MVP, on in prod).

    Activation rule: only `payment_status='payment_successful'` flips `is_active=True`
    and writes a PlatformRevenue row. `payment_pending` and `payment_declined` update
    the merchant's status but leave `is_active=False`."""
    try:
        req = PaymentWebhookRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid webhook payload: {e}")

    valid_statuses = {"payment_successful", "payment_pending", "payment_declined"}
    if req.payment_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid payment_status. Expected one of {sorted(valid_statuses)}",
        )

    # Production requires a provider_event_id — real Stripe always sends `event.id`, and
    # without it we can't dedupe retries. Dev / MVP can omit it (no real provider yet).
    if not req.provider_event_id and os.environ.get("OSIRIS_ENV", "").lower() == "production":
        raise HTTPException(
            status_code=400,
            detail="provider_event_id is required in production (needed for retry dedup).",
        )

    # Event-level idempotency: if we've already processed this provider_event_id, return
    # the merchant's current state without re-running side effects (no double revenue, no
    # double activate). Stripe and most providers retry 5xx responses; this guard is what
    # makes the webhook safe to retry.
    if req.provider_event_id:
        prior_event = (
            db.query(models.PaymentWebhookEvent)
            .filter(models.PaymentWebhookEvent.provider_event_id == req.provider_event_id)
            .first()
        )
        if prior_event:
            existing = db.query(models.Merchant).filter(models.Merchant.id == prior_event.merchant_id).first()
            if not existing:
                # Event row points at a merchant that no longer exists — degenerate.
                raise HTTPException(status_code=404, detail="Merchant from prior event not found")
            return PaymentWebhookResponse(
                merchant_id=existing.id,
                payment_status=existing.payment_status,
                is_active=bool(existing.is_active),
                message=(
                    f"Duplicate event {req.provider_event_id} ignored "
                    f"(already processed at {prior_event.received_at.isoformat()})."
                ),
            )

    merchant = db.query(models.Merchant).filter(models.Merchant.id == req.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    # Cross-check provider_payment_id if one was previously stored — guards against
    # webhooks for a different intent landing on this merchant.
    if merchant.payment_provider_id and merchant.payment_provider_id != req.provider_payment_id:
        raise HTTPException(
            status_code=400,
            detail="provider_payment_id does not match the merchant's last payment intent",
        )

    occurred_at = _to_naive_utc(req.occurred_at)
    merchant.payment_status = req.payment_status
    merchant.payment_provider_id = req.provider_payment_id

    if req.payment_status == "payment_successful":
        # Idempotency: don't double-record revenue if the same successful webhook fires twice.
        already_active = bool(merchant.is_active)
        merchant.is_active = True
        merchant.last_payment_at = occurred_at
        if not already_active and req.amount_cents > 0:
            db.add(models.PlatformRevenue(
                source="merchant_pilot_fee",
                amount=req.amount_cents,
                user_id=None,
                note=f"Merchant {merchant.id} pilot fee via {req.provider_payment_id}",
            ))
        message = "Merchant activated. Pilot fee recorded."
    else:
        # Pending or declined: do NOT flip is_active. Merchant can retry.
        message = f"Status updated to {req.payment_status}; merchant remains inactive."

    # Record the event AFTER side effects but in the same transaction. The unique index on
    # provider_event_id makes a concurrent duplicate delivery fail at commit time; we catch
    # the IntegrityError and treat it as a replay.
    if req.provider_event_id:
        db.add(models.PaymentWebhookEvent(
            provider_event_id=req.provider_event_id,
            merchant_id=merchant.id,
            payment_status=req.payment_status,
            provider_payment_id=req.provider_payment_id,
            amount_cents=req.amount_cents,
            received_at=_now_naive_utc(),
        ))

    try:
        db.commit()
    except IntegrityError:
        # Concurrent retry beat us to the unique-index insert. Roll back and replay
        # the prior outcome instead.
        db.rollback()
        existing = db.query(models.Merchant).filter(models.Merchant.id == req.merchant_id).first()
        return PaymentWebhookResponse(
            merchant_id=existing.id if existing else req.merchant_id,
            payment_status=existing.payment_status if existing else req.payment_status,
            is_active=bool(existing.is_active) if existing else False,
            message=(
                f"Duplicate event {req.provider_event_id} raced — earlier delivery won."
            ),
        )
    return PaymentWebhookResponse(
        merchant_id=merchant.id,
        payment_status=merchant.payment_status,
        is_active=bool(merchant.is_active),
        message=message,
    )


# --- Phase 3: Stripe-native webhook + shared terminal-state processors ---
#
# Stripe event type -> our internal payment_status vocabulary. Only these are acted on; any
# other event type is acknowledged with 200 and ignored so Stripe stops retrying it.
_STRIPE_EVENT_TO_STATUS = {
    "payment_intent.succeeded": "payment_successful",
    "payment_intent.payment_failed": "payment_declined",
    "payment_intent.processing": "payment_pending",
}


def _apply_merchant_pilot_fee(
    db: Session, *, merchant, payment_status: str, provider_payment_id: str,
    amount_cents: int, occurred_at: datetime,
) -> str:
    """Apply a terminal payment status to a merchant pilot fee. Same activation rule as the
    generic webhook: only 'payment_successful' flips is_active and records revenue (once, on
    the activating transition). Does NOT commit — the caller owns the transaction."""
    merchant.payment_status = payment_status
    merchant.payment_provider_id = provider_payment_id
    if payment_status == "payment_successful":
        already_active = bool(merchant.is_active)
        merchant.is_active = True
        merchant.last_payment_at = occurred_at
        if not already_active and amount_cents > 0:
            db.add(models.PlatformRevenue(
                source="merchant_pilot_fee",
                amount=amount_cents,
                user_id=None,
                note=f"Merchant {merchant.id} pilot fee via {provider_payment_id}",
            ))
        return "Merchant activated. Pilot fee recorded."
    return f"Status updated to {payment_status}; merchant remains inactive."


def _fulfill_crystal_purchase(
    db: Session, *, purchase, payment_status: str, amount_cents: int, occurred_at: datetime,
) -> str:
    """Apply a terminal payment status to a player crystal purchase.

    RED LINE — no double-mint: on success we credit crystals through the ledger EXACTLY ONCE.
    The guard is `purchase.status`: a row already 'succeeded' is a no-op, so a replayed/duplicate
    Stripe event can never credit twice. Does NOT commit — the caller owns the transaction."""
    if payment_status == "payment_successful":
        if purchase.status == "succeeded":
            return "Crystal purchase already fulfilled (no-op)."
        user = db.query(models.User).filter(models.User.id == purchase.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Purchasing user not found")
        entry = ledger.apply_crystal_delta(
            db, user, purchase.crystal_amount, "crystal_purchase",
            note=f"Stripe top-up {purchase.stripe_payment_intent_id} ({purchase.pack_id})",
        )
        db.flush()  # assign entry.id so the purchase can link to its ledger row
        purchase.status = "succeeded"
        purchase.crystal_ledger_id = entry.id
        purchase.fulfilled_at = occurred_at
        if amount_cents > 0:
            db.add(models.PlatformRevenue(
                source="crystal_purchase",
                amount=amount_cents,
                user_id=purchase.user_id,
                note=f"User {purchase.user_id} crystal top-up {purchase.stripe_payment_intent_id}",
            ))
        return f"Credited {purchase.crystal_amount} crystals to user {purchase.user_id}."
    if payment_status == "payment_declined":
        if purchase.status != "succeeded":
            purchase.status = "failed"
        return "Crystal purchase marked failed."
    return f"Crystal purchase status updated to {payment_status}."


@router.post("/api/v1/payments/stripe/webhook", response_model=PaymentWebhookResponse)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    _rl: None = Depends(_rl_webhook),
):
    """Stripe-native webhook. Verifies the `Stripe-Signature` header against the RAW body with
    `stripe.Webhook.construct_event`, then routes `payment_intent.*` events by their metadata
    `kind` to the merchant-pilot-fee or crystal-purchase processor.

    Event-level idempotency: PaymentWebhookEvent keyed on the Stripe `event.id` (unique index)
    makes retried deliveries no-ops. Purchase-level idempotency (no double-mint) is enforced
    separately by `_fulfill_crystal_purchase`."""
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe_gateway.construct_event(payload, sig_header)
    except stripe_gateway.StripeNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")
    except Exception:
        # stripe.error.SignatureVerificationError (and any other verification failure).
        raise HTTPException(status_code=401, detail="Invalid Stripe signature")

    event_id = event["id"]
    event_type = event["type"]

    payment_status = _STRIPE_EVENT_TO_STATUS.get(event_type)
    if payment_status is None:
        return PaymentWebhookResponse(
            merchant_id=0, payment_status="ignored", is_active=False,
            message=f"Event type {event_type} acknowledged; no action taken.",
        )

    # Event-level dedup: if we've seen this Stripe event.id, replay nothing.
    prior = (
        db.query(models.PaymentWebhookEvent)
        .filter(models.PaymentWebhookEvent.provider_event_id == event_id)
        .first()
    )
    if prior:
        return PaymentWebhookResponse(
            merchant_id=prior.merchant_id or 0,
            payment_status=prior.payment_status or payment_status,
            is_active=False,
            message=f"Duplicate event {event_id} ignored (already processed).",
        )

    intent = event["data"]["object"]
    pi_id = intent["id"]
    amount_cents = intent.get("amount") or 0
    metadata = intent.get("metadata") or {}
    kind = metadata.get("kind")
    occurred_at = _now_naive_utc()

    merchant_id_for_event: Optional[int] = None
    user_id_for_event: Optional[int] = None

    if kind == "merchant_pilot_fee":
        merchant = (
            db.query(models.Merchant)
            .filter(models.Merchant.id == int(metadata["merchant_id"]))
            .first()
        )
        if not merchant:
            raise HTTPException(status_code=404, detail="Merchant not found")
        merchant_id_for_event = merchant.id
        message = _apply_merchant_pilot_fee(
            db, merchant=merchant, payment_status=payment_status,
            provider_payment_id=pi_id, amount_cents=amount_cents, occurred_at=occurred_at,
        )
        resp_merchant_id, resp_status, resp_active = (
            merchant.id, merchant.payment_status, bool(merchant.is_active),
        )
    elif kind == "crystal_purchase":
        purchase = (
            db.query(models.CrystalPurchase)
            .filter(models.CrystalPurchase.stripe_payment_intent_id == pi_id)
            .first()
        )
        if not purchase:
            raise HTTPException(status_code=404, detail="Crystal purchase not found")
        user_id_for_event = purchase.user_id
        message = _fulfill_crystal_purchase(
            db, purchase=purchase, payment_status=payment_status,
            amount_cents=amount_cents, occurred_at=occurred_at,
        )
        resp_merchant_id, resp_status, resp_active = (
            0, purchase.status, purchase.status == "succeeded",
        )
    else:
        return PaymentWebhookResponse(
            merchant_id=0, payment_status="ignored", is_active=False,
            message=f"Event {event_id} metadata.kind={kind!r} is unknown; ignored.",
        )

    # Record the event AFTER side effects, same transaction. The unique index on
    # provider_event_id turns a concurrent duplicate delivery into an IntegrityError at commit.
    db.add(models.PaymentWebhookEvent(
        provider_event_id=event_id,
        merchant_id=merchant_id_for_event,
        user_id=user_id_for_event,
        event_type=event_type,
        payment_status=payment_status,
        provider_payment_id=pi_id,
        amount_cents=amount_cents,
        received_at=_now_naive_utc(),
    ))

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return PaymentWebhookResponse(
            merchant_id=merchant_id_for_event or 0,
            payment_status=payment_status,
            is_active=False,
            message=f"Duplicate event {event_id} raced — earlier delivery won.",
        )

    return PaymentWebhookResponse(
        merchant_id=resp_merchant_id, payment_status=resp_status,
        is_active=resp_active, message=message,
    )


# --- Phase 3: player crystal top-up (one-way purchase) endpoints ---

@router.get("/api/v1/payments/crystals/packs", response_model=List[CrystalPackInfo])
def list_crystal_packs():
    """Buyable crystal packs with server-authoritative pricing. The client renders these and
    sends back only a `pack_id`; it never sets a price."""
    return [
        CrystalPackInfo(
            pack_id=pid, label=p["label"], crystals=p["crystals"],
            amount_cents=p["amount_cents"], currency=CRYSTAL_PURCHASE_CURRENCY,
        )
        for pid, p in CRYSTAL_PACKS.items()
    ]


@router.post("/api/v1/payments/crystals/intent", response_model=CrystalPurchaseIntentResponse)
def create_crystal_purchase_intent(
    req: CrystalPurchaseIntentRequest,
    token_data: dict = Depends(get_active_player),
    db: Session = Depends(get_db),
):
    """Start a real-money crystal top-up. The price and crystal grant come from CRYSTAL_PACKS
    on the server — the client only chooses a `pack_id`. Creates a Stripe PaymentIntent and a
    'pending' CrystalPurchase; crystals are credited later by the webhook on success."""
    pack = CRYSTAL_PACKS.get(req.pack_id)
    if not pack:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown pack_id {req.pack_id!r}. Valid packs: {sorted(CRYSTAL_PACKS)}",
        )

    user_id = token_data["id"]
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        intent = stripe_gateway.create_payment_intent(
            amount_cents=pack["amount_cents"],
            currency=CRYSTAL_PURCHASE_CURRENCY,
            description=f"Osiris crystal top-up — {pack['label']} for user {user_id}",
            metadata={
                "kind": "crystal_purchase",
                "user_id": str(user_id),
                "pack_id": req.pack_id,
                "crystal_amount": str(pack["crystals"]),
            },
        )
    except stripe_gateway.StripeNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))

    purchase = models.CrystalPurchase(
        user_id=user_id,
        pack_id=req.pack_id,
        crystal_amount=pack["crystals"],
        amount_cents=pack["amount_cents"],
        currency=CRYSTAL_PURCHASE_CURRENCY,
        stripe_payment_intent_id=intent.id,
        status="pending",
    )
    db.add(purchase)
    db.commit()
    db.refresh(purchase)

    return CrystalPurchaseIntentResponse(
        purchase_id=purchase.id,
        pack_id=req.pack_id,
        crystal_amount=pack["crystals"],
        amount_cents=pack["amount_cents"],
        currency=CRYSTAL_PURCHASE_CURRENCY,
        payment_intent_id=intent.id,
        client_secret=intent.client_secret,
        publishable_key=stripe_gateway.STRIPE_PUBLISHABLE_KEY,
        status=purchase.status,
    )
