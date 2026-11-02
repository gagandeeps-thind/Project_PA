"""Arise tab: public routes, domains and attacks, heatmaps.

Run directly from the backend directory:
    python tests/test_arise.py
"""
import base64
import math
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "arise-test-secret-aaaaaaaaaaaaaaaaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import growth_api  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from services import arise  # noqa: E402
from services import challenges as rules  # noqa: E402

PREFIX = "arise_test_"
PASSWORD = "AriseTest1!"
M_PER_DEG_LAT = 111_195.0
# Far from the other suites' fixtures so nearby queries only see this suite's rows.
BASE = (45.9000, -66.6000)
FAR = (46.5000, -66.6000)

client = TestClient(main.app)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _north(origin, metres):
    return (origin[0] + metres / M_PER_DEG_LAT, origin[1])


def _east(origin, metres):
    return (origin[0], origin[1] + metres / (M_PER_DEG_LAT * math.cos(math.radians(origin[0]))))


def _path(waypoints, speed_mps, step_s=10):
    """Timed points along straight legs between waypoints at a constant speed."""
    pts, t = [(waypoints[0][0], waypoints[0][1], 0)], 0.0
    for a, b in zip(waypoints, waypoints[1:]):
        leg = rules.distance_m(a, b)
        n = max(1, math.ceil(leg / (speed_mps * step_s)))
        for i in range(1, n + 1):
            f = i / n
            t += leg / n / speed_mps
            pts.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, int(t * 1000)))
    return pts


def _square(origin, side_m, speed_mps):
    """A closed loop: north, east, south, west back to the start."""
    a = origin
    b = _north(a, side_m)
    c = _east(b, side_m)
    d = _east(a, side_m)
    return _path([a, b, c, d, a], speed_mps)


def _cleanup() -> None:
    db = database.SessionLocal()
    try:
        ids = [u.id for u in db.query(models.User).filter(models.User.email.like(PREFIX + "%")).all()]
        if ids:
            if hasattr(models, "AriseAttack"):
                db.query(models.AriseAttack).filter(models.AriseAttack.attacker_id.in_(ids)).delete(synchronize_session=False)
            domain_ids = [d.id for d in db.query(models.Domain).filter(models.Domain.owner_id.in_(ids)).all()]
            if domain_ids and hasattr(models, "DomainPhoto"):
                db.query(models.DomainPhoto).filter(models.DomainPhoto.domain_id.in_(domain_ids)).delete(synchronize_session=False)
            if domain_ids and hasattr(models, "AriseAttack"):
                db.query(models.AriseAttack).filter(models.AriseAttack.domain_id.in_(domain_ids)).delete(synchronize_session=False)
            db.query(models.Domain).filter(models.Domain.owner_id.in_(ids)).delete(synchronize_session=False)
            course_ids = [c.id for c in db.query(models.Course).filter(models.Course.owner_id.in_(ids)).all()]
            db.query(models.AuditEvent).filter(
                ((models.AuditEvent.entity_type == "course") & models.AuditEvent.entity_id.in_(course_ids or [-1]))
                | ((models.AuditEvent.actor_type == "player") & models.AuditEvent.actor_id.in_(ids))
                | ((models.AuditEvent.entity_type == "user") & models.AuditEvent.entity_id.in_(ids))
            ).delete(synchronize_session=False)
            db.query(models.Course).filter(models.Course.owner_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.UserBadge).filter(models.UserBadge.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.ExerciseSession).filter(models.ExerciseSession.user_id.in_(ids)).delete(synchronize_session=False)
            run_ids = [r.id for r in db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).all()]
            if run_ids:
                db.query(models.AuditEvent).filter(
                    (models.AuditEvent.entity_type == "run_session") & models.AuditEvent.entity_id.in_(run_ids)
                ).delete(synchronize_session=False)
                db.query(models.VerificationDecision).filter(models.VerificationDecision.run_session_id.in_(run_ids)).delete(synchronize_session=False)
                db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.ActivityLog).filter(models.ActivityLog.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id.in_(ids)).delete(synchronize_session=False)
            growth_api.delete_growth_data(db, ids)
            db.query(models.User).filter(models.User.id.in_(ids)).delete(synchronize_session=False)
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


