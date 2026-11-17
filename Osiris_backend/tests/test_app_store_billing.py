"""App Store (StoreKit 2) verification tests (money path).

No pytest dependency — run directly:

    cd Osiris_backend
    OSIRIS_ENV=test python tests/test_app_store_billing.py

Apple is never involved: the suite builds a throwaway root / intermediate / leaf chain, makes it the
trusted root (services.app_store.TRUSTED_ROOT_PEM) and signs its own transactions and notifications.

Coverage:
  - The vendored root is Apple Root CA G3; appAccountToken follows the client contract.
  - Closed (503, nothing granted) until APPLE_APP_STORE_ENVIRONMENT is set.
  - A crystal pack is credited through the ledger exactly once per transaction id; quantity counts.
  - Rejected: another app's bundle id, an environment that is not enabled, a chain from another
    root, a leaf without Apple's receipt-signing extension, a tampered payload, an unknown product.
  - appAccountToken must match the caller when present; a transaction belongs to one account.
  - Founder pack and pass feed GET /api/v2/payments/entitlements; DID_RENEW extends, EXPIRED ends,
    an old transaction never shortens a newer period, a revoked one stays revoked.
  - REFUND notification: the pack is clawed back once however often Apple delivers it, capped at
    the balance, and never granted again; a transaction with a revocationDate grants nothing.
  - Notifications endpoint: closed without configuration, 400 on a forged payload, TEST ignored.
"""
import base64
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND)

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "app-store-test-secret-dddddddddddddddddddddd")
os.environ.pop("APPLE_APP_STORE_ENVIRONMENT", None)
os.environ.pop("APPLE_BUNDLE_ID", None)

from datetime import datetime, timedelta, timezone  # noqa: E402

import jwt  # noqa: E402
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import models  # noqa: E402
from core import security  # noqa: E402
from database import Base, get_db  # noqa: E402
from main import app  # noqa: E402
from services import app_store, ledger  # noqa: E402

_FAILURES = []


def _check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _FAILURES.append(name)


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
Base.metadata.create_all(bind=engine)

# --- A throwaway "Apple" ---------------------------------------------------------------------
_MARK = b"\x05\x00"  # ASN.1 NULL: Apple's marker extensions carry no meaningful value


def _cert(name, key, issuer_name, issuer_key, marker_oid=None, ca=True):
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if marker_oid:
        builder = builder.add_extension(
            x509.UnrecognizedExtension(x509.ObjectIdentifier(marker_oid), _MARK), critical=False)
    return builder.sign(issuer_key, hashes.SHA256())


def _chain(leaf_marker="1.2.840.113635.100.6.11.1"):
    """(leaf private key, x5c header list, root PEM) for a fresh three-certificate chain."""
    root_key, mid_key, leaf_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
    root = _cert("Test Root", root_key, "Test Root", root_key)
    mid = _cert("Test WWDR", mid_key, "Test Root", root_key, "1.2.840.113635.100.6.2.1")
    leaf = _cert("Test Receipt Signer", leaf_key, "Test WWDR", mid_key, leaf_marker, ca=False)
    x5c = [base64.b64encode(c.public_bytes(serialization.Encoding.DER)).decode() for c in (leaf, mid, root)]
    return leaf_key, x5c, root.public_bytes(serialization.Encoding.PEM)


LEAF_KEY, X5C, ROOT_PEM = _chain()
REAL_ROOT_PEM = app_store.TRUSTED_ROOT_PEM
app_store.TRUSTED_ROOT_PEM = ROOT_PEM


def _ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sign(payload, key=None, x5c=None):
    return jwt.encode(payload, key or LEAF_KEY, algorithm="ES256", headers={"x5c": x5c or X5C})


def _payload(transaction_id, product_id, **extra):
    return {
        "transactionId": transaction_id, "originalTransactionId": transaction_id, "bundleId": "osiris.fit",
        "productId": product_id, "environment": "Production", "quantity": 1, "signedDate": _ms(_utcnow()),
        **extra,
    }


def _tx(transaction_id, product_id, **extra):
    """A signed JWSTransactionDecodedPayload."""
    return _sign(_payload(transaction_id, product_id, **extra))


def _note(notification_type, signed_transaction, **extra):
    """A signed responseBodyV2DecodedPayload."""
    return _sign({
        "notificationType": notification_type, "notificationUUID": str(uuid.uuid4()), "signedDate": _ms(_utcnow()),
        "data": {"bundleId": "osiris.fit", "environment": "Production", "signedTransactionInfo": signed_transaction},
        **extra,
    })


