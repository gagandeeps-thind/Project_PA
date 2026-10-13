from sqlalchemy import Integer, String, Float, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base
import datetime


def _default_now_naive_utc():
    """Naive UTC timestamp (tz stripped) for SQLite-compatible storage.
    Server-side fallback default; most timestamps now flow from the client device."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


# Opening Mana Crystal grant every new player receives at registration. Kept as a single
# named constant so the column default, the onboarding ledger row, and any backfill all
# agree on one number.
OPENING_CRYSTAL_BALANCE = 100

class User(Base):
    __tablename__ = "users"

    # Every database table needs a Primary Key (a unique ID)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    
    email: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String) # Notice we store hashed_password, NEVER plain text
    
    # Fitness Stats
    bmi: Mapped[float | None] = mapped_column(Float)
    avatar_class: Mapped[str | None] = mapped_column(String)
    rank: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String, default="Unawakened")  # Tied to Domain area
    cumulative_area: Mapped[float | None] = mapped_column(Float, default=0.0)  # Total km2 owned
    xp: Mapped[int | None] = mapped_column(Integer, default=0)
    streak: Mapped[int | None] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)

    # Virtual in-game currency; value and permitted uses are product-policy controlled.
    # The authoritative running balance. Every write to this column MUST flow through
    # services.ledger.apply_crystal_delta, which also appends a CrystalLedger row so the
    # invariant sum(CrystalLedger.delta for user) == mana_crystals always holds.
    mana_crystals: Mapped[int | None] = mapped_column(Integer, default=OPENING_CRYSTAL_BALANCE)

    # Party Attribute Stats — accumulate on every verified activity, drive Party Role assignment.
    # MVP keeps these as running totals; Phase 2 will recompute from a 30-day rolling ActivityLog.
    str_stat: Mapped[int | None] = mapped_column(Integer, default=0)  # Push-ups, squats, resistance
    agi_stat: Mapped[int | None] = mapped_column(Integer, default=0)  # Sprint, burpees, high-cadence
    end_stat: Mapped[int | None] = mapped_column(Integer, default=0)  # Long runs, walks, sustained volume
    con_stat: Mapped[int | None] = mapped_column(Integer, default=0)  # Planks, holds, streak precision

    # PRD-010: admins suspend a player without database edits. Non-null = suspended; the
    # v2 API refuses every mutation for a suspended player (see main.get_active_player).
    suspended_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # G4 session revocation: tokens issued (iat) before this instant are refused by the v2
    # API. "Sign out everywhere", password change, and account erasure move it forward.
    tokens_valid_after: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    domains = relationship("Domain", back_populates="owner")

class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    guild_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # For MVP SQLite, we store the polygon coordinates as a JSON string.
    # In production, this becomes: geometry = Column(Geometry('POLYGON'))
    geometry_json: Mapped[str | None] = mapped_column(String) 
    area_sqkm: Mapped[float | None] = mapped_column(Float, default=0.0)
    defense_score: Mapped[int | None] = mapped_column(Integer, default=0)
    defense_type: Mapped[str | None] = mapped_column(String) # e.g., 'pushups'
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)

    # Ownership economy: 0 = free tier (unprotected), >0 = paid tier.
    # vault_balance doubles as the required Challenger Match amount for a siege.
    vault_balance: Mapped[int | None] = mapped_column(Integer, default=0)

    owner = relationship("User", back_populates="domains")

class SiegeLog(Base):
    __tablename__ = "sieges_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    challenger_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    target_domain_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("domains.id"))
    status: Mapped[str | None] = mapped_column(String, default="pending_feat") # pending_feat, won, failed
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)

    # Snapshot of defender's score at siege creation — immutable for fair resolution
    defender_score_snapshot: Mapped[int | None] = mapped_column(Integer, default=0)
    # Set on resolution
    challenger_fee: Mapped[int | None] = mapped_column(Integer, default=0)      # Crystals staked by challenger (0 for free-tier targets)
    challenger_score: Mapped[int | None] = mapped_column(Integer, nullable=True) # Defense Feat score submitted to resolve
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class SiegeDiscount(Base):
    """Retry discount credit: created when a challenger fails a paid-tier siege. 20% of the forfeit
    is stored here and auto-applied on their next attempt against the same target_domain_id."""
    __tablename__ = "siege_discounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    challenger_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    target_domain_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("domains.id"), index=True)
    amount: Mapped[int | None] = mapped_column(Integer, default=0)               # Crystals of discount available
    consumed: Mapped[int | None] = mapped_column(Integer, default=0)             # 0 = available, 1 = already applied
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)
    consumed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


# --- Epic 1: Bounty Board ---

class Merchant(Base):
    """B2B partner (local business) that can sponsor merchant_chest-type bounties at their storefront.

    Activation lifecycle (v2.9):
      - On register: is_active=False, payment_status='payment_pending'.
      - Merchant calls /payments/intent → provider_payment_id is recorded.
      - Provider hits /payments/webhook with terminal status:
          * 'payment_successful' → is_active=True, last_payment_at set.
          * 'payment_pending'    → no change (still inactive).
          * 'payment_declined'   → stays inactive; merchant can retry.
      - Admin manual /admin/merchants/{id}/{activate,deactivate} endpoints exist as fallbacks
        for refunds, disputes, and demo seeding.
    """
    __tablename__ = "merchants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str | None] = mapped_column(String, index=True)
    email: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String)
    business_type: Mapped[str | None] = mapped_column(String, default="general")  # e.g., 'gym', 'cafe', 'retail'
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=False)  # True once pilot fee is paid
    # Payment tracking (v2.9). payment_status is the source of truth; is_active is derived
    # by the webhook handler so legacy reads of is_active stay correct.
    payment_status: Mapped[str | None] = mapped_column(String, default="payment_pending")  # payment_pending | payment_successful | payment_declined
    payment_provider_id: Mapped[str | None] = mapped_column(String, nullable=True)         # e.g., Stripe PaymentIntent ID
    pilot_fee_cents: Mapped[int | None] = mapped_column(Integer, default=5000)             # $50 USD default; per-merchant override possible
    last_payment_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)

    bounties = relationship("Bounty", back_populates="merchant")


class Bounty(Base):
    """A geofenced quest. Two flavors:
       - 'daily'         : system-issued fitness task (e.g., 20 push-ups in DeWolf Park)
       - 'merchant_chest': sponsored, often score=0 (just visit), unlocks a coupon
    """
    __tablename__ = "bounties"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    bounty_type: Mapped[str | None] = mapped_column(String, default="daily")
    merchant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("merchants.id"), nullable=True)

    # Geofence
    target_lat: Mapped[float | None] = mapped_column(Float)
    target_lng: Mapped[float | None] = mapped_column(Float)
    radius_m: Mapped[float | None] = mapped_column(Float, default=30.0)

    # Quest spec — activity_type maps to DEFENSE_TYPE_TO_STAT for stat increment.
    activity_type: Mapped[str | None] = mapped_column(String, default="walk")
    target_score: Mapped[int | None] = mapped_column(Integer, default=0)  # 0 = proximity-only (e.g., merchant chest)

    # Rewards
    xp_reward: Mapped[int | None] = mapped_column(Integer, default=0)
    crystal_reward: Mapped[int | None] = mapped_column(Integer, default=0)
    coupon_text: Mapped[str | None] = mapped_column(String, nullable=True)  # Display text for merchant coupons

    # Lifecycle / pilot caps
    max_completions: Mapped[int | None] = mapped_column(Integer, default=50)   # Bedford pilot constraint
    completions_count: Mapped[int | None] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[int | None] = mapped_column(Integer, default=1)           # 1 = listable, 0 = retired
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)

    merchant = relationship("Merchant", back_populates="bounties")


class BountyCompletion(Base):
    """One row per (user, bounty) successful completion. Enforces single-claim-per-user and
    is the source of truth for issued coupon codes.

    Coupon lifecycle (v2.12):
      - On bounty complete with `coupon_text` set: `coupon_code_issued` is minted, and
        `coupon_redeemed_at` stays NULL.
      - Merchant calls `POST /api/v1/coupons/{code}/redeem` at the till → stamps
        `coupon_redeemed_at` + `coupon_redeemed_by_merchant_id`. A re-redeem 409s.
    """
    __tablename__ = "bounty_completions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    bounty_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("bounties.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    score_submitted: Mapped[int | None] = mapped_column(Integer, default=0)
    xp_awarded: Mapped[int | None] = mapped_column(Integer, default=0)
    crystals_awarded: Mapped[int | None] = mapped_column(Integer, default=0)
    coupon_code_issued: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    coupon_redeemed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    coupon_redeemed_by_merchant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("merchants.id"), nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)


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
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str | None] = mapped_column(String, index=True)
    amount: Mapped[int | None] = mapped_column(Integer, default=0)        # crystals (Phase 1 unit)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    related_siege_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sieges_log.id"), nullable=True, index=True)
    related_bounty_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("bounties.id"), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)


# --- Player-side Crystal Ledger ---

class CrystalLedger(Base):
    """Append-only, double-entry-style journal of every Mana Crystal movement on the
    PLAYER side. `PlatformRevenue` is the platform-side ledger; this is its player-side
    counterpart. One row per balance mutation, written by services.ledger.apply_crystal_delta
    (the ONLY writer of User.mana_crystals).

    Invariant (enforced by scripts/reconcile_ledger.py --check, run in CI):
        sum(CrystalLedger.delta WHERE user_id == u) == User(u).mana_crystals

    `balance_after` is the wallet balance immediately after this row was applied, so the
    ledger is independently auditable without replaying every prior row.

    reason_code (string enum, not enforced at DB level):
      - 'opening_balance'     : the +100 grant a new player gets at registration
      - 'vault_lock'          : crystals moved from wallet into a domain Vault
      - 'siege_out_of_pocket' : challenger's match debited on a siege WIN
      - 'siege_win_payout'    : winner's 80% pot share credited on a siege WIN
      - 'siege_forfeit'       : challenger's match debited (forfeited) on a siege LOSS
      - 'bounty_reward'       : crystals awarded for completing a bounty
      - 'crystal_purchase'    : (Phase 3) real-money one-way top-up, credited on a Stripe
                                payment_intent.succeeded webhook (see CrystalPurchase)

    Append-only: there is no update or delete path anywhere in the codebase.
    """
    __tablename__ = "crystal_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)            # signed crystal movement (+credit / -debit)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)    # wallet balance immediately after this row
    reason_code: Mapped[str] = mapped_column(String, index=True, nullable=False)
    related_siege_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sieges_log.id"), nullable=True)
    related_bounty_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("bounties.id"), nullable=True)
    related_domain_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("domains.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)


# --- Hardening Sprint v2.7: ActivityLog ---

class ActivityLog(Base):
    """One row per verified physical activity. Source of truth for the 30-day rolling
    Party Stats window. Lifetime totals on `User.{str_stat,agi_stat,end_stat,con_stat}` stay
    (cheap aggregate); this table powers windowed queries like 'leading stat over the last
    30 days'."""
    __tablename__ = "activity_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    activity_type: Mapped[str | None] = mapped_column(String, index=True)         # pushups | squats | sprint | run | walk | burpees | plank | hold
    score: Mapped[int | None] = mapped_column(Integer, default=0)                  # reps (or seconds for holds)
    stat_column: Mapped[str | None] = mapped_column(String, nullable=True)         # which Party Stat this fed (str/agi/end/con)
    confidence: Mapped[float | None] = mapped_column(Float, default=1.0)              # 1.0 if no proof attached; ML Referee's confidence otherwise
    verified: Mapped[int | None] = mapped_column(Integer, default=0)                # 1 if a passing ActivityProof was attached
    source: Mapped[str | None] = mapped_column(String, index=True)                  # 'domain_claim' | 'siege_resolve' | 'bounty_complete'
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True)          # ID of the originating domain/siege/bounty row
    occurred_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, index=True)           # device_timestamp at the moment of the activity
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)


