"""Discover challenge hub sections and Social global leaderboards.

Runs against an in-memory database so the global boards contain only this suite's players.
    python tests/test_growth_hub.py
"""
import os
import sys
from datetime import timedelta

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "growth-hub-test-secret-aaaaaaaaaaaaaaaaaaaaaa")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
from services import challenges as challenge_rules  # noqa: E402
from database import Base  # noqa: E402
from services import leaderboards as lb  # noqa: E402

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def _db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


main.app.dependency_overrides[main.get_db] = _db
client = TestClient(main.app)
NOW = main._now_naive_utc()


def register(name, opt_in=True):
    r = client.post("/api/v2/auth/register", json={
        "email": f"hub_{name}@example.com", "password": "HubTest123!", "display_name": name,
        "location_consent": True, "goal": "running",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.put("/api/v2/me/profile", headers=headers, json={"leaderboard_opt_in": opt_in})
    assert r.status_code == 200, r.text
    return headers, _user_id(name)


def _user_id(name):
    db = Session()
    try:
        return db.query(models.User).filter(models.User.email == f"hub_{name.lower()}@example.com").one().id
    finally:
        db.close()


def run(db, user_id, metres, seconds, days_ago=0, status="accepted"):
    r = models.RunSession(user_id=user_id, status="finished", distance_m=metres, duration_seconds=seconds,
                          verification_status=status, finished_at=NOW - timedelta(days=days_ago))
    db.add(r)
    db.flush()
    return r


def challenge(db, creator_id, title, opens, closes, status="open"):
    source = run(db, creator_id, 2000, 600, status="course-source")
    course = models.Course(owner_id=creator_id, source_run_session_id=source.id, rules_version="v1", name=title,
                           distance_m=2000, benchmark_seconds=600, start_lat=0, start_lng=0, finish_lat=0,
                           finish_lng=0, route_json="[]", route_hash=f"h-{title}", public_lat=0, public_lng=0)
    db.add(course)
    db.flush()
    ch = models.Challenge(course_id=course.id, creator_id=creator_id, title=title, status=status, rules_version="v1",
                          course_version=1, target_seconds=600, win_xp=100, participation_xp=10, opens_at=opens,
                          closes_at=closes, terms_hash=f"t-{title}")
    db.add(ch)
    db.flush()
    return ch


def attempt(db, ch, user_id, outcome=None, elapsed=None, xp=0):
    a = models.ChallengeAttempt(challenge_id=ch.id, user_id=user_id, status="decided" if outcome else "joined",
                                outcome=outcome, terms_hash=ch.terms_hash, elapsed_seconds=elapsed, xp_awarded=xp,
                                decided_at=NOW if outcome else None)
    db.add(a)
    return a


def exercise(db, user_id, key, reps=0, hold=0.0, status="verified"):
    db.add(models.ExerciseSession(user_id=user_id, client_session_id=f"{user_id}-{key}-{reps}-{hold}", exercise_key=key,
                                  rules_version="v1", duration_s=60, reps_valid=reps, hold_s=hold,
                                  client_verdict="ok", status=status, local_date=NOW.date().isoformat()))


ana_h, ana = register("Ana")
ben_h, ben = register("Ben")
cy_h, cy = register("Cy", opt_in=False)
db = Session()
live = challenge(db, ana, "Live", NOW - timedelta(hours=1), NOW + timedelta(days=2))
upcoming = challenge(db, ana, "Upcoming", NOW + timedelta(hours=3), NOW + timedelta(days=3))
finished = challenge(db, ana, "Finished", NOW - timedelta(days=3), NOW - timedelta(days=1), status="closed")
stale = challenge(db, ana, "Stale", NOW - timedelta(days=40), NOW - timedelta(days=30), status="settled")
featured = challenge(db, ana, "Featured", NOW - timedelta(hours=2), NOW + timedelta(days=5))
club = models.Community(slug="hub-club", name="Hub Club", kind="running_club", owner_user_id=ana, visibility="public")
db.add(club)
db.flush()
db.add(models.CommunityChallenge(community_id=club.id, challenge_id=featured.id, added_by_user_id=ana))
attempt(db, live, ben)
attempt(db, live, cy)
attempt(db, finished, ben, "won", 590.0, xp=100)
attempt(db, finished, cy, "won", 580.0, xp=100)
attempt(db, finished, ana, "lost", 700.0, xp=10)
run(db, ben, 5000, 1500)            # 5 km in 25:00
run(db, cy, 10000, 3000)            # 10 km in 50:00 -> 5 km eq ~24:00
run(db, ben, 3000, 600, days_ago=30)
run(db, ana, 800, 120)              # too short for pace
run(db, ana, 4000, 900, status="rejected")
exercise(db, ben, "pushup", reps=40)
exercise(db, cy, "pushup", reps=55)
exercise(db, cy, "pushup", reps=500, status="rejected")
exercise(db, ana, "plank", hold=95.0)
db.commit()
LIVE_ID = live.id
db.close()


def section(name, headers=ben_h):
    r = client.get(f"/api/v2/challenge-hub?section={name}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def board(name, headers=ben_h, **params):
    query = "&".join(f"{k}={v}" for k, v in {"board": name, **params}.items())
    r = client.get(f"/api/v2/leaderboards/global?{query}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_hub_sections():
    live_items = section("live")
    assert [i["challenge"]["title"] for i in live_items] == ["Live", "Featured"]
    assert live_items[0]["participants"] == 2
    up = section("upcoming")
    assert [i["challenge"]["title"] for i in up] == ["Upcoming"]
    assert 3 * 3600 - 120 <= up[0]["starts_in_seconds"] <= 3 * 3600
    community = section("community")
    assert [(i["challenge"]["title"], i["community_name"]) for i in community] == [("Featured", "Hub Club")]
    done = section("finished")
    assert [i["challenge"]["title"] for i in done] == ["Finished"]
    assert done[0]["xp_paid"] == 210
    # Cy did not opt in to leaderboards, so the winner is shown without a name.
    assert [(w["rank"], w["name"]) for w in done[0]["winners"]] == [(1, "Private runner"), (2, "Ben")]
    assert client.get("/api/v2/challenge-hub?section=everything", headers=ben_h).status_code == 422
    assert client.get("/api/v2/challenge-hub?section=live").status_code == 401
    print("PASS test_hub_sections")


def test_blocked_creators_are_hidden():
    r = client.post("/api/v2/blocks", headers=ben_h, json={"challenge_id": LIVE_ID})
    assert r.status_code in (200, 201), r.text
    assert section("live") == [] and section("finished") == []
    assert [i["challenge"]["title"] for i in section("live", headers=cy_h)] == ["Live", "Featured"]
    block_id = client.get("/api/v2/me/blocks", headers=ben_h).json()[0]["id"]
    assert client.delete(f"/api/v2/blocks/{block_id}", headers=ben_h).status_code in (200, 204)
    print("PASS test_blocked_creators_are_hidden")


def test_distance_board_counts_verified_runs_in_the_period():
    week = board("distance")
    assert [(r["name"], r["value"]) for r in week["rows"]][:2] == [("Private runner", 10.0), ("Ben", 5.0)]
    assert week["my_row"]["name"] == "Ben" and week["my_row"]["is_me"]
    all_time = board("distance", period="all")
    assert next(r for r in all_time["rows"] if r["is_me"])["value"] == 8.0
    print("PASS test_distance_board_counts_verified_runs_in_the_period")


def test_pace_board_ranks_riegel_time_lowest_first():
    pace = board("pace", period="all")
    assert pace["lower_is_better"] and pace["unit"] == "s"
    # Ben's 3 km in 10:00 (all time) predicts ~17:31 for 5 km and beats Cy's 10 km.
    assert [r["name"] for r in pace["rows"]] == ["Ben", "Private runner"]
    assert abs(pace["rows"][0]["value"] - round(lb.riegel_seconds(600, 3000), 1)) < 0.11
    assert all(r["name"] != "Ana" for r in pace["rows"])
    print("PASS test_pace_board_ranks_riegel_time_lowest_first")


def test_reps_and_rewards_boards():
    reps = board("reps", exercise="pushup")
    assert [(r["name"], r["value"]) for r in reps["rows"]] == [("Private runner", 55.0), ("Ben", 40.0)]
    plank = board("reps", exercise="plank", headers=ana_h)
    assert plank["unit"] == "s" and plank["rows"] == [{"rank": 1, "name": "Ana", "value": 95.0, "is_me": True}]
    assert client.get("/api/v2/leaderboards/global?board=reps&exercise=burpee", headers=ben_h).status_code == 422
    rewards = board("rewards")
    assert [(r["rank"], r["value"]) for r in rewards["rows"]] == [(1, 100.0), (1, 100.0)]
    print("PASS test_reps_and_rewards_boards")


def test_riegel_and_ranking_rules():
    assert lb.riegel_seconds(1500, 5000) == 1500
    assert lb.riegel_seconds(3000, 10000) < 1500
    assert lb.rank_values({1: 5.0, 2: 9.0, 3: 9.0, 4: 0.0}, ascending=False) == [(2, 9.0, 1), (3, 9.0, 1), (1, 5.0, 3)]
    assert lb.rank_values({1: 30.0, 2: 20.0}, ascending=True) == [(2, 20.0, 1), (1, 30.0, 2)]
    try:
        lb.riegel_seconds(0, 1000)
        raise AssertionError("zero time must be rejected")
    except ValueError:
        pass
    print("PASS test_riegel_and_ranking_rules")


def test_progression_counts_for_the_profile():
    db = Session()
    for uid, xp in ((ana, 50), (ben, 300), (cy, 300)):
        db.query(models.User).filter(models.User.id == uid).update({models.User.xp: xp})
    db.commit()
    db.close()
    p = client.get("/api/v2/me/progression", headers=ben_h).json()
    assert (p["challenges_won"], p["challenges_lost"], p["challenges_played"]) == (1, 0, 1)
    assert p["lifetime_distance_km"] == 8.0
    assert p["global_rank"] == 1
    assert (p["rank_floor_xp"], p["next_rank_xp"]) == (0, 500)
    assert [challenge_rules.rank_floor(x) for x in (0, 499, 500, 1100, 40000)] == [0, 0, 500, 500, 35000]
    a = client.get("/api/v2/me/progression", headers=ana_h).json()
    assert (a["challenges_won"], a["challenges_lost"], a["challenges_played"], a["global_rank"]) == (0, 1, 1, 3)
    print("PASS test_progression_counts_for_the_profile")


def _queries(url, headers):
    """SQL statements one GET runs (after a warm-up call, so lazy settlement is already done)."""
    from sqlalchemy import event
    client.get(url, headers=headers)
    seen = []

    def _count(*_args, **_kwargs):
        seen.append(1)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        assert client.get(url, headers=headers).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    return len(seen)


def test_list_endpoints_run_a_fixed_number_of_queries():
    """Performance audit 2026-10-19: list endpoints ran 1-3 queries per challenge shown (the nearby map
    ran 51 queries for 24 challenges). Adding challenges must not add queries."""
    db = Session()
    admin = models.Admin(email="hub_admin@example.com", hashed_password="x", name="Hub Admin")
    db.add(admin)
    db.commit()
    admin_h = {"Authorization": f"Bearer {main.create_access_token({'sub': str(admin.id), 'role': 'admin'})}"}
    db.close()
    urls = [(f"/api/v2/challenge-hub?section={s}", ben_h) for s in ("live", "upcoming", "community", "finished")]
    urls += [("/api/v2/challenges/nearby?lat=0&lng=0&radius_km=5", ben_h), ("/api/v2/communities/hub-club/challenges", ben_h),
             ("/api/v2/admin/challenges", admin_h)]
    before = {u: _queries(u, h) for u, h in urls}
    db = Session()
    club_id = db.query(models.Community.id).filter(models.Community.slug == "hub-club").scalar()
    for i in range(6):
        live_more = challenge(db, ana, f"Live {i}", NOW - timedelta(hours=1), NOW + timedelta(days=2))
        attempt(db, live_more, ben)
        attempt(db, live_more, cy)
        challenge(db, ana, f"Upcoming {i}", NOW + timedelta(hours=2), NOW + timedelta(days=3))
        done = challenge(db, ana, f"Finished {i}", NOW - timedelta(days=3), NOW - timedelta(days=1), status="closed")
        attempt(db, done, ben, "won", 590.0 + i, xp=100)
        attempt(db, done, cy, "lost", 700.0, xp=10)
        db.add(models.CommunityChallenge(community_id=club_id, challenge_id=live_more.id, added_by_user_id=ana))
    db.commit()
    db.close()
    after = {u: _queries(u, h) for u, h in urls}
    assert after == before, {u: (before[u], after[u]) for u in before if before[u] != after[u]}
    assert len(section("live")) >= 7 and len(section("finished")) >= 7
    print("PASS test_list_endpoints_run_a_fixed_number_of_queries")


def test_responses_are_compressed_and_revalidated():
    """Performance audit 2026-10-19: list payloads went uncompressed and every poll re-sent the full body."""
    url = "/api/v2/challenge-hub?section=live"
    full = client.get(url, headers=ben_h)
    assert full.status_code == 200 and len(full.content) > 1000
    assert full.headers.get("content-encoding") == "gzip"
    assert full.headers["cache-control"] == "private, no-cache"
    tag = full.headers["etag"]
    assert client.get(url, headers=ben_h).headers["etag"] == tag  # stable while nothing changes
    same = client.get(url, headers={**ben_h, "If-None-Match": tag})
    assert same.status_code == 304 and same.content == b""
    assert same.headers["cache-control"] == "private, no-cache" and same.headers["etag"] == tag  # clients key on these
    stale = client.get(url, headers={**ben_h, "If-None-Match": 'W/"stale"'})
    assert stale.status_code == 200 and stale.json() == full.json()
    small = client.get("/api/v2/me/blocks", headers=ben_h)
    assert small.status_code == 200 and "content-encoding" not in small.headers  # not worth compressing
    rules = client.get("/api/v2/rules")
    assert rules.headers["cache-control"] == "public, max-age=300"
    assert client.post("/api/v2/challenges/999999/join", headers=ben_h).headers.get("etag") is None
    print("PASS test_responses_are_compressed_and_revalidated")


def test_board_cache_serves_others_stale_and_the_viewer_fresh():
    """Performance audit 2026-10-19: every Social tab open rescanned all verified runs (~300 ms at 100k runs)."""
    from growth_hub import BOARD_CACHE
    url = "/api/v2/leaderboards/global?board=distance&period=all"
    uncached = _queries(url, ben_h)
    BOARD_CACHE.ttl_seconds = 60
    BOARD_CACHE.clear()
    try:
        assert _queries(url, ben_h) < uncached
        before = board("distance", period="all")
        ana_before = next(r["value"] for r in before["rows"] if r["name"] == "Ana")
        db = Session()
        run(db, ana, 5000, 1500)
        run(db, ben, 2000, 600)
        db.commit()
        db.close()
        cached = board("distance", period="all")
        assert next(r["value"] for r in cached["rows"] if r["name"] == "Ana") == ana_before  # others lag
        assert cached["my_row"]["value"] == before["my_row"]["value"] + 2.0  # the viewer's run shows at once
        assert next(r for r in cached["rows"] if r["is_me"])["value"] == cached["my_row"]["value"]
        BOARD_CACHE.clear()
        fresh = board("distance", period="all")
        assert next(r["value"] for r in fresh["rows"] if r["name"] == "Ana") == round(ana_before + 5.0, 1)
    finally:
        BOARD_CACHE.ttl_seconds = 0
        BOARD_CACHE.clear()
    print("PASS test_board_cache_serves_others_stale_and_the_viewer_fresh")


def test_ttl_cache_expires_and_evicts():
    from services.ttl_cache import TTLCache
    clock = [100.0]
    calls = []
    cache = TTLCache(ttl_seconds=10, max_entries=2, clock=lambda: clock[0])

    def get(key):
        return cache.get_or_compute(key, lambda: calls.append(key) or f"v{len(calls)}")

    assert get("a") == "v1" and get("a") == "v1"
    clock[0] = 111.0
    assert get("a") == "v2"  # expired
    get("b")
    get("c")  # evicts "a", the least recently used
    assert get("b") == "v3" and get("a") == "v5"
    assert TTLCache(ttl_seconds=0).get_or_compute("k", lambda: calls.append("off") or "x") == "x" and calls[-1] == "off"
    print("PASS test_ttl_cache_expires_and_evicts")


if __name__ == "__main__":
    test_hub_sections()
    test_blocked_creators_are_hidden()
    test_distance_board_counts_verified_runs_in_the_period()
    test_pace_board_ranks_riegel_time_lowest_first()
    test_reps_and_rewards_boards()
    test_riegel_and_ranking_rules()
    test_progression_counts_for_the_profile()
    test_list_endpoints_run_a_fixed_number_of_queries()  # last: it adds challenges the tests above count
    test_responses_are_compressed_and_revalidated()
    test_board_cache_serves_others_stale_and_the_viewer_fresh()
    test_ttl_cache_expires_and_evicts()
