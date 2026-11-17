"""Google Play Billing verification tests (money path).

No pytest dependency — run directly:

    cd Osiris_backend
    OSIRIS_ENV=test python tests/test_google_play_billing.py

Google is never called: the services.google_play functions are replaced with fakes that answer
from the FAKE_* dicts below.

Coverage:
  - A crystal pack is credited through the ledger exactly once per purchase token; a repeat
    verify grants nothing and the ledger still sums to the balance.
  - A token cannot be claimed by a second account, or re-used for another product.
  - Pending and canceled purchases grant nothing; unknown products 404; malformed tokens 422.
  - Purchases are acknowledged with Google after the grant.
  - Subscriptions: active / canceled-but-paid count; expired and on-hold do not; the
    entitlements endpoint re-reads a pass past its stored expiry.
  - Unconfigured Google Play -> 503; Google outage -> 502; unknown token -> 400. With the real
    client and no credentials, verify grants nothing; error text from Google never reaches the client.
  - Multi-quantity purchases credit every pack; obfuscatedAccountId must match the caller when
    present; licence-test purchases are refused when GOOGLE_PLAY_ALLOW_TEST_PURCHASES is off.
  - Refunds: a voided pack is clawed back once through the ledger (capped at the balance), by a
    notification or by the voided-purchases job; a refunded purchase is never granted again.
  - RTDN endpoint: closed without its token, 403 on a wrong one, follows Google's state.
"""
import base64
import json
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

import database  # noqa: E402
import models  # noqa: E402
from core import security  # noqa: E402
from database import Base, get_db  # noqa: E402
from main import app  # noqa: E402
from services import google_play, jobs, ledger  # noqa: E402

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


_REAL_GET_PRODUCT = google_play.get_product_purchase
VOIDED: list = []          # voidedpurchases.list body items
google_play.get_product_purchase = _fake_get_product
google_play.list_voided_purchases = lambda: list(VOIDED)
database.SessionLocal = TestingSessionLocal  # the job opens its own session
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


def test_fails_closed_without_credentials():
    """The real client, no service-account key: nothing is verified, so nothing is granted."""
    uid = _onboard("gp_nocreds@test.com")
    before, _ = _balance_and_ledger(uid)
    os.environ.pop("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", None)
    os.environ.pop("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_FILE", None)
    google_play._session = None
    google_play.get_product_purchase = _REAL_GET_PRODUCT
    try:
        r = _verify(uid, "osiris_crystals_starter", "tok-nocreds")
    finally:
        google_play.get_product_purchase = _fake_get_product
    _check("no credentials -> 503", r.status_code == 503)
    db = TestingSessionLocal()
    stored = db.query(models.GooglePlayPurchase).filter(
        models.GooglePlayPurchase.purchase_token == "tok-nocreds").count()
    db.close()
    balance, ledger_sum = _balance_and_ledger(uid)
    _check("no credentials -> no purchase row, no crystals", stored == 0 and balance == before == ledger_sum)


def test_error_text_is_not_returned():
    uid = _onboard("gp_leak@test.com")
    MODE["raise"] = google_play.GooglePlayError("https://androidpublisher.example/tokens/SECRET-TOKEN failed")
    r = _verify(uid, "osiris_crystals_starter", "tok-leak")
    MODE["raise"] = None
    _check("Google's error text stays in the log", r.status_code == 502 and "SECRET" not in r.text)


def test_acknowledge_failure_keeps_the_grant():
    uid = _onboard("gp_ack@test.com")
    FAKE_PRODUCTS[("osiris_crystals_starter", "tok-ack")] = {"purchaseState": 0, "acknowledgementState": 0}

    def _ack_fails(product_id, token):
        raise google_play.InvalidPurchaseError("Google Play does not recognise this purchase.")

    working = google_play.acknowledge_product
    google_play.acknowledge_product = _ack_fails
    try:
        r = _verify(uid, "osiris_crystals_starter", "tok-ack")
    finally:
        google_play.acknowledge_product = working
    _check("acknowledge failure after the grant -> still 200 credited",
           r.status_code == 200 and r.json()["crystals_credited"] == 500 and r.json()["consume"] is True)


