"""R2 course and challenge pilot regression tests.

Run directly from the backend directory:
    python tests/test_challenge_release.py
"""
import math
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "challenge-release-test-secret-aaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi.testclient import TestClient

import database
import growth_api
import main
from core import security  # noqa: E402
from services import jobs  # noqa: E402
import models
from services import challenges as rules


PREFIX = "r2_challenge_test_"
PASSWORD = "ChallengeTest1!"
ADMIN_EMAIL = PREFIX + "admin@example.com"
M_PER_DEG_LAT = 111_195.0
# Far from the other suites' fixtures so nearby queries only see this suite's courses.
BASE = (44.7000, -63.5000)

client = TestClient(main.app)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _north(origin, metres):
    return (origin[0] + metres / M_PER_DEG_LAT, origin[1])


def _east(origin, metres):
    return (origin[0], origin[1] + metres / (M_PER_DEG_LAT * math.cos(math.radians(origin[0]))))


def _path(waypoints, speed_mps, step_s=10):
    """Timed points along straight legs between waypoints at a constant speed."""
    pts, t = [], 0.0
    pts.append((waypoints[0][0], waypoints[0][1], 0))
    for a, b in zip(waypoints, waypoints[1:]):
        leg = rules.distance_m(a, b)
        n = max(1, math.ceil(leg / (speed_mps * step_s)))
        for i in range(1, n + 1):
            f = i / n
            t += leg / n / speed_mps
            pts.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, int(t * 1000)))
    return pts


# The defender's run: 1.5 km due north at 3 m/s. After the 150 m privacy trim at each end
# the course is the middle 1.2 km, benchmark ~400 s.
RUN_START = BASE
RUN_END = _north(BASE, 1500)
COURSE_START = _north(BASE, 150)
COURSE_END = _north(BASE, 1350)


def _cleanup() -> None:
    db = database.SessionLocal()
    try:
        ids = [u.id for u in db.query(models.User).filter(models.User.email.like(PREFIX + "%")).all()]
        if ids:
            ch_ids = [c.id for c in db.query(models.Challenge).filter(models.Challenge.creator_id.in_(ids)).all()]
            att = db.query(models.ChallengeAttempt).filter(
                (models.ChallengeAttempt.user_id.in_(ids)) | (models.ChallengeAttempt.challenge_id.in_(ch_ids or [-1]))
            )
            att_ids = [a.id for a in att.all()]
            att.delete(synchronize_session=False)
            db.query(models.AuditEvent).filter(
                ((models.AuditEvent.entity_type == "challenge") & models.AuditEvent.entity_id.in_(ch_ids or [-1]))
                | ((models.AuditEvent.entity_type == "challenge_attempt") & models.AuditEvent.entity_id.in_(att_ids or [-1]))
                | ((models.AuditEvent.actor_type == "player") & models.AuditEvent.actor_id.in_(ids))
                | ((models.AuditEvent.entity_type == "user") & models.AuditEvent.entity_id.in_(ids))
            ).delete(synchronize_session=False)
            db.query(models.Challenge).filter(models.Challenge.creator_id.in_(ids)).delete(synchronize_session=False)
            course_ids = [c.id for c in db.query(models.Course).filter(models.Course.owner_id.in_(ids)).all()]
            db.query(models.AuditEvent).filter(
                (models.AuditEvent.entity_type == "course") & models.AuditEvent.entity_id.in_(course_ids or [-1])
            ).delete(synchronize_session=False)
            db.query(models.Course).filter(models.Course.owner_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.UserBadge).filter(models.UserBadge.user_id.in_(ids)).delete(synchronize_session=False)
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
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["id"]


def _admin() -> dict:
    db = database.SessionLocal()
    try:
        admin = models.Admin(email=ADMIN_EMAIL, hashed_password="x", name="R2 Admin")
        db.add(admin)
        db.commit()
        admin_id = admin.id
    finally:
        db.close()
    return {"Authorization": f"Bearer {security.create_access_token({'sub': str(admin_id), 'role': 'admin'})}"}


