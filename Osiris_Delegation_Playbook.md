# Osiris — Delegation Playbook (Phases 0–6)

| Field | Value |
| :--- | :--- |
| **Document type** | Phase-by-phase delegation briefs for the agent teams defined in `Osiris_Agent_Team_Spec.md` |
| **How to use** | Feed each "Instruction to Orchestrator" block verbatim to the Orchestrator agent. One phase at a time. Do not start a phase whose dependencies are open. |
| **Version** | 1.0 |

---

## 0. Sequencing correction (read before delegating)

The operator's proposed order was amended for two dependency inversions:

| Operator's order | Amended order | Why it moved |
| :--- | :--- | :--- |
| — | **Phase 0 — Build baseline (CI, manifest, Docker)** | Pulled forward from old #4. Phases 2–3 rewrite money and security code; without CI and a reproducible environment, no agent's fix is verifiable. Tests-before-surgery, not after. |
| 1. PM/Economist + Privacy/Compliance | **Phase 1 — Viability** (unchanged; runs **in parallel** with Phase 0 — no code involved) | Cheapest failure point. Correct as proposed. |
| 2. Payments/Ledger + Security | **Phase 2 — Ledger + security holes** (+ money-invariant tests pulled forward from old #5) | Tests that protect money paths must land *with* the money code, not three phases later. |
| 4. DBA + SRE (Postgres+PostGIS, CI, observability) | **Phase 3 — Data platform + SRE** (Postgres/PostGIS migration, backups, cron externalization, observability; CI already done in Phase 0) | Moved *ahead* of geospatial work: spatial hardening must be written once, against PostGIS — not first against JSON-string polygons and then rewritten. |
| 3. Geospatial + Anti-Cheat | **Phase 4 — Spatial correctness + anti-cheat** | Now sits on its actual dependency (PostGIS). |
| 5. Monolith split + QA suite | **Phase 5 — Refactor behind the net** (split `main.py`; expand tests to property/fuzz) | Invariant tests moved to Phase 2; this phase keeps the refactor + suite expansion. |
| 6. Mobile/Frontend/Data/ML | **Phase 6 — Loop polish + ML groundwork** (unchanged) | Correct as proposed. |

**Parallelism:** 0 ∥ 1. Everything else is sequential. 2 is blocked by 0; 3 by 2; 4 by 3; 5 by 4 (refactoring mid-migration multiplies merge pain); 6 by 5.

---

## Phase 0 — Build baseline

> **Instruction to Orchestrator:** "Phase 0. Route to DevOps/Release Engineer. Produce a reproducible build and CI gate for `Osiris_backend`. Nothing in later phases merges without this pipeline passing."

**Agents.** Senior DevOps / Release Engineer (lead); Principal QA (review).

**Read first.** `Osiris_Master_Spec.md` §3.7 (the "missing for prod" list); `Deep_Audit_2026-06.md`.

**Scope — in.**
- `pyproject.toml` (or `requirements.txt`) pinning every dependency, including transitive pins for anything cryptographic (`pyjwt`, `bcrypt`).
- Dockerfile producing a runnable image from a clean clone; secrets via env only, never baked in.
- CI pipeline: lint → type-check → run the two existing suites (`test_ml_referee`, `test_v2_10_flows`) → build image → export OpenAPI and **diff against the committed `Documentation/openapi.json`** (fail on drift — this is the contract three clients depend on).
- `/healthz` endpoint (DB reachable, migrations current).
- Structured JSON logging skeleton (request id, user id, route, latency).

**Scope — out.** Postgres migration (Phase 3). Observability dashboards (Phase 3). Any business-logic change.

**Exit criteria.**
1. Fresh clone → `docker build` → container boots → both test suites pass inside CI, zero manual steps.
2. An intentional OpenAPI change fails CI until the committed contract is regenerated.
3. Deploy/rollback runbook exists (even if "deploy" is one VM for now).

**Human gates touched.** None. This phase is pure scaffolding — approve the pipeline config and move on.

**Kill condition.** None. There is no finding here that stops the project; there are only findings that stop *later phases* from being trustworthy if this one is skipped.

---

## Phase 1 — Viability: "can this legally and financially exist?"

> **Instruction to Orchestrator:** "Phase 1, parallel with Phase 0. Route to Principal PM, Principal Game Economist, and Compliance & Privacy Analyst. Deliverable: a viability memo I will take to a human lawyer. No agent concludes legality."

**Agents.** Principal Product Manager (frame); Principal Game Economist (model); Senior Compliance & Privacy Analyst (draft questions for counsel).

**Read first.** Master spec §1.5 (business model), §2.5 (out of scope), §6.2 (economy constants); `Deep_Audit_2026-06.md` §3.x (GDPR gaps).

**Tasks.**
1. **Gambling analysis (draft, not conclusion).** Map the Phase-2 mechanic — players stake convertible currency, an outcome partly outside their control determines a winner, platform takes 20% — against the consideration/chance/prize test in Nova Scotia and federal Canadian law, plus the top 3 target markets. Enumerate which design changes (e.g., entry-fee skill contest vs. head-to-head wager; non-convertible reward currency; sweepstakes model) change the classification. Output: a decision matrix **for a licensed gaming lawyer**, with the agent's uncertainty stated per cell.
2. **Payments obligations map.** If crystals become convertible: money-services/KYC/AML exposure, Stripe's prohibited-business list (gambling categories require pre-approval), chargeback model for siege losses.
3. **Privacy gap plan.** PIPEDA applies to the Bedford pilot now (the spec says "UK GDPR" — **flag this as wrong for a Nova Scotia pilot**; UK GDPR applies to UK data subjects, PIPEDA/provincial law to the actual pilot population). Spec the consent, export, and delete endpoints engineering must build; classify the telemetry (GPS traces + biometric-adjacent motion data = sensitive).
4. **Unit economics.** Economist models pilot P&L: merchant pilot fees vs. infra + acquisition; what retention/redemption numbers make Phase 2 worth legal spend.

**Exit criteria.**
1. Viability memo exists with three economy-design options ranked by regulatory risk.
2. Counsel question list is concrete enough to bill ≤2 hours of a lawyer's time.
3. Privacy build-list handed to Backend agent (consumed in Phase 2/5).

**Human gates touched.** **Financial-feature launch** and **privacy go-live** — both require explicit human review at phase end. The phase produces the inputs for that review.

**Kill condition.** If the chosen value-transfer model is not commercially viable or cannot be operated safely, reposition around virtual economy + B2B merchant revenue before further money-path engineering.

---

## Phase 2 — Ledger + the named security holes

> **Instruction to Orchestrator:** "Phase 2. Route to Principal Backend Engineer, Principal AppSec Engineer, and Principal QA jointly. Every fix lands with a test that failed before it and passes after. The exploit list comes from the audit; no fix without a regression test."

**Agents.** Principal Backend Engineer (ledger + fixes); Principal Application Security Engineer (threat-model, verify); Principal QA (invariant tests — pulled forward from old Phase 5); Principal Game Economist (ledger schema review).

**Read first.** `Deep_Audit_2026-06.md` in full; master spec §3.5, §4.5, §6.2.

**Tasks — A. Player-side crystal ledger (the spec admits it doesn't exist).**
- Append-only `crystal_ledger` table: `(id, user_id, delta, balance_after, reason_code, related_{siege,bounty,vault}_id, created_at)`; every mutation of `users.mana_crystals` happens **only** through a single service function that writes the ledger row and the balance in one transaction.
- Backfill/reconciliation script: sum of ledger deltas must equal stored balance for every user; CI job asserts it on the seed world.
- Vault movements get the same treatment (lock, top-up, payout, forfeit splits).

**Tasks — B. Close the named holes (each = fix + failing-first regression test).**
1. Webhook **fail-open → fail-closed**: missing `OSIRIS_WEBHOOK_SECRET` in any non-dev env refuses to start; unsigned/garbage-signed webhook → 401, merchant stays inactive. Test: forged `payment_successful` must not activate a merchant or write `PlatformRevenue` (this is the audit's payment-forgeability exploit — the single highest-priority fix in the codebase).
2. CORS: explicit origin allowlist; **wildcard + credentials is removed**, not configured around.
3. Rate limiting on `/auth/login`, `/onboard`, `/activities/verify`, webhook endpoint.
4. JWT revocation: short-lived access token + server-side revocable refresh, or a denylist with TTL — agent proposes, you pick; "7-day irrevocable token" does not survive this phase.
5. `GET /domains/nearby` and `/bounties/nearby`: authenticated, or consciously public with rate limits and a written justification — the current silent-public state is a decision nobody made.
6. Idempotency sweep: bounty completion, vault top-up, siege resolve all safe under duplicate submission (proof replay guard exists; verify it actually covers all three paths).

**Tasks — C. Money invariants (QA).** Property tests asserting: crystals are conserved (created/destroyed only via ledger reason codes); siege pot splits sum to 100%; no double coupon redemption; two concurrent resolves of the same siege produce exactly one winner and one set of ledger rows. Concurrency tests run against SQLite now, re-run against Postgres in Phase 3.

**Exit criteria.**
1. Every audit finding has status fixed-with-test, accepted-by-operator (with your signature in the risk register), or deferred-with-date.
2. Reconciliation job green on seed data; ledger is the only write path to balances.
3. AppSec agent's residual-risk register delivered to you — **you** accept or reject each line.

**Human gates touched.** **Security readiness sign-off** — agent prepares the register; only you accept residual risk, and an independent review is required before real-money features.

**Kill condition.** If fixing the webhook exploit reveals the payment-intent flow can't be made safe against the chosen provider's semantics, real-money work halts and the risk register is updated.

---

## Phase 3 — Data platform + SRE (Postgres/PostGIS, backups, jobs, observability)

> **Instruction to Orchestrator:** "Phase 3. Route to Senior SRE (lead) and Principal Backend Engineer. Migrate the system of record to Postgres+PostGIS with zero ledger discrepancies, externalize the cron jobs, and stand up backups and basic observability. Spatial *logic* changes wait for Phase 4."

**Agents.** Senior SRE / Reliability Engineer (lead); Principal Backend Engineer (migration code); Senior Spatial/GIS Engineer (schema design only — geometry column types, SRID, indexes); Principal QA (re-run invariant + concurrency suite on Postgres).

**Read first.** Master spec §5.6.1–.4; Phase 2's ledger schema.

**Tasks.**
1. **Migration.** Alembic chain → Postgres; `domains.geometry_json` → PostGIS `geometry(Polygon, 4326)` with GiST index (keep the JSON column one release for rollback); data-migration script with row-count and **ledger-reconciliation parity checks** before/after.
2. **Concurrency upgrade.** The Phase-2 money service functions gain `SELECT … FOR UPDATE` row locks now that the engine supports them properly; QA's concurrent-siege test must pass under real parallelism (multiple workers), not just asyncio interleaving.
3. **Cron externalization.** Decay + telemetry-TTL move out of in-process APScheduler to a single-runner mechanism (separate worker with a Postgres advisory lock is sufficient at this scale). Both jobs proven idempotent: running twice = running once.
4. **Backups.** Point-in-time recovery configured **and a restore actually rehearsed** — an untested backup is a hope, not a backup. Runbook with RTO/RPO numbers you choose.
5. **Observability.** Error tracking, p95 latency per route, money-mutation audit log stream, alert on reconciliation-job failure and webhook-signature failures (signature failures are attack telemetry).

**Exit criteria.**
1. App runs on Postgres in CI and staging; SQLite path deleted, not maintained in parallel.
2. Ledger reconciliation: zero discrepancies across migration.
3. Restore rehearsal documented with timing.
4. Kill the scheduler double-fire risk: two app instances running simultaneously execute decay exactly once.

**Human gates touched.** None new; you approve the migration cutover.

**Kill condition.** None — but a failed parity check stops the cutover, by construction.

---

## Phase 4 — Spatial correctness + anti-cheat

> **Instruction to Orchestrator:** "Phase 4. Route to Senior Spatial/GIS Engineer and Senior Anti-Cheat Engineer jointly. Make the reward-determining geometry correct under PostGIS and make cheating expensive. The referee is heuristic — layer around it; do not pretend it's a model."

**Agents.** Senior Spatial/GIS Engineer; Senior Anti-Cheat / Trust Engineer; Senior Data/ML Engineer (telemetry hooks); Principal QA (adversarial corpus).

**Read first.** Master spec §4.2, §5.3, FR-2.x, FR-4.x; audit §2.3 (weak GPS co-location).

**Tasks — Spatial (now written once, against PostGIS).**
1. Replace manual centroid/shoelace/point-in-polygon with `ST_Area(geography)`, `ST_Within`, `ST_DWithin`, `ST_Intersects`; `/domains/nearby` and `/bounties/nearby` become indexed queries.
2. Polygon validation beyond closure distance: `ST_IsValid` (reject self-intersections/figure-eights), sliver rejection (area-to-perimeter ratio bound), max-area sanity cap, duplicate/overlap policy made explicit (current swallow logic decides sieges — define what partial overlap means, because right now it's whatever the code happens to do).
3. Track-level checks, not just endpoint checks: per-segment velocity (a 25 km/h *average* gate passes a 200 km/h teleport followed by standing still), minimum point density per perimeter length, accuracy-radius weighting from the GPS samples.
4. **Adversarial polygon corpus (QA):** straight-line "runs," teleport tracks, figure-eights, slivers, replayed tracks with timestamp shifts, mirrored tracks, polygons enclosing another user's domain drawn without plausible perimeter traversal. Every one rejected with a named reason code.

**Tasks — Anti-cheat.**
1. **Device attestation:** Play Integrity (Android) + App Attest (iOS) verified server-side; unattested clients can play but **cannot perform money-bearing or siege actions** — a tiered-trust model, since attestation will exclude some legitimate devices.
2. Replay hardening: confirm `proofs_consumed` covers claims, sieges, *and* bounties; bind proof hash to user + action type + a server-issued nonce so a proof can't be minted offline and replayed across accounts.
3. GPS-spoof heuristics: sensor cross-consistency (accelerometer energy vs. distance covered), impossible-travel between consecutive actions, mock-location flags where the OS exposes them.
4. Anomaly feed → admin fraud queue (the React admin's review view from the team spec); every flagged event becomes a **labeled example** for Phase 6's ML work — this is where the future referee's training data actually comes from.

**Exit criteria.**
1. Adversarial corpus: 100% rejected, each with a reason code and a test.
2. Attestation enforced on money/siege paths in staging.
3. Honest-user false-positive rate measured on seed/pilot data and judged acceptable *by you* — anti-cheat that blocks real runners kills the pilot faster than cheaters do.

**Human gates touched.** **Anti-cheat readiness** stays under continuous review — this phase raises cost-to-cheat; it does not close an arms race.

**Kill condition.** If attestation coverage on the pilot's device population is so low that the tiered model gates out most legitimate testers, surface the trade-off to you; do not quietly weaken the control.

---

## Phase 5 — Monolith split behind the net + full QA suite

> **Instruction to Orchestrator:** "Phase 5. Route to Principal Backend Engineer with Principal QA embedded. Split `main.py` into routers/schemas/services/jobs with zero behavior change — the Phase 2 invariant suite and the OpenAPI drift check are the referee. Then expand the suite."

**Agents.** Principal Backend Engineer (refactor); Principal QA / Test Architect (suite expansion, behavior-freeze verification); Senior DevOps (CI coverage gates).

**Read first.** Master spec §3.2, §5.6.5.

**Tasks.**
1. **Behavior-freeze refactor.** Target tree: `routers/` (auth, players, domains, sieges, bounties, coupons, merchants, payments, admin, ml) · `schemas/` · `services/` (economy, ledger, spatial, referee, telemetry) · `jobs/`. Rule: the OpenAPI export is byte-identical before/after (CI drift check from Phase 0 enforces this for free), and the invariant suite passes unmodified. Any intentional behavior change is a separate, labeled commit — never smuggled inside the refactor.
2. **Why now and not earlier:** small files with single responsibilities are what make *agent* work safe — bounded context per task, bounded blast radius per change. This refactor is an investment in every later delegation.
3. **Suite expansion.** Per-service unit tests; auth-matrix tests (every endpoint × every role × no-token — the table in master spec §6.1 becomes executable); fuzzing on proof payloads and polygon inputs; privacy endpoints from Phase 1's build-list (consent, export, delete) implemented and tested here; coverage floor enforced in CI for `services/` (money code held to the highest bar).
4. Privacy build-out: data export (user's activities, domains, telemetry metadata), deletion with ledger-preserving anonymization (you cannot hard-delete ledger rows without breaking conservation — anonymize the subject, keep the accounting; the Compliance agent reviews this design).

**Exit criteria.**
1. `main.py` < ~150 lines (app factory + wiring); OpenAPI byte-identical; suite green.
2. Auth matrix executable and green.
3. Export/delete endpoints live; Compliance agent's checklist items closed or escalated.

**Human gates touched.** **Privacy go-live** — implementation done here; sign-off still you + counsel.

---

## Phase 6 — Loop polish + ML groundwork

> **Instruction to Orchestrator:** "Phase 6. Route to Mobile, Admin-Web, UX, Growth, and Data/ML agents. Polish the pilot loop end-to-end and build the labeling/eval harness. No one claims an ML referee exists until the eval says so."

**Agents.** Senior Mobile Engineer; Senior Frontend Engineer; Senior UX Designer; Senior Growth/Lifecycle Engineer; Senior Data/ML Engineer; Principal PM (acceptance).

**Read first.** Master spec §2.2 personas, §4.6 telemetry flow; Phase 4's anomaly feed.

**Tasks — Mobile/UX (the pilot lives or dies here).**
1. Onboarding to first verified reward in under five minutes of real-world activity; every failure mode (GPS denied, referee rejection, offline) has a recovery path with honest copy — "verification failed" with a retry beats a silent error.
2. Domain-claim UX: live trace, closure indicator, post-claim siege notifications; merchant app: coupon scan/redeem in two taps at the till.
3. Background-location and battery behavior validated on real low-end Android hardware, not just emulators.
4. Store-submission prep dossier (health data, location, virtual currency disclosures) — **submission itself is your gate**.

**Tasks — Growth (within the §5 reframing of the team spec).**
1. Retention instrumentation: D1/D7/D30, bounty completion rate, claim-to-siege conversion, merchant redemption rate — the numbers Phase 1's economics need.
2. Healthy-loop experiments: progression visibility, territorial social stakes, merchant value. Rest-day-punishing streak mechanics and compulsion patterns remain barred; the current "−5 % XP after 24 h idle" decay is reviewed against this bar — daily-punishment decay is exactly a streak-anxiety mechanic wearing a different name, and the PM agent must justify it with pilot data or soften it.

**Tasks — Data/ML (groundwork, not a model).**
1. Labeling rubric + tooling over the Phase 4 anomaly feed and admin fraud-queue decisions; every operator adjudication becomes a labeled row.
2. Offline eval harness: heuristic referee scored on the labeled set (precision/recall per activity type) — this baseline is the bar any future model must beat.
3. Train a first model **only when** labeled adversarial examples exist in meaningful volume; until then the deliverable is the harness and the honest scorecard. The agent's standing instruction: report "insufficient labels" as a finding, never paper over it with a model trained on synthetic assumptions.

**Exit criteria.**
1. End-to-end pilot rehearsal: register → bounty → claim → siege → coupon redemption, on physical devices, in DeWolf Park conditions.
2. Retention dashboard live; baseline referee scorecard exists.
3. Store dossiers ready for your submission decision.

**Human gates touched.** **Store submission** (you); **anything involving minors** (pilot recruitment must screen 18+ — a fitness game with wagering mechanics and location tracking has zero room for minors in the cohort).

---

## 7. Standing rules across all phases

1. **One phase open at a time** (0 ∥ 1 excepted). Half-finished phases are how a solo operator loses state.
2. **Every fix ships with the test that catches its regression.** No exceptions on money or security paths.
3. **The Orchestrator's "blocked on human" queue is reviewed by you before any new phase opens.** Open §6 gates from the team spec carry forward; they do not expire.
4. **Agents report uncertainty as a finding.** "I could not verify X" is a deliverable; silent confidence is a defect.
5. **The audit file is the canon of known holes.** Until `Deep_Audit_2026-06.md` is provided to the agents, Phase 2 cannot certify completeness against it — it can only fix what the master spec names. Feed agents the audit before Phase 2 starts.
