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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt.exceptions import InvalidTokenError

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "dummy-secret-key-for-mvp-phase"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        role: str = payload.get("role")
        user_id_str: str = payload.get("sub")
        if role is None or user_id_str is None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        return {"id": int(user_id_str), "role": role}
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

def get_current_player(token_data: dict = Depends(get_current_user_token)):
    if token_data["role"] != "player":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return token_data

def get_current_admin(token_data: dict = Depends(get_current_user_token)):
    if token_data["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return token_data

def get_current_merchant(token_data: dict = Depends(get_current_user_token)):
    if token_data["role"] != "merchant":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return token_data

def get_current_admin_or_merchant(token_data: dict = Depends(get_current_user_token)):
    if token_data["role"] not in ["admin", "merchant"]:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return token_data


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
    """Returned when a merchant initiates payment. In Phase 2 with a real provider this would
    include a client_secret for Stripe Elements; in MVP it's a stub UUID."""
    merchant_id: int
    pilot_fee_cents: int
    provider_payment_id: str
    payment_status: str
    next_action: str

class PaymentWebhookRequest(BaseModel):
    """Payload from the payment provider when a payment terminal-state is reached.
    Production will additionally verify a signature header against the provider's public key
    before trusting the body — for MVP we accept any well-formed JSON."""
    merchant_id: int
    payment_status: str       # 'payment_successful' | 'payment_pending' | 'payment_declined'
    provider_payment_id: str
    amount_cents: int
    occurred_at: datetime

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
    try:
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
                access_token=create_access_token({"sub": str(admin.id), "role": "admin"})
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
                access_token=create_access_token({"sub": str(merchant.id), "role": "merchant"})
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
                access_token=create_access_token({"sub": str(user.id), "role": "player"})
            )

        # No match in any table — return 401 with a generic message so callers can't enumerate.
        raise HTTPException(status_code=401, detail="Invalid email or password")
    except Exception as e:
        import traceback
        # Return 500 but log exception
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}\n{traceback.format_exc()}")

