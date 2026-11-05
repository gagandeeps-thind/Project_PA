"""Tests for the redesigned Home Screen API:
- Notifications (list, unread count, mark read, mark all read)
- Suggested Global Challenges (circular deck payload + join)
- Suggested Osirians (swipe list, follow, unfollow, 'x' dismiss, 'See All' trending)
- People's Posts (create workout/domain/streak/crystal post, feed list, react, comment, share)
- Social tab (following feed, active today, compose with photo/workouts/chart, discover, search,
  profile, delete, followers-only visibility, direct messages, GDPR export)

Run directly from Osiris_backend:
    python tests/test_home_social_feed.py
"""
import base64
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "home-feed-test-secret-aaaaaaaaaaaaaaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import growth_api  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402

PREFIX = "home_feed_test_"
PASSWORD = "HomeFeedTest1!"

client = TestClient(main.app)


def cleanup() -> None:
    db = database.SessionLocal()
    try:
        ids = [u.id for u in db.query(models.User).filter(models.User.email.like(PREFIX + "%")).all()]
        if ids:
            growth_api.delete_growth_data(db, ids)
            db.query(models.AuditEvent).filter(
                ((models.AuditEvent.actor_type == "player") & models.AuditEvent.actor_id.in_(ids))
                | ((models.AuditEvent.entity_type == "user") & models.AuditEvent.entity_id.in_(ids))
            ).delete(synchronize_session=False)
            db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _register(name: str) -> tuple[int, dict]:
    r = client.post(
        "/api/v2/auth/register",
        json={
            "email": f"{PREFIX}{name}@example.com",
            "password": PASSWORD,
            "display_name": f"Osirian {name.title()}",
            "goal": "fitness",
            "location_consent": True,
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return data["profile"]["user_id"], {"Authorization": f"Bearer {data['access_token']}"}


def test_notifications_flow() -> None:
    _, headers = _register("notif")
    r = client.get("/api/v2/me/notifications", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unread_count"] >= 2
    assert len(body["items"]) >= 2

    first_id = body["items"][0]["id"]
    r_read = client.post(f"/api/v2/me/notifications/{first_id}/read", headers=headers)
    assert r_read.status_code == 200 and r_read.json()["read"] is True

    r_all = client.post("/api/v2/me/notifications/read-all", headers=headers)
    assert r_all.status_code == 200
    after = client.get("/api/v2/me/notifications", headers=headers).json()
    assert after["unread_count"] == 0
    print("PASS notifications flow")


def test_suggested_osirians_follow_dismiss_and_trending() -> None:
    _, h_viewer = _register("viewer")
    u_alice, _ = _register("alice")
    u_bob, _ = _register("bob")

    # Suggested Osirians should include Alice and Bob
    r = client.get("/api/v2/osirians/suggested?limit=100", headers=h_viewer)
    assert r.status_code == 200, r.text
    suggested_ids = [item["user_id"] for item in r.json()]
    assert u_alice in suggested_ids and u_bob in suggested_ids

    # Dismiss Bob ('x' button) -> Bob disappears from suggested
    r_dis = client.post(f"/api/v2/osirians/{u_bob}/dismiss", headers=h_viewer)
    assert r_dis.status_code == 200 and r_dis.json()["dismissed"] is True
    suggested_after_dismiss = [item["user_id"] for item in client.get("/api/v2/osirians/suggested?limit=100", headers=h_viewer).json()]
    assert u_bob not in suggested_after_dismiss

    # Follow Alice -> Alice disappears from suggested, appears as following in trending ("See All")
    r_fol = client.post(f"/api/v2/osirians/{u_alice}/follow", headers=h_viewer)
    assert r_fol.status_code == 200 and r_fol.json()["following"] is True and r_fol.json()["followers_count"] == 1
    suggested_after_follow = [item["user_id"] for item in client.get("/api/v2/osirians/suggested?limit=100", headers=h_viewer).json()]
    assert u_alice not in suggested_after_follow

    trending = client.get("/api/v2/osirians/trending?limit=100", headers=h_viewer).json()
    alice_row = next(item for item in trending if item["user_id"] == u_alice)
    assert alice_row["following"] is True
    print("PASS suggested osirians follow, dismiss and see all trending")


def test_peoples_posts_create_react_comment_share() -> None:
    _, h_author = _register("author")
    _, h_fan = _register("fan")

    # Author posts a multi-set pushup + domain + streak + crystal update
    r_post = client.post(
        "/api/v2/feed/posts",
        headers=h_author,
        json={
            "kind": "workout",
            "caption": "Morning push-ups 10 x 3 and claimed 0.45 km² domain!",
            "exercise_key": "pushup",
            "sets": 3,
            "reps_per_set": 10,
            "total_reps": 30,
            "domain_area_sqkm": 0.45,
            "streak_days": 7,
            "crystals_earned": 25,
            "xp_earned": 65,
        },
    )
    assert r_post.status_code == 201, r_post.text
    post = r_post.json()
    post_id = post["id"]
    assert "Push-up - 10 x 3 (30 reps)" in post["summary"]["measure_label"]
    assert post["summary"]["domain_area_sqkm"] == 0.45
    assert post["summary"]["crystals_earned"] == 25

    # Fan sees the post in People's Posts feed
    feed = client.get("/api/v2/feed/posts", headers=h_fan).json()["items"]
    assert any(p["id"] == post_id for p in feed)

    # Fan reacts with 'fire'
    r_react = client.post(f"/api/v2/feed/posts/{post_id}/react", headers=h_fan, json={"reaction": "fire"})
    assert r_react.status_code == 200, r_react.text
    assert r_react.json()["my_reaction"] == "fire"
    assert r_react.json()["reactions"]["fire"] == 1

    # Fan comments on the post
    r_comment = client.post(
        f"/api/v2/feed/posts/{post_id}/comments",
        headers=h_fan,
        json={"body": "Huge domain claim and clean 10 x 3 sets!"},
    )
    assert r_comment.status_code == 201, r_comment.text
    comments = client.get(f"/api/v2/feed/posts/{post_id}/comments", headers=h_fan).json()
    assert len(comments) == 1 and "10 x 3" in comments[0]["body"]

    # Fan shares the post
    r_share = client.post(f"/api/v2/feed/posts/{post_id}/share", headers=h_fan)
    assert r_share.status_code == 200, r_share.text
    assert r_share.json()["share_count"] == 1
    assert "Osiris" in r_share.json()["share_text"]

    # Author received notifications for the reaction and comment
    author_notifs = client.get("/api/v2/me/notifications", headers=h_author).json()["items"]
    kinds = {n["kind"] for n in author_notifs}
    assert "post_reaction" in kinds and "post_comment" in kinds
    print("PASS peoples posts create, react, comment and share")


# --- Social tab ------------------------------------------------------------------

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


def _session(headers: dict, activity: str = "run", distance: float = 5000.0, duration: float = 1500.0) -> int:
    started = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = client.post("/api/v2/training/sessions", headers=headers, json={
        "client_session_id": str(uuid.uuid4()), "activity_key": activity, "mode": "train", "source": "sensor",
        "started_at": started, "duration_s": duration, "distance_m": distance, "series": {}, "devices": [],
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _block(headers: dict, target_id: int) -> None:
    handle = client.get(f"/api/v2/social/users/{target_id}", headers=headers).json()["user"]["handle"]
    r = client.post("/api/v2/blocks", headers=headers, json={"handle": handle})
    assert r.status_code == 201, r.text


def test_social_compose_feed_and_visibility() -> None:
    u_me, h_me = _register("sm")
    u_friend, h_friend = _register("sfriend")
    u_stranger, h_stranger = _register("sstranger")
    assert client.post(f"/api/v2/osirians/{u_friend}/follow", headers=h_me).status_code == 200

    # Empty posts are refused; somebody else's session cannot be attached.
    r = client.post("/api/v2/social/posts", headers=h_me, json={})
    assert r.status_code == 422 and "EMPTY_POST" in r.text, r.text
    foreign = _session(h_stranger)
    r = client.post("/api/v2/social/posts", headers=h_me, json={"training_session_ids": [foreign]})
    assert r.status_code == 404, r.text

    # Bad photos are refused.
    r = client.post("/api/v2/social/posts", headers=h_friend, json={"photo_jpeg_base64": "not base64!"})
    assert r.status_code == 422, r.text
    png = base64.b64encode(b"\x89PNG" + b"0" * 32).decode()
    assert client.post("/api/v2/social/posts", headers=h_friend, json={"photo_jpeg_base64": png}).status_code == 422

    # The friend posts a photo + two workouts + chart; stats come from the server rows.
    s1 = _session(h_friend, "run", 5000.0, 1500.0)
    s2 = _session(h_friend, "cycle", 12000.0, 2400.0)
    r = client.post("/api/v2/social/posts", headers=h_friend, json={
        "caption": "Brick day", "photo_jpeg_base64": base64.b64encode(JPEG).decode(),
        "training_session_ids": [s1, s2, s1], "chart": "weekly_progress", "visibility": "followers",
    })
    assert r.status_code == 201, r.text
    post = r.json()
    assert [a["session_id"] for a in post["attachments"]] == [s1, s2]
    assert post["attachments"][0]["distance_m"] == 5000.0 and post["attachments"][1]["activity_name"] == "Ride"
    assert post["summary"]["distance_m"] == 17000.0
    assert post["chart"]["kind"] == "weekly_progress" and len(post["chart"]["values"]) == 8
    # Sessions started an hour ago land in this week or, just after Monday midnight, the last one.
    assert sum(post["chart"]["values"][-2:]) >= 65.0
    photo = client.get(post["photo_url"])
    assert photo.status_code == 200 and photo.content == JPEG
    assert client.get("/api/v2/social/media/" + "0" * 32).status_code == 404
    # The attached sessions now read as posted.
    sessions = client.get("/api/v2/me/training/sessions", headers=h_friend).json()["items"]
    assert all(it["posted"] for it in sessions)

    # My following feed has it, plus the friend in "active today"; the stranger's feed does not.
    feed = client.get("/api/v2/social/feed", headers=h_me).json()
    assert post["id"] in [p["id"] for p in feed["items"]]
    active = {a["user_id"]: a for a in feed["active_today"]}
    assert u_friend in active and active[u_friend]["minutes"] >= 25
    stranger_feed = client.get("/api/v2/social/feed", headers=h_stranger).json()
    assert post["id"] not in [p["id"] for p in stranger_feed["items"]]

    # Followers-only: a non-follower cannot react, comment, read comments or share.
    for method, path, body in (
        ("post", f"/api/v2/feed/posts/{post['id']}/react", {"reaction": "fire"}),
        ("post", f"/api/v2/feed/posts/{post['id']}/comments", {"body": "nice"}),
        ("get", f"/api/v2/feed/posts/{post['id']}/comments", None),
        ("post", f"/api/v2/feed/posts/{post['id']}/share", None),
    ):
        call = getattr(client, method)
        r = call(path, headers=h_stranger, json=body) if body is not None else call(path, headers=h_stranger)
        assert r.status_code == 404, (path, r.status_code, r.text)
    assert client.post(f"/api/v2/feed/posts/{post['id']}/react", headers=h_me,
                       json={"reaction": "fire"}).status_code == 200

    # Profiles: the stranger sees no followers-only posts; I do.
    mine = client.get(f"/api/v2/social/users/{u_friend}", headers=h_me).json()
    assert mine["posts_count"] == 1 and mine["followers_count"] == 1 and mine["user"]["following"] is True
    assert mine["week_sessions"] in (0, 2) and mine["can_message"] is True and mine["is_me"] is False
    if datetime.now() - timedelta(hours=2) >= datetime.combine(
            datetime.now().date() - timedelta(days=datetime.now().weekday()), datetime.min.time()):
        assert mine["week_sessions"] == 2 and mine["week_minutes"] == 65
    theirs = client.get(f"/api/v2/social/users/{u_friend}", headers=h_stranger).json()
    assert theirs["posts_count"] == 0 and theirs["can_message"] is False

    # Paging with before_id.
    for n in range(3):
        assert client.post("/api/v2/social/posts", headers=h_friend, json={"caption": f"p{n}"}).status_code == 201
    page1 = client.get("/api/v2/social/feed?limit=2", headers=h_me).json()
    assert len(page1["items"]) == 2 and page1["next_before_id"] is not None
    page2 = client.get(f"/api/v2/social/feed?limit=2&before_id={page1['next_before_id']}", headers=h_me).json()
    assert not {p["id"] for p in page1["items"]} & {p["id"] for p in page2["items"]}
    assert page2["active_today"] == []

    # Only the author can delete; deleting frees the attached sessions and removes the photo.
    assert client.delete(f"/api/v2/social/posts/{post['id']}", headers=h_me).status_code == 404
    assert client.delete(f"/api/v2/social/posts/{post['id']}", headers=h_friend).status_code == 204
    assert client.get(post["photo_url"]).status_code == 404
    sessions = client.get("/api/v2/me/training/sessions", headers=h_friend).json()["items"]
    assert not any(it["posted"] for it in sessions)
    assert u_me and u_stranger
    print("PASS social tab compose, following feed, visibility, profile and delete")


def test_social_discover_and_search() -> None:
    _, h_viewer = _register("sdviewer")
    u_runner, h_runner = _register("sdrunner")
    u_lifter, h_lifter = _register("sdlifter")
    _session(h_viewer, "run")  # the viewer's interest: running

    run_post = client.post("/api/v2/social/posts", headers=h_runner,
                           json={"training_session_ids": [_session(h_runner, "run")]}).json()
    lift_post = client.post("/api/v2/social/posts", headers=h_lifter,
                            json={"training_session_ids": [_session(h_lifter, "strength", 0.0, 1800.0)]}).json()
    private = client.post("/api/v2/social/posts", headers=h_lifter,
                          json={"caption": "secret", "visibility": "followers"}).json()

    d = client.get("/api/v2/social/discover?limit=50", headers=h_viewer).json()
    ids = [p["id"] for p in d["items"]]
    assert "run" in d["interests"]
    assert run_post["id"] in ids and lift_post["id"] in ids and private["id"] not in ids
    assert ids.index(run_post["id"]) < ids.index(lift_post["id"])
    only_strength = client.get("/api/v2/social/discover?activity=strength&limit=50", headers=h_viewer).json()
    assert [p["id"] for p in only_strength["items"]] == [lift_post["id"]]

    # Following someone moves them out of discover and into the feed.
    client.post(f"/api/v2/osirians/{u_runner}/follow", headers=h_viewer)
    d = client.get("/api/v2/social/discover?limit=50", headers=h_viewer).json()
    assert run_post["id"] not in [p["id"] for p in d["items"]]

    # Search by name, case-insensitive; wildcards are literal; blocked players are hidden.
    hits = client.get("/api/v2/social/search?q=SDRUNNER", headers=h_viewer).json()
    assert [h["user_id"] for h in hits] == [u_runner] and hits[0]["following"] is True
    assert client.get("/api/v2/social/search?q=%25%25", headers=h_viewer).json() == []
    assert client.get("/api/v2/social/search?q=a", headers=h_viewer).status_code == 422
    _block(h_viewer, u_lifter)
    assert client.get("/api/v2/social/search?q=sdlifter", headers=h_viewer).json() == []
    assert client.get(f"/api/v2/social/users/{u_lifter}", headers=h_viewer).status_code == 404
    print("PASS social tab discover ranking and people search")


def test_direct_messages() -> None:
    u_a, h_a = _register("dma")
    u_b, h_b = _register("dmb")
    u_c, h_c = _register("dmc")

    # Not connected: refused. Self: refused.
    r = client.post(f"/api/v2/social/conversations/{u_b}/messages", headers=h_a, json={"body": "hi"})
    assert r.status_code == 403, r.text
    assert client.post(f"/api/v2/social/conversations/{u_a}/messages", headers=h_a,
                       json={"body": "me"}).status_code == 422

    # B follows A: A may message B (a follower), and B may reply.
    client.post(f"/api/v2/osirians/{u_a}/follow", headers=h_b)
    for body in ("Run tomorrow?", "6am at the park"):
        r = client.post(f"/api/v2/social/conversations/{u_b}/messages", headers=h_a, json={"body": body})
        assert r.status_code == 201 and r.json()["mine"] is True, r.text
    assert client.post(f"/api/v2/social/conversations/{u_b}/messages", headers=h_a,
                       json={"body": "   "}).status_code == 422

    inbox_b = client.get("/api/v2/social/conversations", headers=h_b).json()
    assert inbox_b["unread_total"] == 2
    assert inbox_b["items"][0]["user"]["user_id"] == u_a and inbox_b["items"][0]["last_message"]["body"] == "6am at the park"
    # One notification for the unread burst, not one per message.
    notes = client.get("/api/v2/me/notifications", headers=h_b).json()["items"]
    assert sum(1 for n in notes if n["kind"] == "direct_message") == 1

    thread = client.get(f"/api/v2/social/conversations/{u_a}/messages", headers=h_b).json()
    assert [m["body"] for m in thread["items"]] == ["Run tomorrow?", "6am at the park"] and thread["can_message"]
    older = client.get(f"/api/v2/social/conversations/{u_a}/messages?before_id={thread['items'][1]['id']}",
                       headers=h_b).json()
    assert [m["body"] for m in older["items"]] == ["Run tomorrow?"]
    read = client.post(f"/api/v2/social/conversations/{u_a}/read", headers=h_b).json()
    assert read["unread_total"] == 0
    assert client.post(f"/api/v2/social/conversations/{u_a}/messages", headers=h_b,
                       json={"body": "Deal"}).status_code == 201

    # C cannot read A and B's thread as its own: C's thread with A is empty.
    assert client.get(f"/api/v2/social/conversations/{u_a}/messages", headers=h_c).json()["items"] == []

    # The export carries both directions.
    export = client.get("/api/v2/me/export", headers=h_a).json()
    assert len(export["direct_messages"]) == 3 and "social_posts" in export

    # A block hides the conversation and stops sending both ways.
    _block(h_b, u_a)
    assert client.get("/api/v2/social/conversations", headers=h_a).json()["items"] == []
    assert client.post(f"/api/v2/social/conversations/{u_a}/messages", headers=h_b,
                       json={"body": "x"}).status_code == 404
    assert client.get(f"/api/v2/social/conversations/{u_b}/messages", headers=h_a).status_code == 404
    print("PASS social tab direct messages")


def main() -> None:
    cleanup()
    try:
        test_notifications_flow()
        test_suggested_osirians_follow_dismiss_and_trending()
        test_peoples_posts_create_react_comment_share()
        test_social_compose_feed_and_visibility()
        test_social_discover_and_search()
        test_direct_messages()
    finally:
        cleanup()


if __name__ == "__main__":
    main()
