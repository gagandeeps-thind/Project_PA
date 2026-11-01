# Osiris — Architecture, UI Redesign & Full-Stack Implementation Plan

## 1. Executive Summary & Goal

Redesign the **Osiris Home Screen** and expand the platform into a complete social fitness RPG where players:
1. Receive in-app **Osiris Notifications** (top-right bell icon with unread badge: feature suggestions, app updates, challenge outcomes, social interactions).
2. Browse and join **Suggested Global Challenges** via an interactive **circular-floating card deck** (challenge name, 1-line description, and one-tap **Join Challenge** button).
3. Launch a **Streak Start Workout Customizer** directly from Home — picking GPS activities (`run`, `walk`, `sprint`, `domain_claim`) or **16 camera-verified exercises** with customizable **sets × reps / hold targets** (e.g., `Push-ups — 10 × 3`, `Squats — 15 × 4`, `Plank — 60s × 3`), powered by fast, local on-device pose estimation on both Android and iOS.
4. Discover **Suggested Osirians** in an Instagram-style horizontal swipe carousel with avatar/profile picture, display name, rank/trending badge, **Follow** button, top-right **`×` dismiss** button, and a **`See All`** screen showcasing influential and trending Osirians.
5. Scroll through **People's Posts** — a rich social community feed where Osirians post verified workouts, acquired/claimed domains, active streaks, Mana Crystal earnings, and custom captions/photos, and where players can **react** (`fire`, `like`, `clap`, `crown`), **comment**, and **share** internally on Osiris or externally to other social apps.

All existing Today features (**Daily Quest hero card**, **Weekly Streak strip**, **Tomorrow preview**, and **Shortcuts**) remain preserved and integrated seamlessly into the new Home Screen layout.

---

## 2. Home Screen Layout & Visual Architecture

```
+-------------------------------------------------------------------+
|  Osiris                             [Bell Icon + Unread Badge] [⚙] |
|  Hi <DisplayName> · <Rank> <Identity> · <XP> XP                   |
+-------------------------------------------------------------------+
|  [1] SUGGESTED CHALLENGES (Circular-Floating Card Deck)           |
|      ╭─────────────────────────────────────────────────────╮      |
|    ╭─┤  🌍 Global 5K Surge / 100 Push-up Blitz             ├─╮    |
|    │ │  "Complete 5 km anywhere this week to earn +120 XP" │ │    |
|    │ │  [ Join Challenge ]                     248 joined  │ │    |
|    ╰─┴─────────────────────────────────────────────────────┴─╯    |
|      (Swipe left/right circularly with scale, depth & tilt)       |
+-------------------------------------------------------------------+
|  [2] STREAK START — WORKOUT & DOMAIN CUSTOMIZER                   |
|      🔥 Start / Extend Your Streak                     [Customize] |
|      • Mode: [Camera Exercises] | [GPS Run/Walk] | [Claim Domain] |
|      • Exercise Picker (16 camera-verified exercises)             |
|      • Measure Customizer: Reps/Hold × Sets (e.g. 10 × 3)         |
|      [ ▶ Start Verified Workout (Push-ups · 10 × 3) ]             |
+-------------------------------------------------------------------+
|  [3] TODAY'S QUEST & WEEKLY STREAK STRIP (Existing Core Loop)     |
|      • Daily Quest Hero Card (72sp focal distance + progress bar) |
|      • Weekly Goal & Streak Strip + Tomorrow & Shortcuts          |
+-------------------------------------------------------------------+
|  [4] SUGGESTED OSIRIANS                         [See All ->]      |
|      ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         |
|      │          [×] │  │          [×] │  │          [×] │         |
|      │   (Avatar)   │  │   (Avatar)   │  │   (Avatar)   │         |
|      │  Aria Vance  │  │  Kaelen Vos  │  │  Mira Solis  │         |
|      │  🔥 14d · S  │  │  ⚡ Top 1%   │  │  🏆 3.2 km²  │         |
|      │  [ Follow ]  │  │  [ Follow ]  │  │  [ Follow ]  │         |
|      └──────────────┘  └──────────────┘  └──────────────┘         |
+-------------------------------------------------------------------+
|  [5] PEOPLE'S POSTS (Community Feed)            [+ Create Post]   |
|      ┌─────────────────────────────────────────────────────────┐  |
|      │ (Avatar) Kaelen Vos · Diamond Vanguard · 2h ago         │  |
|      │ "Crushed morning sets & locked down DeWolf Park loop!"  │  |
|      │ ╭─────────────────────────────────────────────────────╮ │  |
|      │ │ 🏋️ Push-ups · 10 × 3 Verified (30 reps · 96% form) │ │  |
|      │ │ 🗺️ Domain Claimed · 0.42 km² · +42 XP · 🔥 12d     │ │  |
|      │ │ 💎 +25 Mana Crystals Earned                         │ │  |
|      │ ╰─────────────────────────────────────────────────────╯ │  |
|      │ [🔥 24] [❤️ 12] [👏 8]   [💬 5 Comments]   [↗ Share]    │  |
|      └─────────────────────────────────────────────────────────┘  |
+-------------------------------------------------------------------+
```