def _onboard(email):
    r = client.post("/api/v1/onboard", json={
        "email": email, "password": "PlayerTest1!",
        "weight_kg": 75, "height_m": 1.8, "preferred_path": "Strength",
        "device_timestamp": "2026-10-31T12:00:00Z",
    })
    assert r.status_code == 200, f"onboard failed: {r.status_code} {r.text}"
    db = TestingSessionLocal()
    try:
        return db.query(models.User).filter(models.User.email == email).first().id
    finally:
        db.close()


def _auth(uid):
    return {"Authorization": f"Bearer {security.create_access_token({'sub': str(uid), 'role': 'player'})}"}


def _verify(uid, signed_transaction):
    return client.post("/api/v2/payments/app-store/verify", headers=_auth(uid),
                       json={"signed_transaction": signed_transaction})


def _notify(signed_payload):
    return client.post("/api/v2/payments/app-store/notifications", json={"signedPayload": signed_payload})


def _entitlements(uid):
    return client.get("/api/v2/payments/entitlements", headers=_auth(uid)).json()


def _balance_and_ledger(uid):
    db = TestingSessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == uid).first()
        total = db.query(func.coalesce(func.sum(models.CrystalLedger.delta), 0)).filter(
            models.CrystalLedger.user_id == uid).scalar()
        return user.mana_crystals or 0, total
    finally:
        db.close()


def _purchase_count():
    db = TestingSessionLocal()
    try:
        return db.query(models.AppStorePurchase).count()
    finally:
        db.close()


def test_contract_constants():
    root = x509.load_pem_x509_certificate(REAL_ROOT_PEM)
    _check("vendored root is Apple Root CA - G3",
           root.fingerprint(hashes.SHA256()).hex()
           == "63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179")
    _check("appAccountToken is UUIDv5(NAMESPACE_URL, 'osiris:<id>')",
           app_store.account_token(42) == "3992d9c9-b83f-5732-b590-2b6edfe75473")


def test_closed_until_configured():
    uid = _onboard("as_closed@test.com")
    before, _ = _balance_and_ledger(uid)
    os.environ.pop("APPLE_APP_STORE_ENVIRONMENT", None)
    r = _verify(uid, _tx("1000", "osiris_crystals_starter"))
    _check("verify without APPLE_APP_STORE_ENVIRONMENT -> 503", r.status_code == 503)
    _check("notifications without it -> 503", _notify(_note("TEST", "")).status_code == 503)
    balance, _ = _balance_and_ledger(uid)
    _check("nothing granted or stored while closed", balance == before and _purchase_count() == 0)
    os.environ["APPLE_APP_STORE_ENVIRONMENT"] = "Production"


def test_crystal_pack_credited_once():
    uid = _onboard("as_pack@test.com")
    before, _ = _balance_and_ledger(uid)
    signed = _tx("2000", "osiris_crystals_starter", appAccountToken=app_store.account_token(uid).upper())
    r1 = _verify(uid, signed)
    body = r1.json()
    _check("pack verify -> 200 credited", r1.status_code == 200 and body["state"] == "credited")
    _check("pack credits the server's 500 crystals", body["crystals_credited"] == 500)
    _check("app is told to finish (consume)", body["consume"] is True and body["entitled"] is True)
    r2 = _verify(uid, signed)
    _check("replay grants nothing", r2.status_code == 200 and r2.json()["crystals_credited"] == 0)
    r3 = _verify(uid, _tx("2001", "osiris_crystals_adventurer", quantity=2))
    _check("quantity 2 credits two packs", r3.json()["crystals_credited"] == 2400)
    balance, ledger_sum = _balance_and_ledger(uid)
    _check("balance rose by exactly 2900", balance == before + 2900)
    _check("ledger sums to the balance", balance == ledger_sum)