def test_quantity_multiplies_the_grant():
    uid = _onboard("gp_qty@test.com")
    before, _ = _balance_and_ledger(uid)
    FAKE_PRODUCTS[("osiris_crystals_starter", "tok-qty")] = {"purchaseState": 0, "quantity": 3, "orderId": "GPA.Q"}
    r = _verify(uid, "osiris_crystals_starter", "tok-qty")
    balance, ledger_sum = _balance_and_ledger(uid)
    _check("quantity 3 credits three packs", r.json()["crystals_credited"] == 1500 and balance == before + 1500)
    _check("ledger sums to the balance after a multi-quantity grant", balance == ledger_sum)


def test_obfuscated_account_id():
    _check("contract: sha256 hex of 'osiris:<id>'", google_play.obfuscated_account_id(42)
           == "df7e2e42324356cfe97e6fe75ee3e9467aabecf5393e9b8a5ba23d3dbb9e745d")
    a, b = _onboard("gp_acct_a@test.com"), _onboard("gp_acct_b@test.com")
    before_b, _ = _balance_and_ledger(b)
    FAKE_PRODUCTS[("osiris_crystals_starter", "tok-acct")] = {
        "purchaseState": 0, "obfuscatedExternalAccountId": google_play.obfuscated_account_id(a),
    }
    r = _verify(b, "osiris_crystals_starter", "tok-acct")
    _check("purchase started by another account -> 409, nothing granted",
           r.status_code == 409 and _balance_and_ledger(b)[0] == before_b)
    r = _verify(a, "osiris_crystals_starter", "tok-acct")
    _check("the buyer's own account is credited", r.status_code == 200 and r.json()["crystals_credited"] == 500)
    FAKE_SUBS["tok-acct-sub"] = {
        "subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
        "externalAccountIdentifiers": {"obfuscatedExternalAccountId": google_play.obfuscated_account_id(a)},
        "lineItems": [{"productId": "osiris_pass_monthly", "expiryTime": _iso(_utcnow() + timedelta(days=30))}],
    }
    _check("subscription started by another account -> 409",
           _verify(b, "osiris_pass_monthly", "tok-acct-sub").status_code == 409)
    _check("subscription for its buyer -> entitled", _verify(a, "osiris_pass_monthly", "tok-acct-sub").json()["entitled"])


def test_test_purchases_can_be_refused():
    uid = _onboard("gp_tester@test.com")
    before, _ = _balance_and_ledger(uid)
    FAKE_PRODUCTS[("osiris_crystals_starter", "tok-test")] = {"purchaseState": 0, "purchaseType": 0}
    FAKE_SUBS["tok-test-sub"] = {
        "subscriptionState": "SUBSCRIPTION_STATE_ACTIVE", "testPurchase": {},
        "lineItems": [{"productId": "osiris_pass_monthly", "expiryTime": _iso(_utcnow() + timedelta(days=30))}],
    }
    os.environ["GOOGLE_PLAY_ALLOW_TEST_PURCHASES"] = "false"
    try:
        r = _verify(uid, "osiris_crystals_starter", "tok-test")
        r_sub = _verify(uid, "osiris_pass_monthly", "tok-test-sub")
    finally:
        del os.environ["GOOGLE_PLAY_ALLOW_TEST_PURCHASES"]
    _check("test purchases off -> 403, nothing granted",
           r.status_code == 403 and r_sub.status_code == 403 and _balance_and_ledger(uid)[0] == before)
    r = _verify(uid, "osiris_crystals_starter", "tok-test")
    _check("test purchases on (default) -> credited", r.status_code == 200 and r.json()["crystals_credited"] == 500)


def _rtdn(note, token="rtdn-secret", headers=None):
    data = base64.b64encode(json.dumps({"packageName": "osiris.fit", **note}).encode()).decode()
    suffix = f"?token={token}" if token else ""
    return client.post(f"/api/v2/payments/google-play/rtdn{suffix}", headers=headers,
                       json={"message": {"data": data, "messageId": "m-1"}, "subscription": "projects/x/subscriptions/y"})