---

## 3. Research: Camera-Verified Exercises & On-Device Pose Estimation

### 3.1 On-Device ML Models for Super-Fast Pose Estimation

To guarantee zero-upload privacy, sub-20ms frame inference, and smooth 30–60 FPS skeleton tracking on mobile devices:

1. **Android (`android_version`)**:
   - **Engine**: **Google ML Kit Pose Detection (BlazePose MobileNet / Heavy TFLite pipeline)** in `STREAM_MODE` with `PREFERRED_HARDWARE_ACCELERATION` (GPU / NNAPI delegate) coupled with **CameraX `ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST`** at 640×480 4:3.
   - **Optimization**: Pre-warm the detector when opening the workout customizer/camera, reuse single-frame buffers with zero-copy `InputImage.fromMediaImage`, and expose real-time FPS, latency, and multi-set progress (`Set 1 of 3 · 10 reps`).
2. **iOS (`ios_version`)**:
   - **Engine**: **Apple Vision `VNDetectHumanBodyPoseRequest` (Apple Neural Engine / ANE accelerated)** on `kCVPixelFormatType_420YpCbCr8BiPlanarFullRange` 640×480 buffers with `alwaysDiscardsLateVideoFrames = true`.
   - **Optimization**: Reuse a warm `VNSequenceRequestHandler` across frames on a dedicated high-priority serial capture queue (`qos: .userInteractive`) for <8ms ANE inference latency on iPhone.

### 3.2 Complete Catalog of 16 Camera-Verifiable Bodyweight Exercises

Every exercise below uses the 13 tracked BlazePose/Vision landmarks (`nose`, `left/right_shoulder`, `left/right_elbow`, `left/right_wrist`, `left/right_hip`, `left/right_knee`, `left/right_ankle`) and is verified both on-device (`RepEngine.kt`) and server-side (`Osiris_backend/services/exercises.py`):

