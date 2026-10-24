# PLAN

## Goal
Get every check that CI runs green locally, and close the coverage and tooling gaps found while
setting the repo up for autonomous agent work (2026-10-12).

## Constraints
- Follow CLAUDE.md: one item per commit, gate green, conventional commit on a feature branch, never push to main/master.
- Items marked `[human]` touch danger zones (CI, migrations, lockfiles, .env, Dockerfile, deploy runbook) and need a human.
- The working tree contains uncommitted mixed WIP from earlier sessions. Do not commit files unrelated to the item.

## Tasks

- [x] backend: diagnose the crystal ledger reconciliation failure
  - `python scripts/reconcile_ledger.py --check` fails on the dev DB (seen: `challenger.09270021@example.com` ledger 200 vs wallet 100;
    `growth_g3_test_seeker@example.com` ledger 100 vs wallet 0). The count changed while the test suites ran.
  - Determine whether a code path writes `mana_crystals` without `services.ledger.apply_crystal_delta`, or whether test cleanup deletes users/ledger rows partially.
  - Acceptance: a written root cause in the commit body, plus a failing-then-passing regression test in the owning suite.
    After running all 13 CI suites, `reconcile_ledger.py --check` exits 0 for every user the suites create.

- [ ] data: clean the pre-existing ledger orphans out of the local dev DB
  - Root cause fixed in `fix/ledger-orphan-rows`, but rows written before the fix remain in `fitness_mvp.db`
    (orphans for missing users 14, 21, 22, 23; user 6 inherited row 68 from a deleted account).
  - Acceptance: delete those rows (or recreate the dev DB with `alembic upgrade head`); `reconcile_ledger.py --check` exits 0.

- [x] backend: route `DELETE /api/v1/users/{id}` through `growth_safety.erase_player`
  - Today it hard-deletes the users row and its crystal ledger rows (financial records must be anonymised and kept,
    PRD-009) while leaving runs, route points, courses, challenges and attempts behind. SQLite then reuses the id,
    so a new account can inherit another person's GPS history.
  - Acceptance: the endpoint anonymises via `erase_player` and keeps the tombstone row and ledger;
    the GDPR suite asserts route points are gone and the ledger still reconciles.

- [x] backend: resolve the OpenAPI contract drift
  - `python scripts/check_openapi_drift.py` exits 1 against the current working tree.
  - Acceptance: confirm that every schema difference comes from an intended API change in the WIP, then run
    `python scripts/check_openapi_drift.py --write`; the drift check exits 0 and the diff to `Documentation/openapi.json` conttended changes.

- [ ] [human] ci: add `python tests/test_mvp_gdpr_and_email_uniqueness.py` to `.github/workflows/ci.yml`
  - The suite exists and passes locally, but CI does not run it. After the CI step is added, an agent adds it to `BACKEND_TESTS` in `.claude/hooks/gate.sh`.
  - Acceptance: the CI jouite and it passes.

- [ ] [human] ci: add a job for `Osiris_admin_web` (`npm run build`)
  - Today CI covers the backend only; the command passes locally. (The Flutter app this item also named was retired
    on 2026-10-19; the KMP job is its own item below.)
  - Acceptance: a pull request that touches the admin app runs its job, and the job passes.

- [x] admin web: remove dead Vite template files
  - `index.html` loads `/src/main.tsx`; `src/main.ts`, `src/counter.ts`, `src/style.css` are only referenced by each other.
  - Acceptance: files deleted, `npm run build` passes, the dev server renders the login page.

- [x] backend: make mypy clean for `spatial_utils.py` and `ml_referee.py`
  - CI's mypy step is `continue-on-error` and currently reports 640 errors in 6 files.
  - Acceptance: the CI mypy command reports zero errors located in these two files; behaviour is unchanged and all backend suites still pass.

- [x] backend: convert `models.py` to SQLAlchemy 2.0 typed mappings (`Mapped[...]` / `mapped_column`)
  - Found 2026-10-12: `spatial_utils.py` and `ml_referee.py` already have zero mypy errors. The 640 errors are in
    main.py (386), growth_communities/api/safety/social (298) and services/ledger.py (1), and ~95% are arg-type /
    assignment errors because legacy `Column(...)` attributes type as `Column[int]` instead of `int`.
  - Acceptance: identical DDL (`Base.metadata` produces the same tables, columns, types, nullability, indexes and
    constraints before and after; no migration); all backend suites pass; the CI mypy error count drops substantially.