def _run(headers: dict, points, key: str, activity_type: str = "run", finish: bool = True) -> int:
    """Create/start/upload/finish a run; returns its id."""
    r = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now(), "activity_type": activity_type})
    assert r.status_code in (200, 201), r.text
    run_id = r.json()["id"]
    assert client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _now()}).status_code == 200
    payload = [
        {"sequence": i, "t_ms": t, "lat": lat, "lng": lng, "accuracy_m": 5}
        for i, (lat, lng, t) in enumerate(points)
    ]
    for i in range(0, len(payload), 400):
        r = client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": payload[i:i + 400]})
        assert r.status_code == 200, r.text
    if not finish:
        return run_id
    r = client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _now(), "idempotency_key": f"{PREFIX}{key}",
    })
    assert r.status_code == 200, r.text
    assert r.json()["verification_status"] == "accepted", r.json()
    db = database.SessionLocal()
    try:
        run = db.query(models.RunSession).filter(models.RunSession.id == run_id).first()
        run.started_at = run.finished_at - timedelta(seconds=run.duration_seconds + 30)
        run.created_at = run.started_at
        db.commit()
    finally:
        db.close()
    return run_id


def _publish(headers, run_id, hide_ends=True, name="River loop"):
    return client.post("/api/v2/arise/routes", headers=headers, json={
        "run_session_id": run_id, "name": name, "hide_ends": hide_ends,
    })


# --- routes -----------------------------------------------------------------------

def test_trail_runs_can_be_recorded() -> None:
    headers, _ = _player("trail")
    r = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now(), "activity_type": "trail"})
    assert r.status_code in (200, 201), r.text
    print("PASS test_trail_runs_can_be_recorded")


def test_publish_with_hidden_ends_shows_only_the_trimmed_line() -> None:
    headers, _ = _player("hider")
    start = BASE
    run_id = _run(headers, _path([start, _north(start, 1500)], 3.0), "hider", activity_type="hike")
    r = _publish(headers, run_id, hide_ends=True)
    assert r.status_code == 201, r.text
    route = r.json()
    assert route["activity_type"] == "hike"
    assert route["hide_ends"] is True
    first = tuple(route["line"][0])
    assert rules.distance_m(first, start) >= 100, rules.distance_m(first, start)
    assert "start_lat" not in route and "route_json" not in route
    again = _publish(headers, run_id, hide_ends=True)
    assert again.status_code == 201 and again.json()["id"] == route["id"]
    print("PASS test_publish_with_hidden_ends_shows_only_the_trimmed_line")


def test_publish_with_visible_ends_starts_at_the_run_start() -> None:
    headers, _ = _player("shower")
    start = _east(BASE, 3000)
    run_id = _run(headers, _path([start, _north(start, 1500)], 3.0), "shower")
    r = _publish(headers, run_id, hide_ends=False)
    assert r.status_code == 201, r.text
    assert rules.distance_m(tuple(r.json()["line"][0]), start) <= 5
    print("PASS test_publish_with_visible_ends_starts_at_the_run_start")


def test_unfinished_and_foreign_runs_cannot_be_published() -> None:
    headers, _ = _player("owner")
    other, _ = _player("stranger")
    start = _east(BASE, 6000)
    open_run = _run(headers, _path([start, _north(start, 1500)], 3.0), "open", finish=False)
    assert _publish(headers, open_run).status_code == 409
    done = _run(headers, _path([_east(start, 500), _north(_east(start, 500), 1500)], 3.0), "done")
    assert _publish(other, done).status_code == 403
    print("PASS test_unfinished_and_foreign_runs_cannot_be_published")


