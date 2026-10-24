"""Seed a launch city so its map is never empty (growth release G3).

Creates, idempotently:
- the "Osiris Official" player account that owns official content;
- official starter courses and their free challenges, from waypoint routes in the config;
- verified partner communities (running clubs, gyms, ...) with featured challenges;
- the city season.

Official courses go through the same pipeline as any player's: a run is uploaded at the
configured benchmark pace, verified by `run_verifier`, trimmed for privacy, registered,
and published with immutable terms. Nothing is written around the rules.

Challenges last at most 30 days (MAX_WINDOW_HOURS), so re-run this monthly (or from a
scheduler). Existing open challenges are left alone; closed ones are re-published.

Usage (from Osiris_backend/):
    OSIRIS_ENV=dev python scripts/seed_city.py seeds/bedford_ns.example.json

Routes must be walked on the ground before launch: well lit, public, on paths or
sidewalks, and with 150 m of lead-in at each end (the privacy trim removes it).
"""
from __future__ import annotations

import json
import math
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

os.environ.setdefault("OSIRIS_ENV", "dev")

from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402,F401  (creates missing tables)
from core import security  # noqa: E402
from services import progression  # noqa: E402
import models  # noqa: E402
from services import challenges as challenge_rules  # noqa: E402
from services import leaderboards as lb  # noqa: E402

OFFICIAL_NAME = "Osiris Official"
STEP_SECONDS = 5


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


def _route_points(waypoints: list, pace_s_per_km: float) -> list[dict]:
    speed = 1000.0 / pace_s_per_km
    pts = [{"sequence": 0, "t_ms": 0, "lat": waypoints[0][0], "lng": waypoints[0][1], "accuracy_m": 5}]
    t = 0.0
    for a, b in zip(waypoints, waypoints[1:]):
        leg = challenge_rules.distance_m(tuple(a), tuple(b))
        n = max(1, math.ceil(leg / (speed * STEP_SECONDS)))
        for i in range(1, n + 1):
            f = i / n
            t += leg / n / speed
            pts.append({"sequence": len(pts), "t_ms": int(t * 1000),
                        "lat": a[0] + (b[0] - a[0]) * f, "lng": a[1] + (b[1] - a[1]) * f, "accuracy_m": 5})
    return pts


def _official_account(email: str) -> tuple[int, dict]:
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is None:
            user = models.User(email=email, hashed_password=security.get_password_hash(secrets.token_urlsafe(24)),
                               xp=0, rank=progression.get_rank(0), title=progression.get_title(0.0), cumulative_area=0.0,
                               streak=0, mana_crystals=0, avatar_class="Official")
            db.add(user)
            db.flush()
        profile = db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == user.id).first()
        if profile is None:
            import growth_api
            profile = growth_api.get_or_create_profile(db, user)
        profile.display_name = OFFICIAL_NAME
        profile.public_profile = False
        db.commit()
        uid = user.id
    finally:
        db.close()
    token = security.create_access_token({"sub": str(uid), "role": "player"})
    return uid, {"Authorization": f"Bearer {token}"}


def _ensure_course(client: TestClient, headers: dict, owner_id: int, route: dict) -> int:
    db = database.SessionLocal()
    try:
        existing = db.query(models.Course).filter(
            models.Course.owner_id == owner_id, models.Course.name == route["name"]).first()
        if existing is not None:
            return existing.id
    finally:
        db.close()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    r = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _iso(now)})
    r.raise_for_status()
    run_id = r.json()["id"]
    client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _iso(now)}).raise_for_status()
    points = _route_points(route["waypoints"], route["benchmark_pace_s_per_km"])
    for i in range(0, len(points), 400):
        client.post(f"/api/v2/runs/{run_id}/points", headers=headers,
                    json={"points": points[i:i + 400]}).raise_for_status()
    r = client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _iso(now + timedelta(milliseconds=points[-1]["t_ms"])),
        "idempotency_key": f"seed-run-{lb.slugify(route['name'])}-{secrets.token_hex(4)}",
    })
    r.raise_for_status()
    if r.json()["verification_status"] != "accepted":
        raise SystemExit(f"Route '{route['name']}' failed run verification: {r.json()}")
    r = client.post("/api/v2/courses", headers=headers, json={"run_id": run_id, "name": route["name"]})
    if r.status_code != 201:
        raise SystemExit(f"Route '{route['name']}' could not become a course: {r.text}")
    return r.json()["id"]


