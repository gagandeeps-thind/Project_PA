"""Camera-verified exercise regression tests: catalog, server re-check, idempotency, XP caps,
history, data export and erasure, metrics.

Run directly from the backend directory:
    python tests/test_exercise_sessions.py
"""
import os
import sys
import uuid

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "exercise-test-secret-aaaaaaaaaaaaaaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "scripts")))

from fastapi.testclient import TestClient

import database
import growth_api
import main
import models
from services import exercises as rules

PREFIX = "exercise_test_"
PASSWORD = "ExerciseTest1!"
ADMIN_EMAIL = PREFIX + "admin@example.com"

client = TestClient(main.app)


def cleanup() -> None:
    db = database.SessionLocal()
    try:
        ids = [u.id for u in db.query(models.User).filter(models.User.email.like(PREFIX + "%")).all()]
        if ids:
            set_ids = [i for (i,) in db.query(models.ExerciseSession.id).filter(
                models.ExerciseSession.user_id.in_(ids)).all()] or [-1]
            db.query(models.AuditEvent).filter(
                (models.AuditEvent.entity_type == "exercise_session") & models.AuditEvent.entity_id.in_(set_ids)
            ).delete(synchronize_session=False)
            growth_api.delete_growth_data(db, ids)
            db.query(models.AuditEvent).filter(
                ((models.AuditEvent.actor_type == "player") & models.AuditEvent.actor_id.in_(ids))
                | ((models.AuditEvent.entity_type == "user") & models.AuditEvent.entity_id.in_(ids))
            ).delete(synchronize_session=False)
            db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_(ids)).delete(synchronize_session=False)
        db.query(models.Admin).filter(models.Admin.email == ADMIN_EMAIL).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _register(name, exercise_consent=True):
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}{name}@example.com", "password": PASSWORD, "display_name": name.title(),
        "goal": "fitness", "location_consent": True,
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if exercise_consent:
        r = client.put("/api/v2/me/exercise-consent", headers=headers, json={"granted": True})
        assert r.status_code == 200 and r.json()["granted"], r.text
    return headers


def _admin() -> dict:
    db = database.SessionLocal()
    try:
        admin = db.query(models.Admin).filter(models.Admin.email == ADMIN_EMAIL).first()
        if admin is None:
            admin = models.Admin(email=ADMIN_EMAIL, hashed_password="x", name="Exercise Admin")
            db.add(admin)
            db.commit()
        admin_id = admin.id
    finally:
        db.close()
    return {"Authorization": f"Bearer {main.create_access_token({'sub': str(admin_id), 'role': 'admin'})}"}


def _durations(n, base=1.5):
    # Human tempo varies rep to rep; a cycle of offsets keeps the CV well above the replay bound.
    offsets = (0.0, 0.3, -0.2, 0.45, -0.35, 0.1)
    return [round(base + offsets[i % len(offsets)], 3) for i in range(n)]


def _set(exercise="pushup", reps=10, **over):
    durations = over.pop("rep_durations_s", None) or _durations(reps)
    body = {
        "client_session_id": uuid.uuid4().hex, "exercise_key": exercise, "rules_version": rules.RULES_VERSION,
        "duration_s": round(sum(durations) + 3.0, 3), "reps_attempted": reps, "reps_valid": reps,
        "form_score": 0.9, "client_verdict": "verified", "reason_codes": [], "rep_durations_s": durations,
    }
    body.update(over)
    return body


def _xp(headers):
    return client.get("/api/v2/me/exercise-sessions", headers=headers).json()["today_xp"]


def test_catalog_served_and_bundled_copy_in_sync() -> None:
    assert client.get("/api/v2/exercises").status_code == 401
    headers = _register("catalog")
    r = client.get("/api/v2/exercises", headers=headers)
    assert r.status_code == 200, r.text
    keys = [e["key"] for e in r.json()["exercises"]]
    assert keys == ["pushup", "squat", "lunge", "situp", "jumping_jack", "high_knees", "plank"], keys
    assert r.json()["rules_version"] == rules.RULES_VERSION
    import export_exercise_catalog
    assert export_exercise_catalog.main() == 0, "bundled app catalog drifted; run export_exercise_catalog.py --write"
    print("PASS catalog served and bundled copy in sync")


