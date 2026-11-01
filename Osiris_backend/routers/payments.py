"""Payments: merchant payment intents, provider webhooks, and player crystal top-ups.
Money path: every crystal movement goes through services.ledger.apply_crystal_delta."""
import logging
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
    GooglePlayEntitlementsResponse,
    GooglePlayVerifyRequest,
    GooglePlayVerifyResponse,
    PaymentIntentResponse,
    PaymentWebhookRequest,
    PaymentWebhookResponse,
)
from services import google_play, ledger, stripe_gateway


logger = logging.getLogger(__name__)
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


# --- Google Play Billing (Android) ---
#
# The app buys through Play Billing and sends the purchase token here; only the server asks Google
# whether it is real and only the server grants. Product ids are the ones created in Play Console.
# Crystal grants reuse CRYSTAL_PACKS; Play Console sets the (localized) prices.
PLAY_CRYSTAL_PRODUCTS = {f"osiris_crystals_{pack_id}": pack_id for pack_id in CRYSTAL_PACKS}
PLAY_FOUNDER_PACK = "osiris_founder_pack"
PLAY_PASS_PRODUCTS = frozenset({"osiris_pass_monthly", "osiris_pass_annual"})
_SUB_STATES = {
    "SUBSCRIPTION_STATE_PENDING": "pending",
    "SUBSCRIPTION_STATE_ACTIVE": "active",
    "SUBSCRIPTION_STATE_PAUSED": "paused",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "in_grace_period",
    "SUBSCRIPTION_STATE_ON_HOLD": "on_hold",
    "SUBSCRIPTION_STATE_CANCELED": "canceled",  # auto-renew off; the paid period still counts
    "SUBSCRIPTION_STATE_EXPIRED": "expired",
    "SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED": "canceled",
}
_PASS_ENTITLED = frozenset({"active", "in_grace_period", "canceled"})


def _play_kind(product_id: str) -> str:
    if product_id in PLAY_CRYSTAL_PRODUCTS:
        return "consumable"
    if product_id == PLAY_FOUNDER_PACK:
        return "non_consumable"
    if product_id in PLAY_PASS_PRODUCTS:
        return "subscription"
    raise HTTPException(status_code=404, detail=f"Unknown Google Play product {product_id!r}.")


def _pass_entitled(row: models.GooglePlayPurchase, now: datetime) -> bool:
    return row.state in _PASS_ENTITLED and row.expires_at is not None and row.expires_at > now


def _apply_subscription(row: models.GooglePlayPurchase, sub: dict) -> None:
    """Copy Google's subscriptionsv2 state onto `row`; a token that is not for this product is invalid."""
    items = [i for i in sub.get("lineItems") or [] if i.get("productId") == row.product_id]
    if not items:
        raise google_play.InvalidPurchaseError("This subscription token is for a different product.")
    expiries = [t for t in (google_play.parse_time(i.get("expiryTime")) for i in items) if t]
    row.state = _SUB_STATES.get(sub.get("subscriptionState"), "pending")
    row.expires_at = max(expiries, default=None)
    row.order_id = sub.get("latestOrderId") or row.order_id


def _commit_play_row(
    db: Session, row: models.GooglePlayPurchase, user_id: int,
) -> tuple[models.GooglePlayPurchase, bool]:
    """Commit `row`. Returns (row, False) when a concurrent call stored this token first: the
    unique index rolled this call back, crystals included, so nothing is granted twice."""
    token = row.purchase_token
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        stored = db.query(models.GooglePlayPurchase).filter(
            models.GooglePlayPurchase.purchase_token == token,
        ).first()
        if stored is None or stored.user_id != user_id:
            raise HTTPException(status_code=409, detail="This purchase is linked to another account.")
        return stored, False
    db.refresh(row)
    return row, True


def _acknowledge(kind: str, product_id: str, token: str, ack_needed: bool) -> None:
    """Acknowledge after the grant is committed, or Google refunds the purchase after 3 days.
    A failure is only logged: the app's consumeAsync also acknowledges, and a re-verify retries."""
    if not ack_needed:
        return
    try:
        if kind == "subscription":
            google_play.acknowledge_subscription(product_id, token)
        else:
            google_play.acknowledge_product(product_id, token)
    except google_play.GooglePlayError as exc:
        logger.warning("google play acknowledge failed for %s: %s", product_id, exc)


def _play_response(
    db: Session, row: models.GooglePlayPurchase, user_id: int, crystals: int,
) -> GooglePlayVerifyResponse:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if row.kind == "subscription":
        entitled = _pass_entitled(row, _now_naive_utc())
    else:
        entitled = row.state in ("credited", "owned")
    return GooglePlayVerifyResponse(
        product_id=row.product_id, kind=row.kind, state=row.state, crystals_credited=crystals,
        balance=user.mana_crystals if user else None, expires_at=row.expires_at,
        consume=row.kind == "consumable" and row.state == "credited", entitled=entitled,
    )


