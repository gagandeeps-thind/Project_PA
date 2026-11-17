"""Payments: the merchant pilot-fee webhook and Google Play / App Store purchases (crystals, founder pack,
pass).
Money path: every crystal movement goes through services.ledger.apply_crystal_delta."""
import base64
import hmac
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import settings
from core.clock import _now_naive_utc, _to_naive_utc
from core.rate_limit import _rl_purchase, _rl_webhook
from core.security import get_active_player, verify_webhook_signature
from database import get_db
from schemas import (
    AppStoreVerifyRequest,
    GooglePlayEntitlementsResponse,
    GooglePlayVerifyRequest,
    GooglePlayVerifyResponse,
    PaymentWebhookRequest,
    PaymentWebhookResponse,
)
from services import app_store, google_play, ledger


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

    # Outside dev/test a provider_event_id is required — real providers always send an event id, and
    # without it we can't dedupe retries. It is also the replay guard: the HMAC covers only the body, so a
    # captured signed payload replayed later carries an event id already stored and changes nothing.
    if not req.provider_event_id and not settings.is_dev_env():
        raise HTTPException(
            status_code=400,
            detail="provider_event_id is required in production (needed for retry dedup).",
        )

    # Event-level idempotency: if we've already processed this provider_event_id, return
    # the merchant's current state without re-running side effects (no double revenue, no
    # double activate). Payment providers retry 5xx responses; this guard is what
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


# --- Google Play Billing (Android) ---
#
# The app buys through Play Billing and sends the purchase token here; only the server asks Google
# whether it is real and only the server grants. Product ids are the ones created in Play Console.
# Crystal grants reuse CRYSTAL_PACKS; Play Console sets the (localized) prices.
PLAY_CRYSTAL_PRODUCTS = {f"osiris_crystals_{pack_id}": pack_id for pack_id in CRYSTAL_PACKS}
PLAY_FOUNDER_PACK = "osiris_founder_pack"
PLAY_PASS_PRODUCTS = frozenset({"osiris_pass_monthly", "osiris_pass_annual"})
_PASS_ENTITLED = frozenset({"active", "in_grace_period", "canceled"})


def _play_kind(product_id: str) -> str:
    if product_id in PLAY_CRYSTAL_PRODUCTS:
        return "consumable"
    if product_id == PLAY_FOUNDER_PACK:
        return "non_consumable"
    if product_id in PLAY_PASS_PRODUCTS:
        return "subscription"
    raise HTTPException(status_code=404, detail=f"Unknown product {product_id!r}.")


def _pass_entitled(row, now: datetime) -> bool:
    return row.state in _PASS_ENTITLED and row.expires_at is not None and row.expires_at > now


def _check_buyer(user_id: int, obfuscated_account_id: str | None, test_purchase: bool) -> None:
    """Refuse a purchase that Play says another Osiris account started (the app sets
    obfuscatedAccountId; a purchase without one is accepted), and licence-test purchases when
    GOOGLE_PLAY_ALLOW_TEST_PURCHASES is off."""
    if obfuscated_account_id and obfuscated_account_id != google_play.obfuscated_account_id(user_id):
        raise HTTPException(status_code=409, detail="This purchase is linked to another account.")
    if test_purchase and not settings.google_play_allow_test_purchases():
        raise HTTPException(status_code=403, detail="Test purchases are not accepted.")


def _commit_play_row(db: Session, row, user_id: int) -> tuple:
    """Commit `row` (a GooglePlayPurchase or an AppStorePurchase). Returns (row, False) when a
    concurrent call stored this token first: the unique index rolled this call back, crystals
    included, so nothing is granted twice."""
    model = type(row)
    unique = model.purchase_token if model is models.GooglePlayPurchase else model.transaction_id
    token = getattr(row, unique.key)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        stored = db.query(model).filter(unique == token).first()
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
    except (
        google_play.GooglePlayError, google_play.InvalidPurchaseError, google_play.GooglePlayNotConfiguredError,
    ) as exc:  # the grant is already committed: never turn this into a client error
        logger.warning("google play acknowledge failed for %s: %s", product_id, exc)


