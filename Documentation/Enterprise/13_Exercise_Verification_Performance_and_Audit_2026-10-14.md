# Camera-Verified Exercises — Design, Performance Test and Audit — 2026-10-14

**Build:** branch `claude/busy-johnson-twfvqr`.
**Environment:** Linux cloud container, 4 vCPU; Flutter 3.41.9 / Dart 3.11.5; backend = one uvicorn worker, SQLite,
`OSIRIS_ENV=test`. No KVM, no Android SDK download access and no macOS, so **no emulator, simulator or device run
was possible**; device QA is an open `[human]` item in `PLAN.md`.

## 1. What was built

The player opens the camera, ML Kit BlazePose estimates the body pose on the phone, and a rep engine counts
push-ups, squats, lunges, sit-ups, jumping jacks, high knees, and plank holds, judging each rep's genuineness.
Video frames and landmarks never leave the phone and are never stored. The phone uploads a per-set summary; the
server re-checks it and grants capped XP. Exercises never touch Mana Crystals.

| Exercise | Camera | Tracked angle | Rep / hold rule | Position rule |
|---|---|---|---|---|
| Push-up | side | shoulder–elbow–wrist | >150° → <100° → >150° | torso within 40° of horizontal; body line ≥145° |
| Squat | side | hip–knee–ankle | >155° → <110° → >155° | shin within 50° of vertical; hip angle ≥45° |
| Lunge | side | hip–knee–ankle (either leg) | >150° → <115° → >150° | torso within 35° of vertical |
| Sit-up | side | shoulder–hip–knee | >115° → <75° → >115° | hip–ankle within 35° of horizontal |
| Jumping jack | front | hip–shoulder–wrist (both arms) | <50° → >130° → <50° | ankles ≥1.3× hip width at the top; torso vertical |
| High knees | side | shoulder–hip–knee (either leg) | >155° → <115° → >155° | torso within 35° of vertical |
| Plank | side | shoulder–hip–ankle | timed while >160° | torso within 40° of horizontal; must start outside the hold |

These exercises were chosen because each has one joint angle with a large, unambiguous swing in a single camera
view, so a 2D landmark model judges them reliably. Burpees, mountain climbers, and pull-ups were left out: they
need multi-phase recognition or a bar the camera rarely sees.

### Components

| Layer | Files |
|---|---|
| Catalog (single source of truth) | `Osiris_backend/services/exercises.py` → `Osiris_customer/assets/exercise_catalog.json` (`scripts/export_exercise_catalog.py`; drift fails the test suite) |
| Server table | `exercise_sessions` (migration `a7c3e9f2b4d1`), unique per (user, `client_session_id`) |
| API | `GET /api/v2/exercises`, `POST /api/v2/exercise-sessions` (idempotent, rate-limited), `GET /api/v2/me/exercise-sessions` |
| On-device engine | `lib/exercise/rep_engine.dart` (pure Dart, O(1) per frame) |
| On-device storage | `osiris_exercise.db` (sqflite): `exercise_catalog`, `exercise_sessions`, `exercise_reps` |
| Pose source | `lib/exercise/mlkit_pose_source.dart` (camera stream + ML Kit, one frame in flight) |
| UI | `/exercise` hub (Today → Bodyweight), camera screen with skeleton overlay and live counter |

## 2. Genuineness checks

A rep counts only if all of these hold:

| Check | Catches |
|---|---|
| Reaches the peak zone and returns to rest | half reps (`partial_range`) |
| Duration within the exercise's min/max | bouncing, jitter-driven counts (`too_fast`), stalls (`too_slow`) |
| Body position (orientation rule) holds on ≥80% of frames | arm curls while standing counted as push-ups (`wrong_position`) |
| Form rule holds on ≥80% of frames | sagging hips, folded torso, arms-only jumping jacks (`form_break`) |
| Joints visible on ≥70% of rep frames | occluded or out-of-frame reps (`low_visibility`) |
| No joint moves faster than 1000°/s; limb lengths stable (CV ≤0.3) | tracker jumping between people or glitching (`tracking_glitch`) |

Session rules (applied identically on device and server, values shipped in the catalog): at least one valid rep,
≥60% of attempted reps valid, reps per minute under the exercise limit, and rep-duration CV ≥0.03 over 8+ reps
(machine-identical timing → `replay_suspected`). Plank holds need an entry transition and natural micro-motion.

