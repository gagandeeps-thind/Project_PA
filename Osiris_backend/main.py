# --- Library Imports ---
# FastAPI: The core web framework. HTTPException: Used to return errors (like 404 Not Found). Depends: Used to inject database sessions.
from fastapi import FastAPI, HTTPException, Depends
# Pydantic: Used for validating the shape of JSON data coming in and going out of our API.
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import json
import secrets
import hashlib
# SQLAlchemy: Our ORM (Object Relational Mapper). It lets us interact with the database using Python objects instead of raw SQL.
from sqlalchemy.orm import Session
# bcrypt: Used to securely scramble (hash) passwords so they aren't saved as plain text.
import bcrypt
# APScheduler: Runs background tasks automatically (like a cron job) while the server is running.
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager

# Import our newly created database connection and models
import database
import models
import spatial_utils
import ml_referee

# This line tells SQLAlchemy to look at our models and actually CREATE the tables
# in the SQLite database file if they don't exist yet.
models.Base.metadata.create_all(bind=database.engine)

# Background scheduler — runs the daily-decay cron. Defined before the app so the lifespan
# handler below can reference it. Job is wired in lifespan(), not at module import.
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler — replaces the deprecated @app.on_event("startup"/"shutdown")
    pattern. The hourly decay job (process_daily_decay) is wired up on startup and torn down
    cleanly on shutdown. process_daily_decay is defined later in the module; that's fine
    because lifespan only runs once the server starts (after full module import)."""
    scheduler.add_job(process_daily_decay, 'interval', hours=24)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()

# Initialize the FastAPI application
app = FastAPI(title="Verified Fitness Reward System API", version="1.0-MVP", lifespan=lifespan)

# A simple root endpoint to verify the server is running
@app.get("/")
async def root():
    return {
        "message": "Verified Fitness Reward System API is running",
        "docs": "/docs"
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return {}

# --- Security ---
def _now_naive_utc() -> datetime:
    """Server-side 'now' as a naive UTC datetime (tz stripped) for SQLite-compatible storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _to_naive_utc(dt: datetime) -> datetime:
    """Normalize a client-supplied datetime to naive UTC so comparisons with stored values work.
    Accepts either aware or naive datetimes; assumes naive inputs are already UTC."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

def get_password_hash(password: str) -> str:
    """Takes a plain text password and returns a securely hashed version using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Checks if a plain text password matches the hashed version stored in the database."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

# --- Pydantic Models (Data Validation) ---
# NOTE: Do not confuse Pydantic models with SQLAlchemy models!
# - SQLAlchemy models (in models.py) define the structure of the DATABASE tables.
# - Pydantic models (here) define the structure of the JSON data we receive or return via the API.

# The JSON shape we expect when a user registers
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=12, description="Password cannot exceed 72 characters")
    weight_kg: float = Field(..., gt=0, description="Weight in kg must be greater than 0")
    height_m: float = Field(..., gt=0, description="Height in meters must be greater than 0")
    preferred_path: str = "Balance"  # Options: Strength, Cardio, Balance
    device_timestamp: datetime = Field(..., description="Client device's current datetime (ISO 8601)")

# The JSON shape we expect when a user logs in
class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=12)
    device_timestamp: datetime = Field(..., description="Client device's current datetime (ISO 8601)")

# --- Unified auth (v2.8): role-aware login ---
# Frontend posts to /api/v1/auth/login; backend probes Admin → Merchant → User in that
# order and returns the matching role. The Flutter app uses `role` to decide which UI tree
# to render — game vs. merchant portal vs. admin portal.

class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=12)
    device_timestamp: datetime = Field(..., description="Client device's current datetime (ISO 8601)")

class AuthLoginResponse(BaseModel):
    role: str          # 'admin' | 'merchant' | 'player'
    id: int            # role-specific primary key
    email: EmailStr
    name: str          # display name
    message: str

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

# Summary of MediaPipe pose data extracted on-device. Sent for camera-verified exercises only.
class PoseSummary(BaseModel):
    rep_count: int = Field(..., ge=0)
    min_joint_angle_deg: Optional[float] = None
    max_joint_angle_deg: Optional[float] = None
    avg_rep_duration_ms: Optional[float] = None

# The proof envelope a client posts to vouch for an activity.
class ActivityProof(BaseModel):
    activity_type: str                                     # pushups | squats | sprint | run | walk | burpees | plank | hold
    declared_score: int = Field(..., ge=0)
    duration_seconds: float = Field(..., gt=0)
    accelerometer: List[AccelerometerSample] = Field(default_factory=list)
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
    email: EmailStr
    bmi: float
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
    password: str = Field(..., max_length=12)
    business_type: str = "general"

class MerchantResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    business_type: str

    class Config:
        from_attributes = True

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

# --- Core Business Logic ---

# --- Dependencies ---
def get_db():
    """Dependency that creates a new database session for an API request and closes it when done.
       FastAPI uses this via 'Depends(get_db)' in the endpoint parameters."""
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_avatar_class(preferred_path: str) -> str:
    """
    Maps user's chosen path to a physical class (Dynamic 2D Sprite logic)
    to avoid the BMI body-shaming flaw.
    """
    path = preferred_path.lower()
    if path == "strength":
        return "Tank"      # Vanguard/Heavy
    elif path == "cardio":
        return "Assassin"  # Striker/Fast
    else:
        return "Mage"      # Balanced/Support

