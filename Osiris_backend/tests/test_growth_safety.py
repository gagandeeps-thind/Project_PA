"""Growth G4 regression tests: consent, reports and the abuse queue, blocking, session
revocation, password change, data export, and erasure.

Run directly from the backend directory:
    python tests/test_growth_safety.py
"""
import math
import os
import sys
import time
from datetime import datetime, timezone

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "growth-safety-test-secret-aaaaaaaaaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi.testclient import TestClient

import database
import main
import growth_api
import models


PREFIX = "growth_g4_test_"
PASSWORD = "SafetyTest1!"
ADMIN_EMAIL = PREFIX + "admin@example.com"
M_PER_DEG_LAT = 111_195.0
BASE = (45.5000, -64.5000)

client = TestClient(main.app)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _north(origin, metres):
    return (origin[0] + metres / M_PER_DEG_LAT, origin[1])


def _path(a, b, speed_mps=3.0, step_s=10):
    dist = (b[0] - a[0]) * M_PER_DEG_LAT
    n = max(1, math.ceil(dist / (speed_mps * step_s)))
    return [(a[0] + (b[0] - a[0]) * i / n, a[1], int(dist / n / speed_mps * i * 1000)) for i in range(n + 1)]


def cleanup() -> None:
    db = database.SessionLocal()
    try:
        ids = [u.id for u in db.query(models.User).filter(
            models.User.email.like(PREFIX + "%") | models.User.email.like("deleted-%@deleted.invalid")).all()]
        if ids:
            ch_ids = [c.id for c in db.query(models.Challenge).filter(models.Challenge.creator_id.in_(ids)).all()] or [-1]
            db.query(models.Report).filter(
                (models.Report.target_type == "challenge") & models.Report.target_id.in_(ch_ids)
                | (models.Report.target_type == "user") & models.Report.target_id.in_(ids)
                | models.Report.reporter_id.in_(ids)
            ).delete(synchronize_session=False)
            growth_api.delete_growth_data(db, ids)
            db.query(models.ChallengeAttempt).filter(
                models.ChallengeAttempt.user_id.in_(ids) | models.ChallengeAttempt.challenge_id.in_(ch_ids)
            ).delete(synchronize_session=False)
            db.query(models.Challenge).filter(models.Challenge.id.in_(ch_ids)).delete(synchronize_session=False)
            db.query(models.Course).filter(models.Course.owner_id.in_(ids)).delete(synchronize_session=False)
            run_ids = [r.id for r in db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).all()] or [-1]
            db.query(models.VerificationDecision).filter(models.VerificationDecision.run_session_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(models.AuditEvent).filter(
                ((models.AuditEvent.actor_type == "player") & models.AuditEvent.actor_id.in_(ids))
                | ((models.AuditEvent.entity_type == "user") & models.AuditEvent.entity_id.in_(ids))
                | ((models.AuditEvent.entity_type == "run_session") & models.AuditEvent.entity_id.in_(run_ids))
                | ((models.AuditEvent.entity_type == "challenge") & models.AuditEvent.entity_id.in_(ch_ids))
            ).delete(synchronize_session=False)
            db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.ActivityLog).filter(models.ActivityLog.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.UserBadge).filter(models.UserBadge.user_id.in_(ids)).delete(synchronize_session=False)
            # Ledger rows must go too: SQLite reuses freed user ids, so orphans would be inherited.
            db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_(ids)).delete(synchronize_session=False)
        db.query(models.Admin).filter(models.Admin.email == ADMIN_EMAIL).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _register(name, consent=True):
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}{name}@example.com", "password": PASSWORD, "display_name": name.title(),
        "goal": "running", "location_consent": consent,
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["profile"]


def _run(headers, start, metres, key):
    pts = _path(start, _north(start, metres))
    r = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now()})
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _now()})
    client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": [
        {"sequence": i, "t_ms": t, "lat": lat, "lng": lng, "accuracy_m": 5} for i, (lat, lng, t) in enumerate(pts)
    ]})
    r = client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _now(), "idempotency_key": f"{PREFIX}{key}",
    })
    assert r.status_code == 200 and r.json()["verification_status"] == "accepted", r.text
    return r.json()


def _challenge(headers, key):
    run = _run(headers, BASE, 1500, f"course-{key}")
    course = client.post("/api/v2/courses", headers=headers, json={"run_id": run["id"], "name": f"Route {key}"})
    assert course.status_code == 201, course.text
    r = client.post("/api/v2/challenges", headers=headers, json={
        "course_id": course.json()["id"], "title": f"Route {key}", "window_hours": 24,
        "idempotency_key": PREFIX + key})
    assert r.status_code == 201, r.text
    return r.json()


