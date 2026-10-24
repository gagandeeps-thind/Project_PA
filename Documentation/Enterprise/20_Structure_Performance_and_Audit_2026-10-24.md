# Structure, Performance and Audit — 2026-10-24

**Branch:** `claude/cool-wozniak-dk57od` (from `a161811`).
**Environment:** Linux cloud container, 4 cores, Python 3.13, Node 22, JDK 17, Docker 29 (daemon started
in the container). No KVM and no Android SDK: the network policy refuses `dl.google.com`, so no APK build
and no emulator run were possible. Every Android result below comes from shared Kotlin code on the JVM.
**Scope:** the request was to reorganise the project, separate business logic, harden error handling, run
the performance checklist, test and audit, and continue the pending PLAN items.

## 1. Summary

| Area | Result |
|---|---|
| Backend structure | `main.py` went from 4,398 lines to 111. It now only assembles the app: `core/`, `routers/`, `schemas.py` and six new service modules. Contract, routes and middleware are unchanged. |
| Bugs fixed | Admin Bounties page broken since 2026-10-12. Admin console stuck on errors after token expiry. `stripe` missing from `requirements.txt`. Decay job aborting on a NULL. Replicas rejecting each other's tokens. |
| Performance | Load p95 927 → 413 ms on one worker; 158 ms with two replicas behind the gateway. Board ranking per request 7.8 → 0.03 ms at 10k players. Decay job 890 → 271 ms at 20k players. |
| Feature | Tracker 1b: cue intervals, mid-run mute, and an auto-pause speed setting; the server's moving time follows that setting. |
| Infra | The gateway stack ran for the first time; the open `[human]` item is now done. |

## 2. Checks run

| Check | Result |
|---|---|
| `ruff check .` | clean |
| CI mypy command | 0 issues |
| 19 backend suites, including the GDPR suite, which CI does not run yet | all pass, plus 5 new tests |
| Ledger reconciliation, OpenAPI drift | exit 0 |
| `./gradlew detekt` and four shared JVM test suites | 145 tests, 0 failures, 0 skipped |
| `:shared:presentation:compileKotlinIosSimulatorArm64` | passes |
| Admin `npm run build` | passes |
| Admin console in Chromium against a live API | 7 pages load without error; wrong password, expired token and failed chunk all behave correctly |
| Docker images: backend 298 MB, admin 82 MB; compose stack with the nginx gateway | healthy; migrations current |

Images were built from base images that trust the container's TLS-inspecting proxy CA. Those base
images were tagged locally; the repository's Dockerfiles were not changed.

## 3. Project structure

### Backend: done

`main.py` mixed six concerns: app setup, auth, rate limiting, about 120 Pydantic models, domain logic,
70 endpoints and the cron jobs. The code was moved verbatim and no names changed:

```
core/        security (JWT, roles, suspension check, bcrypt, webhook HMAC), rate_limit, logging_setup, clock, errors
routers/     system, accounts, runs, challenges, admin_trust, legacy_game, merchants, payments, bounties
schemas.py   request/response models of routers/
services/    + progression, challenge_store, proofs, audit, accounts, jobs   (get_db moved to database.py)
```

The growth routers now import from these modules instead of `main`, and `main` mounts every router
explicitly. Equivalence was checked four ways:
- The OpenAPI contract is byte-identical.
- The same 118 routes are registered. One block moved: the admin-merchant routes now precede the
  payment routes. Those paths share no prefix, so no URL can match differently.
- The middleware stack and its order are identical.
- All suites pass.

Layout and rules: `docs/architecture/backend.md`.

### Top-level folders: not renamed

The request asked for clean, consistent folder names. The repository already separates the parts:

| Folder | Contents |
|---|---|
| `Osiris_backend` | API |
| `Osiris_admin_web` | admin console |
| `shared` | KMP business logic |
| `android_version` | Android UI |
| `ios_version` | iOS UI |
| `infrastructure` | container configs |
| `docs`, `Documentation` | docs |

Only the naming is inconsistent. Renaming, for example to `apps/backend` and `apps/admin`, would mean
editing the CI workflow, the Dockerfile context, both compose files, the gate, the agent guides and the
19 enterprise documents. It would also break every open branch and each contributor's local venv and IDE
paths. CI files and the Dockerfile are human-only (`CLAUDE.md`, enforced by `guard.sh`), so this is a
`[human]` item in `PLAN.md` with the exact rename map. It was not done halfway.

## 4. Bugs found and fixed

| Bug | How it was found | Fix |
|---|---|---|
| Admin Bounties page said "Not enough permissions". The 2026-10-12 suspension fix made `/api/v1/bounties/nearby` player-only. | Driving the built console in Chromium | `get_active_player_or_admin`: admins pass, players keep the suspension check. Regression test added. |
| An expired admin token left every page erroring until a manual Disconnect | Chromium | A 401 handler in the API client signs out and returns to login |
| Five pages and the login screen showed "Request failed with status code 401" instead of the server's message. A 422 list was never shown. | Chromium | All pages use `apiErrorMessage`, which now reads 422 lists and names network failures |
| A page chunk deleted by a deploy blanked the console, because there was no error boundary | Code review; checked by blocking a chunk in Chromium | `ErrorBoundary` with a reload prompt; it clears on navigation |
| A reload flashed the login form | Code review | The session is read before the first render |
| `stripe` was imported at startup but missing from `requirements.txt`; four listed packages were never imported | Installing from `requirements.txt` | List fixed; a fresh venv imports the app |
| One NULL `last_activity_date` made the daily decay raise, so nobody decayed. The column is nullable; the ORM only fills a default. | Code review; the test fails on the old code | Decay is now one SQL UPDATE that skips NULL |
| With two replicas, half of all requests answered 401: each dev process invents its own JWT secret | First run of the gateway stack | The gateway override requires `OSIRIS_JWT_SECRET` |
| Server moving time ignored the player's auto-pause setting: off live, but on in the server's figure | Tracker 1b design | The finish request sends `auto_pause_mps` |