class Admin(Base):
    """Single-tenant admin account. Used for the in-app admin portal route — when admin
    credentials are entered in the Flutter app, the app switches to admin UI instead of
    the game UI. Public admin registration is intentionally not exposed; rows are seeded
    via `Osiris_backend/scripts/seed_admin.py`."""
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class TelemetrySession(Base):
    """Metadata row per submitted workout/activity. The ML training pipeline reads this to
    discover which sessions to load samples for. Linked back to the ActivityLog row that
    represents the gameplay-side outcome (XP awarded, stat incremented, etc.).

    Sensor samples themselves live in TelemetryData (one row per sensor type) so callers
    can selectively load only the channels they need for a given training task."""
    __tablename__ = "telemetry_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    activity_log_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("activity_log.id"), nullable=True, index=True)
    activity_type: Mapped[str | None] = mapped_column(String, index=True)
    declared_score: Mapped[int | None] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=0.0)
    confidence: Mapped[float | None] = mapped_column(Float, default=0.0)
    verified: Mapped[int | None] = mapped_column(Integer, default=0)              # 1 if ml_referee passed
    sample_count_accel: Mapped[int | None] = mapped_column(Integer, default=0)
    sample_count_gyro: Mapped[int | None] = mapped_column(Integer, default=0)
    sample_count_mag: Mapped[int | None] = mapped_column(Integer, default=0)
    sample_count_gps: Mapped[int | None] = mapped_column(Integer, default=0)
    sample_count_barometer: Mapped[int | None] = mapped_column(Integer, default=0)
    has_pose: Mapped[bool | None] = mapped_column(Boolean, default=False)
    occurred_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, index=True)         # device_timestamp
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)


