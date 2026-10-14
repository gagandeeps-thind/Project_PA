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
                db.query(models.ChallengeAttempt).filter(models.ChallengeAttempt.run_session_id.in_(run_ids)).delete(synchronize_session=False)
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


def _finished_run(client: TestClient, headers: dict, key: str) -> int:
    run_id = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now()}).json()["id"]
    client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _now()})
    client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": [
        {"sequence": i, "t_ms": i * 30_000, "lat": 44.6 + i * 0.0005, "lng": -63.6, "accuracy_m": 10} for i in range(4)
    ]})
    response = client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _now(), "idempotency_key": f"run-release-retention-{key}"})
    assert response.status_code == 200, response.text
    return run_id


def test_raw_route_points_expire_after_retention_window() -> None:
    """Security plan §2: raw telemetry is kept only as long as needed. Summaries stay."""
    from datetime import timedelta
    _cleanup()
    client = TestClient(main.app)
    headers = {"Authorization": f"Bearer {_login(client)}"}
    old_run = _finished_run(client, headers, "old")
    recent_run = _finished_run(client, headers, "recent")
    in_review = _finished_run(client, headers, "review")
    db = database.SessionLocal()
    try:
        long_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=main.ROUTE_POINT_RETENTION_DAYS + 5)
        for rid in (old_run, in_review):
            db.query(models.RunSession).filter(models.RunSession.id == rid).update({"finished_at": long_ago})
        # Evidence for an attempt still awaiting a human reviewer must survive.
        db.add(models.ChallengeAttempt(challenge_id=0, user_id=0, status="review_required", terms_hash="x",
                                       run_session_id=in_review))
        db.commit()

        main.process_route_point_ttl()

        db.expire_all()
        def points(rid: int) -> int:
            return db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id == rid).count()

        assert points(old_run) == 0, "raw points of an old closed run are deleted"
        assert points(recent_run) == 4, "recent runs keep their points"
        assert points(in_review) == 4, "runs under review keep their evidence"
        summary = db.query(models.RunSession).filter(models.RunSession.id == old_run).first()
        assert summary.verification_status == "accepted" and summary.distance_m > 100 and summary.point_count == 4
        assert db.query(models.VerificationDecision).filter(
            models.VerificationDecision.run_session_id == old_run).count() == 1
    finally:
        db.close()


def test_metrics_count_requests_and_verification_outcomes() -> None:
    from services import metrics
    _cleanup()
    metrics.reset()
    client = TestClient(main.app)
    headers = {"Authorization": f"Bearer {_login(client)}"}
    good = _finished_run(client, headers, "metrics-ok")
    bad = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now()}).json()["id"]
    client.post(f"/api/v2/runs/{bad}/start", headers=headers, json={"device_started_at": _now()})
    client.post(f"/api/v2/runs/{bad}/points", headers=headers, json={"points": [
        {"sequence": i, "t_ms": i * 1_000, "lat": 44.6 + i * 0.1, "lng": -63.6, "accuracy_m": 10} for i in range(3)]})
    client.post(f"/api/v2/runs/{bad}/finish", headers=headers, json={
        "device_finished_at": _now(), "idempotency_key": "run-release-metrics-bad"})

    response = client.get("/metrics")  # test env: no token configured, served in dev/test only
    assert response.status_code == 200, response.text
    body = response.text
    assert 'route="/api/v2/runs/{run_id}/finish"' in body
    assert f"/api/v2/runs/{good}/" not in body, "raw ids must never become labels"
    assert 'osiris_run_verifications_total{status="accepted"} 1' in body
    assert 'osiris_run_verifications_total{status="rejected"} 1' in body
    assert 'osiris_run_rejection_reasons_total{reason="IMPOSSIBLE_SPEED"} 1' in body
    assert 'osiris_http_request_duration_seconds_bucket{method="POST",route="/api/v2/runs/{run_id}/points",le="+Inf"}' in body


if __name__ == "__main__":
    for test in (
        test_metrics_count_requests_and_verification_outcomes,
        test_valid_run_is_verified_and_finish_is_idempotent,
        test_invalid_route_is_rejected_with_reason_codes,
        test_route_sequence_and_authentication_are_enforced,
        test_raw_route_points_expire_after_retention_window,
    ):
        test()
        print(f"PASS {test.__name__}")
    _cleanup()
