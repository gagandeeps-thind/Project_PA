# Start screen — design

Date: 2026-11-02. Owner: Gagan. Status: approved scope (user request 2026-11-02, "I approve it").

## Intent

A Start tab where the player begins any workout. Two big entry cards lead to **Train**, a personal
session tracked live from Bluetooth watches and sensors, and **Challenge**, which runs the same
session but counts it towards challenges.

Every finished session is saved. The player can also post it to the feed. The Profile gains a
**Progress** section with the activity history.

**Success:**
- The player taps Start and picks an activity.
- Live heart rate, power, speed and elevation appear if a sensor or GPS provides them.
- On stop, they choose Post or Just save.
- The session shows in Results, the charts and Profile → Progress.
- In Challenge mode it also advances the group challenges they joined.

## Decisions (user answers)

- **Tab bar.** It becomes Home · Arise · **Start** · Social · Profile.
  - Start takes Wallet's slot in the bar.
  - Wallet becomes a pushed screen, opened from Start's top-right wallet icon. Builds without a wallet hide the icon.
  - The `wallet` deep link still opens it.
- **Telemetry.**
  - Live data comes from Bluetooth LE standard fitness profiles plus phone GPS.
  - Health Connect imports past workouts.
  - No vendor accounts.

## Interpretations (mine, flagged)

- **Extra entry cards.** "2–3 more cards" are Train, Challenge, **Camera coach** (the existing exercise hub) and **Courses** (the existing course board). They reuse existing screens.
- **Group challenge connections.** "Connected Osirians" means people you follow or who follow you.
- **What counts towards a challenge.**
  - Only sessions started from the Challenge page count; they are stored as `mode=challenge`.
  - Segments report Train and Challenge sessions separately ("workouts" vs "challenges").
- **"Challenges from Osiris"** are *official* group challenges. Admins create them; everyone sees and can join them.
- **Suggested challenges** reuse `GET /api/v2/challenges/suggested`, the existing course challenges.
- **Camera exercises** (push-ups and the like) are in the activity list.
  - Choosing one opens the existing camera coach. It counts and verifies reps and saves an `ExerciseSession`.
  - The app then saves a training session linked to that exercise session. The server copies the verified rep count from the link and never trusts the client's reps.
- **iOS.** Only the shared Kotlin layers are built here. The SwiftUI Start screen is out of scope, since this machine cannot build Swift. The iOS tab switch gains the new case so it still compiles.

## Start screen

- **Header.** No title. A wallet icon sits in the top-right.
- **Entry cards.**
  - Four large cards in a vertical pager.
  - A spiral 3D effect: each card's position on a helix drives `rotationY`, a sideways shift, scale and alpha.
  - Tapping a card opens its screen.
- **Tab icon.** A new vector, "ignition": a ring broken at the top with a forward chevron inside, drawn as an `ImageVector`.

## Train and Challenge pages (one composable, `mode` parameter)

1. **Activity ribbon.** A thin ribbon of activity chips on a horizontal 3D cylinder.
   - Chips rotate around the y-axis and turn slowly by themselves.
   - Dragging spins it; tapping a chip pre-selects that activity.
   - The list comes from `GET /api/v2/training/activities`.
2. **Motivation board.** A small card showing a quote from `GET /api/v2/motivation/quote?exclude=<last id>`.
   - It is fetched once per app launch, so it changes every time the app opens.
3. **Start button.** A small circle in the middle.
   - Tap → activity picker (the same list, ribbon choice preselected) → start.
   - Camera activities open the camera coach.
   - All others open the **Live session** screen.
4. **Train only.**
   - **Results**, five tiles:
     - PR
     - Segments (workouts · challenges)
     - Total time
     - Total distance, or total reps for camera activities
     - This week (sessions)
   - **Charts**: heart rate, power, speed and elevation of the latest session for the selected activity.
     - Shown in a horizontal pager with a 3D rotation between cards.
     - Each chart is labelled with avg, min and max.
     - A chart with no data shows a plain empty state ("Connect a heart-rate sensor to see this").
5. **Challenge only.**
   - **Osiris challenges**: official group challenges, shown only if any exist.
   - **Group challenges**: one card.
     - Collapsed, it shows a horizontal row of 3 challenges with a 4th "View all" tile, which opens the Group challenges screen.
     - Tapping the card header expands it in place to list all of them.
   - **Suggested challenges**: a two-column grid, about six cards per screen. Tapping one opens the existing challenge detail.

**Group challenges screen.**
- Tabs: Mine · Invited · From connections.
- "Create" form fields: title, activity, goal metric, target, length in days, and connections to invite.
- **Detail:** the goal, the window, my progress, a leaderboard by progress, and Join or Leave.

## Live session screen

- **Header and live tiles.**
  - Activity name and elapsed time.
  - Live tiles for heart rate, power, speed and elevation; a tile shows "—" until it has a source.
