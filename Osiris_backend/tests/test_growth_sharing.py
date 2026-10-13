"""Growth G2 regression tests: share cards, invite-a-friend challenges, referral rules,
and public achievement pages.

Run directly from the backend directory:
    python tests/test_growth_sharing.py
"""
import math
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "growth-sharing-test-secret-aaaaaaaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi.testclient import TestClient

import database
import main
import growth_api
import models


PREFIX = "growth_g2_test_"
PASSWORD = "SharingTest1!"
M_PER_DEG_LAT = 111_195.0
BASE = (45.1000, -64.1000)

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
        ids = [u.id for u in db.query(models.User).filter(models.User.email.like(PREFIX + "%")).all()]
        if ids:
            ch_ids = [c.id for c in db.query(models.Challenge).filter(models.Challenge.creator_id.in_(ids)).all()] or [-1]
            growth_api.delete_growth_data(db, ids)
            db.query(models.ShareCard).filter(models.ShareCard.challenge_id.in_(ch_ids)).delete(synchronize_session=False)
            db.query(models.ChallengeInvite).filter(models.ChallengeInvite.challenge_id.in_(ch_ids)).delete(synchronize_session=False)
            db.query(models.ChallengeAttempt).filter(
                models.ChallengeAttempt.user_id.in_(ids) | models.ChallengeAttempt.challenge_id.in_(ch_ids)
            ).delete(synchronize_session=False)
            db.query(models.Challenge).filter(models.Challenge.id.in_(ch_ids)).delete(synchronize_session=False)
            db.query(models.Course).filter(models.Course.owner_id.in_(ids)).delete(synchronize_session=False)
            run_ids = [r.id for r in db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).all()] or [-1]
            db.query(models.AuditEvent).filter(
                ((models.AuditEvent.actor_type == "player") & models.AuditEvent.actor_id.in_(ids))
                | ((models.AuditEvent.entity_type == "user") & models.AuditEvent.entity_id.in_(ids))
                | ((models.AuditEvent.entity_type == "run_session") & models.AuditEvent.entity_id.in_(run_ids))
                | ((models.AuditEvent.entity_type == "challenge") & models.AuditEvent.entity_id.in_(ch_ids))
            ).delete(synchronize_session=False)
            db.query(models.VerificationDecision).filter(models.VerificationDecision.run_session_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.ActivityLog).filter(models.ActivityLog.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.UserBadge).filter(models.UserBadge.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _register(name, *, referral_code=None, invite_token=None, install_id=None, public=False):
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}{name}@example.com", "password": PASSWORD, "display_name": name.title(), "location_consent": True,
        "goal": "running", "referral_code": referral_code, "invite_token": invite_token,
        "install_id": install_id or f"{PREFIX}{name}-device",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if public:
        assert client.put("/api/v2/me/profile", headers=headers, json={"public_profile": True}).status_code == 200
    return headers, r.json()["profile"]


def _run(headers, start, metres, key):
    pts = _path(start, _north(start, metres))
    run_id = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now()}).json()["id"]
    client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _now()})
    r = client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": [
        {"sequence": i, "t_ms": t, "lat": lat, "lng": lng, "accuracy_m": 5} for i, (lat, lng, t) in enumerate(pts)
    ]})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _now(), "idempotency_key": f"{PREFIX}{key}",
    })
    assert r.status_code == 200 and r.json()["verification_status"] == "accepted", r.text
    return r.json()


def _xp(user_id):
    db = database.SessionLocal()
    try:
        return db.query(models.User).filter(models.User.id == user_id).first().xp
    finally:
        db.close()


def _badges(user_id):
    db = database.SessionLocal()
    try:
        return {b.badge_code for b in db.query(models.UserBadge).filter(models.UserBadge.user_id == user_id)}
    finally:
        db.close()


