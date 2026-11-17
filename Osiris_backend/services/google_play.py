"""Google Play Developer API client for server-side purchase verification.

The app sends a purchase token; only this module asks Google whether it is real. Configure with
`GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` (the key file's JSON, or `_FILE` with its path) for a service
account invited in Play Console (Users and permissions) with "View financial data" and
"Manage orders and subscriptions". `GOOGLE_PLAY_PACKAGE_NAME` defaults to the app's id.
The authorised session is cached for the life of the process: restart the API after rotating the key.
"""
import hashlib
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

import models
import settings
from core.clock import _to_naive_utc
from services import ledger

logger = logging.getLogger(__name__)

_API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
_TIMEOUT_S = 10

_session = None


ERASED_PREFIX = "erased:"


def erased_key(token: str) -> str:
    """What an erased account's store token (Play purchase token, App Store transaction id) is replaced by:
    one-way, still unique, so the same purchase re-sent later is still refused (409) and never credited twice."""
    return ERASED_PREFIX + hashlib.sha256(token.encode("utf-8")).hexdigest()


def erase_store_purchases(db: Session, user_id: int) -> None:
    """Account erasure: the purchase rows stay as anonymous accounting records, without the store's
    token or order number. Does not commit. Erasure does not cancel a subscription at the store."""
    for table, column in ((models.GooglePlayPurchase, "purchase_token"), (models.AppStorePurchase, "transaction_id")):
        for row in db.query(table).filter(table.user_id == user_id).all():
            token = getattr(row, column)
            if not token.startswith(ERASED_PREFIX):
                setattr(row, column, erased_key(token))
            row.order_id = None


class GooglePlayNotConfiguredError(RuntimeError):
    """No service-account key: the verify endpoint answers 503."""


class InvalidPurchaseError(ValueError):
    """Google does not know this token for this product (forged, wrong product or wrong app)."""


class GooglePlayError(RuntimeError):
    """Google answered with an unexpected error or could not be reached."""


def _authorized_session():
    global _session
    if _session is None:
        raw = settings.secret("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON")
        if not raw:
            raise GooglePlayNotConfiguredError("Google Play billing is not configured on this server.")
        # Imported lazily so the API boots (and the tests run) without touching Google.
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=[_SCOPE])
        _session = AuthorizedSession(creds)
    return _session


def _call(method: str, path: str) -> dict:
    try:
        url = f"{_API}/{settings.android_package_name()}/{path}"
        resp = _authorized_session().request(method, url, timeout=_TIMEOUT_S)
    except GooglePlayNotConfiguredError:
        raise
    except Exception as exc:  # network / auth failures: the caller answers 502 and the app retries
        # Only the type: the message can carry the request URL, which holds the purchase token.
        raise GooglePlayError(f"Google Play could not be reached ({type(exc).__name__}).") from exc
    if resp.status_code in (400, 404, 410):
        raise InvalidPurchaseError("Google Play does not recognise this purchase.")
    if resp.status_code >= 300:
        raise GooglePlayError(f"Google Play answered {resp.status_code}.")
    return resp.json() if resp.content else {}


def get_product_purchase(product_id: str, token: str) -> dict:
    """purchases.products.get: purchaseState (0 purchased, 1 canceled, 2 pending), acknowledgementState."""
    return _call("GET", f"purchases/products/{product_id}/tokens/{token}")


def acknowledge_product(product_id: str, token: str) -> None:
    _call("POST", f"purchases/products/{product_id}/tokens/{token}:acknowledge")


def get_subscription(token: str) -> dict:
    """purchases.subscriptionsv2.get: subscriptionState, lineItems[].productId/.expiryTime."""
    return _call("GET", f"purchases/subscriptionsv2/tokens/{token}")


def acknowledge_subscription(product_id: str, token: str) -> None:
    _call("POST", f"purchases/subscriptions/{product_id}/tokens/{token}:acknowledge")


def list_voided_purchases() -> list[dict]:
    """purchases.voidedpurchases.list: refunds, chargebacks and revocations of the last 30 days
    (Google's default window), one-time products and subscriptions (`type=1`)."""
    voided: list[dict] = []
    page = ""
    while True:
        body = _call("GET", f"purchases/voidedpurchases?type=1{page}")
        voided.extend(body.get("voidedPurchases") or [])
        next_token = (body.get("tokenPagination") or {}).get("nextPageToken")
        if not next_token:
            return voided
        page = f"&token={next_token}"


