"""Google Play Billing verification tests (money path).

No pytest dependency — run directly:

    cd Osiris_backend
    OSIRIS_ENV=test python tests/test_google_play_billing.py

Google is never called: the services.google_play functions are replaced with fakes that answer
from the FAKE_* dicts below, the same way tests/test_phase3_stripe.py fakes Stripe.

Coverage:
  - A crystal pack is credited through the ledger exactly once per purchase token; a repeat
    verify grants nothing and the ledger still sums to the balance.
  - A token cannot be claimed by a second account, or re-used for another product.
  - Pending and canceled purchases grant nothing; unknown products 404; malformed tokens 422.
  - Purchases are acknowledged with Google after the grant.
  - Subscriptions: active / canceled-but-paid count; expired and on-hold do not; the
    entitlements endpoint re-reads a pass past its stored expiry.
  - Unconfigured Google Play -> 503; Google outage -> 502; unknown token -> 400.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND)

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "google-play-test-secret-cccccccccccccccccccc")

from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import models  # noqa: E402
from core import security  # noqa: E402
from database import Base, get_db  # noqa: E402
from main import app  # noqa: E402
from services import google_play  # noqa: E402

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

# --- Fake Google Play ----------------------------------------------------------------------
FAKE_PRODUCTS: dict = {}   # (product_id, token) -> products.get body
FAKE_SUBS: dict = {}       # token -> subscriptionsv2.get body
ACKS: list = []
MODE = {"raise": None}


def _maybe_raise():
    if MODE["raise"]:
        raise MODE["raise"]


def _fake_get_product(product_id, token):
    _maybe_raise()
    if (product_id, token) not in FAKE_PRODUCTS:
        raise google_play.InvalidPurchaseError("Google Play does not recognise this purchase.")
    return FAKE_PRODUCTS[(product_id, token)]


def _fake_get_sub(token):
    _maybe_raise()
    if token not in FAKE_SUBS:
        raise google_play.InvalidPurchaseError("Google Play does not recognise this purchase.")
    return FAKE_SUBS[token]


google_play.get_product_purchase = _fake_get_product
google_play.get_subscription = _fake_get_sub
google_play.acknowledge_product = lambda product_id, token: ACKS.append(("product", product_id, token))
google_play.acknowledge_subscription = lambda product_id, token: ACKS.append(("sub", product_id, token))


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


def _verify(uid, product_id, token):
    return client.post("/api/v2/payments/google-play/verify", headers=_auth(uid),
                       json={"product_id": product_id, "purchase_token": token})


def _balance_and_ledger(uid):
    db = TestingSessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == uid).first()
        total = db.query(func.coalesce(func.sum(models.CrystalLedger.delta), 0)).filter(
            models.CrystalLedger.user_id == uid).scalar()
        return user.mana_crystals or 0, total
    finally:
        db.close()


def test_crystal_pack_credited_once():
    uid = _onboard("gp_pack@test.com")
    before, _ = _balance_and_ledger(uid)
    FAKE_PRODUCTS[("osiris_crystals_starter", "tok-pack-1")] = {
        "purchaseState": 0, "acknowledgementState": 0, "consumptionState": 0, "orderId": "GPA.1",
    }
    r1 = _verify(uid, "osiris_crystals_starter", "tok-pack-1")
    body = r1.json()
    _check("pack verify -> 200 credited", r1.status_code == 200 and body["state"] == "credited")
    _check("pack credits the server's 500 crystals", body["crystals_credited"] == 500)
    _check("app is told to consume", body["consume"] is True)
    _check("server acknowledged the purchase", ("product", "osiris_crystals_starter", "tok-pack-1") in ACKS)

    r2 = _verify(uid, "osiris_crystals_starter", "tok-pack-1")
    _check("repeat verify grants nothing", r2.status_code == 200 and r2.json()["crystals_credited"] == 0)
    balance, ledger_sum = _balance_and_ledger(uid)
    _check("balance rose by exactly 500", balance == before + 500)
    _check("ledger sums to the balance", balance == ledger_sum)


def test_token_bound_to_one_account_and_product():
    a, b = _onboard("gp_owner@test.com"), _onboard("gp_thief@test.com")
    before_b, _ = _balance_and_ledger(b)
    FAKE_PRODUCTS[("osiris_crystals_champion", "tok-shared")] = {"purchaseState": 0, "acknowledgementState": 1}
    FAKE_PRODUCTS[("osiris_crystals_adventurer", "tok-shared")] = {"purchaseState": 0, "acknowledgementState": 1}
    _verify(a, "osiris_crystals_champion", "tok-shared")
    r = _verify(b, "osiris_crystals_champion", "tok-shared")
    _check("second account claiming a token -> 409", r.status_code == 409)
    r = _verify(a, "osiris_crystals_adventurer", "tok-shared")
    _check("same token for another product -> 409", r.status_code == 409)
    balance_b, _ = _balance_and_ledger(b)
    _check("second account got no crystals", balance_b == before_b)


def test_pending_canceled_unknown_invalid():
    uid = _onboard("gp_edge@test.com")
    before, _ = _balance_and_ledger(uid)
    FAKE_PRODUCTS[("osiris_crystals_starter", "tok-pending")] = {"purchaseState": 2}
    FAKE_PRODUCTS[("osiris_crystals_starter", "tok-canceled")] = {"purchaseState": 1}
    r = _verify(uid, "osiris_crystals_starter", "tok-pending")
    _check("pending purchase grants nothing", r.status_code == 200 and r.json()["state"] == "pending"
           and r.json()["crystals_credited"] == 0 and r.json()["consume"] is False)
    r = _verify(uid, "osiris_crystals_starter", "tok-canceled")
    _check("canceled purchase grants nothing", r.json()["state"] == "canceled" and r.json()["crystals_credited"] == 0)
    _check("unknown product -> 404", _verify(uid, "osiris_crystals_free", "tok-x").status_code == 404)
    _check("token Google does not know -> 400", _verify(uid, "osiris_crystals_starter", "tok-forged").status_code == 400)
    _check("token with path characters -> 422", _verify(uid, "osiris_crystals_starter", "../../x").status_code == 422)
    balance, _ = _balance_and_ledger(uid)
    _check("no crystals from any of these", balance == before)


def test_founder_pack_and_refund():
    uid = _onboard("gp_founder@test.com")
    FAKE_PRODUCTS[("osiris_founder_pack", "tok-founder")] = {"purchaseState": 0, "acknowledgementState": 0}
    r = _verify(uid, "osiris_founder_pack", "tok-founder")
    _check("founder pack -> owned, not consumed", r.json()["state"] == "owned" and r.json()["consume"] is False)
    ent = client.get("/api/v2/payments/google-play/entitlements", headers=_auth(uid)).json()
    _check("entitlements show the founder pack", ent["founder_pack"] is True)
    FAKE_PRODUCTS[("osiris_founder_pack", "tok-founder")] = {"purchaseState": 1}
    _verify(uid, "osiris_founder_pack", "tok-founder")
    ent = client.get("/api/v2/payments/google-play/entitlements", headers=_auth(uid)).json()
    _check("refunded founder pack stops unlocking", ent["founder_pack"] is False)


def test_subscription_lifecycle():
    uid = _onboard("gp_pass@test.com")
    future = _utcnow() + timedelta(days=30)
    FAKE_SUBS["tok-pass"] = {
        "subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
        "acknowledgementState": "ACKNOWLEDGEMENT_STATE_PENDING",
        "latestOrderId": "GPA.SUB.1",
        "lineItems": [{"productId": "osiris_pass_monthly", "expiryTime": _iso(future)}],
    }
    r = _verify(uid, "osiris_pass_monthly", "tok-pass")
    body = r.json()
    _check("active pass -> entitled", r.status_code == 200 and body["state"] == "active" and body["entitled"])
    _check("pass acknowledged", ("sub", "osiris_pass_monthly", "tok-pass") in ACKS)
    _check("pass grants no crystals", body["crystals_credited"] == 0)
    _check("token for another subscription -> 400", _verify(uid, "osiris_pass_annual", "tok-pass").status_code in (400, 409))

    FAKE_SUBS["tok-pass"]["subscriptionState"] = "SUBSCRIPTION_STATE_CANCELED"
    r = _verify(uid, "osiris_pass_monthly", "tok-pass")
    _check("canceled but paid through expiry -> still entitled", r.json()["entitled"] is True)

    FAKE_SUBS["tok-pass"]["subscriptionState"] = "SUBSCRIPTION_STATE_ON_HOLD"
    r = _verify(uid, "osiris_pass_monthly", "tok-pass")
    _check("on hold -> not entitled", r.json()["entitled"] is False)

    # Stored expiry in the past: entitlements re-reads Google and sees the renewal.
    db = TestingSessionLocal()
    row = db.query(models.GooglePlayPurchase).filter(models.GooglePlayPurchase.purchase_token == "tok-pass").first()
    row.state, row.expires_at = "active", _utcnow() - timedelta(minutes=1)
    db.commit()
    db.close()
    FAKE_SUBS["tok-pass"]["subscriptionState"] = "SUBSCRIPTION_STATE_ACTIVE"
    FAKE_SUBS["tok-pass"]["lineItems"][0]["expiryTime"] = _iso(_utcnow() + timedelta(days=60))
    ent = client.get("/api/v2/payments/google-play/entitlements", headers=_auth(uid)).json()
    _check("entitlements refresh a renewed pass", ent["osiris_pass"] is True and ent["osiris_pass_state"] == "active")

    FAKE_SUBS["tok-pass"]["subscriptionState"] = "SUBSCRIPTION_STATE_EXPIRED"
    FAKE_SUBS["tok-pass"]["lineItems"][0]["expiryTime"] = _iso(_utcnow() - timedelta(days=1))
    r = _verify(uid, "osiris_pass_monthly", "tok-pass")
    _check("expired -> not entitled", r.json()["entitled"] is False)
    ent = client.get("/api/v2/payments/google-play/entitlements", headers=_auth(uid)).json()
    _check("entitlements: no pass after expiry", ent["osiris_pass"] is False)


def test_google_unavailable():
    uid = _onboard("gp_down@test.com")
    FAKE_PRODUCTS[("osiris_crystals_starter", "tok-down")] = {"purchaseState": 0}
    MODE["raise"] = google_play.GooglePlayNotConfiguredError("Google Play billing is not configured on this server.")
    _check("unconfigured -> 503", _verify(uid, "osiris_crystals_starter", "tok-down").status_code == 503)
    MODE["raise"] = google_play.GooglePlayError("Google Play answered 500.")
    _check("Google outage -> 502", _verify(uid, "osiris_crystals_starter", "tok-down").status_code == 502)
    MODE["raise"] = None
    r = _verify(uid, "osiris_crystals_starter", "tok-down")
    _check("retry after outage credits once", r.json()["crystals_credited"] == 500)


def test_parse_time():
    t = google_play.parse_time("2026-11-30T12:00:00.123Z")
    _check("RFC 3339 'Z' time parses to naive UTC", t == datetime(2026, 11, 30, 12, 0, 0, 123000))
    _check("missing time -> None", google_play.parse_time(None) is None)


if __name__ == "__main__":
    print("Google Play Billing verification tests")
    test_crystal_pack_credited_once()
    test_token_bound_to_one_account_and_product()
    test_pending_canceled_unknown_invalid()
    test_founder_pack_and_refund()
    test_subscription_lifecycle()
    test_google_unavailable()
    test_parse_time()
    print()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)}): {_FAILURES}")
        sys.exit(1)
    print("ALL PASSED")