def test_rejected_transactions():
    uid = _onboard("as_reject@test.com")
    before, _ = _balance_and_ledger(uid)
    rows = _purchase_count()
    r = _verify(uid, _tx("3000", "osiris_crystals_starter", bundleId="com.evil.app"))
    _check("wrong bundle id -> 400", r.status_code == 400)
    r = _verify(uid, _tx("3001", "osiris_crystals_starter", environment="Sandbox"))
    _check("Sandbox while only Production is enabled -> 400", r.status_code == 400)

    other_key, other_x5c, _ = _chain()
    r = _verify(uid, _sign(_payload("3002", "osiris_crystals_champion"), key=other_key, x5c=other_x5c))
    _check("chain from an untrusted root -> 400", r.status_code == 400)
    _check("error text does not explain the check", "root" not in r.text.lower() and "cert" not in r.text.lower())

    # An attacker's own intermediate + leaf with our root's certificate appended: still not signed by the root.
    r = _verify(uid, _sign(_payload("3003", "osiris_crystals_champion"), key=other_key, x5c=other_x5c[:2] + X5C[2:]))
    _check("forged chain ending in the trusted root's certificate -> 400", r.status_code == 400)

    bare_key, bare_x5c, app_store.TRUSTED_ROOT_PEM = _chain(leaf_marker=None)
    r = _verify(uid, _sign(_payload("3004", "osiris_crystals_starter"), key=bare_key, x5c=bare_x5c))
    app_store.TRUSTED_ROOT_PEM = ROOT_PEM
    _check("leaf without Apple's receipt-signing extension -> 400", r.status_code == 400)

    head, _, sig = _tx("3005", "osiris_crystals_starter").split(".")
    forged = jwt.utils.base64url_encode(
        b'{"transactionId":"3005","originalTransactionId":"3005","bundleId":"osiris.fit",'
        b'"productId":"osiris_crystals_champion","environment":"Production"}').decode()
    _check("tampered payload -> 400", _verify(uid, f"{head}.{forged}.{sig}").status_code == 400)
    _check("not a JWS -> 400", _verify(uid, "abc.def.ghi").status_code == 400)
    _check("unknown product -> 404", _verify(uid, _tx("3006", "osiris_crystals_free")).status_code == 404)

    os.environ["APPLE_APP_STORE_ENVIRONMENT"] = "Production, Sandbox"
    r = _verify(uid, _tx("3007", "osiris_crystals_starter", environment="Sandbox"))
    os.environ["APPLE_APP_STORE_ENVIRONMENT"] = "Production"
    _check("Sandbox is granted once enabled", r.status_code == 200 and r.json()["crystals_credited"] == 500)
    balance, ledger_sum = _balance_and_ledger(uid)
    _check("rejections granted and stored nothing", balance == before + 500 and _purchase_count() == rows + 1)
    _check("ledger sums to the balance", balance == ledger_sum)


def test_account_binding():
    a, b = _onboard("as_owner@test.com"), _onboard("as_thief@test.com")
    before_b, _ = _balance_and_ledger(b)
    signed = _tx("4000", "osiris_crystals_champion", appAccountToken=app_store.account_token(a))
    r = _verify(b, signed)
    _check("appAccountToken of another account -> 409", r.status_code == 409)
    _check("the owner can still claim it", _verify(a, signed).json()["crystals_credited"] == 2600)
    unbound = _tx("4001", "osiris_crystals_starter")
    _verify(a, unbound)
    _check("a stored transaction cannot be claimed by a second account", _verify(b, unbound).status_code == 409)
    balance_b, _ = _balance_and_ledger(b)
    _check("second account got no crystals", balance_b == before_b)


def test_founder_pack_and_refund():
    uid = _onboard("as_founder@test.com")
    signed = _tx("5000", "osiris_founder_pack", type="Non-Consumable")
    r = _verify(uid, signed)
    _check("founder pack -> owned, entitled, no crystals",
           r.json()["state"] == "owned" and r.json()["entitled"] is True and r.json()["crystals_credited"] == 0)
    _check("entitlements show the founder pack", _entitlements(uid)["founder_pack"] is True)
    r = _notify(_note("REFUND", _tx("5000", "osiris_founder_pack", revocationDate=_ms(_utcnow()))))
    _check("REFUND notification -> refunded", r.status_code == 200 and r.json()["state"] == "refunded")
    _check("refunded founder pack stops unlocking", _entitlements(uid)["founder_pack"] is False)
    _check("re-sending the old transaction does not bring it back",
           _verify(uid, signed).json()["entitled"] is False and _entitlements(uid)["founder_pack"] is False)


def test_subscription_lifecycle():
    uid = _onboard("as_pass@test.com")
    now = _utcnow()
    first = _tx("6000", "osiris_pass_monthly", expiresDate=_ms(now + timedelta(days=5)))
    r = _verify(uid, first)
    _check("pass -> active and entitled", r.json()["state"] == "active" and r.json()["entitled"] is True)
    ent = _entitlements(uid)
    _check("entitlements show the pass",
           ent["osiris_pass"] is True and ent["osiris_pass_product_id"] == "osiris_pass_monthly")

    renewed = _tx("6001", "osiris_pass_monthly", originalTransactionId="6000",
                  expiresDate=_ms(now + timedelta(days=35)))
    r = _notify(_note("DID_RENEW", renewed))
    _check("DID_RENEW -> ok", r.status_code == 200 and r.json()["state"] == "active")
    expiry = datetime.fromisoformat(_entitlements(uid)["osiris_pass_expires_at"])
    _check("renewal extends the same pass", expiry > now + timedelta(days=30) and _purchase_count_for(uid) == 1)
    _notify(_note("DID_RENEW", renewed))
    _verify(uid, first)
    expiry_again = datetime.fromisoformat(_entitlements(uid)["osiris_pass_expires_at"])
    _check("a repeat and an older transaction change nothing", expiry_again == expiry)

    lapsed = _tx("6002", "osiris_pass_monthly", originalTransactionId="6000",
                 expiresDate=_ms(now + timedelta(days=65)))
    _notify(_note("DID_RENEW", lapsed))
    revoked = _tx("6002", "osiris_pass_monthly", originalTransactionId="6000",
                  expiresDate=_ms(now + timedelta(days=65)), revocationDate=_ms(now))
    r = _notify(_note("REVOKE", revoked))
    _check("REVOKE ends the pass at once", r.json()["state"] == "refunded" and _entitlements(uid)["osiris_pass"] is False)
    _check("the revoked transaction cannot re-activate it",
           _verify(uid, lapsed).json()["entitled"] is False and _entitlements(uid)["osiris_pass"] is False)

    other = _onboard("as_pass2@test.com")
    ended = _tx("6100", "osiris_pass_annual", expiresDate=_ms(now + timedelta(days=1)))
    _verify(other, ended)
    r = _notify(_note("EXPIRED", ended, subtype="VOLUNTARY"))
    _check("EXPIRED ends the pass", r.json()["state"] == "expired" and _entitlements(other)["osiris_pass"] is False)