| # | Key | Name | Kind | Camera | Tracked Metric (Joints) | Rest Zone | Peak Zone | Form & Orientation Rules |
|---|---|---|---|---|---|---|---|---|
| 1 | `pushup` | Push-up | `reps` | `side` | `shoulder–elbow–wrist` (`best`) | `> 150°` | `< 100°` | `body_line` (`shoulder–hip–ankle >= 145°`), horizontal `<= 50°` |
| 2 | `squat` | Squat | `reps` | `side` | `hip–knee–ankle` (`best`) | `> 155°` | `< 110°` | `torso_upright` (`shoulder–hip–knee >= 45°`), vertical `<= 65°` |
| 3 | `lunge` | Lunge | `reps` | `side` | `hip–knee–ankle` (`min`) | `> 150°` | `< 115°` | vertical `shoulder–hip <= 45°` |
| 4 | `situp` | Sit-up | `reps` | `side` | `shoulder–hip–knee` (`best`) | `> 115°` | `< 75°` | horizontal `hip–ankle <= 45°` |
| 5 | `jumping_jack` | Jumping Jack | `reps` | `front` | `hip–shoulder–wrist` (`mean`) | `< 50°` | `> 130°` | `ankle_spread >= 0.7` at peak, vertical `<= 45°` |
| 6 | `high_knees` | High Knees | `reps` | `side` | `shoulder–hip–knee` (`min`) | `> 155°` | `< 115°` | vertical `shoulder–hip <= 45°` |
| 7 | `plank` | Plank | `hold` | `side` | `shoulder–hip–ankle` (`best`) | `< 140°` | `> 160°` | horizontal `shoulder–hip <= 50°` |
| 8 | `glute_bridge` | Glute Bridge | `reps` | `side` | `shoulder–hip–knee` (`best`) | `< 135°` | `> 162°` | horizontal `shoulder–hip <= 50°` |
| 9 | `calf_raise` | Calf Raise | `reps` | `side` | `hip–knee–ankle` (`best`) | `< 168°` | `> 175°` | vertical `shoulder–hip <= 35°` (or knee-extension peak) |
| 10 | `shoulder_press` | Pike / Overhead Press | `reps` | `front` | `shoulder–elbow–wrist` (`mean`) | `< 95°` | `> 155°` | vertical `shoulder–hip <= 45°` |
| 11 | `tricep_dip` | Tricep Dip | `reps` | `side` | `shoulder–elbow–wrist` (`best`) | `> 150°` | `< 105°` | vertical `shoulder–hip <= 55°` |
| 12 | `mountain_climber` | Mountain Climber | `reps` | `side` | `shoulder–hip–knee` (`min`) | `> 145°` | `< 105°` | horizontal `shoulder–hip <= 50°` |
| 13 | `leg_raise` | Lying Leg Raise | `reps` | `side` | `shoulder–hip–ankle` (`best`) | `> 150°` | `< 110°` | horizontal `shoulder–hip <= 40°` |
| 14 | `wall_sit` | Wall Sit | `hold` | `side` | `hip–knee–ankle` (`best`) | `> 145°` | `< 115°` | vertical `shoulder–hip <= 40°` |
| 15 | `side_jack` | Star / Lateral Raise | `reps` | `front` | `hip–shoulder–elbow` (`mean`) | `< 45°` | `> 95°` | vertical `shoulder–hip <= 40°` |
| 16 | `burpee` | Burpee (Full Squat-Thrust) | `reps` | `side` | `shoulder–hip–knee` (`best`) | `> 155°` | `< 95°` | full hip flexion-to-extension cycle |

### 3.3 Multi-Set Workout Customizer (`reps × sets` / `hold_s × sets`)
- Players can customize any workout before starting:
  - **Exercise / Activity**: Run, Walk, Claim Domain, or any of the 16 Camera Exercises.
  - **Target Reps / Hold / Distance**: e.g., `10 reps` (or `45s hold`, or `3.0 km`).
  - **Target Sets**: e.g., `3 sets` (`10 × 3 = 30 total reps`), with an automatic rest timer between sets and per-set verification uploads.

---

## 4. Database Schema & Backend API Design

### 4.1 New SQLAlchemy Models (`Osiris_backend/models.py`) & Alembic Migration
1. **`PlayerNotification` (`player_notifications`)**:
   - `id`, `user_id` (nullable for global broadcast notifications or per-user rows), `kind` (`feature_suggestion`, `app_update`, `challenge_update`, `social_follow`, `post_reaction`, `post_comment`, `streak_reminder`), `title`, `body`, `action_route` (optional deep link/route), `read_at` (nullable), `created_at`.
2. **`UserFollow` (`user_follows`)**:
   - `id`, `follower_id`, `followed_id`, `created_at` (Unique `follower_id, followed_id`).
3. **`DismissedSuggestion` (`dismissed_suggestions`)**:
   - `id`, `user_id`, `dismissed_user_id`, `created_at` (Unique `user_id, dismissed_user_id` so clicking `×` permanently hides that Osirian from suggestions).
