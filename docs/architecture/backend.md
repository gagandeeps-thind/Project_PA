# Backend architecture (FastAPI)

One API serves the Android and iOS apps and the admin console. It is a FastAPI app on SQLAlchemy 2.0,
SQLite in development, and PostgreSQL before SIT (ADR-002). Alembic owns the schema.

```
Osiris_backend/
  main.py            app assembly only: middleware, background scheduler, router mounting
  core/              cross-cutting plumbing, no endpoints
    security.py        JWT issue/verify, role dependencies (player/admin/merchant), get_active_player
                       (suspension and sign-out-everywhere), bcrypt, webhook HMAC, fail-closed secret checks
    rate_limit.py      in-memory per-IP limits as dependencies (off in dev/test)
    logging_setup.py   JSON logs (OSIRIS_LOG_JSON=1), access log with X-Request-ID, route metrics
    clock.py           naive-UTC "now" (SQLite has no time zones)
    errors.py          v2 error shape {code, message}
  routers/           original v1/v2 API, one module per area
    system.py          /, /healthz, /metrics
    accounts.py        v1 sign-up, login, profile, export, erasure
    runs.py            v2 run sessions and route upload
    challenges.py      v2 courses, challenges, attempts, progression
    admin_trust.py     v2 admin review queue, moderation, suspensions, audit log
    legacy_game.py     v1 domains, vaults, sieges, party roles, proof preview
    merchants.py       merchants, admin merchant management, platform revenue
    payments.py        payment intents, provider webhooks, crystal top-ups (money path)
    bounties.py        bounty board, coupons
  growth_api.py      growth release routers (G1-G4) and exercise sets; each keeps its own models
  growth_social.py, growth_safety.py, growth_communities.py, growth_hub.py, growth_support.py, exercise_api.py
  schemas.py         Pydantic request/response models of routers/
  services/          domain logic without HTTP
    ledger.py          the only writer of User.mana_crystals
    progression.py     rank, title, XP, badges, attribute stats, activity log
    challenge_store.py challenge status, settlement, batched read models
    proofs.py          ML Referee proof checks and replay protection
    jobs.py            scheduled jobs: XP decay, telemetry and route-point retention, settlement
    challenges.py, quests.py, leaderboards.py, exercises.py   pure rules
    stripe_gateway.py, metrics.py, ttl_cache.py, player_safety.py
  models.py          database tables
  database.py        engine, pool settings, SQLite pragmas, get_db
  settings.py        configuration; secrets via settings.secret("NAME") or NAME_FILE
  alembic/           migrations (human-reviewed)
  tests/             standalone suites, one per release or feature
```

## Rules

- **Dependencies point down.** Routers use `core/`, `schemas`, `services/` and `models`. Services never
  import routers. `core/` never imports routers and uses only leaf services (`metrics`, `stripe_gateway`). The growth modules import from the same places, never from `main`.
- **One router per area.** A new endpoint goes into the router of its area, its models into `schemas.py`
  (or next to a growth router), and its logic into `services/` when a job or another router needs it too.
- **Route order matters.** FastAPI matches in registration order, so `/challenges/nearby` must be
  mounted before `/challenges/{id}`. `main.py` mounts routers in a fixed order; keep literal paths before
  parameterised ones inside a router.
- **The endpoint owns the transaction.** Services add and flush; the endpoint commits.
  `services.ledger.apply_crystal_delta` is the only way to move crystals.
- **Errors.** Raise `HTTPException`; v2 endpoints use `core.errors._api_error(status, CODE, message)` so
  clients can branch on `detail.code`.
- **Contract.** `Documentation/openapi.json` is the committed API contract; regenerate it with
  `python scripts/check_openapi_drift.py --write` after any API change.

## Cycles that remain

Four call sites reach back into the growth release: run acceptance grants quest XP, joining and completing
a challenge emit funnel events. `growth_api` imports `services.challenge_store`, so those call sites
import `growth_api` inside the function. Moving `emit_event` and `on_run_accepted` into a service
removes the last of them.

## Performance features

Gzip for bodies of 1 KB and more, weak ETags with `304 Not Modified`, a 60 s cache per global
leaderboard, fixed query counts on list endpoints (asserted in `tests/test_growth_hub.py`),
`limit`/`offset` paging, a PostgreSQL connection pool (`OSIRIS_DB_POOL_*`), SQLite WAL and planner
statistics. Measurements: `Documentation/Enterprise/17_Performance_Pass_and_Audit_2026-10-19.md`.
