"""Google Play Developer API client for server-side purchase verification.

The app sends a purchase token; only this module asks Google whether it is real. Configure with
`GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` (the key file's JSON, or `_FILE` with its path) for a service
account invited in Play Console (Users and permissions) with "View financial data" and
"Manage orders and subscriptions". `GOOGLE_PLAY_PACKAGE_NAME` defaults to the app's id.
"""
import json
import os
from datetime import datetime

import settings
from core.clock import _to_naive_utc

PACKAGE_NAME = os.environ.get("GOOGLE_PLAY_PACKAGE_NAME", "com.osiris.player")
_API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
_TIMEOUT_S = 10

_session = None


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
        resp = _authorized_session().request(method, f"{_API}/{PACKAGE_NAME}/{path}", timeout=_TIMEOUT_S)
    except GooglePlayNotConfiguredError:
        raise
    except Exception as exc:  # network / auth failures: the caller answers 502 and the app retries
        raise GooglePlayError(f"Google Play could not be reached: {exc}") from exc
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


def parse_time(value: str | None) -> datetime | None:
    """Google's RFC 3339 timestamps ('2026-11-30T12:00:00.123Z') as naive UTC."""
    if not value:
        return None
    return _to_naive_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