def _publish_challenge(headers):
    run = _run(headers, BASE, 1500, "course-run")
    r = client.post("/api/v2/courses", headers=headers, json={"run_id": run["id"], "name": "Harbour Mile"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v2/challenges", headers=headers, json={
        "course_id": r.json()["id"], "title": "Harbour Mile", "window_hours": 48,
        "safety_notes": "Busy at lunch; keep right.", "idempotency_key": PREFIX + "pub",
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_share_card_hides_location_and_can_be_revoked() -> None:
    cleanup()
    ada, _ = _register("ada")
    run = _run(ada, BASE, 1200, "ada-1")
    r = client.post("/api/v2/share", headers=ada, json={"kind": "run", "entity_id": run["id"]})
    assert r.status_code == 201, r.text
    card = r.json()
    assert card["stats"]["distance_km"] >= 1.1 and "/s/" in card["url"]
    again = client.post("/api/v2/share", headers=ada, json={"kind": "run", "entity_id": run["id"]}).json()
    assert again["token"] == card["token"]

    public = client.get(f"/api/v2/share/{card['token']}")
    assert public.status_code == 200
    body = public.json()
    for leak in ("lat", "lng", "route", "email"):
        assert leak not in body and leak not in body["stats"], leak
    assert "@example.com" not in public.text
    page = client.get(f"/s/{card['token']}")
    assert page.status_code == 200 and "og:title" in page.text and "noindex" in page.text

    # Someone else's run is not shareable by me, and I cannot revoke their card.
    bob, _ = _register("bob")
    assert client.post("/api/v2/share", headers=bob, json={"kind": "run", "entity_id": run["id"]}).status_code == 404
    assert client.delete(f"/api/v2/share/{card['token']}", headers=bob).status_code == 404
    assert client.delete(f"/api/v2/share/{card['token']}", headers=ada).status_code == 204
    assert client.get(f"/api/v2/share/{card['token']}").status_code == 404
    assert client.get(f"/s/{card['token']}").status_code == 404


def test_invite_signup_join_and_referral_reward() -> None:
    cleanup()
    host, host_profile = _register("host")
    ch = _publish_challenge(host)
    r = client.post(f"/api/v2/challenges/{ch['id']}/invites", headers=host)
    assert r.status_code == 201, r.text
    invite = r.json()
    preview = client.get(f"/api/v2/invites/{invite['token']}")
    assert preview.status_code == 200 and preview.json()["free_entry"] is True
    assert "marker_lat" not in preview.json() and preview.json()["inviter_name"] == "Host"
    assert client.get(f"/i/{invite['token']}").status_code == 200

    friend, friend_profile = _register("friend", invite_token=invite["token"])
    xp_before = _xp(host_profile["user_id"])
    far = (BASE[0], BASE[1] + 0.05)
    # A short first run does not trigger the reward yet.
    _run(friend, far, 600, "friend-short")
    assert _xp(host_profile["user_id"]) == xp_before
    _run(friend, far, 1200, "friend-long")
    assert _xp(host_profile["user_id"]) == xp_before + growth_api.REFERRAL_XP
    assert "RECRUITER" in _badges(host_profile["user_id"]) and "WELCOMED" in _badges(friend_profile["user_id"])
    # Paid out once only.
    _run(friend, far, 1200, "friend-long-2")
    assert _xp(host_profile["user_id"]) == xp_before + growth_api.REFERRAL_XP

    assert client.post(f"/api/v2/challenges/{ch['id']}/join", headers=friend).status_code == 200
    stats = client.get("/api/v2/me/invites", headers=host).json()
    assert stats[0]["signups"] == 1 and stats[0]["joins"] == 1 and stats[0]["opens"] >= 2, stats
    refs = client.get("/api/v2/me/referrals", headers=host).json()
    assert refs["rewarded"] == 1 and refs["rules"]


def test_self_referral_from_same_device_earns_nothing() -> None:
    cleanup()
    _, profile = _register("main", install_id=PREFIX + "shared-phone")
    alt, _ = _register("alt", referral_code=profile["referral_code"], install_id=PREFIX + "shared-phone")
    before = _xp(profile["user_id"])
    _run(alt, (BASE[0], BASE[1] + 0.1), 1200, "alt-1")
    assert _xp(profile["user_id"]) == before
    db = database.SessionLocal()
    try:
        referee = db.query(models.PlayerProfile).filter(
            models.PlayerProfile.referred_by_user_id == profile["user_id"]).first()
        assert referee.referral_status == "same_device"
    finally:
        db.close()


def test_referral_rewards_are_capped() -> None:
    cleanup()
    _, host = _register("capper")
    db = database.SessionLocal()
    try:
        # Five referrals already rewarded this month.
        for i in range(growth_api.REFERRAL_CAP):
            u = models.User(email=f"{PREFIX}prior{i}@example.com", hashed_password="x", xp=0, mana_crystals=0)
            db.add(u)
            db.flush()
            db.add(models.PlayerProfile(
                user_id=u.id, display_name=f"P{i}", goal="running", referral_code=f"G2CAP{i:03d}",
                referred_by_user_id=host["user_id"], referral_status="rewarded",
                referral_rewarded_at=main._now_naive_utc(),
            ))
        db.commit()
    finally:
        db.close()
    sixth, sixth_profile = _register("sixth", referral_code=host["referral_code"])
    before = _xp(host["user_id"])
    _run(sixth, (BASE[0], BASE[1] + 0.15), 1200, "sixth-1")
    assert _xp(host["user_id"]) == before
    assert "WELCOMED" in _badges(sixth_profile["user_id"])


def test_public_achievement_page_is_opt_in() -> None:
    cleanup()
    _, shy_profile = _register("shy")
    pub, pub_profile = _register("proud", public=True)
    _run(pub, (BASE[0], BASE[1] + 0.2), 1200, "proud-1")
    assert client.get(f"/api/v2/public/players/{shy_profile['referral_code']}").status_code == 404
    assert client.get(f"/p/{shy_profile['referral_code']}").status_code == 404
    r = client.get(f"/api/v2/public/players/{pub_profile['referral_code']}")
    assert r.status_code == 200 and r.json()["verified_runs"] == 1
    assert "FIRST_VERIFIED_RUN" in {b["code"] for b in r.json()["badges"]}
    page = client.get(f"/p/{pub_profile['referral_code']}")
    assert page.status_code == 200
    assert "index,follow" in page.text and "application/ld+json" in page.text and "Proud" in page.text
    assert "@example.com" not in page.text
    assert client.get(f"/join/{pub_profile['referral_code']}").status_code == 200


def test_display_name_is_escaped_on_public_pages() -> None:
    cleanup()
    evil, profile = _register("evil", public=True)
    client.put("/api/v2/me/profile", headers=evil, json={"display_name": "<script>x</script>"})
    page = client.get(f"/p/{profile['referral_code']}")
    assert "<script>x</script>" not in page.text and "&lt;script&gt;" in page.text


if __name__ == "__main__":
    for test in (
        test_share_card_hides_location_and_can_be_revoked,
        test_invite_signup_join_and_referral_reward,
        test_self_referral_from_same_device_earns_nothing,
        test_referral_rewards_are_capped,
        test_public_achievement_page_is_opt_in,
        test_display_name_is_escaped_on_public_pages,
    ):
        test()
        print(f"PASS {test.__name__}")
    cleanup()
