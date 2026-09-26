# --- Library Imports ---
# FastAPI: The core web framework. HTTPException: Used to return errors (like 404 Not Found). Depends: Used to inject database sessions.
from fastapi import FastAPI, HTTPException, Depends, Request
# Pydantic: Used for validating the shape of JSON data coming in and going out of our API.
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import json
import logging
import os
import secrets
import hashlib
import hmac

# Load a local .env (gitignored) into os.environ before anything reads config. In real
# deployments env vars are set by the platform/CI and this is a no-op; locally it's how
# OSIRIS_* / STRIPE_* secrets get in without exporting them by hand. Existing real env vars
# win (override=False) so the shell/CI always takes precedence over a stray .env.
from dotenv import load_dotenv
load_dotenv(override=False)

logger = logging.getLogger(__name__)
# SQLAlchemy: Our ORM (Object Relational Mapper). It lets us interact with the database using Python objects instead of raw SQL.
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
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
import run_verifier
from services import ledger, stripe_gateway

# Bootstrap convenience: creates any missing tables on first run. Alembic is the schema
# source-of-truth going forward (see `alembic/` + `alembic.ini`). For new dev DBs, run
# `alembic upgrade head` instead. This line is kept so the existing test scripts in
# `tests/` that use the live DB still work without an extra setup step.
#
# WARNING: every model change still needs an Alembic revision —
#   `alembic revision --autogenerate -m "..."` then `alembic upgrade head`.
# `create_all` only creates *missing* tables; it never alters existing ones, so a forgotten
# migration will silently let dev drift away from prod.
models.Base.metadata.create_all(bind=database.engine)

# Background scheduler — runs the daily-decay cron. Defined before the app so the lifespan
# handler below can reference it. Job is wired in lifespan(), not at module import.
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler — replaces the deprecated @app.on_event("startup"/"shutdown")
    pattern. Background jobs are wired up on startup and torn down cleanly on shutdown.
    The job functions are defined later in the module; that's fine because lifespan only
    runs once the server starts (after full module import)."""
    scheduler.add_job(process_daily_decay, 'interval', hours=24)
    # v2.11 telemetry retention: nightly cleanup of raw sample blobs older than TTL.
    scheduler.add_job(process_telemetry_ttl, 'interval', hours=24)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()

# --- Phase 0: structured JSON logging skeleton ---------------------------------
# Emits one JSON line per request (request id, user id, route, method, status, latency).
# Opt-in via OSIRIS_LOG_JSON=1 so local dev keeps human-readable logs by default; CI and
# any container set the env var. This is a *skeleton* — fields can grow; format stays JSON.
import time as _time
import contextvars

_request_id_ctx: "contextvars.ContextVar[str]" = contextvars.ContextVar("request_id", default="-")


class _JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": _request_id_ctx.get(),
        }
        # Structured extras attached via logger.info(..., extra={"ctx": {...}})
        ctx = getattr(record, "ctx", None)
        if isinstance(ctx, dict):
            payload.update(ctx)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _configure_logging() -> None:
    level = os.environ.get("OSIRIS_LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler()
    if os.environ.get("OSIRIS_LOG_JSON", "").lower() in ("1", "true", "yes"):
        handler.setFormatter(_JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    # Replace existing handlers so we don't double-log under uvicorn.
    root.handlers = [handler]
    # Quiet chatty third-party loggers so they don't drown the access log.
    for noisy in ("alembic", "apscheduler", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_configure_logging()

# Initialize the FastAPI application
app = FastAPI(title="Verified Fitness Reward System API", version="1.0-MVP", lifespan=lifespan)

# Phase 2 / audit §2.5: explicit CORS allowlist. `allow_origins=["*"]` with
# `allow_credentials=True` is invalid (browsers refuse credentialed requests to a wildcard
# origin) and signals "any site may call us with the user's session." Origins come from
# OSIRIS_CORS_ORIGINS (comma-separated) with a localhost dev default for the Vite admin web.
# Native mobile apps (customer/merchant) are not subject to browser CORS, so they need no entry.
_default_cors = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
_cors_origins = [
    o.strip() for o in os.environ.get("OSIRIS_CORS_ORIGINS", _default_cors).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Phase 0: per-request structured access log + request id -------------------
@app.middleware("http")
async def _access_log_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or secrets.token_hex(8)
    token = _request_id_ctx.set(req_id)
    start = _time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = req_id
        return response
    finally:
        latency_ms = round((_time.perf_counter() - start) * 1000, 2)
        # user id is best-effort: auth dependencies may set request.state.user_id.
        user_id = getattr(request.state, "user_id", None)
        logger.info(
            "request",
            extra={"ctx": {
                "method": request.method,
                "route": request.url.path,
                "status": status_code,
                "latency_ms": latency_ms,
                "user_id": user_id,
            }},
        )
        _request_id_ctx.reset(token)


# --- Phase 0: liveness/readiness probe ----------------------------------------
# include_in_schema=False keeps it out of the client OpenAPI contract (ops-only route).
@app.get("/healthz", include_in_schema=False)
def healthz():
    """Readiness probe: DB reachable + migrations current.

    Returns 200 only when a trivial query succeeds AND the DB's stamped Alembic
    revision matches the latest local migration head. 503 otherwise."""
    from sqlalchemy import text

    checks: dict = {"db": "down", "migrations": "unknown"}
    try:
        with database.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            checks["db"] = "ok"
            db_rev = None
            try:
                db_rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            except Exception:
                db_rev = None
        head_rev = _alembic_head_revision()
        if db_rev is not None and head_rev is not None:
            checks["migrations"] = "current" if db_rev == head_rev else f"behind ({db_rev} != {head_rev})"
            checks["db_revision"] = db_rev
            checks["head_revision"] = head_rev
    except Exception as exc:  # pragma: no cover - exercised via probe, not unit test
        logger.warning("healthz check failed", extra={"ctx": {"error": str(exc)}})

    healthy = checks["db"] == "ok" and checks["migrations"] in ("current", "unknown")
    if not healthy:
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ok", **checks}


def _alembic_head_revision() -> Optional[str]:
    """Latest revision id from the local alembic/versions scripts, or None if unavailable."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:
        return None

# --- v2.10: JWT secret loaded from env var with a clearly-flagged dev fallback ---
# Set OSIRIS_JWT_SECRET in any non-dev environment. Deployment must use a 32+ byte secret
# (HS256 minimum per RFC 7518 § 3.2). Setting OSIRIS_ENV=production makes a missing secret
# fatal at boot — that's the production-safety check.
_jwt_secret_from_env = os.environ.get("OSIRIS_JWT_SECRET")
if _jwt_secret_from_env:
    SECRET_KEY = _jwt_secret_from_env
elif os.environ.get("OSIRIS_ENV", "").lower() == "production":
    raise RuntimeError(
        "OSIRIS_JWT_SECRET is required when OSIRIS_ENV=production. "
        "Generate one with `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`."
    )