- [x] backend: stop blocking the event loop (found by load test 2026-10-12)
  - 101 `async def` endpoints made blocking SQLAlchemy calls, so a single worker served requests one at a time.
  - Acceptance: endpoints that never await run as plain `def` (FastAPI thread pool); p95 < 500 ms at 20 concurrent
    users for the main player endpoints (PRD NFR); all suites pass.

- [x] backend: close auth gaps found by the route inventory (2026-10-12)
  - Legacy `POST /api/v1/login` had no rate limit (brute-force bypass of `/auth/login`); unauthenticated
    `POST /api/v2/events` had none; 8 v1 player routes (incl. crystal purchase intent, vault, siege) skipped the
    suspension check.
  - Acceptance: regression checks in `test_phase2_security.py` fail before and pass after.

- [x] backend: delete raw route points after a retention window (Security plan §2, release status risk 3)
  - Acceptance: a scheduled job removes raw points of closed runs finished > 45 days ago, keeps run summaries and
    verification decisions, and keeps evidence for attempts in `review_required`; covered in `test_run_release.py`.

- [x] customer: keep recording runs with the screen locked (PRD-002; release status risk 7, background part)
  - Acceptance: an Android location foreground service runs only while a run is recording; points keep arriving
    and syncing with the screen asleep; the service leaves the foreground on finish/discard. iOS declares the
    background location mode and shows the system indicator.

- [x] backend: Prometheus metrics endpoint (backlog Phase 1 observability, Phase 2 run instrumentation)
  - Acceptance: request count and latency histogram by route template, run verification outcomes and rejection
    reasons; token-protected outside dev/test; covered in `test_run_release.py` and `test_phase2_security.py`.

- [ ] [human] customer: request the Android 13+ notification permission
  - The recording notification is posted but hidden until the app holds POST_NOTIFICATIONS; tracking works
    regardless. Requesting it needs a permission plugin (pubspec/lockfile change) or a small platform channel.
  - Acceptance: decision recorded; if adopted, the app asks once before the first run and the notification shows.

- [ ] [human] product: design pause/resume for runs (PRD-002)
  - Needs a per-point segment (migration) and an anti-cheat rule so a pause cannot hide travel (e.g. resume must be
    near the pause point, or the paused leg is excluded and capped). Verification rules version must be bumped.
  - Acceptance: then migration + verifier + app work can be planned as agent items.

- [ ] [human] product: retire or gate the legacy v1 game endpoints (domains, vault, sieges, bounties, coupons)
  - The PRD scopes them out of the MVP; they are kept alive by the admin Merchants/Bounties pages (the parked
    Flutter merchant app was removed on 2026-10-19). Retiring them is a product decision.
  - Acceptance: decision recorded; if retired, the endpoints, their tests, client screens and contract entries are
    removed in agent items.

- [x] customer: camera-denied recovery on the exercise screen (emulator QA 2026-10-14)
  - Denial left a dead end: no way to settings, and the failed camera was never cleared, so allowing the camera in
    settings and returning still showed the error. A first fix (retry on every resume) re-asked for permission at once,
    because the dialog itself pauses/resumes the app; caught on the emulator.
  - Acceptance: one denial shows the error and OPEN SETTINGS without re-prompting; returning from settings with the
    camera allowed starts the camera. Widget test covers both; verified on emulator-5554.

- [x] customer: automated accessibility audit (PRD NFR: touch targets, labels, contrast)
  - `test/accessibility_test.dart` renders the main screens with the real theme in a full-height phone viewport and
    checks Android tap-target size, labelled tap targets and WCAG AA contrast.
  - Found and fixed: home footer contrast 3.62 (< 4.5), unlabelled copy-invite, sign-up back and bounty refresh buttons.

- [x] customer: low-light warning before a run (Security plan §3: lighting warnings from available context)
  - On-device NOAA solar position from the current fix (no network, location stays on the phone); below civil
    twilight (-6°) START asks first, with advice; the player can still start.

- [x] customer: restore cold start after the exercise feature (release build, 2026-10-14)
  - Session restore opened the exercise SQLite DB on every launch to drop other accounts' rows (~er
    is now remembered in preferences; the DB opens o - Nonly when the signed-in account changes.

- [ ] [human] product: should a zero-rep exercise set be uploaded? (report 14)
  - Todit uploads a summary that earns nothing and counts against the 30/min upload limit.
  - Acceptance: decision recorded; if "no", the app keeps it local and the result sheet says so.