def test_nearby_routes_lists_public_routes_within_the_radius() -> None:
    headers, _ = _player("lister")
    start = _east(BASE, 9000)
    run_id = _run(headers, _path([start, _north(start, 1500)], 3.0), "lister", activity_type="walk")
    published = _publish(headers, run_id).json()
    near = client.get("/api/v2/arise/routes", headers=headers, params={"lat": start[0], "lng": start[1], "radius_km": 5})
    assert near.status_code == 200, near.text
    assert published["id"] in [r["id"] for r in near.json()]
    far = client.get("/api/v2/arise/routes", headers=headers, params={"lat": FAR[0], "lng": FAR[1], "radius_km": 5})
    assert published["id"] not in [r["id"] for r in far.json()]
    print("PASS test_nearby_routes_lists_public_routes_within_the_radius")


def test_public_line_helper() -> None:
    full = [(0.0, 0.0), (0.0, 0.001), (0.0, 0.002)]
    trimmed = [(0.0, 0.001)]
    assert arise.public_line(full, trimmed, hide_ends=True) == [[0.0, 0.001]]
    assert arise.public_line(full, trimmed, hide_ends=False) == [[0.0, 0.0], [0.0, 0.001], [0.0, 0.002]]
    print("PASS test_public_line_helper")


# --- domains and attacks ----------------------------------------------------------

def _session(user_id: int, key: str, reps: int) -> None:
    """A verified camera set, as the exercise upload would store it."""
    db = database.SessionLocal()
    try:
        db.add(models.ExerciseSession(
            user_id=user_id, client_session_id=f"{PREFIX}{user_id}-{key}-{reps}-{datetime.now().timestamp()}",
            exercise_key=key, rules_version="test", duration_s=30.0, reps_attempted=reps, reps_valid=reps,
            client_verdict="pass", status="verified", local_date=datetime.now().date().isoformat(),
        ))
        db.commit()
    finally:
        db.close()


def _claim(headers, origin, side=400, speed=3.0, key="claim"):
    run_id = _run(headers, _square(origin, side, speed), key)
    return client.post("/api/v2/arise/domains", headers=headers, json={"run_session_id": run_id})


def test_workout_generator_bounds_and_determinism() -> None:
    keys = ["pushup", "squat", "lunge", "situp", "burpee"]
    for level in (1, 5, 15, 40):
        w = arise.generate_workout(1234, level, keys)
        total = sum(s["reps"] for s in w)
        assert total == arise.total_reps(level), (level, total)
        assert 30 <= total <= 100
        assert 3 <= len(w) <= 6
        assert all(10 <= s["rest_s"] <= 30 and s["exercise_key"] in keys and s["reps"] >= 5 for s in w)
    assert arise.generate_workout(7, 3, keys) == arise.generate_workout(7, 3, keys)
    assert arise.player_level(0) == 1 and arise.player_level(10**6) == 15
    print("PASS test_workout_generator_bounds_and_determinism")


def test_only_an_accepted_loop_claims_a_domain() -> None:
    headers, _ = _player("claimer")
    origin = _north(BASE, 4000)
    straight = _run(headers, _path([origin, _north(origin, 1500)], 3.0), "straight")
    r = client.post("/api/v2/arise/domains", headers=headers, json={"run_session_id": straight})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "NOT_A_LOOP", r.text
    r = _claim(headers, _east(origin, 2000), key="loop")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["distance_m"] > 1400 and d["duration_s"] > 400 and d["area_sqkm"] > 0.1
    assert d["workout"] is None
    again = client.post("/api/v2/arise/domains", headers=headers, json={"run_session_id": d["source_run_session_id"]})
    assert again.status_code == 409
    print("PASS test_only_an_accepted_loop_claims_a_domain")


def test_exceed_attaches_the_workout_only_when_every_set_is_done() -> None:
    headers, uid = _player("exceeder")
    d = _claim(headers, _north(BASE, 8000), key="exceed").json()
    w = client.post(f"/api/v2/arise/domains/{d['id']}/workout", headers=headers)
    assert w.status_code == 200, w.text
    sets = w.json()["sets"]
    for s in sets[:-1]:
        _session(uid, s["exercise_key"], s["reps"])
    r = client.post(f"/api/v2/arise/domains/{d['id']}/workout/complete", headers=headers)
    assert r.status_code == 200 and r.json()["completed"] is False, r.text
    _session(uid, sets[-1]["exercise_key"], sets[-1]["reps"])
    r = client.post(f"/api/v2/arise/domains/{d['id']}/workout/complete", headers=headers)
    assert r.json()["completed"] is True, r.text
    assert r.json()["domain"]["workout"]["sets"] == sets
    print("PASS test_exceed_attaches_the_workout_only_when_every_set_is_done")