def _run(headers: dict, points, key: str) -> dict:
    """Create/start/upload/finish a run; returns the finish summary."""
    run_id = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now()}).json()["id"]
    assert client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _now()}).status_code == 200
    payload = [
        {"sequence": i, "t_ms": t, "lat": lat, "lng": lng, "accuracy_m": 5}
        for i, (lat, lng, t) in enumerate(points)
    ]
    for i in range(0, len(payload), 400):
        r = client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": payload[i:i + 400]})
        assert r.status_code == 200, r.text
    r = client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _now(), "idempotency_key": f"{PREFIX}{key}",
    })
    assert r.status_code == 200, r.text
    # Tests replay a whole run instantly; widen the server wall clock so the CLOCK_SKEW
    # check sees the real-world duration the synthetic timestamps describe.
    db = database.SessionLocal()
    try:
        run = db.query(models.RunSession).filter(models.RunSession.id == run_id).first()
        run.started_at = run.finished_at - timedelta(seconds=run.duration_seconds + 30)
        run.created_at = run.started_at
        db.commit()
    finally:
        db.close()
    return r.json()


def _set_join_time_past(attempt_id: int) -> None:
    """Joins happen 'before' the run in real life; backdate so the synthetic run counts."""
    db = database.SessionLocal()
    try:
        a = db.query(models.ChallengeAttempt).filter(models.ChallengeAttempt.id == attempt_id).first()
        a.joined_at = a.joined_at - timedelta(hours=2)
        db.commit()
    finally:
        db.close()


def _xp(user_id: int) -> int:
    db = database.SessionLocal()
    try:
        return db.query(models.User).filter(models.User.id == user_id).first().xp
    finally:
        db.close()


def _code(response) -> str:
    return response.json()["detail"]["code"]


def _challenger_route(speed):
    """Approach from the west, run the course north, then cool down a little further."""
    approach = _east(COURSE_START, -300)
    return _path([approach, COURSE_START, COURSE_END, _north(COURSE_END, 60)], speed)


# --- unit tests on the pure rules ---------------------------------------------------

def test_privacy_trim_and_public_marker() -> None:
    pts = _path([RUN_START, RUN_END], 3.0)
    trimmed = rules.trim_route(pts)
    assert 1130 <= trimmed.distance_m <= 1210, trimmed.distance_m
    assert rules.distance_m(trimmed.route[0], RUN_START) >= rules.PRIVACY_TRIM_M
    assert rules.distance_m(trimmed.route[-1], RUN_END) >= rules.PRIVACY_TRIM_M
    marker = rules.public_marker(trimmed.route)
    # The marker is a grid-cell centre, and not the course start or the run start.
    assert rules.distance_m(marker, RUN_START) > 300
    assert rules.snap_to_grid(marker) == marker


def test_terms_hash_is_stable_and_sensitive() -> None:
    opens = datetime(2026, 1, 1, 12, 0, 0)
    terms = rules.build_terms(course_id=1, course_version=1, target_seconds=400.0, win_xp=62,
                              safety_notes=None, opens_at=opens, closes_at=opens + timedelta(hours=24))
    assert rules.terms_hash(terms) == rules.terms_hash(dict(terms))
    assert terms["entry_crystals"] == 0 and terms["reward_policy"] == "xp_badge"
    changed = dict(terms, target_seconds=399.0)
    assert rules.terms_hash(changed) != rules.terms_hash(terms)
    try:
        rules.terms_hash(dict(terms, extra=1))
    except ValueError:
        pass
    else:
        raise AssertionError("terms with an unknown field must not hash")


def test_segment_timing_matches_benchmark_distance() -> None:
    course = rules.trim_route(_path([RUN_START, RUN_END], 3.0))
    route = rules.simplify_route(course.route)
    ev = rules.evaluate_attempt(
        course_route=route, course_distance=course.distance_m, target_seconds=course.elapsed_seconds,
        run_verification_status="accepted", run_points=_challenger_route(3.0),
        run_duration=10_000, run_wall_clock_seconds=None,
    )
    # Same speed as the benchmark: timed segment within a few percent of the benchmark.
    assert ev.status == "accepted", ev
    assert abs(ev.elapsed_seconds - course.elapsed_seconds) / course.elapsed_seconds < 0.05, ev
    assert ev.coverage >= 0.95


# --- end-to-end API flow ---------------------------------------------------------------

