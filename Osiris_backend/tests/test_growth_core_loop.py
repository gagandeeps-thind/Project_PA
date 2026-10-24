"""Growth G1 regression tests: BMI-free registration, daily quests, rest-friendly weekly
streaks, and funnel analytics.

Run directly from the backend directory:
    python tests/test_growth_core_loop.py
"""
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "growth-core-loop-test-secret-aaaaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi.testclient import TestClient

import database
import main
from core import security  # noqa: E402
import growth_api
import models
from services import quests as q


PREFIX = "growth_g1_test_"
PASSWORD = "GrowthTest1!"
ADMIN_EMAIL = PREFIX + "admin@example.com"
M_PER_DEG_LAT = 111_195.0
BASE = (44.9000, -63.9000)

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
            run_ids = [r.id for r in db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).all()]
            growth_api.delete_growth_data(db, ids)
            db.query(models.AuditEvent).filter(
                ((models.AuditEvent.actor_type == "player") & models.AuditEvent.actor_id.in_(ids))
                | ((models.AuditEvent.entity_type == "user") & models.AuditEvent.entity_id.in_(ids))
                | ((models.AuditEvent.entity_type == "run_session") & models.AuditEvent.entity_id.in_(run_ids or [-1]))
            ).delete(synchronize_session=False)
            if run_ids:
                db.query(models.VerificationDecision).filter(models.VerificationDecision.run_session_id.in_(run_ids)).delete(synchronize_session=False)
                db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(models.RunSession).filter(models.RunSession.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.ActivityLog).filter(models.ActivityLog.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.UserBadge).filter(models.UserBadge.user_id.in_(ids)).delete(synchronize_session=False)
            # Ledger rows must go too: SQLite reuses freed user ids, so orphans would be inherited.
            db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_(ids)).delete(synchronize_session=False)
        db.query(models.AnalyticsEvent).filter(models.AnalyticsEvent.install_id.like(PREFIX + "%")).delete(synchronize_session=False)
        db.query(models.Admin).filter(models.Admin.email == ADMIN_EMAIL).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _register(name: str, goal: str = "running", referral_code=None):
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}{name}@example.com", "password": PASSWORD, "display_name": name.title(), "location_consent": True,
        "goal": goal, "referral_code": referral_code, "install_id": f"{PREFIX}{name}",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["profile"]


def _run(headers, metres, key):
    pts = _path(BASE, _north(BASE, metres))
    run_id = client.post("/api/v2/runs", headers=headers, json={"device_started_at": _now()}).json()["id"]
    assert client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _now()}).status_code == 200
    r = client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": [
        {"sequence": i, "t_ms": t, "lat": lat, "lng": lng, "accuracy_m": 5} for i, (lat, lng, t) in enumerate(pts)
    ]})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _now(), "idempotency_key": f"{PREFIX}{key}",
    })
    assert r.status_code == 200, r.text
    return r.json()


def _admin() -> dict:
    db = database.SessionLocal()
    try:
        admin = models.Admin(email=ADMIN_EMAIL, hashed_password="x", name="G1 Admin")
        db.add(admin)
        db.commit()
        admin_id = admin.id
    finally:
        db.close()
    return {"Authorization": f"Bearer {security.create_access_token({'sub': str(admin_id), 'role': 'admin'})}"}


# --- pure rules ---------------------------------------------------------------------

def test_starter_quest_for_new_player() -> None:
    quest = q.daily_quest("running", date(2026, 9, 28), {})
    assert quest.kind == "starter" and quest.target_m == 1000 and not quest.optional


def test_quest_scales_with_history_and_is_capped() -> None:
    today = date(2026, 9, 28)   # Monday
    history = {today - timedelta(days=d): 3000.0 for d in (2, 4, 6, 9)}
    quest = q.daily_quest("running", today, history)
    assert quest.kind == "steady" and quest.target_m == 3000, quest
    # A huge outlier day cannot push the target past 125% of the best day or 10 km.
    history[today - timedelta(days=5)] = 30_000.0
    assert q.daily_quest("competition", today, history).target_m <= q.MAX_TARGET_M
    # Today's own distance never moves today's target.
    history[today] = 50_000.0
    assert q.daily_quest("running", today, history).target_m == q.daily_quest(
        "running", today, {k: v for k, v in history.items() if k != today}).target_m