4. **`SocialPost` (`social_posts`)**:
   - `id`, `user_id`, `kind` (`workout`, `run`, `domain_claim`, `streak`, `crystal_earn`, `custom`), `caption`, `media_url` (optional image/card attachment), `workout_summary_json` (JSON with exercise_key, sets, reps_per_set, total_reps, hold_s, distance_m, domain_area_sqkm, streak_days, crystals_earned, xp_earned), `related_run_id`, `related_exercise_session_id`, `related_domain_id`, `visibility` (`public`, `followers`), `share_count`, `created_at`.
5. **`PostReaction` (`post_reactions`)**:
   - `id`, `post_id`, `user_id`, `reaction` (`fire`, `like`, `clap`, `crown`), `created_at` (Unique `post_id, user_id`).
6. **`PostComment` (`post_comments`)**:
   - `id`, `post_id`, `user_id`, `body`, `created_at`.
7. **`PlayerProfile` additions**:
   - `avatar_url` (optional profile picture URL / preset avatar key), `bio` (optional 1-line bio).

### 4.2 New / Updated Backend Endpoints (`Osiris_backend/growth_feed.py` & existing routers)
- **Notifications**:
  - `GET /api/v2/me/notifications` — returns notifications (including seeded/system feature suggestions & app updates for new users) + `unread_count`.
  - `POST /api/v2/me/notifications/{id}/read` & `POST /api/v2/me/notifications/read-all` — marks notifications read.
- **Suggested Global Challenges (Card Deck)**:
  - `GET /api/v2/challenges/suggested` — returns global open challenges (joinable from anywhere, plus featured challenges) with `id`, `title`, `one_line_description`, `course_distance_m`, `win_xp`, `participants`, `joined`.
  - `POST /api/v2/challenges/{id}/join` — existing endpoint (enhanced so global suggested challenges can be joined with one tap from the Home deck).
- **Streak Start & Multi-Set Workouts**:
  - `GET /api/v2/exercises` — returns the expanded 16-exercise catalog.
  - `POST /api/v2/exercise-sessions` — accepts optional `set_index`, `target_sets`, `target_reps` in metrics and optionally auto-creates a `SocialPost` when `auto_post=True`.
  - `POST /api/v1/domains` — claims a GPS loop domain with defense feat proof and can be shared directly to `SocialPost`.
- **Suggested Osirians & Follow Graph**:
  - `GET /api/v2/osirians/suggested?limit=12` — returns suggested Osirians (excluding self, already-followed, blocked, and `DismissedSuggestion` rows), ranked by influence/trending workout score.
  - `GET /api/v2/osirians/trending?limit=50` — backs the **"See All"** screen, returning influential and trending Osirians by recent verified workouts, streaks, XP, and follower count.
  - `POST /api/v2/osirians/{user_id}/follow` & `DELETE /api/v2/osirians/{user_id}/follow` — follow/unfollow an Osirian (emits a notification).
  - `POST /api/v2/osirians/{user_id}/dismiss` — records a `DismissedSuggestion` when the user taps `×`.
- **People's Posts (Social Feed)**:
  - `GET /api/v2/feed/posts?limit=25&offset=0` — paginated feed of public & followed Osirians' posts with author profile (name, avatar, rank, title), workout/domain/streak/crystal payload, reaction counts, viewer's reaction, comment count, and recent comments.
  - `POST /api/v2/feed/posts` — create a post (manual or one-tap after a run, camera workout, streak milestone, crystal earn, or domain claim).
  - `POST /api/v2/feed/posts/{post_id}/react` — toggle/set reaction (`fire`, `like`, `clap`, `crown`).
  - `GET /api/v2/feed/posts/{post_id}/comments` & `POST /api/v2/feed/posts/{post_id}/comments` — list and add comments.
  - `POST /api/v2/feed/posts/{post_id}/share` — increments share count and mints a shareable deep link / external share text for Osiris or external social apps.

---

## 5. Task Checklist