def test_course_and_challenge_lifecycle() -> None:
    _cleanup()
    defender, defender_id = _player("defender")
    challenger, challenger_id = _player("challenger")
    slowpoke, slowpoke_id = _player("slowpoke")
    rocket, rocket_id = _player("rocket")
    admin = _admin()

    # Defender verifies a run and registers it as a course (idempotent per run).
    run = _run(defender, _path([RUN_START, RUN_END], 3.0), "defender-1")
    assert run["verification_status"] == "accepted", run
    r = client.post("/api/v2/courses", headers=defender, json={"run_id": run["id"], "name": "North Straight"})
    assert r.status_code == 201, r.text
    course = r.json()
    assert 1130 <= course["distance_m"] <= 1210
    assert 360 <= course["benchmark_seconds"] <= 420
    again = client.post("/api/v2/courses", headers=defender, json={"run_id": run["id"], "name": "Dup"})
    assert again.status_code == 201 and again.json()["id"] == course["id"]

    # The same course from another run by the same owner is a duplicate.
    run2 = _run(defender, _path([RUN_START, RUN_END], 3.0), "defender-2")
    r = client.post("/api/v2/courses", headers=defender, json={"run_id": run2["id"], "name": "Again"})
    assert r.status_code == 409 and _code(r) == "DUPLICATE_COURSE", r.text

    # Publish: fixed immutable terms, no stakes; idempotent by key; one open per course.
    body = {"course_id": course["id"], "title": "Beat my straight", "window_hours": 48,
            "safety_notes": "Shared path, keep right.", "idempotency_key": PREFIX + "pub-1"}
    r = client.post("/api/v2/challenges", headers=defender, json=body)
    assert r.status_code == 201, r.text
    ch = r.json()
    assert ch["entry_crystals"] == 0 and ch["reward_policy"] == "xp_badge"
    assert ch["target_seconds"] == course["benchmark_seconds"]
    assert client.post("/api/v2/challenges", headers=defender, json=body).json()["id"] == ch["id"]
    r = client.post("/api/v2/challenges", headers=defender, json=dict(body, idempotency_key=PREFIX + "pub-2"))
    assert r.status_code == 409 and _code(r) == "CHALLENGE_ALREADY_OPEN"
    r = client.post("/api/v2/challenges", headers=challenger, json=dict(body, idempotency_key=PREFIX + "pub-3"))
    assert r.status_code == 403 and _code(r) == "NOT_COURSE_OWNER"

    # Discovery is generalized: no owner, no route, marker is not the course start.
    r = client.get("/api/v2/challenges/nearby", headers=challenger, params={"lat": BASE[0], "lng": BASE[1], "radius_km": 5})
    assert r.status_code == 200, r.text
    found = [c for c in r.json() if c["id"] == ch["id"]]
    assert found, r.json()
    public = found[0]
    for forbidden in ("creator_id", "owner_id", "route", "start_lat", "geometry"):
        assert forbidden not in public
    assert rules.distance_m((public["marker_lat"], public["marker_lng"]), COURSE_START) > 200
    assert public["is_mine"] is False

    # Route is released only after joining; eligibility needs one verified run.
    r = client.get(f"/api/v2/challenges/{ch['id']}/course", headers=challenger)
    assert r.status_code == 403 and _code(r) == "JOIN_REQUIRED"
    r = client.post(f"/api/v2/challenges/{ch['id']}/join", headers=challenger)
    assert r.status_code == 403 and _code(r) == "NOT_ELIGIBLE"
    r = client.post(f"/api/v2/challenges/{ch['id']}/join", headers=defender)
    assert r.status_code == 409 and _code(r) == "OWN_CHALLENGE"

    warmups = {}
    for name, headers in (("challenger", challenger), ("slowpoke", slowpoke), ("rocket", rocket)):
        warm = _path([_east(BASE, 3000), _north(_east(BASE, 3000), 400)], 3.0)
        warmups[name] = _run(headers, warm, f"warm-{name}")
        assert warmups[name]["verification_status"] == "accepted"

    attempts = {}
    for name, headers in (("challenger", challenger), ("slowpoke", slowpoke), ("rocket", rocket)):
        r = client.post(f"/api/v2/challenges/{ch['id']}/join", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["terms_hash"] == ch["terms_hash"]
        attempts[name] = r.json()["id"]
        assert client.post(f"/api/v2/challenges/{ch['id']}/join", headers=headers).json()["id"] == attempts[name]
    r = client.get(f"/api/v2/challenges/{ch['id']}/course", headers=challenger)
    assert r.status_code == 200 and len(r.json()["route"]) >= 2

    # A run from before joining does not count.
    r = client.post(f"/api/v2/challenges/{ch['id']}/attempts", headers=challenger, json={"run_id": warmups["challenger"]["id"]})
    assert r.status_code == 409 and _code(r) == "RUN_BEFORE_JOIN", r.text

    for name in attempts:
        _set_join_time_past(attempts[name])

    # Off-course run is rejected with reasons, and the attempt can be retried.
    off = _run(challenger, _path([_east(BASE, 800), _north(_east(BASE, 800), 1300)], 3.3), "off")
    r = client.post(f"/api/v2/challenges/{ch['id']}/attempts", headers=challenger, json={"run_id": off["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected" and "START_OUTSIDE_COURSE" in r.json()["reason_codes"]

    defender_xp_before = _xp(defender_id)

    # Faster than the benchmark -> won.
    win = _run(challenger, _challenger_route(3.4), "win")
    challenger_xp_before = _xp(challenger_id)
    r = client.post(f"/api/v2/challenges/{ch['id']}/attempts", headers=challenger, json={"run_id": win["id"]})
    assert r.status_code == 200, r.text
    won = r.json()
    assert won["status"] == "accepted" and won["outcome"] == "won", won
    assert won["xp_awarded"] == ch["win_xp"]
    assert _xp(challenger_id) == challenger_xp_before + ch["win_xp"]
    assert _xp(defender_id) == defender_xp_before
    # Idempotent re-submit of the same run.
    again = client.post(f"/api/v2/challenges/{ch['id']}/attempts", headers=challenger, json={"run_id": win["id"]})
    assert again.status_code == 200 and again.json()["outcome"] == "won"
    # A decided attempt can't be replaced.
    r = client.post(f"/api/v2/challenges/{ch['id']}/attempts", headers=challenger, json={"run_id": off["id"]})
    assert r.status_code == 409 and _code(r) == "ATTEMPT_ALREADY_DECIDED"

    # Slower than the benchmark -> lost; defender earns defense XP.
    slow = _run(slowpoke, _challenger_route(2.6), "slow")
    r = client.post(f"/api/v2/challenges/{ch['id']}/attempts", headers=slowpoke, json={"run_id": slow["id"]})
    assert r.json()["outcome"] == "lost", r.text
    assert _xp(defender_id) == defender_xp_before + rules.DEFENSE_XP

    # Implausibly fast (under 75% of benchmark) -> human review, not an automatic win.
    fast = _run(rocket, _challenger_route(5.5), "fast")
    r = client.post(f"/api/v2/challenges/{ch['id']}/attempts", headers=rocket, json={"run_id": fast["id"]})
    assert r.json()["status"] == "review_required", r.text
    rocket_xp = _xp(rocket_id)
    queue = client.get("/api/v2/admin/review-queue", headers=admin).json()
    assert any(item["attempt_id"] == attempts["rocket"] for item in queue)
    assert client.get("/api/v2/admin/review-queue", headers=challenger).status_code == 403
    r = client.post(f"/api/v2/admin/attempts/{attempts['rocket']}/review", headers=admin,
                    json={"decision": "accept", "note": "Verified with race footage."})
    assert r.status_code == 200 and r.json()["outcome"] == "won", r.text
    assert _xp(rocket_id) == rocket_xp + ch["win_xp"]

    # Progression shows badges and the versioned rank.
    prog = client.get("/api/v2/me/progression", headers=defender).json()
    codes = {b["code"] for b in prog["badges"]}
    assert {"FIRST_VERIFIED_RUN", "FIRST_COURSE", "FIRST_CHALLENGE_PUBLISHED", "FIRST_DEFENSE"} <= codes
    assert prog["rank_ladder_version"] == rules.RANK_LADDER_VERSION and prog["defenses"] == 1
    assert "FIRST_CHALLENGE_WIN" in {b["code"] for b in client.get("/api/v2/me/progression", headers=challenger).json()["badges"]}

    # Voiding reverses every XP award and marks attempts voided.
    challenger_xp = _xp(challenger_id)
    defender_xp = _xp(defender_id)
    r = client.post(f"/api/v2/admin/challenges/{ch['id']}/status", headers=admin,
                    json={"action": "void", "reason": "Course crossed a closed road."})
    assert r.status_code == 200 and r.json()["status"] == "voided", r.text
    assert _xp(challenger_id) == challenger_xp - ch["win_xp"]
    assert _xp(defender_id) == defender_xp - rules.DEFENSE_XP
    mine = client.get(f"/api/v2/challenges/{ch['id']}", headers=challenger).json()["my_attempt"]
    assert mine["outcome"] == "voided"

    # Every step left an audit trail.
    events = client.get("/api/v2/admin/audit-events", headers=admin,
                        params={"entity_type": "challenge", "entity_id": ch["id"]}).json()
    actions = {e["action"] for e in events}
    assert {"challenge.published", "challenge.void"} <= actions, actions


def test_settlement_and_suspension() -> None:
    _cleanup()
    defender, defender_id = _player("defender")
    admin = _admin()
    run = _run(defender, _path([RUN_START, RUN_END], 3.0), "settle-1")
    course = client.post("/api/v2/courses", headers=defender, json={"run_id": run["id"], "name": "Settle"}).json()
    ch = client.post("/api/v2/challenges", headers=defender, json={
        "course_id": course["id"], "title": "Short window", "window_hours": 1,
        "idempotency_key": PREFIX + "settle-pub",
    }).json()

    # Past the window plus grace -> the scheduled job settles it.
    db = database.SessionLocal()
    try:
        row = db.query(models.Challenge).filter(models.Challenge.id == ch["id"]).first()
        row.closes_at = row.closes_at - timedelta(hours=3)
        db.commit()
    finally:
        db.close()
    jobs.process_challenge_settlement()
    assert client.get(f"/api/v2/challenges/{ch['id']}", headers=defender).json()["status"] == "settled"

    # Suspended players are locked out of the v2 API until unsuspended.
    r = client.post(f"/api/v2/admin/users/{defender_id}/suspend", headers=admin, json={"reason": "Harassment report"})
    assert r.status_code == 200 and r.json()["suspended"] is True
    r = client.get("/api/v2/courses", headers=defender)
    assert r.status_code == 403 and _code(r) == "ACCOUNT_SUSPENDED"
    assert client.post(f"/api/v2/admin/users/{defender_id}/unsuspend", headers=admin).status_code == 200
    assert client.get("/api/v2/courses", headers=defender).status_code == 200

    # Suspending a course suspends its live challenges and hides them from discovery.
    ch2 = client.post("/api/v2/challenges", headers=defender, json={
        "course_id": course["id"], "title": "Second window", "window_hours": 24,
        "idempotency_key": PREFIX + "settle-pub-2",
    }).json()
    r = client.post(f"/api/v2/admin/courses/{course['id']}/suspend", headers=admin, json={"reason": "Sensitive site"})
    assert r.status_code == 200 and r.json()["suspended_challenges"] == 1
    nearby = client.get("/api/v2/challenges/nearby", headers=defender, params={"lat": BASE[0], "lng": BASE[1]}).json()
    assert all(c["id"] != ch2["id"] for c in nearby)


def test_short_run_cannot_become_course() -> None:
    _cleanup()
    player, _ = _player("shorty")
    run = _run(player, _path([RUN_START, _north(RUN_START, 500)], 3.0), "short")
    assert run["verification_status"] == "accepted"
    r = client.post("/api/v2/courses", headers=player, json={"run_id": run["id"], "name": "Too short"})
    assert r.status_code == 422 and _code(r) == "COURSE_TOO_SHORT", r.text


if __name__ == "__main__":
    for test in (
        test_privacy_trim_and_public_marker,
        test_terms_hash_is_stable_and_sensitive,
        test_segment_timing_matches_benchmark_distance,
        test_course_and_challenge_lifecycle,
        test_settlement_and_suspension,
        test_short_run_cannot_become_course,
    ):
        test()
        print(f"PASS {test.__name__}")
    _cleanup()