class TelemetryData(Base):
    """Raw sensor samples, JSON-serialized. One row per (session, sensor_type).
    sensor_type ∈ {'accel', 'gyro', 'magnetometer', 'gps', 'barometer', 'pose'}.

    samples_json shape varies by sensor — see the corresponding Pydantic model in main.py:
      - accel/gyro/magnetometer: list of {t_ms, ax/gx/mx, ay/gy/my, az/gz/mz}
      - gps:                     list of {t_ms, lat, lng, accuracy_m, speed_mps, altitude_m}
      - barometer:               list of {t_ms, pressure_hpa}
      - pose:                    single object (rep_count, min/max joint angle, avg duration)
    """
    __tablename__ = "telemetry_data"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("telemetry_sessions.id"), index=True)
    sensor_type: Mapped[str | None] = mapped_column(String, index=True)
    sample_count: Mapped[int | None] = mapped_column(Integer, default=0)
    samples_json: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)


class PaymentWebhookEvent(Base):
    """Idempotency guard for the payment webhook. Stripe (and most providers) retry failed
    webhook deliveries; without dedup, the same successful payment can credit revenue twice
    if the first response is slow or 5xx's. Every inbound webhook records its
    `provider_event_id` here BEFORE side effects run — a duplicate insert (unique constraint
    violation) makes the handler return the prior outcome instead of re-processing.

    `provider_event_id` is the provider's top-level event id (Stripe: `event.id`), distinct
    from `payment_provider_id` (Stripe: `payment_intent.id`) — multiple events can reference
    the same payment intent, so we dedupe at the event level.
    """
    __tablename__ = "payment_webhook_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_event_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    merchant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("merchants.id"), nullable=True, index=True)
    # Phase 3: the same dedup table now guards player crystal-purchase webhooks too, so an
    # event references either a merchant (pilot fee) or a user (crystal top-up), never both.
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_type: Mapped[str | None] = mapped_column(String, nullable=True)  # Stripe event.type, e.g. 'payment_intent.succeeded'
    payment_status: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc, index=True)


