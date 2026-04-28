from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
import datetime


def _default_now_naive_utc():
    """Naive UTC timestamp (tz stripped) for SQLite-compatible storage.
    Server-side fallback default; most timestamps now flow from the client device."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"

    # Every database table needs a Primary Key (a unique ID)
    id = Column(Integer, primary_key=True, index=True)
    
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String) # Notice we store hashed_password, NEVER plain text
    
    # Fitness Stats
    bmi = Column(Float)
    avatar_class = Column(String)
    rank = Column(String)
    title = Column(String, default="Unawakened")  # Tied to Domain area
    cumulative_area = Column(Float, default=0.0)  # Total km2 owned
    xp = Column(Integer, default=0)
    streak = Column(Integer, default=0)
    last_activity_date = Column(DateTime, default=_default_now_naive_utc)

    # Virtual in-game currency (Phase 1 MVP — becomes real-world convertible in Phase 2)
    mana_crystals = Column(Integer, default=100)

    # Party Attribute Stats — accumulate on every verified activity, drive Party Role assignment.
    # MVP keeps these as running totals; Phase 2 will recompute from a 30-day rolling ActivityLog.
    str_stat = Column(Integer, default=0)  # Push-ups, squats, resistance
    agi_stat = Column(Integer, default=0)  # Sprint, burpees, high-cadence
    end_stat = Column(Integer, default=0)  # Long runs, walks, sustained volume
    con_stat = Column(Integer, default=0)  # Planks, holds, streak precision

    # Relationships
    domains = relationship("Domain", back_populates="owner")

class Domain(Base):
    __tablename__ = "domains"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    guild_id = Column(Integer, nullable=True)
    
    # For MVP SQLite, we store the polygon coordinates as a JSON string.
    # In production, this becomes: geometry = Column(Geometry('POLYGON'))
    geometry_json = Column(String) 
    area_sqkm = Column(Float, default=0.0)
    defense_score = Column(Integer, default=0)
    defense_type = Column(String) # e.g., 'pushups'
    created_at = Column(DateTime, default=_default_now_naive_utc)

    # Ownership economy: 0 = free tier (unprotected), >0 = paid tier.
    # vault_balance doubles as the required Challenger Match amount for a siege.
    vault_balance = Column(Integer, default=0)

    owner = relationship("User", back_populates="domains")

class SiegeLog(Base):
    __tablename__ = "sieges_log"
    id = Column(Integer, primary_key=True, index=True)
    challenger_id = Column(Integer, ForeignKey("users.id"))
    target_domain_id = Column(Integer, ForeignKey("domains.id"))
    status = Column(String, default="pending_feat") # pending_feat, won, failed
    created_at = Column(DateTime, default=_default_now_naive_utc)

    # Snapshot of defender's score at siege creation — immutable for fair resolution
    defender_score_snapshot = Column(Integer, default=0)
    # Set on resolution
    challenger_fee = Column(Integer, default=0)      # Crystals staked by challenger (0 for free-tier targets)
    challenger_score = Column(Integer, nullable=True) # Defense Feat score submitted to resolve
    resolved_at = Column(DateTime, nullable=True)


class SiegeDiscount(Base):
    """Retry discount credit: created when a challenger fails a paid-tier siege. 20% of the forfeit
    is stored here and auto-applied on their next attempt against the same target_domain_id."""
    __tablename__ = "siege_discounts"
    id = Column(Integer, primary_key=True, index=True)
    challenger_id = Column(Integer, ForeignKey("users.id"), index=True)
    target_domain_id = Column(Integer, ForeignKey("domains.id"), index=True)
    amount = Column(Integer, default=0)               # Crystals of discount available
    consumed = Column(Integer, default=0)             # 0 = available, 1 = already applied
    created_at = Column(DateTime, default=_default_now_naive_utc)
    consumed_at = Column(DateTime, nullable=True)


# --- Epic 1: Bounty Board ---

class Merchant(Base):
    """B2B partner (local business) that can sponsor merchant_chest-type bounties at their storefront."""
    __tablename__ = "merchants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_type = Column(String, default="general")  # e.g., 'gym', 'cafe', 'retail'
    created_at = Column(DateTime, default=_default_now_naive_utc)

    bounties = relationship("Bounty", back_populates="merchant")


class Bounty(Base):
    """A geofenced quest. Two flavors:
       - 'daily'         : system-issued fitness task (e.g., 20 push-ups in DeWolf Park)
       - 'merchant_chest': sponsored, often score=0 (just visit), unlocks a coupon
    """
    __tablename__ = "bounties"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    bounty_type = Column(String, default="daily")
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=True)

    # Geofence
    target_lat = Column(Float)
    target_lng = Column(Float)
    radius_m = Column(Float, default=30.0)

    # Quest spec — activity_type maps to DEFENSE_TYPE_TO_STAT for stat increment.
    activity_type = Column(String, default="walk")
    target_score = Column(Integer, default=0)  # 0 = proximity-only (e.g., merchant chest)

    # Rewards
    xp_reward = Column(Integer, default=0)
    crystal_reward = Column(Integer, default=0)
    coupon_text = Column(String, nullable=True)  # Display text for merchant coupons

    # Lifecycle / pilot caps
    max_completions = Column(Integer, default=50)   # Bedford pilot constraint
    completions_count = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Integer, default=1)           # 1 = listable, 0 = retired
    created_at = Column(DateTime, default=_default_now_naive_utc)

    merchant = relationship("Merchant", back_populates="bounties")


class BountyCompletion(Base):
    """One row per (user, bounty) successful completion. Enforces single-claim-per-user and
    is the source of truth for issued coupon codes."""
    __tablename__ = "bounty_completions"
    id = Column(Integer, primary_key=True, index=True)
    bounty_id = Column(Integer, ForeignKey("bounties.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    score_submitted = Column(Integer, default=0)
    xp_awarded = Column(Integer, default=0)
    crystals_awarded = Column(Integer, default=0)
    coupon_code_issued = Column(String, nullable=True)
    completed_at = Column(DateTime, default=_default_now_naive_utc)
