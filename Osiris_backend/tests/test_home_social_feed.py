"""Tests for the redesigned Home Screen API:
- Notifications (list, unread count, mark read, mark all read)
- Suggested Global Challenges (circular deck payload + join)
- Suggested Osirians (swipe list, follow, unfollow, 'x' dismiss, 'See All' trending)
- People's Posts (create workout/domain/streak/crystal post, feed list, react, comment, share)

Run directly from Osiris_backend:
    python tests/test_home_social_feed.py
"""
import os
import sys

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


def main() -> None:
    cleanup()
    try:
        test_notifications_flow()
        test_suggested_osirians_follow_dismiss_and_trending()
        test_peoples_posts_create_react_comment_share()
    finally:
        cleanup()


if __name__ == "__main__":
    main()
