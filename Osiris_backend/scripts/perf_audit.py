"""SQL queries per request on the hot read endpoints, against a seeded in-memory database.

    python scripts/perf_audit.py [players]

Seeds a few hundred rows (players, runs, Arise domains and routes, a city season, posts with
comments and reactions, training sessions, bounties), then calls each endpoint once and prints
how many SQL statements it ran. A count that grows with `players` is an N+1.
tests/test_query_budget.py runs the same audit and fails when an endpoint goes over its budget.
"""
import json
import os
import sys
from datetime import timedelta

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "perf-audit-secret-aaaaaaaaaaaaaaaaaaaaaaaa")
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from core import security  # noqa: E402
from core.clock import _now_naive_utc  # noqa: E402
from services import training  # noqa: E402

LAT, LNG = 44.72, -63.66
CITY = "perf-city"
PASSWORD = "PerfAudit123!"
DISTANCE_KEY = next(a["key"] for a in training.ACTIVITIES if a["metric"] == "distance_m")

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
_count = [0]


@event.listens_for(engine, "before_cursor_execute")
def _on_query(*_args) -> None:
    _count[0] += 1


def _db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _square(lat: float, lng: float, d: float = 0.002) -> str:
    return json.dumps([{"lat": lat, "lng": lng}, {"lat": lat + d, "lng": lng},
                       {"lat": lat + d, "lng": lng + d}, {"lat": lat, "lng": lng + d}])