def get_rank(xp: int, last_activity_date: Optional[datetime] = None) -> str:
    """Calculates Grade/Title based on Master GDD Tier System.
    NOTE: inactivity comparison uses server-side 'now' intentionally — decay is a system-owned
    concept; relying on a possibly-drifted device clock here would be exploitable."""
    if last_activity_date:
        days_inactive = (_now_naive_utc() - last_activity_date).total_seconds() / 86400
        if days_inactive > 30:
            # Harsh punishment for 30+ days of inactivity
            return "F - The Dishonored"
            
    if xp < 500: return "D - Beginner"
    if xp < 1000: return "C - Intermediate"
    if xp < 2500: return "B - Advanced"
    if xp < 5000: return "A - Saint"
    if xp < 7500: return "S - King"
    if xp < 10000: return "SS - Emperor"
    return "SSS - God"

def get_title(cumulative_area: float) -> str:
    """Calculates Map Title based on total km2 owned."""
    if cumulative_area >= 100.0: return "Sovereign"
    if cumulative_area >= 20.0: return "High Lord"
    if cumulative_area >= 5.0: return "Lord"
    if cumulative_area >= 1.0: return "Warden"
    return "Unawakened"

# --- Economy Constants (Phase 1 MVP — virtual Mana Crystals only) ---
# Real-world currency conversion is deferred to Phase 2.
CLAIM_XP_PER_SQKM = 100           # XP granted per km² on a successful domain claim
SIEGE_WIN_XP_BONUS = 500          # Flat XP bonus for winning a siege

# Payout splits on siege WIN (paid tier): pot = defender_vault + challenger_match
WAR_TAX_PCT = 0.20                # Platform's cut from a winning pot (80/20 to challenger/system)

# Payout splits on siege LOSS (paid tier): challenger's forfeited match is split
LOSS_DEFENDER_PCT = 0.50          # Goes back into defender's Vault (grows the moat)
LOSS_SYSTEM_PCT = 0.30            # Platform retains outright
LOSS_DISCOUNT_PCT = 0.20          # Banked as a retry discount for the same challenger vs. same domain

def calculate_claim_xp(area_sqkm: float) -> int:
    """XP awarded for claiming land. Floors to keep small traces from earning fractional XP."""
    return int(area_sqkm * CLAIM_XP_PER_SQKM)

# --- Epic 6: Party Attribute Stats ---
# Maps a verified activity's defense_type to the User column it feeds.
DEFENSE_TYPE_TO_STAT = {
    "pushups": "str_stat",
    "squats": "str_stat",
    "sprint": "agi_stat",
    "burpees": "agi_stat",
    "run": "end_stat",
    "walk": "end_stat",
    "plank": "con_stat",
    "hold": "con_stat",
}

def increment_stat_from_activity(user: models.User, defense_type: str, score: int) -> Optional[str]:
    """Adds `score` to the matching attribute column on `user` based on activity type.
    Returns the stat column name touched, or None if the activity type isn't mapped."""
    if score <= 0:
        return None
    stat_col = DEFENSE_TYPE_TO_STAT.get((defense_type or "").lower())
    if stat_col is None:
        return None
    setattr(user, stat_col, (getattr(user, stat_col) or 0) + score)
    return stat_col

def record_activity(
    db: Session,
    user: models.User,
    activity_type: str,
    score: int,
    occurred_at: datetime,
    source: str,
    related_id: Optional[int] = None,
    verified: bool = False,
    confidence: float = 1.0,
) -> Optional[models.ActivityLog]:
    """Single entry point for the activity history table. Increments the lifetime stat AND
    appends an `ActivityLog` row so the 30-day rolling window can be reconstructed.
    Returns the new log row (uncommitted) or None when score is non-positive."""
    if score <= 0:
        return None
    stat_col = increment_stat_from_activity(user, activity_type, score)
    log = models.ActivityLog(
        user_id=user.id,
        activity_type=(activity_type or "").lower(),
        score=score,
        stat_column=stat_col,
        confidence=confidence,
        verified=1 if verified else 0,
        source=source,
        related_id=related_id,
        occurred_at=occurred_at,
    )
    db.add(log)
    return log

def get_party_role(user: models.User) -> tuple[str, str]:
    """Returns (role, leading_stat_name) based on the user's highest attribute.
    Ties broken by the order STR > AGI > END > CON (favors melee on equal stats)."""
    stats = [
        ("str_stat", user.str_stat or 0, "Vanguard"),
        ("agi_stat", user.agi_stat or 0, "Striker"),
        ("end_stat", user.end_stat or 0, "Scout"),
        ("con_stat", user.con_stat or 0, "Strategist"),
    ]
    leading = max(stats, key=lambda s: s[1])
    return leading[2], leading[0]

# --- Endpoints ---

