"""Request and response models (Pydantic) of the routers in `routers/`.
Database tables live in models.py; growth routers keep their own models next to their endpoints."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from core.security import NewPassword
from services import challenges as challenge_rules



# --- Pydantic Models (Data Validation) ---
# NOTE: Do not confuse Pydantic models with SQLAlchemy models!
# - SQLAlchemy models (in models.py) define the structure of the DATABASE tables.
# - Pydantic models (here) define the structure of the JSON data we receive or return via the API.

# The JSON shape we expect when a user registers
class UserCreate(BaseModel):
    email: EmailStr
    password: NewPassword = Field(..., description="8-72 characters (bcrypt's byte limit).")
    weight_kg: float = Field(..., gt=0, description="Weight in kg must be greater than 0")
    height_m: float = Field(..., gt=0, description="Height in meters must be greater than 0")
    preferred_path: str = "Balance"  # Options: Strength, Cardio, Balance
    device_timestamp: datetime = Field(..., description="Client device's current datetime (ISO 8601)")

# The JSON shape we expect when a user logs in
class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=72)
    device_timestamp: datetime = Field(..., description="Client device's current datetime (ISO 8601)")

# --- Unified auth (v2.8): role-aware login ---
# Frontend posts to /api/v1/auth/login; backend probes Admin → Merchant → User in that
# order and returns the matching role. The Flutter app uses `role` to decide which UI tree
# to render — game vs. merchant portal vs. admin portal.

class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=72)
    device_timestamp: datetime = Field(..., description="Client device's current datetime (ISO 8601)")

class AuthLoginResponse(BaseModel):
    role: str          # 'admin' | 'merchant' | 'player'
    id: int            # role-specific primary key
    email: EmailStr
    name: str          # display name
    message: str
    access_token: str
    token_type: str = "bearer"

# The JSON shape for a single GPS point in our Domain trace
class Coordinate(BaseModel):
    lat: float
    lng: float
    timestamp: datetime

# --- Epic 2: ML Referee Pydantic shapes ---
# (Defined here, ahead of DomainCreate/SiegeResolveRequest/BountyCompleteRequest, because
# those endpoints embed an optional ActivityProof and need the type already in scope.)

# A single accelerometer sample. `t_ms` is millis since the activity start (client-relative).
class AccelerometerSample(BaseModel):
    t_ms: int = Field(..., ge=0)
    ax: float
    ay: float
    az: float

# Gyroscope: rotational rate in rad/s on each device axis.
class GyroscopeSample(BaseModel):
    t_ms: int = Field(..., ge=0)
    gx: float
    gy: float
    gz: float

# Magnetometer: magnetic field strength on each device axis (μT).
class MagnetometerSample(BaseModel):
    t_ms: int = Field(..., ge=0)
    mx: float
    my: float
    mz: float

# GPS sample: world position + accuracy + optional speed/altitude.
class GpsSample(BaseModel):
    t_ms: int = Field(..., ge=0)
    lat: float
    lng: float
    accuracy_m: Optional[float] = None
    speed_mps: Optional[float] = None
    altitude_m: Optional[float] = None

# Barometer: atmospheric pressure (hPa) — useful for stair-climb / altitude-change inference.
class BarometerSample(BaseModel):
    t_ms: int = Field(..., ge=0)
    pressure_hpa: float

# Summary of MediaPipe pose data extracted on-device. Sent for camera-verified exercises only.
class PoseSummary(BaseModel):
    rep_count: int = Field(..., ge=0)
    min_joint_angle_deg: Optional[float] = None
    max_joint_angle_deg: Optional[float] = None
    avg_rep_duration_ms: Optional[float] = None

# Per-channel sample cap (DoS guard, v2.11). 20000 samples comfortably accommodates a
# ~7-minute workout at 50 Hz; longer activities should be chunked client-side. Without
# this cap a malicious client could OOM the server with multi-megabyte payloads.
MAX_SAMPLES_PER_CHANNEL = 20000

# The proof envelope a client posts to vouch for an activity. v2.10 expanded the sensor
# suite: ml_referee still gates on accelerometer + pose (cheap, well-understood), but the
# full payload is persisted in TelemetrySession + TelemetryData for ML training and richer
# fraud-detection in Phase 2.
class ActivityProof(BaseModel):
    activity_type: str                                     # pushups | squats | sprint | run | walk | burpees | plank | hold
    declared_score: int = Field(..., ge=0)
    duration_seconds: float = Field(..., gt=0)
    accelerometer: List[AccelerometerSample] = Field(default_factory=list, max_length=MAX_SAMPLES_PER_CHANNEL)
    gyroscope: List[GyroscopeSample] = Field(default_factory=list, max_length=MAX_SAMPLES_PER_CHANNEL)
    magnetometer: List[MagnetometerSample] = Field(default_factory=list, max_length=MAX_SAMPLES_PER_CHANNEL)
    gps: List[GpsSample] = Field(default_factory=list, max_length=MAX_SAMPLES_PER_CHANNEL)
    barometer: List[BarometerSample] = Field(default_factory=list, max_length=MAX_SAMPLES_PER_CHANNEL)
    pose: Optional[PoseSummary] = None
    device_timestamp: datetime

# Verdict returned by the verifier.
class VerificationResult(BaseModel):
    verified: bool
    confidence: float
    verified_score: int
    activity_type: str
    flags: List[str]


# The JSON shape we promise to return to the frontend when sending user data
class UserProfile(BaseModel):
    id: int
    # Plain str: older v2 sign-ups stored addresses EmailStr rejects, and output must not fail on them.
    email: str
    bmi: Optional[float] = None  # v2 registrations collect no body measurements
    avatar_class: str
    xp: int
    rank: str
    title: str
    cumulative_area: float
    last_activity_date: datetime
    streak: int
    mana_crystals: int
    str_stat: int
    agi_stat: int
    end_stat: int
    con_stat: int

    class Config:
        # Tells Pydantic to read data even if it's not a standard Python dictionary (i.e., read from SQLAlchemy DB objects)
        from_attributes = True


# --- First-release running loop ------------------------------------------------

class RunSessionCreate(BaseModel):
    # Foot sports only: game rules (quests, boards, challenges) count every verified session as
    # running or walking distance, so rides wait for per-sport rules and boards.
    activity_type: str = Field(default="run", pattern="^(run|jog|walk|hike)$")
    device_started_at: datetime


class RunSessionStart(BaseModel):
    device_started_at: datetime


class RoutePointInput(BaseModel):
    sequence: int = Field(..., ge=0)
    t_ms: int = Field(..., ge=0)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0, le=10000)
    speed_mps: Optional[float] = Field(default=None, ge=0, le=100)
    altitude_m: Optional[float] = Field(default=None, ge=-1000, le=10000)


class RoutePointBatch(BaseModel):
    points: List[RoutePointInput] = Field(..., min_length=1, max_length=500)


class RunSessionFinish(BaseModel):
    device_finished_at: datetime
    idempotency_key: str = Field(..., min_length=8, max_length=128)


class RunSessionSummary(BaseModel):
    id: int
    activity_type: str
    status: str
    verification_status: Optional[str] = None
    point_count: int
    distance_m: float
    duration_seconds: float
    route_hash: Optional[str] = None
    rejection_reason: Optional[str] = None
    # From the verification decision; null until the run is finished.
    moving_seconds: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    xp_awarded: int = 0
    message: str


# The JSON shape we expect when a user submits a completed territory run
class DomainCreate(BaseModel):
    owner_id: int
    coordinates: List[Coordinate]
    defense_score: int
    defense_type: str = "pushups"
    device_timestamp: datetime = Field(..., description="Client device's current datetime (ISO 8601)")
    # Optional ML-Referee proof. If supplied, the server verifies it and uses verified_score
    # as the canonical defense_score; if rejected, the whole submission 400s.
    defense_proof: Optional[ActivityProof] = None

# The JSON shape we return after a territory is successfully claimed
class DomainResponse(BaseModel):
    id: int
    area_sqkm: float
    defense_score: int
    message: str
    sieges_triggered: int = 0
    xp_awarded: int = 0

# v2.10 — public read shape used by GET /api/v1/domains/nearby for the Flutter map render.
# Excludes hashed secrets and ownership internals; exposes everything a player needs to
# decide whether to siege.
class DomainSummary(BaseModel):
    id: int
    owner_id: int
    area_sqkm: float
    defense_score: int
    defense_type: str
    vault_balance: int
    is_protected: bool                  # vault_balance > 0
    geometry: List[dict]                # parsed polygon coords [{lat, lng}, ...]
    centroid_lat: float
    centroid_lng: float
    distance_km: float

# The JSON shape a user posts to lock (or top up) an Ownership Fee in a Domain's Vault
class VaultLockRequest(BaseModel):
    user_id: int
    amount: int = Field(..., gt=0, description="Target vault balance in Mana Crystals")

# The JSON shape we return after a vault lock succeeds
class VaultLockResponse(BaseModel):
    domain_id: int
    vault_balance: int
    crystals_spent: int
    mana_crystals_remaining: int
    message: str

# The JSON shape a challenger posts to resolve a pending siege
class SiegeResolveRequest(BaseModel):
    challenger_score: int = Field(..., ge=0)
    device_timestamp: datetime = Field(..., description="Client device's current datetime (ISO 8601)")
    # Optional ML-Referee proof for the Defense Feat. If supplied and verified, the
    # verified_score replaces challenger_score; if rejected, the resolve 400s.
    challenger_proof: Optional[ActivityProof] = None

# The JSON shape we return after a siege resolves
class SiegeResolveResponse(BaseModel):
    siege_id: int
    status: str                  # "won" or "failed"
    defender_score: int
    challenger_score: int
    crystals_awarded: int        # 0 for free-tier wins / losses
    xp_awarded: int
    discount_applied: int = 0    # Retry-discount crystals auto-applied to this attempt
    new_discount_banked: int = 0 # Discount crystals banked for the NEXT retry (on loss)
    message: str

# The JSON shape returned for the Party Role resolver (Epic 6)
class PartyRoleResponse(BaseModel):
    user_id: int
    role: str                    # Vanguard / Striker / Scout / Strategist
    str_stat: int
    agi_stat: int
    end_stat: int
    con_stat: int
    leading_stat: str

# --- Epic 1: Bounty Board Pydantic shapes ---

# JSON to register a B2B Merchant
class MerchantCreate(BaseModel):
    name: str
    email: EmailStr
    password: NewPassword
    business_type: str = "general"

class MerchantResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    business_type: str

    class Config:
        from_attributes = True


# --- v2.9: Merchant payment lifecycle Pydantic shapes ---

class MerchantProfile(BaseModel):
    """Full merchant profile including activation + payment status. Returned to the merchant
    themselves (post-login refresh) and to admins."""
    id: int
    name: str
    email: EmailStr
    business_type: str
    is_active: bool
    payment_status: str
    pilot_fee_cents: int
    payment_provider_id: Optional[str] = None
    last_payment_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class PaymentIntentResponse(BaseModel):
    """Returned when a merchant initiates the pilot-fee payment. `client_secret` is what the
    Flutter Stripe SDK uses to confirm the card on-device; `publishable_key` lets the client
    init the SDK from the server's config so the pk isn't pinned in two places."""
    merchant_id: int
    pilot_fee_cents: int
    provider_payment_id: str         # Stripe PaymentIntent id (pi_...)
    payment_status: str
    client_secret: Optional[str] = None
    publishable_key: Optional[str] = None
    next_action: str



class CrystalPackInfo(BaseModel):
    pack_id: str
    label: str
    crystals: int
    amount_cents: int
    currency: str


class CrystalPurchaseIntentRequest(BaseModel):
    pack_id: str  # must be a key of CRYSTAL_PACKS; price is looked up server-side


class CrystalPurchaseIntentResponse(BaseModel):
    purchase_id: int
    pack_id: str
    crystal_amount: int
    amount_cents: int
    currency: str
    payment_intent_id: str           # Stripe PaymentIntent id (pi_...)
    client_secret: str
    publishable_key: Optional[str] = None
    status: str

class PaymentWebhookRequest(BaseModel):
    """Payload from the payment provider when a payment terminal-state is reached.

    `provider_event_id` is the provider's top-level event id (Stripe sends `event.id` —
    distinct from `payment_intent.id`). Optional during MVP smoke tests; required by real
    providers since they all retry failed deliveries. When present, we dedup against the
    `payment_webhook_events` table so a duplicate delivery is a no-op."""
    merchant_id: int
    payment_status: str       # 'payment_successful' | 'payment_pending' | 'payment_declined'
    provider_payment_id: str
    amount_cents: int
    occurred_at: datetime
    provider_event_id: Optional[str] = None

class PaymentWebhookResponse(BaseModel):
    merchant_id: int
    payment_status: str
    is_active: bool
    message: str

class AdminMerchantListItem(BaseModel):
    id: int
    name: str
    email: EmailStr
    business_type: str
    is_active: bool
    payment_status: str
    pilot_fee_cents: int
    last_payment_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class AdminMerchantToggleResponse(BaseModel):
    merchant_id: int
    is_active: bool
    payment_status: str
    message: str

# v2.10 — merchant analytics row, returned by GET /api/v1/merchants/{id}/bounties.
class MerchantBountyAnalytics(BaseModel):
    id: int
    title: str
    bounty_type: str
    target_lat: float
    target_lng: float
    is_active: bool
    completions_count: int
    completions_remaining: int
    coupons_issued: int                  # subset of completions where a coupon was minted
    xp_reward: int
    crystal_reward: int
    created_at: datetime
    expires_at: Optional[datetime] = None

# JSON to seed a Bounty (admin / merchant)
class BountyCreate(BaseModel):
    title: str
    description: str
    bounty_type: str = "daily"               # 'daily' | 'merchant_chest'
    merchant_id: Optional[int] = None
    target_lat: float
    target_lng: float
    radius_m: float = 30.0
    activity_type: str = "walk"
    target_score: int = Field(0, ge=0)        # 0 = proximity-only
    xp_reward: int = Field(50, ge=0)
    crystal_reward: int = Field(0, ge=0)
    coupon_text: Optional[str] = None
    max_completions: int = Field(50, gt=0)
    expires_at: Optional[datetime] = None

# Returned in the nearby-listing — includes computed distance from the caller.
class BountySummary(BaseModel):
    id: int
    title: str
    description: str
    bounty_type: str
    target_lat: float
    target_lng: float
    radius_m: float
    activity_type: str
    target_score: int
    xp_reward: int
    crystal_reward: int
    has_coupon: bool
    completions_remaining: int
    distance_km: float

# JSON to claim a bounty
class BountyCompleteRequest(BaseModel):
    user_id: int
    user_lat: float
    user_lng: float
    score: int = Field(..., ge=0)
    device_timestamp: datetime
    # Optional ML-Referee proof. If supplied and verified, verified_score replaces `score`;
    # if rejected, the completion 400s.
    score_proof: Optional[ActivityProof] = None

# JSON returned after a successful bounty claim
class BountyCompleteResponse(BaseModel):
    bounty_id: int
    completed: bool
    xp_awarded: int
    crystals_awarded: int
    stat_incremented: Optional[str]
    coupon_code: Optional[str]
    coupon_text: Optional[str]
    new_rank: str
    message: str


# --- R2 API v2: courses and challenges (PRD-005..008, ADR-004/005) -------------------

class CourseCreate(BaseModel):
    run_id: int
    name: str = Field(..., min_length=3, max_length=60)


class CourseSummary(BaseModel):
    """Owner view of a course. Includes the private route; never returned to other players."""
    id: int
    name: str
    status: str
    version: int
    rules_version: str
    distance_m: float
    benchmark_seconds: float
    is_loop: bool
    public_lat: float
    public_lng: float
    route: List[List[float]]
    open_challenge_id: Optional[int] = None
    created_at: datetime


class ChallengeCreate(BaseModel):
    course_id: int
    title: str = Field(..., min_length=3, max_length=80)
    window_hours: int = Field(..., ge=challenge_rules.MIN_WINDOW_HOURS, le=challenge_rules.MAX_WINDOW_HOURS)
    safety_notes: Optional[str] = Field(default=None, max_length=500)
    idempotency_key: str = Field(..., min_length=8, max_length=128)


class AttemptSummary(BaseModel):
    id: int
    challenge_id: int
    status: str
    outcome: Optional[str] = None
    run_id: Optional[int] = None
    elapsed_seconds: Optional[float] = None
    target_seconds: float
    course_coverage: Optional[float] = None
    reason_codes: List[str]
    xp_awarded: int
    terms_hash: str
    joined_at: datetime
    decided_at: Optional[datetime] = None


class ChallengePublic(BaseModel):
    """Privacy-safe challenge view (ADR-004): a generalized marker, the immutable terms, and
    aggregate participation. No owner identity, no route, no challenger identities."""
    id: int
    title: str
    status: str
    rules_version: str
    terms_hash: str
    course_distance_m: float
    target_seconds: float
    entry_crystals: int
    reward_policy: str
    win_xp: int
    participation_xp: int
    eligibility: str
    privacy_mode: str
    safety_notes: Optional[str] = None
    opens_at: datetime
    closes_at: datetime
    marker_lat: float
    marker_lng: float
    distance_km: Optional[float] = None
    attempt_count: int
    is_mine: bool
    my_attempt: Optional[AttemptSummary] = None


class ChallengeCourseRoute(BaseModel):
    challenge_id: int
    course_distance_m: float
    start_radius_m: float
    route: List[List[float]]


class AttemptSubmit(BaseModel):
    run_id: int


class BadgeOut(BaseModel):
    code: str
    label: str
    awarded_at: datetime


class ProgressionResponse(BaseModel):
    xp: int
    performance_rank: str
    rank_ladder_version: str
    rank_floor_xp: int = 0                   # where the current rank starts, for the progress gauge
    next_rank_xp: Optional[int] = None
    verified_runs: int
    courses: int
    challenges_won: int
    challenges_lost: int = 0
    challenges_played: int = 0
    lifetime_distance_km: float = 0.0
    global_rank: Optional[int] = None        # by XP among active players; None until the first XP
    defenses: int
    badges: List[BadgeOut]


# --- R2 admin trust console API (PRD-010) ----------------------------------------------

class AdminReason(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class AdminChallengeAction(BaseModel):
    action: str = Field(..., pattern="^(suspend|resume|void)$")
    reason: str = Field(..., min_length=3, max_length=500)


class AdminReviewDecision(BaseModel):
    decision: str = Field(..., pattern="^(accept|reject)$")
    note: str = Field(..., min_length=3, max_length=500)


class ReviewQueueItem(BaseModel):
    attempt_id: int
    challenge_id: int
    challenge_title: str
    user_id: int
    run_id: Optional[int] = None
    elapsed_seconds: Optional[float] = None
    target_seconds: float
    course_coverage: Optional[float] = None
    submitted_at: Optional[datetime] = None


class AdminChallengeItem(BaseModel):
    id: int
    title: str
    status: str
    status_reason: Optional[str] = None
    creator_id: int
    course_id: int
    attempt_count: int
    closes_at: datetime
    created_at: datetime


class AdminCourseStatus(BaseModel):
    id: int
    status: str
    suspended_challenges: int


class AdminUserStatus(BaseModel):
    user_id: int
    email: str
    suspended: bool
    suspension_reason: Optional[str] = None


class AuditEventOut(BaseModel):
    id: int
    actor_type: str
    actor_id: Optional[int] = None
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    details: dict
    created_at: datetime


class PlatformRevenueSummary(BaseModel):
    total_crystals: int
    by_source: dict
    row_count: int


# --- v2.12: Coupon redemption ---

class CouponLookupResponse(BaseModel):
    """Pre-redeem validation payload — lets a merchant scan the code and see what it is
    before committing the redemption. Same RBAC as the redeem endpoint."""
    coupon_code: str
    bounty_id: int
    bounty_title: str
    merchant_id: int
    customer_user_id: int
    coupon_text: Optional[str]
    issued_at: datetime
    redeemed_at: Optional[datetime]
    redeemed_by_merchant_id: Optional[int]
    is_redeemed: bool


class CouponRedeemResponse(BaseModel):
    coupon_code: str
    bounty_id: int
    customer_user_id: int
    redeemed_at: datetime
    message: str