def _ensure_open_challenge(client: TestClient, headers: dict, course_id: int, route: dict) -> int:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    r = client.post("/api/v2/challenges", headers=headers, json={
        "course_id": course_id, "title": route.get("challenge_title", route["name"]),
        "window_hours": min(challenge_rules.MAX_WINDOW_HOURS, 24 * int(route.get("window_days", 30))),
        "safety_notes": route.get("safety_notes"), "idempotency_key": f"seed:{course_id}:{today}",
    })
    if r.status_code == 201:
        return r.json()["id"]
    if r.status_code == 409 and r.json()["detail"]["code"] == "CHALLENGE_ALREADY_OPEN":
        db = database.SessionLocal()
        try:
            return db.query(models.Challenge).filter(
                models.Challenge.course_id == course_id, models.Challenge.status == "open").first().id
        finally:
            db.close()
    raise SystemExit(f"Could not publish challenge for '{route['name']}': {r.text}")


def _ensure_community(owner_id: int, spec: dict, city: str) -> str:
    db = database.SessionLocal()
    try:
        slug = lb.slugify(spec.get("slug") or spec["name"])
        c = db.query(models.Community).filter(models.Community.slug == slug).first()
        if c is None:
            c = models.Community(slug=slug, name=spec["name"], kind=spec["kind"], owner_user_id=owner_id,
                                 city=city, visibility=spec.get("visibility", "public"))
            db.add(c)
            db.flush()
            db.add(models.CommunityMember(community_id=c.id, user_id=owner_id, role="owner"))
        c.description = spec.get("description")
        c.brand_color = spec.get("brand_color")
        c.perk_text = spec.get("perk_text")
        c.weekly_team_goal_km = float(spec.get("weekly_team_goal_km", 100))
        c.verified = True
        if c.visibility == "private" and not c.join_code:
            c.join_code = secrets.token_hex(3).upper()
        db.commit()
        return slug
    finally:
        db.close()


def _ensure_season(spec: dict, city: str) -> str:
    db = database.SessionLocal()
    try:
        slug = lb.slugify(spec.get("slug") or spec["name"])
        s = db.query(models.Season).filter(models.Season.slug == slug).first()
        if s is None:
            s = models.Season(slug=slug, name=spec["name"], city=city,
                              starts_at=datetime.fromisoformat(spec["starts_at"]),
                              ends_at=datetime.fromisoformat(spec["ends_at"]))
            db.add(s)
        s.description = spec.get("description")
        s.perk_text = spec.get("perk_text")
        db.commit()
        return slug
    finally:
        db.close()


def seed(config: dict) -> dict:
    """Seed one city from a config dict. Returns what exists afterwards."""
    city = lb.slugify(config["city"])
    client = TestClient(main.app)
    owner_id, headers = _official_account(config.get("official_email", "official@osiris.invalid"))
    challenges: dict[str, int] = {}
    for route in config.get("routes", []):
        course_id = _ensure_course(client, headers, owner_id, route)
        challenges[route["name"]] = _ensure_open_challenge(client, headers, course_id, route)
    communities = []
    for spec in config.get("communities", []):
        slug = _ensure_community(owner_id, spec, city)
        communities.append(slug)
        for name in spec.get("featured_routes", []):
            if name in challenges:
                client.post(f"/api/v2/communities/{slug}/challenges/{challenges[name]}",
                            headers=headers).raise_for_status()
    season = _ensure_season(config["season"], city) if config.get("season") else None
    return {"city": city, "official_user_id": owner_id, "challenges": challenges,
            "communities": communities, "season": season}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/seed_city.py <city-config.json>")
    with open(sys.argv[1], encoding="utf-8") as fh:
        result = seed(json.load(fh))
    print(json.dumps(result, indent=2))
