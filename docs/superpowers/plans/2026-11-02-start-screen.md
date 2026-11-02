# Start Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Start tab with Train and Challenge pages. They record live workouts from Bluetooth sensors and GPS, import past workouts from Health Connect, save every session, let the player post it, run group challenges, and show history under Profile → Progress.

**Architecture:**
- **Backend:** a `training` router and service plus a `group_challenges` router, on three new tables in one migration.
- **KMP:** shared domain models and pure logic (BLE parsers, recorder), data repositories, and view models.
- **Android:** Compose screens plus BLE and Health Connect platform adapters.

**Tech Stack:**
- FastAPI, SQLAlchemy and Alembic
- Kotlin Multiplatform, Compose Material 3
- Android BLE GATT
- `androidx.health.connect:connect-client`
- Vite/React for the admin web

**Spec:** `docs/superpowers/specs/2026-11-02-start-screen-design.md`

## Global Constraints

- **Bar order:** Home · Arise · Start · Social · Profile.
  - Wallet is a pushed route, opened from Start's top-right icon. The icon is hidden when `graph.hasWallet` is false.
- **Series limits:**
  - ≤ 720 points per channel.
  - HR 25–250, power 0–3000 W, speed 0–activity `max_speed_mps`, elevation −500–9000 m.
  - Out-of-range points are dropped.
- **Server-side computation:** stats are computed by the server. Camera reps and duration are copied from the linked `ExerciseSession`.
- **Challenge credit:** only `mode=challenge` sessions count towards group challenges.
- **Crystals:** the Start page never touches crystals.
- **Detekt:** new Kotlin code must be clean, with named constants and lines ≤ 120.
- **Backend conventions:**
  - Python suites print `PASS <name>`.
  - Ruff `E`,`F` at 120 columns.
  - `HTTPException` for errors.
  - `openapi.json` is regenerated.
- **Secrets:** never commit `config/environments/local.properties` (the Mapbox token).

## Review Focus

- **Upload retry after a network failure** must not create a duplicate session.
  - Fix: idempotent on `client_session_id`.
  - Test: `test_upload_idempotent` (Task 1).
- **A session with no sensors at all** (indoor, nothing paired) must still save, with null stats and a duration.
  - Tests: `test_upload_without_series` (Task 1) and `recorder with no samples still has duration` (Task 4).
- **Joining a group challenge after it ended**, or one the player cannot see, gives 409 or 404.
  - Test: `test_group_join_rules` (Task 2).
- **Pausing the session.** Paused time must not count in the duration, and points recorded while paused are dropped.
  - Test: `recorder pause excludes time` (Task 4).
- **A BLE heart-rate packet in 16-bit format** (flag bit 0) must decode correctly.
  - Test: `hr uint16 format` (Task 4).

---

### Task 1: Backend training sessions, summary, progress, quote, connections

**Files:**
- Create:
  - `Osiris_backend/alembic/versions/d4e8a1b2c3f5_start_training.py` (all three tables: `training_sessions`, `group_challenges`, `group_challenge_members`)
  - `Osiris_backend/services/training.py`
  - `Osiris_backend/routers/training.py`
  - `Osiris_backend/tests/test_training.py`
- Modify:
  - `Osiris_backend/models.py`: `TrainingSession`, `GroupChallenge`, `GroupChallengeMember`
  - `Osiris_backend/main.py`: mount the router
  - `.claude/hooks/gate.sh`: `BACKEND_TESTS`
  - `.github/workflows/ci.yml`: add the step
  - `Documentation/openapi.json`

