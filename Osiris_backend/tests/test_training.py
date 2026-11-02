"""Start tab: training sessions, results, progress, quotes, connections and group challenges.

Run directly from the backend directory:
    python tests/test_training.py
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "training-test-secret-aaaaaaaaaaaaaaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import growth_api  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from core import security  # noqa: E402

PREFIX = "training_test_"
PASSWORD = "TrainingTest1!"
ADMIN_EMAIL = PREFIX + "admin@example.com"

client = TestClient(main.app)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup() -> None:
    db = database.SessionLocal()
    try:
        ids = [u.id for u in db.query(models.User).filter(models.User.email.like(PREFIX + "%")).all()]
        if ids:
            db.query(models.SocialPost).filter(models.SocialPost.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.UserFollow).filter(
                models.UserFollow.follower_id.in_(ids) | models.UserFollow.followed_id.in_(ids)
            ).delete(synchronize_session=False)
            db.query(models.PlayerNotification).filter(models.PlayerNotification.user_id.in_(ids)).delete(
                synchronize_session=False)
            growth_api.delete_growth_data(db, ids)
            db.query(models.ActivityLog).filter(models.ActivityLog.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.AuditEvent).filter(
                (models.AuditEvent.actor_type == "player") & models.AuditEvent.actor_id.in_(ids)
                | ((models.AuditEvent.entity_type == "user") & models.AuditEvent.entity_id.in_(ids))
            ).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_(ids)).delete(synchronize_session=False)
        official = db.query(models.GroupChallenge).filter(models.GroupChallenge.title.like(PREFIX + "%")).all()
        for ch in official:
            db.query(models.GroupChallengeMember).filter(models.GroupChallengeMember.challenge_id == ch.id).delete(
                synchronize_session=False)
            db.delete(ch)
        db.query(models.Admin).filter(models.Admin.email == ADMIN_EMAIL).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _player(name: str) -> tuple[dict, int]:
    email = f"{PREFIX}{name}@example.com"
    r = client.post("/api/v1/onboard", json={
        "email": email, "password": PASSWORD, "weight_kg": 70, "height_m": 1.75,
        "preferred_path": "Cardio", "device_timestamp": _now(),
    })
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "device_timestamp": _now()})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["id"]


def _admin() -> dict:
    db = database.SessionLocal()
    try:
        admin = db.query(models.Admin).filter(models.Admin.email == ADMIN_EMAIL).first()
        if admin is None:
            admin = models.Admin(email=ADMIN_EMAIL, hashed_password="x", name="Training Admin")
            db.add(admin)
            db.commit()
        admin_id = admin.id
    finally:
        db.close()
    return {"Authorization": f"Bearer {security.create_access_token({'sub': str(admin_id), 'role': 'admin'})}"}


def _upload(headers, activity="run", mode="train", distance=3000.0, duration=1200.0, series=None, **extra):
    body = {
        "client_session_id": extra.pop("client_session_id", str(uuid.uuid4())),
        "activity_key": activity, "mode": mode, "source": extra.pop("source", "sensor"),
        "started_at": extra.pop("started_at", _now()), "duration_s": duration, "distance_m": distance,
        "series": series or {}, "devices": [],
    }
    body.update(extra)
    return client.post("/api/v2/training/sessions", json=body, headers=headers)


def _exercise_session(user_id: int, reps: int) -> int:
    db = database.SessionLocal()
    try:
        row = models.ExerciseSession(
            user_id=user_id, client_session_id=f"{PREFIX}{uuid.uuid4()}", exercise_key="pushup", rules_version="test",
            duration_s=45.0, reps_attempted=reps, reps_valid=reps, client_verdict="pass", status="verified",
            local_date=datetime.now().date().isoformat(),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _follow(headers, target_id):
    r = client.post(f"/api/v2/osirians/{target_id}/follow", headers=headers)
    assert r.status_code == 200, r.text


# --- training sessions ---------------------------------------------------------------

def test_catalog() -> None:
    headers, _ = _player("catalog")
    r = client.get("/api/v2/training/activities", headers=headers)
    assert r.status_code == 200, r.text
    by_key = {a["key"]: a for a in r.json()}
    assert by_key["pushup"]["kind"] == "camera" and by_key["pushup"]["metric"] == "reps"
    assert by_key["run"]["kind"] == "gps" and by_key["run"]["gps"] is True
    assert by_key["indoor_cycle"]["gps"] is False
    print("PASS test_catalog")


def test_upload_stats_server_side() -> None:
    headers, _ = _player("stats")
    series = {
        "hr": [[0, 100], [10, 140], [20, 999]],
        "elevation": [[0, 100], [5, 103], [10, 102], [15, 106]],
        "power": [[0, -5], [5, 200]],
    }
    r = _upload(headers, series=series, hr_avg=50, hr_max=250)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["hr_max"] == 140 and s["hr_min"] == 100 and s["hr_avg"] == 120, s
    assert s["elevation_gain_m"] == 7.0, s
    assert s["power_min"] == 200 and s["power_max"] == 200, s
    print("PASS test_upload_stats_server_side")


def test_upload_without_series() -> None:
    headers, _ = _player("noseries")
    r = _upload(headers, activity="strength", distance=0.0, duration=900.0)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["hr_avg"] is None and s["duration_s"] == 900.0 and s["elevation_gain_m"] == 0.0, s
    print("PASS test_upload_without_series")


def test_implausible_speed_and_bad_input() -> None:
    headers, _ = _player("cheat")
    assert _upload(headers, distance=10_000.0, duration=60.0).status_code == 422
    assert _upload(headers, activity="teleport").status_code == 422
    assert _upload(headers, mode="ranked").status_code == 422
    print("PASS test_implausible_speed_and_bad_input")


def test_upload_idempotent() -> None:
    headers, _ = _player("idem")
    cid = str(uuid.uuid4())
    a = _upload(headers, client_session_id=cid)
    b = _upload(headers, client_session_id=cid)
    assert a.status_code == 201 and b.status_code == 201, (a.text, b.text)
    assert a.json()["id"] == b.json()["id"]
    items = client.get("/api/v2/me/training/sessions", headers=headers).json()["items"]
    assert len(items) == 1
    print("PASS test_upload_idempotent")


def test_camera_link() -> None:
    headers, uid = _player("camera")
    _, other = _player("camera_other")
    foreign = _exercise_session(other, 20)
    r = _upload(headers, activity="pushup", distance=0.0, duration=30.0, source="camera", exercise_session_id=foreign)
    assert r.status_code == 403, r.text
    mine = _exercise_session(uid, 18)
    r = _upload(headers, activity="pushup", distance=0.0, duration=999.0, source="camera",
                exercise_session_id=mine, reps=500)
    assert r.status_code == 201, r.text
    assert r.json()["reps"] == 18 and r.json()["duration_s"] == 45.0, r.json()
    # A camera activity without its verified set is refused.
    assert _upload(headers, activity="pushup", distance=0.0, duration=30.0, source="camera").status_code == 422
    print("PASS test_camera_link")


def test_pr_and_segments() -> None:
    headers, _ = _player("pr")
    first = _upload(headers, distance=3000.0)
    assert first.json()["is_pr"] is True
    second = _upload(headers, mode="challenge", distance=5000.0, duration=1800.0)
    assert second.json()["is_pr"] is True
    third = _upload(headers, distance=4000.0)
    assert third.json()["is_pr"] is False
    s = client.get("/api/v2/me/training/summary", params={"activity": "run"}, headers=headers).json()
    assert s["pr"]["value"] == 5000.0 and s["pr"]["unit"] == "m" and s["pr"]["session_id"] == second.json()["id"], s
    assert s["segments"] == {"workouts": 2, "challenges": 1}, s
    assert s["total_distance_m"] == 12000.0 and s["week_sessions"] == 3, s
    assert s["latest"]["id"] == third.json()["id"] and "series" in s["latest"], s
    empty = client.get("/api/v2/me/training/summary", params={"activity": "yoga"}, headers=headers).json()
    assert empty["pr"] is None and empty["latest"] is None and empty["segments"] == {"workouts": 0, "challenges": 0}
    print("PASS test_pr_and_segments")


def test_list_detail_and_foreign_404() -> None:
    headers, _ = _player("list")
    other, _ = _player("list_other")
    sid = _upload(headers, series={"hr": [[0, 120], [5, 130]]}).json()["id"]
    _upload(headers, activity="walk", distance=1000.0)
    runs = client.get("/api/v2/me/training/sessions", params={"activity": "run"}, headers=headers).json()["items"]
    assert [s["id"] for s in runs] == [sid] and runs[0].get("series") is None
    detail = client.get(f"/api/v2/me/training/sessions/{sid}", headers=headers).json()
    assert detail["series"]["hr"] == [[0.0, 120.0], [5.0, 130.0]], detail
    assert client.get(f"/api/v2/me/training/sessions/{sid}", headers=other).status_code == 404
    print("PASS test_list_detail_and_foreign_404")


def test_progress_weeks() -> None:
    headers, _ = _player("progress")
    _upload(headers, duration=600.0)
    _upload(headers, activity="walk", distance=500.0, duration=300.0)
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    _upload(headers, duration=999.0, started_at=old)
    weeks = client.get("/api/v2/me/training/progress", params={"weeks": 8}, headers=headers).json()["weeks"]
    assert len(weeks) == 8
    current = weeks[-1]
    assert current["duration_s"] == 900.0 and current["sessions"] == 2, current
    assert current["by_activity"] == {"run": 600.0, "walk": 300.0}, current
    assert sum(w["sessions"] for w in weeks) == 2
    print("PASS test_progress_weeks")


def test_post_idempotent() -> None:
    headers, _ = _player("post")
    other, _ = _player("post_other")
    sid = _upload(headers).json()["id"]
    assert client.post(f"/api/v2/training/sessions/{sid}/post", json={"caption": ""}, headers=other).status_code == 404
    a = client.post(f"/api/v2/training/sessions/{sid}/post", json={"caption": "Morning run"}, headers=headers)
    b = client.post(f"/api/v2/training/sessions/{sid}/post", json={"caption": "again"}, headers=headers)
    assert a.status_code == 201 and b.status_code == 201, (a.text, b.text)
    assert a.json()["id"] == b.json()["id"] and a.json()["caption"] == "Morning run"
    assert client.get(f"/api/v2/me/training/sessions/{sid}", headers=headers).json()["posted"] is True
    print("PASS test_post_idempotent")


def test_quote_exclude() -> None:
    headers, _ = _player("quote")
    first = client.get("/api/v2/motivation/quote", headers=headers).json()
    assert first["text"] and "id" in first
    for _ in range(20):
        q = client.get("/api/v2/motivation/quote", params={"exclude": first["id"]}, headers=headers).json()
        assert q["id"] != first["id"]
    print("PASS test_quote_exclude")


def test_connections() -> None:
    me, my_id = _player("conn")
    fan, fan_id = _player("conn_fan")
    _, idol_id = _player("conn_idol")
    _, stranger_id = _player("conn_stranger")
    _follow(fan, my_id)
    _follow(me, idol_id)
    ids = {c["user_id"] for c in client.get("/api/v2/me/connections", headers=me).json()}
    assert ids == {fan_id, idol_id}, ids
    assert stranger_id not in ids
    print("PASS test_connections")


TESTS = [
    test_catalog,
    test_upload_stats_server_side,
    test_upload_without_series,
    test_implausible_speed_and_bad_input,
    test_upload_idempotent,
    test_camera_link,
    test_pr_and_segments,
    test_list_detail_and_foreign_404,
    test_progress_weeks,
    test_post_idempotent,
    test_quote_exclude,
    test_connections,
]


if __name__ == "__main__":
    _cleanup()
    try:
        for test in TESTS:
            test()
    finally:
        _cleanup()
    print("ALL TRAINING TESTS PASSED")
