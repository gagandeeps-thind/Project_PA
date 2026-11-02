"""Arise tab: public routes, domains and attacks, heatmaps.

Run directly from the backend directory:
    python tests/test_arise.py
"""
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


TESTS = [
    test_public_line_helper,
    test_trail_runs_can_be_recorded,
    test_publish_with_hidden_ends_shows_only_the_trimmed_line,
    test_publish_with_visible_ends_starts_at_the_run_start,
    test_unfinished_and_foreign_runs_cannot_be_published,
    test_nearby_routes_lists_public_routes_within_the_radius,
]


if __name__ == "__main__":
    _cleanup()
    try:
        for test in TESTS:
            test()
    finally:
        _cleanup()
    print("ALL ARISE TESTS PASSED")
