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
IDS: dict[str, int] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup() -> None:
    db = database.SessionLocal()
    try:
        ids = [u.id for u in db.query(models.User).filter(models.User.email.like(PREFIX + "%")).all()]
        if ids:
            db.query(models.SocialPost).filter(models.SocialPost.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.Challenge).filter(models.Challenge.creator_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.Course).filter(models.Course.owner_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).delete(synchronize_session=False)
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
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    IDS[headers["Authorization"]] = r.json()["id"]
    return headers, r.json()["id"]


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


def _exercise_session(user_id: int, reps: int) -> str:
    """A camera set as the exercise upload stores it; returns its client session id."""
    db = database.SessionLocal()
    try:
        cid = f"{PREFIX}{uuid.uuid4()}"
        db.add(models.ExerciseSession(
            user_id=user_id, client_session_id=cid, exercise_key="pushup", rules_version="test",
            duration_s=45.0, reps_attempted=reps, reps_valid=reps, client_verdict="pass", status="verified",
            local_date=datetime.now().date().isoformat(),
        ))
        db.commit()
        return cid
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
    # Another player's set, even with a known client id, is not found for this player.
    foreign = _exercise_session(other, 20)
    r = _upload(headers, activity="pushup", distance=0.0, duration=30.0, source="camera",
                exercise_client_session_id=foreign)
    assert r.status_code == 404, r.text
    mine = _exercise_session(uid, 18)
    r = _upload(headers, activity="pushup", distance=0.0, duration=999.0, source="camera",
                exercise_client_session_id=mine, reps=500)
    assert r.status_code == 201, r.text
    assert r.json()["reps"] == 18 and r.json()["duration_s"] == 45.0, r.json()
    # The same set cannot back a second session.
    again = _upload(headers, activity="pushup", distance=0.0, duration=30.0, source="camera",
                    exercise_client_session_id=mine)
    assert again.status_code == 409, again.text
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


# --- group challenges ------------------------------------------------------------------

def _group(headers, invitees=(), title=PREFIX + "Weekend 20k", activity="run", metric="distance_m", target=20000.0,
           days=7):
    return client.post("/api/v2/group-challenges", headers=headers, json={
        "title": title, "activity_key": activity, "metric": metric, "target": target, "days": days,
        "invitee_ids": list(invitees),
    })


def _set_window(challenge_id: int, starts: datetime, ends: datetime) -> None:
    db = database.SessionLocal()
    try:
        ch = db.query(models.GroupChallenge).filter(models.GroupChallenge.id == challenge_id).first()
        ch.starts_at, ch.ends_at = starts.replace(tzinfo=None), ends.replace(tzinfo=None)
        db.commit()
    finally:
        db.close()


def test_group_create_and_invites() -> None:
    owner, _ = _player("g_owner")
    friend, friend_id = _player("g_friend")
    _, stranger_id = _player("g_stranger")
    _follow(friend, _me_id(owner))
    assert _group(owner, invitees=[stranger_id]).status_code == 422
    assert _group(owner, activity="teleport").status_code == 422
    r = _group(owner, invitees=[friend_id])
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["my_status"] == "joined" and g["members"] == 1 and g["status"] == "active", g
    assert g["created_by_me"] is True
    assert client.get(f"/api/v2/group-challenges/{g['id']}", headers=friend).json()["created_by_me"] is False
    lists = client.get("/api/v2/group-challenges", headers=friend).json()
    assert [c["id"] for c in lists["invited"]] == [g["id"]], lists
    notes = client.get("/api/v2/me/notifications", headers=friend).json()
    assert any(n["kind"] == "group_challenge_invite" for n in notes["items"]), notes
    print("PASS test_group_create_and_invites")


def _me_id(headers) -> int:
    return IDS[headers["Authorization"]]


def test_group_visibility() -> None:
    owner, owner_id = _player("v_owner")
    fan, _ = _player("v_fan")
    stranger, _ = _player("v_stranger")
    _follow(fan, owner_id)
    gid = _group(owner).json()["id"]
    assert client.get(f"/api/v2/group-challenges/{gid}", headers=stranger).status_code == 404
    assert client.post(f"/api/v2/group-challenges/{gid}/join", headers=stranger).status_code == 404
    assert gid not in [c["id"] for c in client.get("/api/v2/group-challenges", headers=stranger).json()["connections"]]
    assert gid in [c["id"] for c in client.get("/api/v2/group-challenges", headers=fan).json()["connections"]]
    assert client.get(f"/api/v2/group-challenges/{gid}", headers=fan).status_code == 200
    r = client.post(f"/api/v2/group-challenges/{gid}/join", headers=fan)
    assert r.status_code == 200 and r.json()["my_status"] == "joined" and r.json()["members"] == 2, r.text
    mine = client.get("/api/v2/group-challenges", headers=fan).json()
    assert gid in [c["id"] for c in mine["mine"]] and gid not in [c["id"] for c in mine["connections"]]
    print("PASS test_group_visibility")


