# First Release Implementation Status

**Release:** R0/R1 verified running + R2 course and challenge pilot (non-stakes)
**Status:** Implemented and verified locally. Not yet promoted to SIT (see "Before promotion").
**Economy:** XP and badges only. `entry_crystals` is pinned to 0 per ADR-005; no crystal settlement exists.

## R0/R1 — verified running (delivered earlier)

- `RunSession`, `RoutePoint`, `VerificationDecision` models; migration `7c2a4b1d9e01`.
- `/api/v2/runs` create/start/points/finish/status with contiguous sequences and idempotent finish.
- Server-authoritative distance, duration, speed, gap, accuracy, ordering, and route hash (`run-rules-v1`).
- Explainable rejection reason codes and immutable verification decisions.
- Accepted-run XP and endurance progression.

## R2 — course and challenge pilot (this release)

### Backend (`services/challenges.py`, `main.py`, migration `a3e8d5c2f710`)

| Requirement | Implementation |
|---|---|
| PRD-005 course from a validated run | `POST /api/v2/courses`. Accepted runs only. One course per run (idempotent). 0.4–42.2 km. Duplicate (same owner) and overlap (other owner) detection. Limit of 10 active courses per player. |
| Privacy (ADR-004, Security §2–3) | The first and last 150 m of the run are trimmed before storage, so a course never starts at the owner's door. Public marker = route midpoint snapped to a ~550 m grid cell. Discovery returns no owner, route, or challenger identities. The exact route goes only to the creator and joined players. |
| PRD-006 immutable challenge | `POST /api/v2/challenges`. Terms are hashed (`terms_hash`) and there is no edit path. Idempotent publish key. One open challenge per course. The target is the owner's verified benchmark over the trimmed course. |
| PRD-007 join rules | `POST /api/v2/challenges/{id}/join`. Open challenges only. Challenger needs ≥1 verified run. Players cannot join their own challenge. Idempotent. The terms hash is snapshotted at join. |
| Attempt verification | `POST /api/v2/challenges/{id}/attempts`. The run must start after the join and finish before the close. One run per attempt. The on-course segment is timed from the point closest to the start to the point closest to the finish. Checks start/finish zones (75 m), distance ±15%, route coverage ≥80% within 50 m, and clock skew. A result under 75% of the benchmark goes to human review, not an automatic win. Rejected attempts may retry. |
| Outcomes and rewards | Win: challenge `win_xp`. Verified loss: participation XP, plus defense XP for the creator. Badges: first verified run, course, publish, win, defense. |
| Lifecycle | open → closed at `closes_at` → settled after a 1 h grace period once no review is pending. Driven lazily on read and by an hourly scheduler job. |
| Progression | `GET /api/v2/me/progression`: XP, versioned performance rank (`rank-ladder-v1`: Bronze…Divine), badges, and counts. |
| PRD-008 audit | Append-only `audit_events` for run verification, course registration, publish, join, submit, review, close/settle, and every admin action. No coordinates in details. |
| PRD-010 admin controls | Review queue and accept/reject. Challenge suspend/resume/void (void reverses all XP awards). Course suspension (suspends its live challenges). User suspend/reinstate: every v2 player endpoint refuses a suspended account. Audit search. |
| Errors | v2 errors return `detail: {code, message}` so clients can branch on `code`. |
| Abuse | Rate limits on route upload (120/min) and challenge publish/join/submit (30/min) in non-dev environments. |

### Customer app (`Osiris_customer`)

- Run screen: live time/distance/pace. Challenge course overlay with start/finish zones and safety guidance. Challenge markers replace the legacy exact-domain polygons.
- Durable offline route queue (`services/run_upload_queue.dart`): points are persisted on the phone and survive restarts and outages. A lost upload response is recovered via a server point-count resync. Finish uses a stable idempotency key.
- After an accepted run: submits the challenge attempt, or offers to register a course.
- Challenge board (radius filter), challenge detail (all terms, including free entry, before joining; route preview after joining; result with human-readable reasons), My Courses with publish.
- Dashboard progression card (rank, next-rank progress, badges). Legacy bounty/vault screens hidden behind `--dart-define=OSIRIS_LEGACY_FEATURES=true`.
- Structured v2 error parsing.

### Admin console (`Osiris_admin_web`)

- New Trust & Safety page: review queue, challenge controls, pull course, user suspension, audit log. Every action requires a written reason.
- Fixed: `index.html` loaded the Vite starter template, so the React console never rendered. It now mounts `src/main.tsx`.
- Fixed: admin login omitted the required `device_timestamp`.

## Verification completed (2026-09-26)

- Backend suites, all passing: R2 challenge (6 tests), R1 run, ML referee, v2.10 flows, Phase 2 security, crystal ledger, replay guard, party stats, Stripe.
- Ruff clean. OpenAPI contract regenerated; drift check passes.
- Alembic: fresh DB from zero → head; downgrade R2 → re-upgrade; existing dev DB upgraded.
- Ledger reconciliation passes after all suites (challenges never touch crystals).
- `flutter analyze`: no issues. `flutter test`: passing. `flutter build apk --debug`: succeeds.
- Admin web: `tsc --noEmit` clean; production `vite build` succeeds.
- CI now runs every backend suite plus a post-suite ledger reconciliation.

## Residual risks (owner acceptance required before UAT)

1. **Time evidence is device-sourced.** Point timestamps come from the phone. Clock-skew checks, the speed ceiling, and the outlier review queue mitigate this, but signed chunks, device-integrity signals, and mock-location detection are not built.
2. **Joined players see the exact trimmed route.** Any verified runner can join, so in practice the trimmed course is available to verified runners. The 150 m trim protects endpoints. User-defined privacy zones and a "hide from discovery" setting are not built.
3. **Raw route points have no retention TTL yet.** Security §2 requires one; a retention job must run before pilot.
4. **Suspension is enforced on v2 endpoints only.** The legacy v1 endpoints do not check it; they should be removed or gated before pilot.
5. **SQLite and in-memory rate limits.** ADR-002 requires PostgreSQL/PostGIS for SIT onward. Rate limits are per process.
6. **Admin MFA, refresh-token rotation, and token revocation are not built.**
7. **Mobile foreground-only tracking.** Background location, pause/resume, and battery policy (PRD-002) are not implemented. The run records while the app is in the foreground.

## Before promotion to SIT

- PostgreSQL/PostGIS migration and integration run.
- Route-point retention job; remove or gate legacy v1 domain/siege endpoints.
- Physical-device field test of a full run → course → challenge → attempt loop, including an airplane-mode segment.
- Human sign-off on the residual-risk list above.

## Next release items

- R2 hardening: pause/resume and background tracking, privacy zones, report-a-challenge, device integrity.
- Phase 1 platform: consent ledger, data export/deletion (PRD-009), refresh tokens, admin MFA, observability.
- R3 crystals: blocked on the approved settlement equation (D-ECON-001 / ADR-005).
