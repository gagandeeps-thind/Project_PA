import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Webhook fail-closed boot check requires an explicit dev/test env.
os.environ.setdefault("OSIRIS_ENV", "test")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from main import app, get_db, get_password_hash, get_rank, get_title
import models

# Set up an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Create a dummy user
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = models.User(
        email="test_replay@example.com",
        hashed_password=get_password_hash("password"),
        bmi=22.0,
        avatar_class="Tank",
        xp=0,
        rank=get_rank(0),
        title=get_title(0.0),
        cumulative_area=0.0,
        last_activity_date=now,
        streak=0,
        mana_crystals=100
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return db, user

def teardown_db():
    Base.metadata.drop_all(bind=engine)

def test_replay_attack_guard():
    print("Running test_replay_attack_guard...")
    db, user = setup_db()
    
    try:
        now_str = "2026-05-04T12:00:00Z"
        
        # Valid domain claim payload with a mock proof
        payload = {
            "owner_id": user.id,
            "device_timestamp": now_str,
            "defense_score": 30,
            "defense_type": "pushups",
            "coordinates": [
                {"lat": 43.50, "lng": -80.50, "timestamp": now_str},
                {"lat": 43.501, "lng": -80.50, "timestamp": now_str},
                {"lat": 43.501, "lng": -80.501, "timestamp": now_str},
                {"lat": 43.50, "lng": -80.501, "timestamp": now_str},
                {"lat": 43.50, "lng": -80.50, "timestamp": now_str}
            ],
            "defense_proof": {
                "activity_type": "pushups",
                "declared_score": 30,
                "duration_seconds": 30.0,
                "device_timestamp": now_str,
                "accelerometer": [
                    {"t_ms": 0, "ax": 0, "ay": 0, "az": 9.8},
                    {"t_ms": 500, "ax": 0, "ay": 0, "az": 15.0},
                    {"t_ms": 1000, "ax": 0, "ay": 0, "az": 9.8}
                ]
            }
        }
        
        # 1. First submission should succeed (200 OK)
        client.post("/api/v1/domains", json=payload)
        # Note: the heuristic ml_referee might reject our fake accelerometer trace
        # with a 400 Bad Request depending on its internal math. But if the replay
        # guard works, the SECOND request must be 409 regardless, or if the first
        # one fails validation it never gets consumed.
        # Let's check status. If it's 400 because of "cadence too slow", we need to
        # make the trace look like a real workout.
        # Actually, let's just make sure we hit the endpoint. Wait, _consume_proof_or_409
        # is called AFTER _enforce_proof! If _enforce_proof fails, we don't consume it.
        # Let's bypass _enforce_proof by making a perfect trace, or we can just patch
        # _enforce_proof for this test so it always returns a pass.
        # Let's just try it. If it fails, we will see.
        
        # But wait, we can also test it by calling _consume_proof_or_409 directly!
        # Let's do that for a much cleaner unit test.
        from main import _consume_proof_or_409
        from models import ProofConsumed
        from pydantic import TypeAdapter
        from main import ActivityProof
        
        proof_obj = TypeAdapter(ActivityProof).validate_python(payload["defense_proof"])
        
        # Attempt 1: Call helper directly
        _consume_proof_or_409(db, user.id, proof_obj, "domain_claim")
        db.commit() # commit the consumption
        
        # Verify it's in the DB
        consumed = db.query(ProofConsumed).filter(ProofConsumed.user_id == user.id).first()
        assert consumed is not None
        assert consumed.source == "domain_claim"
        
        # Attempt 2: Replay the exact same proof
        from fastapi import HTTPException
        try:
            _consume_proof_or_409(db, user.id, proof_obj, "domain_claim")
            assert False, "Expected HTTPException(409) for replay attack"
        except HTTPException as e:
            assert e.status_code == 409
            assert "already been consumed" in e.detail
        
        # Attempt 3: Modify the proof slightly (simulate a new workout)
        payload["defense_proof"]["device_timestamp"] = "2026-05-04T12:05:00Z"
        proof_obj2 = TypeAdapter(ActivityProof).validate_python(payload["defense_proof"])
        
        # This should succeed and not raise 409
        _consume_proof_or_409(db, user.id, proof_obj2, "domain_claim")
        db.commit()
        
        print("  [PASS] test_replay_attack_guard")
    finally:
        db.close()
        teardown_db()

if __name__ == "__main__":
    print("--- Running Replay Guard Tests ---")
    test_replay_attack_guard()
    print("--- All tests passed! ---")