@app.get("/api/v1/users/{user_id}", response_model=UserProfile)
async def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    """Fetches the latest stats, Rank, and XP for the app dashboard."""
    # Query the database for a user matching the ID passed in the URL path
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/api/v1/domains", response_model=DomainResponse)
async def submit_domain(domain_req: DomainCreate, db: Session = Depends(get_db), token_data: dict = Depends(get_current_player)):
    """Processes a completed Domain Trace, validates anti-cheat, and claims the territory."""
    
    if token_data["id"] != domain_req.owner_id:
        raise HTTPException(status_code=403, detail="Not authorized to act as this user")

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
async def lock_vault(domain_id: int, req: VaultLockRequest, db: Session = Depends(get_db), token_data: dict = Depends(get_current_player)):
    """Lock (or top up) an Ownership Fee on a domain. Crystals are deducted from the owner's
    wallet and added to the domain's Vault. Vault balance doubles as the required Challenger
    Match amount. Topping up is allowed; unlocking (lowering) is deferred to Phase 2."""
    
    if token_data["id"] != req.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to act as this user")

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
async def resolve_siege(siege_id: int, req: SiegeResolveRequest, db: Session = Depends(get_db), token_data: dict = Depends(get_current_player)):
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

    if token_data["id"] != siege.challenger_id:
        raise HTTPException(status_code=403, detail="Not authorized to resolve this siege")

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
    token_data: dict = Depends(get_current_player),
):
    if token_data["id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this user's role")
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
async def get_platform_revenue(db: Session = Depends(get_db), token_data: dict = Depends(get_current_admin)):
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
    Newly-registered merchants start `is_active=False` / `payment_status='payment_pending'`;
    they must complete the pilot-fee flow (or be activated by an admin) before they can
    create merchant_chest bounties."""
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


# --- v2.9: Merchant payment + activation endpoints ---

@app.get("/api/v1/merchants/{merchant_id}", response_model=MerchantProfile)
async def get_merchant_profile(
    merchant_id: int,
    token_data: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db),
):
    """Fetch a merchant's full profile (incl. activation + payment status). Accessible to
    the merchant themselves (same-id check) and to any admin. Used post-login by the
    Flutter app to refresh state and decide whether to show the 'pay your pilot fee' UI."""
    role = token_data["role"]
    caller_id = token_data["id"]
    if role == "merchant" and caller_id != merchant_id:
        raise HTTPException(status_code=403, detail="Merchants can only view their own profile")
    if role not in ("merchant", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


@app.post("/api/v1/merchants/{merchant_id}/payments/intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    merchant_id: int,
    token_data: dict = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """Initiate the pilot-fee payment. In production this calls the payment provider (e.g.,
    Stripe) and returns a client_secret for the front-end to redirect to a payment form.
    For MVP we stub a unique provider_payment_id and leave payment_status='payment_pending'
    until the webhook fires."""
    if token_data["id"] != merchant_id:
        raise HTTPException(status_code=403, detail="Merchants can only pay their own pilot fee")

    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    if merchant.is_active:
        raise HTTPException(status_code=400, detail="Merchant is already active; nothing to pay")

    # Stub provider integration. Replace with provider SDK in Phase 2.
    provider_payment_id = f"mvp_intent_{secrets.token_urlsafe(12)}"
    merchant.payment_provider_id = provider_payment_id
    merchant.payment_status = "payment_pending"
    db.commit()

    return PaymentIntentResponse(
        merchant_id=merchant.id,
        pilot_fee_cents=merchant.pilot_fee_cents,
        provider_payment_id=provider_payment_id,
        payment_status=merchant.payment_status,
        next_action=(
            "MVP stub: simulate the provider by POSTing a webhook to "
            "/api/v1/payments/webhook with the same provider_payment_id and "
            "payment_status='payment_successful'."
        ),
    )


@app.post("/api/v1/payments/webhook", response_model=PaymentWebhookResponse)
async def payment_webhook(req: PaymentWebhookRequest, db: Session = Depends(get_db)):
    """Endpoint the payment provider POSTs to when a payment reaches a terminal state.
    NOT JWT-gated — providers don't carry our JWTs. Production MUST verify a signature
    header against the provider's public key before trusting the payload; for MVP we
    accept any well-formed JSON.

    Activation rule: only `payment_status='payment_successful'` flips `is_active=True`
    and writes a PlatformRevenue row. `payment_pending` and `payment_declined` update
    the merchant's status but leave `is_active=False`."""
    valid_statuses = {"payment_successful", "payment_pending", "payment_declined"}
    if req.payment_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid payment_status. Expected one of {sorted(valid_statuses)}",
        )

    merchant = db.query(models.Merchant).filter(models.Merchant.id == req.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    # Cross-check provider_payment_id if one was previously stored — guards against
    # webhooks for a different intent landing on this merchant.
    if merchant.payment_provider_id and merchant.payment_provider_id != req.provider_payment_id:
        raise HTTPException(
            status_code=400,
            detail="provider_payment_id does not match the merchant's last payment intent",
        )

    occurred_at = _to_naive_utc(req.occurred_at)
    merchant.payment_status = req.payment_status
    merchant.payment_provider_id = req.provider_payment_id

    if req.payment_status == "payment_successful":
        # Idempotency: don't double-record revenue if the same successful webhook fires twice.
        already_active = bool(merchant.is_active)
        merchant.is_active = True
        merchant.last_payment_at = occurred_at
        if not already_active and req.amount_cents > 0:
            db.add(models.PlatformRevenue(
                source="merchant_pilot_fee",
                amount=req.amount_cents,
                user_id=None,
                note=f"Merchant {merchant.id} pilot fee via {req.provider_payment_id}",
            ))
        message = "Merchant activated. Pilot fee recorded."
    else:
        # Pending or declined: do NOT flip is_active. Merchant can retry.
        message = f"Status updated to {req.payment_status}; merchant remains inactive."

    db.commit()
    return PaymentWebhookResponse(
        merchant_id=merchant.id,
        payment_status=merchant.payment_status,
        is_active=bool(merchant.is_active),
        message=message,
    )


# --- v2.9: Admin merchant management (manual fallback for refunds / disputes / demos) ---

@app.get("/api/v1/admin/merchants", response_model=List[AdminMerchantListItem])
async def admin_list_merchants(
    status: Optional[str] = None,           # 'pending' | 'active' | 'declined' | 'all' (default 'all')
    token_data: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Admin-only triage view. Filter by activation status; sorted newest-first."""
    q = db.query(models.Merchant)
    if status == "active":
        q = q.filter(models.Merchant.is_active == True)  # noqa: E712
    elif status == "pending":
        q = q.filter(models.Merchant.payment_status == "payment_pending")
    elif status == "declined":
        q = q.filter(models.Merchant.payment_status == "payment_declined")
    elif status not in (None, "all"):
        raise HTTPException(status_code=400, detail="status must be one of: pending, active, declined, all")
    rows = q.order_by(models.Merchant.created_at.desc()).all()
    return rows


@app.post("/api/v1/admin/merchants/{merchant_id}/activate", response_model=AdminMerchantToggleResponse)
async def admin_activate_merchant(
    merchant_id: int,
    token_data: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Manual activation fallback. Use when payment was confirmed out-of-band (e.g., bank
    transfer for a pilot merchant) or to re-activate after a deactivate. Records a
    PlatformRevenue row only if the merchant wasn't already active."""
    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    already_active = bool(merchant.is_active)
    merchant.is_active = True
    merchant.payment_status = "payment_successful"
    merchant.last_payment_at = _now_naive_utc()
    if not already_active and (merchant.pilot_fee_cents or 0) > 0:
        db.add(models.PlatformRevenue(
            source="merchant_pilot_fee",
            amount=merchant.pilot_fee_cents,
            user_id=None,
            note=f"Manual admin activation of merchant {merchant.id}",
        ))
    db.commit()
    return AdminMerchantToggleResponse(
        merchant_id=merchant.id,
        is_active=True,
        payment_status=merchant.payment_status,
        message="Merchant activated by admin.",
    )


@app.post("/api/v1/admin/merchants/{merchant_id}/deactivate", response_model=AdminMerchantToggleResponse)
async def admin_deactivate_merchant(
    merchant_id: int,
    token_data: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Manual deactivation. Use for refunds, policy violations, or to remove a merchant
    from the pilot. Does not write a PlatformRevenue row (no money flowed)."""
    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    merchant.is_active = False
    db.commit()
    return AdminMerchantToggleResponse(
        merchant_id=merchant.id,
        is_active=False,
        payment_status=merchant.payment_status,
        message="Merchant deactivated by admin.",
    )


@app.post("/api/v1/bounties", response_model=BountySummary)
async def create_bounty(bounty: BountyCreate, db: Session = Depends(get_db), token_data: dict = Depends(get_current_admin_or_merchant)):
    if token_data["role"] == "merchant" and token_data["id"] != bounty.merchant_id:
        raise HTTPException(status_code=403, detail="Not authorized to create bounty for this merchant")
    """Seed a bounty. Used by admins for daily quests and by merchants for storefront chests.
    Geofence radius is in metres; distance to caller is filled with 0 since the creator may not
    be on-site."""
    if bounty.bounty_type == "merchant_chest" and bounty.merchant_id is None:
        raise HTTPException(status_code=400, detail="merchant_chest requires merchant_id")
    if bounty.merchant_id is not None:
        merchant_row = db.query(models.Merchant).filter(models.Merchant.id == bounty.merchant_id).first()
        if not merchant_row:
            raise HTTPException(status_code=404, detail="Merchant not found")
        # v2.9 gate: merchant_chest bounties require an active merchant. Daily/system bounties
        # may carry a merchant_id for attribution but don't require active status.
        if bounty.bounty_type == "merchant_chest" and not merchant_row.is_active:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Merchant {merchant_row.id} is not active "
                    f"(payment_status={merchant_row.payment_status}). "
                    "Complete the pilot-fee payment before creating merchant_chest bounties."
                ),
            )

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
async def get_nearby_bounties(lat: float, lng: float, radius_km: float = 5.0, db: Session = Depends(get_db), token_data: dict = Depends(get_current_player)):
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
async def complete_bounty(bounty_id: int, req: BountyCompleteRequest, db: Session = Depends(get_db), token_data: dict = Depends(get_current_player)):
    if token_data["id"] != req.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to complete bounty for this user")
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

@app.get("/api/v1/merchants/{merchant_id}/bounties", response_model=List[BountySummary])
async def get_merchant_bounties(merchant_id: int, db: Session = Depends(get_db), token_data: dict = Depends(get_current_merchant)):
    if token_data["id"] != merchant_id:
        raise HTTPException(status_code=403, detail="Not authorized to view these bounties")
    
    bounties = db.query(models.Bounty).filter(models.Bounty.merchant_id == merchant_id).all()
    
    result = []
    for b in bounties:
        result.append(BountySummary(
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
            distance_km=0.0,
        ))
    return result

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