def test_recovery_after_three_active_days() -> None:
    today = date(2026, 9, 28)
    history = {today - timedelta(days=d): 2000.0 for d in (1, 2, 3)}
    quest = q.daily_quest("fitness", today, history)
    assert quest.kind == "recovery" and quest.optional


def test_weekly_streak_does_not_punish_rest() -> None:
    today = date(2026, 9, 30)   # Wednesday; this week has no activity yet
    totals = {}
    for weeks_back in (1, 2):
        start = q.week_start(today) - timedelta(days=7 * weeks_back)
        for d in (0, 2, 4):     # three active days, rest on the others
            totals[start + timedelta(days=d)] = 1500.0
    assert q.weekly_streak("running", today, totals) == 2
    # Meeting this week extends it; an unmet in-progress week does not break it.
    for d in (0, 1, 2):
        totals[q.week_start(today) + timedelta(days=d)] = 1200.0
    assert q.weekly_streak("running", today, totals) == 3
    # A missed full week ends the streak, but nothing is taken away.
    gap = {k: v for k, v in totals.items() if k >= q.week_start(today) - timedelta(days=7)}
    assert q.weekly_streak("running", today, gap) == 2


# --- API --------------------------------------------------------------------------

def test_registration_is_bmi_free_and_onboarding_tracks_funnel() -> None:
    cleanup()
    headers, profile = _register("ada", goal="consistency")
    assert profile["identity"] == "explorer" and not profile["onboarding_completed"]
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == profile["user_id"]).first()
        assert user.bmi is None and user.mana_crystals == 0
    finally:
        db.close()
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}ada@example.com", "password": PASSWORD, "display_name": "Dup", "goal": "running",
    })
    assert r.status_code == 400
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}bad@example.com", "password": PASSWORD, "display_name": "Bad", "goal": "bmi",
    })
    assert r.status_code == 422
    r = client.put("/api/v2/me/profile", headers=headers, json={
        "onboarding_completed": True, "location_consent": True, "utc_offset_minutes": 60,
    })
    assert r.status_code == 200 and r.json()["onboarding_completed"] and r.json()["location_consent"]
    # Login still works through the role-aware endpoint.
    r = client.post("/api/v1/auth/login", json={
        "email": f"{PREFIX}ada@example.com", "password": PASSWORD, "device_timestamp": _now(),
    })
    assert r.status_code == 200 and r.json()["role"] == "player"


def test_sign_up_input_the_profile_cannot_serve_is_refused_up_front() -> None:
    cleanup()
    # A reserved domain passed the old "@" check, then every profile load failed EmailStr with a 500.
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}reserved@example.test", "password": PASSWORD, "display_name": "Reserved",
    })
    assert r.status_code == 422, r.text
    # 40 characters but 80 bytes: bcrypt refuses more than 72 bytes, so this must be a 422, not a 500.
    long_password = "\u00e9" * 40
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}long@example.com", "password": long_password, "display_name": "Long",
    })
    assert r.status_code == 422, r.text
    db = database.SessionLocal()
    try:
        assert db.query(models.User).filter(models.User.email.in_([
            f"{PREFIX}reserved@example.test", f"{PREFIX}long@example.com",
        ])).count() == 0
    finally:
        db.close()

    headers, profile = _register("grace")
    r = client.post("/api/v2/me/password", headers=headers, json={
        "current_password": PASSWORD, "new_password": long_password,
    })
    assert r.status_code == 422, r.text
    # An over-long attempt is a wrong password, not a server error.
    r = client.post("/api/v1/auth/login", json={
        "email": f"{PREFIX}grace@example.com", "password": long_password, "device_timestamp": _now(),
    })
    assert r.status_code == 401, r.text

    # Accounts already stored with such an address still load their profile.
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == profile["user_id"]).first()
        user.email = f"{PREFIX}grace@example.test"
        db.commit()
    finally:
        db.close()
    r = client.get(f"/api/v1/users/{profile['user_id']}", headers=headers)
    assert r.status_code == 200 and r.json()["email"] == f"{PREFIX}grace@example.test", r.text


