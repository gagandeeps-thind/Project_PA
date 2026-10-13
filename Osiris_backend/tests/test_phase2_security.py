"""Regression suite for the named security hardening requirements.

No pytest dependency — run directly:

    cd Osiris_backend
    python tests/test_phase2_security.py

Each test is written to FAIL on the pre-Phase-2 code and PASS after the fix:

  B1 (§2.1) webhook fail-closed:
     - boot: with NO webhook secret and an unset OSIRIS_ENV (a deploy that forgot the var),
       importing `main` must RAISE. Old code booted fine and served a forgeable webhook.
     - runtime: with the secret configured, an UNSIGNED forged `payment_successful` must 401
       and must NOT activate the merchant or write a PlatformRevenue row.
  B2 (§2.5) CORS: a disallowed Origin must NOT be reflected, and `*` must never be returned.
       Old code (`allow_origins=["*"]` + credentials) reflected the attacker's origin.
  B5 (§2.2) /domains/nearby now requires a player JWT. Old code returned 200 unauthenticated.
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND)

_FAILURES = []


def _check(name, cond):
    status = "PASS" if cond else "FAIL"
    print(f"  {status}  {name}")
    if not cond:
        _FAILURES.append(name)


# --- B1a: fail-closed boot (subprocess; must run BEFORE main is imported in-process) -------
def test_webhook_fail_closed_boot():
    env = {k: v for k, v in os.environ.items()
           if k not in ("OSIRIS_WEBHOOK_SECRET", "OSIRIS_ENV")}
    # The repository may contain a developer-only .env. Disable dotenv loading in this
    # subprocess so the test genuinely exercises the missing-secret boot path.
    env["PYTHON_DOTENV_DISABLED"] = "1"
    proc = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )
    booted_wide_open = proc.returncode == 0
    mentions_secret = "OSIRIS_WEBHOOK_SECRET" in (proc.stderr + proc.stdout)
    _check("B1 §2.1 app refuses to boot with no webhook secret in a non-dev env",
           (not booted_wide_open) and mentions_secret)


# Configure a correct prod-like env, THEN import main for the in-process tests.
os.environ["OSIRIS_ENV"] = "production"
os.environ["OSIRIS_WEBHOOK_SECRET"] = "phase2-test-webhook-secret"
os.environ.setdefault("OSIRIS_JWT_SECRET", "phase2-test-jwt-secret-aaaaaaaaaaaaaaaaaaaa")
# Production also requires Stripe config (fail-closed), so a
# correct prod-like env must supply these too — same pattern as the secrets above.
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_phase2_dummy")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_phase2_dummy")


def _client_and_models():
    from fastapi.testclient import TestClient
    import main
    import models
    import database
    return TestClient(main.app), models, database


# --- B1b: unsigned forged webhook is rejected; no activation, no revenue -------------------
def test_unsigned_webhook_rejected():
    client, models, database = _client_and_models()
    db = database.SessionLocal()
    rev_before = db.query(models.PlatformRevenue).count()
    m = models.Merchant(
        name="ph2-sec-test", email="ph2sec_merchant@example.com",
        hashed_password="x", is_active=False, payment_status="payment_pending",
        pilot_fee_cents=5000,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    mid = m.id
    try:
        forged = {
            "merchant_id": mid, "payment_status": "payment_successful",
            "provider_payment_id": "pi_forged", "amount_cents": 5000,
            "occurred_at": "2026-06-11T00:00:00+00:00", "provider_event_id": "evt_forged_1",
        }
        # No X-Provider-Signature header -> must be rejected.
        resp = client.post("/api/v1/payments/webhook", json=forged)
        db.expire_all()
        m2 = db.query(models.Merchant).filter(models.Merchant.id == mid).first()
        rev_after = db.query(models.PlatformRevenue).count()
        _check("B1 §2.1 unsigned forged webhook -> 401", resp.status_code == 401)
        _check("B1 §2.1 forged webhook did not activate merchant", m2.is_active is False)
        _check("B1 §2.1 forged webhook wrote no PlatformRevenue", rev_after == rev_before)
    finally:
        db.query(models.Merchant).filter(models.Merchant.id == mid).delete()
        db.commit()
        db.close()


# --- B5: /domains/nearby requires auth ------------------------------------------------------
def test_domains_nearby_requires_auth():
    client, _models, _db = _client_and_models()
    resp = client.get("/api/v1/domains/nearby", params={"lat": 44.6, "lng": -63.6})
    _check("B5 §2.2 /domains/nearby without token -> 401", resp.status_code == 401)


# --- B2: CORS does not reflect a disallowed origin and never returns '*' --------------------
def test_cors_no_wildcard_reflection():
    client, _models, _db = _client_and_models()
    evil = client.get("/", headers={"Origin": "http://evil.example"})
    acao_evil = evil.headers.get("access-control-allow-origin")
    _check("B2 §2.5 disallowed origin is not reflected and is not '*'",
           acao_evil not in ("http://evil.example", "*"))
    allowed = client.get("/", headers={"Origin": "http://localhost:5173"})
    acao_ok = allowed.headers.get("access-control-allow-origin")
    _check("B2 §2.5 allowlisted origin is echoed explicitly (not '*')",
           acao_ok == "http://localhost:5173")


# --- B3 (§4.3): auth/login is rate limited --------------------------------------------------
def test_login_rate_limited():
    client, _models, _db = _client_and_models()
    body = {
        "email": "nobody-ph2@example.com", "password": "wrongpass",
        "device_timestamp": "2026-06-11T00:00:00+00:00",
    }
    codes = [client.post("/api/v1/auth/login", json=body).status_code for _ in range(15)]
    # Limit is 10/60s; a 15-call burst from one IP must hit 429 (old code: all 401, never 429).
    _check("B3 §4.3 /auth/login is rate limited (429 after a burst)", 429 in codes)


if __name__ == "__main__":
    test_webhook_fail_closed_boot()
    test_unsigned_webhook_rejected()
    test_domains_nearby_requires_auth()
    test_cors_no_wildcard_reflection()
    test_login_rate_limited()
    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} check(s) FAILED: {_FAILURES}")
        sys.exit(1)
    print("All Phase 2 security checks passed.")