def _purchase_count_for(uid):
    db = TestingSessionLocal()
    try:
        return db.query(models.AppStorePurchase).filter(models.AppStorePurchase.user_id == uid).count()
    finally:
        db.close()


def test_refund_notification_claws_back_once():
    uid = _onboard("as_refund@test.com")
    before, _ = _balance_and_ledger(uid)
    signed = _tx("7000", "osiris_crystals_adventurer")
    _verify(uid, signed)
    refund = _note("REFUND", _tx("7000", "osiris_crystals_adventurer", revocationDate=_ms(_utcnow())))
    r = _notify(refund)
    _check("REFUND -> refunded", r.status_code == 200 and r.json()["state"] == "refunded")
    _notify(refund)
    _notify(_note("REFUND", _tx("7000", "osiris_crystals_adventurer", revocationDate=_ms(_utcnow()))))
    balance, ledger_sum = _balance_and_ledger(uid)
    _check("the pack is clawed back exactly once", balance == before)
    _check("ledger sums to the balance", balance == ledger_sum)
    r = _verify(uid, signed)
    _check("a refunded transaction is never granted again",
           r.json()["state"] == "refunded" and r.json()["crystals_credited"] == 0 and r.json()["consume"] is False)

    # Policy shared with Google Play: the clawback is capped at the balance, the wallet never goes negative.
    _verify(uid, _tx("7001", "osiris_crystals_starter"))
    db = TestingSessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == uid).first()
        ledger.apply_crystal_delta(db, user, -(user.mana_crystals - 100), "vault_lock")
        db.commit()
    finally:
        db.close()
    _notify(_note("REFUND", _tx("7001", "osiris_crystals_starter", revocationDate=_ms(_utcnow()))))
    balance, ledger_sum = _balance_and_ledger(uid)
    _check("clawback is capped at the balance", balance == 0 and ledger_sum == 0)

    fresh = _onboard("as_revoked@test.com")
    before, _ = _balance_and_ledger(fresh)
    r = _verify(fresh, _tx("7002", "osiris_crystals_champion", revocationDate=_ms(_utcnow())))
    balance, _ = _balance_and_ledger(fresh)
    _check("a transaction Apple already revoked grants nothing",
           r.status_code == 200 and r.json()["state"] == "refunded" and balance == before)


def test_notification_endpoint():
    _check("forged notification -> 400", _notify("abc.def.ghi").status_code == 400)
    _check("missing signedPayload -> 400",
           client.post("/api/v2/payments/app-store/notifications", json={}).status_code == 400)
    r = _notify(_sign({"notificationType": "TEST", "notificationUUID": str(uuid.uuid4()), "data": {}}))
    _check("TEST notification -> 200 ignored", r.status_code == 200 and r.json()["status"] == "ignored")
    r = _notify(_note("DID_RENEW", _tx("8000", "osiris_pass_monthly", expiresDate=_ms(_utcnow()))))
    _check("notification for an unknown purchase -> 200 ignored", r.json()["status"] == "ignored")
    other_key, other_x5c, _ = _chain()
    r = _notify(_sign({"notificationType": "REFUND", "data": {}}, key=other_key, x5c=other_x5c))
    _check("notification from an untrusted chain -> 400", r.status_code == 400)


if __name__ == "__main__":
    print("App Store billing verification tests")
    test_contract_constants()
    test_closed_until_configured()
    test_crystal_pack_credited_once()
    test_rejected_transactions()
    test_account_binding()
    test_founder_pack_and_refund()
    test_subscription_lifecycle()
    test_refund_notification_claws_back_once()
    test_notification_endpoint()
    print()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)}): {_FAILURES}")
        sys.exit(1)
    print("ALL PASSED")
