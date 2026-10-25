"""Player accounts (v1): sign-up, login, profile, GDPR export and erasure."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import growth_safety
import models
from core.clock import _to_naive_utc
from core.rate_limit import _rl_login, _rl_onboard
from core.security import create_access_token, get_current_user_token, get_password_hash, verify_password
from database import get_db
from schemas import AuthLoginRequest, AuthLoginResponse, UserCreate, UserLogin, UserProfile
from services import ledger
from services.accounts import _check_email_unique
from services.progression import get_avatar_class, get_rank, get_title

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Endpoints ---

@router.post("/api/v1/onboard", response_model=UserProfile)
def onboard_user(user: UserCreate, db: Session = Depends(get_db), _rl: None = Depends(_rl_onboard)):
    """API Endpoint to register a new user, calculate their stats, and assign an avatar."""

    # 0. Check if user email already exists across any table
    _check_email_unique(db, user.email)

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
    # mana_crystals starts at 0 here; the opening grant is applied below via the ledger
    # service so the invariant sum(CrystalLedger.delta) == mana_crystals holds from row one.
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
        streak=0,
        mana_crystals=0,
    )

    # 4. Save to Database. Flush first to mint the user id, then write the opening-balance
    # ledger row (the ONLY path that sets the starting wallet), and commit atomically.
    db.add(new_user)
    db.flush()  # populates new_user.id without committing
    ledger.apply_crystal_delta(
        db, new_user, models.OPENING_CRYSTAL_BALANCE, "opening_balance",
        note="New player opening grant",
    )
    db.commit()
    db.refresh(new_user) # Retrieves the newly generated 'id' from the database

    # 5. Return the saved data
    # (FastAPI automatically converts the SQLAlchemy model into the Pydantic UserProfile JSON)
    return new_user

@router.post("/api/v1/login", response_model=UserProfile)
def login_user(credentials: UserLogin, db: Session = Depends(get_db), _rl: None = Depends(_rl_login)):
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


@router.post("/api/v1/auth/login", response_model=AuthLoginResponse)
def auth_login(credentials: AuthLoginRequest, db: Session = Depends(get_db), _rl: None = Depends(_rl_login)):
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
    except HTTPException:
        # Auth-flow HTTPExceptions (e.g., the 401 above) are intentional — let them through
        # rather than re-wrapping them as 500s.
        raise
    except Exception:
        # Log the full stack trace server-side; return an opaque 500 to the client so we
        # don't leak internals (DB errors, secrets) over the wire.
        logger.exception("auth_login: unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/api/v1/users/{user_id}", response_model=UserProfile)
def get_user_profile(
    user_id: int,
    token_data: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db),
):
    """Fetches the latest stats, Rank, and XP for the app dashboard. RBAC: a player can
    only fetch their own profile; admins can fetch any. Merchants get 403 — they have no
    legitimate reason to read player profiles."""
    role = token_data["role"]
    caller_id = token_data["id"]
    if role == "player" and caller_id != user_id:
        raise HTTPException(status_code=403, detail="Players can only fetch their own profile")
    if role not in ("player", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/api/v1/users/{user_id}")
def delete_user_account(
    user_id: int,
    token_data: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db),
):
    """GDPR Right to Erasure (§3.4). Same erasure as `POST /api/v2/me/erase`: personal data is
    deleted and the users row stays as an anonymous tombstone, so the crystal ledger is kept
    (financial records are anonymised, not destroyed — PRD-009) and the id is never reused."""
    caller_id = token_data["id"]
    role = token_data["role"]
    if role == "player" and caller_id != user_id:
        raise HTTPException(status_code=403, detail="Players can only delete their own account")
    if role not in ("player", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Legacy v1 personal data that erase_player does not cover: exact territory polygons,
    # issued coupon codes, and proof hashes.
    db.query(models.BountyCompletion).filter(models.BountyCompletion.user_id == user_id).delete(synchronize_session=False)
    db.query(models.ProofConsumed).filter(models.ProofConsumed.user_id == user_id).delete(synchronize_session=False)
    db.query(models.Domain).filter(models.Domain.owner_id == user_id).delete(synchronize_session=False)
    growth_safety.erase_player(db, user, role, caller_id)
    db.commit()
    return {"status": "deleted", "user_id": user_id, "message": "Account and personal data erased."}


@router.get("/api/v1/users/{user_id}/export")
def export_user_data(
    user_id: int,
    token_data: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db),
):
    """GDPR Data Portability (§3.4): returns user profile and activity summary."""
    caller_id = token_data["id"]
    role = token_data["role"]
    if role == "player" and caller_id != user_id:
        raise HTTPException(status_code=403, detail="Players can only export their own account data")
    if role not in ("player", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    activities_count = db.query(models.ActivityLog).filter(models.ActivityLog.user_id == user_id).count()
    completions_count = db.query(models.BountyCompletion).filter(models.BountyCompletion.user_id == user_id).count()
    domains_count = db.query(models.Domain).filter(models.Domain.owner_id == user_id).count()
    telemetry_count = db.query(models.TelemetrySession).filter(models.TelemetrySession.user_id == user_id).count()

    return {
        "user_profile": {
            "id": user.id,
            "email": user.email,
            "bmi": user.bmi,
            "avatar_class": user.avatar_class,
            "rank": user.rank,
            "title": user.title,
            "cumulative_area": user.cumulative_area,
            "xp": user.xp,
            "streak": user.streak,
            "mana_crystals": user.mana_crystals,
            "last_activity_date": user.last_activity_date.isoformat() if user.last_activity_date else None,
        },
        "summary": {
            "activities_recorded": activities_count,
            "bounties_completed": completions_count,
            "domains_owned": domains_count,
            "telemetry_sessions": telemetry_count,
        },
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