def test_attack_rules() -> None:
    defender, _ = _player("defender")
    attacker, attacker_id = _player("attacker")
    origin = _north(BASE, 12000)
    d = _claim(defender, origin, side=400, speed=3.0, key="def").json()
    start = _north(_east(origin, -25), -25)

    def attack(points, key):
        run_id = _run(attacker, points, key)
        return client.post(f"/api/v2/arise/domains/{d['id']}/attack", headers=attacker, json={"run_session_id": run_id})

    own = client.post(
        f"/api/v2/arise/domains/{d['id']}/attack", headers=defender, json={"run_session_id": d["source_run_session_id"]},
    )
    assert own.status_code == 409, own.text
    slow = attack(_square(start, 450, 2.8), "slow").json()
    assert slow["status"] == "failed" and "TOO_SLOW" in slow["reasons"], slow
    short = attack(_square(_north(_east(origin, 100), 100), 250, 4.0), "short").json()
    assert short["status"] == "failed" and "TOO_SHORT" in short["reasons"], short
    away = attack(_square(_north(origin, 3000), 450, 4.0), "away").json()
    assert away["status"] == "failed" and "NOT_ENCLOSING" in away["reasons"], away
    listed = client.get(
        "/api/v2/arise/domains", headers=attacker, params={"lat": origin[0], "lng": origin[1], "radius_km": 5},
    ).json()
    assert d["id"] in [x["id"] for x in listed["suggested"]], listed
    won = attack(_square(start, 450, 4.0), "won").json()
    assert won["status"] == "won", won
    db = database.SessionLocal()
    try:
        assert db.query(models.Domain).filter(models.Domain.id == d["id"]).one().owner_id == attacker_id
    finally:
        db.close()
    print("PASS test_attack_rules")


def test_a_defended_domain_needs_the_same_workout() -> None:
    defender, defender_id = _player("wall")
    attacker, attacker_id = _player("raider")
    origin = _north(BASE, 16000)
    d = _claim(defender, origin, key="wall").json()
    sets = client.post(f"/api/v2/arise/domains/{d['id']}/workout", headers=defender).json()["sets"]
    for s in sets:
        _session(defender_id, s["exercise_key"], s["reps"])
    assert client.post(f"/api/v2/arise/domains/{d['id']}/workout/complete", headers=defender).json()["completed"]
    run_id = _run(attacker, _square(_north(_east(origin, -25), -25), 450, 4.0), "raid")
    r = client.post(f"/api/v2/arise/domains/{d['id']}/attack", headers=attacker, json={"run_session_id": run_id}).json()
    assert r["status"] == "needs_workout" and r["workout"]["sets"] == sets, r
    pending = client.post(f"/api/v2/arise/attacks/{r['attack_id']}/workout/complete", headers=attacker).json()
    assert pending["status"] == "needs_workout", pending
    for s in sets:
        _session(attacker_id, s["exercise_key"], s["reps"])
    done = client.post(f"/api/v2/arise/attacks/{r['attack_id']}/workout/complete", headers=attacker).json()
    assert done["status"] == "won", done
    print("PASS test_a_defended_domain_needs_the_same_workout")


def test_domain_photo_owner_only_and_limited() -> None:
    owner, _ = _player("painter")
    other, _ = _player("vandal")
    d = _claim(owner, _north(BASE, 20000), key="photo").json()
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 1000
    body = {"jpeg_base64": base64.b64encode(jpeg).decode()}
    url = f"/api/v2/arise/domains/{d['id']}/photo"
    assert client.put(url, headers=other, json=body).status_code == 403
    gif = {"jpeg_base64": base64.b64encode(b"GIF89a").decode()}
    assert client.put(url, headers=owner, json=gif).status_code == 422
    big = {"jpeg_base64": base64.b64encode(b"\xff\xd8" + b"0" * 350_000).decode()}
    assert client.put(url, headers=owner, json=big).status_code == 413
    r = client.put(url, headers=owner, json=body)
    assert r.status_code == 200 and r.json()["photo_url"], r.text
    got = client.get(url)
    assert got.status_code == 200 and got.content == jpeg and got.headers["content-type"] == "image/jpeg"
    print("PASS test_domain_photo_owner_only_and_limited")


