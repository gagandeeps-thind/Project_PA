# End-to-End Delivery Backlog

## Phase 0 — Reframe and protect the foundation

- [ ] Approve this document set as the working baseline.
- [ ] Freeze legacy siege/bounty expansion and mark old docs as historical.
- [ ] Choose target pilot geography, age policy, and launch jurisdictions.
- [ ] Complete the market, payment, app-store, privacy, and risk review for paid challenges and crystals.
- [ ] Establish product, engineering, security/privacy, operations, and finance owners.
- [ ] Create Dev/SIT/UAT/Prod accounts, databases, buckets, keys, and access groups.

## Phase 1 — Secure platform foundation

- [ ] Migrate production path to PostgreSQL/PostGIS.
- [ ] Add refresh-token rotation, revocation, admin MFA, strict CORS, and rate limiting.
- [ ] Add consent ledger, export, deletion/anonymization workflow, and retention jobs.
- [ ] Replace exact public domain exposure with privacy-safe challenge map responses.
- [ ] Add structured logs, metrics, traces, audit events, dashboards, alerts, and correlation IDs.
- [ ] Add outbox/job worker and idempotency middleware.
- [ ] Add secret/dependency/container scanning to CI.

## Phase 2 — Verified running

- [ ] Add `RunSession`, `RoutePoint`, `VerificationDecision`, and evidence version tables.
- [ ] Implement mobile permission UX, foreground/background behavior, pause/resume, offline queue, battery policy, and upload retry.
- [ ] Implement route chunk signing/sequence validation and server receipt timestamps.
- [ ] Implement rule-based verification with explainable reason codes and review queue.
- [ ] Add synthetic route fixtures: valid run, GPS jump, vehicle speed, replay, clock skew, poor accuracy, partial upload, duplicate finish.
- [ ] Instrument p50/p95 route upload latency, acceptance rate, rejection reasons, and battery impact.

## Phase 3 — Course and challenge pilot

- [ ] Normalize accepted routes into versioned Courses with privacy/safety checks.
- [ ] Build challenge creation, discovery, join, attempt, result, appeal, suspend, and void flows.
- [ ] Build customer map and run screens around the new API; keep old screens behind migration flags.
- [ ] Build admin trust console for review, support, user/challenge suspension, and audit search.
- [ ] Pilot with XP/badges or sponsor rewards only; measure retention and safety.

## Phase 4 — Controlled crystals

- [ ] Implement the approved economy equation as a versioned settlement policy.
- [ ] Add server-authoritative price packs, payment intent/webhook flow, refunds, chargebacks, and reconciliation.
- [ ] Add caps, region/age eligibility, responsible-play messaging, and finance reports.
- [ ] Run adversarial simulations and a capped internal cohort before public activation.

## Phase 5 — Expansion

- [ ] Add pose estimation behind explicit activity and ML consent.
- [ ] Collect labeled data under governance; evaluate bias, false accepts/rejects, and model drift.
- [ ] Design live Hyrox-style event operations: timing, course marshals, medical plan, waivers, insurance, incident response, and post-event data handling.

## Definition of done for each feature

Code, tests, API contract, migration, threat/privacy review, telemetry, support copy, rollback plan, documentation, and UAT acceptance are complete. A feature is not done because the happy-path UI works.