else:
    # Dev fallback: ephemeral 48-byte secret regenerated each boot. Existing tokens become
    # invalid on every reload, which is what we want during local development.
    SECRET_KEY = secrets.token_urlsafe(48)
    print(
        "WARNING: OSIRIS_JWT_SECRET not set — using an ephemeral dev secret. "
        "Tokens will not survive a server restart."
    )

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


# --- v2.10: webhook signature verification ---
# Off by default during MVP so manual webhook calls work in smoke tests. To enable, set
# OSIRIS_WEBHOOK_SECRET=<hex-bytes>. With it set, every /payments/webhook call MUST carry
# `X-Provider-Signature: <hex hmac-sha256 over the raw body>` or it 401s.
#
# Production safety: when OSIRIS_ENV=production, the secret is required at boot. Without it
# the webhook endpoint would accept any payload — indistinguishable from a forged-webhook
# attacker activating an arbitrary merchant. Mirrors the JWT secret pattern above.
# Phase 2 / audit §2.1: FAIL CLOSED. The webhook secret is REQUIRED unless OSIRIS_ENV is an
# *explicit* dev/test value. A forgotten or unknown OSIRIS_ENV is treated as production and
# must refuse to boot — the old behavior (fail open whenever the secret was unset, only
# fail-fast when OSIRIS_ENV was *explicitly* "production") meant a deploy that forgot the env
# var served a wide-open, forgeable payment webhook. Inverted here.
_DEV_ENVS = {"dev", "development", "test", "testing", "local"}
_IS_DEV_ENV = os.environ.get("OSIRIS_ENV", "").lower() in _DEV_ENVS
_WEBHOOK_SECRET = os.environ.get("OSIRIS_WEBHOOK_SECRET")
if not _WEBHOOK_SECRET and not _IS_DEV_ENV:
    raise RuntimeError(
        "OSIRIS_WEBHOOK_SECRET is required unless OSIRIS_ENV is one of "
        f"{sorted(_DEV_ENVS)}. An unset or unknown OSIRIS_ENV is treated as production: "
        "the app refuses to boot rather than serve an unauthenticated, forgeable payment "
        "webhook (audit §2.1). For local development set OSIRIS_ENV=dev. "
        "Generate a secret with `python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
        "and configure the same value on the payment provider's webhook settings."
    )

# Stripe fail-closed boot check (audit §2.1 parity). Called here, AFTER the webhook-secret
# check above, so that when multiple secrets are missing the OSIRIS_WEBHOOK_SECRET error
# surfaces first (stripe_gateway is import-side-effect-free by design).
stripe_gateway.assert_boot_config()

async def verify_webhook_signature(request: Request) -> bytes:
    """Reads the raw body once, validates the X-Provider-Signature HMAC, and returns the
    body bytes so the calling endpoint can re-parse them (FastAPI's body() consumes the
    stream — we do it here so signature + parsing share one read)."""
    body = await request.body()
    if _WEBHOOK_SECRET is None:
        return body  # MVP / dev: signature checking disabled
    sig = request.headers.get("X-Provider-Signature", "")
    expected = hmac.new(
        _WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    return body

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

# --- Phase 2 / audit §4.3: rate limiting ------------------------------------------------
# Dependency-free, in-memory sliding-window limiter keyed on client IP + scope. Sufficient for
# the single-VM pilot; at horizontal scale this must move to a shared store (Redis) because the
# buckets are per-process. Disabled in dev/test (OSIRIS_ENV dev/test) so the suites and local
# work aren't throttled — it protects the real deployment, where OSIRIS_ENV is prod-like.
import threading as _threading

_rate_buckets: "dict[str, list[float]]" = {}
_rate_lock = _threading.Lock()


def _rate_limit(max_requests: int, window_s: int, scope: str):
    """Returns a FastAPI dependency that raises 429 when an IP exceeds `max_requests` in
    `window_s` seconds for the given `scope`."""
    def _dep(request: Request) -> None:
        if _IS_DEV_ENV:
            return  # no throttling in dev/test
        ip = request.client.host if request.client else "unknown"
        key = f"{scope}:{ip}"
        now = _time.monotonic()
        cutoff = now - window_s
        with _rate_lock:
            bucket = _rate_buckets.setdefault(key, [])
            # Drop timestamps outside the window.
            i = 0
            for ts in bucket:
                if ts >= cutoff:
                    break
                i += 1
            if i:
                del bucket[:i]
            if len(bucket) >= max_requests:
                raise HTTPException(status_code=429, detail="Too many requests. Slow down.")
            bucket.append(now)
    return _dep


# Prod defaults; tuned for the Bedford pilot. Auth + payment + proof endpoints are the
# brute-force / spam / CPU-burn (triple-bcrypt) targets named in the audit.
_rl_login = _rate_limit(10, 60, "login")
_rl_onboard = _rate_limit(5, 60, "onboard")
_rl_verify = _rate_limit(30, 60, "verify")
_rl_webhook = _rate_limit(60, 60, "webhook")


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
    password: str = Field(..., min_length=8, max_length=72, description="8-72 characters (bcrypt's byte limit).")
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


# --- First-release running loop ------------------------------------------------

class RunSessionCreate(BaseModel):
    activity_type: str = Field(default="run", pattern="^(run|jog)$")
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
    xp_awarded: int = 0
    message: str


def _run_summary(session: models.RunSession, *, xp_awarded: int = 0, message: str = "Run session") -> RunSessionSummary:
    return RunSessionSummary(
        id=session.id,
        activity_type=session.activity_type,
        status=session.status,
        verification_status=session.verification_status,
        point_count=session.point_count or 0,
        distance_m=round(session.distance_m or 0.0, 2),
        duration_seconds=round(session.duration_seconds or 0.0, 2),
        route_hash=session.route_hash,
        rejection_reason=session.rejection_reason,
        xp_awarded=xp_awarded,
        message=message,
    )

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
    password: str = Field(..., min_length=8, max_length=72)
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


# --- Phase 3: player crystal top-up (one-way real-money purchase) ---
#
# Server-authoritative crystal packs. The client picks a `pack_id`; the SERVER decides the
# price and the crystal grant. The client never sends an amount — that's the whole point, it
# stops a tampered client buying 1,000,000 crystals for $0.01.
#
# NOTE: this purchase path is intentionally isolated behind server-authoritative packs,
# payment-provider confirmation, and ledgered fulfillment.
CRYSTAL_PACKS: dict[str, dict] = {
    "starter":    {"crystals": 500,  "amount_cents": 499,  "label": "Starter Pouch"},
    "adventurer": {"crystals": 1200, "amount_cents": 999,  "label": "Adventurer's Cache"},
    "champion":   {"crystals": 2600, "amount_cents": 1999, "label": "Champion's Hoard"},
}
CRYSTAL_PURCHASE_CURRENCY = "usd"


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
    proof: Optional["ActivityProof"] = None,
) -> Optional[models.ActivityLog]:
    """Single entry point for the activity history table. Three writes happen here:

    1. **Lifetime stat increment** on the User row (cheap aggregate read path).
    2. **`ActivityLog` row** for the 30-day rolling Party-Stats window.
    3. **`TelemetrySession` + per-sensor `TelemetryData` rows** if a `proof` is attached —
       gives the ML training pipeline raw sensor data linked back to the gameplay outcome.

    Returns the new ActivityLog row (uncommitted) or None when score is non-positive."""
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

    # If the caller also gave us the raw proof, archive sensor data linked to this log row.
    if proof is not None:
        db.flush()  # need log.id before linking telemetry rows
        _persist_telemetry(db, user.id, log.id, proof, occurred_at, verified, confidence)

    return log