def test_today_quest_completes_once_from_verified_run() -> None:
    cleanup()
    headers, profile = _register("grace")
    today = client.get("/api/v2/me/today", headers=headers).json()
    assert today["today"]["kind"] == "starter" and today["tagline"] == "Fitness, turned into quests."
    assert today["streak_weeks"] == 0 and today["safety_note"]

    run = _run(headers, 1200, "grace-1")
    assert run["verification_status"] == "accepted"
    starter_xp = q.daily_quest("running", date.today(), {}).xp
    # Run XP (12 per the run rule) plus the starter quest XP.
    assert run["xp_awarded"] == 12 + starter_xp, run
    today = client.get("/api/v2/me/today", headers=headers).json()
    assert today["today"]["completed"] and today["today"]["rewarded"]
    assert today["week"]["active_days"] == 1 and today["tomorrow"]["target_m"] >= 800

    # A second run the same day completes nothing new.
    run2 = _run(headers, 1200, "grace-2")
    assert run2["xp_awarded"] == 12, run2
    db = database.SessionLocal()
    try:
        awards = db.query(models.QuestAward).filter(models.QuestAward.user_id == profile["user_id"]).count()
        firsts = db.query(models.AnalyticsEvent).filter(
            models.AnalyticsEvent.user_id == profile["user_id"],
            models.AnalyticsEvent.event_name == "first_verified_run",
        ).count()
        assert awards == 1 and firsts == 1
    finally:
        db.close()


def test_client_events_cannot_forge_milestones_or_location() -> None:
    cleanup()
    headers, _ = _register("linus")
    ok = client.post("/api/v2/events", json={"event_name": "app_installed", "install_id": PREFIX + "dev1"})
    assert ok.status_code == 202
    assert client.post("/api/v2/events", json={"event_name": "app_opened"}).status_code == 422
    forged = client.post("/api/v2/events", headers=headers, json={"event_name": "first_verified_run"})
    assert forged.status_code == 422 and forged.json()["detail"]["code"] == "UNKNOWN_EVENT"
    loc = client.post("/api/v2/events", headers=headers, json={"event_name": "app_opened", "properties": {"lat": 1}})
    assert loc.status_code == 422 and loc.json()["detail"]["code"] == "FORBIDDEN_PROPERTY"


def test_admin_funnel() -> None:
    cleanup()
    a, _ = _register("one")
    _register("two")
    client.put("/api/v2/me/profile", headers=a, json={"onboarding_completed": True})
    _run(a, 1200, "one-1")
    admin = _admin()
    assert client.get("/api/v2/admin/funnel", headers=a).status_code == 403
    r = client.get("/api/v2/admin/funnel", headers=admin, params={"days": 1})
    assert r.status_code == 200, r.text
    steps = {s["step"]: s["users"] for s in r.json()["steps"]}
    assert steps["account_created"] >= 2
    assert steps["onboarding_completed"] >= 1 and steps["first_verified_result"] >= 1


if __name__ == "__main__":
    for test in (
        test_starter_quest_for_new_player,
        test_quest_scales_with_history_and_is_capped,
        test_recovery_after_three_active_days,
        test_weekly_streak_does_not_punish_rest,
        test_registration_is_bmi_free_and_onboarding_tracks_funnel,
        test_sign_up_input_the_profile_cannot_serve_is_refused_up_front,
        test_today_quest_completes_once_from_verified_run,
        test_client_events_cannot_forge_milestones_or_location,
        test_admin_funnel,
    ):
        test()
        print(f"PASS {test.__name__}")
    cleanup()