def _purchase_state(token):
    db = TestingSessionLocal()
    try:
        return db.query(models.GooglePlayPurchase).filter(models.GooglePlayPurchase.purchase_token == token).first().state
    finally:
        db.close()


def test_rtdn_auth_fails_closed():
    os.environ.pop("GOOGLE_PLAY_RTDN_TOKEN", None)
    _check("rtdn without a configured token -> 503", _rtdn({"testNotification": {}}).status_code == 503)
    os.environ["GOOGLE_PLAY_RTDN_TOKEN"] = "rtdn-secret"
    _check("rtdn with a wrong token -> 403", _rtdn({"testNotification": {}}, token="guess").status_code == 403)
    _check("rtdn with no token -> 403", _rtdn({"testNotification": {}}, token=None).status_code == 403)
    r = _rtdn({"testNotification": {}})
    _check("rtdn test notification -> 200 ignored", r.status_code == 200 and r.json()["status"] == "ignored")
    r = _rtdn({"testNotification": {}}, token=None, headers={"X-Osiris-Rtdn-Token": "rtdn-secret"})
    _check("rtdn token accepted in the header", r.status_code == 200)
    r = client.post("/api/v2/payments/google-play/rtdn?token=rtdn-secret", json={"message": {"data": "!!"}})
    _check("rtdn malformed message -> 400", r.status_code == 400)
    r = _rtdn({"voidedPurchaseNotification": {"purchaseToken": "tok-never-seen"}})
    _check("rtdn for an unknown purchase -> 200 ignored", r.status_code == 200 and r.json()["status"] == "ignored")


def test_rtdn_refund_claws_back_once():
    os.environ["GOOGLE_PLAY_RTDN_TOKEN"] = "rtdn-secret"
    uid = _onboard("gp_refund@test.com")
    before, _ = _balance_and_ledger(uid)
    FAKE_PRODUCTS[("osiris_crystals_starter", "tok-refund")] = {"purchaseState": 0, "orderId": "GPA.R"}
    _verify(uid, "osiris_crystals_starter", "tok-refund")
    note = {"voidedPurchaseNotification": {"purchaseToken": "tok-refund", "orderId": "GPA.R", "productType": 2, "refundType": 1}}
    r = _rtdn(note)
    balance, ledger_sum = _balance_and_ledger(uid)
    _check("refund notification -> purchase refunded", r.status_code == 200 and r.json()["state"] == "refunded")
    _check("refund takes the 500 crystals back", balance == before and balance == ledger_sum)
    _rtdn(note)
    _check("repeated notification claws back nothing more", _balance_and_ledger(uid)[0] == before)
    r = _verify(uid, "osiris_crystals_starter", "tok-refund")
    _check("a refunded purchase is never granted again", r.json()["crystals_credited"] == 0
           and r.json()["consume"] is False and r.json()["entitled"] is False and _balance_and_ledger(uid)[0] == before)
    db = TestingSessionLocal()
    reasons = [e.reason_code for e in db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id == uid)]
    db.close()
    _check("one crystal_refund ledger entry", reasons.count("crystal_refund") == 1)

    # A pending purchase that Google cancels after the fact arrives as a one-time product notification.
    FAKE_PRODUCTS[("osiris_founder_pack", "tok-founder-rtdn")] = {"purchaseState": 0}
    _verify(uid, "osiris_founder_pack", "tok-founder-rtdn")
    FAKE_PRODUCTS[("osiris_founder_pack", "tok-founder-rtdn")] = {"purchaseState": 1}
    _rtdn({"oneTimeProductNotification": {"purchaseToken": "tok-founder-rtdn", "notificationType": 2}})
    ent = client.get("/api/v2/payments/entitlements", headers=_auth(uid)).json()
    _check("canceled founder pack stops unlocking", _purchase_state("tok-founder-rtdn") == "refunded"
           and ent["founder_pack"] is False)