def _persist_telemetry(
    db: Session,
    user_id: int,
    activity_log_id: int,
    proof: "ActivityProof",
    occurred_at: datetime,
    verified: bool,
    confidence: float,
) -> None:
    """Writes one TelemetrySession (metadata) + N TelemetryData rows (one per non-empty
    sensor channel). Pose, when present, is stored as a single-element JSON array under
    sensor_type='pose'."""
    session = models.TelemetrySession(
        user_id=user_id,
        activity_log_id=activity_log_id,
        activity_type=(proof.activity_type or "").lower(),
        declared_score=proof.declared_score,
        duration_seconds=proof.duration_seconds,
        confidence=confidence,
        verified=1 if verified else 0,
        sample_count_accel=len(proof.accelerometer),
        sample_count_gyro=len(proof.gyroscope),
        sample_count_mag=len(proof.magnetometer),
        sample_count_gps=len(proof.gps),
        sample_count_barometer=len(proof.barometer),
        has_pose=proof.pose is not None,
        occurred_at=occurred_at,
    )
    db.add(session)
    db.flush()  # session.id needed for child rows

    # Per-sensor archives. Empty channels skipped to avoid noise rows.
    sensor_blobs = [
        ("accel",        [s.model_dump() for s in proof.accelerometer]),
        ("gyro",         [s.model_dump() for s in proof.gyroscope]),
        ("magnetometer", [s.model_dump() for s in proof.magnetometer]),
        ("gps",          [s.model_dump() for s in proof.gps]),
        ("barometer",    [s.model_dump() for s in proof.barometer]),
    ]
    for sensor_type, samples in sensor_blobs:
        if not samples:
            continue
        db.add(models.TelemetryData(
            session_id=session.id,
            sensor_type=sensor_type,
            sample_count=len(samples),
            samples_json=json.dumps(samples, default=str),
        ))
    if proof.pose is not None:
        db.add(models.TelemetryData(
            session_id=session.id,
            sensor_type="pose",
            sample_count=1,
            samples_json=json.dumps(proof.pose.model_dump(), default=str),
        ))

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
async def onboard_user(user: UserCreate, db: Session = Depends(get_db), _rl: None = Depends(_rl_onboard)):
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
async def auth_login(credentials: AuthLoginRequest, db: Session = Depends(get_db), _rl: None = Depends(_rl_login)):
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

@app.get("/api/v1/users/{user_id}", response_model=UserProfile)
async def get_user_profile(
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


# --- First-release API v2: verified running -----------------------------------

def _get_player_run(db: Session, run_id: int, player_id: int) -> models.RunSession:
    session = db.query(models.RunSession).filter(models.RunSession.id == run_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Run session not found")
    if session.user_id != player_id:
        raise HTTPException(status_code=403, detail="Run session belongs to another player")
    return session


@app.post("/api/v2/runs", response_model=RunSessionSummary, status_code=201)
async def create_run_session(
    req: RunSessionCreate,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_player),
):
    """Create a run shell. The route is not accepted until it is finished and verified."""
    session = models.RunSession(
        user_id=token_data["id"],
        activity_type=req.activity_type.lower(),
        status="created",
        device_started_at=_to_naive_utc(req.device_started_at),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _run_summary(session, message="Run session created")


@app.post("/api/v2/runs/{run_id}/start", response_model=RunSessionSummary)
async def start_run_session(
    run_id: int,
    req: RunSessionStart,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_player),
):
    session = _get_player_run(db, run_id, token_data["id"])
    if session.status == "active":
        return _run_summary(session, message="Run session already active")
    if session.status != "created":
        raise HTTPException(status_code=409, detail=f"Run session cannot start from status={session.status}")
    session.status = "active"
    session.started_at = _now_naive_utc()
    session.device_started_at = _to_naive_utc(req.device_started_at)
    session.updated_at = _now_naive_utc()
    db.commit()
    db.refresh(session)
    return _run_summary(session, message="Run session started")


@app.post("/api/v2/runs/{run_id}/points", response_model=RunSessionSummary)
async def append_run_points(
    run_id: int,
    req: RoutePointBatch,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_player),
):
    session = _get_player_run(db, run_id, token_data["id"])
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Route points can only be appended to an active run")
    existing_last = (
        db.query(models.RoutePoint)
        .filter(models.RoutePoint.run_session_id == run_id)
        .order_by(models.RoutePoint.sequence.desc())
        .first()
    )
    expected = (existing_last.sequence + 1) if existing_last else 0
    sequences = [point.sequence for point in req.points]
    if sequences != list(range(expected, expected + len(sequences))):
        raise HTTPException(status_code=409, detail=f"Route sequence must start at {expected} and be contiguous")
    for point in req.points:
        db.add(models.RoutePoint(
            run_session_id=run_id,
            sequence=point.sequence,
            t_ms=point.t_ms,
            lat=point.lat,
            lng=point.lng,
            accuracy_m=point.accuracy_m,
            speed_mps=point.speed_mps,
            altitude_m=point.altitude_m,
        ))
    session.point_count = (session.point_count or 0) + len(req.points)
    session.updated_at = _now_naive_utc()
    db.commit()
    db.refresh(session)
    return _run_summary(session, message=f"Accepted {len(req.points)} route points")


