# Performance Test and Audit — 2026-10-12

**Build:** branch `osiris/orchestrated-buildout` lineage, feature branches `fix/*`, `perf/*`, `feat/*` from this date.
**Environment:** Windows 11 dev machine; backend = one uvicorn worker, SQLite (WAL), `OSIRIS_ENV=dev`;
Android emulator `test_device` (Android 17 / API 37, 1344×2992).
**Scope:** customer app on the emulator end to end, backend API latency under load, and an audit of auth coverage,
privacy defaults, and data hygiene.

## 1. End-to-end device test (customer app)

| Flow | Result |
|---|---|
| Sign-up (goal → consent → account), no BMI | Pass |
| First quest: 1.24 km run with real-time GPS replay | Pass: verified, quest credited, +37 XP, week progress and tomorrow's quest shown |
| Offline: airplane mode for 60 s mid-run | Pass: points queued on the phone ("OFFLINE 25/36"), drained after reconnect, nothing lost |
| Screen locked for 120 s mid-run (after `feat/background-run-tracking`) | Pass: location foreground service kept recording; 300 m and 25/25 points synced |
| Discard a run | Pass: run cleared, foreground service stops |
| Sign out | Pass: saved run cleared, back to login |
| Admin console login page (dev server, emulator browser) | Pass |

## 2. Backend latency

Load generator: 200 requests per endpoint, 1 and 20 concurrent players, over `127.0.0.1`.
(Using `localhost` on Windows adds ~200 ms per request from the IPv6→IPv4 fallback; that is a client artifact,
not server time.) PRD target: p95 < 500 ms for ordinary reads.

| Endpoint, 20 concurrent users | p95 before | p95 after | p99 after |
|---|---|---|---|
| `GET /healthz` | 256 ms | 37 ms | 42 ms |
| `GET /api/v2/me/today` (writes an analytics event) | 215 ms | 156 ms | 833 ms |
| `GET /api/v2/me/progression` | 101 ms | 146 ms | 167 ms |
| `GET /api/v2/challenges/nearby` | 145 ms | 62 ms | 68 ms |
| `GET /api/v2/leaderboards/local` | 191 ms | 76 ms | 85 ms |
| `POST /api/v2/runs/{id}/points` (5 points) | 367 ms | 353 ms | 1,129 ms |

Single-user p50 is 3–9 ms for every endpoint.

Changes behind "after" (`perf/backend-concurrency`):
- 101 endpoints were `async def` but made blocking database calls, which serialized all requests on the event loop.
  They are now plain `def` and run in FastAPI's thread pool.
- SQLite now runs in WAL mode with `busy_timeout`, because real concurrency exposed rollback-journal lock contention.
- `/healthz` caches the Alembic head instead of re-parsing every migration per probe.

**Known limit:** write p99 is 0.8–1.1 s at 20 concurrent writers. That is SQLite's single writer; ADR-002 already
requires PostgreSQL before SIT, and the load test should be re-run there.

## 3. Device performance (release build)

| Metric | Value |
|---|---|
| Cold start (`am start -W`, 3 runs) | 1.03 s, 0.87 s, 0.83 s (debug build: 4.2 s) |
| Memory after login (PSS) | 76 MB (native heap 27 MB, Java heap 4 MB) |
| APK size | 53 MB universal; Play app bundles / `--split-per-abi` ship roughly a third of that per device |
| Frame times | Not measured: Flutter's surface is invisible to `gfxinfo`, SurfaceFlinger returned no per-layer samples on this image, and emulator rendering is not representative. Measure on a physical device. |

## 4. Audit findings

| # | Area | Finding | Status |
|---|---|---|---|
| 1 | Privacy | Sign-up location-consent switch started ON (pre-ticked consent). | Fixed: starts OFF; regression test |
| 2 | UI | Material 3 progress tracks made 0% bars look full. | Fixed in theme |
| 3 | UI | Android 15+ edge-to-edge put bottom content under the gesture bar. | Fixed app-wide |
| 4 | Privacy / correctness | A saved unfinished run had no owner, so the next account on the phone resumed it (and its GPS points); abandoned runs never expired. | Fixed: run tied to account, 12 h staleness prompt, Discard action; 6 tests |
| 5 | Security | Legacy `POST /api/v1/login` had no rate limit (bypass of the login limiter). | Fixed; regression test |
| 6 | Abuse | Unauthenticated `POST /api/v2/events` had no rate limit. | Fixed (60/min/IP); regression test |
| 7 | Security / money path | 8 v1 player routes skipped the suspension check, including crystal purchase intent, vault and siege. | Fixed; regression test |
| 8 | Privacy | `DELETE /api/v1/users/{id}` hard-deleted the ledger but left GPS history; reused ids could inherit it. | Fixed: same erasure as v2 |
| 9 | Data | Test cleanups orphaned crystal-ledger rows; reconciliation check could not see orphans. | Fixed; check now reports orphans |
| 10 | Privacy | Raw route points were kept forever. | Fixed: 45-day retention job |
| 11 | Reliability | Locked screen stopped GPS, so real runs were rejected. | Fixed: location foreground service while recording |
| 12 | Copy | "you are an runner". | Fixed |
| 13 | Tooling | 640 mypy errors (legacy SQLAlchemy `Column` typing). | Fixed: typed models, 0 errors |

Route inventory: every route without an auth dependency was reviewed. The remaining ones are intentional
(health, rules, opt-in public pages, sign-up/login, crystal pack list, Stripe webhook with signature check,
rate-limited `/api/v1/activities/verify`).

## 5. Open items needing a decision

Tracked as `[human]` items in `PLAN.md`: PostgreSQL for SIT, CI jobs for the apps and the GDPR suite, making mypy
blocking in CI, the Android 13+ notification permission, pause/resume design, retiring the legacy v1 game endpoints,
formatter and admin-lint choices, and cleaning pre-existing orphan rows from the local dev database.