class CrystalPurchase(Base):
    """Phase 3 — a player's real-money Mana Crystal top-up (one-way: money -> crystals).

    Lifecycle:
      - Player calls POST /payments/crystals/intent with a server-defined pack id. We create a
        Stripe PaymentIntent (server sets the price — the client never sends an amount) and
        insert this row with status='pending'.
      - Stripe fires payment_intent.succeeded -> the webhook credits the crystals via
        services.ledger.apply_crystal_delta exactly once and stamps status='succeeded' +
        crystal_ledger_id + fulfilled_at.
      - payment_intent.payment_failed -> status='failed', no crystals.

    Idempotency / no-double-mint (RED LINE): `stripe_payment_intent_id` is UNIQUE and the
    webhook only credits a row whose status is not already 'succeeded'. A retried/duplicate
    webhook for the same intent is therefore a no-op. This row is the player-purchase
    counterpart to PaymentWebhookEvent (which dedupes at the Stripe event level).

    Purchase fulfillment is recorded as a one-way provider-confirmed credit in this model.
    """
    __tablename__ = "crystal_purchases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    pack_id: Mapped[str] = mapped_column(String, nullable=False)              # server pack key, e.g. 'starter'
    crystal_amount: Mapped[int] = mapped_column(Integer, nullable=False)      # crystals to credit on success
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)        # price charged (server-authoritative)
    currency: Mapped[str | None] = mapped_column(String, default="usd")
    stripe_payment_intent_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    status: Mapped[str | None] = mapped_column(String, default="pending", index=True)  # pending | succeeded | failed
    crystal_ledger_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("crystal_ledger.id"), nullable=True)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)
    fulfilled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class ProofConsumed(Base):
    """Idempotency / replay-attack guard. One row per `ActivityProof` ever consumed by an
    action endpoint (domain claim, siege resolve, bounty complete). The `proof_key` is a
    SHA-256 hash of (user_id, device_timestamp, activity_type, declared_score, accelerometer
    samples) — re-submitting the same proof produces the same hash and the second consumer
    receives a 409 Conflict."""
    __tablename__ = "proofs_consumed"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    proof_key: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)               # 'domain_claim' | 'siege_resolve' | 'bounty_complete'
    consumed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=_default_now_naive_utc)


