"""Growth G3 regression tests: communities, team goals, local rankings, seasons, and
city seeding.

Run directly from the backend directory:
    python tests/test_growth_communities.py
"""
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "growth-communities-test-secret-aaaaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "scripts")))

from fastapi.testclient import TestClient

import database
import main
import growth_api
import models
from services import leaderboards as lb


PREFIX = "growth_g3_test_"
PASSWORD = "CommunityTest1!"
ADMIN_EMAIL = PREFIX + "admin@example.com"
OFFICIAL_EMAIL = PREFIX + "official@example.com"
CITY = "g3-test-city"
M_PER_DEG_LAT = 111_195.0
BASE = (45.3000, -64.3000)

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
        community_ids = [c.id for c in db.query(models.Community).filter(
            (models.Community.city == CITY) | models.Community.owner_user_id.in_(ids or [-1])).all()] or [-1]
        db.query(models.CommunityChallenge).filter(models.CommunityChallenge.community_id.in_(community_ids)).delete(synchronize_session=False)
        db.query(models.CommunityMember).filter(models.CommunityMember.community_id.in_(community_ids)).delete(synchronize_session=False)
        db.query(models.Community).filter(models.Community.id.in_(community_ids)).delete(synchronize_session=False)
        season_ids = [s.id for s in db.query(models.Season).filter(models.Season.city == CITY).all()] or [-1]
        db.query(models.SeasonEntry).filter(models.SeasonEntry.season_id.in_(season_ids)).delete(synchronize_session=False)
        db.query(models.Season).filter(models.Season.id.in_(season_ids)).delete(synchronize_session=False)
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
            db.query(models.VerificationDecision).filter(models.VerificationDecision.run_session_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(models.AuditEvent).filter(
                ((models.AuditEvent.actor_type == "player") & models.AuditEvent.actor_id.in_(ids))
                | ((models.AuditEvent.entity_type == "user") & models.AuditEvent.entity_id.in_(ids))
                | ((models.AuditEvent.entity_type == "run_session") & models.AuditEvent.entity_id.in_(run_ids))
                | ((models.AuditEvent.entity_type == "challenge") & models.AuditEvent.entity_id.in_(ch_ids))
                | (models.AuditEvent.entity_type.in_(("community", "season")))
                & models.AuditEvent.entity_id.in_(community_ids + season_ids)
            ).delete(synchronize_session=False)
            db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.ActivityLog).filter(models.ActivityLog.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.UserBadge).filter(models.UserBadge.user_id.in_(ids)).delete(synchronize_session=False)
            # Ledger rows must go too: SQLite reuses freed user ids, so orphans would be inherited.
            db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_(ids)).delete(synchronize_session=False)
        db.query(models.Admin).filter(models.Admin.email == ADMIN_EMAIL).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _register(name, *, city=CITY, opt_in=False):
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}{name}@example.com", "password": PASSWORD, "display_name": name.title(), "location_consent": True,
        "goal": "running",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.put("/api/v2/me/profile", headers=headers, json={"city": city, "leaderboard_opt_in": opt_in})
    assert r.status_code == 200 and r.json()["city"] == CITY, r.text
    return headers, r.json()


def _run(headers, metres, key, lng_offset=0.0):
    start = (BASE[0], BASE[1] + lng_offset)
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


def _admin() -> dict:
    db = database.SessionLocal()
    try:
        admin = models.Admin(email=ADMIN_EMAIL, hashed_password="x", name="G3 Admin")
        db.add(admin)
        db.commit()
        admin_id = admin.id
    finally:
        db.close()
    return {"Authorization": f"Bearer {main.create_access_token({'sub': str(admin_id), 'role': 'admin'})}"}


# --- pure rules ---------------------------------------------------------------------

def test_scoring_caps_days_and_rewards_consistency() -> None:
    assert lb.day_points(0) == 0
    assert lb.day_points(1000) == 20
    assert lb.day_points(40_000) == lb.day_points(10_000) == 110
    one_big_day = lb.score({date(2026, 9, 1): 30_000})
    five_easy_days = lb.score({date(2026, 9, d): 2000 for d in range(1, 6)})
    assert five_easy_days[0] > one_big_day[0]
    standings = lb.rank({1: (50, 2, 0), 2: (50, 2, 0), 3: (40, 3, 0), 4: (0, 0, 0)})
    assert [(s.key, s.rank) for s in standings] == [(1, 1), (2, 1), (3, 3)]


def test_community_season_scores_use_averages() -> None:
    scores = {1: (100, 5, 0), 2: (100, 5, 0), 3: (100, 5, 0), 4: (10, 1, 0), 5: (10, 1, 0),
              6: (10, 1, 0), 7: (10, 1, 0), 8: (500, 5, 0)}
    out = lb.community_season_scores({10: [1, 2, 3], 20: [4, 5, 6, 7], 30: [8]}, scores)
    assert out[10][0] == 100 and out[20][0] == 10 and 30 not in out