def seed(players: int = 40) -> dict:
    """Builds the app on a fresh in-memory database. Returns the client, auth headers and ids."""
    database.Base.metadata.drop_all(bind=engine)
    database.Base.metadata.create_all(bind=engine)
    main.app.dependency_overrides[database.get_db] = _db
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.post("/api/v2/auth/register", json={
        "email": "perf_viewer@example.com", "password": PASSWORD, "display_name": "Viewer",
        "goal": "fitness", "location_consent": False,
    })
    assert r.status_code == 201, r.text
    player = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = r.json()["profile"]["user_id"]

    db = Session()
    now = _now_naive_utc().replace(microsecond=0)
    db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == me).update({"city": CITY})
    users = [models.User(email=f"perf{i}@example.com", xp=i * 10) for i in range(players)]
    db.add_all(users)
    db.flush()
    ids = [u.id for u in users]
    for i, uid in enumerate(ids):
        db.add(models.PlayerProfile(user_id=uid, display_name=f"Runner {i}", referral_code=f"PERF{i:04d}",
                                    city=CITY, leaderboard_opt_in=True))
        db.add(models.UserFollow(follower_id=me, followed_id=uid))
        runs = [models.RunSession(user_id=uid, status="closed", verification_status="accepted",
                                  started_at=now - timedelta(hours=k + 2), finished_at=now - timedelta(hours=k + 1),
                                  distance_m=5000.0, duration_seconds=1500.0) for k in range(3)]
        db.add_all(runs)
        db.flush()
        lat, lng = LAT + (i % 10) * 0.003, LNG + (i // 10) * 0.003
        db.add(models.Course(owner_id=uid, source_run_session_id=runs[0].id, rules_version="1", name=f"Route {i}",
                             distance_m=5000.0, benchmark_seconds=1500.0, start_lat=lat, start_lng=lng,
                             finish_lat=lat, finish_lng=lng, route_json="[]", route_hash=f"h{i}",
                             public_lat=lat, public_lng=lng, is_public=True, public_route_json="[[0,0]]"))
        domain = models.Domain(owner_id=uid, geometry_json=_square(lat, lng), area_sqkm=0.05, defense_type="arise",
                               distance_m=5000.0, duration_s=1500.0, source_run_session_id=runs[1].id)
        db.add(domain)
        # The same number again on another continent: rows a radius search must never load.
        db.add(models.Domain(owner_id=uid, geometry_json=_square(-LAT, -LNG), area_sqkm=0.05, defense_type="arise",
                             distance_m=5000.0, duration_s=1500.0))
        db.flush()
        if i % 2:
            db.add(models.DomainPhoto(domain_id=domain.id, jpeg=b"\xff\xd8perf"))
        for k in range(2):
            post = models.SocialPost(user_id=uid, kind="custom", caption=f"post {i}/{k}")
            db.add(post)
            db.flush()
            for j in range(1, 6):
                other = ids[(i + j) % len(ids)] if j < len(ids) else me
                db.add(models.PostComment(post_id=post.id, user_id=other, body=f"nice {j}"))
                db.add(models.PostReaction(post_id=post.id, user_id=other, reaction="fire"))
    for k in range(50):
        db.add(models.TrainingSession(user_id=me, client_session_id=f"perf-{k}", activity_key=DISTANCE_KEY,
                                      started_at=now - timedelta(days=k), duration_s=1800.0,
                                      distance_m=float(1000 + (k * 37) % 900), series_json='{"hr": []}',
                                      local_date=(now - timedelta(days=k)).date().isoformat()))
    season = models.Season(slug="perf-season", name="Perf Season", city=CITY,
                           starts_at=now - timedelta(days=3), ends_at=now + timedelta(days=30))
    db.add(season)
    db.flush()
    for uid in ids + [me]:
        db.add(models.SeasonEntry(season_id=season.id, user_id=uid))
    for c in range(8):
        community = models.Community(slug=f"perf-club-{c}", name=f"Perf Club {c}", kind="club", city=CITY,
                                     owner_user_id=ids[c % len(ids)])
        db.add(community)
        db.flush()
        for uid in ids[c::8]:
            db.add(models.CommunityMember(community_id=community.id, user_id=uid))
    merchant = models.Merchant(name="Perf Cafe", email="perf_merchant@example.com", is_active=True)
    db.add(merchant)
    db.flush()
    for b in range(20):
        bounty = models.Bounty(title=f"Chest {b}", description="Visit", merchant_id=merchant.id, target_lat=LAT + b * 0.001,
                               target_lng=LNG, radius_m=50.0, max_completions=100, completions_count=1)
        db.add(bounty)
        db.flush()
        db.add(models.BountyCompletion(bounty_id=bounty.id, user_id=ids[b % len(ids)], coupon_code_issued=f"C{b}"))
    admin = models.Admin(email="perf_admin@example.com", hashed_password=security.get_password_hash(PASSWORD),
                         name="Perf Admin")
    db.add(admin)
    db.commit()
    merchant_id = merchant.id
    db.close()
    r = client.post("/api/v1/auth/login", json={"email": "perf_admin@example.com", "password": PASSWORD,
                                                "device_timestamp": now.isoformat() + "+00:00"})
    assert r.status_code == 200, r.text
    admin_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return {"client": client, "player": player, "admin": admin_headers, "merchant_id": merchant_id}


def endpoints(ctx: dict) -> list[tuple[str, str, dict, dict]]:
    """(label, path, params, headers) for every audited endpoint."""
    near = {"lat": LAT, "lng": LNG}
    p, a = ctx["player"], ctx["admin"]
    return [
        ("arise domains", "/api/v2/arise/domains", near, p),
        ("arise routes", "/api/v2/arise/routes", near, p),
        ("v1 domains nearby", "/api/v1/domains/nearby", near, p),
        ("season leaderboard", "/api/v2/seasons/perf-season/leaderboard", {}, p),
        ("city leaderboard", "/api/v2/leaderboards/local", {}, p),
        ("global board", "/api/v2/leaderboards/global", {"board": "distance"}, p),
        ("training sessions", "/api/v2/me/training/sessions", {"limit": 50}, p),
        ("feed posts", "/api/v2/feed/posts", {"limit": 50}, p),
        ("social feed", "/api/v2/social/feed", {"limit": 50}, p),
        ("suggested osirians", "/api/v2/osirians/suggested", {}, p),
        ("bounties nearby", "/api/v1/bounties/nearby", near, p),
        ("merchant bounties", f"/api/v1/merchants/{ctx['merchant_id']}/bounties", {}, a),
    ]


def measure(ctx: dict) -> list[tuple[str, int, int]]:
    """(label, status, queries) per endpoint."""
    out = []
    for label, path, params, headers in endpoints(ctx):
        _count[0] = 0
        status = ctx["client"].get(path, params=params, headers=headers).status_code
        out.append((label, status, _count[0]))
    return out


def main_cli() -> None:
    players = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    rows = measure(seed(players))
    width = max(len(label) for label, _, _ in rows)
    sys.stdout.write(f"{'endpoint'.ljust(width)}  status  queries   ({players} players)\n")
    for label, status, queries in rows:
        sys.stdout.write(f"{label.ljust(width)}  {status:>6}  {queries:>7}\n")


if __name__ == "__main__":
    main_cli()