class RunSession(Base):
    """First-release running session and its server-authoritative outcome."""
    __tablename__ = "run_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    activity_type: Mapped[str] = mapped_column(String, nullable=False, default="run", index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="created", index=True)
    device_started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    device_finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    point_count: Mapped[int | None] = mapped_column(Integer, default=0)
    distance_m: Mapped[float | None] = mapped_column(Float, default=0.0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=0.0)
    route_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    finish_idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True, unique=True, index=True)
    verification_status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "id", name="uq_run_sessions_user_id_id"),)


class RoutePoint(Base):
    """Private route evidence. It is never returned by public discovery endpoints."""
    __tablename__ = "route_points"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_session_id: Mapped[int] = mapped_column(Integer, ForeignKey("run_sessions.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    t_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)

    __table_args__ = (UniqueConstraint("run_session_id", "sequence", name="uq_route_points_session_sequence"),)


class VerificationDecision(Base):
    """Immutable, explainable verification result for a run."""
    __tablename__ = "verification_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_session_id: Mapped[int] = mapped_column(Integer, ForeignKey("run_sessions.id"), nullable=False, unique=True)
    rules_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    metrics_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)


# --- R2: Course and challenge pilot ---------------------------------------------

class Course(Base):
    """A versioned course normalized from one accepted run (PRD-005).

    `route_json`, `start_*` and `finish_*` are PRIVATE: only the owner and admins see them.
    Public discovery uses `public_lat`/`public_lng`, a grid-snapped marker derived from the
    route midpoint (never the start or finish, which are the likeliest home/work points).

    status: active | suspended | retired
    """
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # One course proposal per accepted run; the unique constraint is the idempotency guard.
    source_run_session_id: Mapped[int] = mapped_column(Integer, ForeignKey("run_sessions.id"), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rules_version: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    benchmark_seconds: Mapped[float] = mapped_column(Float, nullable=False)   # owner's verified time on the source run
    is_loop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    start_lat: Mapped[float] = mapped_column(Float, nullable=False)
    start_lng: Mapped[float] = mapped_column(Float, nullable=False)
    finish_lat: Mapped[float] = mapped_column(Float, nullable=False)
    finish_lng: Mapped[float] = mapped_column(Float, nullable=False)
    route_json: Mapped[str] = mapped_column(String, nullable=False)          # simplified [[lat, lng], ...]
    route_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    public_lat: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    public_lng: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)


class Challenge(Base):
    """Immutable asynchronous challenge published against a Course (PRD-006).

    Every field in `services.challenges.TERMS_FIELDS` is frozen at publish time and hashed
    into `terms_hash`; each attempt snapshots that hash when the challenger joins.
    Corrections create a new challenge — there is no edit path.

    status: open -> closed -> settled, or suspended | voided by an admin.
    entry_crystals is always 0 in this release (ADR-005: no stakes until the settlement
    equation is approved); the column exists so the terms contract is stable.
    """
    __tablename__ = "challenges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", index=True)
    rules_version: Mapped[str] = mapped_column(String, nullable=False)
    course_version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    entry_crystals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_policy: Mapped[str] = mapped_column(String, nullable=False, default="xp_badge")
    win_xp: Mapped[int] = mapped_column(Integer, nullable=False)
    participation_xp: Mapped[int] = mapped_column(Integer, nullable=False)
    eligibility: Mapped[str] = mapped_column(String, nullable=False, default="verified_runner")
    privacy_mode: Mapped[str] = mapped_column(String, nullable=False, default="generalized")
    safety_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    opens_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    closes_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, index=True)
    terms_hash: Mapped[str] = mapped_column(String, nullable=False)
    publish_idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    status_reason: Mapped[str | None] = mapped_column(String, nullable=True)        # admin suspend/void reason
    settled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)


