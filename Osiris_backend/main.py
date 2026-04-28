# --- Library Imports ---
# FastAPI: The core web framework. HTTPException: Used to return errors (like 404 Not Found). Depends: Used to inject database sessions.
from fastapi import FastAPI, HTTPException, Depends
# Pydantic: Used for validating the shape of JSON data coming in and going out of our API.
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import json
import secrets
# SQLAlchemy: Our ORM (Object Relational Mapper). It lets us interact with the database using Python objects instead of raw SQL.
from sqlalchemy.orm import Session
# bcrypt: Used to securely scramble (hash) passwords so they aren't saved as plain text.
import bcrypt
# APScheduler: Runs background tasks automatically (like a cron job) while the server is running.
from apscheduler.schedulers.background import BackgroundScheduler

# Import our newly created database connection and models
import database
import models
import spatial_utils

# This line tells SQLAlchemy to look at our models and actually CREATE the tables 
# in the SQLite database file if they don't exist yet.
models.Base.metadata.create_all(bind=database.engine)

# Initialize the FastAPI application
app = FastAPI(title="Verified Fitness Reward System API", version="1.0-MVP")

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

# The JSON shape for a single GPS point in our Domain trace
class Coordinate(BaseModel):
    lat: float
    lng: float
    timestamp: datetime

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
    """Authenticates a user and returns their profile data for the app to load."""
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
    increment_stat_from_activity(user, domain_req.defense_type, domain_req.defense_score)

    db.add(new_domain)
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
            challenger.mana_crystals += winner_share
            crystals_awarded = winner_share
            target_domain.vault_balance = 0

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
            # SYSTEM_KEEP portion is simply not credited to anyone (platform revenue).
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
        siege.status = "failed"
        message = "Defense held. Your Defense Feat did not beat the defender's Ghost score."
        if new_discount_banked > 0:
            message += f" {new_discount_banked} crystals banked as a retry discount."

    # Stat increment runs regardless of outcome — the challenger performed the activity.
    increment_stat_from_activity(challenger, target_defense_type, req.challenger_score)

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
async def get_user_party_role(user_id: int, db: Session = Depends(get_db)):
    """Returns the user's assigned Party Role (Vanguard / Striker / Scout / Strategist)
    based on their leading attribute stat. MVP uses lifetime totals; Phase 2 will switch
    to a rolling 30-day window computed from an ActivityLog."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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

    # Score gate — bounties with target_score=0 are proximity-only (e.g., merchant chests).
    if bounty.target_score > 0 and req.score < bounty.target_score:
        raise HTTPException(status_code=400, detail=f"Score {req.score} did not meet target {bounty.target_score}")

    # Award rewards
    device_ts = _to_naive_utc(req.device_timestamp)
    user.xp += bounty.xp_reward
    user.mana_crystals += bounty.crystal_reward
    user.last_activity_date = device_ts
    user.rank = get_rank(user.xp, user.last_activity_date)
    stat_touched = increment_stat_from_activity(user, bounty.activity_type, req.score or bounty.target_score)

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

scheduler = BackgroundScheduler()

@app.on_event("startup")
def start_scheduler():
    """When the FastAPI server starts, begin the background scheduler."""
    scheduler.add_job(process_daily_decay, 'interval', hours=24)
    scheduler.start()

@app.on_event("shutdown")
def shutdown_scheduler():
    """Safely shut down the background scheduler when the FastAPI server stops."""
    scheduler.shutdown()