def test_group_join_rules() -> None:
    owner, owner_id = _player("j_owner")
    fan, _ = _player("j_fan")
    _follow(fan, owner_id)
    assert client.post(f"/api/v2/group-challenges/{_group(owner).json()['id']}/leave", headers=owner).status_code == 409
    ended = _group(owner).json()["id"]
    past = datetime.now(timezone.utc) - timedelta(days=10)
    _set_window(ended, past, past + timedelta(days=2))
    assert client.post(f"/api/v2/group-challenges/{ended}/join", headers=fan).status_code == 409
    assert client.get(f"/api/v2/group-challenges/{ended}", headers=fan).json()["status"] == "ended"
    cancelled = _group(owner).json()["id"]
    assert client.post(f"/api/v2/group-challenges/{cancelled}/cancel", headers=fan).status_code in (403, 404)
    assert client.post(f"/api/v2/group-challenges/{cancelled}/cancel", headers=owner).status_code == 200
    assert client.post(f"/api/v2/group-challenges/{cancelled}/join", headers=fan).status_code == 409
    open_id = _group(owner).json()["id"]
    assert client.post(f"/api/v2/group-challenges/{open_id}/join", headers=fan).status_code == 200
    r = client.post(f"/api/v2/group-challenges/{open_id}/leave", headers=fan)
    assert r.status_code == 200 and r.json()["my_status"] is None and r.json()["members"] == 1, r.text
    print("PASS test_group_join_rules")


def test_group_progress_challenge_mode_only() -> None:
    owner, _ = _player("p_owner")
    gid = _group(owner).json()["id"]
    _upload(owner, mode="train", distance=4000.0)
    _upload(owner, mode="challenge", activity="walk", distance=1000.0)
    _upload(owner, mode="challenge", distance=3000.0)
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _upload(owner, mode="challenge", distance=2000.0, started_at=old)
    g = client.get(f"/api/v2/group-challenges/{gid}", headers=owner).json()
    assert g["my_progress"] == 3000.0, g
    print("PASS test_group_progress_challenge_mode_only")


def test_group_leaderboard_order() -> None:
    owner, owner_id = _player("l_owner")
    a, _ = _player("l_a")
    b, _ = _player("l_b")
    _follow(a, owner_id)
    _follow(b, owner_id)
    gid = _group(owner, metric="sessions", target=5).json()["id"]
    for h in (a, b):
        client.post(f"/api/v2/group-challenges/{gid}/join", headers=h)
    _upload(a, mode="challenge")
    for _ in range(2):
        _upload(b, mode="challenge")
    board = client.get(f"/api/v2/group-challenges/{gid}", headers=owner).json()["leaderboard"]
    assert [m["progress"] for m in board] == [2.0, 1.0, 0.0], board
    assert board[0]["user_id"] == _me_id(b)
    print("PASS test_group_leaderboard_order")


def test_official_admin() -> None:
    player, _ = _player("o_player")
    body = {"title": PREFIX + "Osiris 100 push-ups", "activity_key": "pushup", "metric": "reps", "target": 100, "days": 14}
    assert client.post("/api/v2/admin/group-challenges", json=body).status_code == 401
    assert client.post("/api/v2/admin/group-challenges", json=body, headers=player).status_code == 403
    r = client.post("/api/v2/admin/group-challenges", json=body, headers=_admin())
    assert r.status_code == 201 and r.json()["is_official"] is True, r.text
    gid = r.json()["id"]
    assert gid in [c["id"] for c in client.get("/api/v2/group-challenges", headers=player).json()["official"]]
    assert client.post(f"/api/v2/group-challenges/{gid}/join", headers=player).status_code == 200
    assert gid in [c["id"] for c in client.get("/api/v2/admin/group-challenges", headers=_admin()).json()]
    # The admin console fills its activity picker from the same catalog.
    assert client.get("/api/v2/training/activities", headers=_admin()).status_code == 200
    print("PASS test_official_admin")


def _open_challenge(owner_id: int, title: str) -> int:
    """A minimal open course challenge, as publishing one would leave it."""
    db = database.SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        run = models.RunSession(user_id=owner_id, status="finished")
        db.add(run)
        db.flush()
        course = models.Course(
            owner_id=owner_id, source_run_session_id=run.id, rules_version="test", name=title, distance_m=1500.0,
            benchmark_seconds=480.0, start_lat=45.0, start_lng=-66.0, finish_lat=45.01, finish_lng=-66.0,
            route_json="[]", route_hash=f"{PREFIX}{uuid.uuid4()}", public_lat=45.0, public_lng=-66.0,
        )
        db.add(course)
        db.flush()
        ch = models.Challenge(
            course_id=course.id, creator_id=owner_id, title=title, rules_version="test", course_version=1,
            target_seconds=480.0, win_xp=40, participation_xp=10, opens_at=now, closes_at=now + timedelta(days=2),
            terms_hash="test",
        )
        db.add(ch)
        db.commit()
        return ch.id
    finally:
        db.close()


def test_suggested_challenges_with_open_challenges() -> None:
    """The Challenge page's suggested grid; it failed whenever any challenge was open."""
    host, host_id = _player("s_host")
    viewer, _ = _player("s_viewer")
    cid = _open_challenge(host_id, PREFIX + "Riverside mile")
    r = client.get("/api/v2/challenges/suggested", params={"limit": 30}, headers=viewer)
    assert r.status_code == 200, r.text
    card = next(c for c in r.json() if c["id"] == cid)
    assert card["joined"] is False and card["course_distance_m"] == 1500.0
    print("PASS test_suggested_challenges_with_open_challenges")


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
    test_group_create_and_invites,
    test_group_visibility,
    test_group_join_rules,
    test_group_progress_challenge_mode_only,
    test_group_leaderboard_order,
    test_official_admin,
    test_suggested_challenges_with_open_challenges,
]


if __name__ == "__main__":
    _cleanup()
    try:
        for test in TESTS:
            test()
    finally:
        _cleanup()
    print("ALL TRAINING TESTS PASSED")
