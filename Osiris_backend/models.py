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
    is_active = Column(Boolean, default=False)  # True once pilot fee is paid
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


# --- Hardening Sprint: PlatformRevenue Ledger ---

class PlatformRevenue(Base):
    """Append-only ledger of every Mana Crystal that flowed to the platform. Each row is one
    revenue event so we can audit what the system has earned over time.

    Sources (string enum, not enforced at DB level):
      - 'siege_war_tax'      : 20% cut from a paid-tier siege win pot
      - 'siege_loss_keep'    : 30% cut from a paid-tier siege loss
      - 'merchant_pilot_fee' : (Phase 2) flat fee paid by merchants to host a chest
      - 'black_market_fee'   : (Phase 2) 15% transaction fee
      - 'tower_pass'         : (Phase 2) subscription revenue
    """
    __tablename__ = "platform_revenue"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, index=True)
    amount = Column(Integer, default=0)        # crystals (Phase 1 unit)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    related_siege_id = Column(Integer, ForeignKey("sieges_log.id"), nullable=True, index=True)
    related_bounty_id = Column(Integer, ForeignKey("bounties.id"), nullable=True, index=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=_default_now_naive_utc)


# --- Hardening Sprint v2.7: ActivityLog ---

class ActivityLog(Base):
    """One row per verified physical activity. Source of truth for the 30-day rolling
    Party Stats window. Lifetime totals on `User.{str_stat,agi_stat,end_stat,con_stat}` stay
    (cheap aggregate); this table powers windowed queries like 'leading stat over the last
    30 days'."""
    __tablename__ = "activity_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    activity_type = Column(String, index=True)         # pushups | squats | sprint | run | walk | burpees | plank | hold
    score = Column(Integer, default=0)                  # reps (or seconds for holds)
    stat_column = Column(String, nullable=True)         # which Party Stat this fed (str/agi/end/con)
    confidence = Column(Float, default=1.0)              # 1.0 if no proof attached; ML Referee's confidence otherwise
    verified = Column(Integer, default=0)                # 1 if a passing ActivityProof was attached
    source = Column(String, index=True)                  # 'domain_claim' | 'siege_resolve' | 'bounty_complete'
    related_id = Column(Integer, nullable=True)          # ID of the originating domain/siege/bounty row
    occurred_at = Column(DateTime, index=True)           # device_timestamp at the moment of the activity
    created_at = Column(DateTime, default=_default_now_naive_utc)


class Admin(Base):
    """Single-tenant admin account. Used for the in-app admin portal route — when admin
    credentials are entered in the Flutter app, the app switches to admin UI instead of
    the game UI. Public admin registration is intentionally not exposed; rows are seeded
    via `Osiris_backend/scripts/seed_admin.py`."""
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    created_at = Column(DateTime, default=_default_now_naive_utc)
    last_login_at = Column(DateTime, nullable=True)


class ProofConsumed(Base):
    """Idempotency / replay-attack guard. One row per `ActivityProof` ever consumed by an
    action endpoint (domain claim, siege resolve, bounty complete). The `proof_key` is a
    SHA-256 hash of (user_id, device_timestamp, activity_type, declared_score, accelerometer
    samples) — re-submitting the same proof produces the same hash and the second consumer
    receives a 409 Conflict."""
    __tablename__ = "proofs_consumed"
    id = Column(Integer, primary_key=True, index=True)
    proof_key = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    source = Column(String, nullable=True)               # 'domain_claim' | 'siege_resolve' | 'bounty_complete'
    consumed_at = Column(DateTime, default=_default_now_naive_utc)
