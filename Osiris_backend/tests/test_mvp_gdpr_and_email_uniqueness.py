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

    # 5. Delete account (GDPR Erasure)
    del_resp = client.delete(f"/api/v1/users/{user_id}", headers=headers)
    _check("GDPR account deletion returns 200", del_resp.status_code == 200)

    # Verify user is gone from DB
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    _check("User row removed from database", db_user is None)

    db.close()

if __name__ == "__main__":
    test_gdpr_and_email_uniqueness()
    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} check(s) FAILED: {_FAILURES}")
        sys.exit(1)
    print("All GDPR & Email Uniqueness checks passed.")
