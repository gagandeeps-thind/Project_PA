from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

# Import our newly created database connection and models
import database
import models

# This line tells SQLAlchemy to look at our models and actually CREATE the tables 
# in the SQLite database if they don't exist yet.
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Verified Fitness Reward System API", version="1.0-MVP")


@app.get("/")
async def root():
    return {
        "message": "Verified Fitness Reward System API is running",
        "docs": "/docs"
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return {}

# --- Pydantic Models ---

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    weight_kg: float = Field(..., gt=0, description="Weight in kg must be greater than 0")
    height_m: float = Field(..., gt=0, description="Height in meters must be greater than 0")
    preferred_path: str = "Balance"  # Options: Strength, Cardio, Balance

class UserProfile(BaseModel):
    id: int
    email: EmailStr
    bmi: float
    avatar_class: str
    xp: int
    rank: str
    last_activity_date: datetime
    streak: int

    class Config:
        from_attributes = True  # For Pydantic v2 (Modern FastAPI)

# --- Core Business Logic ---

# --- Dependencies ---
def get_db():
    """Creates a new database session for a request and closes it when done."""
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
    """Calculates Grade/Title based on Master GDD Tier System."""
    if last_activity_date:
        days_inactive = (datetime.utcnow() - last_activity_date).total_seconds() / 86400
        if days_inactive > 30:
            return "F - The Dishonored"
            
    if xp < 500: return "D - Beginner"
    if xp < 1000: return "C - Intermediate"
    if xp < 2500: return "B - Advanced"
    if xp < 5000: return "A - Saint"
    if xp < 7500: return "S - King"
    if xp < 10000: return "SS - Emperor"
    return "SSS - God"

# --- Endpoints ---

@app.post("/api/v1/onboard", response_model=UserProfile)
async def onboard_user(user: UserCreate, db: Session = Depends(get_db)):
    """Creates a new user, calculates their stats, and assigns an avatar."""
    
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
    # TODO: In a real app, hash the password using passlib/bcrypt here!
    fake_hashed_password = user.password + "_hashed"
    
    new_user = models.User(
        email=user.email,
        hashed_password=fake_hashed_password,
        bmi=bmi,
        avatar_class=avatar_class,
        xp=0,
        rank=get_rank(0),
        last_activity_date=datetime.utcnow(),
        streak=0
    )
    
    # 4. Save to Database
    db.add(new_user)
    db.commit()
    db.refresh(new_user) # Retrieves the newly generated ID and data from the database
    
    # 5. Return the saved data
    # (FastAPI automatically converts the SQLAlchemy model back to the Pydantic UserProfile)
    return new_user

# --- Background Tasks (Cron Logic) ---

def process_daily_decay(profile: UserProfile) -> UserProfile:
    """To be triggered daily. Deducts XP if last activity is > 24 hours."""
    now = datetime.utcnow()
    hours_since_activity = (now - profile.last_activity_date).total_seconds() / 3600
    
    if hours_since_activity > 24:
        profile.streak = 0
        # Deduct 5% of XP daily as a penalty
        penalty = int(profile.xp * 0.05)
        profile.xp = max(0, profile.xp - penalty)
        
    # Re-evaluate rank in case XP dropped below a threshold or 30-day inactivity hit
    profile.rank = get_rank(profile.xp, profile.last_activity_date)
        
    return profile