def test_voided_purchases_job():
    uid = _onboard("gp_voided@test.com")
    before, _ = _balance_and_ledger(uid)
    FAKE_PRODUCTS[("osiris_crystals_starter", "tok-voided")] = {"purchaseState": 0, "orderId": "GPA.V"}
    _verify(uid, "osiris_crystals_starter", "tok-voided")
    # The player spends 450 of the 500 before the refund lands: the clawback is capped at the balance.
    db = TestingSessionLocal()
    user = db.query(models.User).filter(models.User.id == uid).first()
    ledger.apply_crystal_delta(db, user, -(before + 450), "vault_lock")
    db.commit()
    db.close()
    VOIDED[:] = [{"purchaseToken": "tok-voided", "orderId": "GPA.V"}, {"purchaseToken": "tok-not-ours"}]
    _check("job voids the refunded purchase", jobs.process_play_voided_purchases() == 1)
    balance, ledger_sum = _balance_and_ledger(uid)
    _check("clawback is capped at the balance (never negative)", balance == 0 and ledger_sum == 0)
    _check("job is idempotent", jobs.process_play_voided_purchases() == 0 and _balance_and_ledger(uid)[0] == 0)
    VOIDED[:] = []

    def _unconfigured():
        raise google_play.GooglePlayNotConfiguredError("Google Play billing is not configured on this server.")

    working = google_play.list_voided_purchases
    google_play.list_voided_purchases = _unconfigured
    try:
        _check("job is a no-op without credentials", jobs.process_play_voided_purchases() == 0)
    finally:
        google_play.list_voided_purchases = working


def test_rtdn_subscription_follows_google():
    os.environ["GOOGLE_PLAY_RTDN_TOKEN"] = "rtdn-secret"
    uid = _onboard("gp_rtdn_sub@test.com")
    FAKE_SUBS["tok-rtdn-sub"] = {
        "subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
        "lineItems": [{"productId": "osiris_pass_annual", "expiryTime": _iso(_utcnow() + timedelta(days=30))}],
    }
    _verify(uid, "osiris_pass_annual", "tok-rtdn-sub")
    note = {"subscriptionNotification": {"purchaseToken": "tok-rtdn-sub", "subscriptionId": "osiris_pass_annual"}}
    FAKE_SUBS["tok-rtdn-sub"]["lineItems"][0]["expiryTime"] = _iso(_utcnow() + timedelta(days=395))
    _rtdn({"subscriptionNotification": {**note["subscriptionNotification"], "notificationType": 2}})
    ent = client.get("/api/v2/payments/entitlements", headers=_auth(uid)).json()
    _check("renewal notification extends the pass", ent["osiris_pass"] is True
           and datetime.fromisoformat(ent["osiris_pass_expires_at"]) > _utcnow() + timedelta(days=390))
    legacy = client.get("/api/v2/payments/google-play/entitlements", headers=_auth(uid)).json()
    _check("store-neutral and google-play entitlements agree", ent == legacy)

    MODE["raise"] = google_play.GooglePlayError("Google Play answered 500.")
    r = _rtdn(note)
    MODE["raise"] = None
    _check("Google outage -> 502 so Pub/Sub redelivers", r.status_code == 502)

    FAKE_SUBS["tok-rtdn-sub"]["subscriptionState"] = "SUBSCRIPTION_STATE_EXPIRED"  # revoked: Google ends it at once
    r = _rtdn({"subscriptionNotification": {**note["subscriptionNotification"], "notificationType": 12}})
    ent = client.get("/api/v2/payments/entitlements", headers=_auth(uid)).json()
    _check("revoked pass stops unlocking at once", r.json()["state"] == "expired" and ent["osiris_pass"] is False)


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
    test_fails_closed_without_credentials()
    test_error_text_is_not_returned()
    test_acknowledge_failure_keeps_the_grant()
    test_quantity_multiplies_the_grant()
    test_obfuscated_account_id()
    test_test_purchases_can_be_refused()
    test_rtdn_auth_fails_closed()
    test_rtdn_refund_claws_back_once()
    test_voided_purchases_job()
    test_rtdn_subscription_follows_google()
    test_parse_time()
    print()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)}): {_FAILURES}")
        sys.exit(1)
    print("ALL PASSED")