def _admin() -> dict:
    db = database.SessionLocal()
    try:
        admin = models.Admin(email=ADMIN_EMAIL, hashed_password="x", name="G4 Admin")
        db.add(admin)
        db.commit()
        admin_id = admin.id
    finally:
        db.close()
    return {"Authorization": f"Bearer {main.create_access_token({'sub': str(admin_id), 'role': 'admin'})}"}


def test_location_consent_gates_runs_and_is_recorded() -> None:
    cleanup()
    headers, profile = _register("noconsent", consent=False)
    assert client.get("/api/v2/me/today", headers=headers).json()["needs_location_consent"]
    r = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now()})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "LOCATION_CONSENT_REQUIRED"
    client.put("/api/v2/me/profile", headers=headers, json={"location_consent": True})
    assert client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now()}).status_code == 201
    client.put("/api/v2/me/profile", headers=headers, json={"location_consent": False, "leaderboard_opt_in": True})
    consents = client.get("/api/v2/me/export", headers=headers).json()["consents"]
    assert sorted((c["kind"], c["granted"]) for c in consents) == sorted([
        ("location", True), ("location", False), ("leaderboard", True)])


def test_reports_abuse_queue_and_unsafe_route_auto_pause() -> None:
    cleanup()
    admin = _admin()
    owner, owner_profile = _register("routeowner")
    ch = _challenge(owner, "unsafe")
    reporters = [_register(f"rep{i}")[0] for i in range(3)]
    body = {"target_type": "challenge", "target_id": ch["id"], "reason": "unsafe_route",
            "details": "No sidewalk on the highway section"}
    first = client.post("/api/v2/reports", headers=reporters[0], json=body)
    assert first.status_code == 201, first.text
    again = client.post("/api/v2/reports", headers=reporters[0], json=body)
    assert again.json()["id"] == first.json()["id"]
    client.post("/api/v2/reports", headers=reporters[1], json=body)
    assert client.get(f"/api/v2/challenges/{ch['id']}", headers=owner).json()["status"] == "open"
    third = client.post("/api/v2/reports", headers=reporters[2], json=body)
    assert "paused" in third.json()["message"]
    assert client.get(f"/api/v2/challenges/{ch['id']}", headers=owner).json()["status"] == "suspended"

    bad = client.post("/api/v2/reports", headers=owner, json={
        "target_type": "user", "target_ref": owner_profile["referral_code"], "reason": "spam"})
    assert bad.status_code == 422
    assert client.post("/api/v2/reports", headers=owner, json=dict(body, reason="vibes")).status_code == 422

    assert client.get("/api/v2/admin/reports", headers=owner).status_code == 403
    queue = client.get("/api/v2/admin/reports", headers=admin).json()
    mine = [q for q in queue if q["target_type"] == "challenge" and q["target_id"] == ch["id"]]
    assert len(mine) == 3 and mine[0]["open_reports_on_target"] == 3 and "Route unsafe" in mine[0]["target_summary"]
    r = client.post(f"/api/v2/admin/reports/{mine[0]['id']}/resolve", headers=admin,
                    json={"status": "actioned", "note": "Route pulled; highway section unsafe"})
    assert r.json()["resolved"] == 3
    status = client.get("/api/v2/me/reports", headers=reporters[1]).json()[0]
    assert status["status"] == "actioned" and "highway" in status["message"]


def test_blocking_hides_and_prevents_joining() -> None:
    cleanup()
    creator, _ = _register("creator")
    ch = _challenge(creator, "block")
    blocker, _ = _register("blocker")
    _run(blocker, (BASE[0], BASE[1] + 0.01), 1200, "blocker-1")
    near = client.get("/api/v2/challenges/nearby", headers=blocker, params={"lat": BASE[0], "lng": BASE[1]}).json()
    assert any(c["id"] == ch["id"] for c in near)
    r = client.post("/api/v2/blocks", headers=blocker, json={"challenge_id": ch["id"]})
    assert r.status_code == 201 and r.json()["name"].startswith("Blocked runner")
    near = client.get("/api/v2/challenges/nearby", headers=blocker, params={"lat": BASE[0], "lng": BASE[1]}).json()
    assert all(c["id"] != ch["id"] for c in near)
    today = client.get("/api/v2/me/today", headers=blocker, params={"lat": BASE[0], "lng": BASE[1]}).json()
    assert today["starter_challenge"] is None or today["starter_challenge"]["id"] != ch["id"]
    r = client.post(f"/api/v2/challenges/{ch['id']}/join", headers=blocker)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "BLOCKED"
    assert client.post("/api/v2/blocks", headers=blocker, json={"challenge_id": 10**9}).status_code == 404
    block_id = client.get("/api/v2/me/blocks", headers=blocker).json()[0]["id"]
    assert client.delete(f"/api/v2/blocks/{block_id}", headers=creator).status_code == 404
    assert client.delete(f"/api/v2/blocks/{block_id}", headers=blocker).status_code == 204
    assert client.post(f"/api/v2/challenges/{ch['id']}/join", headers=blocker).status_code == 200