def _verify_product(
    db: Session, req: GooglePlayVerifyRequest, kind: str, user_id: int, row,
) -> GooglePlayVerifyResponse:
    purchase = google_play.get_product_purchase(req.product_id, req.purchase_token)
    state = {0: "purchased", 1: "canceled", 2: "pending"}.get(purchase.get("purchaseState"), "pending")
    if state != "purchased":
        # Nothing is granted; Play Billing re-delivers a pending purchase once it completes.
        if row:  # a refunded founder pack stops unlocking
            row.state = state
            db.commit()
        return GooglePlayVerifyResponse(product_id=req.product_id, kind=kind, state=state)
    row = row or models.GooglePlayPurchase(
        user_id=user_id, purchase_token=req.purchase_token, product_id=req.product_id, kind=kind, state="owned",
    )
    row.order_id = purchase.get("orderId")
    crystals = 0
    if kind == "consumable":
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        pack_id = PLAY_CRYSTAL_PRODUCTS[req.product_id]
        crystals = CRYSTAL_PACKS[pack_id]["crystals"]
        test = " (license test)" if purchase.get("purchaseType") == 0 else ""
        entry = ledger.apply_crystal_delta(
            db, user, crystals, "crystal_purchase", note=f"Google Play {row.order_id} ({pack_id}){test}",
        )
        db.flush()
        row.crystal_ledger_id = entry.id
        row.state = "credited"
    row, fresh = _commit_play_row(db, row, user_id)
    _acknowledge(kind, req.product_id, req.purchase_token, purchase.get("acknowledgementState") == 0)
    return _play_response(db, row, user_id, crystals if fresh else 0)


def _verify_subscription(
    db: Session, req: GooglePlayVerifyRequest, user_id: int, row,
) -> GooglePlayVerifyResponse:
    sub = google_play.get_subscription(req.purchase_token)
    row = row or models.GooglePlayPurchase(
        user_id=user_id, purchase_token=req.purchase_token, product_id=req.product_id,
        kind="subscription", state="pending",
    )
    _apply_subscription(row, sub)
    row, _ = _commit_play_row(db, row, user_id)
    ack_needed = sub.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_PENDING" and row.state in _PASS_ENTITLED
    _acknowledge("subscription", req.product_id, req.purchase_token, ack_needed)
    return _play_response(db, row, user_id, 0)


@router.post("/api/v2/payments/google-play/verify", response_model=GooglePlayVerifyResponse)
def verify_google_play_purchase(
    req: GooglePlayVerifyRequest,
    token_data: dict = Depends(get_active_player),
    db: Session = Depends(get_db),
):
    """Verify a Play Billing purchase with Google and grant it. Crystal packs are credited through
    the ledger once per purchase token; repeating the call is safe and grants nothing more. The app
    calls consumeAsync only after this answers `consume: true`."""
    kind = _play_kind(req.product_id)
    user_id = token_data["id"]
    row = db.query(models.GooglePlayPurchase).filter(
        models.GooglePlayPurchase.purchase_token == req.purchase_token,
    ).first()
    if row and (row.user_id != user_id or row.product_id != req.product_id):
        raise HTTPException(status_code=409, detail="This purchase is linked to another account.")
    if row and row.state == "credited":
        return _play_response(db, row, user_id, 0)
    try:
        if kind == "subscription":
            return _verify_subscription(db, req, user_id, row)
        return _verify_product(db, req, kind, user_id, row)
    except google_play.GooglePlayNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except google_play.InvalidPurchaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except google_play.GooglePlayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/api/v2/payments/google-play/entitlements", response_model=GooglePlayEntitlementsResponse)
def google_play_entitlements(
    token_data: dict = Depends(get_active_player),
    db: Session = Depends(get_db),
):
    """What the player's verified Google Play purchases unlock now."""
    user_id = token_data["id"]
    now = _now_naive_utc()
    rows = db.query(models.GooglePlayPurchase).filter(
        models.GooglePlayPurchase.user_id == user_id,
        models.GooglePlayPurchase.kind.in_(("subscription", "non_consumable")),
    ).all()
    passes = [r for r in rows if r.kind == "subscription"]
    # shortcut: no Real-time Developer Notifications yet, so a pass past its stored expiry is re-read
    # from Google here (renewed or lapsed). Add an RTDN Pub/Sub endpoint before refunds must revoke at once.
    for r in passes:
        if r.state != "expired" and (r.expires_at is None or r.expires_at <= now):
            try:
                _apply_subscription(r, google_play.get_subscription(r.purchase_token))
            except google_play.InvalidPurchaseError:
                r.state = "expired"
            except (google_play.GooglePlayError, google_play.GooglePlayNotConfiguredError) as exc:
                logger.warning("google play refresh failed for purchase %s: %s", r.id, exc)
    db.commit()
    active = max((r for r in passes if _pass_entitled(r, now)), key=lambda r: r.expires_at, default=None)
    return GooglePlayEntitlementsResponse(
        osiris_pass=active is not None,
        osiris_pass_product_id=active.product_id if active else None,
        osiris_pass_state=active.state if active else None,
        osiris_pass_expires_at=active.expires_at if active else None,
        founder_pack=any(r.kind == "non_consumable" and r.state == "owned" for r in rows),
    )