@app.post("/api/v2/runs/{run_id}/finish", response_model=RunSessionSummary)
async def finish_run_session(
    run_id: int,
    req: RunSessionFinish,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_player),
):
    session = _get_player_run(db, run_id, token_data["id"])
    if session.status in ("submitted", "verifying", "closed"):
        if session.finish_idempotency_key == req.idempotency_key:
            return _run_summary(session, message="Run finish already processed")
        raise HTTPException(status_code=409, detail="Run session has already been finished")
    if session.status != "active":
        raise HTTPException(status_code=409, detail=f"Run session cannot finish from status={session.status}")

    points = (
        db.query(models.RoutePoint)
        .filter(models.RoutePoint.run_session_id == run_id)
        .order_by(models.RoutePoint.sequence.asc())
        .all()
    )
    if not points:
        raise HTTPException(status_code=400, detail="A run must contain route points before it can finish")

    session.status = "verifying"
    session.device_finished_at = _to_naive_utc(req.device_finished_at)
    session.finished_at = _now_naive_utc()
    session.finish_idempotency_key = req.idempotency_key
    session.updated_at = _now_naive_utc()
    db.flush()

    result = run_verifier.verify_route([
        {
            "sequence": point.sequence,
            "t_ms": point.t_ms,
            "lat": point.lat,
            "lng": point.lng,
            "accuracy_m": point.accuracy_m,
            "speed_mps": point.speed_mps,
            "altitude_m": point.altitude_m,
        }
        for point in points
    ])
    session.status = "closed"
    session.verification_status = result.status
    session.route_hash = result.route_hash
    session.distance_m = float(result.metrics["distance_m"])
    session.duration_seconds = float(result.metrics["duration_seconds"])
    session.rejection_reason = ",".join(result.reason_codes) if result.reason_codes else None
    decision = models.VerificationDecision(
        run_session_id=session.id,
        rules_version=run_verifier.RULES_VERSION,
        status=result.status,
        reason_codes_json=json.dumps(result.reason_codes),
        metrics_json=json.dumps(result.metrics),
    )
    db.add(decision)

    xp_awarded = 0
    if result.status == "accepted":
        user = db.query(models.User).filter(models.User.id == token_data["id"]).first()
        if user:
            xp_awarded = max(10, int(float(result.metrics["distance_m"]) // 100))
            user.xp += xp_awarded
            user.last_activity_date = session.finished_at
            user.rank = get_rank(user.xp, user.last_activity_date)
            record_activity(
                db, user, "run", max(1, int(float(result.metrics["distance_m"]) // 100)),
                session.finished_at, "run_session", related_id=session.id,
                verified=True, confidence=1.0,
            )
    db.commit()
    db.refresh(session)
    message = "Run verified and accepted" if result.status == "accepted" else "Run rejected by verification rules"
    return _run_summary(session, xp_awarded=xp_awarded, message=message)


@app.get("/api/v2/runs/{run_id}", response_model=RunSessionSummary)
async def get_run_session(
    run_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_player),
):
    session = _get_player_run(db, run_id, token_data["id"])
    return _run_summary(session, message="Run session status")

@app.get("/api/v1/domains/nearby", response_model=List[DomainSummary])
async def get_nearby_domains(
    lat: float,
    lng: float,
    radius_km: float = 5.0,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_player),
):
    """Returns existing claimed domains whose centroid falls within `radius_km` of (lat, lng),
    sorted nearest-first.

    Phase 2 / audit §2.2: this is now AUTHENTICATED (a player JWT is required). Previously it
    was public, which leaked `owner_id` + exact polygon geometry + `vault_balance` for any
    lat/lng to any unauthenticated caller — a stalking + economic-recon primitive. Requiring
    auth closes the unauthenticated leak. NOTE (residual risk, see register): the response
    still exposes raw `owner_id` and full geometry to *authenticated* players; coarsening to an
    opaque handle + centroid-only for non-owners is a follow-up that changes the client
    contract and is deferred for a product decision. MVP uses an in-memory haversine sweep;
    PostGIS `ST_DWithin` replaces this in Phase 4."""
    candidates = db.query(models.Domain).all()
    out: List[DomainSummary] = []
    for d in candidates:
        if not d.geometry_json:
            continue
        try:
            coords = json.loads(d.geometry_json)
        except Exception:
            continue
        if not coords:
            continue
        # Centroid as the simple average of vertex coords. Fine for park-sized polygons;
        # PostGIS `ST_Centroid` will be exact in Phase 2.
        c_lat = sum(c["lat"] for c in coords) / len(coords)
        c_lng = sum(c["lng"] for c in coords) / len(coords)
        dist = spatial_utils.haversine_distance(lat, lng, c_lat, c_lng)
        if dist > radius_km:
            continue
        out.append(DomainSummary(
            id=d.id,
            owner_id=d.owner_id,
            area_sqkm=d.area_sqkm or 0.0,
            defense_score=d.defense_score or 0,
            defense_type=d.defense_type or "pushups",
            vault_balance=d.vault_balance or 0,
            is_protected=(d.vault_balance or 0) > 0,
            geometry=coords,
            centroid_lat=c_lat,
            centroid_lng=c_lng,
            distance_km=round(dist, 4),
        ))
    out.sort(key=lambda x: x.distance_km)
    return out


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
    # 0.55. Co-location: if the proof carries GPS samples, they must land inside the polygon
    # the user is trying to claim. Cheapest big anti-cheat win — without this a verified
    # workout from anywhere can be attached to any polygon.
    claim_polygon = [{"lat": c.lat, "lng": c.lng} for c in domain_req.coordinates]
    _enforce_proof_gps_in_polygon(domain_req.defense_proof, claim_polygon, context="domain_claim")
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
        proof=domain_req.defense_proof,
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

    ledger.apply_crystal_delta(
        db, user, -delta, "vault_lock",
        related_domain_id=domain.id,
        note=f"Vault lock to {req.amount} on domain {domain.id}",
    )
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
    # Co-location: the challenger's GPS samples (if present) must land inside the polygon
    # being sieged — you can't take someone's land from another time zone.
    if req.challenger_proof is not None and target_domain.geometry_json:
        try:
            target_polygon = json.loads(target_domain.geometry_json)
            _enforce_proof_gps_in_polygon(req.challenger_proof, target_polygon, context="siege_resolve")
        except (ValueError, json.JSONDecodeError):
            # Corrupted polygon JSON — skip the check rather than block the resolve.
            pass
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
    is_time_trial = target_defense_type in ("run", "walk", "sprint")
    if is_time_trial:
        # Time trials are won by a LOWER time. A free-tier domain has no baseline
        # (defender_score == 0): there is no real time to beat, so any positive challenger
        # time wins (§3.1 fix — previously `score <= 0 and score > 0` was always False,
        # making free-tier time-trial domains unconquerable). Paid/seeded tiers keep the
        # genuine "beat the baseline" comparison.
        if defender_score == 0:
            challenger_won = req.challenger_score > 0
        else:
            challenger_won = 0 < req.challenger_score <= defender_score
    else:
        challenger_won = req.challenger_score > defender_score

    crystals_awarded = 0
    new_discount_banked = 0
    xp_gained = 0

    if challenger_won:
        # Debit only the out-of-pocket; the discount portion was subsidized by the system.
        if required_match > 0:
            # NB: target_domain is db.delete()'d below on the win path, so we deliberately
            # do NOT set related_domain_id here (it would dangle); the id lives in the note.
            if out_of_pocket > 0:
                ledger.apply_crystal_delta(
                    db, challenger, -out_of_pocket, "siege_out_of_pocket",
                    related_siege_id=siege.id,
                    note=f"Match staked on siege {siege.id} win (domain {target_domain.id})",
                )
            pot = required_match * 2  # treat as full match vs defender vault
            winner_share = int(pot * (1 - WAR_TAX_PCT))  # 80%
            war_tax_revenue = pot - winner_share          # 20% to platform
            ledger.apply_crystal_delta(
                db, challenger, winner_share, "siege_win_payout",
                related_siege_id=siege.id,
                note=f"80% pot payout on siege {siege.id} win (domain {target_domain.id})",
            )
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
            if out_of_pocket > 0:
                ledger.apply_crystal_delta(
                    db, challenger, -out_of_pocket, "siege_forfeit",
                    related_siege_id=siege.id, related_domain_id=target_domain.id,
                    note=f"Forfeited match on siege {siege.id} loss",
                )
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
        proof=req.challenger_proof,
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


def _enforce_proof_gps_in_polygon(
    proof: Optional[ActivityProof],
    polygon: list,
    context: str,
) -> None:
    """Co-location guard: if the proof carries GPS samples, their centroid must fall
    inside `polygon`. Without this, a verified workout from one city can be attached to
    a Domain in another — the ML referee only checks rhythm, not location.

    Permissive on purpose: an empty GPS channel is treated as 'no check' so legacy clients
    that don't ship GPS yet still work. Once the frontend reliably samples GPS during all
    activities, swap this to require samples for outdoor activity_types.

    `polygon` is a list of {lat, lng} dicts (the JSON shape stored in Domain.geometry_json).
    Raises 400 with a referee-style flag on mismatch."""
    if proof is None or not proof.gps or not polygon:
        return
    avg_lat = sum(s.lat for s in proof.gps) / len(proof.gps)
    avg_lng = sum(s.lng for s in proof.gps) / len(proof.gps)
    if spatial_utils.point_in_polygon(avg_lng, avg_lat, polygon):
        return
    raise HTTPException(
        status_code=400,
        detail=(
            f"ML Referee rejected proof ({context}): GPS centroid "
            f"({avg_lat:.6f}, {avg_lng:.6f}) outside expected polygon."
        ),
    )


def _enforce_proof_gps_in_geofence(
    proof: Optional[ActivityProof],
    center_lat: float,
    center_lng: float,
    radius_m: float,
    context: str,
) -> None:
    """Geofence variant of the co-location guard for circular bounty zones. Same
    permissive contract: empty GPS channel skips the check."""
    if proof is None or not proof.gps or radius_m <= 0:
        return
    avg_lat = sum(s.lat for s in proof.gps) / len(proof.gps)
    avg_lng = sum(s.lng for s in proof.gps) / len(proof.gps)
    dist_km = spatial_utils.haversine_distance(avg_lat, avg_lng, center_lat, center_lng)
    if dist_km * 1000.0 <= radius_m:
        return
    raise HTTPException(
        status_code=400,
        detail=(
            f"ML Referee rejected proof ({context}): GPS centroid "
            f"({avg_lat:.6f}, {avg_lng:.6f}) is {dist_km*1000:.0f}m from geofence "
            f"center (radius {radius_m:.0f}m)."
        ),
    )


@app.post("/api/v1/activities/verify", response_model=VerificationResult)
async def verify_activity_endpoint(proof: ActivityProof, _rl: None = Depends(_rl_verify)):
    """Stateless preview of the ML Referee. The frontend can call this to confirm a workout
    will pass before submitting the real action (claim, siege, bounty). No DB writes.
    Note: the co-location check is NOT applied here — that requires the target polygon /
    geofence which only the calling endpoint knows."""
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


@app.get("/api/v1/merchants/{merchant_id}/bounties", response_model=List[MerchantBountyAnalytics])
async def get_merchant_bounties(
    merchant_id: int,
    token_data: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db),
):
    """Returns every bounty owned by the merchant with completion + coupon-issued counts.
    Powers the merchant portal's analytics view. Auth: merchant must be the owner, or
    caller must be admin."""
    role = token_data["role"]
    caller_id = token_data["id"]
    if role == "merchant" and caller_id != merchant_id:
        raise HTTPException(status_code=403, detail="Merchants can only view their own bounties")
    if role not in ("merchant", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    bounties = (
        db.query(models.Bounty)
        .filter(models.Bounty.merchant_id == merchant_id)
        .order_by(models.Bounty.created_at.desc())
        .all()
    )

    out: List[MerchantBountyAnalytics] = []
    for b in bounties:
        coupon_count = (
            db.query(models.BountyCompletion)
            .filter(
                models.BountyCompletion.bounty_id == b.id,
                models.BountyCompletion.coupon_code_issued.isnot(None),
            )
            .count()
        )
        out.append(MerchantBountyAnalytics(
            id=b.id,
            title=b.title,
            bounty_type=b.bounty_type,
            target_lat=b.target_lat,
            target_lng=b.target_lng,
            is_active=bool(b.is_active),
            completions_count=b.completions_count or 0,
            completions_remaining=max(0, (b.max_completions or 0) - (b.completions_count or 0)),
            coupons_issued=coupon_count,
            xp_reward=b.xp_reward or 0,
            crystal_reward=b.crystal_reward or 0,
            created_at=b.created_at,
            expires_at=b.expires_at,
        ))
    return out


@app.post("/api/v1/merchants/{merchant_id}/payments/intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    merchant_id: int,
    token_data: dict = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    """Initiate the pilot-fee payment via Stripe. Creates a Stripe PaymentIntent for the
    merchant's `pilot_fee_cents` and returns its `client_secret` so the Flutter Stripe SDK can
    confirm the card on-device. Activation does NOT happen here — it happens when Stripe POSTs
    `payment_intent.succeeded` to /payments/stripe/webhook."""
    if token_data["id"] != merchant_id:
        raise HTTPException(status_code=403, detail="Merchants can only pay their own pilot fee")

    merchant = db.query(models.Merchant).filter(models.Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    if merchant.is_active:
        raise HTTPException(status_code=400, detail="Merchant is already active; nothing to pay")

    try:
        intent = stripe_gateway.create_payment_intent(
            amount_cents=merchant.pilot_fee_cents,
            currency=CRYSTAL_PURCHASE_CURRENCY,
            description=f"Osiris merchant pilot fee — merchant {merchant.id}",
            metadata={"kind": "merchant_pilot_fee", "merchant_id": str(merchant.id)},
            idempotency_key=f"merchant_pilot_fee:{merchant.id}",
        )
    except stripe_gateway.StripeNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))

    merchant.payment_provider_id = intent.id
    merchant.payment_status = "payment_pending"
    db.commit()

    return PaymentIntentResponse(
        merchant_id=merchant.id,
        pilot_fee_cents=merchant.pilot_fee_cents,
        provider_payment_id=intent.id,
        payment_status=merchant.payment_status,
        client_secret=intent.client_secret,
        publishable_key=stripe_gateway.STRIPE_PUBLISHABLE_KEY,
        next_action="Confirm the PaymentIntent client_secret with the Stripe SDK in the app.",
    )


@app.post("/api/v1/payments/webhook", response_model=PaymentWebhookResponse)
async def payment_webhook(
    body: bytes = Depends(verify_webhook_signature),
    db: Session = Depends(get_db),
    _rl: None = Depends(_rl_webhook),
):
    """Endpoint the payment provider POSTs to when a payment reaches a terminal state.
    NOT JWT-gated — providers don't carry our JWTs. Signature verification (`X-Provider-
    Signature` HMAC-SHA256 over the raw body) is performed via the `verify_webhook_signature`
    dependency, gated by the `OSIRIS_WEBHOOK_SECRET` env var (off in dev/MVP, on in prod).

    Activation rule: only `payment_status='payment_successful'` flips `is_active=True`
    and writes a PlatformRevenue row. `payment_pending` and `payment_declined` update
    the merchant's status but leave `is_active=False`."""
    try:
        req = PaymentWebhookRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid webhook payload: {e}")

    valid_statuses = {"payment_successful", "payment_pending", "payment_declined"}
    if req.payment_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid payment_status. Expected one of {sorted(valid_statuses)}",
        )

    # Production requires a provider_event_id — real Stripe always sends `event.id`, and
    # without it we can't dedupe retries. Dev / MVP can omit it (no real provider yet).
    if not req.provider_event_id and os.environ.get("OSIRIS_ENV", "").lower() == "production":
        raise HTTPException(
            status_code=400,
            detail="provider_event_id is required in production (needed for retry dedup).",
        )

    # Event-level idempotency: if we've already processed this provider_event_id, return
    # the merchant's current state without re-running side effects (no double revenue, no
    # double activate). Stripe and most providers retry 5xx responses; this guard is what
    # makes the webhook safe to retry.
    if req.provider_event_id:
        prior_event = (
            db.query(models.PaymentWebhookEvent)
            .filter(models.PaymentWebhookEvent.provider_event_id == req.provider_event_id)
            .first()
        )
        if prior_event:
            existing = db.query(models.Merchant).filter(models.Merchant.id == prior_event.merchant_id).first()
            if not existing:
                # Event row points at a merchant that no longer exists — degenerate.
                raise HTTPException(status_code=404, detail="Merchant from prior event not found")
            return PaymentWebhookResponse(
                merchant_id=existing.id,
                payment_status=existing.payment_status,
                is_active=bool(existing.is_active),
                message=(
                    f"Duplicate event {req.provider_event_id} ignored "
                    f"(already processed at {prior_event.received_at.isoformat()})."
                ),
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

    # Record the event AFTER side effects but in the same transaction. The unique index on
    # provider_event_id makes a concurrent duplicate delivery fail at commit time; we catch
    # the IntegrityError and treat it as a replay.
    if req.provider_event_id:
        db.add(models.PaymentWebhookEvent(
            provider_event_id=req.provider_event_id,
            merchant_id=merchant.id,
            payment_status=req.payment_status,
            provider_payment_id=req.provider_payment_id,
            amount_cents=req.amount_cents,
            received_at=_now_naive_utc(),
        ))

    try:
        db.commit()
    except IntegrityError:
        # Concurrent retry beat us to the unique-index insert. Roll back and replay
        # the prior outcome instead.
        db.rollback()
        existing = db.query(models.Merchant).filter(models.Merchant.id == req.merchant_id).first()
        return PaymentWebhookResponse(
            merchant_id=existing.id if existing else req.merchant_id,
            payment_status=existing.payment_status if existing else req.payment_status,
            is_active=bool(existing.is_active) if existing else False,
            message=(
                f"Duplicate event {req.provider_event_id} raced — earlier delivery won."
            ),
        )
    return PaymentWebhookResponse(
        merchant_id=merchant.id,
        payment_status=merchant.payment_status,
        is_active=bool(merchant.is_active),
        message=message,
    )


# --- Phase 3: Stripe-native webhook + shared terminal-state processors ---
#
# Stripe event type -> our internal payment_status vocabulary. Only these are acted on; any
# other event type is acknowledged with 200 and ignored so Stripe stops retrying it.
_STRIPE_EVENT_TO_STATUS = {
    "payment_intent.succeeded": "payment_successful",
    "payment_intent.payment_failed": "payment_declined",
    "payment_intent.processing": "payment_pending",
}


def _apply_merchant_pilot_fee(
    db: Session, *, merchant, payment_status: str, provider_payment_id: str,
    amount_cents: int, occurred_at: datetime,
) -> str:
    """Apply a terminal payment status to a merchant pilot fee. Same activation rule as the
    generic webhook: only 'payment_successful' flips is_active and records revenue (once, on
    the activating transition). Does NOT commit — the caller owns the transaction."""
    merchant.payment_status = payment_status
    merchant.payment_provider_id = provider_payment_id
    if payment_status == "payment_successful":
        already_active = bool(merchant.is_active)
        merchant.is_active = True
        merchant.last_payment_at = occurred_at
        if not already_active and amount_cents > 0:
            db.add(models.PlatformRevenue(
                source="merchant_pilot_fee",
                amount=amount_cents,
                user_id=None,
                note=f"Merchant {merchant.id} pilot fee via {provider_payment_id}",
            ))
        return "Merchant activated. Pilot fee recorded."
    return f"Status updated to {payment_status}; merchant remains inactive."


def _fulfill_crystal_purchase(
    db: Session, *, purchase, payment_status: str, amount_cents: int, occurred_at: datetime,
) -> str:
    """Apply a terminal payment status to a player crystal purchase.

    RED LINE — no double-mint: on success we credit crystals through the ledger EXACTLY ONCE.
    The guard is `purchase.status`: a row already 'succeeded' is a no-op, so a replayed/duplicate
    Stripe event can never credit twice. Does NOT commit — the caller owns the transaction."""
    if payment_status == "payment_successful":
        if purchase.status == "succeeded":
            return "Crystal purchase already fulfilled (no-op)."
        user = db.query(models.User).filter(models.User.id == purchase.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Purchasing user not found")
        entry = ledger.apply_crystal_delta(
            db, user, purchase.crystal_amount, "crystal_purchase",
            note=f"Stripe top-up {purchase.stripe_payment_intent_id} ({purchase.pack_id})",
        )
        db.flush()  # assign entry.id so the purchase can link to its ledger row
        purchase.status = "succeeded"
        purchase.crystal_ledger_id = entry.id
        purchase.fulfilled_at = occurred_at
        if amount_cents > 0:
            db.add(models.PlatformRevenue(
                source="crystal_purchase",
                amount=amount_cents,
                user_id=purchase.user_id,
                note=f"User {purchase.user_id} crystal top-up {purchase.stripe_payment_intent_id}",
            ))
        return f"Credited {purchase.crystal_amount} crystals to user {purchase.user_id}."
    if payment_status == "payment_declined":
        if purchase.status != "succeeded":
            purchase.status = "failed"
        return "Crystal purchase marked failed."
    return f"Crystal purchase status updated to {payment_status}."


@app.post("/api/v1/payments/stripe/webhook", response_model=PaymentWebhookResponse)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    _rl: None = Depends(_rl_webhook),
):
    """Stripe-native webhook. Verifies the `Stripe-Signature` header against the RAW body with
    `stripe.Webhook.construct_event`, then routes `payment_intent.*` events by their metadata
    `kind` to the merchant-pilot-fee or crystal-purchase processor.

    Event-level idempotency: PaymentWebhookEvent keyed on the Stripe `event.id` (unique index)
    makes retried deliveries no-ops. Purchase-level idempotency (no double-mint) is enforced
    separately by `_fulfill_crystal_purchase`."""
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe_gateway.construct_event(payload, sig_header)
    except stripe_gateway.StripeNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")
    except Exception:
        # stripe.error.SignatureVerificationError (and any other verification failure).
        raise HTTPException(status_code=401, detail="Invalid Stripe signature")

    event_id = event["id"]
    event_type = event["type"]

    payment_status = _STRIPE_EVENT_TO_STATUS.get(event_type)
    if payment_status is None:
        return PaymentWebhookResponse(
            merchant_id=0, payment_status="ignored", is_active=False,
            message=f"Event type {event_type} acknowledged; no action taken.",
        )

    # Event-level dedup: if we've seen this Stripe event.id, replay nothing.
    prior = (
        db.query(models.PaymentWebhookEvent)
        .filter(models.PaymentWebhookEvent.provider_event_id == event_id)
        .first()
    )
    if prior:
        return PaymentWebhookResponse(
            merchant_id=prior.merchant_id or 0,
            payment_status=prior.payment_status or payment_status,
            is_active=False,
            message=f"Duplicate event {event_id} ignored (already processed).",
        )

    intent = event["data"]["object"]
    pi_id = intent["id"]
    amount_cents = intent.get("amount") or 0
    metadata = intent.get("metadata") or {}
    kind = metadata.get("kind")
    occurred_at = _now_naive_utc()

    merchant_id_for_event: Optional[int] = None
    user_id_for_event: Optional[int] = None

    if kind == "merchant_pilot_fee":
        merchant = (
            db.query(models.Merchant)
            .filter(models.Merchant.id == int(metadata["merchant_id"]))
            .first()
        )
        if not merchant:
            raise HTTPException(status_code=404, detail="Merchant not found")
        merchant_id_for_event = merchant.id
        message = _apply_merchant_pilot_fee(
            db, merchant=merchant, payment_status=payment_status,
            provider_payment_id=pi_id, amount_cents=amount_cents, occurred_at=occurred_at,
        )
        resp_merchant_id, resp_status, resp_active = (
            merchant.id, merchant.payment_status, bool(merchant.is_active),
        )
    elif kind == "crystal_purchase":
        purchase = (
            db.query(models.CrystalPurchase)
            .filter(models.CrystalPurchase.stripe_payment_intent_id == pi_id)
            .first()
        )
        if not purchase:
            raise HTTPException(status_code=404, detail="Crystal purchase not found")
        user_id_for_event = purchase.user_id
        message = _fulfill_crystal_purchase(
            db, purchase=purchase, payment_status=payment_status,
            amount_cents=amount_cents, occurred_at=occurred_at,
        )
        resp_merchant_id, resp_status, resp_active = (
            0, purchase.status, purchase.status == "succeeded",
        )
    else:
        return PaymentWebhookResponse(
            merchant_id=0, payment_status="ignored", is_active=False,
            message=f"Event {event_id} metadata.kind={kind!r} is unknown; ignored.",
        )

    # Record the event AFTER side effects, same transaction. The unique index on
    # provider_event_id turns a concurrent duplicate delivery into an IntegrityError at commit.
    db.add(models.PaymentWebhookEvent(
        provider_event_id=event_id,
        merchant_id=merchant_id_for_event,
        user_id=user_id_for_event,
        event_type=event_type,
        payment_status=payment_status,
        provider_payment_id=pi_id,
        amount_cents=amount_cents,
        received_at=_now_naive_utc(),
    ))

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return PaymentWebhookResponse(
            merchant_id=merchant_id_for_event or 0,
            payment_status=payment_status,
            is_active=False,
            message=f"Duplicate event {event_id} raced — earlier delivery won.",
        )

    return PaymentWebhookResponse(
        merchant_id=resp_merchant_id, payment_status=resp_status,
        is_active=resp_active, message=message,
    )


# --- Phase 3: player crystal top-up (one-way purchase) endpoints ---

@app.get("/api/v1/payments/crystals/packs", response_model=List[CrystalPackInfo])
async def list_crystal_packs():
    """Buyable crystal packs with server-authoritative pricing. The client renders these and
    sends back only a `pack_id`; it never sets a price."""
    return [
        CrystalPackInfo(
            pack_id=pid, label=p["label"], crystals=p["crystals"],
            amount_cents=p["amount_cents"], currency=CRYSTAL_PURCHASE_CURRENCY,
        )
        for pid, p in CRYSTAL_PACKS.items()
    ]


@app.post("/api/v1/payments/crystals/intent", response_model=CrystalPurchaseIntentResponse)
async def create_crystal_purchase_intent(
    req: CrystalPurchaseIntentRequest,
    token_data: dict = Depends(get_current_player),
    db: Session = Depends(get_db),
):
    """Start a real-money crystal top-up. The price and crystal grant come from CRYSTAL_PACKS
    on the server — the client only chooses a `pack_id`. Creates a Stripe PaymentIntent and a
    'pending' CrystalPurchase; crystals are credited later by the webhook on success."""
    pack = CRYSTAL_PACKS.get(req.pack_id)
    if not pack:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown pack_id {req.pack_id!r}. Valid packs: {sorted(CRYSTAL_PACKS)}",
        )

    user_id = token_data["id"]
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        intent = stripe_gateway.create_payment_intent(
            amount_cents=pack["amount_cents"],
            currency=CRYSTAL_PURCHASE_CURRENCY,
            description=f"Osiris crystal top-up — {pack['label']} for user {user_id}",
            metadata={
                "kind": "crystal_purchase",
                "user_id": str(user_id),
                "pack_id": req.pack_id,
                "crystal_amount": str(pack["crystals"]),
            },
        )
    except stripe_gateway.StripeNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))

    purchase = models.CrystalPurchase(
        user_id=user_id,
        pack_id=req.pack_id,
        crystal_amount=pack["crystals"],
        amount_cents=pack["amount_cents"],
        currency=CRYSTAL_PURCHASE_CURRENCY,
        stripe_payment_intent_id=intent.id,
        status="pending",
    )
    db.add(purchase)
    db.commit()
    db.refresh(purchase)

    return CrystalPurchaseIntentResponse(
        purchase_id=purchase.id,
        pack_id=req.pack_id,
        crystal_amount=pack["crystals"],
        amount_cents=pack["amount_cents"],
        currency=CRYSTAL_PURCHASE_CURRENCY,
        payment_intent_id=intent.id,
        client_secret=intent.client_secret,
        publishable_key=stripe_gateway.STRIPE_PUBLISHABLE_KEY,
        status=purchase.status,
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
    """Seed a bounty. Admins can create both 'daily' (system-issued) and 'merchant_chest'
    (any merchant). Merchants can only create 'merchant_chest' bounties keyed to their own
    merchant_id. Geofence radius is in metres; distance to caller is filled with 0 since
    the creator may not be on-site."""
    role = token_data["role"]
    # v2.10 RBAC tightening: merchants can only create their own merchant_chest bounties.
    if role == "merchant":
        if bounty.bounty_type != "merchant_chest":
            raise HTTPException(status_code=403, detail="Merchants can only create merchant_chest bounties")
        if token_data["id"] != bounty.merchant_id:
            raise HTTPException(status_code=403, detail="Merchant can only create bounties keyed to their own merchant_id")
    # Daily bounties are admin-only; this also lets admins seed merchant_chest bounties for any merchant.
    if bounty.bounty_type == "daily" and role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create daily bounties")

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
    # Co-location: GPS samples in the proof must land inside the bounty's geofence —
    # mirrors the proximity check we already do on req.user_lat/lng but against the
    # workout's own GPS trace rather than the moment-of-submission position.
    _enforce_proof_gps_in_geofence(
        req.score_proof,
        center_lat=bounty.target_lat,
        center_lng=bounty.target_lng,
        radius_m=bounty.radius_m or 0,
        context="bounty_complete",
    )
    # Replay-attack guard
    _consume_proof_or_409(db, user.id, req.score_proof, source="bounty_complete")

    # Score gate — bounties with target_score=0 are proximity-only (e.g., merchant chests).
    if bounty.target_score > 0 and req.score < bounty.target_score:
        raise HTTPException(status_code=400, detail=f"Score {req.score} did not meet target {bounty.target_score}")

    # Award rewards
    device_ts = _to_naive_utc(req.device_timestamp)
    user.xp += bounty.xp_reward
    if bounty.crystal_reward:
        ledger.apply_crystal_delta(
            db, user, bounty.crystal_reward, "bounty_reward",
            related_bounty_id=bounty.id,
            note=f"Reward for bounty {bounty.id}",
        )
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
        proof=req.score_proof,
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


def _load_coupon_for_merchant(
    db: Session,
    code: str,
    token_data: dict,
) -> tuple[models.BountyCompletion, models.Bounty]:
    """Shared lookup + authz for the coupon endpoints. Returns the completion row and its
    bounty, or raises:
      - 404 if the code doesn't exist
      - 403 if a merchant calls about another merchant's bounty
      - 403 if any non-{merchant,admin} role calls"""
    role = token_data["role"]
    if role not in ("merchant", "admin"):
        raise HTTPException(status_code=403, detail="Coupon redemption is merchant-only")

    completion = (
        db.query(models.BountyCompletion)
        .filter(models.BountyCompletion.coupon_code_issued == code)
        .first()
    )
    if not completion:
        raise HTTPException(status_code=404, detail="Coupon not found")

    bounty = db.query(models.Bounty).filter(models.Bounty.id == completion.bounty_id).first()
    if not bounty:
        # Bounty was deleted but completion lingered — degenerate state, treat as not found.
        raise HTTPException(status_code=404, detail="Bounty for this coupon no longer exists")

    if role == "merchant" and bounty.merchant_id != token_data["id"]:
        raise HTTPException(status_code=403, detail="This coupon belongs to a different merchant")

    return completion, bounty


@app.get("/api/v1/coupons/{code}", response_model=CouponLookupResponse)
async def lookup_coupon(
    code: str,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_user_token),
):
    """Pre-redemption check. Use this to validate a code shown at the till before tapping
    the redeem button — surfaces 'already redeemed' and 'wrong merchant' before a write."""
    completion, bounty = _load_coupon_for_merchant(db, code, token_data)
    return CouponLookupResponse(
        coupon_code=code,
        bounty_id=bounty.id,
        bounty_title=bounty.title,
        merchant_id=bounty.merchant_id or 0,
        customer_user_id=completion.user_id,
        coupon_text=bounty.coupon_text,
        issued_at=completion.completed_at,
        redeemed_at=completion.coupon_redeemed_at,
        redeemed_by_merchant_id=completion.coupon_redeemed_by_merchant_id,
        is_redeemed=completion.coupon_redeemed_at is not None,
    )