# --- heatmaps -----------------------------------------------------------------------

HEAT = _north(BASE, 30000)


def _set_times(run_id: int, started: datetime) -> None:
    db = database.SessionLocal()
    try:
        run = db.query(models.RunSession).filter(models.RunSession.id == run_id).one()
        run.started_at = started
        run.finished_at = started + timedelta(seconds=run.duration_seconds or 600)
        db.commit()
    finally:
        db.close()


def _heat(headers, kind, centre=HEAT, span=0.05):
    return client.get("/api/v2/arise/heatmap", headers=headers, params={
        "kind": kind, "min_lat": centre[0] - span, "min_lng": centre[1] - span,
        "max_lat": centre[0] + span, "max_lng": centre[1] + span,
    })


def test_heat_cells_trim_the_ends_and_hide_rare_cells() -> None:
    line = [_north(HEAT, m) for m in range(0, 1001, 10)]
    runs = [(uid, line) for uid in (1, 2)]
    assert arise.heat_cells(runs, min_players=3) == []
    cells = arise.heat_cells(runs + [(3, line)], min_players=3)
    assert cells, cells
    assert all(rules.distance_m((c[0], c[1]), HEAT) >= 150 for c in cells), "start trimmed"
    assert all(rules.distance_m((c[0], c[1]), line[-1]) >= 150 for c in cells), "finish trimmed"
    assert all(c[2] == 3 for c in cells)
    assert arise.is_night(datetime(2026, 6, 21, 3, 0), -66.6)
    assert not arise.is_night(datetime(2026, 6, 21, 16, 0), -66.6)
    print("PASS test_heat_cells_trim_the_ends_and_hide_rare_cells")


def test_heatmap_kinds() -> None:
    players = [_player(f"heat{i}") for i in range(3)]
    path = _path([HEAT, _north(HEAT, 1500)], 3.0)
    ids = [_run(h, path, f"heat{i}") for i, (h, _) in enumerate(players)]
    me = players[0][0]
    assert _heat(me, "global").json(), "three players make the cells public"
    _set_times(ids[1], datetime.now() - timedelta(days=10))
    assert _heat(me, "weekly").json() == [], "only two players ran this week"
    assert _heat(me, "personal").json(), "a player always sees their own runs"
    night = datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)
    for run_id in ids:
        _set_times(run_id, night)
    assert _heat(me, "night").json(), "03:00 UTC is 22:30 solar time at this longitude"
    too_big = client.get("/api/v2/arise/heatmap", headers=me, params={
        "kind": "global", "min_lat": 0, "min_lng": 0, "max_lat": 2, "max_lng": 2,
    })
    assert too_big.status_code == 422
    print("PASS test_heatmap_kinds")


TESTS = [
    test_public_line_helper,
    test_trail_runs_can_be_recorded,
    test_publish_with_hidden_ends_shows_only_the_trimmed_line,
    test_publish_with_visible_ends_starts_at_the_run_start,
    test_unfinished_and_foreign_runs_cannot_be_published,
    test_nearby_routes_lists_public_routes_within_the_radius,
    test_workout_generator_bounds_and_determinism,
    test_only_an_accepted_loop_claims_a_domain,
    test_exceed_attaches_the_workout_only_when_every_set_is_done,
    test_attack_rules,
    test_a_defended_domain_needs_the_same_workout,
    test_domain_photo_owner_only_and_limited,
    test_heat_cells_trim_the_ends_and_hide_rare_cells,
    test_heatmap_kinds,
]


if __name__ == "__main__":
    _cleanup()
    try:
        for test in TESTS:
            test()
    finally:
        _cleanup()
    print("ALL ARISE TESTS PASSED")
