"""Per-player-IP rate limits, exposed as FastAPI dependencies. Off in dev/test.

Counts are shared across API instances through Upstash Redis when `UPSTASH_REDIS_REST_URL` and
`UPSTASH_REDIS_REST_TOKEN` are set, so a limit of 10 a minute stays 10 with three instances.
Without them, or when Upstash does not answer within half a second, each process counts on its
own: limits keep working (per process) instead of failing every request.

The key is the player's IP. Behind Cloudflare with the origin lock on (`OSIRIS_ORIGIN_SECRET`),
every request passed Cloudflare, which overwrites `CF-Connecting-IP`, so that header is trusted.
Without the lock the socket peer is used; behind a platform proxy (Render) that is the proxy,
which puts every player in one bucket, so production must run with the lock on.
"""
import json
import logging
import threading as _threading
import time as _time
import urllib.request
import uuid

from fastapi import HTTPException, Request

import settings

logger = logging.getLogger(__name__)

_IS_DEV_ENV = settings.is_dev_env()
TRUST_CF_CONNECTING_IP = bool(settings.secret("OSIRIS_ORIGIN_SECRET"))
UPSTASH_URL = (settings.secret("UPSTASH_REDIS_REST_URL") or "").rstrip("/") or None
UPSTASH_TOKEN = settings.secret("UPSTASH_REDIS_REST_TOKEN")
UPSTASH_TIMEOUT_S = 0.5
_WARN_EVERY_S = 60.0

_rate_buckets: "dict[str, list[float]]" = {}
_rate_lock = _threading.Lock()
_last_warning = 0.0


def client_ip(request: Request) -> str:
    """The player's IP, as described in the module docstring."""
    if TRUST_CF_CONNECTING_IP:
        forwarded = request.headers.get("cf-connecting-ip", "").strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def _local_hit(key: str, max_requests: int, window_s: int) -> bool:
    """Sliding window in this process. True when the request is within the limit."""
    now = _time.monotonic()
    cutoff = now - window_s
    with _rate_lock:
        bucket = _rate_buckets.setdefault(key, [])
        i = 0
        for ts in bucket:  # timestamps are in order; drop those outside the window
            if ts >= cutoff:
                break
            i += 1
        if i:
            del bucket[:i]
        if len(bucket) >= max_requests:
            return False
        bucket.append(now)
        return True


def _shared_hit(key: str, max_requests: int, window_s: int) -> bool | None:
    """Sliding window in Upstash (one sorted set per key, one atomic MULTI/EXEC round trip).
    True/False as `_local_hit`; None when Upstash is not configured or did not answer.
    A refused request is counted too, so a client that keeps hammering stays blocked."""
    if not (UPSTASH_URL and UPSTASH_TOKEN):
        return None
    now_ms = int(_time.time() * 1000)
    window_ms = window_s * 1000
    redis_key = f"osiris:rl:{key}"
    commands = [
        ["ZREMRANGEBYSCORE", redis_key, "0", str(now_ms - window_ms)],
        ["ZADD", redis_key, str(now_ms), f"{now_ms}-{uuid.uuid4().hex[:8]}"],
        ["ZCARD", redis_key],
        ["PEXPIRE", redis_key, str(window_ms)],
    ]
    req = urllib.request.Request(
        f"{UPSTASH_URL}/multi-exec",
        data=json.dumps(commands).encode(),
        headers={"Authorization": f"Bearer {UPSTASH_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=UPSTASH_TIMEOUT_S) as resp:
            results = json.loads(resp.read())
        return int(results[2]["result"]) <= max_requests
    except Exception as exc:  # network, timeout, auth or shape: degrade to per-process counting
        global _last_warning
        now = _time.monotonic()
        if now - _last_warning > _WARN_EVERY_S:
            _last_warning = now
            logger.warning("Upstash rate limiter unavailable, counting per process",
                           extra={"ctx": {"error": type(exc).__name__}})
        return None


def _rate_limit(max_requests: int, window_s: int, scope: str):
    """Returns a FastAPI dependency that raises 429 when an IP exceeds `max_requests` in
    `window_s` seconds for the given `scope`."""
    def _dep(request: Request) -> None:
        if _IS_DEV_ENV:
            return  # no throttling in dev/test
        key = f"{scope}:{client_ip(request)}"
        allowed = _shared_hit(key, max_requests, window_s)
        if allowed is None:
            allowed = _local_hit(key, max_requests, window_s)
        if not allowed:
            raise HTTPException(status_code=429, detail="Too many requests. Slow down.")
    return _dep


# Prod defaults; tuned for the Bedford pilot. Auth + payment + proof endpoints are the
# brute-force / spam / CPU-burn (triple-bcrypt) targets named in the audit.
_rl_login = _rate_limit(10, 60, "login")
_rl_onboard = _rate_limit(5, 60, "onboard")
_rl_verify = _rate_limit(30, 60, "verify")
_rl_webhook = _rate_limit(60, 60, "webhook")
# Security §2: route upload, challenge join/submit, and publish are abuse targets too.
_rl_route = _rate_limit(120, 60, "route")
_rl_challenge = _rate_limit(30, 60, "challenge")
# Public analytics ingestion accepts unauthenticated writes; cap it per IP.
_rl_events = _rate_limit(60, 60, "events")