@app.post("/api/v1/coupons/{code}/redeem", response_model=CouponRedeemResponse)
async def redeem_coupon(
    code: str,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_user_token),
):
    """Stamps a coupon as redeemed at the till. RBAC: only the merchant who owns the
    bounty (or an admin) can redeem; a re-redeem returns 409 so the customer can't
    re-use the code at another visit."""
    completion, bounty = _load_coupon_for_merchant(db, code, token_data)

    if completion.coupon_redeemed_at is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Coupon already redeemed at {completion.coupon_redeemed_at.isoformat()} "
                f"by merchant {completion.coupon_redeemed_by_merchant_id}"
            ),
        )

    # Admin redemptions stamp the bounty's owning merchant (so the audit trail follows the
    # storefront, not the admin). Merchant redemptions stamp themselves.
    redeeming_merchant_id = token_data["id"] if token_data["role"] == "merchant" else (bounty.merchant_id or 0)
    redeemed_at = _now_naive_utc()
    completion.coupon_redeemed_at = redeemed_at
    completion.coupon_redeemed_by_merchant_id = redeeming_merchant_id
    db.commit()

    return CouponRedeemResponse(
        coupon_code=code,
        bounty_id=bounty.id,
        customer_user_id=completion.user_id,
        redeemed_at=redeemed_at,
        message=f"Coupon redeemed for bounty '{bounty.title}'.",
    )


