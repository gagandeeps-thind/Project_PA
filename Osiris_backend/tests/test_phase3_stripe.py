"""Phase 3 money-path tests: Stripe payment integration.

No pytest dependency — run directly:

    cd Osiris_backend
    OSIRIS_ENV=test python tests/test_phase3_stripe.py

Style mirrors tests/test_phase2_ledger.py: module-level `_check`, env set at the top, an
isolated in-memory DB, and a `__main__` block that prints PASS/FAIL and exits non-zero on
any failure. The Stripe SDK is never called for real — `stripe_gateway.create_payment_intent`
and `.construct_event` are monkeypatched to drive deterministic inputs.

Coverage:
  - Crystal pack price is SERVER-authoritative: the client sends only a pack_id; the Stripe
    PaymentIntent is created with the server's amount_cents. Unknown pack_id -> 404.
  - Crystal purchase fulfillment credits via the ledger EXACTLY ONCE; a replayed Stripe event
    (same event.id) and a same-PaymentIntent re-fulfillment are both no-ops (no double-mint).
  - Ledger conservation holds after a purchase (sum(deltas) == mana_crystals).
  - Webhook with a bad signature -> 401; unconfigured Stripe -> 503 on intent creation.
  - Merchant pilot fee activates via payment_intent.succeeded and records revenue once.
"""
import importlib.util
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND)

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "phase3-stripe-test-secret-bbbbbbbbbbbbbbbb")

from datetime import datetime, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from database import Base  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from main import app, get_db, get_password_hash  # noqa: E402

_FAILURES = []


def _check(name, cond):
    status = "PASS" if cond else "FAIL"
    print(f"  {status}  {name}")
    if not cond:
        _FAILURES.append(name)


# --- Isolated in-memory DB shared by the FastAPI app and the test ---------------------------
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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

# Reconciliation script, loaded as a module (scripts/ is not a package) — used to assert the
# ledger invariant end-to-end after a purchase.
_recon_spec = importlib.util.spec_from_file_location(
    "reconcile_ledger", os.path.join(BACKEND, "scripts", "reconcile_ledger.py")
)
reconcile = importlib.util.module_from_spec(_recon_spec)
_recon_spec.loader.exec_module(reconcile)


# --- Fake Stripe gateway --------------------------------------------------------------------
# Records every create_payment_intent call so tests can assert the SERVER chose the amount.
_INTENT_CALLS = []
_PI_COUNTER = {"n": 0}


def _fake_create_payment_intent(*, amount_cents, currency="usd", metadata, description=None,
                                idempotency_key=None):
    _PI_COUNTER["n"] += 1
    pi_id = f"pi_test_{_PI_COUNTER['n']}"
    _INTENT_CALLS.append({
        "amount_cents": amount_cents, "currency": currency, "metadata": dict(metadata),
        "idempotency_key": idempotency_key, "id": pi_id,
    })
    return types.SimpleNamespace(id=pi_id, client_secret=f"{pi_id}_secret_abc")


def _fake_construct_event(payload, sig_header):
    """Drive events by POST body. A 'bad' signature header raises like Stripe would."""
    if sig_header == "bad":
        raise Exception("SignatureVerificationError: no signatures found matching the payload")
    return json.loads(payload)


main.stripe_gateway.create_payment_intent = _fake_create_payment_intent
main.stripe_gateway.construct_event = _fake_construct_event
main.stripe_gateway.STRIPE_PUBLISHABLE_KEY = "pk_test_fake"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _now_str() -> str:
    return "2026-06-29T12:00:00Z"


def _player_auth(uid: int) -> dict:
    tok = main.create_access_token({"sub": str(uid), "role": "player"})
    return {"Authorization": f"Bearer {tok}"}


def _merchant_auth(mid: int) -> dict:
    tok = main.create_access_token({"sub": str(mid), "role": "merchant"})
    return {"Authorization": f"Bearer {tok}"}


def _onboard(email):
    r = client.post("/api/v1/onboard", json={
        "email": email, "password": "PlayerTest1!",
        "weight_kg": 75, "height_m": 1.8, "preferred_path": "Strength",
        "device_timestamp": _now_str(),
    })
    assert r.status_code == 200, f"onboard failed: {r.status_code} {r.text}"
    db = TestingSessionLocal()
    try:
        return db.query(models.User).filter(models.User.email == email).first().id
    finally:
        db.close()