def obfuscated_account_id(user_id: int) -> str:
    """What the app passes to Play Billing as obfuscatedAccountId: SHA-256 hex of "osiris:<user id>"."""
    return hashlib.sha256(f"osiris:{user_id}".encode()).hexdigest()


SUB_STATES = {
    "SUBSCRIPTION_STATE_PENDING": "pending",
    "SUBSCRIPTION_STATE_ACTIVE": "active",
    "SUBSCRIPTION_STATE_PAUSED": "paused",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "in_grace_period",
    "SUBSCRIPTION_STATE_ON_HOLD": "on_hold",
    "SUBSCRIPTION_STATE_CANCELED": "canceled",  # auto-renew off; the paid period still counts
    "SUBSCRIPTION_STATE_EXPIRED": "expired",
    "SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED": "canceled",
}


def apply_subscription(row: "models.GooglePlayPurchase", sub: dict) -> None:
    """Copy Google's subscriptionsv2 state onto `row`; a token that is not for this product is invalid."""
    items = [i for i in sub.get("lineItems") or [] if i.get("productId") == row.product_id]
    if not items:
        raise InvalidPurchaseError("This subscription token is for a different product.")
    expiries = [t for t in (parse_time(i.get("expiryTime")) for i in items) if t]
    row.state = SUB_STATES.get(sub.get("subscriptionState"), "pending")
    row.expires_at = max(expiries, default=None)
    row.order_id = sub.get("latestOrderId") or row.order_id


def refresh_subscription(row: "models.GooglePlayPurchase") -> None:
    """Re-read a stored subscription from Google (renewed, canceled, revoked, expired)."""
    try:
        apply_subscription(row, get_subscription(row.purchase_token))
    except InvalidPurchaseError:
        row.state = "expired"


def void_purchase(db: Session, row: "models.GooglePlayPurchase") -> int:
    """Apply a refund, chargeback or revocation Google reported for a stored purchase. Does not
    commit. Safe to repeat: a one-time purchase is voided once (the state flip is one guarded
    UPDATE, so a notification and the reconciliation job cannot both claw back).

    Subscriptions are re-read from Google, which is the truth for them (revoked -> expired; a refund
    that leaves access keeps it). A one-time purchase becomes `refunded`, and a crystal pack's grant
    is taken back through the ledger as `crystal_refund`. Policy when the player already spent the
    crystals: the clawback is capped at the current balance, so a wallet never goes negative; the
    shortfall is written to the ledger note and logged. Returns the crystals taken back."""
    if row.kind == "subscription":
        refresh_subscription(row)
        return 0
    return refund_one_time(db, row, "Google Play")


def refund_one_time(db: Session, row, store: str) -> int:
    """The one-time-purchase half of a refund, shared with services/app_store.py (`row` is a
    GooglePlayPurchase or an AppStorePurchase). Does not commit."""
    purchases = type(row)
    flipped = db.query(purchases).filter(purchases.id == row.id, purchases.state != "refunded").update(
        {purchases.state: "refunded"}, synchronize_session=False,
    )
    db.refresh(row)
    if not flipped or row.crystal_ledger_id is None:
        return 0
    grant = db.get(models.CrystalLedger, row.crystal_ledger_id)
    user = db.get(models.User, row.user_id)
    if grant is None or user is None:
        return 0
    clawback = min(grant.delta, user.mana_crystals or 0)
    shortfall = grant.delta - clawback
    if shortfall:
        logger.warning("store refund shortfall", extra={"ctx": {
            "store": store, "purchase_id": row.id, "user_id": user.id, "granted": grant.delta,
            "clawed_back": clawback}})
    if clawback > 0:
        note = f"{store} refund {row.order_id}" + (f" (short by {shortfall}: already spent)" if shortfall else "")
        ledger.apply_crystal_delta(db, user, -clawback, "crystal_refund", note=note)
    return clawback


def parse_time(value: str | None) -> datetime | None:
    """Google's RFC 3339 timestamps ('2026-11-30T12:00:00.123Z') as naive UTC."""
    if not value:
        return None
    return _to_naive_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