def _play_response(db: Session, row, user_id: int, crystals: int) -> GooglePlayVerifyResponse:
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
    _check_buyer(user_id, purchase.get("obfuscatedExternalAccountId"), purchase.get("purchaseType") == 0)
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
        quantity = max(1, int(purchase.get("quantity") or 1))  # multi-quantity purchase: one token, N packs
        crystals = CRYSTAL_PACKS[pack_id]["crystals"] * quantity
        test = " (license test)" if purchase.get("purchaseType") == 0 else ""
        entry = ledger.apply_crystal_delta(
            db, user, crystals, "crystal_purchase",
            note=f"Google Play {row.order_id} ({pack_id} x{quantity}){test}",
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
    account_ids = sub.get("externalAccountIdentifiers") or {}
    _check_buyer(user_id, account_ids.get("obfuscatedExternalAccountId"), "testPurchase" in sub)
    row = row or models.GooglePlayPurchase(
        user_id=user_id, purchase_token=req.purchase_token, product_id=req.product_id,
        kind="subscription", state="pending",
    )
    google_play.apply_subscription(row, sub)
    row, _ = _commit_play_row(db, row, user_id)
    ack_needed = sub.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_PENDING" and row.state in _PASS_ENTITLED
    _acknowledge("subscription", req.product_id, req.purchase_token, ack_needed)
    return _play_response(db, row, user_id, 0)


@router.post("/api/v2/payments/google-play/verify", response_model=GooglePlayVerifyResponse)
def verify_google_play_purchase(
    req: GooglePlayVerifyRequest,
    token_data: dict = Depends(get_active_player),
    db: Session = Depends(get_db),
    _rl: None = Depends(_rl_purchase),
):
    """Verify a Play Billing purchase with Google and grant it. Crystal packs are credited through
    the ledger once per purchase token; repeating the call is safe and grants nothing more. The app
    calls consumeAsync only after this answers `consume: true`."""
    kind = _play_kind(req.product_id)
    user_id = token_data["id"]
    row = db.query(models.GooglePlayPurchase).filter(
        # The erased form too: a purchase of an erased account stays claimed and is never credited again.
        models.GooglePlayPurchase.purchase_token.in_((req.purchase_token, google_play.erased_key(req.purchase_token))),
    ).first()
    if row and (row.user_id != user_id or row.product_id != req.product_id):
        raise HTTPException(status_code=409, detail="This purchase is linked to another account.")
    # A refunded one-time purchase stays refunded whatever Google answers later: never grant it again.
    if row and row.state in ("credited", "refunded"):
        return _play_response(db, row, user_id, 0)
    try:
        if kind == "subscription":
            return _verify_subscription(db, req, user_id, row)
        return _verify_product(db, req, kind, user_id, row)
    except google_play.GooglePlayNotConfiguredError:
        # Fail closed: without credentials nothing can be verified, so nothing is granted.
        logger.error("google play verify refused: GOOGLE_PLAY_SERVICE_ACCOUNT_JSON is not set")
        raise HTTPException(status_code=503, detail="Purchases are temporarily unavailable.")
    except google_play.InvalidPurchaseError as exc:
        logger.info("google play rejected a purchase of %s for user %s: %s", req.product_id, user_id, exc)
        raise HTTPException(status_code=400, detail="Google Play does not recognise this purchase.")
    except google_play.GooglePlayError as exc:
        logger.warning("google play verify failed for %s: %s", req.product_id, exc)
        raise HTTPException(status_code=502, detail="Google Play could not be reached. Try again later.")


@router.post("/api/v2/payments/google-play/rtdn")
def google_play_rtdn(
    payload: dict,
    token: str | None = None,
    x_osiris_rtdn_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    _rl: None = Depends(_rl_webhook),
):
    """Real-time Developer Notifications, delivered by a Pub/Sub push subscription. Not JWT-gated:
    the caller proves itself with the shared `GOOGLE_PLAY_RTDN_TOKEN` (`?token=` in the push URL, or
    the `X-Osiris-Rtdn-Token` header) and the endpoint is closed (503) until that is set.

    The message is only a hint: the purchase is re-read from Google and the stored row follows it
    (renewed, canceled, expired, revoked, refunded), so a repeated or forged-content delivery
    changes nothing. A 5xx answer makes Pub/Sub deliver again later."""
    expected = settings.secret("GOOGLE_PLAY_RTDN_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Notifications are not configured.")
    if not hmac.compare_digest((x_osiris_rtdn_token or token or "").encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        note = json.loads(base64.b64decode(payload["message"]["data"]))
        voided = note.get("voidedPurchaseNotification")
        detail = voided or note.get("subscriptionNotification") or note.get("oneTimeProductNotification") or {}
        purchase_token = detail.get("purchaseToken")
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed notification.")
    row = None
    if purchase_token and note.get("packageName") == settings.android_package_name():
        row = db.query(models.GooglePlayPurchase).filter(
            models.GooglePlayPurchase.purchase_token == purchase_token,
        ).first()
    if row is None:
        # A test notification, another app, or a purchase the app has not sent to /verify yet.
        return {"status": "ignored"}
    try:
        if row.kind == "subscription":
            google_play.refresh_subscription(row)
        elif voided and voided.get("refundType") == 2:
            # shortcut: a partial (per-quantity) refund is not clawed back automatically; handle it by
            # hand from this log line. Automate if multi-quantity packs see real refund volume.
            logger.warning("google play partial refund needs manual review", extra={"ctx": {"purchase_id": row.id}})
        elif voided or google_play.get_product_purchase(row.product_id, row.purchase_token).get("purchaseState") == 1:
            google_play.void_purchase(db, row)
    except google_play.InvalidPurchaseError:
        return {"status": "ignored"}
    except google_play.GooglePlayNotConfiguredError:
        raise HTTPException(status_code=503, detail="Purchases are temporarily unavailable.")
    except google_play.GooglePlayError as exc:
        logger.warning("google play notification refresh failed for purchase %s: %s", row.id, exc)
        raise HTTPException(status_code=502, detail="Google Play could not be reached. Try again later.")
    db.commit()
    return {"status": "ok", "state": row.state}


# --- App Store (iOS, StoreKit 2) ---
#
# The app sends the signed transaction StoreKit gave it; services/app_store.py checks Apple's
# signature, so nothing is asked of Apple. Product ids, kinds and crystal grants are the Play ones above.
@router.post("/api/v2/payments/app-store/verify", response_model=GooglePlayVerifyResponse)
def verify_app_store_purchase(
    req: AppStoreVerifyRequest,
    token_data: dict = Depends(get_active_player),
    db: Session = Depends(get_db),
    _rl: None = Depends(_rl_purchase),
):
    """Verify a StoreKit 2 transaction and grant it. Crystal packs are credited through the ledger
    once per transaction id; repeating the call is safe and grants nothing more. The app finishes
    the transaction once this answers 200 (see docs/architecture/app-store-billing.md)."""
    user_id = token_data["id"]
    try:
        tx = app_store.verify_transaction(req.signed_transaction)
    except app_store.AppStoreNotConfiguredError:
        # Fail closed: until the environment is chosen nothing is verified, so nothing is granted.
        logger.error("app store verify refused: APPLE_APP_STORE_ENVIRONMENT is not set")
        raise HTTPException(status_code=503, detail="Purchases are temporarily unavailable.")
    except app_store.InvalidTransactionError as exc:
        logger.info("app store transaction rejected for user %s: %s", user_id, exc)
        raise HTTPException(status_code=400, detail="The App Store does not recognise this purchase.")
    product_id = tx["productId"]
    kind = _play_kind(product_id)
    # The app sets appAccountToken; a transaction without one is accepted.
    account_token = tx.get("appAccountToken")
    if account_token and str(account_token).lower() != app_store.account_token(user_id):
        raise HTTPException(status_code=409, detail="This purchase is linked to another account.")
    key = app_store.purchase_key(tx, kind)
    row = db.query(models.AppStorePurchase).filter(
        models.AppStorePurchase.transaction_id.in_((key, google_play.erased_key(key))),
    ).first()
    if row and row.user_id != user_id:
        raise HTTPException(status_code=409, detail="This purchase is linked to another account.")
    if tx.get("revocationDate"):  # refunded or revoked by Apple: grants nothing, and takes back a grant
        if row is None:
            return GooglePlayVerifyResponse(product_id=product_id, kind=kind, state="refunded")
        app_store.void_purchase(db, row, tx)
        db.commit()
        return _play_response(db, row, user_id, 0)
    if row and kind != "subscription":  # credited, owned or refunded: never granted again
        return _play_response(db, row, user_id, 0)
    row = row or models.AppStorePurchase(
        user_id=user_id, transaction_id=key, product_id=product_id, kind=kind,
        state="expired" if kind == "subscription" else "owned",
        order_id=str(tx["transactionId"]), environment=tx["environment"],
    )
    crystals = 0
    if kind == "subscription":
        app_store.apply_subscription(row, tx)
    elif kind == "consumable":
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        pack_id = PLAY_CRYSTAL_PRODUCTS[product_id]
        quantity = max(1, int(tx.get("quantity") or 1))
        crystals = CRYSTAL_PACKS[pack_id]["crystals"] * quantity
        sandbox = "" if tx["environment"] == "Production" else f" ({tx['environment'].lower()})"
        entry = ledger.apply_crystal_delta(
            db, user, crystals, "crystal_purchase",
            note=f"App Store {row.order_id} ({pack_id} x{quantity}){sandbox}",
        )
        db.flush()
        row.crystal_ledger_id = entry.id
        row.state = "credited"
    row, fresh = _commit_play_row(db, row, user_id)
    return _play_response(db, row, user_id, crystals if fresh else 0)


@router.post("/api/v2/payments/app-store/notifications")
def app_store_notifications(
    payload: dict,
    db: Session = Depends(get_db),
    _rl: None = Depends(_rl_webhook),
):
    """App Store Server Notifications v2. Not JWT-gated: the body's `signedPayload` must carry
    Apple's signature for this app, and the endpoint is closed (503) until App Store billing is
    configured. Every type is applied from the signed transaction inside, so a repeated or
    out-of-order delivery changes nothing. A 5xx answer makes Apple deliver again later."""
    try:
        note, tx = app_store.verify_notification(str(payload.get("signedPayload") or ""))
    except app_store.AppStoreNotConfiguredError:
        raise HTTPException(status_code=503, detail="Notifications are not configured.")
    except app_store.InvalidTransactionError as exc:
        logger.warning("app store notification rejected: %s", exc)
        raise HTTPException(status_code=400, detail="Malformed notification.")
    row = None
    if tx is not None:
        row = db.query(models.AppStorePurchase).filter(models.AppStorePurchase.transaction_id.in_(
            (str(tx["transactionId"]), str(tx["originalTransactionId"])),
        )).first()
    if row is None or tx is None:
        # A TEST notification, or a purchase the app has not sent to /verify yet.
        return {"status": "ignored"}
    event = note.get("notificationType")
    if event in ("REFUND", "REVOKE") or tx.get("revocationDate"):
        app_store.void_purchase(db, row, tx)
    elif event == "REFUND_REVERSED":
        # shortcut: a reversed refund is not re-granted automatically; handle it by hand from this
        # log line. Automate if it ever happens often.
        logger.warning("app store refund reversal needs manual review", extra={"ctx": {"purchase_id": row.id}})
    elif row.kind == "subscription":  # DID_RENEW, SUBSCRIBED, ...: the transaction's expiry date decides
        app_store.apply_subscription(row, tx)
        if event in ("EXPIRED", "GRACE_PERIOD_EXPIRED") and row.state == "active" and row.order_id == str(tx["transactionId"]):
            row.state = "expired"
    db.commit()
    return {"status": "ok", "state": row.state}


@router.get("/api/v2/payments/entitlements", response_model=GooglePlayEntitlementsResponse)
@router.get("/api/v2/payments/google-play/entitlements", response_model=GooglePlayEntitlementsResponse)
def google_play_entitlements(
    token_data: dict = Depends(get_active_player),
    db: Session = Depends(get_db),
):
    """What the player's verified store purchases unlock now. `/api/v2/payments/entitlements` is the
    store-neutral path; the `google-play` one is kept for older app builds."""
    user_id = token_data["id"]
    now = _now_naive_utc()
    rows = db.query(models.GooglePlayPurchase).filter(
        models.GooglePlayPurchase.user_id == user_id,
        models.GooglePlayPurchase.kind.in_(("subscription", "non_consumable")),
    ).all()
    # Safety net for a missed notification: a pass past its stored expiry is re-read from Google here.
    for r in rows:
        if r.kind == "subscription" and r.state != "expired" and (r.expires_at is None or r.expires_at <= now):
            try:
                google_play.refresh_subscription(r)
            except (google_play.GooglePlayError, google_play.GooglePlayNotConfiguredError) as exc:
                logger.warning("google play refresh failed for purchase %s: %s", r.id, exc)
    db.commit()
    # App Store rows need no refresh: a lapsed pass fails the expiry check, a renewal arrives signed.
    rows += db.query(models.AppStorePurchase).filter(
        models.AppStorePurchase.user_id == user_id,
        models.AppStorePurchase.kind.in_(("subscription", "non_consumable")),
    ).all()
    passes = [r for r in rows if r.kind == "subscription"]
    active = max((r for r in passes if _pass_entitled(r, now)), key=lambda r: r.expires_at, default=None)
    return GooglePlayEntitlementsResponse(
        osiris_pass=active is not None,
        osiris_pass_product_id=active.product_id if active else None,
        osiris_pass_state=active.state if active else None,
        osiris_pass_expires_at=active.expires_at if active else None,
        founder_pack=any(r.kind == "non_consumable" and r.state == "owned" for r in rows),
    )
