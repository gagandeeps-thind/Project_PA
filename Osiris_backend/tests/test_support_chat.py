"""Live support chat stub: player-only WebSocket with an automated acknowledgement.

    python tests/test_support_chat.py
"""
import os
import sys
from datetime import timedelta

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "support-chat-test-secret-aaaaaaaaaaaaaaaaaaaaa")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

import growth_support  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from database import Base  # noqa: E402

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
URL = "/api/v2/support/ws"


def register(name):
    r = client.post("/api/v2/auth/register", json={
        "email": f"support_{name}@example.com", "password": "Support123!", "display_name": name,
        "location_consent": False, "goal": "fitness",
    })
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def refused(headers):
    try:
        with client.websocket_connect(URL, headers=headers):
            return False
    except WebSocketDisconnect:
        return True


def test_player_gets_greeting_and_acknowledgement():
    token = register("ana")
    with client.websocket_connect(URL, headers={"Authorization": f"Bearer {token}"}) as ws:
        assert ws.receive_json()["text"] == growth_support.GREETING
        ws.send_json({"text": "My run was not counted"})
        reply = ws.receive_json()
        assert reply["from"] == "support" and reply["text"] == growth_support.RECEIVED
        ws.send_json({"text": "x" * (growth_support.MAX_TEXT + 1)})
        assert "1 to" in ws.receive_json()["text"]
        ws.send_text("not json")
        assert "could not be read" in ws.receive_json()["text"]
    print("PASS test_player_gets_greeting_and_acknowledgement")


def test_unauthenticated_and_revoked_sessions_are_refused():
    assert refused({})
    assert refused({"Authorization": "Bearer not-a-token"})
    token = register("ben")
    db = Session()
    user = db.query(models.User).filter(models.User.email == "support_ben@example.com").one()
    user.tokens_valid_after = main._now_naive_utc() + timedelta(minutes=1)
    db.commit()
    db.close()
    assert refused({"Authorization": f"Bearer {token}"})
    print("PASS test_unauthenticated_and_revoked_sessions_are_refused")


def test_suspended_player_can_still_reach_support():
    token = register("cy")
    db = Session()
    db.query(models.User).filter(models.User.email == "support_cy@example.com").update(
        {models.User.suspended_at: main._now_naive_utc()})
    db.commit()
    db.close()
    with client.websocket_connect(URL, headers={"Authorization": f"Bearer {token}"}) as ws:
        assert ws.receive_json()["text"] == growth_support.GREETING
    print("PASS test_suspended_player_can_still_reach_support")


if __name__ == "__main__":
    test_player_gets_greeting_and_acknowledgement()
    test_unauthenticated_and_revoked_sessions_are_refused()
    test_suspended_player_can_still_reach_support()
