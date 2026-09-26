# Osiris Product Charter and PRD

## 1. Product definition

Osiris is a health-improvement system that uses verified movement, progression, and territory-based challenges to motivate recurring exercise. The initial product is a mobile running experience with a supporting admin console.

### Initial target user

An adult recreational runner who wants motivation, visible progress, and local competition without needing a formal race or club.

### Initial business objective

Prove that verified, local, asynchronous running challenges increase weekly active exercise and repeat participation. Revenue experiments are secondary to trust, safety, and retention in the first pilot.

## 2. MVP scope

### Included

- Account registration, login, consent, and profile.
- Run session: permission check, start/pause/resume/finish, live GPS breadcrumb, elapsed time, distance, pace, and battery/network-aware sampling.
- Server validation of route integrity: timestamps, continuity, speed, accuracy, completion boundary, duplicate/replay protection, and suspicious-session review.
- Course registration: a completed route becomes a proposed virtual course after validation.
- Challenge board and map markers with privacy-preserving route previews.
- Defender publishes a challenge with a fixed entry crystal amount, rules, eligibility, expiry, and safety metadata.
- Challenger discovers, joins, completes, and receives a result after verification.
- XP, rank, badges, streaks, and transparent progression.
- Crystals as a server-priced, ledgered virtual unit with permitted uses defined by product policy and platform requirements.
- Admin review, abuse handling, refunds/voids, feature flags, audit log, and support tools.

### Explicitly out of MVP

- Push-up/squat pose estimation as a scored competitive mechanic.
- Live synchronous races, video judging, WebRTC, or “Hyrox by Osiris.”
- Cash withdrawal, cryptocurrency/token issuance, blockchain ownership, NFTs, or secondary markets.
- Public exact route history, public home/work inference, or persistent owner identity on the map.
- Merchant bounties and AR treasure mechanics unless they support the validated running loop.

## 3. Core user journey

1. User signs up, accepts terms and granular data consents, and configures safety preferences.
2. User opens the map and sees nearby generalized challenge markers.
3. User selects a challenge and reviews distance, terrain/safety notes, time window, entry amount, and privacy treatment.
4. User reaches the start area, passes a coarse start check, and begins a run.
5. The mobile app draws the route live and queues signed telemetry locally when offline.
6. User finishes within the course boundary. The app submits the route once with an idempotency key.
7. Verification returns accepted, rejected, or review-required with human-readable reasons.
8. The settlement service posts immutable ledger entries, awards XP/rank, and makes the result visible.

## 4. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| PRD-001 | A user can create and authenticate an account with secure password handling and session revocation. | Must |
| PRD-002 | A user can start, pause, resume, and finish a run with a visible live route. | Must |
| PRD-003 | The client remains usable through short network outages and prevents duplicate submissions. | Must |
| PRD-004 | The server verifies route evidence; client-declared time/distance is never authoritative. | Must |
| PRD-005 | A validated run can create one course proposal; duplicate and overlapping abuse is controlled. | Must |
| PRD-006 | A defender can publish an asynchronous challenge with fixed immutable terms. | Must |
| PRD-007 | A challenger can join only while eligible and before the challenge closes. | Must |
| PRD-008 | Every settlement has a traceable ledger, reason code, and audit event. | Must |
| PRD-009 | Users can export, correct, and request deletion of personal data; financial records are anonymized where retention is required. | Must |
| PRD-010 | Admins can suspend a challenge, user, or payout path without database edits. | Must |
| PRD-011 | Later activity types can plug into a common verification contract. | Should |
| PRD-012 | Live physical events can be introduced without changing the wallet or identity model. | Later |

## 5. Non-functional requirements

- API p95 under 500 ms for ordinary reads; route ingestion is asynchronous where practical.
- No lost settled ledger entry; settlement is idempotent and reconcilable.
- 99.5% monthly availability for pilot API, excluding planned maintenance.
- Route verification decisions are explainable and reviewable; ML may assist but does not silently decide an irreversible money outcome.
- All production secrets are externalized; all environments are isolated.
- Accessibility: readable map controls, large touch targets, non-color-only status, and clear safety warnings.
- Observability: structured logs, metrics, traces, audit events, and alert ownership.

## 6. Success metrics

- Activation: ≥60% of new users complete one verified run within 7 days.
- Retention: ≥35% week-4 retained runners in pilot cohort.
- Trust: ≥95% of valid pilot runs accepted; false-positive fraud blocks reviewed weekly.
- Challenge repeat: ≥40% of activated users join a second challenge within 30 days.
- Safety: zero known severe injuries caused by an Osiris instruction; safety incident response tested before pilot.
- Economy: 100% ledger reconciliation; zero duplicate crystal mint or settlement incidents.

## 7. Release phases

| Phase | Outcome |
|---|---|
| R0 Foundation | Secure account, consent, run session skeleton, environments, CI, observability |
| R1 Verified Run | Reliable route capture and server verification without competitive stakes |
| R2 Course and Challenge Pilot | Course registration, map discovery, asynchronous challenge, non-cash rewards |
| R3 Controlled Crystal Economy | Approved purchase/entry flow, ledger settlement, support/refunds |
| R4 Activity Expansion | Pose-assisted push-ups/squats behind feature flags and new consent |
| R5 Live Events | Physical event operations, timing, safety, staffing, and insurance model |
