import sys
import os
from datetime import datetime, timezone

# Add the parent directory to the Python path so we can import the backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import database
import models
from main import get_password_hash, get_rank, get_title, get_avatar_class

def seed_pilot_data():
    db = database.SessionLocal()
    
    # Check if data already exists to make script idempotent
    if db.query(models.User).filter(models.User.email == "vanguard@example.com").first():
        print("Pilot data already seeded. Exiting gracefully.")
        db.close()
        return

    print("Seeding pilot data for Bedford...")
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # --- 1. Seed Users ---
    users_data = [
        {"email": "vanguard@example.com", "path": "Strength", "password": "password"},
        {"email": "striker@example.com", "path": "Cardio", "password": "password"},
        {"email": "strategist@example.com", "path": "Balance", "password": "password"}
    ]
    
    created_users = {}
    for ud in users_data:
        avatar_class = get_avatar_class(ud["path"])
        user = models.User(
            email=ud["email"],
            hashed_password=get_password_hash(ud["password"]),
            bmi=22.5,
            avatar_class=avatar_class,
            xp=1000,
            rank=get_rank(1000),
            title=get_title(0.0),
            cumulative_area=0.0,
            last_activity_date=now,
            streak=5,
            mana_crystals=500
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        created_users[ud["email"]] = user
        print(f"Created User: {user.email}")

    vanguard = created_users["vanguard@example.com"]
    striker = created_users["striker@example.com"]

    # --- 2. Seed Domains (DeWolf Park) ---
    # DeWolf Park: 44.71676282525317, -63.671012220979044
    base_lat = 44.716762
    base_lng = -63.671012
    
    # A small triangle polygon near the base coordinates
    poly1 = [
        {"lat": base_lat, "lng": base_lng},
        {"lat": base_lat + 0.001, "lng": base_lng},
        {"lat": base_lat, "lng": base_lng + 0.001},
        {"lat": base_lat, "lng": base_lng}
    ]
    
    import json
    domain1 = models.Domain(
        owner_id=vanguard.id,
        geometry_json=json.dumps(poly1),
        area_sqkm=0.05,
        defense_score=50,
        defense_type="pushups",
        vault_balance=100  # Paid Vault
    )
    
    # Second domain (Free Tier)
    poly2 = [
        {"lat": base_lat - 0.001, "lng": base_lng},
        {"lat": base_lat - 0.002, "lng": base_lng},
        {"lat": base_lat - 0.001, "lng": base_lng - 0.001},
        {"lat": base_lat - 0.001, "lng": base_lng}
    ]
    
    domain2 = models.Domain(
        owner_id=striker.id,
        geometry_json=json.dumps(poly2),
        area_sqkm=0.03,
        defense_score=20,
        defense_type="squats",
        vault_balance=0  # Free Tier
    )
    
    db.add(domain1)
    db.add(domain2)
    db.commit()
    print("Created 2 Domains in DeWolf Park.")

    # --- 3. Seed Merchant ---
    merchant = models.Merchant(
        name="Bedford Cafe",
        email="cafe@bedford.local",
        hashed_password=get_password_hash("password"),
        business_type="cafe"
    )
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    print("Created 1 Merchant.")

    # --- 4. Seed Bounties ---
    bounties = [
        models.Bounty(
            title="DeWolf Morning Run",
            description="Run around DeWolf park to earn your daily crystals.",
            bounty_type="daily",
            target_lat=base_lat + 0.0005,
            target_lng=base_lng + 0.0005,
            radius_m=50.0,
            activity_type="run",
            target_score=10,
            xp_reward=50,
            crystal_reward=5
        ),
        models.Bounty(
            title="Park Pushups",
            description="Drop and give me 20 at the park entrance.",
            bounty_type="daily",
            target_lat=base_lat - 0.0005,
            target_lng=base_lng - 0.0005,
            radius_m=30.0,
            activity_type="pushups",
            target_score=20,
            xp_reward=50,
            crystal_reward=5
        ),
        models.Bounty(
            title="Squats by the Water",
            description="30 squats near the water line.",
            bounty_type="daily",
            target_lat=base_lat + 0.001,
            target_lng=base_lng - 0.001,
            radius_m=30.0,
            activity_type="squats",
            target_score=30,
            xp_reward=50,
            crystal_reward=5
        ),
        models.Bounty(
            title="Free Coffee at Bedford Cafe",
            description="Visit the cafe to claim a free coffee coupon!",
            bounty_type="merchant_chest",
            merchant_id=merchant.id,
            target_lat=base_lat + 0.002,
            target_lng=base_lng + 0.002,
            radius_m=20.0,
            activity_type="walk",
            target_score=0,
            xp_reward=25,
            crystal_reward=10,
            coupon_text="FREE_COFFEE_2026"
        ),
        models.Bounty(
            title="Cafe Discount Box",
            description="Stop by for 10% off your next meal.",
            bounty_type="merchant_chest",
            merchant_id=merchant.id,
            target_lat=base_lat + 0.0025,
            target_lng=base_lng + 0.0025,
            radius_m=20.0,
            activity_type="walk",
            target_score=0,
            xp_reward=25,
            crystal_reward=10,
            coupon_text="10_OFF_MEAL"
        )
    ]
    
    db.add_all(bounties)
    db.commit()
    print("Created 5 Bounties.")

    db.close()
    print("Seed complete.")

if __name__ == "__main__":
    seed_pilot_data()