The server never sees video, so it does not trust the device verdict for rewards. It re-checks tempo bounds per
rep, rate, totals against duration, rules version, and replay timing; then caps XP per exercise per day and at
120 XP per day in total, on the server's clock in the player's offset.

## 3. Test results

| Suite | Result |
|---|---|
| `tests/test_exercise_sessions.py` (catalog drift, re-check, idempotency, caps, plank, 422s, rate limit, history, export, erasure, metrics) | 9/9 PASS |
| All 14 existing backend suites, ruff, mypy (CI command + new modules), OpenAPI drift | PASS |
| `flutter test` (46 tests; 33 new: engine, SQLite store/sync, screens) | PASS |
| `flutter analyze` | No issues |
| Full-app Dart compile to kernel (`frontend_server`, plugin registrant included) | 0 errors |
| `.claude/hooks/gate.sh` | exit 0 |

Engine tests replay synthetic skeletons built from joint angles with pixel noise: genuine sets for all seven
exercises, and the cheat cases above.

## 4. Performance

### On-device rep engine (x86-64, Dart JIT, 10-minute sets at 30 fps)

| Exercise | Frames | Cost per frame |
|---|---|---|
| Push-up (300 reps) | 17,791 | 2.2 µs |
| Squat (300 reps) | 23,286 | 2.3 µs |
| Jumping jack (300 reps) | 9,586 | 1.5 µs |
| Plank (600 s) | 18,243 | 1.6 µs |

A 30 fps frame budget is 33 ms; the engine uses well under 0.1% of it even allowing 10× for a phone CPU. The
pipeline's cost is ML Kit inference. It is bounded by design: medium resolution stream, `base` model in stream
mode, and at most one frame in flight, so a slow phone drops frames instead of queueing them and latency stays one
frame deep. Debug builds show measured pose fps, average and max inference time, and dropped frames on the result
sheet; record these on the target devices during device QA.

### On-device storage (sqflite ffi, in-memory)

20 sets with 520 rep rows saved, then history and personal bests read: under the asserted bounds of 2 s and
0.5 s respectively in the test; both are single indexed queries.

### Backend (20 concurrent players, 200 requests per endpoint, one worker, SQLite)

| Endpoint | p50 | p95 | p99 |
|---|---|---|---|
| `GET /api/v2/exercises` | 62 ms | 95 ms | 102 ms |
| `POST /api/v2/exercise-sessions` | 190 ms | 298 ms | 495 ms |
| `GET /api/v2/me/exercise-sessions` | 237 ms | 327 ms | 364 ms |

Single-user p50 is 3–9 ms. All meet the PRD p95 < 500 ms target. Latency at 20 users is queueing on one worker
and SQLite's single writer (see report 12 and ADR-002).

## 5. Audit findings

| # | Area | Finding | Status |
|---|---|---|---|
| 1 | Abuse | `POST /api/v2/exercise-sessions` had no rate limit; a player could insert unlimited rows. | Fixed: 30/min per IP; regression test |
| 2 | Anti-cheat | Standing arm curls satisfied the push-up elbow cycle; standing straight satisfied the plank line. | Fixed before release: orientation rules; tests |
| 3 | Lifecycle | The camera permission prompt makes the app inactive, which would have torn down a camera still starting. | Fixed: only a started camera is released |
| 4 | UI | Result sheet overflowed with several reason lines. | Fixed: scrollable sheet; caught by widget test |
| 5 | Privacy | Frames and landmarks never leave the phone or reach storage; export and erasure include server rows; local rows are removed when another account signs in. | Pass |
| 6 | Trust (residual) | A modified app can upload a plausible forged summary, and a screen replaying a real person's workout passes on-device checks. | Accepted: XP only, ≤120 XP/day, no effect on leaderboards (they rank verified run distance) |
| 7 | Product (decision needed) | README launch principle 1 says push-ups, squats and pose estimation are later increments; this feature contradicts it. | `[human]` item in `PLAN.md` |
| 8 | Device QA | No emulator, simulator or device run was possible in this environment; thresholds are tuned on synthetic data. | `[human]` item in `PLAN.md` |
| 9 | Orientation | Landmarks are upright in 90° steps from the device orientation; a phone propped at a tilt adds error. Orientation rules allow 30–50°. | Accepted; revisit with device recordings |
