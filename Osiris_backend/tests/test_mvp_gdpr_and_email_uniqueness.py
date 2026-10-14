"""Regression suite for GDPR endpoints and Cross-Table Email Uniqueness.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND)

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "test-jwt-secret-gdpr-12345678901234567890")
os.environ.setdefault("OSIRIS_WEBHOOK_SECRET", "test-webhook-secret-gdpr-1234567890")

_FAILURES = []

def _check(name, cond):
    status = "PASS" if cond else "FAIL"
    print(f"  {status}  {name}")
    if not cond:
        _FAILURES.append(name)

def test_gdpr_and_email_uniqueness():
    from fastapi.testclient import TestClient
    import main
    import models
    import database

    client = TestClient(main.app)
    db = database.SessionLocal()

    test_email = "gdpr_unique_test@osirisseed.com"
    
    # Cleanup previous test runs. Ledger rows go first: SQLite reuses freed user ids, so
    # orphaned rows would be inherited by the next account.
    stale_ids = [u.id for u in db.query(models.User).filter(models.User.email == test_email).all()]
    db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id.in_(stale_ids)).delete(
        synchronize_session=False)
    db.query(models.User).filter(models.User.email == test_email).delete()
    db.query(models.Merchant).filter(models.Merchant.email == test_email).delete()
    db.commit()

    # 1. Register player account
    onboard_payload = {
        "email": test_email,
        "password": "password123",
        "weight_kg": 75.0,
        "height_m": 1.80,
        "preferred_path": "Strength",
        "device_timestamp": "2026-06-12T10:00:00Z"
    }
    r1 = client.post("/api/v1/onboard", json=onboard_payload)
    _check("Player onboarding succeeds", r1.status_code == 200)
    user_id = r1.json()["id"]

    # 2. Attempt registering merchant with same email -> must fail (400)
    merchant_payload = {
        "name": "Collision Gym",
        "email": test_email,
        "password": "password123",
        "business_type": "gym"
    }
    r2 = client.post("/api/v1/merchants/register", json=merchant_payload)
    _check("Cross-table email collision rejected with 400", r2.status_code == 400)

    # 3. Log in as player to obtain JWT
    login_resp = client.post("/api/v1/auth/login", json={
        "email": test_email,
        "password": "password123",
        "device_timestamp": "2026-06-12T10:05:00Z"
    })
    _check("Player login succeeds", login_resp.status_code == 200)
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 4. Export data (GDPR Portability)
    export_resp = client.get(f"/api/v1/users/{user_id}/export", headers=headers)
    _check("GDPR data export returns 200", export_resp.status_code == 200)
    _check("Export contains user_profile", "user_profile" in export_resp.json())

    # 5. Record a run so the account owns raw GPS evidence.
    now = "2026-06-12T10:10:00Z"
    run_id = client.post("/api/v2/runs", headers=headers, json={"device_started_at": now}).json()["id"]
    client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": now})
    client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": [
        {"sequence": i, "t_ms": i * 30_000, "lat": 44.6 + i * 0.0005, "lng": -63.6, "accuracy_m": 10}
        for i in range(4)
    ]})
    points_before = db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id == run_id).count()
    _check("Run recorded route points before deletion", points_before == 4)

    # 6. Delete account (GDPR Erasure)
    del_resp = client.delete(f"/api/v1/users/{user_id}", headers=headers)
    _check("GDPR account deletion returns 200", del_resp.status_code == 200)

    # Personal data is erased, but the row stays as an anonymous tombstone so the id is never
    # reused and the financial ledger is retained (PRD-009).
    db.expire_all()
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    _check("User row kept as an anonymous tombstone", db_user is not None and db_user.email != test_email)
    _check("Route points erased", db.query(models.RoutePoint).filter(
        models.RoutePoint.run_session_id == run_id).count() == 0)
    ledger_sum = sum(r.delta for r in db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id == user_id))
    _check("Crystal ledger retained and still reconciles", db_user is not None and
           ledger_sum == db_user.mana_crystals and ledger_sum > 0)
    relogin = client.post("/api/v1/auth/login", json={
        "email": test_email, "password": "password123", "device_timestamp": now})
    _check("Deleted account can no longer log in", relogin.status_code == 401)

    # Test hygiene only: hard-delete the tombstone so repeated runs do not accumulate rows.
    import growth_api
    run_ids = [r.id for r in db.query(models.RunSession).filter(models.RunSession.user_id == user_id)]
    db.query(models.VerificationDecision).filter(models.VerificationDecision.run_session_id.in_(run_ids)).delete(
        synchronize_session=False)
    db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id.in_(run_ids)).delete(
        synchronize_session=False)
    db.query(models.RunSession).filter(models.RunSession.user_id == user_id).delete(synchronize_session=False)
    db.query(models.AuditEvent).filter(models.AuditEvent.actor_id == user_id).delete(synchronize_session=False)
    growth_api.delete_growth_data(db, [user_id])
    db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id == user_id).delete(synchronize_session=False)
    db.query(models.User).filter(models.User.id == user_id).delete(synchronize_session=False)
    db.commit()
    db.close()

if __name__ == "__main__":
    test_gdpr_and_email_uniqueness()
    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} check(s) FAILED: {_FAILURES}")
        sys.exit(1)
    print("All GDPR & Email Uniqueness checks passed.")