class ChallengeAttempt(Base):
    """One player's participation in a Challenge.

    status: joined -> accepted | rejected | review_required -> (outcome set)
    outcome: won | lost | voided (NULL until the attempt is decided)
    """
    __tablename__ = "challenge_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    challenge_id: Mapped[int] = mapped_column(Integer, ForeignKey("challenges.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="joined", index=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    terms_hash: Mapped[str] = mapped_column(String, nullable=False)          # snapshot at join time
    run_session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("run_sessions.id"), nullable=True, unique=True)
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    course_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_codes_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    xp_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    defender_xp_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    joined_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)
    submitted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admins.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (UniqueConstraint("challenge_id", "user_id", name="uq_challenge_attempts_challenge_user"),)


class UserBadge(Base):
    """A non-cash achievement. One row per (user, badge_code)."""
    __tablename__ = "user_badges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    badge_code: Mapped[str] = mapped_column(String, nullable=False)
    awarded_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "badge_code", name="uq_user_badges_user_badge"),)


class AuditEvent(Base):
    """Append-only trail of security, admin, challenge, and economy actions (PRD-008).
    `details_json` must never carry raw coordinates or secrets."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_type: Mapped[str] = mapped_column(String, nullable=False)          # player | admin | system
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    details_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False, index=True)


# --- Growth release G1: core habit loop -------------------------------------------

class PlayerProfile(Base):
    """Plain-language player profile created by the BMI-free v2 registration.

    No body measurements are stored here: the goal drives quest sizing, and identity is a
    label derived from it. `utc_offset_minutes` is the device's last reported offset, used
    only to decide which local day a run belongs to for quests.
    """
    __tablename__ = "player_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    goal: Mapped[str] = mapped_column(String, nullable=False, default="fitness")
    utc_offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Public achievement page is opt-in. Location is never on it.
    public_profile: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    location_consent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    onboarding_completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    referral_code: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    referred_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # Set once the referral reward has been granted (after the referee's first verified run).
    referral_rewarded_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # none | pending | rewarded | capped | same_device (see growth_social referral rules)
    referral_status: Mapped[str] = mapped_column(String, nullable=False, default="none")
    # Install id reported at sign-up; used only to refuse self-referral rewards.
    signup_install_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # G3: the home city the player chose (a slug such as "bedford-ns"), never derived from
    # GPS. Local rankings group by it. Appearing by name on leaderboards is opt-in.
    city: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    leaderboard_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # G4: v2 registrations must grant location consent before recording a run. Players from
    # the legacy v1 onboarding predate the consent screen and are not blocked (False).
    consent_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)


class QuestAward(Base):
    """One XP award per (player, quest key). The unique constraint makes quest rewards
    idempotent no matter how many runs complete the same quest."""
    __tablename__ = "quest_awards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    quest_key: Mapped[str] = mapped_column(String, nullable=False)        # daily:YYYY-MM-DD | weekly:YYYY-Www
    rules_version: Mapped[str] = mapped_column(String, nullable=False)
    target_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    xp_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    run_session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("run_sessions.id"), nullable=True)
    awarded_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "quest_key", name="uq_quest_awards_user_key"),)


class AnalyticsEvent(Base):
    """Product funnel event. Server-emitted for milestones it can observe (account,
    onboarding, first verified run, challenge join/complete, invite accepted) and
    client-emitted for the rest (app_open, install). Never carries coordinates."""
    __tablename__ = "analytics_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    install_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    event_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="server")   # server | client
    properties_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    occurred_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False, index=True)


# --- Growth release G2: sharing, invites, public pages --------------------------------

class ShareCard(Base):
    """A public, unguessable link to one achievement ("I completed this route").

    `stats_json` holds only what the owner agreed to show: distance, time, rank, badge.
    Never a route, start/finish point, or map. Owners can revoke a card.
    kind: run | challenge_result | quest | badge
    """
    __tablename__ = "share_cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headline: Mapped[str] = mapped_column(String, nullable=False)
    stats_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    challenge_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("challenges.id"), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "kind", "entity_id", name="uq_share_cards_user_kind_entity"),)


class ChallengeInvite(Base):
    """Invite-a-friend link for one challenge. Carries the inviter's referral code so a
    friend who signs up through it is linked for the referral reward."""
    __tablename__ = "challenge_invites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    challenge_id: Mapped[int] = mapped_column(Integer, ForeignKey("challenges.id"), nullable=False, index=True)
    inviter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    opens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signups: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)

    __table_args__ = (UniqueConstraint("challenge_id", "inviter_id", name="uq_challenge_invites_challenge_inviter"),)


# --- Growth release G3: communities, seasons ------------------------------------------

class Community(Base):
    """A running club, gym, university group, trainer group, race, cafe, or workplace with
    its own branded leaderboard, weekly team goal, and featured challenges.

    Created by a player organiser. `verified` is set by an admin after checking that the
    organisation is real; unverified communities work but show no verified mark.
    Private communities (corporate wellness, university teams) need `join_code`.
    status: active | suspended
    """
    __tablename__ = "communities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String, nullable=True)       # "#RRGGBB"
    city: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="public")
    join_code: Mapped[str | None] = mapped_column(String, nullable=True)
    weekly_team_goal_km: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    # Non-cash partner perk shown to members, e.g. "10% off at Harbour Cafe with your badge".
    perk_text: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)
    status_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)


class CommunityMember(Base):
    __tablename__ = "community_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    community_id: Mapped[int] = mapped_column(Integer, ForeignKey("communities.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")   # owner | admin | member
    joined_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)

    __table_args__ = (UniqueConstraint("community_id", "user_id", name="uq_community_members_community_user"),)


class CommunityChallenge(Base):
    """A challenge featured by a community (its branded challenge). Featuring never changes
    the challenge's immutable terms."""
    __tablename__ = "community_challenges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    community_id: Mapped[int] = mapped_column(Integer, ForeignKey("communities.id"), nullable=False, index=True)
    challenge_id: Mapped[int] = mapped_column(Integer, ForeignKey("challenges.id"), nullable=False, index=True)
    added_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)

    __table_args__ = (UniqueConstraint("community_id", "challenge_id", name="uq_community_challenges"),)


