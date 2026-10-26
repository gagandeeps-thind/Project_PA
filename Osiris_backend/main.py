"""Osiris API entry point: builds the FastAPI app, installs middleware and mounts the routers.

Layout (see docs/architecture/backend.md):
  core/       cross-cutting plumbing: logging, auth and RBAC, rate limits, clock, error shapes
  routers/    HTTP endpoints of the original API, one module per area
  growth_*.py, exercise_api.py   growth-release routers (G1-G4, exercises)
  services/   domain logic with no HTTP: ledger, challenges, quests, progression, jobs, ...
  schemas.py  request/response models of the routers; models.py holds the database tables

Run with `uvicorn main:app`. Route order matters (a literal path such as
`/challenges/nearby` must be registered before `/challenges/{id}`), so routers are mounted in
the fixed order below.
"""
from contextlib import asynccontextmanager
import os

# Load a local .env (gitignored) into os.environ before any module reads config. Real env vars
# win (override=False), so the shell, CI and the platform always take precedence.
from dotenv import load_dotenv

load_dotenv(override=False)

from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402

from core import logging_setup  # noqa: E402  (configures logging before anything logs)
from core.origin_guard import OriginGuardMiddleware  # noqa: E402
import core.security  # noqa: E402,F401  (fail-closed secret checks run at import)
import database  # noqa: E402
import exercise_api  # noqa: E402
import growth_api  # noqa: E402
import growth_communities  # noqa: E402
import growth_hub  # noqa: E402
import growth_safety  # noqa: E402
import growth_social  # noqa: E402
import growth_support  # noqa: E402
from http_cache import ConditionalGetMiddleware  # noqa: E402
import models  # noqa: E402
from routers import (  # noqa: E402
    accounts, admin_trust, bounties, challenges, legacy_game, merchants, payments, runs, system,
)
import settings  # noqa: E402
from services import jobs  # noqa: E402

# Creates missing tables so a fresh dev database works without an extra step. Alembic stays the
# schema source of truth: create_all never alters an existing table, so every model change
# still needs a migration (`alembic upgrade head`).
models.Base.metadata.create_all(bind=database.engine)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Starts the background jobs with the server and stops them on shutdown.
    OSIRIS_RUN_SCHEDULER=0 serves requests without the jobs (extra replicas behind a balancer)."""
    if not settings.run_scheduler():
        yield
        return
    scheduler.add_job(jobs.process_daily_decay, "interval", hours=24)
    scheduler.add_job(jobs.process_telemetry_ttl, "interval", hours=24)
    scheduler.add_job(jobs.process_challenge_settlement, "interval", hours=1)
    scheduler.add_job(jobs.process_route_point_ttl, "interval", hours=24)
    scheduler.add_job(database.optimize, "interval", hours=24)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(title="Verified Fitness Reward System API", version="1.0-MVP", lifespan=lifespan)

# Explicit CORS allowlist (a wildcard origin with credentials is invalid and unsafe). Origins come
# from OSIRIS_CORS_ORIGINS; native apps are not subject to browser CORS and need no entry.
_default_cors = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
_cors_origins = [o.strip() for o in os.environ.get("OSIRIS_CORS_ORIGINS", _default_cors).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Both sit inside the access log, so a 304 is logged as a 304. GZip wraps the ETag layer, so the tag
# hashes the plain body; it must also sit inside the access log, whose call_next re-chunks the body
# and would defeat the small-body threshold. Small bodies are not worth the CPU.
app.add_middleware(ConditionalGetMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
# Outside CORS, so a request that skipped the CDN is refused before anything else runs; inside the
# access log, so those refusals are still logged.
app.add_middleware(OriginGuardMiddleware)
app.middleware("http")(logging_setup.access_log_middleware)

for _router in (
    system.router,
    accounts.router,
    runs.router,
    challenges.router,
    admin_trust.router,
    legacy_game.router,
    merchants.router,
    payments.router,
    bounties.router,
    growth_api.router,
    growth_social.router,
    growth_safety.router,
    growth_communities.router,
    exercise_api.router,
    growth_hub.router,
    growth_support.router,
):
    app.include_router(_router)
