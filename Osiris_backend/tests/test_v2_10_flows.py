"""Regression tests for v2.10 backend flows.

No pytest dependency — run directly:

    cd Osiris_backend
    python tests/test_v2_10_flows.py

Covers:
  - Telemetry persistence: a domain claim with a full proof envelope produces one
    TelemetrySession + per-sensor TelemetryData rows.
  - Replay-attack guard: re-submitting the same proof key returns 409.
  - DoS cap: ActivityProof with > 20000 samples per channel is rejected at validation.
  - RBAC matrix: /users/{id} self-only for players; /platform/revenue admin-only.

Tests run against the real `fitness_mvp.db` and clean up their own fixtures (no leaks).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND_DIR)

import bcrypt
from datetime import datetime, timezone
from fastapi.testclient import TestClient

import database
import models
import main


# --- Test infrastructure ---

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


SMOKE_EMAIL_PREFIX = "v210test_"
SMOKE_DOMAIN = "@osirisseed.com"


def _cleanup() -> None:
    """Delete all rows created by tests in this file. Idempotent."""
    db = database.SessionLocal()
    try:
        # Find user IDs to cascade through dependent tables.
        user_ids = [u.id for u in db.query(models.User).filter(models.User.email.like(f"{SMOKE_EMAIL_PREFIX}%{SMOKE_DOMAIN}")).all()]
        if user_ids:
            session_ids = [s.id for s in db.query(models.TelemetrySession).filter(models.TelemetrySession.user_id.in_(user_ids)).all()]
            if session_ids:
                db.query(models.TelemetryData).filter(models.TelemetryData.session_id.in_(session_ids)).delete(synchronize_session=False)
            db.query(models.TelemetrySession).filter(models.TelemetrySession.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(models.ActivityLog).filter(models.ActivityLog.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(models.ProofConsumed).filter(models.ProofConsumed.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(models.Domain).filter(models.Domain.owner_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_(user_ids)).delete(synchronize_session=False)
        db.query(models.Admin).filter(models.Admin.email.like(f"{SMOKE_EMAIL_PREFIX}%{SMOKE_DOMAIN}")).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _onboard_player(client, suffix: str, password: str = "PlayerTest1!") -> tuple[int, str]:
    """Returns (player_id, jwt_token)."""
    email = f"{SMOKE_EMAIL_PREFIX}{suffix}{SMOKE_DOMAIN}"
    r = client.post("/api/v1/onboard", json={
        "email": email, "password": password,
        "weight_kg": 75, "height_m": 1.8, "preferred_path": "Strength",
        "device_timestamp": _now().isoformat(),
    })
    assert r.status_code == 200, f"onboard failed: {r.status_code} {r.text}"
    pid = r.json()["id"]
    r = client.post("/api/v1/auth/login", json={
        "email": email, "password": password, "device_timestamp": _now().isoformat(),
    })
    assert r.status_code == 200
    return pid, r.json()["access_token"]


def _seed_admin(suffix: str, password: str = "AdminTest1!") -> str:
    """Creates an Admin row directly (no API for admin registration). Returns email."""
    email = f"{SMOKE_EMAIL_PREFIX}{suffix}{SMOKE_DOMAIN}"
    db = database.SessionLocal()
    try:
        existing = db.query(models.Admin).filter(models.Admin.email == email).first()
        if existing:
            existing.hashed_password = _hash(password)
        else:
            db.add(models.Admin(email=email, hashed_password=_hash(password), name="TestAdmin"))
        db.commit()
    finally:
        db.close()
    return email


def _build_pushup_proof(score: int = 30, duration_s: float = 30.0) -> dict:
    """Synthetic ActivityProof matching the smoke fixture used in v2.10 dev work —
    cadence ~1 Hz, ROM 90°, plausible score."""
    accel = [
        {"t_ms": i * 100, "ax": 0.0, "ay": 0.0, "az": 9.8 + (5.0 if (i % 10) in (4, 5) else 0.0)}
        for i in range(int(duration_s * 10))
    ]
    return {
        "activity_type": "pushups",
        "declared_score": score,
        "duration_seconds": duration_s,
        "accelerometer": accel,
        "gyroscope": [],
        "magnetometer": [],
        "gps": [],
        "barometer": [],
        "pose": {"rep_count": score, "min_joint_angle_deg": 80, "max_joint_angle_deg": 170},
        "device_timestamp": _now().isoformat(),
    }


def _build_domain(player_id: int, proof: dict) -> dict:
    ts = _now().isoformat()
    return {
        "owner_id": player_id,
        "device_timestamp": ts,
        "defense_score": proof["declared_score"],
        "defense_type": proof["activity_type"],
        "coordinates": [
            {"lat": 43.500, "lng": -80.500, "timestamp": ts},
            {"lat": 43.501, "lng": -80.500, "timestamp": ts},
            {"lat": 43.501, "lng": -80.501, "timestamp": ts},
            {"lat": 43.500, "lng": -80.501, "timestamp": ts},
            {"lat": 43.500, "lng": -80.500, "timestamp": ts},
        ],
        "defense_proof": proof,
    }


# --- Tests ---

@case("Telemetry persistence: domain claim with proof writes TelemetrySession + TelemetryData")
def test_telemetry_persistence():
    client = TestClient(main.app)
    pid, token = _onboard_player(client, "telp")

    proof = _build_pushup_proof()
    r = client.post("/api/v1/domains", json=_build_domain(pid, proof),
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"domain submit failed: {r.status_code} {r.text}"

    db = database.SessionLocal()
    try:
        sess = db.query(models.TelemetrySession).filter(models.TelemetrySession.user_id == pid).first()
        assert sess is not None, "no TelemetrySession row created"
        assert sess.activity_type == "pushups"
        assert sess.declared_score == 30
        assert sess.sample_count_accel == 300, f"expected 300 accel samples, got {sess.sample_count_accel}"
        assert sess.has_pose, "pose flag should be set"
        assert sess.activity_log_id is not None, "must link back to ActivityLog"

        data_rows = db.query(models.TelemetryData).filter(models.TelemetryData.session_id == sess.id).all()
        sensor_types = sorted(d.sensor_type for d in data_rows)
        assert sensor_types == ["accel", "pose"], f"expected only accel+pose channels populated, got {sensor_types}"
    finally:
        db.close()


@case("Replay-attack guard: re-submitting same proof key 409s on second call")
def test_replay_attack_guard():
    client = TestClient(main.app)
    pid, token = _onboard_player(client, "replay")

    proof = _build_pushup_proof(score=25)
    payload = _build_domain(pid, proof)

    r1 = client.post("/api/v1/domains", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 200, f"first submit must succeed: {r1.status_code} {r1.text}"

    # Second submit with the SAME proof — guard should fire.
    r2 = client.post("/api/v1/domains", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 409, f"replay should 409, got {r2.status_code}: {r2.text}"
    assert "already" in r2.json().get("detail", "").lower()


@case("DoS cap: > 20000 accelerometer samples is rejected at Pydantic validation")
def test_dos_cap_accelerometer():
    client = TestClient(main.app)
    pid, token = _onboard_player(client, "doscap")

    # Build a payload that overflows the per-channel cap by one.
    OVERFLOW = main.MAX_SAMPLES_PER_CHANNEL + 1
    proof = _build_pushup_proof()
    proof["accelerometer"] = [{"t_ms": i, "ax": 0.0, "ay": 0.0, "az": 9.8} for i in range(OVERFLOW)]

    r = client.post("/api/v1/domains", json=_build_domain(pid, proof),
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422, f"expected 422 from Pydantic length validator, got {r.status_code}: {r.text}"


@case("RBAC: player cannot fetch another player's profile (403)")
def test_rbac_player_other_profile():
    client = TestClient(main.app)
    pid_a, token_a = _onboard_player(client, "rbac_a")
    pid_b, _ = _onboard_player(client, "rbac_b")
    assert pid_a != pid_b

    r = client.get(f"/api/v1/users/{pid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 403, f"expected 403, got {r.status_code}"


@case("RBAC: player CAN fetch own profile (200)")
def test_rbac_player_own_profile():
    client = TestClient(main.app)
    pid, token = _onboard_player(client, "rbac_self")
    r = client.get(f"/api/v1/users/{pid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


@case("RBAC: player cannot read /platform/revenue (403)")
def test_rbac_platform_revenue_player():
    client = TestClient(main.app)
    _, token = _onboard_player(client, "rev_pl")
    r = client.get("/api/v1/platform/revenue", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, f"player should 403 on /platform/revenue, got {r.status_code}"


@case("RBAC: admin CAN read /platform/revenue (200)")
def test_rbac_platform_revenue_admin():
    client = TestClient(main.app)
    email = _seed_admin("rev_ad")
    r = client.post("/api/v1/auth/login", json={
        "email": email, "password": "AdminTest1!", "device_timestamp": _now().isoformat(),
    })
    assert r.status_code == 200
    admin_token = r.json()["access_token"]

    r = client.get("/api/v1/platform/revenue", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, f"admin should 200 on /platform/revenue, got {r.status_code}: {r.text}"


# --- Runner ---

def main_runner() -> None:
    _cleanup()  # start clean
    failed = 0
    try:
        for name, fn in CASES:
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"  FAIL  {name}\n        {e}")
            except Exception as e:
                failed += 1
                print(f"  ERROR {name}\n        {type(e).__name__}: {e}")
    finally:
        _cleanup()
    print()
    print(f"{len(CASES) - failed} / {len(CASES)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main_runner()
