# Camera-Verified Exercises, Phase 2 — Launch Test, Performance and Audit — 2026-10-15

**Build:** branch `claude/busy-johnson-twfvqr` after PR #3 (phase 1, report 13) merged.
**Environment:** Linux cloud container; Flutter 3.41.9; backend = one uvicorn worker, SQLite, `OSIRIS_ENV=dev`;
Chromium (Playwright 1.56). Still no KVM, no Android SDK download access and no macOS: **no Android emulator or
iOS simulator run was possible.** The customer app was launched as a Flutter **web** build in Chromium instead;
that renders the real widget tree and talks to the real API, but has no camera pose model (ML Kit is mobile-only).

## 1. Delivered

| Item | What |
|---|---|
| ML/health-data consent (backlog Phase 5) | `exercise_camera` kind in the append-only consent ledger; `GET/PUT /api/v2/me/exercise-consent`; uploads refused without it (403 `EXERCISE_CONSENT_REQUIRED`); withdrawal can erase the stored sets; app consent sheet before the camera opens; Settings switch with keep/delete choice |
| Review queue | `GET /api/v2/admin/exercise-sessions` (evidence: rep timings and variation, reasons, player history, XP if approved; `user_id` filter) and `POST …/{id}/review` (approve with capped XP / reject; decided once; audited); admin page *Exercise review*; the app pulls review outcomes into local history |
| Resilience | Exercises keep working when the phone's database cannot open; a set that cannot be saved is reported as such |

## 2. Launch test (real browser, real API)

### Admin console (React, production build)

Login → *Exercise review* → flagged squat set (12 reps, identical 1.25 s timings, "Machine-regular rep timing")
→ *Approve (+12 XP)* → note → confirm → "Set #4 verified (+12 XP)". Zero console errors.

### Customer app (Flutter web, release build, driven through the accessibility tree)

| Step | Result | Time |
|---|---|---|
| Boot to login | renders | 1.4–2.1 s |
| Log in → Today ("Hi Ada E2E", quest, week, tiles incl. *Bodyweight*) | pass | 2.5–3.0 s |
| Bodyweight hub: all 7 exercises listed, consent gate shown | pass | 0.5 s |
| Tap Push-up → consent sheet (on-device processing, what is kept, how to withdraw) | pass | 0.2 s |
| Allow → server ledger records consent; camera screen opens | pass (camera unavailable on web, as expected) | 0.6 s |
| Settings → *Camera exercise counting* switch on | pass | 1.4 s |

5 consecutive runs: 4 pass every assertion, 1 failed at the login tap (Flutter web moves accessibility nodes when a
text field loses focus; the harness tap landed on the old position). Page errors in passing runs: none.

**Bug found by this launch:** on a platform without the SQLite plugin the hub showed an error instead of the
exercises, and a set that failed to save was reported as "Saved on your phone". Fixed (see §4, #3).

## 3. Performance

| Measurement | Before | After |
|---|---|---|
| Admin review queue, 100 rows (single worker, reused client) | 59 ms p50 | 22 ms p50 |
| Admin review queue, 500 rows | 287 ms p50 | 69 ms p50 |
| `GET /api/v2/me/exercise-consent` | — | 3.9 ms p50 |
| `PUT /api/v2/me/exercise-consent` (no change) | — | 6.7 ms p50 |

20 concurrent players (now including the consent check on upload): `GET /api/v2/exercises` p95 137 ms,
`POST /api/v2/exercise-sessions` p95 380 ms, `GET /api/v2/me/exercise-sessions` p95 484 ms. All under the 500 ms
PRD target. The history read is close to it at this concurrency on one SQLite worker. ADR-002's PostgreSQL move
and more workers are the remedy, not this endpoint.

A note on method: an earlier measurement showed 55 ms for trivial reads. That was the test client opening a new
connection and TLS context per call; with a reused client the same endpoint serves in 4–6 ms.

Web build: `main.dart.js` 3.3 MB (0.98 MB gzipped) plus the 7.2 MB CanvasKit renderer. Built with
`--no-web-resources-cdn` because this network blocks `www.gstatic.com`. Admin bundle: 287 KB.

## 4. Audit findings

| # | Area | Finding | Status |
|---|---|---|---|
| 1 | Privacy / consent | Pose processing and storing rep timings (health data) had no explicit consent; backlog Phase 5 requires it. | Fixed: ledger-backed consent, server-enforced; tests both sides |
| 2 | Trust | Sets flagged `review` had no reviewer and stayed without an outcome. | Fixed: review queue; decided once via conditional update; audited |
| 3 | Resilience / honesty | Database failure took the feature down; "Saved on your phone" shown when the save failed. | Fixed; tests |
| 4 | Performance | Review queue ran one earnings query per row. | Fixed: one per player-day; 4.2× faster at 500 rows |
| 5 | Test reliability | The review test assumed a clean DB; a perf backlog broke it after a commit. `gate.sh` does not run the exercise suite (CI wiring is a `[human]` item), so nothing caught it automatically. | Fixed the test (`user_id` filter). CI wiring remains `[human]` |
| 6 | Platform | Web is not a player platform: no ML Kit, no SQLite. It is used only for UI smoke tests. | Accepted |
| 7 | Device QA | Thresholds remain tuned on synthetic skeletons; no device run. | Open `[human]` |

## 5. How to rerun the launch test

Build the admin console with `VITE_API_BASE_URL=http://127.0.0.1:8765` and the customer app with
`flutter build web --release --no-web-resources-cdn --dart-define=API_BASE_URL=http://127.0.0.1:8765`. Run the
API with `OSIRIS_CORS_ORIGINS=http://127.0.0.1:8080,http://127.0.0.1:4173`, serve `build/web` on 8080 and
`vite preview` on 4173. Launch Chromium with `--enable-unsafe-swiftshader` and the `en-US` locale, then enable
Flutter semantics by clicking `flt-semantics-placeholder`. The scripts were run ad hoc and are not committed;
adopting a browser E2E suite is part of the open tooling decision in `PLAN.md`.
