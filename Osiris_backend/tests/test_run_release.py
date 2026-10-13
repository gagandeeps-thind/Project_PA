"""First-release running-loop regression tests.

Run directly from the backend directory:
    python tests/test_run_release.py
"""
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "run-release-test-secret-aaaaaaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi.testclient import TestClient

import database
import growth_api
import main
import models


EMAIL = "run_release_test@example.com"
PASSWORD = "RunReleaseTest1!"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup() -> None:
    db = database.SessionLocal()
    try:
        users = db.query(models.User).filter(models.User.email == EMAIL).all()
        ids = [user.id for user in users]
        if ids:
            runs = db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).all()
            run_ids = [run.id for run in runs]
            if run_ids:
                db.query(models.VerificationDecision).filter(models.VerificationDecision.run_session_id.in_(run_ids)).delete(synchronize_session=False)
                db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.ActivityLog).filter(models.ActivityLog.user_id.in_(ids)).delete(synchronize_session=False)
            growth_api.delete_growth_data(db, ids)
            # Ledger rows must go too: SQLite reuses freed user ids, so orphans would be inherited.
            db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _login(client: TestClient) -> str:
    response = client.post("/api/v1/onboard", json={
        "email": EMAIL,
        "password": PASSWORD,
        "weight_kg": 75,
        "height_m": 1.8,
        "preferred_path": "Cardio",
        "device_timestamp": _now(),
    })
    assert response.status_code == 200, response.text
    response = client.post("/api/v1/auth/login", json={
        "email": EMAIL,
        "password": PASSWORD,
        "device_timestamp": _now(),
    })
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_valid_run_is_verified_and_finish_is_idempotent() -> None:
    _cleanup()
    client = TestClient(main.app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/v2/runs", headers=headers, json={
        "activity_type": "run", "device_started_at": _now(),
    })
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    assert client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _now()}).status_code == 200

    points = []
    for sequence in range(4):
        points.append({
            "sequence": sequence,
            "t_ms": sequence * 30_000,
            "lat": 44.6000 + sequence * 0.0005,
            "lng": -63.6000,
            "accuracy_m": 10,
        })
    response = client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": points})
    assert response.status_code == 200, response.text
    response = client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _now(), "idempotency_key": "run-release-finish-001",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "closed"
    assert body["verification_status"] == "accepted"
    assert body["distance_m"] > 100
    assert body["xp_awarded"] >= 10

    duplicate = client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _now(), "idempotency_key": "run-release-finish-001",
    })
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["route_hash"] == body["route_hash"]


def test_invalid_route_is_rejected_with_reason_codes() -> None:
    _cleanup()
    client = TestClient(main.app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now()}).json()["id"]
    client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _now()})
    points = [
        {"sequence": 0, "t_ms": 0, "lat": 44.6000, "lng": -63.6000, "accuracy_m": 10},
        {"sequence": 1, "t_ms": 1_000, "lat": 44.7000, "lng": -63.6000, "accuracy_m": 10},
        {"sequence": 2, "t_ms": 2_000, "lat": 44.8000, "lng": -63.6000, "accuracy_m": 10},
    ]
    assert client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": points}).status_code == 200
    response = client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _now(), "idempotency_key": "run-release-finish-002",
    })
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == "rejected"
    assert "IMPOSSIBLE_SPEED" in response.json()["rejection_reason"]


def test_route_sequence_and_authentication_are_enforced() -> None:
    _cleanup()
    client = TestClient(main.app)
    assert client.post("/api/v2/runs", json={"device_started_at": _now()}).status_code == 401
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    run_id = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now()}).json()["id"]
    client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _now()})
    response = client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": [
        {"sequence": 1, "t_ms": 0, "lat": 44.6, "lng": -63.6},
    ]})
    assert response.status_code == 409


if __name__ == "__main__":
    for test in (
        test_valid_run_is_verified_and_finish_is_idempotent,
        test_invalid_route_is_rejected_with_reason_codes,
        test_route_sequence_and_authentication_are_enforced,
    ):
        test()
        print(f"PASS {test.__name__}")
    _cleanup()