### Phase 1: Backend Catalog, Models, Migrations & Endpoints
- [x] **backend-catalog**: Expand `Osiris_backend/services/exercises.py` to 16 camera-verified exercises and sync `shared/assets/exercise_catalog.json` via `scripts/export_exercise_catalog.py --write`.
- [x] **backend-models-migration**: Add `PlayerNotification`, `UserFollow`, `DismissedSuggestion`, `SocialPost`, `PostReaction`, `PostComment`, and `PlayerProfile.avatar_url` to `Osiris_backend/models.py` and create the Alembic migration in `Osiris_backend/alembic/versions/`, upgrading `fitness_mvp.db` to `head` and cleaning any orphan ledger rows so `reconcile_ledger.py --check` exits 0.
- [x] **backend-social-feed-api**: Implement `Osiris_backend/growth_feed.py` (Notifications, Suggested Global Challenges, Suggested & Trending Osirians, Follow/Dismiss, People's Posts, Reactions, Comments, Share, Domain Claim post hook) and mount it in `Osiris_backend/main.py`.
- [x] **backend-openapi-tests**: Regenerate `Documentation/openapi.json` (`python scripts/check_openapi_drift.py --write`) and add comprehensive backend tests in `Osiris_backend/tests/test_home_social_feed.py` plus update `Osiris_backend/tests/test_exercise_sessions.py`.

### Phase 2: Shared KMP Domain, Data & Presentation Layer
- [x] **shared-models-api**: Add domain models (`NotificationItem`, `SuggestedChallenge`, `WorkoutPlan`, `SuggestedOsirian`, `FeedPost`, `PostCommentItem`, `DomainClaimDraft`) and API methods in `shared/domain` and `shared/data`.
- [x] **shared-pose-rep-engine**: Update `RepEngine.kt`, `ExerciseCopy.kt`, and `ExerciseCatalog.kt` tests to support all 16 exercises and multi-set (`reps × sets` / `hold × sets`) workout tracking.
- [x] **shared-home-viewmodel**: Enhance `TodayViewModel` (and supporting ViewModels for Notifications, Trending Osirians, Workout Customizer, Domain Claiming, and Post Comments/Creation) so both Android and iOS share 100% of the state management and business logic.

### Phase 3: Android Compose UI & ML Kit Pose Optimization
- [x] **android-pose-optimization**: Optimize `PoseAnalyzer.kt` and `ExerciseCameraScreen.kt` for multi-set workouts (`Set X of Y · Target Reps`) and low-latency stream processing.
- [x] **android-home-redesign**: Redesign `TodayScreen.kt` and navigation routes (`OsirisRoot.kt`) with:
  - Top-right Notification bell + badge & Notifications sheet/screen
  - Circular-floating Suggested Challenges card deck with 1-line description & Join button
  - Streak Start Workout Customizer (Run, Walk, Claim Domain, 16 Camera Exercises, `10 × 3` sets/reps selector)
  - Suggested Osirians horizontal swipe row (`Follow`, `×` dismiss, `See All` trending sheet/screen)
  - People's Posts feed (workouts, domains, streaks, crystal earnings, reactions, comments, internal & external share, and post composer)

### Phase 4: iOS SwiftUI UI & Vision Pose Optimization
- [x] **ios-pose-optimization**: Optimize `PoseCamera.swift` (warm `VNSequenceRequestHandler`) and `ExerciseCameraView.swift` for multi-set workouts.
- [x] **ios-home-redesign**: Update `TodayView.swift` and `Navigator.swift` with the matching Notification bell, Circular Suggested Challenges deck, Streak Start Workout Customizer, Suggested Osirians carousel (`Follow`, `×`, `See All`), and People's Posts feed + composer.

### Phase 5: Verification & Quality Gate
- [x] **verification-gate**: Run `ruff check .`, `alembic upgrade head`, `reconcile_ledger.py --check`, `check_openapi_drift.py`, all backend test suites, and `./gradlew detekt :shared:core:jvmTest :shared:domain:jvmTest :shared:data:jvmTest :shared:presentation:jvmTest` until every check passes cleanly.

### Real-Device / External Service QA (Requires Physical Hardware / Live Cloud Credentials)
- [ ] **[human] device-qa-camera-pose**: Validate live camera lighting & floor-stand angles for the 16 exercises on a physical Android phone and physical iPhone.
- [ ] **[human] device-qa-background-gps**: Validate a 60-minute outdoor GPS run & domain loop trace with the screen locked on a physical Android/iOS device.
