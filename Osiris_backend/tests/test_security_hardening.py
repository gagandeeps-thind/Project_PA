"""Security hardening: SQL injection payloads, auth revocation, economy caps, headers and boot checks.

    python tests/test_security_hardening.py

Runs against an in-memory database (dependency override), so it leaves no rows behind.
"""
import os
import subprocess
import sys
from datetime import timedelta

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "security-hardening-test-secret-aaaaaaaaaaaaaa")
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from core import clock, security  # noqa: E402
from core.origin_guard import OriginGuardMiddleware  # noqa: E402
from core.rate_limit import _rl_join, _rl_onboard, _rl_password, _rl_social  # noqa: E402

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
database.Base.metadata.create_all(bind=engine)


def _db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


main.app.dependency_overrides[database.get_db] = _db
client = TestClient(main.app)
PASSWORD = "Hardening123!"
SQLI = ["' OR '1'='1", "'; DROP TABLE users; --", "\" OR \"\"=\"", "1 UNION SELECT email, hashed_password FROM users --",
        "%", "%%", "__", "\\", "admin'--", "') OR ('a'='a"]


def _register(name: str) -> tuple[dict, int]:
    r = client.post("/api/v2/auth/register", json={
        "email": f"sec_{name}@example.com", "password": PASSWORD, "display_name": name.title(),
        "goal": "fitness", "location_consent": False,
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["profile"]["user_id"]


def _admin() -> tuple[dict, int]:
    db = Session()
    admin = models.Admin(email="sec_admin@example.com", hashed_password=security.get_password_hash("Admin-pass-1234"),
                         name="Sec Admin")
    db.add(admin)
    db.commit()
    admin_id = admin.id
    db.close()
    r = client.post("/api/v1/auth/login", json={"email": "sec_admin@example.com", "password": "Admin-pass-1234",
                                                "device_timestamp": "2026-11-16T00:00:00+00:00"})
    assert r.status_code == 200 and r.json()["role"] == "admin", r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, admin_id


def test_sql_injection_payloads_are_inert(player: dict, admin: dict) -> None:
    probes = []
    for p in SQLI:
        probes += [
            ("/api/v2/social/search", {"q": p}, player), ("/api/v2/communities", {"city": p, "kind": p}, player),
            ("/api/v2/seasons", {"city": p}, player), ("/api/v2/admin/reports", {"status": p}, admin),
            ("/api/v2/admin/challenges", {"status": p}, admin), ("/api/v1/admin/merchants", {"status": p}, admin),
            ("/api/v2/admin/audit-events", {"entity_type": p, "action": p}, admin),
            ("/api/v2/admin/exercise-sessions", {"status": p}, admin),
            (f"/api/v2/communities/{p}", {}, player), (f"/api/v2/public/players/{p}", {}, None),
            (f"/api/v1/coupons/{p}", {}, admin), (f"/api/v2/share/{p}", {}, None),
        ]
    for path, params, headers in probes:
        r = client.get(path, params=params, headers=headers or {})
        assert r.status_code < 500, (path, params, r.status_code, r.text)
        # No password hash and no other player's email, whatever the payload (a 422 may echo the payload itself).
        assert "$2b$" not in r.text and "sec_mallory@" not in r.text, (path, params)
    # LIKE wildcards are matched literally: '%', '_' and quotes find nobody, not everybody.
    for p in ["%%", "__", "' OR '1'='1", "%' --"]:
        r = client.get("/api/v2/social/search", params={"q": p}, headers=player)
        assert r.status_code in (200, 422) and (r.status_code == 422 or r.json() == []), (p, r.text)
    assert client.get("/api/v2/social/search", params={"q": "mallo"}, headers=player).json(), "a real name still matches"
    for email in ["' OR '1'='1", "x@example.com' OR '1'='1"]:
        r = client.post("/api/v1/auth/login", json={"email": email, "password": "' OR '1'='1",
                                                    "device_timestamp": "2026-11-16T00:00:00+00:00"})
        assert r.status_code in (401, 422), r.text
    print("PASS test_sql_injection_payloads_are_inert")


def test_login_and_signup_do_not_enumerate() -> None:
    body = {"password": "wrong-password", "device_timestamp": "2026-11-16T00:00:00+00:00"}
    unknown = client.post("/api/v1/login", json={**body, "email": "sec_nobody@example.com"})
    wrong = client.post("/api/v1/login", json={**body, "email": "sec_eve@example.com"})
    assert unknown.status_code == wrong.status_code == 401 and unknown.json() == wrong.json(), (unknown.text, wrong.text)
    r = client.post("/api/v1/merchants/register", json={"name": "Probe", "email": "sec_admin@example.com",
                                                         "password": "Probe-pass-123"})
    assert r.status_code == 400 and r.json()["detail"] == "Email already registered.", r.text
    print("PASS test_login_and_signup_do_not_enumerate")


def test_v1_account_endpoints_honour_revocation_and_suspension() -> None:
    headers, uid = _register("rev")
    db = Session()
    user = db.get(models.User, uid)
    user.suspended_at = clock._now_naive_utc()
    db.commit()
    assert client.get(f"/api/v1/users/{uid}", headers=headers).status_code == 403
    assert client.get(f"/api/v1/users/{uid}/export", headers=headers).status_code == 200, "a suspended player may export"
    user.suspended_at = None
    user.tokens_valid_after = clock._now_naive_utc() + timedelta(minutes=1)
    db.commit()
    db.close()
    for method, path in (("get", f"/api/v1/users/{uid}"), ("get", f"/api/v1/users/{uid}/export"),
                         ("delete", f"/api/v1/users/{uid}")):
        r = getattr(client, method)(path, headers=headers)
        assert r.status_code == 401, (path, r.text)
    print("PASS test_v1_account_endpoints_honour_revocation_and_suspension")


def test_admin_and_merchant_tokens_are_revocable(admin: dict, admin_id: int) -> None:
    assert client.get("/api/v2/admin/reports", headers=admin).status_code == 200
    db = Session()
    db.get(models.Admin, admin_id).hashed_password = security.get_password_hash("Changed-pass-1234")
    db.commit()
    assert client.get("/api/v2/admin/reports", headers=admin).status_code == 401, "a password reset signs out"
    _, victim = _register("victim")
    assert client.delete(f"/api/v1/users/{victim}", headers=admin).status_code == 401, "nor can it erase players"
    ghost = {"Authorization": f"Bearer {security.create_access_token({'sub': '987654', 'role': 'merchant'})}"}
    assert client.post("/api/v1/bounties", headers=ghost, json={}).status_code in (401, 422)
    r = client.post("/api/v1/bounties", headers=ghost, json={
        "title": "t", "description": "d", "bounty_type": "merchant_chest", "merchant_id": 987654,
        "target_lat": 1, "target_lng": 1})
    assert r.status_code == 401, "a deleted merchant's token is refused"
    db.get(models.Admin, admin_id).hashed_password = security.get_password_hash("Admin-pass-1234")
    db.commit()
    db.close()
    print("PASS test_admin_and_merchant_tokens_are_revocable")


def test_merchant_bounty_economy_is_capped() -> None:
    db = Session()
    m = models.Merchant(name="Cafe", email="sec_merchant@example.com",
                        hashed_password=security.get_password_hash("Merchant-pass-1"), is_active=True,
                        payment_status="payment_successful")
    db.add(m)
    db.commit()
    mid = m.id
    db.close()
    login = client.post("/api/v1/auth/login", json={"email": "sec_merchant@example.com", "password": "Merchant-pass-1",
                                                    "device_timestamp": "2026-11-16T00:00:00+00:00"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    base = {"title": "Chest", "description": "Visit us", "bounty_type": "merchant_chest", "merchant_id": mid,
            "target_lat": 44.6, "target_lng": -63.6}
    for extra in ({"crystal_reward": 10**9}, {"crystal_reward": 100}, {"radius_m": 1e7}, {"xp_reward": 10**6},
                  {"max_completions": 10**6}, {"title": "x" * 500}):
        r = client.post("/api/v1/bounties", headers=headers, json={**base, **extra})
        assert r.status_code == 422, (extra, r.text)
    r = client.post("/api/v1/bounties", headers=headers, json={**base, "crystal_reward": 10, "radius_m": 50})
    assert r.status_code == 200, r.text
    print("PASS test_merchant_bounty_economy_is_capped")


def test_feed_posts_do_not_trust_client_numbers(player: dict, other_uid: int) -> None:
    db = Session()
    run = models.RunSession(user_id=other_uid, status="finished", verification_status="accepted", distance_m=5000)
    db.add(run)
    db.commit()
    run_id = run.id
    db.close()
    r = client.post("/api/v2/feed/posts", headers=player, json={"kind": "run", "related_run_id": run_id})
    assert r.status_code == 404, "another player's run cannot be attached"
    r = client.post("/api/v2/feed/posts", headers=player, json={
        "kind": "workout", "xp_earned": 99999, "crystals_earned": 99999, "distance_m": 42195, "streak_days": 999,
        "media_url": "https://tracker.example/pixel.gif"})
    assert r.status_code == 201, r.text
    summary = r.json()["summary"]
    assert summary["xp_earned"] == 0 and summary["crystals_earned"] == 0 and summary["distance_m"] == 0
    assert summary["streak_days"] != 999 and r.json().get("media_url") is None, r.text
    print("PASS test_feed_posts_do_not_trust_client_numbers")


def test_new_join_codes_are_long(player: dict, uid: int) -> None:
    db = Session()
    db.add(models.RunSession(user_id=uid, status="finished", verification_status="accepted", distance_m=3000))
    db.commit()
    db.close()
    r = client.post("/api/v2/communities", headers=player, json={"name": "Secret Club", "kind": "running_club",
                                                                 "visibility": "private"})
    assert r.status_code == 201, r.text
    assert len(r.json()["join_code"]) == 10, r.json()["join_code"]
    print("PASS test_new_join_codes_are_long")


def test_secret_checking_endpoints_are_rate_limited() -> None:
    def deps(path: str, method: str) -> set:
        route = next(r for r in main.app.routes if getattr(r, "path", None) == path and method in r.methods)
        return {d.call for d in route.dependant.dependencies}
    assert _rl_password in deps("/api/v2/me/password", "POST")
    assert _rl_password in deps("/api/v2/me/erase", "POST")
    assert _rl_join in deps("/api/v2/communities/{slug}/join", "POST")
    assert _rl_onboard in deps("/api/v1/merchants/register", "POST")
    assert _rl_social in deps("/api/v2/feed/posts", "POST")
    print("PASS test_secret_checking_endpoints_are_rate_limited")


def test_erasure_anonymises_store_tokens_and_keeps_them_claimed() -> None:
    headers, uid = _register("buyer")
    db = Session()
    db.add(models.GooglePlayPurchase(user_id=uid, purchase_token="play-token-abc", product_id="osiris_founder_pack",
                                     kind="non_consumable", state="owned", order_id="GPA.1234"))
    db.add(models.AppStorePurchase(user_id=uid, transaction_id="2000000123", product_id="osiris_founder_pack",
                                   kind="non_consumable", state="owned", order_id="2000000123", environment="Sandbox"))
    db.commit()
    db.close()
    r = client.post("/api/v2/me/erase", headers=headers, json={"password": PASSWORD, "confirm": "DELETE"})
    assert r.status_code == 202, r.text
    db = Session()
    play = db.query(models.GooglePlayPurchase).filter(models.GooglePlayPurchase.user_id == uid).one()
    apple = db.query(models.AppStorePurchase).filter(models.AppStorePurchase.user_id == uid).one()
    assert play.purchase_token.startswith("erased:") and play.order_id is None
    assert apple.transaction_id.startswith("erased:") and apple.order_id is None
    db.close()
    other, _ = _register("reuser")
    r = client.post("/api/v2/payments/google-play/verify", headers=other,
                    json={"product_id": "osiris_founder_pack", "purchase_token": "play-token-abc"})
    assert r.status_code == 409, "an erased account's purchase is never granted again: " + r.text
    page = client.get("/account-deletion").text
    assert "does not cancel" in page
    print("PASS test_erasure_anonymises_store_tokens_and_keeps_them_claimed")


def test_security_headers() -> None:
    for path in ("/healthz", "/privacy"):
        h = client.get(path).headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY", path
        assert h["referrer-policy"] == "no-referrer" and "frame-ancestors 'none'" in h["content-security-policy"], path
    print("PASS test_security_headers")


def test_support_websocket_goes_through_the_origin_lock() -> None:
    guarded = TestClient(OriginGuardMiddleware(main.app, secret="origin-secret"))
    try:
        with guarded.websocket_connect("/api/v2/support/ws"):
            refused = False
    except WebSocketDisconnect:
        refused = True
    assert refused
    print("PASS test_support_websocket_goes_through_the_origin_lock")


def _boot(env: dict, code: str = "import main") -> subprocess.CompletedProcess:
    base = {k: v for k, v in os.environ.items() if not k.startswith(("OSIRIS_", "PYTHON_DOTENV"))}
    base.update({"PYTHON_DOTENV_DISABLED": "1", "OSIRIS_WEBHOOK_SECRET": "w" * 40, **env})
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=base, capture_output=True, text=True)


def test_production_boot_checks_and_closed_docs() -> None:
    prod = {"OSIRIS_ENV": "production", "OSIRIS_JWT_SECRET": "j" * 48, "OSIRIS_ORIGIN_SECRET": "o" * 32}
    short = _boot({**prod, "OSIRIS_JWT_SECRET": "short"})
    assert short.returncode != 0 and "OSIRIS_JWT_SECRET" in short.stderr, short.stderr[-500:]
    unknown_env = _boot({"OSIRIS_ENV": "prod"})
    assert unknown_env.returncode != 0 and "OSIRIS_JWT_SECRET" in unknown_env.stderr, "an unknown env fails closed"
    no_lock = _boot({k: v for k, v in prod.items() if k != "OSIRIS_ORIGIN_SECRET"})
    assert no_lock.returncode != 0 and "OSIRIS_ORIGIN_SECRET" in no_lock.stderr, no_lock.stderr[-500:]
    ok = _boot(prod, "import main; assert main.app.docs_url is None and main.app.redoc_url is None "
                     "and main.app.openapi_url is None and main.app.openapi()['paths']")
    assert ok.returncode == 0, ok.stderr[-800:]
    print("PASS test_production_boot_checks_and_closed_docs")


if __name__ == "__main__":
    player, player_id = _register("eve")
    _, other_id = _register("mallory")
    admin, admin_id = _admin()
    test_sql_injection_payloads_are_inert(player, admin)
    test_login_and_signup_do_not_enumerate()
    test_v1_account_endpoints_honour_revocation_and_suspension()
    test_admin_and_merchant_tokens_are_revocable(admin, admin_id)
    test_merchant_bounty_economy_is_capped()
    test_feed_posts_do_not_trust_client_numbers(player, other_id)
    test_new_join_codes_are_long(player, player_id)
    test_secret_checking_endpoints_are_rate_limited()
    test_erasure_anonymises_store_tokens_and_keeps_them_claimed()
    test_security_headers()
    test_support_websocket_goes_through_the_origin_lock()
    test_production_boot_checks_and_closed_docs()