- **Sensors chip.**
  - It scans for BLE devices advertising Heart Rate (0x180D), Cycling Power (0x1818), Running Speed & Cadence (0x1814) or Cycling Speed & Cadence (0x1816).
  - Tapping a found device connects and subscribes to its measurement characteristic.
  - Connected devices reconnect if they drop.
- **Phone GPS.** It runs for outdoor activities (run, walk, hike, trail, cycle) and adds speed, distance and altitude. GPS speed is replaced by sensor speed when a sensor has it.
- **Recording.** Samples are kept in memory, one per channel per second at most.
  - The upload downsamples each channel to ≤ 720 points.
  - Pause and resume are supported.
- **Stop.**
  - Stop opens a summary dialog with Post to feed or Just save.
  - The session is uploaded either way. Post also creates a `workout` post through the existing `POST /api/v2/feed/posts`, with the summary.
  - A failed upload keeps the session and offers Retry.

## Health Connect import

- Profile → Progress has "Import from Health Connect".
- Permissions: read ExerciseSession, HeartRate, Speed, Power, Distance and ElevationGained.
- **What it reads.** Exercise sessions from the last 30 days.
  - Each type maps to an activity key; unmapped types are skipped.
  - Heart rate, speed and power series and the distance and elevation totals are read inside each session's window.
- **Upload.** Each session is uploaded with `source=health_connect`, `mode=train` and `client_session_id = "hc-" + record id`, so re-imports are idempotent.
- **No Health Connect.** If the provider is missing, the button explains and links to the Play listing.

## Profile → Progress

- Activity filter chips (All plus the activities used).
- A weekly duration bar chart for the last 8 weeks.
- A list of recent sessions.
- Tapping a session opens its detail: summary plus the same four charts.

## Backend

### Tables (one migration)

**`training_sessions`**
- Columns:
  - `id`, `user_id`, `client_session_id`
  - `activity_key`, `mode` (train | challenge), `source` (sensor | camera | health_connect)
  - `started_at`, `duration_s`, `distance_m`, `elevation_gain_m`, `reps`
  - `exercise_session_id` (FK, nullable, unique)
  - `hr_avg`/`hr_min`/`hr_max`, `power_avg`/`power_min`/`power_max`, `speed_avg`/`speed_max`, `elev_min`/`elev_max`
  - `series_json`, `devices_json`, `social_post_id` (nullable), `local_date`, `created_at`
- Constraints: unique (user_id, client_session_id); index (user_id, activity_key, started_at).

**`group_challenges`**
- Columns:
  - `id`, `creator_id` (nullable for official), `is_official`, `title`, `activity_key`
  - `metric` (distance_m | duration_s | reps | sessions), `target`
  - `starts_at`, `ends_at`, `status` (active | cancelled), `created_at`
- Ended is derived from `ends_at`.

**`group_challenge_members`**
- Columns: `id`, `challenge_id`, `user_id`, `status` (invited | joined), `invited_by`, `joined_at`.
- Unique (challenge_id, user_id).

### Service `services/training.py` (pure where possible)

- **Activity catalog** (`ACTIVITIES`):
  - The 16 camera exercises from `exercise_rules.BY_KEY`.
  - Plus run, walk, hike, trail, cycle, indoor cycle, swim, row, elliptical, stairs, HIIT, strength and yoga.
  - Each entry has `kind` (camera | gps | sensor), primary `metric`, `max_speed_mps`, and `gps`.
- **Series validation.**
  - Each channel is `[[t_s, value], ...]` with t ascending and within the duration.
  - Values must be in range: HR 25–250, power 0–3000 W, speed 0–max_speed, elevation −500–9000 m.
  - ≤ 720 points per channel, and out-of-range points are dropped.
- **Stats.** Avg, min and max per channel are computed server-side from the series. Elevation gain is the sum of positive steps above 1 m hysteresis.
- **Plausibility.** distance / duration must be ≤ `max_speed_mps`, otherwise 422.
- **PR.** The best primary metric: distance for distance activities, duration for duration activities, reps for camera activities.
- **Group challenge progress.** For each joined member, the sum of the metric over their `mode=challenge` sessions of that activity within [starts_at, ends_at]. `sessions` counts them.

### Endpoints (all `get_active_player` unless noted)

- `GET /api/v2/training/activities` returns the catalog.
- `POST /api/v2/training/sessions` (201).
  - It is idempotent on `client_session_id`.
  - With `exercise_session_id`, the link must be the caller's own `ExerciseSession`; reps and duration are copied from it.
  - It returns the session plus `is_pr`.
- `POST /api/v2/training/sessions/{id}/post` creates the feed post (kind `workout`) and stores `social_post_id`.
  - Idempotent: a second call returns the same post.
