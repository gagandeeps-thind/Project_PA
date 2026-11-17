"""App Store (StoreKit 2) purchase verification.

The iOS app sends the signed transaction (a JWS) StoreKit gave it; App Store Server Notifications
arrive in the same format. Nothing here calls Apple: a JWS is trusted only when its certificate
chain (`x5c` header) leads to the Apple Root CA G3 below and its signature checks out.

Closed until `APPLE_APP_STORE_ENVIRONMENT` is set (see docs/architecture/app-store-billing.md).
"""
import base64
import uuid
from datetime import datetime, timezone

import jwt
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy.orm import Session

import models
import settings
from core.clock import _now_naive_utc
from services import google_play

# Apple Root CA - G3, from https://www.apple.com/certificateauthority/ (valid to 2039-04-30).
# SHA-256 fingerprint 63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179.
APPLE_ROOT_CA_G3_PEM = b"""-----BEGIN CERTIFICATE-----
MIICQzCCAcmgAwIBAgIILcX8iNLFS5UwCgYIKoZIzj0EAwMwZzEbMBkGA1UEAwwS
QXBwbGUgUm9vdCBDQSAtIEczMSYwJAYDVQQLDB1BcHBsZSBDZXJ0aWZpY2F0aW9u
IEF1dGhvcml0eTETMBEGA1UECgwKQXBwbGUgSW5jLjELMAkGA1UEBhMCVVMwHhcN
MTQwNDMwMTgxOTA2WhcNMzkwNDMwMTgxOTA2WjBnMRswGQYDVQQDDBJBcHBsZSBS
b290IENBIC0gRzMxJjAkBgNVBAsMHUFwcGxlIENlcnRpZmljYXRpb24gQXV0aG9y
aXR5MRMwEQYDVQQKDApBcHBsZSBJbmMuMQswCQYDVQQGEwJVUzB2MBAGByqGSM49
AgEGBSuBBAAiA2IABJjpLz1AcqTtkyJygRMc3RCV8cWjTnHcFBbZDuWmBSp3ZHtf
TjjTuxxEtX/1H7YyYl3J6YRbTzBPEVoA/VhYDKX1DyxNB0cTddqXl5dvMVztK517
IDvYuVTZXpmkOlEKMaNCMEAwHQYDVR0OBBYEFLuw3qFYM4iapIqZ3r6966/ayySr
MA8GA1UdEwEB/wQFMAMBAf8wDgYDVR0PAQH/BAQDAgEGMAoGCCqGSM49BAMDA2gA
MGUCMQCD6cHEFl4aXTQY2e3v9GwOAEZLuN+yRhHFD/3meoyhpmvOwgPUnPWTxnS4
at+qIxUCMG1mihDK1A3UT82NQz60imOlM27jbdoXt2QfyFMm+YhidDkLF1vLUagM
6BgD56KyKA==
-----END CERTIFICATE-----
"""
# The only trusted root. Tests replace this with a throwaway root; there is no runtime setting for it.
TRUSTED_ROOT_PEM = APPLE_ROOT_CA_G3_PEM

# Apple marks its certificates with these extensions: the WWDR intermediate, and the leaf that signs
# App Store receipts. Without the check any certificate under this root could sign a "purchase".
_OID_APPLE_INTERMEDIATE = x509.ObjectIdentifier("1.2.840.113635.100.6.2.1")
_OID_APPLE_RECEIPT_SIGNER = x509.ObjectIdentifier("1.2.840.113635.100.6.11.1")


class AppStoreNotConfiguredError(RuntimeError):
    """`APPLE_APP_STORE_ENVIRONMENT` is unset: the endpoints answer 503."""


class InvalidTransactionError(ValueError):
    """The JWS is not a transaction Apple signed for this app and environment."""


def account_token(user_id: int) -> str:
    """What the app passes to StoreKit as appAccountToken: UUIDv5(NAMESPACE_URL, "osiris:<user id>")."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"osiris:{user_id}"))


def _from_ms(value) -> datetime | None:
    """Apple's millisecond timestamps as naive UTC."""
    if not value:
        return None
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(tzinfo=None)


def _has_extension(cert: x509.Certificate, oid: x509.ObjectIdentifier) -> bool:
    return any(ext.oid == oid for ext in cert.extensions)


