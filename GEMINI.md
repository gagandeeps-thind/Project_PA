# Osiris — agent guide

## Project overview
Osiris is a location-based fitness RPG. Players complete GPS-verified runs, quests, courses,
challenges and community rankings in a Kotlin Multiplatform app (Android + iOS), backed by a FastAPI + SQLAlchemy API on SQLite
(Alembic migrations) with a Mana Crystal ledger and Stripe top-ups. An admin web console (Vite +
React + TS) handles trust/moderation and growth. Product and architecture docs: `Documentation/Enterprise/`.

## Commands
Python commands run from `Osiris_backend/` using the repo venv (`../.venv/Scripts/python.exe` on Windows).
CI (`.github/workflows/ci.yml`) exports `OSIRIS_JWT_SECRET=ci-fixed-secret-not-for-production-use-only OSIRIS_ENV=test OSIRIS_LOG_JSON=1`.

| Purpose | Command | Dir |
|---|---|---|
| Install | `pip install -r requirements.lock.txt -r requirements-dev.txt` | Osiris_backend |
| Lint | `ruff check .` | Osiris_backend |
| Type-check (non-blocking in CI, ~640 errors) | `mypy --ignore-missing-imports --no-strict-optional main.py models.py spatial_utils.py ml_referee.py` | Osiris_backend |
| Migrate | `python -m alembic upgrade head` | Osiris_backend |
| Ledger invariant | `python scripts/reconcile_ledger.py --check` | Osiris_backend |
| Tests (one per suite) | `python tests/test_<suite>.py` (list in `ci.yml`) | Osiris_backend |
| OpenAPI drift | `python scripts/check_openapi_drift.py` (`--write` regenerates `Documentation/openapi.json`) | Osiris_backend |
| Run API | `..\.venv\Scripts\uvicorn.exe main:app --reload --host 0.0.0.0` | Osiris_backend |
| Image | `docker build -t osiris-backend:ci Osiris_backend` | repo root |
| Admin install / dev | `npm install` / `npm run dev` | Osiris_admin_web |
| Admin typecheck + build | `npm run build` (`tsc && vite build`) | Osiris_admin_web |

The gate (`.claude/hooks/gate.sh`, Stop hook) runs ruff → admin build → migrations +
the backend suites → detekt + KMP shared tests, and only re-checks components whose diff changed since the last pass.
No formatter is adopted yet (ruff.toml defers `ruff format`), so do not reformat files wholesale.

## Architecture map
- `Osiris_backend/main.py` — app assembly only: middleware, scheduler, router mounting (order matters).
- `Osiris_backend/core/` — logging, auth/JWT/RBAC (`security.py`), rate limits, clock, error shapes.
- `Osiris_backend/routers/` — v1/v2 endpoints by area (accounts, runs, challenges, admin trust, payments, ...);
  their Pydantic models live in `schemas.py`. See `docs/architecture/backend.md`.
- `Osiris_backend/growth_api.py` — `APIRouter` for growth features, mounted onto `main.app`;
  logic in `growth_social.py`, `growth_communities.py`, `growth_safety.py`.
- `Osiris_backend/services/` — domain services: `ledger.py` (sole writer of `User.mana_crystals`),
  `stripe_gateway.py`, `challenges.py`, `quests.py`, `leaderboards.py`, `player_safety.py`,
  `progression.py` (rank, XP, badges), `challenge_store.py`, `proofs.py`, `jobs.py` (scheduled jobs).
- `Osiris_backend/models.py` / `database.py` — SQLAlchemy models; SQLite at `Osiris_backend/fitness_mvp.db`.
- `Osiris_backend/run_verifier.py`, `ml_referee.py`, `spatial_utils.py` — run/proof verification and geo math.
- `Osiris_backend/alembic/versions/` — migrations. `scripts/` — ops (reconcile, OpenAPI export/drift, seeding).
- `Osiris_backend/tests/` — standalone test scripts, one per release/feature suite.
- `Osiris_admin_web/src/` — `api/client.ts` + `types.ts`, `pages/*Page.tsx`, `components/`. Entry `main.tsx`.
- `Documentation/openapi.json` — committed API contract, checked for drift in CI.

## Conventions
- Backend tests have no pytest dependency. Each `tests/test_*.py` sets `os.environ.setdefault("OSIRIS_ENV", "test")`
  and a JWT secret, inserts the backend dir on `sys.path`, uses `fastapi.testclient.TestClient` against `main.app`,
  cleans up its own users by unique email, and prints `PASS <name>`. Copy this pattern for new suites
  and add the suite to `ci.yml` (human edit, see danger zones) and to `BACKEND_TESTS` in `gate.sh`.
- Errors: raise `HTTPException(status_code=..., detail="...")` from endpoints.
- Every crystal movement goes through `services.ledger.apply_crystal_delta`; it does not commit,
  the endpoint owns the transaction. Challenges must never touch crystals.
- Python: snake_case, type hints on new code, ruff rules `E`,`F` at line length 120.
- Kotlin: detekt (`./gradlew detekt`); shared logic in `shared/`, platform code only in `android_version/` and `ios_version/`.
- TS/React: pages `XxxPage.tsx`, API types centralised in `src/api/types.ts`.
- API changes require regenerating `Documentation/openapi.json` with `python scripts/check_openapi_drift.py --write`.
- Commit history uses `<Phase/Release>: <summary>` (e.g. `R2 backend: ...`). New commits use conventional
  commits (`feat(backend): ...`, `fix(customer): ...`, `test(backend): ...`).

## Danger zones (never touch without a human)
- Secrets: `**/.env*` (`Osiris_backend/.env`), anything `*secret*`, Stripe keys.
- Migrations: `Osiris_backend/alembic/versions/**`, `alembic.ini`; no `alembic revision/downgrade/stamp`.
- Data: `*.db` files (`fitness_mvp.db` is local dev state).
- Lockfiles: `requirements.lock.txt`, `package-lock.json`, `pubspec.lock`.
- CI/deploy: `.github/workflows/**`, `Osiris_backend/Dockerfile`, `Osiris_backend/DEPLOY_RUNBOOK.md`.
- Money path (editable, but flag for human review in the commit body): `services/ledger.py`,
  `services/stripe_gateway.py`, `scripts/reconcile_ledger.py`.
These are enforced by `permissions.deny` in `.claude/settings.json` and `.claude/hooks/guard.sh`.
If a task needs one, stop and write what is needed into PLAN.md as a `[human]` item.

## Definition of Done
- The gate passes (`.claude/hooks/gate.sh` exits 0).
- New behaviour has tests that follow the patterns above.
- No `TODO`, `FIXME`, `print` debugging, or `console.log` left behind in changed code.
- Conventional commit on a feature branch (`git checkout -b feat/<slug>`). Never push to main/master.

## Autonomous workflow
1. Read `PLAN.md`. Take the first unchecked `- [ ]` item that is not marked `[human]`.
2. Create or reuse a feature branch for it.
3. Implement exactly that item, meeting its acceptance criteria.
4. Run the gate; fix until it passes.
5. Commit with a conventional message, tick the box in `PLAN.md` (same commit).
6. Repeat. Stop and report when only `[human]` items remain or an item is blocked.