def test_sign_out_everywhere_and_password_change() -> None:
    cleanup()
    old, _ = _register("sessions")
    time.sleep(1.1)   # iat has one-second resolution
    r = client.post("/api/v2/me/sessions/revoke", headers=old)
    assert r.status_code == 200
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.get("/api/v2/me/profile", headers=old)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "SESSION_REVOKED"
    assert client.get("/api/v2/me/profile", headers=fresh).status_code == 200

    time.sleep(1.1)
    bad = client.post("/api/v2/me/password", headers=fresh, json={"current_password": "nope", "new_password": "NewPass123!"})
    assert bad.status_code == 403
    r = client.post("/api/v2/me/password", headers=fresh, json={"current_password": PASSWORD, "new_password": "NewPass123!"})
    assert r.status_code == 200
    assert client.get("/api/v2/me/profile", headers=fresh).status_code == 401
    login = client.post("/api/v1/auth/login", json={
        "email": f"{PREFIX}sessions@example.com", "password": "NewPass123!", "device_timestamp": _now()})
    assert login.status_code == 200


def test_export_and_erase() -> None:
    cleanup()
    headers, profile = _register("eraseme")
    ch = _challenge(headers, "erase")
    rival, _ = _register("rival")
    _run(rival, (BASE[0], BASE[1] + 0.02), 1200, "rival-1")
    assert client.post(f"/api/v2/challenges/{ch['id']}/join", headers=rival).status_code == 200

    export = client.get("/api/v2/me/export", headers=headers).json()
    assert export["account"]["email"] == f"{PREFIX}eraseme@example.com"
    assert export["runs"] and export["runs"][0]["route_points"] and export["courses"][0]["route"]

    assert client.post("/api/v2/me/erase", headers=headers, json={"password": PASSWORD, "confirm": "yes"}).status_code == 422
    assert client.post("/api/v2/me/erase", headers=headers, json={"password": "bad", "confirm": "DELETE"}).status_code == 403
    r = client.post("/api/v2/me/erase", headers=headers, json={"password": PASSWORD, "confirm": "DELETE"})
    assert r.status_code == 202, r.text
    assert client.get("/api/v2/me/profile", headers=headers).status_code in (401, 403)
    login = client.post("/api/v1/auth/login", json={
        "email": f"{PREFIX}eraseme@example.com", "password": PASSWORD, "device_timestamp": _now()})
    assert login.status_code == 401

    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == profile["user_id"]).first()
        assert user.email.endswith("@deleted.invalid") and user.suspended_at is not None
        runs = [r.id for r in db.query(models.RunSession).filter(models.RunSession.user_id == user.id)]
        assert db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id.in_(runs)).count() == 0
        course = db.query(models.Course).filter(models.Course.owner_id == user.id).first()
        assert course.route_json == "[]" and course.status == "retired"
        assert db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == user.id).first() is None
        # The rival's attempt still exists and refers to a still-valid challenge.
        attempt = db.query(models.ChallengeAttempt).filter(models.ChallengeAttempt.challenge_id == ch["id"]).first()
        assert attempt is not None
        challenge = db.query(models.Challenge).filter(models.Challenge.id == ch["id"]).first()
        assert challenge.closes_at <= main._now_naive_utc()
    finally:
        db.close()


def test_rules_are_public_and_honest() -> None:
    r = client.get("/api/v2/rules")
    assert r.status_code == 200
    text = str(r.json()).lower()
    assert "no cash value" in text and "nothing to refund" in text and "not ai" in text


if __name__ == "__main__":
    for test in (
        test_location_consent_gates_runs_and_is_recorded,
        test_reports_abuse_queue_and_unsafe_route_auto_pause,
        test_blocking_hides_and_prevents_joining,
        test_sign_out_everywhere_and_password_change,
        test_export_and_erase,
        test_rules_are_public_and_honest,
    ):
        test()
        print(f"PASS {test.__name__}")
    cleanup()