def test_verified_set_awards_xp_once() -> None:
    headers = _register("verified")
    body = _set(reps=12)
    r = client.post("/api/v2/exercise-sessions", headers=headers, json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "verified" and out["xp_awarded"] == 12 and not out["duplicate"], out
    assert out["daily_xp_remaining"] == rules.DAILY_EXERCISE_XP_CAP - 12
    retry = client.post("/api/v2/exercise-sessions", headers=headers, json=body)
    assert retry.status_code == 200 and retry.json()["duplicate"] and retry.json()["id"] == out["id"], retry.text
    assert retry.json()["total_xp"] == out["total_xp"], "a retried upload must not grant XP twice"
    print("PASS verified set awards XP once")


def test_implausible_sets_are_refused() -> None:
    headers = _register("cheater")
    cases = [
        (_set(reps=10, rep_durations_s=[0.2] * 10), "tempo_implausible", "rejected"),
        (_set(reps=10, duration_s=5.0), "duration_mismatch", "rejected"),
        (_set(reps=10, rep_durations_s=[1.0] * 10), "replay_suspected", "review"),
        (_set(reps=5, client_verdict="rejected", reason_codes=["no_valid_reps"], reps_valid=0, rep_durations_s=[],
              duration_s=20.0), "client_rejected", "rejected"),
        (_set(reps=10, rules_version="exercise-rules-v0"), "rules_version_mismatch", "rejected"),
        (_set(reps=10, reps_attempted=30), "low_valid_ratio", "review"),
    ]
    before = _xp(headers)
    for body, reason, status in cases:
        r = client.post("/api/v2/exercise-sessions", headers=headers, json=body)
        assert r.status_code == 201, r.text
        assert r.json()["status"] == status and reason in r.json()["reason_codes"], (reason, r.json())
        assert r.json()["xp_awarded"] == 0, r.json()
    assert _xp(headers) == before
    print("PASS implausible sets are refused")


def test_rate_limit_on_reps_per_minute() -> None:
    decision = rules.evaluate(rules.SessionClaim(
        exercise_key="pushup", rules_version=rules.RULES_VERSION, duration_s=30.0, reps_attempted=40,
        reps_valid=40, hold_s=0.0, rep_durations_s=_durations(40, base=0.7)[:40], client_verdict="verified",
        client_reasons=[]))
    # 40 reps in 30 s is 80/min, above the push-up limit of 60/min (and the durations overrun 30 s).
    assert decision.status == "rejected" and "rate_implausible" in decision.reasons, decision
    print("PASS rate limit on reps per minute")


def test_bad_input_is_422() -> None:
    headers = _register("badinput")
    r = client.post("/api/v2/exercise-sessions", headers=headers, json=_set(exercise="burpee_mega"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "UNKNOWN_EXERCISE", r.text
    r = client.post("/api/v2/exercise-sessions", headers=headers, json=_set(reason_codes=["<script>"]))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "UNKNOWN_REASON_CODE", r.text
    r = client.post("/api/v2/exercise-sessions", headers=headers, json=_set(client_session_id="bad id!"))
    assert r.status_code == 422, r.text
    print("PASS bad input is 422")


def test_daily_caps_per_exercise_and_total() -> None:
    headers = _register("caps")
    awards = [client.post("/api/v2/exercise-sessions", headers=headers, json=_set(reps=25)).json()["xp_awarded"]
              for _ in range(2)]
    assert awards == [25, 15], awards                               # push-up cap 40
    for exercise, cap in (("squat", 40), ("lunge", 30)):
        r = client.post("/api/v2/exercise-sessions", headers=headers, json=_set(exercise, reps=cap,
                        rep_durations_s=_durations(cap, base=2.0)))
        assert r.json()["xp_awarded"] == cap, r.json()
    r = client.post("/api/v2/exercise-sessions", headers=headers, json=_set("situp", reps=30,
                    rep_durations_s=_durations(30, base=2.0)))
    assert r.json()["xp_awarded"] == rules.DAILY_EXERCISE_XP_CAP - 110, r.json()   # total cap 120
    assert r.json()["daily_xp_remaining"] == 0
    assert _xp(headers) == rules.DAILY_EXERCISE_XP_CAP
    print("PASS daily caps per exercise and total")


def test_plank_hold() -> None:
    headers = _register("plank")
    r = client.post("/api/v2/exercise-sessions", headers=headers, json=_set(
        "plank", reps=0, reps_attempted=0, reps_valid=0, rep_durations_s=[], hold_s=47.0, duration_s=55.0))
    assert r.json()["status"] == "verified" and r.json()["xp_awarded"] == 4, r.json()
    r = client.post("/api/v2/exercise-sessions", headers=headers, json=_set(
        "plank", reps=0, reps_attempted=0, reps_valid=0, rep_durations_s=[], hold_s=3.0, duration_s=10.0))
    assert r.json()["status"] == "rejected" and "hold_too_short" in r.json()["reason_codes"], r.json()
    r = client.post("/api/v2/exercise-sessions", headers=headers, json=_set(
        "plank", reps=0, reps_attempted=0, reps_valid=0, rep_durations_s=[], hold_s=90.0, duration_s=20.0))
    assert r.json()["status"] == "rejected" and "duration_mismatch" in r.json()["reason_codes"], r.json()
    print("PASS plank hold")


def test_submission_is_rate_limited() -> None:
    headers = _register("ratelimit")
    main._rate_buckets.clear()
    dev_env = main._IS_DEV_ENV
    main._IS_DEV_ENV = False          # limits are off in dev/test; exercise the prod path
    try:
        codes = [client.post("/api/v2/exercise-sessions", headers=headers, json=_set(reps=3)).status_code
                 for _ in range(35)]
    finally:
        main._IS_DEV_ENV = dev_env
        main._rate_buckets.clear()
    assert codes[:30] == [201] * 30 and 429 in codes[30:], codes
    print("PASS submission is rate limited")


def test_consent_is_explicit_and_revocable() -> None:
    headers = _register("consent", exercise_consent=False)
    state = client.get("/api/v2/me/exercise-consent", headers=headers).json()
    assert state == {"granted": False, "policy_version": None, "updated_at": None, "deleted_sets": 0}, state
    r = client.post("/api/v2/exercise-sessions", headers=headers, json=_set(reps=5))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "EXERCISE_CONSENT_REQUIRED", r.text

    assert client.put("/api/v2/me/exercise-consent", headers=headers, json={"granted": True}).json()["granted"]
    # Granting twice does not add a second ledger row.
    client.put("/api/v2/me/exercise-consent", headers=headers, json={"granted": True})
    body = _set(reps=5)
    assert client.post("/api/v2/exercise-sessions", headers=headers, json=body).status_code == 201

    r = client.put("/api/v2/me/exercise-consent", headers=headers, json={"granted": False, "delete_data": True})
    assert r.status_code == 200 and r.json()["granted"] is False and r.json()["deleted_sets"] == 1, r.text
    assert client.get("/api/v2/me/exercise-sessions", headers=headers).json()["sessions"] == []
    r = client.post("/api/v2/exercise-sessions", headers=headers, json=_set(reps=5))
    assert r.status_code == 403, "no new sets after withdrawal"

    export = client.get("/api/v2/me/export", headers=headers).json()
    ledger = [(c["kind"], c["granted"]) for c in export["consents"] if c["kind"] == "exercise_camera"]
    assert ledger == [("exercise_camera", True), ("exercise_camera", False)], ledger
    db = database.SessionLocal()
    try:
        uid = db.query(models.User.id).filter(models.User.email == f"{PREFIX}consent@example.com").one()[0]
        actions = {a for (a,) in db.query(models.AuditEvent.action).filter(
            models.AuditEvent.actor_type == "player", models.AuditEvent.actor_id == uid).all()}
        assert {"consent.exercise_camera.granted", "consent.exercise_camera.withdrawn",
                "exercise.data_deleted"} <= actions, actions
    finally:
        db.close()
    print("PASS consent is explicit and revocable")


def test_replay_after_withdrawal_returns_stored_result() -> None:
    headers = _register("replay")
    body = _set(reps=6)
    first = client.post("/api/v2/exercise-sessions", headers=headers, json=body).json()
    client.put("/api/v2/me/exercise-consent", headers=headers, json={"granted": False})
    retry = client.post("/api/v2/exercise-sessions", headers=headers, json=body)
    assert retry.status_code == 200 and retry.json()["id"] == first["id"] and retry.json()["duplicate"], retry.text
    print("PASS replay after withdrawal returns the stored result")


def test_admin_review_queue() -> None:
    headers = _register("reviewed")
    flagged = [client.post("/api/v2/exercise-sessions", headers=headers,
                           json=_set(reps=10, rep_durations_s=[1.2] * 10)).json() for _ in range(3)]
    assert all(f["status"] == "review" and f["xp_awarded"] == 0 for f in flagged), flagged
    ids = [f["id"] for f in flagged]

    assert client.get("/api/v2/admin/exercise-sessions").status_code == 401
    assert client.get("/api/v2/admin/exercise-sessions", headers=headers).status_code == 403
    assert client.post(f"/api/v2/admin/exercise-sessions/{ids[0]}/review", headers=headers,
                       json={"decision": "approve", "note": "self approve"}).status_code == 403

    admin = _admin()
    queue = [q for q in client.get("/api/v2/admin/exercise-sessions", headers=admin).json() if q["id"] in ids]
    assert len(queue) == 3, queue
    item = queue[0]
    assert item["display_name"] == "Reviewed" and item["exercise_name"] == "Push-up", item
    assert "replay_suspected" in item["reason_codes"] and item["rep_duration_cv"] == 0.0, item
    assert item["rep_durations_s"] == [1.2] * 10 and item["xp_if_approved"] == 10, item
    assert item["player_sets"] == 3 and item["player_flagged_sets"] == 3, item

    before = client.get("/api/v2/me/exercise-sessions", headers=headers).json()["today_xp"]
    r = client.post(f"/api/v2/admin/exercise-sessions/{ids[0]}/review", headers=admin,
                    json={"decision": "approve", "note": "real person, metronome app"})
    assert r.status_code == 200 and r.json() == {"id": ids[0], "status": "verified", "xp_awarded": 10}, r.text
    again = client.post(f"/api/v2/admin/exercise-sessions/{ids[0]}/review", headers=admin,
                        json={"decision": "reject", "note": "changed my mind"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "EXERCISE_SET_NOT_IN_REVIEW", again.text

    r = client.post(f"/api/v2/admin/exercise-sessions/{ids[1]}/review", headers=admin,
                    json={"decision": "reject", "note": "looped video"})
    assert r.json()["status"] == "rejected" and r.json()["xp_awarded"] == 0, r.text
    assert client.post(f"/api/v2/admin/exercise-sessions/{ids[2]}/review", headers=admin,
                       json={"decision": "approve", "note": "x"}).status_code == 422, "a note is required"
    assert client.post("/api/v2/admin/exercise-sessions/999999999/review", headers=admin,
                       json={"decision": "approve", "note": "missing"}).status_code == 404

    hist = {s["id"]: s for s in client.get("/api/v2/me/exercise-sessions", headers=headers).json()["sessions"]}
    assert hist[ids[0]]["status"] == "verified" and hist[ids[0]]["xp_awarded"] == 10
    assert hist[ids[1]]["status"] == "rejected"
    assert client.get("/api/v2/me/exercise-sessions", headers=headers).json()["today_xp"] == before + 10

    # Approval respects the day's caps: fill the push-up cap, then approve the last flagged set.
    for _ in range(2):
        client.post("/api/v2/exercise-sessions", headers=headers, json=_set(reps=20))
    r = client.post(f"/api/v2/admin/exercise-sessions/{ids[2]}/review", headers=admin,
                    json={"decision": "approve", "note": "fine but capped"})
    assert r.json() == {"id": ids[2], "status": "verified", "xp_awarded": 0}, r.text

    db = database.SessionLocal()
    try:
        actions = [a for (a,) in db.query(models.AuditEvent.action).filter(
            models.AuditEvent.entity_type == "exercise_session", models.AuditEvent.entity_id.in_(ids)).all()]
        assert sorted(actions) == ["exercise.review.approve", "exercise.review.approve", "exercise.review.reject"]
    finally:
        db.close()
    print("PASS admin review queue")


def test_history_export_erase_and_metrics() -> None:
    headers = _register("history")
    client.post("/api/v2/exercise-sessions", headers=headers, json=_set(reps=8))
    client.post("/api/v2/exercise-sessions", headers=headers, json=_set("squat", reps=6))
    hist = client.get("/api/v2/me/exercise-sessions?limit=1", headers=headers).json()
    assert len(hist["sessions"]) == 1 and hist["sessions"][0]["exercise_key"] == "squat", hist
    assert hist["today_xp"] == 14 and hist["daily_xp_cap"] == rules.DAILY_EXERCISE_XP_CAP
    export = client.get("/api/v2/me/export", headers=headers).json()
    assert len(export["exercise_sessions"]) == 2, export["exercise_sessions"]
    metrics_text = client.get("/metrics").text
    assert 'osiris_exercise_verifications_total{exercise="squat",status="verified"}' in metrics_text
    db = database.SessionLocal()
    try:
        uid = db.query(models.User.id).filter(models.User.email == f"{PREFIX}history@example.com").one()[0]
        r = client.post("/api/v2/me/erase", headers=headers, json={"password": PASSWORD, "confirm": "DELETE"})
        assert r.status_code == 202, r.text
        assert db.query(models.ExerciseSession).filter(models.ExerciseSession.user_id == uid).count() == 0
        # The tombstone no longer matches PREFIX; give it back to cleanup().
        db.query(models.User).filter(models.User.id == uid).update({models.User.email: f"{PREFIX}erased-{uid}"})
        db.commit()
    finally:
        db.close()
    print("PASS history, export, erase and metrics")


if __name__ == "__main__":
    cleanup()
    try:
        test_catalog_served_and_bundled_copy_in_sync()
        test_verified_set_awards_xp_once()
        test_implausible_sets_are_refused()
        test_rate_limit_on_reps_per_minute()
        test_bad_input_is_422()
        test_daily_caps_per_exercise_and_total()
        test_plank_hold()
        test_submission_is_rate_limited()
        test_consent_is_explicit_and_revocable()
        test_replay_after_withdrawal_returns_stored_result()
        test_admin_review_queue()
        test_history_export_erase_and_metrics()
    finally:
        cleanup()