## 5. Performance

### API under load

`scripts/load_test.py` (new, committed) runs 20 concurrent players with their own tokens and ETags for
20–30 s. They cycle through Today, progression, both hub sections, nearby challenges, two global boards
and communities, with a profile write every tenth request.

| Setup | Throughput | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|
| Local, 1 worker, before | 75.6 req/s | 166 ms | 927 ms | 1,191 ms | 0 |
| Local, 1 worker, after | 102.9 req/s | 151 ms | 413 ms | 475 ms | 0 |
| Docker + nginx gateway, 1 replica, before | 85.4 req/s | 167 ms | 723 ms | 918 ms | 0 |
| Docker + nginx gateway, 1 replica, after | 90.4 req/s | 192 ms | 400 ms | 495 ms | 0 |
| Docker + nginx gateway, 2 replicas, after | 190.4 req/s | 97 ms | 158 ms | 193 ms | 0 |

The PRD target is p95 < 500 ms at 20 concurrent users. One worker now meets it; before, it did not.

**Root cause of the tail.** The distance board ran at a 700–900 ms p50 while every other endpoint sat
near 150 ms. py-spy put 82% of samples in one fetch: `_names` loaded about 50 whole `PlayerProfile`
rows to read three fields. Under 20 threads, SQLite row fetches cost per column returned:

| Rows read | Serial | 20 threads |
|---|---|---|
| All columns | 0.12 ms | 18 ms |
| Three columns | 0.11 ms | 5 ms |
| One column | 0.07 ms | 2.6 ms |

Both hot paths now read only the columns they use. The suspension check runs on every player request.
After the fix, the board's isolated throughput rose from 30 to 82 req/s.

### Other measurements

| Item | Before | After |
|---|---|---|
| Global board, ranking per request (10k players) | 7.8 ms, a full re-sort | 0.028 ms (`RankedBoard`: sort once per cache fill) |
| Daily decay job (20k players) | 890 ms, every row loaded and rewritten | 271 ms, or 82 ms when nothing changes; identical results |
| Admin first load | 12.7 KB app + 190 KB React + 47 KB libraries (gzip 4.4 + 60 + 18 KB) | unchanged; per-page chunks of 3–11 KB |

### The requested checklist

Most items were delivered by the 2026-10-19 pass (report 17). This pass verified them, then added:

| Item | Status now |
|---|---|
| Compress images | Nothing to gain: launcher PNGs of 0.4–1.4 KB and two small SVGs. The two fonts are 165–172 KB TTFs bundled in the APK. |
| Lazy loading, code splitting, minify JS/CSS, defer scripts, loading skeletons | Verified in the build output and in Chromium |
| Cache API responses, server-side caching, cache computed results | Verified: ETag/304 through the gateway, and 304s in the load test (80–87% of responses). Ranking is now cached sorted. |
| CDN | Verified headers through the container: hashed assets are `public, max-age=31536000, immutable`; HTML is `no-cache`. Not provisioned: no cloud chosen. |
| Compress payloads | Verified gzip through the gateway |
| Load balancer | Ran for the first time; even least_conn split across two replicas; WebSocket upgrade works |
| Connection pooling | Settings exist for PostgreSQL; SQLite keeps SQLAlchemy's pool |
| Index the database | The covering board indexes still need a migration (`[human]`) |
| Fix N+1 queries | Verified by `test_growth_hub` (16 list endpoints). Whole-row over-fetching fixed in two hot paths. |
| Paginate, debounce, reduce re-renders | Verified. No new long lists or inputs. |
| Remove unused dependencies | `requirements.txt` cleaned. `passlib` is still in the lock and `@types/*` sit in admin `dependencies`; both need a lockfile change (`[human]`). |
| Error handling, state management, `.env` separation | See section 4. Config already goes through `settings.secret()` and `.env.example`. App state lives in KMP view models (`StateFlow`). |

## 6. Open findings

| Finding | Impact | Proposed action |
|---|---|---|
| The board name lookup still dominates the distance board under concurrent SQLite load (p50 ~370 ms against ~150 ms) | Board tail latency on SQLite | PostgreSQL (ADR-002) or more worker processes. Caching names with the board would let a leaderboard opt-out lag 60 s; not done. |
| With `--scale backend=2`, every replica runs the scheduler | Jobs run twice; decay is applied twice a day | Run the jobs in one replica (`OSIRIS_RUN_SCHEDULER=0` on the others), as report 17 §4 says |
| Tracker 1b Android UI not compiled here | A compile error would surface only on a machine with the SDK | `./gradlew :android_version:app:assembleDebug` on a dev machine (`[human]` in PLAN) |
| Top-level folder names are inconsistent | Cosmetic | `[human]` rename plan in PLAN |
| `passlib` unused but locked; admin `@types/*` in `dependencies` | Image size, audit noise | `[human]` lockfile edits |

## 7. How to reproduce

```
cd Osiris_backend
python scripts/load_test.py --base-url http://127.0.0.1:8000 --players 60 --users 20 --seconds 30
python tests/test_growth_hub.py      # RankedBoard equivalence and timing
python tests/test_run_release.py     # decay, auto-pause setting
python tests/test_phase2_security.py # admin bounties access
cd ..
OSIRIS_JWT_SECRET=<48+ random chars> docker compose -f docker-compose.yml -f docker-compose.gateway.yml up -d --build --scale backend=2
```