- `GET /api/v2/me/training/summary?activity=` returns PR, segments, totals and this week, plus the latest session with its series.
- `GET /api/v2/me/training/sessions?activity=&limit=&offset=` returns the list without series.
- `GET /api/v2/me/training/sessions/{id}` returns the full session; 404 if it is not yours.
- `GET /api/v2/me/training/progress?weeks=8` returns weekly duration and session totals per activity.
- `GET /api/v2/motivation/quote?exclude=` returns `{id, text, author}` from a curated list.
- `GET /api/v2/me/connections` returns followers ∪ following, with display name and avatar.
- **Group challenges.**
  - `GET /api/v2/group-challenges` → `{official, mine, invited, connections}`.
    - Each item includes progress for me, the member count and the top 3.
    - `connections` holds active challenges created by my connections that I am not in.
  - `POST /api/v2/group-challenges`.
    - Invitees must be connections; others are rejected with 422.
    - Invitees get a `PlayerNotification`.
  - `GET /api/v2/group-challenges/{id}`: detail and leaderboard. Visible to members, invitees, the creator's connections, and everyone for official ones. Otherwise 404.
  - `POST /api/v2/group-challenges/{id}/join` and `/leave`.
    - Join is allowed for official, invited, or a connection of the creator, while active.
    - The creator cannot leave; they cancel instead (`POST /{id}/cancel`).
- `POST /api/v2/admin/group-challenges` (admin) creates an official challenge. `GET /api/v2/admin/group-challenges` lists them.

**Errors:**
- `HTTPException` with 404 for not found or not visible.
- 403 for a foreign exercise-session link.
- 409 for a join after the end or a cancel.
- 422 for validation.

### Admin web

An "Official challenges" page lists and creates official group challenges.

## App architecture (KMP)

- **shared/domain**
  - Models: `TrainingActivity`, `TrainingSession`, `TrainingSummary`, `SeriesPoint`, `Quote`, `GroupChallenge`, `GroupChallengeDetail`, `Connection`, `WeeklyProgress`.
  - Pure `TrainingRecorder`: collects samples per channel at most once per second, tracks pause, computes distance from fixes and downsamples to 720 points.
  - `BleParsers`: decode Heart Rate Measurement, Cycling Power Measurement, RSC Measurement, and CSC Measurement (wheel revolutions → speed with a 2.105 m wheel).
- **shared/data**
  - `TrainingRepository` (+Api): activities (cached), summary, sessions, upload, post, progress, quote (once per process), connections.
  - `GroupChallengeRepository` (+Api).
- **shared/presentation**
  - `StartViewModel` (activities, quote, summary for the selected activity, and in Challenge mode the group, official and suggested challenges).
  - `LiveSessionViewModel` (recorder, sensor and GPS inputs, stop → upload → post choice).
  - `GroupChallengesViewModel`, `GroupChallengeDetailViewModel`, `ProgressViewModel`.
- **android_version**
  - `ui/start/`: StartScreen, SpiralCards, ActivityRibbon, QuoteBoard, StartButton, ResultsRow, TelemetryCharts, ChallengeSections.
  - `ui/training/`: LiveSessionScreen, PostOrSaveDialog, GroupChallengesScreen, GroupChallengeDetailScreen, CreateGroupChallengeSheet.
  - `ui/profile/ProgressSection`.
  - Platform code: `platform/ble/BleSensors.kt` (scanner and GATT client exposing a flow of readings) and `platform/health/HealthConnectImporter.kt`.
  - Manifest: Bluetooth scan and connect permissions (API 31+, `neverForLocation`), legacy Bluetooth up to API 30, Health Connect read permissions, and the Health Connect permissions rationale activity alias.
  - Dependency: `androidx.health.connect:connect-client`.

## Testing

- **Backend:** `tests/test_training.py` covers:
  - Catalog
  - Upload stats computed server-side
  - Out-of-range points dropped
  - Implausible speed rejected
  - Idempotency
  - The camera link: foreign is 403, and verified reps are copied
  - PR and segments
  - Summary, list, detail and foreign 404
  - Progress weeks
  - Post idempotency
  - Quote exclude
  - Connections
  - Group create, with non-connection invites rejected
  - Visibility, join and leave rules
  - Challenge-mode credit only
  - Leaderboard order
  - Official admin create, with players forbidden

  The suite is added to `gate.sh` and `ci.yml`. The OpenAPI contract is regenerated.
- **Kotlin:**
  - jvmTest for the BLE parsers, the recorder (rate limit, pause, downsample, distance) and series stats.
  - StartViewModel and LiveSessionViewModel tests with fakes, following the house pattern.
- **Emulator:**
  - The Start tab, spiral cards, ribbon, quote, Train and Challenge pages, and the live session with mock GPS.
  - The post/save dialog, Progress, group challenge create, join and view, and the Health Connect permission flow.
  - BLE shows "no sensors found" on the emulator; the parsers are covered by tests.

## Out of scope

- The SwiftUI Start screen.
- Wear OS companion app.
- Calories.
- Live sharing.
- Crystals: Start-page challenges never touch crystals, per the ledger rule.
- XP for training sessions (personal sessions are unverified).
