"""Logging: optional JSON log lines (OSIRIS_LOG_JSON=1) and the per-request access log with a request id."""
import contextvars
import json
import logging
import os
import secrets
import time as _time
from datetime import datetime, timezone

from fastapi import Request

from services import metrics

# --- Phase 0: structured JSON logging skeleton ---------------------------------
# Emits one JSON line per request (request id, user id, route, method, status, latency).
# Opt-in via OSIRIS_LOG_JSON=1 so local dev keeps human-readable logs by default; CI and
# any container set the env var. This is a *skeleton* — fields can grow; format stays JSON.

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

# Access lines keep the logger name they always had, so log queries on `logger=main` still match.
access_logger = logging.getLogger("main")


# --- Phase 0: per-request structured access log + request id -------------------
async def access_log_middleware(request: Request, call_next):
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
        elapsed = _time.perf_counter() - start
        latency_ms = round(elapsed * 1000, 2)
        # Label by route template, never the raw path, so series count stays bounded and no
        # ids or query strings reach the metrics store. Unmatched paths (404s) share one label.
        matched = request.scope.get("route")
        metrics.observe_request(request.method, getattr(matched, "path", None) or "unmatched", status_code, elapsed)
        # user id is best-effort: auth dependencies may set request.state.user_id.
        user_id = getattr(request.state, "user_id", None)
        access_logger.info(
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