def _make_merchant(email, fee_cents=5000):
    db = TestingSessionLocal()
    try:
        m = models.Merchant(
            name="Test Cafe", email=email, hashed_password=get_password_hash("pw"),
            business_type="cafe", is_active=False, payment_status="payment_pending",
            pilot_fee_cents=fee_cents,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        return m.id
    finally:
        db.close()


def _succeeded_event(event_id, pi_id, amount_cents, metadata):
    return {
        "id": event_id, "type": "payment_intent.succeeded",
        "data": {"object": {"id": pi_id, "amount": amount_cents, "metadata": metadata}},
    }


def _post_webhook(event, sig="good"):
    return client.post(
        "/api/v1/payments/stripe/webhook",
        content=json.dumps(event),
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )


def _user(uid):
    db = TestingSessionLocal()
    try:
        return db.get(models.User, uid)
    finally:
        db.close()


def _ledger_sum(uid) -> int:
    db = TestingSessionLocal()
    try:
        return (
            db.query(func.coalesce(func.sum(models.CrystalLedger.delta), 0))
            .filter(models.CrystalLedger.user_id == uid).scalar()
        )
    finally:
        db.close()


# --- Test 1: server sets the crystal price; client only picks a pack ------------------------
def test_price_is_server_authoritative():
    uid = _onboard("stripe_price@test.com")
    _INTENT_CALLS.clear()
    r = client.post("/api/v1/payments/crystals/intent",
                    headers=_player_auth(uid), json={"pack_id": "starter"})
    _check("crystals/intent returns 200", r.status_code == 200)
    body = r.json()
    pack = main.CRYSTAL_PACKS["starter"]
    _check("response amount_cents matches server pack",
           body.get("amount_cents") == pack["amount_cents"])
    _check("response crystal_amount matches server pack",
           body.get("crystal_amount") == pack["crystals"])
    _check("client_secret returned for the SDK", bool(body.get("client_secret")))
    _check("Stripe charged the SERVER amount, not a client value",
           _INTENT_CALLS and _INTENT_CALLS[-1]["amount_cents"] == pack["amount_cents"])
    _check("intent metadata routes the webhook (kind=crystal_purchase)",
           _INTENT_CALLS[-1]["metadata"].get("kind") == "crystal_purchase")

    # Unknown pack rejected.
    r2 = client.post("/api/v1/payments/crystals/intent",
                     headers=_player_auth(uid), json={"pack_id": "free_million"})
    _check("unknown pack_id -> 404", r2.status_code == 404)


# --- Test 2: fulfillment credits exactly once; replays are no-ops (no double-mint) ----------
def test_crystal_fulfillment_idempotent():
    uid = _onboard("stripe_fulfill@test.com")
    start = _user(uid).mana_crystals  # opening balance (100)

    r = client.post("/api/v1/payments/crystals/intent",
                    headers=_player_auth(uid), json={"pack_id": "champion"})
    assert r.status_code == 200, r.text
    intent = r.json()
    pi_id = intent["payment_intent_id"]
    grant = main.CRYSTAL_PACKS["champion"]["crystals"]
    price = main.CRYSTAL_PACKS["champion"]["amount_cents"]
    meta = {"kind": "crystal_purchase", "user_id": str(uid),
            "pack_id": "champion", "crystal_amount": str(grant)}

    # First webhook: credit.
    w1 = _post_webhook(_succeeded_event("evt_1", pi_id, price, meta))
    _check("webhook succeeded returns 200", w1.status_code == 200)
    _check("crystals credited once", _user(uid).mana_crystals == start + grant)
    _check("conservation sum(deltas)==mana_crystals", _ledger_sum(uid) == _user(uid).mana_crystals)

    db = TestingSessionLocal()
    try:
        purchase = db.query(models.CrystalPurchase).filter(
            models.CrystalPurchase.stripe_payment_intent_id == pi_id).first()
        _check("purchase marked succeeded", purchase.status == "succeeded")
        _check("purchase linked to a ledger row", purchase.crystal_ledger_id is not None)
        rev = db.query(models.PlatformRevenue).filter(
            models.PlatformRevenue.source == "crystal_purchase",
            models.PlatformRevenue.user_id == uid).all()
        _check("exactly one revenue row for the purchase", len(rev) == 1 and rev[0].amount == price)
    finally:
        db.close()

    # Replay the SAME event id -> event-level dedup, no-op.
    w2 = _post_webhook(_succeeded_event("evt_1", pi_id, price, meta))
    _check("duplicate event.id is a no-op (balance unchanged)",
           _user(uid).mana_crystals == start + grant)

    # A DIFFERENT event id for the SAME PaymentIntent -> purchase.status guard, still no-op.
    w3 = _post_webhook(_succeeded_event("evt_2", pi_id, price, meta))
    _check("re-fulfilling the same PaymentIntent is a no-op (no double-mint)",
           _user(uid).mana_crystals == start + grant)
    _check("conservation still holds after replays", _ledger_sum(uid) == _user(uid).mana_crystals)
    _ = (w2, w3)


# --- Test 3: signature failure -> 401 -------------------------------------------------------
def test_webhook_bad_signature_rejected():
    ev = _succeeded_event("evt_bad", "pi_x", 999, {"kind": "crystal_purchase", "user_id": "1"})
    r = _post_webhook(ev, sig="bad")
    _check("bad Stripe signature -> 401", r.status_code == 401)


# --- Test 4: merchant pilot fee activates once via the webhook ------------------------------
def test_merchant_pilot_fee_activation():
    mid = _make_merchant("stripe_merchant@test.com", fee_cents=5000)
    r = client.post(f"/api/v1/merchants/{mid}/payments/intent", headers=_merchant_auth(mid))
    _check("merchant intent returns 200", r.status_code == 200)
    pi_id = r.json()["provider_payment_id"]
    meta = {"kind": "merchant_pilot_fee", "merchant_id": str(mid)}

    w1 = _post_webhook(_succeeded_event("evt_m1", pi_id, 5000, meta))
    _check("merchant webhook returns 200", w1.status_code == 200)

    db = TestingSessionLocal()
    try:
        m = db.get(models.Merchant, mid)
        _check("merchant activated", bool(m.is_active))
        _check("merchant payment_status successful", m.payment_status == "payment_successful")
        rev = db.query(models.PlatformRevenue).filter(
            models.PlatformRevenue.source == "merchant_pilot_fee").all()
        _check("one pilot-fee revenue row", len(rev) == 1 and rev[0].amount == 5000)
    finally:
        db.close()

    # Replay -> no second activation, no second revenue row.
    _post_webhook(_succeeded_event("evt_m1", pi_id, 5000, meta))
    db = TestingSessionLocal()
    try:
        rev = db.query(models.PlatformRevenue).filter(
            models.PlatformRevenue.source == "merchant_pilot_fee").all()
        _check("replay does not double-record merchant revenue", len(rev) == 1)
    finally:
        db.close()


# --- Test 5: unconfigured Stripe -> 503 (fail loud, never a silent stub) --------------------
def test_unconfigured_stripe_503():
    uid = _onboard("stripe_off@test.com")
    saved = main.stripe_gateway.create_payment_intent

    def _raise_not_configured(**kwargs):
        raise main.stripe_gateway.StripeNotConfiguredError("Stripe is not configured.")

    main.stripe_gateway.create_payment_intent = _raise_not_configured
    try:
        r = client.post("/api/v1/payments/crystals/intent",
                        headers=_player_auth(uid), json={"pack_id": "starter"})
        _check("intent creation with Stripe disabled -> 503", r.status_code == 503)
    finally:
        main.stripe_gateway.create_payment_intent = saved


if __name__ == "__main__":
    print("Phase 3 — Stripe payment integration tests")
    test_price_is_server_authoritative()
    test_crystal_fulfillment_idempotent()
    test_webhook_bad_signature_rejected()
    test_merchant_pilot_fee_activation()
    test_unconfigured_stripe_503()
    print()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)}): {_FAILURES}")
        sys.exit(1)
    print("ALL PASSED")