- [ ] [human] size: ML Kit pose model bundled vs delivered by Google Play services (report 14)
  - Universal APK went 53 → 99.7 MB (arm64 download 43.7 MB). The Play-services model shrinks the app but downloads on
    first use and needs a dependencfile).
  - Acceptance: decision recorded; if switched, first-use download handled in the exercise screen.

- [ ] [human] infra: SQLite single-writer tail latency
  - With WAL on, p95 meets target but write endpoints still show p99 0.8-1.1 s at 20 concurrent writers
    (route upload, /me/today). That is SQLite's one-writer limit; ADR-002 already requires PostgreSQL b
  - Acceptance: SIT runs on PostgreSQL and the load test (`p99 < 500 ms` for writes at 20 users) is re-run there.

- [ ] [human] ci: make the mypy step blocking
  - Since the typed-models refactor the CI mypy command reports zero errors, but the CI workflow still marks the
    step `continue-on-error: true`, so a regression would not fail CI. After the CI edit, an agent adds mypy to gate.sh.
  - Acceptance: the mypy step has no `continue-on-error` and passes.

- [ ] [human] tooling: decide on formatters (`ruff format` for the backend, `dart format` for the apps)
  - None are adopted (`ruff.toml` defers formatting). `.claude/hooks/format.sh` is a no-op until one is chosen.
  - Acceptance: decision recorded; if adopted, a one-off formatting commit, then format.sh and CLAUDE.md are updated with the command.

- [ ] [human] tooling: decide on lint and tests for `Osiris_admin_web`
  - There is no ESLint config and no test runner; only `tsc` (via `npm run build`) guards it.
  - Acceptance: decision recorded; if adopted, the scripts are added to `package.json` and wired into the gate.

## Camera-verified exercises (2026-10-14)
Goal: the player opens the camera, on-device pose estimation (ML Kit BlazePose) tracks the body, and a rep
engine counts push-ups, squats, lunges, sit-ups, jumping jacks, high knees and plank holds, judging whether
each rep is genuine. Everything runs on the phone; frames and landmarks never leave it. The server re-checks
the uploaded summary and grants capped XP (never crystals).
Human approval (2026-10-14, session owner): add the Flutter plugins (pubspec.lock) and one additive migration.

- [x] backend: exercise catalog, `exercise_sessions` table + migration, submit/history endpoints, server re-check
  - Acceptance: `services/exercises.py` is the single catalog source, exported to the app as
    `Osiris_customer/assets/exercise_catalog.json` (drift fails `tests/test_exercise_sessions.py`); implausible tempo,
    rate, totals, replayed timing, rules-version mismatch and device-rejected sets earn 0 XP; uploads are idempotent per
    `client_session_id`; per-exercise and total daily XP caps; export and erasure include the rows; metrics counters.
- [x] customer: on-device rep engine (pure Dart) with genuineness checks
  - Acceptance: synthetic landmark sequences prove genuine reps count; half reps, too-fast reps, broken form,
    occluded joints, tracking glitches, machine-regular replays and static poses do not; per-frame cost benchmarked.
- [x] customer: local SQLite store (catalog cache, sessions, reps) and an upload queue
  - Acceptance: sets survive restarts, upload once the network returns, never duplicate XP; tested with sqflite ffi.
- [x] customer: camera screen with live skeleton overlay, ML Kit adapter, entry point, platform permissions
  - Acceptance: frames are dropped while inference is busy (no queue build-up); Android CAMERA permission, iOS
    `NSCameraUsageDescription` and 15.5 deployment target; widget test drives the screen with a fake pose stream.
- [ ] ci (blocked for agents: guard.sh refuses CI-file commits; see the Sprint 3 `[human]` item): add `python tests/test_exercise_sessions.py` to `.github/workflows/ci.yml`; then an agent adds it to
  `BACKEND_TESTS` in `.claude/hooks/gate.sh`.
