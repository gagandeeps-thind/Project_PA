"""Operational endpoints: root, favicon, health probe and Prometheus metrics."""
import functools
import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

import database
import settings
from core.security import _IS_DEV_ENV
from services import metrics

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Phase 0: liveness/readiness probe ----------------------------------------
# include_in_schema=False keeps it out of the client OpenAPI contract (ops-only route).
@router.get("/metrics", include_in_schema=False)
def prometheus_metrics(request: Request):
    """Prometheus scrape endpoint. Requires `Authorization: Bearer $OSIRIS_METRICS_TOKEN`.
    Without a configured token it is served only in dev/test and is a 404 elsewhere, so a
    deploy never exposes traffic patterns by accident."""
    from fastapi.responses import PlainTextResponse

    expected = settings.secret("OSIRIS_METRICS_TOKEN")
    if expected:
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, f"Bearer {expected}"):
            raise HTTPException(status_code=401, detail="Invalid metrics token")
    elif not _IS_DEV_ENV:
        raise HTTPException(status_code=404, detail="Not Found")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")


@router.get("/healthz", include_in_schema=False)
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


@functools.lru_cache(maxsize=1)
def _alembic_head_revision() -> Optional[str]:
    """Latest revision id from the local alembic/versions scripts, or None if unavailable.

    Cached: the migration scripts shipped with this process cannot change while it runs, and
    parsing every script on each probe made /healthz the slowest endpoint under load."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = Config(os.path.join(backend_dir, "alembic.ini"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:
        return None


# A simple root endpoint to verify the server is running
@router.get("/")
def root():
    return {
        "message": "Verified Fitness Reward System API is running",
        "docs": "/docs"
    }


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return {}