# NOTE (v2.10): a previous duplicate `/api/v1/merchants/{id}/bounties` endpoint was removed
# here. The canonical implementation now lives near the merchant-profile endpoint and uses
# `MerchantBountyAnalytics` (richer payload: completions_count + coupons_issued; admins
# can also call it).

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


def process_telemetry_ttl():
    """v2.11 nightly job — deletes raw `TelemetryData` sample blobs older than the TTL.
    `TelemetrySession` metadata stays so analytics queries against
    'how many workouts per activity_type per week' still work indefinitely; only the
    expensive raw samples expire.

    Default TTL: 90 days. Override with `OSIRIS_TELEMETRY_TTL_DAYS=<N>`. Set to 0 or
    negative to disable the job entirely (no expiry — useful for low-volume pilots that
    want to keep all raw data for ML training)."""
    ttl_days = int(os.environ.get("OSIRIS_TELEMETRY_TTL_DAYS", "90"))
    if ttl_days <= 0:
        return  # disabled
    cutoff = _now_naive_utc() - timedelta(days=ttl_days)
    db = database.SessionLocal()
    try:
        # Find session ids whose creation predates the cutoff. Joining via session_id keeps
        # the delete cheap on SQLite (a single IN-list).
        old_session_ids = [
            row.id for row in
            db.query(models.TelemetrySession.id).filter(models.TelemetrySession.created_at < cutoff).all()
        ]
        if old_session_ids:
            deleted = (
                db.query(models.TelemetryData)
                .filter(models.TelemetryData.session_id.in_(old_session_ids))
                .delete(synchronize_session=False)
            )
            db.commit()
            print(f"[telemetry-ttl] purged {deleted} TelemetryData rows older than {ttl_days} days "
                  f"(across {len(old_session_ids)} sessions; metadata retained).")
    finally:
        db.close()

# Scheduler + lifespan handler are now defined near the top of the module so FastAPI() can
# accept lifespan= at construction time. See the @asynccontextmanager above.
