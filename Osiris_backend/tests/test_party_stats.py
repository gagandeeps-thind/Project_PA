import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Webhook fail-closed boot check requires an explicit dev/test env.
os.environ.setdefault("OSIRIS_ENV", "test")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from main import app
from database import get_db
from core.security import create_access_token, get_password_hash
from services.progression import get_rank, get_title, record_activity
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
        email="test_stats@example.com",
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

def test_record_activity():
    print("Running test_record_activity...")
    db, user = setup_db()
    
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # 1. Record an activity
        log = record_activity(
            db=db,
            user=user,
            activity_type="pushups",  # Feeds str_stat
            score=30,
            occurred_at=now,
            source="domain_claim"
        )
        db.commit()
        db.refresh(user)
        
        # Assertions
        assert log is not None
        assert log.score == 30
        assert log.stat_column == "str_stat"
        assert log.activity_type == "pushups"
        assert user.str_stat == 30, f"Expected 30, got {user.str_stat}"
        
        # 2. Record another activity (different type)
        log2 = record_activity(
            db=db,
            user=user,
            activity_type="sprint",  # Feeds agi_stat
            score=50,
            occurred_at=now,
            source="bounty_complete"
        )
        db.commit()
        db.refresh(user)
        
        assert log2.stat_column == "agi_stat"
        assert user.agi_stat == 50
        
        print("  [PASS] test_record_activity")
    finally:
        db.close()
        teardown_db()

def test_rolling_window_party_role():
    print("Running test_rolling_window_party_role...")
    db, user = setup_db()
    
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # Record an OLD activity (40 days ago) - high score in STR
        old_time = now - timedelta(days=40)
        record_activity(
            db=db, user=user, activity_type="pushups", score=100, 
            occurred_at=old_time, source="domain_claim"
        )
        
        # Record a NEW activity (10 days ago) - moderate score in AGI
        new_time = now - timedelta(days=10)
        record_activity(
            db=db, user=user, activity_type="sprint", score=40, 
            occurred_at=new_time, source="bounty_complete"
        )
        
        db.commit()
        db.refresh(user)
        
        # The user's lifetime totals are now: STR=100, AGI=40
        # If we call without window_days, leading should be STR (Vanguard)
        headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'role': 'player'})}"}
        resp_lifetime = client.get(f"/api/v1/users/{user.id}/party-role", headers=headers)
        assert resp_lifetime.status_code == 200
        data_lifetime = resp_lifetime.json()
        assert data_lifetime["leading_stat"] == "str_stat", f"Expected str_stat, got {data_lifetime['leading_stat']}"
        assert data_lifetime["role"] == "Vanguard"
        assert data_lifetime["str_stat"] == 100
        
        # If we call WITH window_days=30, the 100 STR is ignored.
        # Leading should be AGI (Striker)
        resp_window = client.get(f"/api/v1/users/{user.id}/party-role?window_days=30", headers=headers)
        assert resp_window.status_code == 200
        data_window = resp_window.json()
        assert data_window["leading_stat"] == "agi_stat", f"Expected agi_stat, got {data_window['leading_stat']}"
        assert data_window["role"] == "Striker"
        assert data_window["str_stat"] == 0   # Ignored from 40 days ago
        assert data_window["agi_stat"] == 40
        
        print("  [PASS] test_rolling_window_party_role")
    finally:
        db.close()
        teardown_db()

if __name__ == "__main__":
    print("--- Running Party Stats Tests ---")
    test_record_activity()
    test_rolling_window_party_role()
    print("--- All tests passed! ---")
