# Performance Pass and Audit — 2026-10-19

**Build:** branch `perf/optimization-pass` (from `e2280fe`), 12 commits.
**Environment:** Windows 11 dev machine (8 cores); SQLite in WAL mode; Android emulator `test_device`
(Android 17 / API 37, x86_64 with ARM translation, 1344×2992). Docker is not installed on this machine,
so the container configs below were written but not run.
**Scope:** a requested checklist of web performance techniques, applied where each fits this stack
(FastAPI API, Vite/React admin console, Kotlin Multiplatform Android app), then measured before and after.

## 1. Results

### API under load

Load generator: 20 concurrent players for 30 s over `127.0.0.1`, each with its own token, cycling through the reads
the app makes (Today, progression, Discover hub live and finished, nearby map, two global boards, communities,
seasons, courses), plus a profile write every tenth request. Clients send `If-None-Match` like the app's HTTP cache
does. Seed: 120 players, 264 verified runs, 24 challenges, one 120-member club, one season
(`scratchpad/perf/profile_endpoints.py`, `load_test.py`).

| Build | Throughput | p50 | p95 | p99 | Bytes on the wire | Errors |
|---|---|---|---|---|---|---|
| Baseline `e2280fe`, 1 worker | 67 req/s | 249 ms | 607 ms | 741 ms | 7.2 MB | 0 |
| This branch, 1 worker | 107 req/s | 134 ms | 429 ms | 499 ms | 0.16 MB | 0 |
| This branch, 4 workers | 355 req/s | 40 ms | 122 ms | 165 ms | 0.19 MB | 0 |

With no other load every endpoint answers in 7–15 ms. Under load, latency is CPU time queued behind Python's GIL
in one process, so the remaining lever is worker processes (section 4).

### Database queries per request

| Endpoint | Before | After |
|---|---|---|
| `GET /api/v2/challenges/nearby` (24 challenges) | 51 | 5 |
| `GET /api/v2/challenge-hub?section=finished` | grew 1–3 per challenge | fixed |
| `GET /api/v2/communities` (+3 clubs) | 16 → 28 | 16 → 16 |
| `GET /api/v2/admin/reports` (+9 reports) | 19 → 37 | 19 → 19 |
| Courses, seasons, invites, blocks, admin communities, admin challenges | grew per row | fixed |

`tests/test_growth_hub.py` now adds rows and asserts that 16 list endpoints run the same number of queries.

### Global leaderboards at 100k runs (10k players)

| Board | Before | After, uncached | After, cached |
|---|---|---|---|
| distance, all time | 215 ms | 91 ms | 43 ms |
| pace, all time | 293 ms | 291 ms | 37 ms |
| one player's own totals (viewer row) | 15 ms | 0.05 ms (planner statistics) | — |

### Admin console bundle

| | Before | After |
|---|---|---|
| JavaScript on first load | 287 KB (88 KB gzip), one file | 12 KB app + 190 KB React + 47 KB other libraries |
| Opening a page | already loaded | 3–11 KB chunk on first visit |
| After a deploy | whole bundle re-downloaded | only the 12 KB app chunk and changed pages |

### Android app

| Metric | Before | After |
|---|---|---|
| Release APK | 87 MB | 47 MB |
| Unstable composable parameters (compiler report) | 90 | 2 (`NavHostController`) |
| Release cold start (emulator, warm OS cache) | — | 0.7–1.3 s |
| Debug cold start | 4.2–7.0 s | unchanged (debug Compose is unoptimised) |
| Debug frames, tab tour with scrolling | — | p50 19 ms, p90 28 ms, 4.6 % janky |
| Revisiting Today | full body each time | `304 Not Modified` |

Device run: sign-in, Today, Discover, Social, Wallet and Profile all loaded against the new backend.
The release build is correctly refused by the dev API: release forbids cleartext HTTP and the local API is
`http://10.0.2.2:8000`. So release was measured for startup only.

## 2. The checklist, item by item