class Season(Base):
    """A time-boxed city campaign (e.g. "Bedford Autumn Season"). Players who join, and the
    communities they belong to, are ranked by capped activity points inside the window."""
    __tablename__ = "seasons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    perk_text: Mapped[str | None] = mapped_column(String, nullable=True)
    starts_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)


class SeasonEntry(Base):
    __tablename__ = "season_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    season_id: Mapped[int] = mapped_column(Integer, ForeignKey("seasons.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    joined_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)

    __table_args__ = (UniqueConstraint("season_id", "user_id", name="uq_season_entries_season_user"),)


# --- Growth release G4: safety and trust -----------------------------------------------

class ConsentRecord(Base):
    """Append-only consent ledger. The current state lives on PlayerProfile; this table is
    the evidence of when each choice was made and under which policy version.
    kind: location | public_profile | leaderboard"""
    __tablename__ = "consent_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)


class Report(Base):
    """A player report about a user, challenge, course, community, or share card.
    status: open | actioned | dismissed. `reporter_id` is cleared if the reporter erases
    their account; the report itself is kept for the abuse record."""
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reporter_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    target_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", index=True)
    resolution_note: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admins.id"), nullable=True)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False, index=True)

    __table_args__ = (UniqueConstraint("reporter_id", "target_type", "target_id", name="uq_reports_reporter_target"),)


class UserBlock(Base):
    """`blocker_id` never sees `blocked_id`'s challenges, and neither can join the other's."""
    __tablename__ = "user_blocks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    blocker_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    blocked_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_default_now_naive_utc, nullable=False)

    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_pair"),)