# --- API --------------------------------------------------------------------------

def test_community_lifecycle_privacy_and_team_goal() -> None:
    cleanup()
    owner, _ = _register("owner", opt_in=True)
    fan, _ = _register("fan")
    outsider, _ = _register("outsider")

    body = {"name": "G3 Test Harriers", "kind": "running_club", "city": CITY, "weekly_team_goal_km": 2,
            "brand_color": "#0E7490", "perk_text": "Free coffee after Saturday runs"}
    r = client.post("/api/v2/communities", headers=owner, json=body)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "NOT_ELIGIBLE"
    _run(owner, 1200, "owner-1")
    assert client.post("/api/v2/communities", headers=owner, json=dict(body, kind="casino")).status_code == 422
    r = client.post("/api/v2/communities", headers=owner, json=body)
    assert r.status_code == 201, r.text
    club = r.json()
    assert club["my_role"] == "owner" and club["team_goal"]["goal_km"] == 2 and not club["verified"]

    listed = client.get("/api/v2/communities", headers=outsider, params={"city": CITY}).json()
    assert [c["slug"] for c in listed] == [club["slug"]] and listed[0]["team_goal"] is None
    r = client.get(f"/api/v2/communities/{club['slug']}/leaderboard", headers=outsider)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "MEMBERS_ONLY"

    assert client.post(f"/api/v2/communities/{club['slug']}/join", headers=fan, json={}).status_code == 200
    _run(fan, 1500, "fan-1", lng_offset=0.01)
    board = client.get(f"/api/v2/communities/{club['slug']}/leaderboard", headers=owner).json()
    names = [row["name"] for row in board["rows"]]
    # The owner opted in; the fan did not, so the fan shows as a private runner to others.
    assert "Owner" in names and "Fan" not in names and lb_private(names)
    fan_view = client.get(f"/api/v2/communities/{club['slug']}/leaderboard", headers=fan).json()
    assert fan_view["my_row"]["name"] == "Fan"
    detail = client.get(f"/api/v2/communities/{club['slug']}", headers=fan).json()
    assert detail["team_goal"]["progress_km"] >= 2.6 and detail["team_goal"]["completed"]
    assert detail["join_code"] is None

    # Private workplace community: join code needed; hidden from non-members.
    r = client.post("/api/v2/communities", headers=owner, json={
        "name": "G3 Test Office", "kind": "corporate", "city": CITY, "visibility": "private"})
    office = r.json()
    assert office["join_code"]
    assert client.get(f"/api/v2/communities/{office['slug']}", headers=outsider).status_code == 404
    r = client.post(f"/api/v2/communities/{office['slug']}/join", headers=outsider, json={"join_code": "nope"})
    assert r.status_code == 403
    r = client.post(f"/api/v2/communities/{office['slug']}/join", headers=outsider,
                    json={"join_code": office["join_code"]})
    assert r.status_code == 200 and r.json()["my_role"] == "member"

    r = client.post(f"/api/v2/communities/{club['slug']}/leave", headers=owner)
    assert r.status_code == 409
    assert client.post(f"/api/v2/communities/{club['slug']}/leave", headers=fan).status_code == 204


def lb_private(names):
    return "Private runner" in names


def test_local_leaderboard_needs_city_and_hides_non_opted_names() -> None:
    cleanup()
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}nocity@example.com", "password": PASSWORD, "display_name": "Nocity", "goal": "running", "location_consent": True})
    nocity = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.get("/api/v2/leaderboards/local", headers=nocity)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CITY_REQUIRED"

    alice, _ = _register("alice", opt_in=True)
    bob, _ = _register("bob")
    _run(alice, 1200, "alice-1")
    _run(bob, 2500, "bob-1", lng_offset=0.02)
    board = client.get("/api/v2/leaderboards/local", headers=alice).json()
    assert board["ranked_players"] == 2 and board["rows"][0]["name"] == "Private runner"
    assert board["rows"][1]["name"] == "Alice" and board["my_row"]["rank"] == 2
    assert "10 km" in board["scoring"]


