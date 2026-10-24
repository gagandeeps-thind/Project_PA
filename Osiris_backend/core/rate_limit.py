"""In-memory per-IP rate limits, exposed as FastAPI dependencies. Off in dev/test."""
import threading as _threading
import time as _time

from fastapi import HTTPException, Request

import settings

# Dependency-free, in-memory sliding-window limiter keyed on client IP + scope. Sufficient for
# the single-VM pilot; at horizontal scale this must move to a shared store (Redis) because the
# buckets are per-process. Disabled in dev/test (OSIRIS_ENV dev/test) so the suites and local
# work aren't throttled — it protects the real deployment, where OSIRIS_ENV is prod-like.
_IS_DEV_ENV = settings.is_dev_env()

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
# Security §2: route upload, challenge join/submit, and publish are abuse targets too.
_rl_route = _rate_limit(120, 60, "route")
_rl_challenge = _rate_limit(30, 60, "challenge")
# Public analytics ingestion accepts unauthenticated writes; cap it per IP.
_rl_events = _rate_limit(60, 60, "events")