@app.post("/api/v1/onboard", response_model=UserProfile)
async def onboard_user(user: UserCreate, db: Session = Depends(get_db)):
    """API Endpoint to register a new user, calculate their stats, and assign an avatar."""
    
    # 0. Check if user already exists
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # 1. Calculate BMI (Weight / Height^2) 
    # (Pydantic 'gt=0' prevents division by zero, but adding a fallback safety check is good practice)
    if user.height_m <= 0:
        raise HTTPException(status_code=400, detail="Height must be greater than zero.")
    bmi = round(user.weight_kg / (user.height_m ** 2), 2)
    
    # 2. Determine Avatar Class based on Path, not BMI
    avatar_class = get_avatar_class(user.preferred_path)
    
    # 3. Create the Database "Warehouse Worker" Model
    # Securely hash the user's password using bcrypt
    hashed_pwd = get_password_hash(user.password)
    
    device_ts = _to_naive_utc(user.device_timestamp)
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        bmi=bmi,
        avatar_class=avatar_class,
        xp=0,
        rank=get_rank(0),
        title=get_title(0.0),
        cumulative_area=0.0,
        last_activity_date=device_ts,
        streak=0
    )
    
    # 4. Save to Database and commit the transaction
    db.add(new_user)
    db.commit()
    db.refresh(new_user) # Retrieves the newly generated 'id' from the database
    
    # 5. Return the saved data
    # (FastAPI automatically converts the SQLAlchemy model into the Pydantic UserProfile JSON)
    return new_user

