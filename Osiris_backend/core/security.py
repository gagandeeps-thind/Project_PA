"""Authentication and authorisation: JWT issue/verify, role dependencies, password hashing,
webhook signatures, and the fail-closed boot checks for secrets."""
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import AfterValidator, Field
from sqlalchemy.orm import Session

import models
import settings
from core.errors import _api_error
from database import get_db
from services import stripe_gateway

logger = logging.getLogger(__name__)


# --- v2.10: JWT secret loaded from env var with a clearly-flagged dev fallback ---
# Set OSIRIS_JWT_SECRET in any non-dev environment. Deployment must use a 32+ byte secret
# (HS256 minimum per RFC 7518 § 3.2). Setting OSIRIS_ENV=production makes a missing secret
# fatal at boot — that's the production-safety check.
_jwt_secret_from_env = settings.secret("OSIRIS_JWT_SECRET")
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
    logger.warning(
        "OSIRIS_JWT_SECRET not set — using an ephemeral dev secret. "
        "Tokens will not survive a server restart."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

def create_access_token(data: dict):
    to_encode = data.copy()
    issued = datetime.now(timezone.utc)
    expire = issued + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # iat lets the v2 API refuse tokens issued before a "sign out everywhere" (G4).
    to_encode.update({"exp": expire, "iat": int(issued.timestamp())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        role: str = payload.get("role")
        user_id_str: str = payload.get("sub")
        if role is None or user_id_str is None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        return {"id": int(user_id_str), "role": role, "iat": payload.get("iat")}
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
# Security baseline: FAIL CLOSED. The webhook secret is REQUIRED unless OSIRIS_ENV is an
# *explicit* dev/test value. A forgotten or unknown OSIRIS_ENV is treated as production and
# must refuse to boot — the old behavior (fail open whenever the secret was unset, only
# fail-fast when OSIRIS_ENV was *explicitly* "production") meant a deploy that forgot the env
# var served a wide-open, forgeable payment webhook. Inverted here.
_DEV_ENVS = settings.DEV_ENVS
_IS_DEV_ENV = settings.is_dev_env()
_WEBHOOK_SECRET = settings.secret("OSIRIS_WEBHOOK_SECRET")
if not _WEBHOOK_SECRET and not _IS_DEV_ENV:
    raise RuntimeError(
        "OSIRIS_WEBHOOK_SECRET is required unless OSIRIS_ENV is one of "
        f"{sorted(_DEV_ENVS)}. An unset or unknown OSIRIS_ENV is treated as production: "
        "the app refuses to boot rather than serve an unauthenticated, forgeable payment "
        "webhook. For local development set OSIRIS_ENV=dev. "
        "Generate a secret with `python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
        "and configure the same value on the payment provider's webhook settings."
    )

# Stripe fail-closed boot check. Called here, AFTER the webhook-secret
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



# bcrypt only reads the first 72 bytes and, from bcrypt 4.1, raises on longer input.
BCRYPT_MAX_BYTES = 72


def get_password_hash(password: str) -> str:
    """Takes a plain text password and returns a securely hashed version using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Checks if a plain text password matches the hashed version stored in the database.
    Input is cut to bcrypt's 72 bytes, which is what older bcrypt releases hashed, so a longer
    attempt is a wrong password instead of a server error."""
    return bcrypt.checkpw(plain_password.encode('utf-8')[:BCRYPT_MAX_BYTES], hashed_password.encode('utf-8'))


def _fits_bcrypt(password: str) -> str:
    if len(password.encode('utf-8')) > BCRYPT_MAX_BYTES:
        raise ValueError("Password is too long: at most 72 characters, fewer with accents or emoji")
    return password


# A new password: 72 characters, and at most 72 bytes once encoded, so bcrypt can hash it.
NewPassword = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(_fits_bcrypt)]


def _require_active_player(token_data: dict, db: Session) -> dict:
    """The PRD-010 checks: the player exists, is not suspended, and the token predates no sign-out."""
    user = db.query(models.User).filter(models.User.id == token_data["id"]).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    if user.suspended_at is not None:
        raise _api_error(403, "ACCOUNT_SUSPENDED", "This account is suspended. Contact support.")
    if user.tokens_valid_after is not None:
        issued_at = token_data.get("iat") or 0
        if issued_at < int(user.tokens_valid_after.replace(tzinfo=timezone.utc).timestamp()):
            raise _api_error(401, "SESSION_REVOKED", "This session was signed out. Please sign in again.")
    return token_data


def get_active_player(
    token_data: dict = Depends(get_current_player),
    db: Session = Depends(get_db),
) -> dict:
    """Player auth plus the PRD-010 suspension check. Every v2 player endpoint uses this, so
    an admin suspension takes effect on the player's next request without revoking tokens."""
    return _require_active_player(token_data, db)


def get_active_player_or_admin(
    token_data: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db),
) -> dict:
    """Read endpoints the admin console shares with the app: admins pass, players get the
    suspension check, other roles get 403."""
    if token_data["role"] == "admin":
        return token_data
    if token_data["role"] != "player":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return _require_active_player(token_data, db)