def test_seasons_and_community_standings() -> None:
    cleanup()
    admin = _admin()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    r = client.post("/api/v2/admin/seasons", headers=admin, json={
        "name": "G3 Test Season", "city": CITY, "starts_at": (now - timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=30)).isoformat()})
    assert r.status_code == 201, r.text
    season = r.json()
    assert season["status"] == "live"
    bad = client.post("/api/v2/admin/seasons", headers=admin, json={
        "name": "Too long", "city": CITY, "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(days=400)).isoformat()})
    assert bad.status_code == 422

    players = [_register(n) for n in ("sa", "sb", "sc")]
    owner = players[0][0]
    _run(owner, 1000, "sa-1")
    club = client.post("/api/v2/communities", headers=owner, json={
        "name": "G3 Season Club", "kind": "gym", "city": CITY}).json()
    for i, (h, _) in enumerate(players):
        if i:
            client.post(f"/api/v2/communities/{club['slug']}/join", headers=h, json={})
            _run(h, 1200, f"s{i}-1", lng_offset=0.03 * i)
        assert client.post(f"/api/v2/seasons/{season['slug']}/join", headers=h).status_code == 200
    listed = client.get("/api/v2/seasons", headers=owner).json()
    assert any(s["slug"] == season["slug"] and s["entered"] and s["participants"] == 3 for s in listed)
    board = client.get(f"/api/v2/seasons/{season['slug']}/leaderboard", headers=owner).json()
    assert board["players"]["ranked_players"] == 3
    assert board["communities"] and board["communities"][0]["slug"] == club["slug"]
    assert board["communities"][0]["is_mine"] and board["communities"][0]["entered_members"] == 3


def test_admin_verify_suspend_and_owner_deletion_handover() -> None:
    cleanup()
    admin = _admin()
    owner, owner_profile = _register("boss")
    member, member_profile = _register("heir")
    _run(owner, 1000, "boss-1")
    club = client.post("/api/v2/communities", headers=owner, json={
        "name": "G3 Handover Club", "kind": "university", "city": CITY}).json()
    client.post(f"/api/v2/communities/{club['slug']}/join", headers=member, json={})
    items = client.get("/api/v2/admin/communities", headers=admin).json()
    cid = next(i["id"] for i in items if i["slug"] == club["slug"])
    assert client.post(f"/api/v2/admin/communities/{cid}/status", headers=owner,
                       json={"verified": True, "reason": "checked"}).status_code == 403
    r = client.post(f"/api/v2/admin/communities/{cid}/status", headers=admin,
                    json={"verified": True, "reason": "Called the club secretary"})
    assert r.status_code == 200 and r.json()["verified"]
    assert client.get(f"/api/v2/communities/{club['slug']}", headers=member).json()["verified"]

    db = database.SessionLocal()
    try:
        growth_api.delete_growth_data(db, [owner_profile["user_id"]])
        db.commit()
        c = db.query(models.Community).filter(models.Community.id == cid).first()
        assert c.owner_user_id == member_profile["user_id"]
    finally:
        db.close()
    assert client.get(f"/api/v2/communities/{club['slug']}", headers=member).json()["my_role"] == "owner"

    client.post(f"/api/v2/admin/communities/{cid}/status", headers=admin,
                json={"status": "suspended", "reason": "Spam reports"})
    assert client.get(f"/api/v2/communities/{club['slug']}", headers=member).status_code == 404


def test_seed_city_creates_official_challenges_idempotently() -> None:
    cleanup()
    import seed_city

    start = (BASE[0] + 0.05, BASE[1])
    config = {
        "city": CITY, "official_email": OFFICIAL_EMAIL,
        "routes": [{"name": "G3 Seed Loop", "waypoints": [list(start), list(_north(start, 1400))],
                    "benchmark_pace_s_per_km": 420, "window_days": 30, "safety_notes": "Test route."}],
        "communities": [{"name": "G3 Seed Club", "kind": "running_club", "featured_routes": ["G3 Seed Loop"]}],
        "season": {"name": "G3 Seed Season", "starts_at": "2026-01-01T00:00:00", "ends_at": "2026-03-01T00:00:00"},
    }
    first = seed_city.seed(config)
    second = seed_city.seed(config)
    assert first["challenges"] == second["challenges"] and len(first["challenges"]) == 1
    player, _ = _register("seeker")
    featured = client.get("/api/v2/communities/g3-seed-club/challenges", headers=player).json()
    assert [c["id"] for c in featured] == list(first["challenges"].values())
    assert client.get("/api/v2/communities/g3-seed-club", headers=player).json()["verified"]
    today = client.get("/api/v2/me/today", headers=player, params={"lat": start[0], "lng": start[1]}).json()
    assert today["starter_challenge"]["id"] == first["challenges"]["G3 Seed Loop"]


if __name__ == "__main__":
    for test in (
        test_scoring_caps_days_and_rewards_consistency,
        test_community_season_scores_use_averages,
        test_community_lifecycle_privacy_and_team_goal,
        test_local_leaderboard_needs_city_and_hides_non_opted_names,
        test_seasons_and_community_standings,
        test_admin_verify_suspend_and_owner_deletion_handover,
        test_seed_city_creates_official_challenges_idempotently,
    ):
        test()
        print(f"PASS {test.__name__}")
    cleanup()