@app.post("/api/v1/login", response_model=UserProfile)
async def login_user(credentials: UserLogin, db: Session = Depends(get_db)):
    """Player-only login. Kept for backward compatibility; new clients should use the
    role-aware `/api/v1/auth/login` endpoint and switch UI based on the returned `role`."""
    user = db.query(models.User).filter(models.User.email == credentials.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify the password using bcrypt
    if not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    # Security check passed! Update their activity timestamp so they don't get hit by rank decay
    user.last_activity_date = _to_naive_utc(credentials.device_timestamp)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/v1/auth/login", response_model=AuthLoginResponse)
async def auth_login(credentials: AuthLoginRequest, db: Session = Depends(get_db)):
    """Role-aware login. Probes Admin → Merchant → User in that order; the first table that
    contains the email **and** matches the password wins. Returns `{role, id, email, name}`
    so the Flutter app can route into admin / merchant / game UI accordingly.

    Probe order matters: admins are most privileged, so they're checked first to ensure
    that if Gagan accidentally creates a player account with the same email as the admin
    account (very unlikely), admin still wins."""
    device_ts = _to_naive_utc(credentials.device_timestamp)

    # 1. Admin probe (no public registration; rows are seeded via scripts/seed_admin.py).
    admin = db.query(models.Admin).filter(models.Admin.email == credentials.email).first()
    if admin and verify_password(credentials.password, admin.hashed_password):
        admin.last_login_at = device_ts
        db.commit()
        return AuthLoginResponse(
            role="admin",
            id=admin.id,
            email=admin.email,
            name=admin.name or admin.email,
            message="Admin authenticated. Open admin portal.",
        )

    # 2. Merchant probe (registered via /api/v1/merchants/register).
    merchant = db.query(models.Merchant).filter(models.Merchant.email == credentials.email).first()
    if merchant and verify_password(credentials.password, merchant.hashed_password):
        return AuthLoginResponse(
            role="merchant",
            id=merchant.id,
            email=merchant.email,
            name=merchant.name or merchant.email,
            message="Merchant authenticated. Open merchant portal.",
        )

    # 3. Player probe (registered via /api/v1/onboard).
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if user and verify_password(credentials.password, user.hashed_password):
        user.last_activity_date = device_ts
        db.commit()
        return AuthLoginResponse(
            role="player",
            id=user.id,
            email=user.email,
            name=user.email,  # Users don't have a separate display name yet
            message="Player authenticated. Open game.",
        )

    # No match in any table — return 401 with a generic message so callers can't enumerate.
    raise HTTPException(status_code=401, detail="Invalid email or password")

@app.get("/api/v1/users/{user_id}", response_model=UserProfile)
async def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    """Fetches the latest stats, Rank, and XP for the app dashboard."""
    # Query the database for a user matching the ID passed in the URL path
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/api/v1/domains", response_model=DomainResponse)
async def submit_domain(domain_req: DomainCreate, db: Session = Depends(get_db)):
    """Processes a completed Domain Trace, validates anti-cheat, and claims the territory."""
    
    # 0. Verify the user exists
    user = db.query(models.User).filter(models.User.id == domain_req.owner_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # 0.5. ML Referee: if a proof is attached, validate it and override defense_score with the
    # verified value. Without a proof we fall back to client-trusted defense_score (legacy).
    verification = _enforce_proof(domain_req.defense_proof, expected_activity_type=domain_req.defense_type)
    if verification is not None:
        domain_req.defense_score = verification.verified_score
    # 0.6. Replay-attack guard: every proof can be consumed exactly once across the system.
    _consume_proof_or_409(db, user.id, domain_req.defense_proof, source="domain_claim")

    # 1. Anti-Cheat: Validate Closure Tolerance
    # The user must return to their starting point to close the polygon (within 20 meters)
    start_coord = domain_req.coordinates[0]
    end_coord = domain_req.coordinates[-1]
    closure_dist = spatial_utils.haversine_distance(
        start_coord.lat, start_coord.lng, end_coord.lat, end_coord.lng
    )
    if closure_dist > 0.02: # 0.02 km = 20 meters
        raise HTTPException(status_code=400, detail="Domain Closure Failed: Loop not closed within 20m.")

    # 2. Anti-Cheat: Velocity Lock
    # Ensure the user didn't jump in a car to draw a massive shape
    if spatial_utils.check_velocity_violation(domain_req.coordinates, max_speed_kmh=25.0):
        raise HTTPException(status_code=400, detail="Velocity Lock triggered. Trace Shattered.")

    # 3. Calculate the Area in square kilometers
    area = spatial_utils.calculate_polygon_area_sqkm(domain_req.coordinates)
    if area < 0.001:
        raise HTTPException(status_code=400, detail="Domain too small.")

    # 4. Save Domain to the Database
    geom_json = json.dumps([{"lat": c.lat, "lng": c.lng} for c in domain_req.coordinates])
    
    new_domain = models.Domain(
        owner_id=user.id,
        geometry_json=geom_json,
        area_sqkm=round(area, 4),
        defense_score=domain_req.defense_score,
        defense_type=domain_req.defense_type
    )
    
    # 4.5 Siege Logic: Check if this new domain swallows any existing domains
    all_domains = db.query(models.Domain).filter(models.Domain.owner_id != user.id).all()
    sieges_created = 0
    for existing_domain in all_domains:
        if existing_domain.geometry_json:
            try:
                target_coords = json.loads(existing_domain.geometry_json)
                if spatial_utils.is_polygon_swallowed(target_coords, domain_req.coordinates):
                    # Trigger a Siege! Snapshot the defender's score so it can't be edited before resolution.
                    new_siege = models.SiegeLog(
                        challenger_id=user.id,
                        target_domain_id=existing_domain.id,
                        status="pending_feat",
                        defender_score_snapshot=existing_domain.defense_score or 0
                    )
                    db.add(new_siege)
                    sieges_created += 1
            except Exception:
                pass # Skip if JSON parsing fails

    # 5. Add the land to the user's cumulative total and upgrade their Title if necessary
    user.cumulative_area += round(area, 4)
    user.title = get_title(user.cumulative_area)

    # 6. Award claim XP, increment the matching Party Stat, and re-evaluate Rank
    xp_gained = calculate_claim_xp(area)
    user.xp += xp_gained
    user.last_activity_date = _to_naive_utc(domain_req.device_timestamp)
    user.rank = get_rank(user.xp, user.last_activity_date)

    # 7. Append to ActivityLog so the 30-day rolling Party Stats window can include this rep.
    db.add(new_domain)
    db.flush()  # need new_domain.id for the activity log's related_id
    record_activity(
        db,
        user,
        activity_type=domain_req.defense_type,
        score=domain_req.defense_score,
        occurred_at=_to_naive_utc(domain_req.device_timestamp),
        source="domain_claim",
        related_id=new_domain.id,
        verified=bool(verification and verification.verified),
        confidence=verification.confidence if verification else 1.0,
    )

    db.commit()
    db.refresh(new_domain)

    return DomainResponse(
        id=new_domain.id,
        area_sqkm=new_domain.area_sqkm,
        defense_score=new_domain.defense_score,
        message=f"Domain secured! You claimed {round(area, 4)} km² and are now a {user.title}.",
        sieges_triggered=sieges_created,
        xp_awarded=xp_gained
    )

@app.post("/api/v1/domains/{domain_id}/vault", response_model=VaultLockResponse)
async def lock_vault(domain_id: int, req: VaultLockRequest, db: Session = Depends(get_db)):
    """Lock (or top up) an Ownership Fee on a domain. Crystals are deducted from the owner's
    wallet and added to the domain's Vault. Vault balance doubles as the required Challenger
    Match amount. Topping up is allowed; unlocking (lowering) is deferred to Phase 2."""

    domain = db.query(models.Domain).filter(models.Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found.")

    # Only the owner can protect their domain
    if domain.owner_id != req.user_id:
        raise HTTPException(status_code=403, detail="Only the owner can lock this domain's Vault.")

    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Target vault balance must be a top-up, not a withdrawal
    delta = req.amount - (domain.vault_balance or 0)
    if delta <= 0:
        raise HTTPException(status_code=400, detail="New vault amount must exceed current vault balance.")

    if user.mana_crystals < delta:
        raise HTTPException(status_code=402, detail="Insufficient Mana Crystals.")

    user.mana_crystals -= delta
    domain.vault_balance = req.amount
    db.commit()
    db.refresh(domain)
    db.refresh(user)

    return VaultLockResponse(
        domain_id=domain.id,
        vault_balance=domain.vault_balance,
        crystals_spent=delta,
        mana_crystals_remaining=user.mana_crystals,
        message=f"Domain protected. {delta} crystals locked into the Vault."
    )


@app.post("/api/v1/sieges/{siege_id}/resolve", response_model=SiegeResolveResponse)
async def resolve_siege(siege_id: int, req: SiegeResolveRequest, db: Session = Depends(get_db)):
    """Resolve a pending siege. Challenger submits their Defense Feat score.
    WIN: defender's polygon erased, pot (defender vault + challenger match) paid 80/20 to
         challenger/system.
    LOSS: challenger's match is split 50% to defender vault / 30% to system / 20% banked as a
          retry-discount against the same target_domain_id for this challenger.
    Any unconsumed retry discount for this challenger+domain pair is auto-applied to reduce
    the challenger's out-of-pocket match on this attempt."""

    siege = db.query(models.SiegeLog).filter(models.SiegeLog.id == siege_id).first()
    if not siege:
        raise HTTPException(status_code=404, detail="Siege not found.")
    if siege.status != "pending_feat":
        raise HTTPException(status_code=400, detail=f"Siege already resolved (status={siege.status}).")

    challenger = db.query(models.User).filter(models.User.id == siege.challenger_id).first()
    target_domain = db.query(models.Domain).filter(models.Domain.id == siege.target_domain_id).first()
    if not challenger or not target_domain:
        raise HTTPException(status_code=404, detail="Challenger or target domain missing.")

    defender = db.query(models.User).filter(models.User.id == target_domain.owner_id).first()
    device_ts = _to_naive_utc(req.device_timestamp)

    # Capture defense_type BEFORE any potential db.delete(target_domain) on win path.
    target_defense_type = target_domain.defense_type or "pushups"

    # ML Referee: if the challenger attached a proof, it must match the defender's exercise
    # and pass verification. Verified score overrides the client-supplied challenger_score.
    verification = _enforce_proof(req.challenger_proof, expected_activity_type=target_defense_type)
    if verification is not None:
        req.challenger_score = verification.verified_score
    # Replay-attack guard
    _consume_proof_or_409(db, challenger.id, req.challenger_proof, source="siege_resolve")

    required_match = target_domain.vault_balance or 0

    # Look up any available retry discount from a previous failed attempt at THIS domain.
    discount_row = (
        db.query(models.SiegeDiscount)
        .filter(
            models.SiegeDiscount.challenger_id == challenger.id,
            models.SiegeDiscount.target_domain_id == target_domain.id,
            models.SiegeDiscount.consumed == 0,
        )
        .first()
    )
    discount_applied = 0
    if discount_row and required_match > 0:
        discount_applied = min(discount_row.amount or 0, required_match)

    out_of_pocket = max(0, required_match - discount_applied)

    # Paid tier: challenger must cover the out-of-pocket portion of the match.
    if out_of_pocket > 0 and challenger.mana_crystals < out_of_pocket:
        raise HTTPException(status_code=402, detail="Insufficient Mana Crystals to match defender's Vault.")

    # Consume the discount up front — whether they win or lose, it's been applied.
    if discount_row and discount_applied > 0:
        discount_row.consumed = 1
        discount_row.consumed_at = device_ts

    defender_score = siege.defender_score_snapshot or 0
    challenger_won = req.challenger_score > defender_score

    crystals_awarded = 0
    new_discount_banked = 0
    xp_gained = 0

    if challenger_won:
        # Debit only the out-of-pocket; the discount portion was subsidized by the system.
        if required_match > 0:
            challenger.mana_crystals -= out_of_pocket
            pot = required_match * 2  # treat as full match vs defender vault
            winner_share = int(pot * (1 - WAR_TAX_PCT))  # 80%
            war_tax_revenue = pot - winner_share          # 20% to platform
            challenger.mana_crystals += winner_share
            crystals_awarded = winner_share
            target_domain.vault_balance = 0
            # Ledger: record platform's War Tax cut.
            if war_tax_revenue > 0:
                db.add(models.PlatformRevenue(
                    source="siege_war_tax",
                    amount=war_tax_revenue,
                    user_id=challenger.id,
                    related_siege_id=siege.id,
                    note=f"20% of pot {pot} on siege win",
                ))

        # Transfer land: defender loses area; challenger's cumulative_area was bumped on claim.
        if defender:
            defender.cumulative_area = max(0.0, defender.cumulative_area - (target_domain.area_sqkm or 0.0))
            defender.title = get_title(defender.cumulative_area)

        # Remove defender's polygon entirely.
        db.delete(target_domain)

        # Reward challenger XP + rank bump.
        xp_gained = SIEGE_WIN_XP_BONUS
        challenger.xp += xp_gained
        challenger.last_activity_date = device_ts
        challenger.rank = get_rank(challenger.xp, challenger.last_activity_date)

        siege.status = "won"
        msg_parts = ["Siege won. Claimed defender's territory"]
        if required_match > 0:
            msg_parts.append(f" and {crystals_awarded} crystals")
        if discount_applied > 0:
            msg_parts.append(f" (retry discount of {discount_applied} applied)")
        message = "".join(msg_parts) + "."
    else:
        # LOSS: challenger forfeits their match, split 50/30/20.
        if required_match > 0:
            challenger.mana_crystals -= out_of_pocket
            defender_cut = int(required_match * LOSS_DEFENDER_PCT)
            system_keep = int(required_match * LOSS_SYSTEM_PCT)         # 30% — platform revenue
            future_discount_cut = int(required_match * LOSS_DISCOUNT_PCT)

            if defender_cut > 0:
                target_domain.vault_balance += defender_cut  # defender's moat grows
            if future_discount_cut > 0:
                new_discount = models.SiegeDiscount(
                    challenger_id=challenger.id,
                    target_domain_id=target_domain.id,
                    amount=future_discount_cut,
                    consumed=0,
                )
                db.add(new_discount)
                new_discount_banked = future_discount_cut
            # Ledger: record platform's loss-side keep.
            if system_keep > 0:
                db.add(models.PlatformRevenue(
                    source="siege_loss_keep",
                    amount=system_keep,
                    user_id=challenger.id,
                    related_siege_id=siege.id,
                    note=f"30% of forfeit {required_match} on siege loss",
                ))
        siege.status = "failed"
        message = "Defense held. Your Defense Feat did not beat the defender's Ghost score."
        if new_discount_banked > 0:
            message += f" {new_discount_banked} crystals banked as a retry discount."

    # Stat increment + ActivityLog: runs regardless of outcome — the challenger performed
    # the activity. related_id points at the siege itself for traceability.
    record_activity(
        db,
        challenger,
        activity_type=target_defense_type,
        score=req.challenger_score,
        occurred_at=device_ts,
        source="siege_resolve",
        related_id=siege.id,
        verified=bool(verification and verification.verified),
        confidence=verification.confidence if verification else 1.0,
    )

    siege.challenger_fee = out_of_pocket
    siege.challenger_score = req.challenger_score
    siege.resolved_at = device_ts

    db.commit()

    return SiegeResolveResponse(
        siege_id=siege.id,
        status=siege.status,
        defender_score=defender_score,
        challenger_score=req.challenger_score,
        crystals_awarded=crystals_awarded,
        xp_awarded=xp_gained,
        discount_applied=discount_applied,
        new_discount_banked=new_discount_banked,
        message=message
    )


@app.get("/api/v1/users/{user_id}/party-role", response_model=PartyRoleResponse)
async def get_user_party_role(
    user_id: int,
    window_days: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Returns the user's Party Role. Two modes:
       - default (no `window_days`)  → lifetime totals on `User.{str/agi/end/con}_stat`
       - `?window_days=N`            → rolling sum of `ActivityLog.score` per stat over the
                                       last N days, computed from `occurred_at`.

    Phase 1 wrote stats only as lifetime totals; v2.7 adds the ActivityLog-backed rolling
    path so the 30-day Party Role can flip even if a user's career totals stay unchanged."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if window_days is None or window_days <= 0:
        role, leading_stat = get_party_role(user)
        return PartyRoleResponse(
            user_id=user.id,
            role=role,
            str_stat=user.str_stat or 0,
            agi_stat=user.agi_stat or 0,
            end_stat=user.end_stat or 0,
            con_stat=user.con_stat or 0,
            leading_stat=leading_stat,
        )

    # Rolling-window path: aggregate ActivityLog rows for this user since (now - window_days).
    cutoff = _now_naive_utc() - timedelta(days=window_days)
    rows = (
        db.query(models.ActivityLog)
        .filter(
            models.ActivityLog.user_id == user.id,
            models.ActivityLog.occurred_at >= cutoff,
            models.ActivityLog.stat_column.isnot(None),
        )
        .all()
    )
    totals = {"str_stat": 0, "agi_stat": 0, "end_stat": 0, "con_stat": 0}
    for r in rows:
        if r.stat_column in totals:
            totals[r.stat_column] += r.score or 0

    # Reuse get_party_role's tie-break order by mocking a temp object with the windowed totals.
    class _Tmp:
        pass
    tmp = _Tmp()
    for k, v in totals.items():
        setattr(tmp, k, v)
    role, leading_stat = get_party_role(tmp)  # type: ignore[arg-type]
    return PartyRoleResponse(
        user_id=user.id,
        role=role,
        str_stat=totals["str_stat"],
        agi_stat=totals["agi_stat"],
        end_stat=totals["end_stat"],
        con_stat=totals["con_stat"],
        leading_stat=leading_stat,
    )


# --- Epic 2: ML Referee helpers + endpoint ---

def _run_verification(proof: ActivityProof) -> VerificationResult:
    """Bridge between the Pydantic proof shape and the pure-Python ml_referee module."""
    outcome = ml_referee.verify_activity(
        activity_type=proof.activity_type,
        declared_score=proof.declared_score,
        duration_seconds=proof.duration_seconds,
        accelerometer_samples=proof.accelerometer,
        pose_summary=proof.pose,
    )
    return VerificationResult(
        verified=outcome.verified,
        confidence=outcome.confidence,
        verified_score=outcome.verified_score,
        activity_type=outcome.activity_type,
        flags=outcome.flags,
    )


def _proof_dedup_key(user_id: int, proof: ActivityProof) -> str:
    """Deterministic SHA-256 hash over the bits of an ActivityProof that uniquely identify a
    workout. Re-submitting the same proof produces the same key. Used by the replay-attack
    guard. Pose data is excluded from the hash so a re-extract with slightly different
    angles still collides — the accelerometer trace is the high-entropy fingerprint."""
    sample_repr = ";".join(
        f"{s.t_ms}:{s.ax:.3f}:{s.ay:.3f}:{s.az:.3f}" for s in proof.accelerometer
    )
    raw = (
        f"{user_id}|{proof.device_timestamp.isoformat()}|"
        f"{proof.activity_type.lower()}|{proof.declared_score}|"
        f"{proof.duration_seconds:.3f}|{sample_repr}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _consume_proof_or_409(db: Session, user_id: int, proof: Optional[ActivityProof], source: str) -> None:
    """Idempotency guard. Call AFTER `_enforce_proof` succeeds — if the same proof was already
    consumed by any prior action endpoint, raises 409 Conflict so the client can treat the
    earlier success as authoritative. No-ops when proof is None (legacy trust path)."""
    if proof is None:
        return
    key = _proof_dedup_key(user_id, proof)
    existing = db.query(models.ProofConsumed).filter(models.ProofConsumed.proof_key == key).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"This proof has already been consumed by '{existing.source}' at {existing.consumed_at.isoformat()}",
        )
    db.add(models.ProofConsumed(proof_key=key, user_id=user_id, source=source))


def _enforce_proof(proof: Optional[ActivityProof], expected_activity_type: Optional[str] = None) -> Optional[VerificationResult]:
    """If a proof is attached to an action request, run it through the referee. Returns the
    full VerificationResult (callers read verified_score + confidence) or raises 400 on
    rejection. Returns None when no proof was supplied (legacy trust path)."""
    if proof is None:
        return None
    if expected_activity_type and proof.activity_type.lower() != expected_activity_type.lower():
        raise HTTPException(
            status_code=400,
            detail=f"Proof activity_type '{proof.activity_type}' does not match expected '{expected_activity_type}'",
        )
    result = _run_verification(proof)
    if not result.verified:
        raise HTTPException(
            status_code=400,
            detail=f"ML Referee rejected proof (confidence {result.confidence:.2f}): {'; '.join(result.flags) or 'no flags'}",
        )
    return result


@app.post("/api/v1/activities/verify", response_model=VerificationResult)
async def verify_activity_endpoint(proof: ActivityProof):
    """Stateless preview of the ML Referee. The frontend can call this to confirm a workout
    will pass before submitting the real action (claim, siege, bounty). No DB writes."""
    return _run_verification(proof)


# --- Hardening Sprint: PlatformRevenue read-only audit ---

class PlatformRevenueSummary(BaseModel):
    total_crystals: int
    by_source: dict
    row_count: int


@app.get("/api/v1/platform/revenue", response_model=PlatformRevenueSummary)
async def get_platform_revenue(db: Session = Depends(get_db)):
    """Aggregates the PlatformRevenue ledger so admins can audit total platform earnings and
    the breakdown by source. Read-only; safe to expose internally during MVP. Production will
    gate this behind an admin role."""
    rows = db.query(models.PlatformRevenue).all()
    total = sum(r.amount or 0 for r in rows)
    by_source: dict = {}
    for r in rows:
        by_source[r.source] = by_source.get(r.source, 0) + (r.amount or 0)
    return PlatformRevenueSummary(total_crystals=total, by_source=by_source, row_count=len(rows))


# --- Epic 1: Bounty Board Endpoints ---

@app.post("/api/v1/merchants/register", response_model=MerchantResponse)
async def register_merchant(merchant: MerchantCreate, db: Session = Depends(get_db)):
    """Registers a B2B partner who can sponsor merchant_chest bounties at their storefront.
    For MVP this is unauthenticated; production will gate it behind a Merchant Portal admin login."""
    if db.query(models.Merchant).filter(models.Merchant.email == merchant.email).first():
        raise HTTPException(status_code=400, detail="Merchant email already registered")
    new = models.Merchant(
        name=merchant.name,
        email=merchant.email,
        hashed_password=get_password_hash(merchant.password),
        business_type=merchant.business_type,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return new


@app.post("/api/v1/bounties", response_model=BountySummary)
async def create_bounty(bounty: BountyCreate, db: Session = Depends(get_db)):
    """Seed a bounty. Used by admins for daily quests and by merchants for storefront chests.
    Geofence radius is in metres; distance to caller is filled with 0 since the creator may not
    be on-site."""
    if bounty.bounty_type == "merchant_chest" and bounty.merchant_id is None:
        raise HTTPException(status_code=400, detail="merchant_chest requires merchant_id")
    if bounty.merchant_id is not None:
        if not db.query(models.Merchant).filter(models.Merchant.id == bounty.merchant_id).first():
            raise HTTPException(status_code=404, detail="Merchant not found")

    new = models.Bounty(
        title=bounty.title,
        description=bounty.description,
        bounty_type=bounty.bounty_type,
        merchant_id=bounty.merchant_id,
        target_lat=bounty.target_lat,
        target_lng=bounty.target_lng,
        radius_m=bounty.radius_m,
        activity_type=bounty.activity_type,
        target_score=bounty.target_score,
        xp_reward=bounty.xp_reward,
        crystal_reward=bounty.crystal_reward,
        coupon_text=bounty.coupon_text,
        max_completions=bounty.max_completions,
        expires_at=_to_naive_utc(bounty.expires_at) if bounty.expires_at else None,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return BountySummary(
        id=new.id,
        title=new.title,
        description=new.description,
        bounty_type=new.bounty_type,
        target_lat=new.target_lat,
        target_lng=new.target_lng,
        radius_m=new.radius_m,
        activity_type=new.activity_type,
        target_score=new.target_score,
        xp_reward=new.xp_reward,
        crystal_reward=new.crystal_reward,
        has_coupon=bool(new.coupon_text),
        completions_remaining=new.max_completions,
        distance_km=0.0,
    )


@app.get("/api/v1/bounties/nearby", response_model=List[BountySummary])
async def get_nearby_bounties(lat: float, lng: float, radius_km: float = 5.0, db: Session = Depends(get_db)):
    """Returns active, non-expired, non-full bounties within `radius_km` of (lat, lng), sorted
    nearest-first. MVP uses an in-memory haversine sweep; PostGIS will replace this with
    `ST_DWithin` in Phase 2."""
    now = _now_naive_utc()
    candidates = (
        db.query(models.Bounty)
        .filter(models.Bounty.is_active == 1)
        .filter(models.Bounty.completions_count < models.Bounty.max_completions)
        .all()
    )

    nearby: List[BountySummary] = []
    for b in candidates:
        if b.expires_at is not None and b.expires_at <= now:
            continue
        dist = spatial_utils.haversine_distance(lat, lng, b.target_lat, b.target_lng)
        if dist > radius_km:
            continue
        nearby.append(BountySummary(
            id=b.id,
            title=b.title,
            description=b.description,
            bounty_type=b.bounty_type,
            target_lat=b.target_lat,
            target_lng=b.target_lng,
            radius_m=b.radius_m,
            activity_type=b.activity_type,
            target_score=b.target_score,
            xp_reward=b.xp_reward,
            crystal_reward=b.crystal_reward,
            has_coupon=bool(b.coupon_text),
            completions_remaining=max(0, b.max_completions - b.completions_count),
            distance_km=round(dist, 4),
        ))

    nearby.sort(key=lambda x: x.distance_km)
    return nearby


@app.post("/api/v1/bounties/{bounty_id}/complete", response_model=BountyCompleteResponse)
async def complete_bounty(bounty_id: int, req: BountyCompleteRequest, db: Session = Depends(get_db)):
    """Validates proximity + score, awards XP/crystals, increments the matching attribute stat,
    and (for merchant chests) issues a single-use coupon code. One claim per user per bounty."""
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")
    if not bounty.is_active:
        raise HTTPException(status_code=400, detail="Bounty is no longer active")
    if bounty.completions_count >= bounty.max_completions:
        raise HTTPException(status_code=400, detail="Bounty has reached its max completions")

    now = _now_naive_utc()
    if bounty.expires_at is not None and bounty.expires_at <= now:
        raise HTTPException(status_code=400, detail="Bounty has expired")

    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Single-claim-per-user enforcement
    if (
        db.query(models.BountyCompletion)
        .filter(
            models.BountyCompletion.bounty_id == bounty.id,
            models.BountyCompletion.user_id == user.id,
        )
        .first()
    ):
        raise HTTPException(status_code=400, detail="You have already claimed this bounty")

    # Proximity check — convert geofence radius from metres to km to match haversine units.
    dist_km = spatial_utils.haversine_distance(req.user_lat, req.user_lng, bounty.target_lat, bounty.target_lng)
    if dist_km * 1000.0 > (bounty.radius_m or 0):
        raise HTTPException(status_code=400, detail="You are outside the bounty's geofence")

    # ML Referee: if a proof is attached, the activity type must match the bounty's, and the
    # verified score replaces the client-supplied score before the gate check below.
    verification = _enforce_proof(req.score_proof, expected_activity_type=bounty.activity_type)
    if verification is not None:
        req.score = verification.verified_score
    # Replay-attack guard
    _consume_proof_or_409(db, user.id, req.score_proof, source="bounty_complete")

    # Score gate — bounties with target_score=0 are proximity-only (e.g., merchant chests).
    if bounty.target_score > 0 and req.score < bounty.target_score:
        raise HTTPException(status_code=400, detail=f"Score {req.score} did not meet target {bounty.target_score}")

    # Award rewards
    device_ts = _to_naive_utc(req.device_timestamp)
    user.xp += bounty.xp_reward
    user.mana_crystals += bounty.crystal_reward
    user.last_activity_date = device_ts
    user.rank = get_rank(user.xp, user.last_activity_date)
    activity_score = req.score or bounty.target_score
    log_row = record_activity(
        db,
        user,
        activity_type=bounty.activity_type,
        score=activity_score,
        occurred_at=device_ts,
        source="bounty_complete",
        related_id=bounty.id,
        verified=bool(verification and verification.verified),
        confidence=verification.confidence if verification else 1.0,
    )
    stat_touched = log_row.stat_column if log_row else None

    # Coupon issuance for merchant chests
    coupon_code = None
    if bounty.coupon_text:
        coupon_code = secrets.token_urlsafe(8).upper()

    completion = models.BountyCompletion(
        bounty_id=bounty.id,
        user_id=user.id,
        score_submitted=req.score,
        xp_awarded=bounty.xp_reward,
        crystals_awarded=bounty.crystal_reward,
        coupon_code_issued=coupon_code,
        completed_at=device_ts,
    )
    bounty.completions_count += 1

    db.add(completion)
    db.commit()

    return BountyCompleteResponse(
        bounty_id=bounty.id,
        completed=True,
        xp_awarded=bounty.xp_reward,
        crystals_awarded=bounty.crystal_reward,
        stat_incremented=stat_touched,
        coupon_code=coupon_code,
        coupon_text=bounty.coupon_text,
        new_rank=user.rank,
        message=f"Bounty cleared. +{bounty.xp_reward} XP" + (f", +{bounty.crystal_reward} crystals" if bounty.crystal_reward else "") + (f", coupon {coupon_code}" if coupon_code else "") + ".",
    )


# --- Background Tasks (Cron Logic) ---

def process_daily_decay():
    """Background task triggered daily. Deducts XP and ends streaks if last activity is > 24 hours."""
    # We have to open a manual database session here because this runs outside of normal HTTP requests
    db = database.SessionLocal()
    try:
        users = db.query(models.User).all()
        for user in users:
            now = _now_naive_utc()
            hours_since_activity = (now - user.last_activity_date).total_seconds() / 3600
            
            # If they haven't logged in/completed an activity in over a day
            if hours_since_activity > 24:
                user.streak = 0
                # Deduct 5% of XP daily as a penalty
                penalty = int(user.xp * 0.05)
                user.xp = max(0, user.xp - penalty)
                
            # Re-evaluate rank in case their XP dropped below a tier threshold, or they hit 30-day inactivity
            user.rank = get_rank(user.xp, user.last_activity_date)
        # Save all changes to the database
        db.commit()
    finally:
        db.close()

# Scheduler + lifespan handler are now defined near the top of the module so FastAPI() can
# accept lifespan= at construction time. See the @asynccontextmanager above.
