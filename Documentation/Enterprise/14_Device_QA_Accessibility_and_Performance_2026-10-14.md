# Device QA, Accessibility and Performance — 2026-10-14

**Build:** `master` at `8d58c4b` (camera-verified exercises merged as PR #3) plus the commits below.
**Environment:** Android emulator `test_device` (Android 17 / API 37, x86_64, software GPU, back camera = virtual
scene, front camera = synthetic pattern); backend: one uvicorn worker, SQLite (WAL), `OSIRIS_ENV=dev`.

## 1. Gate on the merged code

All 15 backend suites (13 in CI, plus GDPR and exercise sessions, which CI does not list yet), ruff, mypy, Alembic
upgrade (including the exercise-sessions migration), OpenAPI drift, admin `npm run build`, `flutter analyze`, and
`flutter test` passed. The ledger check reports only the five pre-existing dev-DB rows already logged as a `[human]`
item.

## 2. First device run of camera-verified exercises

Report 13 recorded that no device run had been possible. Results on the emulator:

| Check | Result |
|---|---|
| Exercise hub and privacy note | Pass |
| Camera permission: allow | Pass: preview starts (virtual scene) |
| Camera permission: deny | **Defect, fixed:** no way to settings; allowing the camera there and returning still showed the error. A first fix re-asked for permission at once. Now: one denial, OPEN SETTINGS, retry only on return from settings |
| ML Kit pose detection runs | Pass: no errors; with no person in view the HUD says "Move so your whole body is in view" and counts nothing |
| Pose throughput (emulator x86, debug) | 5.1 fps, 164 ms average inference, 2.1 s first frame (model warm-up). Not representative of phones, where ML Kit typically runs at 15–30 fps |
| CPU and memory during a set | About one core of four; PSS steady at 334–350 MB over a minute (no growth) |
| Release after leaving the screen | Camera released (no active camera clients); native heap 117 → 64 MB; about 36 MB stays resident (ML Kit library) |
| Zero-rep set | Reported "Not verified, no XP"; the summary is still uploaded (see open items) |

Counting real reps needs a person in front of the camera. Physical-device QA (Android and iPhone) remains a
`[human]` item.

## 3. Accessibility audit

`test/accessibility_test.dart` renders home, sign-up steps 1–3, login, exercise hub, settings, My Courses and
challenge detail with the real theme in a full-height phone viewport. It checks Flutter's Android tap-target (48 dp),
labelled-tap-target and WCAG AA contrast guidelines. Each check first asserts that the screen's real content
rendered.

| Finding | Fix |
|---|---|
| Home footer text contrast 3.62 (minimum 4.5) | Lighter text |
| Icon buttons without a screen-reader label: copy invite link, sign-up back, bounty refresh | Tooltips |
| Leaderboard toggle subtitle "Off: …" read like the current state | "When off, …" |

The audit fails on three screens without these fixes. A deliberately bad control fails all three guidelines, so the
checks are live.

## 4. New safety feature: low-light warning

Security plan §3 asks for lighting warnings. The app computes the sun's elevation on the phone (NOAA equations; no
network; the location stays on the device). Below civil twilight (−6°), START asks first, with advice on lit routes,
visibility, and telling someone the route. The runner can still start. Unit tests cover solar-noon geometry, a
published Halifax sunrise, night and day, and midnight sun and polar night. Verified on the emulator at night.

## 5. Release build

| Metric | Before exercises (2026-10-12) | After exercises | After fix |
|---|---|---|---|
| APK, universal | 53 MB | 99.7 MB | — |
| APK, arm64 (typical phone download) | — | 43.7 MB | — |
| Cold start (x86_64, `am start -W`) | 0.83–1.03 s | 1.08–1.22 s | 0.88–1.10 s |
| Idle memory (PSS) | 76 MB | 86 MB | 86 MB |

The cold-start regression came from opening the exercise database on every launch. The database now opens only
when the signed-in account changes. The size growth is ML Kit's bundled pose model.

## 6. Open items needing a decision

- Product: should a zero-rep set upload a row? It earns nothing and counts against the upload rate limit.
- Size: ML Kit's pose detection is bundled into the app. Google's Play Services-delivered model would shrink the
  download, but it needs a dependency change (lockfile) and the model downloads on first use.
- Physical-device QA of rep counting on Android and iPhone (existing `[human]` item).
