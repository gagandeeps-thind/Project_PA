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

- [ ] [human] data: clean the pre-existing ledger orphans out of the local dev DB
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
    `python scripts/check_openapi_drift.py --write`; the drift check exits 0 and the diff to `Documentation/openapi.json` contains only intended changes.

- [ ] [human] ci: add `python tests/test_mvp_gdpr_and_email_uniqueness.py` to `.github/workflows/ci.yml`
  - The suite exists and passes locally, but CI does not run it. After the CI step is added, an agent adds it to `BACKEND_TESTS` in `.claude/hooks/gate.sh`.
  - Acceptance: the CI job runs the suite and it passes.

- [ ] [human] ci: add jobs for `Osiris_admin_web` (`npm run build`) and `Osiris_customer` (`flutter analyze`, `flutter test`)
  - Today CI covers the backend only. Both commands pass locally.
  - Acceptance: a pull request that touches either app runs its job, and the job passes.

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
  - Acceptance: approved design; then migration + verifier + app work can be planned as agent items.

- [ ] [human] product: retire or gate the legacy v1 game endpoints (domains, vault, sieges, bounties, coupons)
  - The PRD scopes them out of the MVP; they are kept alive by the admin Merchants/Bounties pages and the parked
    merchant app. Retiring them is a product decision.
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
  - Session restore opened the exercise SQLite DB on every launch to drop other accounts' rows (~200 ms). The owner
    is now remembered in preferences; the DB opens only when the signed-in account changes.

- [ ] [human] infra: SQLite single-writer tail latency
  - With WAL on, p95 meets target but write endpoints still show p99 0.8-1.1 s at 20 concurrent writers
    (route upload, /me/today). That is SQLite's one-writer limit; ADR-002 already requires PostgreSQL before SIT.
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
- [ ] [human] ci: add `python tests/test_exercise_sessions.py` to `.github/workflows/ci.yml`; then an agent adds it to
  `BACKEND_TESTS` in `.claude/hooks/gate.sh`.
- [ ] [human] product: reconcile launch principle 1 in `Documentation/Enterprise/README.md` ("push-ups, squats, pose
  estimation ... are later product increments") with the camera exercise feature now built on request.
  - Acceptance: either the principle is updated, or the Bodyweight entry is gated behind a build flag for the first release.
- [x] audit: exercise performance test and audit (report 13); rate limit on set uploads added.
- [ ] [human] device QA: run the exercise screen on a physical Android phone and an iPhone (this build environment has
  no KVM, no Android SDK access and no macOS, so no emulator or simulator run was possible), and tune thresholds
  with real recordings if needed (bump `RULES_VERSION` when thresholds change).