def _verify_jws(signed: str) -> dict:
    """The payload of a JWS whose x5c chain leads to the trusted root. No bundle or environment check."""
    try:
        chain = [
            x509.load_der_x509_certificate(base64.b64decode(c, validate=True))
            for c in jwt.get_unverified_header(signed)["x5c"]
        ]
        if len(chain) != 3:
            raise InvalidTransactionError("Expected a three-certificate chain.")
        leaf, intermediate = chain[0], chain[1]
        # The root sent in the header is ignored: the intermediate must be signed by OUR copy.
        intermediate.verify_directly_issued_by(x509.load_pem_x509_certificate(TRUSTED_ROOT_PEM))
        leaf.verify_directly_issued_by(intermediate)
        if not _has_extension(intermediate, _OID_APPLE_INTERMEDIATE):
            raise InvalidTransactionError("The intermediate is not an Apple WWDR certificate.")
        if not _has_extension(leaf, _OID_APPLE_RECEIPT_SIGNER):
            raise InvalidTransactionError("The leaf is not an App Store signing certificate.")
        public_key = leaf.public_key()
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise InvalidTransactionError("Unexpected signing key type.")
        payload = jwt.decode(signed, key=public_key, algorithms=["ES256"], options={"verify_aud": False})
        # Apple rotates the leaf certificate and a restored purchase can be an old JWS, so (like
        # Apple's own library without online checks) the chain must have been valid at signing time.
        # shortcut: no OCSP revocation check of Apple's certificates; add it if Apple ever revokes one.
        signed_ms = payload.get("signedDate")
        signed_at = datetime.fromtimestamp(int(signed_ms) / 1000, tz=timezone.utc) if signed_ms else datetime.now(timezone.utc)
        for cert in (leaf, intermediate):
            if not cert.not_valid_before_utc <= signed_at <= cert.not_valid_after_utc:
                raise InvalidTransactionError("The signing certificate was not valid at signing time.")
        return payload
    except InvalidTransactionError:
        raise
    except Exception as exc:  # malformed JWS, bad certificate, bad signature: all mean "not Apple's"
        raise InvalidTransactionError(f"Not a valid App Store JWS ({type(exc).__name__}).") from exc


def _require_configured() -> frozenset[str]:
    allowed = settings.apple_app_store_environments()
    if not allowed:
        raise AppStoreNotConfiguredError("App Store billing is not configured on this server.")
    return allowed


def _check_app(bundle_id: str | None, environment: str | None) -> None:
    if bundle_id != settings.apple_bundle_id():
        raise InvalidTransactionError("This transaction is for another app.")
    if environment not in _require_configured():
        raise InvalidTransactionError(f"{environment} transactions are not accepted here.")


def verify_transaction(signed_transaction: str) -> dict:
    """The JWSTransactionDecodedPayload of a StoreKit 2 transaction Apple signed for this app."""
    _require_configured()  # closed before anything is parsed
    tx = _verify_jws(signed_transaction)
    _check_app(tx.get("bundleId"), tx.get("environment"))
    if not tx.get("transactionId") or not tx.get("originalTransactionId") or not tx.get("productId"):
        raise InvalidTransactionError("The transaction is missing its ids.")
    return tx


def verify_notification(signed_payload: str) -> tuple[dict, dict | None]:
    """An App Store Server Notification v2: (responseBodyV2DecodedPayload, its transaction or None)."""
    _require_configured()
    note = _verify_jws(signed_payload)
    data = note.get("data") or {}
    if not data.get("signedTransactionInfo"):  # TEST and summary notifications carry no transaction
        return note, None
    _check_app(data.get("bundleId"), data.get("environment"))
    return note, verify_transaction(data["signedTransactionInfo"])


def purchase_key(tx: dict, kind: str) -> str:
    """The id a purchase is stored under: a subscription keeps one row across renewals."""
    return str(tx["originalTransactionId"] if kind == "subscription" else tx["transactionId"])


def apply_subscription(row: "models.AppStorePurchase", tx: dict, revoked: bool = False) -> None:
    """Copy a subscription transaction onto `row`. Safe to repeat and to receive out of order: an
    older period never shortens a newer one, and the transaction that was refunded stays refunded."""
    transaction_id = str(tx["transactionId"])
    if row.state == "refunded" and row.order_id == transaction_id:
        return
    expires = _from_ms(tx.get("expiresDate"))
    if revoked or tx.get("revocationDate"):
        # Only a refund of the period the pass currently rests on ends it.
        if row.expires_at is None or (expires is not None and expires >= row.expires_at):
            row.state, row.order_id, row.expires_at = "refunded", transaction_id, expires
        return
    if expires is None or (row.state != "refunded" and row.expires_at is not None and expires < row.expires_at):
        return
    row.expires_at = expires
    row.order_id = transaction_id
    row.product_id = tx["productId"]  # monthly <-> annual switch inside the subscription group
    row.state = "active" if expires > _now_naive_utc() else "expired"


def void_purchase(db: Session, row: "models.AppStorePurchase", tx: dict) -> int:
    """Apply a refund or revocation Apple reported (a REFUND / REVOKE notification, or a transaction
    with a revocationDate). Does not commit. Same policy as Google Play: a one-time purchase is
    voided once and a crystal pack is clawed back, capped at the balance. Returns the crystals taken back."""
    if row.kind == "subscription":
        apply_subscription(row, tx, revoked=True)
        return 0
    return google_play.refund_one_time(db, row, "App Store")