**Interfaces (produces):**
- **Endpoints**, wire names in snake_case:
  - `GET /api/v2/training/activities` → `[{key, name, kind: "camera"|"gps"|"sensor", metric: "reps"|"distance_m"|"duration_s", max_speed_mps, gps}]`
  - `POST /api/v2/training/sessions`
    - Body: `{client_session_id, activity_key, mode, source, started_at, duration_s, distance_m=0, exercise_session_id?, series:{hr,power,speed,elevation: [[t_s, v]]}, devices:[str]}`
    - Returns `TrainingSessionOut` (201), including `is_pr`.
  - `TrainingSessionOut` fields:
    - `id, activity_key, mode, source, started_at, duration_s, distance_m, elevation_gain_m, reps`
    - `hr_avg/min/max, power_avg/min/max, speed_avg/max, elev_min/max`
    - `posted: bool, is_pr: bool, series` (series only in detail and in the summary's `latest`)
  - `POST /api/v2/training/sessions/{id}/post` with `{caption}` → `FeedPostOut`
  - `GET /api/v2/me/training/summary?activity=`
    - Returns `{activity_key, pr:{value, unit, session_id}|null, segments:{workouts, challenges}, total_duration_s, total_distance_m, total_reps, week_sessions, latest: TrainingSessionOut|null}`.
  - `GET /api/v2/me/training/sessions?activity=&limit=20&offset=0` → `{items:[TrainingSessionOut]}`
  - `GET /api/v2/me/training/sessions/{id}`
  - `GET /api/v2/me/training/progress?weeks=8` → `{weeks:[{week_start: "YYYY-MM-DD", duration_s, sessions, by_activity:{key: duration_s}}]}`
  - `GET /api/v2/motivation/quote?exclude=` → `{id, text, author}`
  - `GET /api/v2/me/connections` → `[{user_id, display_name, avatar_url}]`
- **Service** `services/training.py` (pure):
  - `ACTIVITIES: list[dict]`, `BY_KEY`
  - `clean_series(series, duration_s, max_speed) -> dict`
  - `stats(series) -> dict`
  - `elevation_gain(points, hysteresis=1.0) -> float`
  - `connection_ids(db, uid) -> set[int]` (used by Task 2)

- [ ] **Step 1: Write the tests** in `tests/test_training.py`, following the house pattern (TestClient, unique emails, `PASS` lines):
  - `test_catalog`: includes `pushup` (camera) and `run` (gps).
  - `test_upload_stats_server_side`: HR `[[0,100],[10,140],[20,999]]` gives `hr_max == 140`, `hr_min == 100`, `hr_avg == 120`. Elevation `[[0,100],[5,103],[10,102],[15,106]]` gives a gain of 7.
  - `test_upload_without_series`: 201 with `hr_avg is None`.
  - `test_implausible_speed`: a run of 10 km in 60 s is rejected with 422.
  - `test_upload_idempotent`: the same `client_session_id` twice returns the same id.
  - `test_camera_link`:
    - A foreign `exercise_session_id` gives 403.
    - The player's own link copies `reps_valid` and ignores the client's reps.
  - `test_pr_and_segments`:
    - Run 3000 m (train), then 5000 m (challenge): the second has `is_pr` true.
    - The summary gives `pr.value == 5000` and `segments == {workouts:1, challenges:1}`.
  - `test_list_detail_and_foreign_404`
  - `test_progress_weeks`: 8 weeks, with the current week's duration summed.
  - `test_post_idempotent`: two posts return the same post id, and the second sets `posted`.
  - `test_quote_exclude`: 20 calls with `exclude=<first id>` never return that id.
  - `test_connections`: a follower and a followee are both listed.
- [ ] **Step 2:** Run `python tests/test_training.py`. Expected: ImportError or 404 failures.
- [ ] **Step 3:** Implement the models, migration, service and router.
  - Mount the router in `main.py` next to `arise`.
  - Quotes are a curated list in `services/training.py` (`QUOTES`, about 30 short public-domain lines, `id` is the index).
- [ ] **Step 4:** The tests pass. `ruff check .` is clean. Run `python scripts/check_openapi_drift.py --write`.
- [ ] **Step 5:** Add the suite to `gate.sh` and `ci.yml`, then commit `feat(backend): training sessions, summary, progress and quotes`.

### Task 2: Backend group challenges

**Files:**
- Create: `Osiris_backend/routers/group_challenges.py`
- Modify: `tests/test_training.py`, `main.py`, `Documentation/openapi.json`

**Interfaces:**
- **Consumes:** `connection_ids` and `BY_KEY` from Task 1.
- **Produces:**
  - `GroupChallengeOut`: `{id, title, activity_key, metric, target, starts_at, ends_at, is_official, creator_id, status: "active"|"ended"|"cancelled", my_status: "joined"|"invited"|null, my_progress, members, top:[{user_id, display_name, avatar_url, progress}]}`.
  - `GET /api/v2/group-challenges` → `{official, mine, invited, connections}`.
  - `POST /api/v2/group-challenges` with `{title, activity_key, metric, target, days (1–90), invitee_ids}`.
  - `GET /{id}` → `GroupChallengeOut` plus `leaderboard` (the full `top`).
  - `POST /{id}/join`, `/leave` and `/cancel`.
  - `POST` and `GET /api/v2/admin/group-challenges`, using the admin dependency from `routers/admin_trust.py`.

- [ ] **Step 1: Tests:**
  - `test_group_create_and_invites`: inviting a non-connection gives 422; an invitee gets a notification of kind `group_challenge_invite`.
  - `test_group_visibility`: a stranger gets 404; a connection of the creator sees it under `connections`.
  - `test_group_join_rules`:
    - Joining after the end gives 409.
    - Cancelled gives 409.
    - The creator leaving gives 409.
  - `test_group_progress_challenge_mode_only`: a train session adds 0; a challenge session of the same activity within the window adds its distance.
  - `test_group_leaderboard_order`
  - `test_official_admin`: a player gets 401 or 403; the admin creates it; it appears in every player's `official`.
- [ ] **Step 2:** Run. Expected: failures.
- [ ] **Step 3:** Implement the router.
  - Progress is one grouped query per challenge list over `training_sessions`.
  - `status` is derived: `ended` when `now >= ends_at`.
- [ ] **Step 4:** Pass, run ruff, regenerate openapi, then commit `feat(backend): group challenges`.

### Task 3: Admin web — official challenges page

**Files:**
- Create: `Osiris_admin_web/src/pages/OfficialChallengesPage.tsx`
- Modify: `src/api/types.ts`, `src/api/client.ts`, and the router/nav file where the pages are registered.

- [ ] **Step 1:** Add the `GroupChallenge` type and the `listOfficialChallenges()` / `createOfficialChallenge(body)` client functions.
- [ ] **Step 2:** Build the page: a table of title, activity, metric, target, window and members, plus a create form (title, activity key, metric select, target, days).
- [ ] **Step 3:** `npm run build` passes. Commit `feat(admin): official group challenges page`.

### Task 4: Shared domain — models, BLE parsers, recorder

**Files:**
- Create:
  - `shared/domain/src/commonMain/kotlin/com/osiris/shared/domain/model/Training.kt`
  - `shared/domain/src/commonMain/kotlin/com/osiris/shared/domain/training/BleParsers.kt`
  - `shared/domain/src/commonMain/kotlin/com/osiris/shared/domain/training/TrainingRecorder.kt`
  - `shared/domain/src/commonMain/kotlin/com/osiris/shared/domain/repository/TrainingRepository.kt`
  - `GroupChallengeRepository.kt` (same folder)
- Test:
  - `shared/domain/src/jvmTest/kotlin/com/osiris/shared/domain/training/BleParsersTest.kt`
  - `TrainingRecorderTest.kt` (same folder)

**Produces:**
- **Models** (kotlinx-serializable, `@SerialName` snake_case):
  - `TrainingActivity(key, name, kind: ActivityKind {CAMERA, GPS, SENSOR}, metric, maxSpeedMps, gps)`
  - `TrainingSession`, mirroring `TrainingSessionOut`.
    - `series: TrainingSeries?`
    - `TrainingSeries(hr, power, speed, elevation: List<List<Double>>)`
  - `TrainingSummary`, `Personal(value, unit, sessionId)`, `Segments(workouts, challenges)`
  - `WeeklyProgress(weekStart, durationS, sessions, byActivity: Map<String, Double>)`
  - `Quote(id, text, author)`
  - `Connection(userId, displayName, avatarUrl)`
  - `GroupChallenge`, `GroupMember`, `GroupChallenges(official, mine, invited, connections)`
  - `NewTrainingSession` (the upload body)
  - `NewGroupChallenge`
- **`enum class Channel { HR, POWER, SPEED, ELEVATION }`**
- **`object BleParsers`:**
  - `heartRate(bytes: ByteArray): Int?`
  - `cyclingPower(bytes): Int?` (sint16 at offset 2)
  - `rscSpeedMps(bytes): Double?` (uint16 at offset 1, divided by 256)
  - `class CscSpeed(wheelM = 2.105) { fun next(bytes): Double? }` (wheel revolution and time deltas, time in 1/1024 s)
  - UUID constants:
    - `HEART_RATE_SERVICE`, `HR_MEASUREMENT`
    - `CYCLING_POWER_SERVICE`, `CP_MEASUREMENT`
    - `RSC_SERVICE`, `RSC_MEASUREMENT`
    - `CSC_SERVICE`, `CSC_MEASUREMENT`
- **`class TrainingRecorder(startedAt: Instant)`:**
  - `add(channel: Channel, value: Double, at: Instant)` keeps at most one point per channel per second.
  - `addFix(fix: LocationFix)` accumulates distance (haversine via `Geo`), records speed if no sensor speed arrived within 5 s, and records altitude as elevation.
  - `pause(at)` and `resume(at)`.
  - `elapsedS(at): Double`
  - `latest(channel): Double?`
  - `distanceM`
  - `series(maxPoints = 720): TrainingSeries`, downsampled by bucket average.
- **`TrainingRepository`:**
  - `activities()`
  - `quote()`, fetched once per process
  - `summary(activityKey)`
  - `sessions(activityKey?, offset)`
  - `session(id)`
  - `upload(NewTrainingSession)`
  - `post(id, caption)`
  - `progress(weeks = 8)`
  - `connections()`
- **`GroupChallengeRepository`:** `all()`, `detail(id)`, `create(NewGroupChallenge)`, `join(id)`, `leave(id)`.
- **Return type:** every method returns `Outcome<…>`.

- [ ] **Step 1: Tests:**
  - `hr uint8 format`: `[0x00, 0x48]` → 72.
  - `hr uint16 format`: `[0x01, 0x2C, 0x01]` → 300 is decoded but out of range for the server. The parser returns the raw value, and filtering happens on the server and the recorder. Also `[0x01, 0x78, 0x00]` → 120.
  - `cycling power`: `[0,0, 0xFA,0x00]` → 250.
  - `rsc speed`: `[0, 0x00,0x03]` → 3.0 m/s.
  - `csc speed from two packets`: one wheel rev per 1024 ticks → 2.105 m/s.
  - `recorder keeps one point per second`
  - `recorder pause excludes time`: start t0, pause t10, resume t20, at t30 gives elapsed 20. A sample added while paused is ignored.
  - `recorder with no samples still has duration`
  - `downsample caps at 720`: 2000 points → 720.
  - `gps distance accumulates and gps speed yields to sensor speed`
- [ ] **Step 2:** Run `./gradlew :shared:domain:jvmTest`. Expected: compile failures.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Tests pass. `./gradlew :shared:domain:detekt` is clean.
- [ ] **Step 5:** Commit `feat(shared): training models, BLE parsers and the session recorder`.

### Task 5: Shared data — APIs and repositories

**Files:**
- Create:
  - `shared/data/.../network/api/TrainingApi.kt`, `GroupChallengeApi.kt`
  - `shared/data/.../repository/TrainingRepositoryImpl.kt`, `GroupChallengeRepositoryImpl.kt`
- Modify: `DataGraph.kt` (`val training`, `val groupChallenges`)

- [ ] **Step 1:** Implement them the way `AriseApi` and `AriseRepositoryImpl` do: `outcomeOf`, with the quote cached in a field and the activities cached.
- [ ] **Step 2:** `./gradlew :shared:data:jvmTest :shared:data:detekt` passes.
- [ ] **Step 3:** Commit `feat(shared): training and group challenge repositories`.

### Task 6: Shared presentation — view models and navigation

**Files:**
- Create in `shared/presentation/.../start/`:
  - `StartViewModel.kt`
  - `LiveSessionViewModel.kt`
  - `GroupChallengesViewModel.kt`
  - `GroupChallengeDetailViewModel.kt`
  - `ProgressViewModel.kt`
- Modify:
  - `navigation/Destinations.kt`: `Tab.START("start")`, keeping `Tab.WALLET`
  - `AppGraph.kt` factories: `start(mode: StartMode)`, `liveSession(activity: TrainingActivity, mode: StartMode)`, `groupChallenges()`, `groupChallenge(id)`, `progress()`
  - `DeepLinkParser`: map `start`
- Test: `shared/presentation/src/jvmTest/.../StartViewModelTest.kt`, `LiveSessionViewModelTest.kt`

**Produces:**
- **`enum class StartMode { TRAIN, CHALLENGE }`**
- **`StartState`:**
  - `activities`, `selected: TrainingActivity?`, `quote: Quote?`, `summary: Loadable<TrainingSummary>?`
  - `groups: Loadable<GroupChallenges>?` and `suggested: Loadable<List<SuggestedChallenge>>?`, both Challenge mode only
  - Suggested challenges reuse whatever `ChallengeRepository` already exposes for `/api/v2/challenges/suggested`. If the shared layer lacks that call, add it to `ChallengeRepository`.
  - `select(activity)` reloads the summary.
- **`LiveSessionViewModel`:**
  - `onSample(channel, value)`, `onFix(fix)`, `pause()`, `resume()`, `stop()`
  - `stop()` uploads and sets `dialog = PostOrSave`
  - `post(caption)`, `keep()`, `retry()`
  - `LiveState(elapsedS, live: Map<Channel, Double?>, distanceM, paused, phase: RECORDING|UPLOADING|SAVED|FAILED, session: TrainingSession?, posted)`
  - `client_session_id` is a UUID made once per view model, so a retry reuses it.
  - `linkCamera(exerciseSessionId, activity, mode)`: a companion helper on `StartViewModel`, `saveCameraSet(exerciseSessionId: Int, startedAt: Instant, durationS: Double)`, which uploads the linked session.

- [ ] **Step 1: Tests with fake repositories:**
  - `select reloads summary`
  - `challenge mode loads groups and suggested; train mode does not`
  - `stop uploads once and offers post or save`
  - `failed upload keeps the session and retry reuses the client id`
  - `post marks posted`
- [ ] **Step 2:** Run. The tests fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `./gradlew :shared:presentation:jvmTest :shared:presentation:detekt :shared:presentation:compileKotlinIosSimulatorArm64` passes.
- [ ] **Step 5:** Commit `feat(shared): Start, live session, group challenge and progress view models`.

### Task 7: Android platform — BLE sensors and Health Connect

**Files:**
- Create:
  - `android_version/app/src/main/kotlin/com/osiris/player/platform/ble/BleSensors.kt`
  - `android_version/app/src/main/kotlin/com/osiris/player/platform/health/HealthConnectImporter.kt`
- Modify:
  - `AndroidManifest.xml`:
    - `BLUETOOTH_SCAN` (`usesPermissionFlags="neverForLocation"`), `BLUETOOTH_CONNECT`, and legacy `BLUETOOTH`/`BLUETOOTH_ADMIN` with `maxSdkVersion=30`
    - `android.permission.health.READ_EXERCISE`, `READ_HEART_RATE`, `READ_SPEED`, `READ_POWER`, `READ_DISTANCE`, `READ_ELEVATION_GAINED`
    - A `<queries>` entry for `com.google.android.apps.healthdata`
    - An `activity-alias` named `ViewPermissionUsageActivity` with the `android.intent.action.VIEW_PERMISSION_USAGE` / `HEALTH_PERMISSIONS` category, plus the `ACTION_SHOW_PERMISSIONS_RATIONALE` filter
  - `gradle/libs.versions.toml` and `android_version/app/build.gradle.kts`: `androidx.health.connect:connect-client`, latest stable

**Produces:**
- `class BleSensors(context)`:
  - `scan(): Flow<List<FoundSensor>>`, where `FoundSensor(address, name, services: Set<Channel>)`
  - `connect(address): Flow<Pair<Channel, Double>>`, which reconnects on drop
  - `hasPermission()` and `permissions(): Array<String>`
- `class HealthConnectImporter(context, training: TrainingRepository)`:
  - `availability(): Availability {READY, NOT_INSTALLED, UNSUPPORTED}`
  - `permissions: Set<String>`
  - `suspend fun import(days = 30): Outcome<Int>`, which returns the number uploaded
  - Exercise types map to keys: RUNNING → run, WALKING → walk, HIKING → hike, BIKING → cycle, BIKING_STATIONARY → indoor_cycle, SWIMMING_* → swim, ROWING* → row, ELLIPTICAL → elliptical, STAIR_* → stairs, HIGH_INTENSITY_INTERVAL_TRAINING → hiit, STRENGTH_TRAINING/WEIGHTLIFTING → strength, YOGA → yoga.

- [ ] **Step 1:** Implement both (no unit tests: platform glue; the parsing and recorder logic is tested in Task 4).
- [ ] **Step 2:** `./gradlew :android_version:app:assembleDebug` builds.
- [ ] **Step 3:** Commit `feat(android): Bluetooth fitness sensors and Health Connect import`.

### Task 8: Android UI — Start tab, Train and Challenge pages

**Files:**
- Create in `android_version/app/src/main/kotlin/com/osiris/player/ui/start/`:
  - `StartScreen.kt`
  - `SpiralCards.kt`
  - `ActivityRibbon.kt`
  - `QuoteBoard.kt`
  - `StartButton.kt`
  - `ResultsRow.kt`
  - `TelemetryCharts.kt`
  - `ChallengeSections.kt`
  - `TrainingPage.kt`
  - `StartIcon.kt`
- Modify:
  - `ui/navigation/OsirisRoot.kt`:
    - Section `Tab.START`, `Routes.START`, `"Start"`, `StartIcon` in place of Wallet.
    - `Routes.WALLET` stays as a pushed route with back.
    - New routes: `TRAINING = "training/{mode}"`, `LIVE = "live/{mode}/{activity}"`, `GROUPS`, `GROUP = "group/{id}"`.
  - `Destination.Section(Tab.WALLET)` opens the wallet route.

- [ ] **Step 1:** Build the screens to the spec layout:
  - Spiral cards: `VerticalPager` with a `graphicsLayer` driven by the page offset `o`:
    - `rotationY = o * 35f`
    - `translationX = sin(o) * 120.dp`
    - `scale = 1 - 0.15 * |o|`
    - `alpha = 1 - 0.4 * |o|`
    - `cameraDistance = 12 * density`
  - Ribbon: a 3D cylinder, with chip angle `= (index - rotation) * 360 / n`.
    - Visible when `cos(angle) > 0`.
    - `rotationY = angle`, `translationX = sin(angle) * radius`, `alpha = cos(angle)`.
    - Auto-rotates at 6°/s and is draggable.
  - Charts: `HorizontalPager` with a cube rotation: `rotationY = -o * 90f`, `transformOrigin` on the near edge.
    - Each chart is a Canvas line with avg/min/max labels and an empty state.
- [ ] **Step 2:** Run the app on the emulator. Check:
  - The tab bar shows Start.
  - The wallet icon opens the wallet.
  - The cards spiral.
  - Train shows the ribbon, quote, start button, results and charts.
  - Challenge shows Osiris, group and suggested challenges.
- [ ] **Step 3:** detekt is clean and the app builds. Commit `feat(android): Start tab with Train and Challenge pages`.

### Task 9: Android UI — live session, group challenges, Progress, camera handoff

**Files:**
- Create in `ui/training/`:
  - `LiveSessionScreen.kt`
  - `PostOrSaveDialog.kt`
  - `SensorsSheet.kt`
  - `GroupChallengesScreen.kt`
  - `GroupChallengeDetailScreen.kt`
  - `CreateGroupChallengeSheet.kt`
- Also create `ui/profile/ProgressSection.kt`.
- Modify:
  - `ProfileScreen.kt`: add the Progress section and the Health Connect import button.
  - `ExerciseCameraScreen.kt` and its nav route: optional `start={mode}`. When set, after the exercise session is saved it calls `saveCameraSet` and shows the PostOrSave dialog.
  - `OsirisRoot.kt`

- [ ] **Step 1: Live session.**
  - It collects `LocationClient.fixes()` for `gps` activities and `BleSensors.connect` for chosen devices.
  - On stop it shows the PostOrSave dialog; on SAVED it pops back to the training page, which reloads the summary.
- [ ] **Step 2: Group challenges.** The list screen tabs, create sheet (with the connections picker), and detail with leaderboard and Join or Leave.
- [ ] **Step 3: Progress.** Activity chips, an 8-week bar chart, and a recent sessions list. A session detail sheet reuses `TelemetryCharts`.
- [ ] **Step 4: Emulator check.**
  - Start a run with a mock GPS route. Live speed and elevation appear.
  - Stop → Just save. The session shows in Results, the charts and Progress.
  - Create a group challenge, then complete a challenge-mode session; progress updates.
  - The Health Connect button shows the permission flow or the not-installed message.
- [ ] **Step 5:** Commit `feat(android): live session, group challenges and Progress`.

### Task 10: iOS compile, full gate, merge

- [ ] **Step 1:** In `ios_version/Osiris/Sources/App/RootView.swift`, the tab switch maps `.start` to `.home`. Commented: the SwiftUI Start screen is not built yet.
- [ ] **Step 2:** Run `.claude/hooks/gate.sh`. It exits 0.
- [ ] **Step 3:** `git checkout master && git merge --no-ff feat/start-screen`, then re-run the gate on master.