| Requested | Status | Where |
|---|---|---|
| Fix N+1 database queries | Done | `ChallengeStats`, `CommunityContext`, batched helpers in `main.py`, `growth_hub.py`, `growth_communities.py`, `growth_safety.py`, `growth_social.py` |
| Compress API payloads | Done: gzip ≥ 1 KB | `GZipMiddleware` in `main.py` |
| Cache API responses | Done: weak ETag, 304 on match, `Cache-Control: private, no-cache` (public 5 min for `/api/v2/rules`); Ktor `HttpCache` in the app | `http_cache.py`, `ApiClient.kt` |
| Server-side caching / cache expensive results | Done: global boards cached 60 s per board; the viewer's own row is always live | `services/ttl_cache.py`, `growth_hub.py` |
| Database connection pooling | Done for PostgreSQL: pool 20 + 20 overflow, pre-ping, 30 min recycle (`OSIRIS_DB_POOL_*`) | `database.py` |
| Index the database | Partly. Planner statistics are now kept fresh (`PRAGMA optimize`), which fixed the worst plan; the covering board index needs a migration | `database.py`; `[human]` item in `PLAN.md` |
| Paginate large lists | Done: `limit`/`offset` on courses, blocks, review queue, reports, communities, challenges, exercise sets; `before_id` on audit events; invites capped at 200 | contract regenerated |
| Load balancer | Written, not run: nginx `least_conn` gateway with keepalive, retries, WebSocket upgrade; `OSIRIS_RUN_SCHEDULER=0` for extra replicas | `infrastructure/docker/api-gateway.conf`, `docker-compose.gateway.yml` |
| CDN | Ready, not provisioned: hashed admin assets are `immutable` for a year and the HTML shell is `no-cache`, so any CDN can sit in front unchanged | `infrastructure/docker/admin-nginx.conf` |
| Split code into chunks | Done: one chunk per admin page; React and other libraries in long-lived chunks | `App.tsx`, `vite.config.ts` |
| Minify JS and CSS | Already on (Vite production build); verified in the output | — |
| Defer non-critical scripts | Done: Google Fonts no longer block render (they were chained behind the stylesheet's `@import`); the entry script is a module, which is deferred by default | `index.html` |
| Lazy loading | Done: admin pages load on first visit; app lists were already `LazyColumn` with stable keys | — |
| Loading skeletons | Done: admin tables and KPI cards; app `LoadableContent` (used by most screens) | `Skeleton.tsx`, `Skeleton.kt` |
| Debounce input handlers | Done where input triggers requests: admin audit entity-id and exercise player-id filters (350 ms). The app has no such inputs: city and name save on the dialog's button. | `useDebouncedValue.ts` |
| Reduce unnecessary re-renders | Done: stability config for shared models in Compose (90 → 2 unstable params); memoised admin sidebar with stable handlers | `compose-stability.conf`, `App.tsx` |
| Compress images | Nothing to gain: the only images are launcher PNGs of 0.4–1.4 KB and two small SVGs | — |
| Remove unused dependencies | Done: the Flutter player app (`Osiris_customer/`, 186 files, 4.3 GB of build output) retired now that the KMP app has parity; the unused Flutter merchant app (`Osiris_merchant/`, 141 files, 1.1 GB) removed. The backend merchant endpoints stay: the admin Merchants and Bounties pages use them | commits `e23d347`, merchant removal |
| Performance audit | This document | — |

Bug found and fixed on the way: typing in the admin audit Entity ID field reloaded the list on every keystroke.
The filter row only rendered while not loading, so it unmounted and the input lost focus after each character.

## 3. Audit findings still open

| Finding | Impact | Proposed action |
|---|---|---|
| The covering index `run_sessions (verification_status, finished_at, user_id, distance_m, duration_seconds)` is missing | Board queries 40 → 25 ms at 100k runs | `[human]` migration in `PLAN.md` |
| Today is fetched twice at app start (before and after the first location fix) | One extra request per launch | Wait for the fix, or a short timeout, before the first fetch |
| Ranking a cached board still sorts every player per request (~40 ms at 10k players) | Board latency at scale | Cache the sorted list and insert the viewer by binary search |
| Release APK is 47 MB, of which ML Kit's native pose library is ~37 MB | Download size | Ship an App Bundle (per-device ABI, ~25 MB); the bundled vs Play-services model question is already a `[human]` item |
| Container configs (gateway, admin nginx) were not run here | Unverified | Run `docker compose -f docker-compose.yml -f docker-compose.gateway.yml up --build` once on a machine with Docker |

## 4. Scaling out

Four worker processes gave 5.3× the baseline throughput on one machine. Before running more than one process or
replica in a real environment:

1. **PostgreSQL.** SQLite allows one writer at a time; write p99 already reaches about 1 s at 20 concurrent writers
   (report 12). ADR-002 requires PostgreSQL before SIT, and the pool settings above are ready for it.
2. **One scheduler.** Each process runs decay, settlement and retention jobs unless `OSIRIS_RUN_SCHEDULER=0`.
   Run the jobs in exactly one replica (or a separate worker), and set 0 everywhere else.
3. **Shared rate limits.** The limiter is in memory per process, so N replicas allow N times the configured rate.
   Move it to Redis, or set the per-replica limits to (limit ÷ N).
4. **Client IP.** Behind the gateway, uvicorn must trust `X-Forwarded-For` (`FORWARDED_ALLOW_IPS`), or every player
   shares the gateway's rate-limit bucket. Do this only while the API port is reachable from the gateway alone, as
   the compose override does.
5. **Caches are per process.** Leaderboard values can differ by up to the TTL (60 s) between replicas. That is
   acceptable for boards; do not reuse this cache for anything that must be consistent.

## 5. How to reproduce

```
cd Osiris_backend
python tests/test_growth_hub.py            # query counts, gzip/ETag, cache, paging, planner statistics
python tests/test_settings.py              # one scheduler per deployment
cd ../Osiris_admin_web && npm run build    # chunk sizes
cd .. && ./gradlew :android_version:app:assembleRelease                         # APK size
./gradlew :android_version:app:compileReleaseKotlin -Posiris.composeReports=compose-reports   # stability report
```