- [ ] [human] product: reconcile launch principle 1 in `Documentation/Enterprise/README.md` ("push-ups, squats, pose
  estimation ... are later product increments") with the camera exercise feature now built on request.
  - Acceptance: either the principle is updated, or the Bodyweight entry is gated behind a build flag for the first release.
- [x] audit: exercise performance test and audit (report 13); rate limit on set uploads added.
- [ ] [human] device QA: run the exercise screen on a physical Android phone and an iPhone (this build environment has
  no KVM, no Android SDK access and no macOS, so no emulator or simulator run was possible), and tune thresholds
  with real recordings if needed (bump `RULES_VERSION` when thresholds change).

## Camera exercises, phase 2 (2026-10-15)
Backlog Phase 5: "Add pose estimation behind explicit activity and ML consent." Also closes the gap that sets flagged
for review had no reviewer.

- [x] backend+customer: explicit, revocable consent for camera exercise counting
  - Acceptance: `exercise_camera` consent kind in the append-only ledger; `GET/PUT /api/v2/me/exercise-consent`;
    uploads without consent are refused (403 `EXERCISE_CONSENT_REQUIRED`); withdrawing can delete exercise data;
    the app shows a consent screen before the camera can open and a withdraw control in Settings; tests both sides.
- [x] backend+admin web: review queue for flagged exercise sets
  - Acceptance: admins list `review` sets and approve (capped XP for that set's day) or reject them, once, with an
    audit event; non-admins get 401/403; admin page `ExerciseReviewPage.tsx`; the app's local history picks up
    review outcomes on refresh.
- [x] launch test, performance and audit for phase 2 (report 15): admin console and Flutter web build driven in
  Chromium; fixed the database-failure path and the review-queue N+1.
- [ ] [human] tooling: adopt a browser E2E suite (Playwright) for the admin console and the Flutter web smoke test
  described in report 15 §5, and decide where it runs (gate, CI, or on demand).

## Sprint 3: rep-counting accuracy before device QA (2026-10-17)
Goal: know, with numbers, where the rep engine is right and wrong before people test it, and make device QA
produce reusable labeled data. Input: report 14 measured pose detection at 5.1 fps on the emulator; the engine
had only been tested at 30 fps.

- [x] gate: run `tests/test_exercise_sessions.py` in `.claude/hooks/gate.sh` (done 2026-10-17)
- [ ] [human] ci: add the exercise suite to the CI workflow. The PLAN item above lost its `[human]` tag on master, but
  `guard.sh` still blocks agents from committing CI files, so an agent cannot finish it. Add this step after
  "Tests — Growth G4 …" and before "Crystal ledger reconciliation after suites":
  `- name: Tests — camera-verified exercises` / `run: python tests/test_exercise_sessions.py`.
  Verified locally on 2026-10-17 with CI's full sequence on a fresh database (all 14 suites, reconcile, drift).
- [x] customer: accuracy evaluation of the rep engine (false rejects / false accepts) across frame rate, landmark
  noise, body size, camera roll and tempo, for all 7 exercises; fix what it finds
  - Acceptance: a committed evaluation test prints a per-exercise matrix and asserts budgets (genuine reps counted
    at >= 95% within supported conditions, cheat reps counted at 0%); the supported minimum frame rate is stated.
- [x] customer: tell the player when the phone is too slow to count reliably
  - Acceptance: below the supported pose frame rate the camera screen says so instead of silently missing reps;
    widget test with a slow fake pose stream.
- [x] customer: landmark recording and replay for device QA (debug builds only)
  - Acceptance: a debug-only switch on the camera screen saves the landmark stream (no images) with the tester's
    true rep count to a local JSON file; a replay test runs every recording in `test/exercise/recordings/` through
    the engine and compares with the label; format and retrieval documented; release builds cannot record.
- [x] audit: sprint 3 report (accuracy matrix, fixes, how to record and replay): report 16
- [ ] [human] device QA with recordings: record real sets on Android and iPhone (both good and deliberately
  bad sets, labeled), commit them with the person's consent to `Osiris_customer/test/exercise/recordings/`, and
  re-tune thresholds if any fail. Report 16 §1: the accuracy envelope is synthetic until then.

## Next phase: FrostMatte player app (2026-10-19)
Spec audit and defaults: project thread "next steps" (spec-audit.md). One PR per pipeline phase.

- [x] scaffolding: `.env.example`, `settings.secret()` (env or secret-manager file), `OSIRIS_DATABASE_URL`,
  `docker-compose.yml` + admin image, detekt for Kotlin with baselines, SwiftLint config, gate covers KMP
- [ ] [human] ci: add `python tests/test_settings.py` after the existing suites in `.github/workflows/ci.yml`.
- [ ] [human] ci: add a KMP job on `ubuntu-latest` with JDK 17 running
  `./gradlew detekt :shared:core:jvmTest :shared:domain:jvmTest :shared:data:jvmTest :shared:presentation:jvmTest :shared:presentation:compileKotlinIosSimulatorArm64`s touching `shared/**`, `android_version/**`, `gradle/**`, `*.gradle.kts`, `config/**`;
  and an Android job (`android-actions/setup-android`) running `./gradlew :android_version:app:assembleDebug detekt`.
- [ ] [human] admin web: add `eslint`, `typescript-eslint`, `eslint-plugin-react-hooks` and `prettier` to devDependencies
  (`npm install -D ...` rewrites `package-lock.json`, which agents may not edit); an agent then adds the configs and a `lint` script.
- [ ] [human] infra: pick the cloud (AWS or GCP) before Terraform is written; until then `infrastructure/` holds only images.
- [x] tabs: Discover (live, upcoming, community, finished; `GET /api/v2/challenge-hub`), Social global boards
  (distance, Riegel Pace Index, reps, rewards; `GET /api/v2/leaderboards/global`), Profile (rank gauge from
  `rank_floor_xp`, metrics grid), Wallet behind `features.walletDemo` with mock adapters only (no PAN handling,
  EIP-55 / base58cks, never touches crystals)
- [x] support: live chat stub on Profile, `WS /api/v2/support/ws` (player token, suspended players allowed, nothid Ktor WebSocket client and `SupportChatViewModel`
- [ ] [human] ci: add `python tests/test_growth_hub.py` and `python tests/test_support_chat.py` after the existing
  suites in `.github/workflows/ci.yml`.
- [ ] [human] migrations: approve agent-written Alembic revisions (in PRs) for refresh tokens, friendships and the
  activity feed, daily steps; blocks friends, the steps board and rotating refresh tokens.

## Performance pass (2026-10-19)
Audit report: `Documentation/Enterprise/17_Performance_Pass_and_Audit_2026-10-19.md`. Branch `perf/optimization-pass`.

- [x] retire the Flutter player app (`Osiris_customer/`) now the KMP app has parity; shared assets move to `shared/`
- [x] backend: list endpoints run a fixed number of queries however many rows they return (challenges, hub,
  courses, communities, seasons, invites, blocks, admin queues); `test_growth_hub` asserts it
- [x] backend: gzip (>= 1 KB), weak ETags with 304 on `If-None-Match`, `Cache-Control: private, no-cache`;
  the KMP client installs Ktor `HttpCache`
- [x] backend: PostgreSQL pool settings (`OSIRIS_DB_POOL_*`); SQics on connect and nightly
- [x] backend: global leaderboards cached 60 s per board (`OSIRIS_LEADERBOARD_CACHE_SECONDS`), viewer row always fresh
- [x] backend: `limit`/`offset` paging on long lists, `before_id` on audit events
- [ ] [human] migrations: add a covering index for the global boards and team goals (board query 40 -> 25 ms at
  100k runs, measured on a scratch copy):
  `CREATE INDEX ix_run_sessions_verified_finished ON run_sessions (verification_status, finished_at, user_id, distance_m, duration_seconds);`
  and `ix_run_sessions_user_verified ON run_sessions (user_id, verification_status, finished_at)` for per-player totals.
  - Acceptance: an Alembic revision with both indexes (and `models.py` `Index(...)` entries) passes the gate.
- [x] admin web: per-page chunks and long-lived library chunks, skeletonilters, non-blocking fonts
- [x] android: ARM-only release APK (87 -> 47 MB), Compose stability config (90 -> 2 unstable params), loading skeleton
- [x] infra: nginx gateway / load balancer config and compose override; `OSIRIS_RUN_SCHEDULER`
- [ ] [human] infra: run the gateway override once with Docker (`docker compose -f docker-compose.yml -f docker-compose.gateway.yml up --build`);
  before more than one replica: PostgreSQL, one scheduler, a shared rate limiter (report 17, section 4).
- [x] app: fetch Today once at start (it is fetched before and again after the first location fix)
  - Acceptance: a presentation test shows one `/api/v2/me/today` request when the location arrives within 2 s.

### Security scan (2026-10-19)
- [x] security: share and invite links use `OSIRIS_PUBLIC_BASE_URL`, never the request's Host header outside dev;
  outside dev, link endpoints answer 503 until it is set (`tests/test_public_base_url.py`). `terms_hash` checks its fields with an
  explicit error instead of an `assert` that `python -O` strips.
- [ ] [human] deps (lockfile): pip-audit finds 26 advisories in `requirements.lock.txt`. Bump `PyJWT==2.15.0`,
  `starlette>=1.3.1` (with a `fastapi` release that allows it), `anyio==4.14.2`, `idna==3.15`, `urllib3==2.8.0`.
  PyJWT GHSA-gvp8-978c-rx2q has no fix yet; it only bites callers that reuse an `options` dict, which `main.py` does not.
- [ ] [human] deps (lockfile): `npm audit` finds 6 high advisories in `Osiris_admin_web/package-lock.json`
  (`axios`, `vite` direct; `form-data`, `nanoid`, `postcss`, `source-map-js` transitive); `npm audit fix` resolves all.
- [ ] [human] ci: add `python tests/test_public_base_url.py` after the existing suites in `.github/workflows/ci.yml`.
- [ ] [human] deploy: add `OSIRIS_PUBLIC_BASE_URL` (the public https origin) to `DEPLOY_RUNBOOK.md` and every
  non-dev environment; without it share, invite and referral links answer 503 instead of trusting the Host header.

## UI: Slate redesign (2026-10-21)
Mock-up canvas: https://claude.ai/artifact/9T7qH7rsRZ32o1YXq5McMy (Today, live run, Social).

- [x] android: Slate tokens (charcoal slate, lime accent, orange for streaks; no purple), Manrope + Geist Mono,
  glass panes with a specular top rim, stepped top-left shadows and grain, floating chunky tab bar, one 72 sp
  focal number per screen (Today quest distance, Run distance, Social rank), asymmetric Today shortcuts,
  slate-tinted map tiles. `DesignTokensTest` checks WCAG AA text contrast.
- [ ] ios: bundle `manrope.ttf` and `geist_mono.ttf` (from `android_version/app/src/main/res/font/`) in the Xcode
  target with `UIAppFonts`, and use them in `Frost.swift`; the shared colours already apply. Needs a Mac to build.
  - Acceptance: the iOS Today screen renders the quest distance in Manrope ExtraBold at 72 pt.

## Strava parity program (2026-10-24)
Brief: 24 features, OpenAPI-first, verified-only game effects, privacy defwork.
Repo reality the plan follows: player app is KMP (Compose + SwiftUI, not Flutter), the merchant app is retired,
the database is SQLite until the PostGIS migration (ADR-002), and agents cannot write Alembic revisions, so each
new table is a model + tests here and a `[human]` migration item. Rides wait: every game query counts any accepted
session as foot distance, so ride km would fill run quests and boards until per-sport rules exist.

Build order (dependencies in brackets):
- A. Tracker and performance: 1, 3 [1], 4 [3], 7 [3], 6, 5 [3; HR part after 2], 24 [1 audio cues], 18 volume challenges
- B. Social: visibility + privacy zones [needed by 3, 9, 10, 23], 8, 10, 9 [8, visibility], 11 [9]
- C. Sensors: 2 [health consent; physical device]
- D. Groups: 19 (clubs exist: add feed and board) [9], 20, 21 [8]
- E. Spatial, after PostgreSQL/PostGIS: 12 [routing engine], 13 [12], 14 [12], 15, 16 [3], 17 [16], 22 [8], 23 [privacy zones]

- [x] tracker 1a: sport type (run, walk, hike), auto-pause (slower than 0.5 m/s for 10 s; a reported speed of 0 counts
  only if the position stayed within GPS jitter), live moving time and climb, spoken kilometre cues, no GPS distance
  filter so stops keep producing fixes; the server's verification decision records the same moving time and climb.
- [x] tracker 1b: audio cue interval options (per km or per N minutes) and a mid-run mute; auto-pause threshold setting
  - Cues every km, 5 or 10 min of moving time; mute and interval change mid-run (no burst). Auto-pause off, stops
    only (0.5 m/s), under 3.6 or 5.4 km/h; the finish sends `auto_pause_mps` so the server's moving time matches.
    Android UI not compiled in the agent container (no Android SDK); shared tests cover the logic.
- [ ] [human] device QA for tracker 1: a 60-min run on a low-end Android phone loses under 1% of points (compare
  `point_count` with fixes logged), screen off and app swiped away; record battery drain per hour.
- [ ] tracker 3: activity history and detail (map, splits, elevation profile), edit title, delete with derived-stat cascade
  (never the ledger). Needs `run_sessions.title` and `visibility` ([human] migration).
- [ ] ride: per-sport speed rules, boards and quest eligibility before `ride` is accepted.
