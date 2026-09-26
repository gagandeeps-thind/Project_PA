# Osiris — Project Task Tracker & Handoff Guide

| Field | Value |
| :--- | :--- |
| **Document Type** | Project Task Tracker + Onboarding Handoff |
| **Version** | 2.11 |
| **Last Updated** | 2026-05-04 |
| **Owner** | Gagandeep Thind |
| **Phase** | Phase 1 — MVP (Pilot demo data seeded; v2.10 flows regression-tested) |
| **Companion Doc** | `Documentation/Imp_and_US.md` (Master GDD/TDD) |

---

## Status Legend

| Symbol | Meaning |
| :--- | :--- |
| ✅ | Completed |
| 🚧 | In Progress |
| 📋 | Planned (Next Sprint) |
| ⏳ | Backlog |
| ❗ | Blocked / Needs Decision |

> **How this doc is structured:** Every shipped item is documented with **What / Why / How** so a new contributor can resume work cold. § 8 (How to Resume This Project) is the fastest on-ramp.

---

## 1. Project Overview (Read This First)

**Osiris** is a real-world Action-RPG where verified physical effort (runs, push-ups, etc.) translates to digital rank, territorial control, and rewards. Players claim land by tracing GPS polygons on real terrain; ownership is defended via "Defense Feats" (verified workouts).

**Repository layout (this workspace):**
- `Osiris_backend/` — Backend Python application (FastAPI + SQLAlchemy + SQLite for MVP).
  - `database.py` — SQLAlchemy engine + session factory. Currently SQLite at `./fitness_mvp.db`.
  - `models.py` — All ORM models (User, Domain, SiegeLog, SiegeDiscount, Merchant, Bounty, BountyCompletion, PlatformRevenue, ActivityLog, ProofConsumed, Admin, TelemetrySession *(v2.10)*, TelemetryData *(v2.10)*).
  - `spatial_utils.py` — Pure-math helpers: `haversine_distance`, `calculate_polygon_area_sqkm` (Shoelace), `point_in_polygon` (ray casting), `is_polygon_swallowed`, `check_velocity_violation`.
  - `ml_referee.py` *(v2.5)* — Heuristic anti-cheat verifier. Pure-Python accelerometer cadence + rhythm analysis, MediaPipe pose summary checks, score-vs-duration plausibility. No SQLAlchemy, no I/O — drop-in replaceable in Phase 2 with a trained Scikit-learn model.
  - `main.py` — FastAPI app: Pydantic schemas, business logic, all REST endpoints, `process_daily_decay` cron (now wired via `lifespan` handler — v2.6), and economy/stat constants.
  - `tests/` *(v2.6)* — runnable test scripts (no pytest dependency). `test_ml_referee.py` (10/10) covers heuristic verification; `test_v2_10_flows.py` *(v2.11)* (7/7) covers telemetry persistence + replay-attack guard + DoS cap + RBAC matrix.
  - `scripts/` *(v2.6)* — operational helpers. `export_openapi.py` writes the spec to `Documentation/openapi.json`; `seed_admin.py` provisions admin accounts; `seed_pilot.py` *(v2.11)* populates a Bedford-pilot demo dataset (3 players, 1 active merchant, 2 domains, 5 bounties); `migrate_v2_9.py` is the one-time SQLite ALTER for v2.9 columns.
- `Documentation/Imp_and_US.md` — Master Game Design + Technical Design Document. Source of truth for mechanics & user stories.
- `Documentation/openapi.json` *(v2.6)* — Generated OpenAPI 3 spec; consumed by the frontend projects.
- `Task.md` — *(this file)* — execution tracker + onboarding doc.

**Stack:**
- **Backend:** Python 3, FastAPI, SQLAlchemy ORM, bcrypt (passwords), APScheduler (cron), SQLite (MVP) → PostgreSQL+PostGIS (Phase 2).
- **Frontend / Customer (Mobile):** Flutter project in `Osiris_customer/`.
- **Frontend / Merchant (Mobile):** Flutter project in `Osiris_merchant/`.
- **Frontend / Admin (Web):** React + Vite project in `Osiris_admin_web/`.

**Currency model (Phase 1):** Virtual **Mana Crystals** only. Phase 2 introduces real-money convertibility.

**Time-source policy:** All user-initiated actions carry a `device_timestamp` from the mobile client (client-authoritative). Server-owned clocks (decay job, inactivity check) use `_now_naive_utc()`.

---

# Backend

## 2. Completed Milestones

Each subsection follows **What / Why / How** — read top-to-bottom for project history, or jump to the area you're picking up.

### 2.1 Documentation & Game Design *(Foundational)*

- **What:** Master GDD/TDD (`Documentation/Imp_and_US.md`) covering Titles, Ranks, Guilds, B2B/B2C economy, anti-cheat Verification Matrix.
- **Why:** Single source of truth for game mechanics so backend code and frontend UI stay aligned. Prevents drift when multiple people / tools (VS Code + Antigravity) work in parallel.
- **How:** Living document, versioned via the Revision History table at the bottom. Every breaking design change bumps the version and adds a row.

---

### 2.2 Database & Data Models — `Osiris_backend/models.py`

**What:** ORM models for the entire Phase 1 domain: `User`, `Domain`, `SiegeLog`, `SiegeDiscount`, `Merchant`, `Bounty`, `BountyCompletion`.

**Why:** Persisting RPG stats, territorial polygons, siege state, and bounty completions is the bedrock for every gameplay loop. Started with SQLite to remove infra friction during rapid iteration; will migrate to PostGIS in Phase 2 because true spatial intersect (`ST_Area`, `ST_Intersects`) is required for production-grade siege logic.

**How:**
- All models inherit `Base` from `database.py`.
- Polygons are stored as JSON strings in `Domain.geometry_json` (interim — replaced by PostGIS `Geometry('POLYGON')` later).
- Timestamp defaults use `_default_now_naive_utc()` (helper at top of `models.py`) — naive UTC for SQLite compatibility while avoiding the `datetime.utcnow()` deprecation warnings.
- Tables auto-create on app startup via `models.Base.metadata.create_all(bind=database.engine)` in `main.py`.

---

### 2.3 Backend Utilities — `Osiris_backend/spatial_utils.py`

**What:** Pure-math, framework-free helpers for distance, area, point-in-polygon, polygon swallowing, and anti-cheat velocity check.

**Why:** Keeping spatial math out of the request handlers keeps endpoints readable and the logic unit-testable. Also lets Phase 2 swap each function for a PostGIS equivalent without touching endpoint code.

**How:**
- `haversine_distance(lat1, lon1, lat2, lon2)` → km between two GPS points.
- `calculate_polygon_area_sqkm(coords)` → Shoelace approximation; flat-earth assumption fine for park-sized polygons.
- `point_in_polygon(x, y, polygon)` → ray-casting; accepts dicts or Pydantic Coordinate objects.
- `is_polygon_swallowed(target, challenger)` → siege detection: every target vertex must be inside the challenger.
- `check_velocity_violation(coords, max_speed_kmh=25.0)` → returns True if any segment exceeded the speed limit (anti-vehicle-spoofing).

---

### 2.4 Core Backend APIs (Phase 1) — `Osiris_backend/main.py`

| Endpoint | Purpose |
| :--- | :--- |
| `POST /api/v1/onboard` | Create user; assign Avatar Class from `preferred_path`; init stats; grant 100 starter Mana Crystals. |
| `POST /api/v1/login` | bcrypt verify; bump `last_activity_date` from `device_timestamp`. |
| `GET  /api/v1/users/{user_id}` | Fetch full profile incl. stats and crystals. |
| `POST /api/v1/domains` | Validate closure + velocity, calc area, detect sieges, award claim XP, increment Party Stat from `defense_type`. |

**Why:** These cover the must-have lifecycle: register, authenticate, claim land. Everything else is built on top.

**How — design notes you should know before editing:**
- **Password length:** Pydantic enforces `max_length=12`. The 72-byte bcrypt limit is much higher; the 12-char cap is a deliberate UX choice (users on mobile keypads).
- **Avatar Class** is derived from `preferred_path` (Strength/Cardio/Balance), **not** BMI — see Risk Register in GDD § 7.3 (avoid body-shaming).
- **Rank** is a function of XP **and** inactivity: 30+ days of no activity downgrades the user to "F - The Dishonored" regardless of XP. See `get_rank()` in `main.py`.
- **Daily decay** runs hourly in MVP via `APScheduler` (see `process_daily_decay`). Non-active users (>24h) lose their streak and 5% of XP.

---

### 2.5 Epic 5 — Land Ownership & Siege Resolution *(Shipped v2.1, Refined v2.2)*

**What:** A two-tier ownership economy (free vs. paid Vault) plus the full siege lifecycle: detect on submit → resolve on Defense Feat → distribute Vault → grant retry discounts on loss.

**Why:** Without economic stakes, Domain Expansion was just shape-drawing. Locking real (eventually) money into the Vault makes territory meaningful. The **Retry Discount** (v2.2 refinement) ensures losing a siege isn't all-or-nothing — players who challenge the same defender repeatedly get a partial rebate, encouraging rivalries instead of one-shot churn.

**How — flow:**
1. Challenger calls `POST /api/v1/domains` with a polygon that swallows an existing domain. The endpoint creates a `SiegeLog` row with `status="pending_feat"` and `defender_score_snapshot` (locked at this moment to prevent post-hoc edits).
2. Challenger calls `POST /api/v1/sieges/{id}/resolve` with their Defense Feat score:
   - Server looks up any unconsumed `SiegeDiscount` for `(challenger_id, target_domain_id)` and auto-applies it to reduce out-of-pocket match.
   - **Win:** challenger debited the out-of-pocket match; pot = `match × 2`; challenger gets 80%, system retains 20% (War Tax). Defender's domain is `db.delete()`d; defender's `cumulative_area` and `title` recomputed. Challenger gets `+500` XP.
   - **Loss (paid tier):** challenger debited out-of-pocket match. Match is split: 50% to defender's Vault (moat grows), 30% kept by system, 20% banked as a new `SiegeDiscount` for the next attempt at this domain.
3. Stat increment (`increment_stat_from_activity`) runs **regardless of win/loss** — the player still performed the activity.

**Files:** `Osiris_backend/models.py` (User.mana_crystals, Domain.vault_balance, SiegeLog snapshot fields, SiegeDiscount table), `Osiris_backend/main.py` (constants `WAR_TAX_PCT`, `LOSS_DEFENDER_PCT`, `LOSS_SYSTEM_PCT`, `LOSS_DISCOUNT_PCT`; `lock_vault`, `resolve_siege` endpoints).

**Endpoints:**
- `POST /api/v1/domains/{domain_id}/vault` — owner locks/tops-up Ownership Fee. Top-up only (downgrade is Phase 2).
- `POST /api/v1/sieges/{siege_id}/resolve` — challenger submits Defense Feat; resolves win/loss with payout/discount logic.

**Known simplifications (carry-overs to Phase 2):**
- "Trace shatters on loss" (per GDD § 4.3) is **not** implemented — the challenger's polygon stays. Reintroducing this is a Phase 2 ticket.
- War Tax revenue is "burned" (no platform ledger). Phase 2 needs a `PlatformRevenue` model for accounting.

---

### 2.6 Epic 6 — Party Attribute Stats *(Shipped v2.2)*

**What:** Four new attributes on `User` (STR / AGI / END / CON) plus a `GET /api/v1/users/{id}/party-role` endpoint that returns Vanguard / Striker / Scout / Strategist.

**Why:** Required to assign roles in dungeons and raid bosses (GDD § 4.6). Without per-attribute tracking the system can't differentiate tanks from healers, and the planned Adventure Party feature can't be built.

**How:**
- Mapping `DEFENSE_TYPE_TO_STAT` in `main.py` ties activity types (pushups → STR, sprint → AGI, run → END, plank → CON) to columns.
- `increment_stat_from_activity(user, defense_type, score)` adds `score` to the matching column. Called from:
  - `submit_domain` after a successful claim (uses the polygon's defense_type/score).
  - `resolve_siege` regardless of outcome (challenger performed the activity).
  - `complete_bounty` (Epic 1).
- `get_party_role(user)` returns the role tied to the user's max stat. Tie-break order: STR > AGI > END > CON.
- **MVP shortcut:** stats are lifetime totals, not a 30-day rolling window. Implementing rolling requires an `ActivityLog` table — flagged as Phase 2.

**Endpoint:** `GET /api/v1/users/{user_id}/party-role` → `PartyRoleResponse` (role + all 4 stats + leading_stat name).

---

### 2.7 Epic 1 — Bounty Board *(Shipped v2.3 — newest)*

**What:** Geofenced quests + B2B merchant chests, with proximity-verified completion, coupon issuance, and one-claim-per-user enforcement.

**Why:** Bounties were the missing low-stakes XP loop. Without them, the only way to gain XP was to claim land (Epic 4) or win a siege (Epic 5) — both high-effort. Daily Bounties also keep low-engagement users above the 30-day decay threshold. The merchant chest variant is the entry point for the B2B revenue model (foot traffic as a service).

**How — design:**
- **One unified `Bounty` model**, two flavors via `bounty_type`:
  - `daily` — system-issued; `target_score > 0` (e.g., 20 push-ups); no merchant.
  - `merchant_chest` — sponsored; usually `target_score = 0` (just visit); `coupon_text` populated.
- **Geofence:** `target_lat`, `target_lng`, `radius_m`. Proximity check uses existing `haversine_distance` (km) compared to `radius_m / 1000`.
- **Pilot constraint:** `max_completions` (default 50) caps participation per the Bedford pilot (~50 testers per bounty, GDD § 7.1).
- **Coupon codes:** `secrets.token_urlsafe(8).upper()` — single-use, stored in `BountyCompletion.coupon_code_issued`.
- **Single-claim:** enforced by querying `BountyCompletion` for `(bounty_id, user_id)` before awarding.
- **Score gate:** if `target_score > 0`, the submitted `score` must meet or exceed it.

**Files:** `Osiris_backend/models.py` (Merchant, Bounty, BountyCompletion), `Osiris_backend/main.py` (Pydantic shapes + 4 endpoints + `secrets` import).

**Endpoints:**

| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST | `/api/v1/merchants/register` | Register a B2B partner. **Currently unauthenticated** — gate behind a Merchant Portal admin in production. |
| POST | `/api/v1/bounties` | Seed a bounty (admin or merchant). |
| GET  | `/api/v1/bounties/nearby?lat=&lng=&radius_km=` | List active, non-expired, non-full bounties within radius_km. Sorted nearest-first. |
| POST | `/api/v1/bounties/{id}/complete` | Validate proximity + score, award XP/crystals, increment stat, issue coupon (if merchant_chest). |

**Known simplifications:**
- Merchant registration has no auth — production needs JWT + Merchant Portal admin login.
- Pilot fee billing (the $50 fee from GDD § 5.2) is not implemented — payments integration is Phase 2.
- Nearby search loads all active bounties into memory then filters. Fine for MVP; PostGIS `ST_DWithin` replaces this in Phase 2.

---

### 2.8 Epic 2 — ML Referee (Anti-Cheat) *(Shipped v2.5 — newest)*

**What:** Server-side verifier that inspects a client-submitted `ActivityProof` (accelerometer trace + optional MediaPipe pose summary + declared score) and returns `verified` / `confidence` / `verified_score`. Wired as an **optional `proof` field** on every action endpoint that previously trusted a client-submitted score.

**Why:** Until v2.5 the backend trusted whatever score the client posted. A bad actor could spoof a workout payload and farm XP, claim land, or win sieges they never performed. The GDD's Verification Matrix (§ 6.1) calls for accelerometer pattern matching at 85% confidence as a Phase 1 requirement. Without it, the entire economy is exploitable. Making the proof *optional* (rather than mandatory) keeps existing test flows working while the Flutter client is still being built — Gagan flips it on per-endpoint as Antigravity ships the matching screens.

**How — design:**

1. **Pure-Python heuristics**, not Scikit-learn. We don't have pilot data yet; once we do, the sub-checks in `ml_referee.py` can be swapped for trained models without touching `main.py`. The threshold and per-activity profile constants live at the top of `ml_referee.py` for easy tuning.
2. **Three sub-checks**, multiplied for final confidence (any failure zeroes the verdict):
   - **Accelerometer cadence + rhythm** — peak-detect on the magnitude `|a|`, compute peaks-per-second, compare to the activity's expected band (e.g., push-ups 0.3–1.5 Hz, sprint 2.5–4.5 Hz). Then check inter-peak-interval stdev as a fraction of the mean — a "rhythm score" near 1.0 means regular human movement; near 0 means non-rhythmic shaking.
   - **MediaPipe pose summary** — for camera-verified exercises (push-ups, squats), require min/max joint angles with at least 60° range-of-motion and a min-angle ≤ 100° (depth gate). Ignored for run/walk/sprint.
   - **Score plausibility** — sanity-cap declared score against `max_rate_per_sec × duration × 1.2`. Catches "I did 200 push-ups in 30 seconds" style fraud.
3. **Hold activities (plank, hold)** are special-cased: cadence band collapses to ~0 Hz, declared `score` is interpreted as seconds and capped against wall-clock duration.
4. **Confidence threshold = 0.85**, lifted directly from GDD Story 2.2.
5. **Wiring pattern** — every action endpoint calls a tiny helper `_enforce_proof(proof, expected_activity_type)`:
   - If `proof` is `None` → returns `None` (legacy trust path).
   - If activity type mismatches the expected one → 400 (e.g., challenger sent a "squats" proof to defend against a "pushups" domain).
   - If verification fails → 400 with the verifier's flags as the detail.
   - If verified → returns `verified_score`, which the endpoint uses in place of the client-submitted score.

**Files:** `Osiris_backend/ml_referee.py` (new), `Osiris_backend/main.py` (Pydantic shapes `AccelerometerSample`/`PoseSummary`/`ActivityProof`/`VerificationResult`; helpers `_run_verification`/`_enforce_proof`; new `/activities/verify` endpoint; optional proof fields wired into 3 existing endpoints).

**Endpoints:**

| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST | `/api/v1/activities/verify` | Stateless preview — no DB writes. Frontend calls this to confirm a workout will pass before submitting the real action. |
| POST | `/api/v1/domains` | Now accepts optional `defense_proof: ActivityProof`. Verified score replaces client `defense_score`. |
| POST | `/api/v1/sieges/{id}/resolve` | Now accepts optional `challenger_proof: ActivityProof`. Verified score replaces `challenger_score`; activity_type must match the defender's `defense_type`. |
| POST | `/api/v1/bounties/{id}/complete` | Now accepts optional `score_proof: ActivityProof`. Verified score replaces `score`; activity_type must match `bounty.activity_type`. |

**Per-activity tuning constants** (in `ml_referee.ACTIVITY_PROFILES`):

| Activity | Cadence band (Hz) | Max reps/sec | Stat fed |
| :--- | :--- | :--- | :--- |
| pushups | 0.3 – 1.5 | 1.0 | STR |
| squats | 0.3 – 1.5 | 1.0 | STR |
| burpees | 0.15 – 0.6 | 0.6 | AGI |
| sprint | 2.5 – 4.5 | 5.0 | AGI |
| run | 2.0 – 3.5 | 4.0 | END |
| walk | 1.5 – 2.5 | 3.0 | END |
| plank / hold | 0 – 0.2 (hold) | n/a (seconds) | CON |

**ML Architecture Evolution (Hybrid Approach)**:
- **Phase 1 (Frontend Real-Time ML)**: We will integrate on-device ML in the Flutter app using MediaPipe Pose (for camera-based reps like squats/pushups) and TFLite (for IMU accelerometer data). This ensures immediate feedback and gamification without network latency. Critically, the frontend will log and transmit raw sensor traces alongside the verified score.
- **Phase 2 (Backend Validation)**: The current backend `ml_referee` uses pure-Python algorithmic checks. In Phase 2, the raw sensor datasets collected by the frontend will be used to train a robust Scikit-learn model (e.g., `IsolationForest`) for asynchronous server-side fraud detection.
- **No replay-attack defence (Fixed)**: A verified proof can technically be re-submitted. *(Resolved in v2.7 via `ProofConsumed` table idempotency guards)*.

---

### 2.10 Hardening Sprint *(Shipped v2.6 — newest)*

**What:** Post-Epic-2 cleanup that turns the MVP into something safe to demo: a platform revenue ledger, a modern FastAPI lifecycle wiring, the first runnable test suite, and an OpenAPI snapshot the frontend can consume offline.

**Why:** Each piece closes a different audit/coordination gap that would have blocked the Bedford pilot:
- **PlatformRevenue ledger** — until v2.6 the system's War Tax (20% of siege win pots) and Loss-Keep (30% of siege loss forfeits) were silently "burned." There was no row anywhere recording that the platform had earned crystals. With a real-money convertibility step in Phase 2, that becomes a compliance problem on day one.
- **Lifespan handler** — `@app.on_event` is deprecated and FastAPI will eventually remove it. Migrating now while the surface is small avoids a flag-day later.
- **`ml_referee` tests** — the verifier has subtle floating-point logic (peak detection, rhythm score). Synthetic regression tests catch threshold drift the moment we tune a constant.
- **OpenAPI export** — Antigravity needs to regenerate the Dart client from a frozen spec. Running the dev server every time is awkward; a checked-in `Documentation/openapi.json` makes the contract a file, not a service.

**How:**

1. **`models.PlatformRevenue`** — append-only ledger keyed by `source` ("siege_war_tax", "siege_loss_keep", and Phase-2 placeholders for "merchant_pilot_fee" / "black_market_fee" / "tower_pass"). Every paid-tier siege now writes one row through `db.add(models.PlatformRevenue(...))` inside `resolve_siege` — once on win (20% war tax), once on loss (30% system keep). Read-only audit endpoint `GET /api/v1/platform/revenue` aggregates `total_crystals`, a `by_source` breakdown, and `row_count`.
2. **`lifespan` migration** — `scheduler = BackgroundScheduler()` is now declared near the top of `main.py`, immediately followed by an `@asynccontextmanager async def lifespan(app)` that adds the `process_daily_decay` job, `start()`s the scheduler, yields, and tears down on shutdown. `FastAPI(lifespan=lifespan)` wires it in. The old `@app.on_event("startup"/"shutdown")` decorators are deleted.
3. **`tests/test_ml_referee.py`** — pytest-free runnable script with 10 cases: legit push-ups / shallow ROM / fast cadence / implausible count / steady plank / shaky plank / 5-min run / no samples / missing pose / verified-score zeroed. Run via `python tests/test_ml_referee.py`. Exits non-zero on any failure so it can be wired into CI later. Synthetic accelerometer fixture (`synth_rhythmic`, `synth_steady`, `synth_shaky_hold`) seeds reproducible traces.
4. **`scripts/export_openapi.py`** — imports `main` and dumps `app.openapi()` to `Documentation/openapi.json`. Path-independent (works whether you `cd` into `Osiris_backend/` first or run from the project root). Re-run after every schema change.

**Files:** `Osiris_backend/models.py` (`PlatformRevenue`), `Osiris_backend/main.py` (lifespan handler, ledger writes in `resolve_siege`, `/platform/revenue` endpoint), `Osiris_backend/tests/test_ml_referee.py` (new), `Osiris_backend/scripts/export_openapi.py` (new), `Documentation/openapi.json` (generated, 14 paths / ~45 KB).

**New endpoints:**

| Method | Path | Purpose |
| :--- | :--- | :--- |
| GET | `/api/v1/platform/revenue` | Audit total platform earnings + breakdown by `source`. Read-only; gate behind admin auth in production. |

**Known simplifications (carry-overs to Phase 2):**
- Revenue rows are denominated in Mana Crystals, not USD. When Phase 2 turns crystals real, add a `currency` column and a daily FX-rate snapshot.
- No retention policy — every revenue row sticks around forever. Once volume matters, archive rows older than N months into cold storage.
- The `/platform/revenue` endpoint returns the full aggregate every call. Fine at MVP scale; add a date-range filter (`?from=&to=`) when row count grows.

---

### 2.11 ActivityLog + Rolling Party Stats + Replay-Attack Guard *(Shipped v2.7 — newest)*

**What:** Three tightly-related additions:
1. `ActivityLog` table — one row per verified physical activity, with timestamps, source, and ML-Referee confidence captured at the moment of recording.
2. `?window_days=N` query parameter on `GET /api/v1/users/{id}/party-role` — opt-in rolling-window aggregation that computes leading stat from `ActivityLog` rows in the last N days instead of lifetime totals.
3. `ProofConsumed` table + idempotency guard on every proof-bearing action endpoint — replay-attack defence so the same workout proof can never be cashed in twice.

**Why:**
- **Rolling stats** were flagged as a Phase-2 carryover from Epic 6 (v2.2), but the work was tractable now and unblocks legitimate Adventure Party logic. Without it, the planned dungeon role assignment is permanently biased toward whatever exercise a user did most in their first month of play. The GDD § 4.6 explicitly calls for a 30-day window.
- **The idempotency guard** closes a real exploit: until v2.7, a malicious client could submit the same valid proof to `/domains` AND `/bounties/{id}/complete` AND `/sieges/{id}/resolve` — three free awards from one workout. The cost of the fix is one new table and a deterministic SHA-256 hash. Cheap insurance.
- **`ActivityLog`** was a prerequisite for both. It also makes the `ml_referee` confidence scores queryable (e.g., "show me users whose median proof confidence dropped below 0.85" — useful for fraud detection).

**How:**

1. **`models.ActivityLog`** — `user_id`, `activity_type`, `score`, `stat_column`, `confidence`, `verified` (0/1), `source` (`'domain_claim'` / `'siege_resolve'` / `'bounty_complete'`), `related_id`, `occurred_at` (= `device_timestamp`), `created_at`. Indexed on `user_id`, `activity_type`, `source`, `occurred_at` so the rolling-window query is cheap.
2. **`record_activity(db, user, activity_type, score, occurred_at, source, related_id, verified, confidence)`** — single helper in `main.py` that *both* increments the lifetime stat (calls `increment_stat_from_activity`) *and* appends an `ActivityLog` row. Replaces every previous bare call to `increment_stat_from_activity` in the three action endpoints.
3. **`_enforce_proof` refactor** — now returns the full `VerificationResult` instead of a bare `int`, so call sites can capture both `verified_score` *and* `confidence` and pass them straight into `record_activity`.
4. **Rolling-window endpoint** — `GET /api/v1/users/{user_id}/party-role?window_days=30` aggregates `ActivityLog.score` per `stat_column` for rows whose `occurred_at >= now - window_days`. The lifetime path (no query param) is unchanged for backward compatibility.
5. **`models.ProofConsumed`** — `proof_key` (unique-indexed SHA-256), `user_id`, `source`, `consumed_at`. The hash is computed over `(user_id, device_timestamp, activity_type, declared_score, duration_seconds, accelerometer samples)` — the accelerometer trace is the high-entropy fingerprint, so legitimate workouts produce different keys even at the same timestamp. Pose data is intentionally excluded so a re-extracted pose summary still collides.
6. **`_consume_proof_or_409(db, user_id, proof, source)`** — called immediately after `_enforce_proof` succeeds in each action endpoint. If the key already exists, raises 409 Conflict with the original consumer's `source` and `consumed_at` so the client can confirm the prior success. The `/activities/verify` preview endpoint is intentionally not guarded (no DB writes; safe to spam).

**Files:** `Osiris_backend/models.py` (ActivityLog, ProofConsumed), `Osiris_backend/main.py` (`record_activity` helper, `_proof_dedup_key` + `_consume_proof_or_409` helpers, refactored `_enforce_proof` return type, three action endpoints rewired, `/party-role` extended with `window_days`).

**New / changed endpoints:**

| Method | Path | Change |
| :--- | :--- | :--- |
| GET | `/api/v1/users/{id}/party-role?window_days=N` | New optional query param; default behavior unchanged. |
| POST | `/api/v1/domains` | Now writes an `ActivityLog` row and consumes the proof key (409 on replay). |
| POST | `/api/v1/sieges/{id}/resolve` | Same. |
| POST | `/api/v1/bounties/{id}/complete` | Same. |

**Known simplifications (carry-overs to Phase 2):**
- `ProofConsumed` rows live forever. Add a TTL/archive job once volume warrants it.
- The hash includes raw accelerometer values; rounding to 3 decimal places means a determined attacker who can perfectly clone a trace from network capture can still replay. Future hardening: include a server-issued nonce in the proof envelope, signed by the client.
- Rolling-window aggregation is computed in Python from raw rows. At pilot scale (~50 users × ~5 workouts/day × 30 days = 7,500 rows) it's fine; at production scale promote to a materialized rolling-sum table refreshed nightly.
- The lifetime totals on `User.{str/agi/end/con}_stat` are now redundant with `ActivityLog` and could be derived. Kept for now as a fast read path; consider deprecating once `ActivityLog` is fully trusted.

---

### 2.12 Three-Portal Auth Architecture *(Shipped v2.8 — newest)*

**What:** A single mobile-app codebase serves three distinct UIs — game (player), merchant portal, admin portal — chosen by which credentials are entered at login. Backend exposes one `POST /api/v1/auth/login` endpoint that probes Admin → Merchant → User in order and returns the matching `role`. The Flutter app reads the role and routes accordingly.

**Why:** Per Gagan's 2026-05-04 architecture call:
- **Admin portal** is single-tenant (only Gagan). Public admin registration is intentionally not exposed — admins are seeded out-of-band via a CLI script. This makes "no one but me can access the admin portal" enforceable at the data layer, not just the UI.
- **Merchant portal** lives at a separate web URL for registration (Phase 2 — not yet built), but the same Flutter mobile app is the login surface. A merchant who registers on the web can then enter those credentials in the mobile app and get the merchant UI instead of the game.
- **Player flow** is unchanged from previous sprints — register and login in-app.

This split avoids two bad alternatives: building three separate apps (cost), or showing a "pick your role" dropdown at login (security — would let anyone probe whether an admin email exists).

**How:**

1. **`models.Admin`** — minimal table (`id`, `email`, `hashed_password`, `name`, `created_at`, `last_login_at`). No FK relationships; admins are not players in the game world.
2. **Pydantic shapes** — `AuthLoginRequest` (email + password + device_timestamp) and `AuthLoginResponse` (role + id + email + name + message). Same password rules as everywhere else (max 12 chars, bcrypt-hashed at rest).
3. **`POST /api/v1/auth/login`** — sequential probe of Admin → Merchant → User, returning at the first successful match. On failure, returns `401 Invalid email or password` without revealing which table was checked (no enumeration). Probe order matters: Admin wins email collisions, so an accidental player account with the admin's email would still resolve as admin.
4. **`scripts/seed_admin.py`** — interactive (or env-var-driven via `OSIRIS_ADMIN_EMAIL` / `OSIRIS_ADMIN_PASSWORD` / `OSIRIS_ADMIN_NAME`). Idempotent — re-running with the same email updates the password in place rather than creating duplicates.
5. **Backward compat** — the old `POST /api/v1/login` (player-only) is kept untouched. Flutter clients that already integrate with it continue to work; new clients should use `/auth/login`.

**Files:** `Osiris_backend/models.py` (Admin model), `Osiris_backend/main.py` (Pydantic shapes + `auth_login` endpoint), `Osiris_backend/scripts/seed_admin.py` (CLI seeder).

**Frontend contract for Antigravity:**

```jsonc
// Request
//POST /api/v1/auth/login
{
  "email": "user@example.com",
  "password": "max12chars",
  "device_timestamp": "2026-05-04T12:00:00Z"
}

// Response 200
{
  "role": "player",
  "id": 1,
  "email": "user@example.com",
  "name": "Display Name",
  "message": "Welcome back."
}

// Response 401 — generic, do NOT reveal which table was checked
{ "detail": "Invalid email or password" }
```

Flutter routing logic should be:

```dart
switch (response.role) {
  case 'admin':    Navigator.pushReplacementNamed(ctx, '/admin');     break;
  case 'merchant': Navigator.pushReplacementNamed(ctx, '/merchant');  break;
  case 'player':   Navigator.pushReplacementNamed(ctx, '/game');      break;
}
```

For player-specific data (XP, rank, etc.), the app calls `GET /api/v1/users/{id}` after a successful login as before.

**Endpoints:**

| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST | `/api/v1/auth/login` | Role-aware login (Admin → Merchant → Player). Returns `role` for UI routing. |
| POST | `/api/v1/login` | Player-only login. Kept for backward compat. |

**One-time setup before Bedford pilot:**

```sh
cd Osiris_backend
python scripts/seed_admin.py
# Prompts for email + password + display name. Creates the Admin row.
```

**Known gaps (intentional, scoped for later sprints):**
- **No JWT yet.** `/auth/login` returns `role` but no token. Subsequent API calls still pass `user_id` in the request body. JWT enforcement on per-endpoint basis (so a player can't call `/platform/revenue`) is a separate sprint.
- **No merchant web registration page yet.** Merchants are currently registered via the same `/api/v1/merchants/register` endpoint that's been live since v2.3 — accessible to anyone. Phase 2 fronts it with a web portal + admin approval flow.
- **No admin CRUD endpoints yet.** `/platform/revenue` is the only admin-side endpoint. As the admin portal grows, more (e.g., `GET /admin/users`, `GET /admin/sieges`) will be added — gated by the Admin probe + JWT once that lands.

---

### 2.13 Merchant Payment Lifecycle + JWT *(Shipped v2.9 — newest)*

**What:** Three things shipped together because they're tightly coupled:
1. **JWT-based auth tokens.** `auth_login` now mints an HS256 JWT alongside the role; FastAPI dependencies (`get_current_player` / `get_current_merchant` / `get_current_admin`) gate per-endpoint access by decoded role.
2. **Webhook-driven merchant activation.** A merchant who registers starts `is_active=False` / `payment_status='payment_pending'`. The pilot fee is paid via a `/payments/intent` → provider-fires-webhook → `/payments/webhook` flow that flips `is_active=True` only on `payment_successful`.
3. **Endpoint-level activation gates** (no leakage at login). Inactive merchants log in normally and learn their state from `GET /api/v1/merchants/{id}`; the gate fires only when they try to create a `merchant_chest` bounty.

**Why:**
- Per Gagan's 2026-05-04 call: gate logic lives at the endpoint (defence-in-depth), activation must auto-flip on payment confirmation (no admin-in-the-loop for the happy path), and the three statuses need explicit semantics — only `payment_successful` activates.
- JWT was scaffolded in `main.py` (CORS middleware, `oauth2_scheme`, role-specific dependencies) but no endpoints used it yet. Wiring the new merchant endpoints behind those dependencies is the first real exercise of the JWT machinery.

**How:**

1. **Merchant model extended** (`models.py`):
   - `payment_status` (`'payment_pending'` | `'payment_successful'` | `'payment_declined'`, default `'payment_pending'`)
   - `payment_provider_id` (Stripe-style intent ID)
   - `pilot_fee_cents` (default 5000 = $50 USD)
   - `last_payment_at`

2. **One-time migration** (`scripts/migrate_v2_9.py`) — idempotent ALTER TABLE for the four new columns. Run once after pulling v2.9. SQLAlchemy's `create_all` doesn't add columns to existing tables; Alembic comes in Phase 2.

3. **Activation rules in `payment_webhook`:**
   - `payment_successful` → flips `is_active=True`, sets `last_payment_at`, writes a `PlatformRevenue('merchant_pilot_fee')` row (idempotent — guards against double-credit if the same successful webhook fires twice).
   - `payment_pending` → status updated, `is_active` stays False.
   - `payment_declined` → status updated, `is_active` stays False. Merchant can retry by initiating a new intent.
   - `provider_payment_id` cross-checked against the merchant's last intent — guards against webhooks for a different intent landing on the wrong merchant.

4. **JWT machinery** (already in `main.py` from Gagan's edit, now actively used):
   - `create_access_token({"sub": str(id), "role": role})` — 7-day expiry.
   - `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")`.
   - `get_current_admin/merchant/player` dependencies enforce role on individual endpoints.

5. **Merchant_chest gate** in `create_bounty`: if `bounty_type == 'merchant_chest'` and the linked merchant is not active, return 403 with the merchant's current `payment_status` in the error detail. Daily/system bounties are unaffected.

**Files:** `Osiris_backend/models.py` (4 new Merchant columns), `Osiris_backend/main.py` (Pydantic shapes + 6 new endpoints + bounty gate), `Osiris_backend/scripts/migrate_v2_9.py` (one-time SQLite migration).

**New endpoints (6):**

| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| GET  | `/api/v1/merchants/{id}` | Merchant (same-id) or Admin | Full profile incl. activation/payment state. Used post-login to refresh state. |
| POST | `/api/v1/merchants/{id}/payments/intent` | Merchant (same-id) | Initiate pilot-fee payment. Returns stub `provider_payment_id` for MVP; real Stripe in Phase 2. |
| POST | `/api/v1/payments/webhook` | None (signature verification TODO) | Provider-driven activation. Three terminal statuses; only `payment_successful` activates. |
| GET  | `/api/v1/admin/merchants` | Admin | Triage view; filter by `?status=pending\|active\|declined\|all`. |
| POST | `/api/v1/admin/merchants/{id}/activate` | Admin | Manual fallback (out-of-band payment, demo seeding). Writes a `PlatformRevenue` row. |
| POST | `/api/v1/admin/merchants/{id}/deactivate` | Admin | Manual fallback (refunds, violations). No revenue row. |

**Smoke verified end-to-end** (11 steps, all pass on `fitness_mvp.db`): register → 403 chest → intent → webhook(pending) stays inactive → webhook(successful) flips active → chest creates → admin list → admin deactivate → declined webhook.

**Known simplifications (carry-overs to Phase 2):**
- **Payment provider is stubbed.** `/payments/intent` returns a UUID-style fake `provider_payment_id`. Real Stripe / payment-provider SDK integration is Phase 2.
- **Webhook has no signature verification.** Production MUST verify a signature header against the provider's public key before trusting the body. Currently any client can call `/payments/webhook` with a valid merchant_id and flip activation.
- **JWT secret is hardcoded** (`SECRET_KEY = "dummy-secret-key-for-mvp-phase"`, 30 bytes — pyjwt warns it's below the 32-byte minimum for HS256). Move to an env var (`OSIRIS_JWT_SECRET`) and rotate before any non-pilot deployment.
- **No idempotency-key on `/payments/intent`.** A merchant calling it twice creates two unrelated intents; only the most recent provider_payment_id is honored. Fine for MVP; harden once real money flows.

---

### 2.14 Pilot-Ready Backend *(Shipped v2.10 — newest)*

**What:** Five things shipped together because they're all on the path between "feature-complete backend" and "Bedford-pilot-ready":
1. **Full sensor telemetry capture** (accel, gyro, magnetometer, GPS, barometer, pose) persisted via `TelemetrySession` + `TelemetryData` linked to every `ActivityLog`.
2. **`GET /api/v1/domains/nearby`** — public read endpoint that unblocks the Flutter map.
3. **`GET /api/v1/merchants/{id}/bounties`** — merchant analytics with `completions_count` + `coupons_issued` for the merchant portal.
4. **JWT secret hardened** to env var (`OSIRIS_JWT_SECRET`); fail-fast in production via `OSIRIS_ENV=production`.
5. **Webhook signature verification** (`X-Provider-Signature` HMAC-SHA256) wired in but disabled by default; flips on with `OSIRIS_WEBHOOK_SECRET`. Wider RBAC gates added on `/users/{id}` and tightened on `/bounties`.

**Why:**
- **Telemetry** was flagged earlier as the single highest-leverage data investment. Without it, every pilot workout is unlabeled training data thrown away on the spot. Capturing the full sensor suite (not just accel + pose) lets future ML use richer features — GPS during a run validates run-vs-treadmill; barometer during stair climbs gives altitude deltas; gyroscope catches the rotational signature of burpees. It's far cheaper to capture too much now than to ask 50 pilot testers to redo their workouts later.
- **`/domains/nearby`** is the frontend bottleneck. The Flutter map literally cannot render territory until this endpoint exists. Shipping it now removes the blocker for cycle F1.
- **Merchant analytics** lets the merchant portal show something more interesting than "your activation status is X." Without `coupons_issued`, merchants pay $50 and see no payoff.
- **JWT secret + webhook signature** are the two hard-requirements to flip the production switch. Both were docs-only TODOs in v2.9; v2.10 makes them actually wired.

**How:**

1. **`models.TelemetrySession`** — metadata row per submitted workout. Tracks `activity_log_id` link, `activity_type`, per-sensor sample counts, `confidence`, `verified` flag, `occurred_at` from device clock.
2. **`models.TelemetryData`** — sidecar JSON blob, one row per `(session, sensor_type)`. `sensor_type ∈ {accel, gyro, magnetometer, gps, barometer, pose}`. Lets ML training selectively load only the channels it needs.
3. **`ActivityProof` extended** with `gyroscope: List[GyroscopeSample]`, `magnetometer: List[MagnetometerSample]`, `gps: List[GpsSample]`, `barometer: List[BarometerSample]`. Each sample type is a Pydantic model with `t_ms` (ms since activity start) plus the sensor-specific fields. ML referee continues to read only accelerometer + pose for verification — the rest is captured for archive only.
4. **`record_activity()` extended** with an optional `proof: ActivityProof` parameter. When provided, calls `_persist_telemetry()` after writing the ActivityLog row. All three call sites (`submit_domain`, `resolve_siege`, `complete_bounty`) plumb the proof through.
5. **`GET /api/v1/domains/nearby`** — public (no auth). In-memory haversine sweep over all domains, filtered by centroid distance. Returns owner_id, polygon, area, vault_balance, is_protected. PostGIS `ST_DWithin` replaces this in Phase 2.
6. **`GET /api/v1/merchants/{id}/bounties`** — merchant-self (same id from JWT) or admin. For each bounty, runs a single COUNT(*) for `coupons_issued`. Phase 2 should denormalize to `bounties.coupons_issued_count` if N+1 hits scale.
7. **JWT secret loading**:
   - `OSIRIS_JWT_SECRET` env var if set.
   - In production (`OSIRIS_ENV=production`), missing var raises `RuntimeError` at boot.
   - In dev, falls back to a 48-byte ephemeral secret regenerated each restart (existing tokens become invalid — desired behaviour).
8. **Webhook signature verification** via `verify_webhook_signature` dependency: reads raw body once, HMAC-SHA256 over the bytes using `OSIRIS_WEBHOOK_SECRET`, `compare_digest` against `X-Provider-Signature` header. Disabled when secret unset.
9. **RBAC tightening**:
   - `GET /api/v1/users/{user_id}` — players self-only, admins any, merchants 403.
   - `POST /api/v1/bounties` — daily admin-only; merchant_chest must match `merchant_id` from JWT (or admin).
   - Cleaned up a duplicate `/api/v1/merchants/{id}/bounties` registration that was emitting an OpenAPI warning.

**Files:** `Osiris_backend/models.py` (TelemetrySession, TelemetryData), `Osiris_backend/main.py` (sensor Pydantic shapes; `_persist_telemetry()`; new endpoints; JWT/webhook env-var wiring; RBAC tightening; duplicate cleanup).

**New / changed endpoints:**

| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| GET | `/api/v1/domains/nearby?lat=&lng=&radius_km=` | None (public) | Map render — list domains within radius. |
| GET | `/api/v1/merchants/{id}/bounties` | Merchant (same-id) or Admin | Merchant analytics: bounties + completions + coupons. |
| GET | `/api/v1/users/{user_id}` | Player (same-id) or Admin | Tightened from un-gated. |
| POST | `/api/v1/bounties` | Admin (daily) or Merchant-self (chest) | Tightened from admin-or-any-merchant. |
| POST | `/api/v1/payments/webhook` | Optional `X-Provider-Signature` | When `OSIRIS_WEBHOOK_SECRET` set, verifies HMAC; otherwise accepts as before. |

**Smoke verified end-to-end** (9 steps on `fitness_mvp.db`): onboard player → login (gets JWT) → other-user profile 403 → own profile 200 → /platform/revenue 403 (RBAC) → submit domain w/ full 5-sensor proof → TelemetrySession row created with all 6 channels (300/300/300/30/30/1) → `/domains/nearby` returns the new domain.

**Known simplifications (carry-overs):**
- **Telemetry stored as JSON strings** in SQLite. Phase 2 should consider a columnar store (Parquet on S3?) for the raw samples once volumes grow — `TelemetryData.samples_json` won't scale to millions of rows.
- **No TTL on telemetry archive** yet. Pilot data is small enough to keep forever; production needs a retention policy.
- **`/domains/nearby` is unauth and uncached.** Public game state can be hot — every map pan triggers a fresh scan. Cache-on-edge or PostGIS-with-spatial-index will be needed at scale.
- **Webhook signature verification only checks HMAC.** Real Stripe integration also needs replay protection (timestamp tolerance) — add when wiring the real provider.
- **Pilot-fee ledger logged in cents** but Mana Crystals are unitless. Phase 2 currency layer needs to reconcile.

---

### 2.15 Pilot Demo Prep + v2.10 Regression Tests *(Shipped v2.11 — newest)*

**What:** Four operational additions that turn the v2.10 backend from "feature-complete" into "demoable":
1. **`scripts/seed_pilot.py`** — populates `fitness_mvp.db` with a Bedford-pilot fixture set (3 players, 1 pre-activated merchant, 2 domains around DeWolf Park, 3 daily bounties, 2 merchant_chests).
2. **DoS guard on `ActivityProof`** — Pydantic `max_length=20000` on every sensor channel rejects oversized payloads with 422 before any server CPU is spent.
3. **Telemetry TTL job** — `process_telemetry_ttl()` runs nightly via APScheduler, purging `TelemetryData` rows older than `OSIRIS_TELEMETRY_TTL_DAYS` (default 90). `TelemetrySession` metadata is retained indefinitely so analytics queries never lose history. Setting the env var to 0 disables the job.
4. **`tests/test_v2_10_flows.py`** — 7-case regression suite covering the v2.10 flows we'd previously only smoke-tested by hand: telemetry persistence, replay-attack 409, DoS cap rejection, RBAC matrix (player-self / player-other / player→/platform/revenue / admin→/platform/revenue).

**Why:**
- A demoable seed cuts onboarding friction: a new contributor or pitch-meeting participant runs *one command* and has a live world to point at, instead of curl-seeding 8 endpoints in order.
- Without the DoS cap, a malicious or buggy client could submit a multi-megabyte sensor payload and OOM the server. The cap is a Pydantic validator, so it fires before any server logic runs — pure win.
- Without the TTL job, `TelemetryData` grows unbounded. Each verified workout writes ~5 KB of accelerometer JSON; a busy pilot easily hits hundreds of MBs. We don't need every raw sample forever — once an ML model is trained, the value of older raw data approaches zero.
- The regression tests catch silent breakages we couldn't catch before. Specifically, the replay-attack guard depends on a hash that includes the full accelerometer trace; if anyone tweaks `_proof_dedup_key()` later and accidentally weakens it, the test fires immediately.

**How:**

1. **`scripts/seed_pilot.py`** — idempotent on the `vanguard@example.com` user (early-exit if exists). Creates 3 players (vanguard / striker / strategist), 2 demo domains around DeWolf Park (one paid Vault, one free), 1 merchant **pre-activated** with `is_active=True` + `payment_status='payment_successful'` so demo flows work end-to-end without walking the webhook lifecycle. All passwords are `'password'` — fixture creds, never use in prod.
2. **DoS guard** — single new constant `MAX_SAMPLES_PER_CHANNEL = 20000` plus `Field(..., max_length=MAX_SAMPLES_PER_CHANNEL)` on the five sensor arrays in `ActivityProof`. Justification for the number: 20000 samples = ~7 minutes of 50 Hz capture. Longer activities should chunk.
3. **`process_telemetry_ttl()`** — opens its own DB session (runs outside HTTP request context), queries `TelemetrySession.id` for rows older than the cutoff, deletes matching `TelemetryData` rows in one bulk DELETE. Logs a single line per cleanup. Wired into the existing lifespan handler alongside `process_daily_decay`.
4. **`tests/test_v2_10_flows.py`** — uses the same pytest-free runnable-script pattern as `test_ml_referee.py`. Each test calls a fresh `TestClient(main.app)` against the real `fitness_mvp.db`, isolating fixtures by an `v210test_` email prefix and cleaning up at start + end. 7 cases, all currently green.

**Files:** `Osiris_backend/main.py` (`MAX_SAMPLES_PER_CHANNEL` constant + Pydantic length validators + `process_telemetry_ttl()` + lifespan-handler registration), `Osiris_backend/scripts/seed_pilot.py` (extended with merchant pre-activation + credentials summary), `Osiris_backend/tests/test_v2_10_flows.py` (new).

**No new endpoints** — this sprint was purely operational hardening.

**Test results:**

```
ml_referee:        10 / 10 passed
v2_10_flows:        7 /  7 passed
```

**One-time setup for a new clone:**

```bash
cd Osiris_backend
python scripts/seed_pilot.py        # populates demo data
python scripts/seed_admin.py        # creates Gagan's admin row
python tests/test_ml_referee.py
python tests/test_v2_10_flows.py
```

**Known simplifications (carry-overs):**
- TTL job uses `created_at` (server-side wall clock) not `occurred_at` (device clock). For reasonably-clocked devices the difference is seconds; if a device is wildly out of sync we'd rather over-retain than under-retain. Document this if it ever surprises someone.
- DoS cap is a hard reject — there's no "warn and downsample" path. A legitimate long-distance run would have to chunk client-side. Flutter client should split runs > 7 minutes into multiple ActivityProof submissions, each linked to one `domain_claim` with a separate `device_timestamp`.
- Seed-script merchant pre-activation skips the PlatformRevenue ledger row that a real webhook activation would write. Demo revenue numbers will be $0 unless someone manually triggers a webhook.

---

### 2.9 Time-Source Policy *(Established v2.2)*

**What:** Activity timestamps come from the user's mobile device via a required `device_timestamp` (ISO 8601) field. Server-owned timestamps (decay, inactivity) use server `now`.

**Why:** Two reasons —
1. Mobile clients may go offline and sync later; we want the recorded time to reflect when the activity actually happened, not when the request reached the server.
2. The user explicitly requested this behaviour.

The carve-outs (decay, inactivity check) use server time because trusting a device clock there would let a user fast-forward to skip decay penalties.

**How:**
- `device_timestamp: datetime` is a required field on `UserCreate`, `UserLogin`, `DomainCreate`, `SiegeResolveRequest`, `BountyCompleteRequest`.
- Helpers in `main.py`:
  - `_now_naive_utc()` — server-side "now" as naive UTC.
  - `_to_naive_utc(dt)` — strips tzinfo from a client datetime so comparisons with stored values work.
- All previously deprecated `datetime.utcnow()` calls have been replaced.

---

## 3. Active Sprint — Next Up

### Sprint Goal — v2.12 ("Real Payments + Webhook Hardening + Frontend Coordination")
v2.11 shipped pilot demo data, regression tests, and operational hygiene. Next sprint replaces the stub Stripe-style flow with a real provider integration, hardens the webhook signature path so production can flip on, and gives the merchant portal the analytics it needs to be useful.

### Sprint Backlog — Backend

**Real payments**
- 📋 Wire a real payment-provider SDK (Stripe Elements is the working assumption — confirm before starting). `POST /merchants/{id}/payments/intent` returns a real `client_secret` instead of a UUID stub. `OSIRIS_STRIPE_SECRET_KEY` env var.
- 📋 Webhook signature: enable production-mode by setting `OSIRIS_WEBHOOK_SECRET` — it's wired but currently bypassed in dev.
- 📋 Replay-attack guard on the webhook itself: store the provider's `event_id` in a new `PaymentWebhookEvent` table so retries from the provider don't double-credit. Stripe explicitly retries failed webhooks.

**Operational deepening**
- 📋 Structured logging (JSON) via `python-json-logger`. Tag every request with `request_id`, role from JWT claims, and elapsed ms. Sets up CloudWatch / Sentry visibility for v2.13.
- 📋 Rate limiting on auth + payment endpoints — `slowapi` IP-based limits. `/auth/login` 10/min, `/payments/intent` 5/hr.
- 📋 Add a `/healthz` endpoint that returns DB connectivity status — needed for k8s/ECS health probes in v2.13 deployment.

**Coordination with Frontend**
- 📋 If Antigravity blocks on a missing endpoint shape, surface it here before adding it. No drive-by API additions.

### Sprint Backlog — Frontend (Flutter / Antigravity) *(proposed, Gagan curates)*

**Cycle F3 — Merchant + Admin portals**
- 📋 Merchant dashboard: status banner (active / pending / declined) sourced from `GET /merchants/{id}`; "Pay Pilot Fee" CTA when inactive; analytics card pulling `GET /merchants/{id}/bounties`.
- 📋 Admin dashboard: revenue summary card (`GET /platform/revenue`); merchants table (`GET /admin/merchants`) with activate/deactivate buttons.
- 📋 Both portals share the same auth flow already shipped — only the routing target differs based on `role`.

**Cycle F2 carry-overs (if not done)**
- 📋 Domain Claim Flow as defined last sprint: Start Domain → GPS breadcrumb → Close Domain → Defense Feat → submit.

### Out of scope for v2.12 (deferred to v2.13)

- ML camera flow with on-device MediaPipe — saved for a focused cycle once payment + portal flows are proven.
- PostgreSQL + PostGIS migration — the bigger production lift; v2.13 sprint topic.
- App store submissions, privacy policy, TOS — pre-launch only.

---

## 3.5 Roadmap to Bedford Pilot

The pilot needs ~50 local testers playing in DeWolf Park / Sunnyside Mall. To get there, four sprints from v2.10. Backend-led; frontend cycles run in parallel from Antigravity.

| Sprint | Backend Theme | Frontend Theme | Pilot-Demo Bar |
| :--- | :--- | :--- | :--- |
| **v2.10** *(shipped)* | Pilot-ready security (RBAC, env JWT, webhook sig) + map-unblocking endpoints (`/domains/nearby`, `/merchants/{id}/bounties`) + telemetry capture (`TelemetrySession` + `TelemetryData`) | Player Core Loop: login → dashboard → map → bounty claim | A tester can register, see nearby bounties on a map, walk to one, and claim it for XP + coupon. |
| **v2.11** *(shipped)* | Seed-data CLI for pilot demo, DoS guard on `ActivityProof`, telemetry TTL job, regression test suite (`test_v2_10_flows.py`) | Domain Claim Flow: Start Domain → GPS breadcrumb → Close Domain → Defense Feat (manual score input; ML camera deferred) | A tester can claim a polygon and lock crystals into the Vault. |
| **v2.12** *(active)* | Real Stripe payment integration replacing the intent stub, webhook event-id deduplication, structured JSON logging, rate limiting, `/healthz` | Merchant + Admin portals: status banners, pay CTA, analytics cards, revenue summary | A merchant can pay their pilot fee with a real card and see the activation flip live. |
| **v2.12** | Real Stripe (or chosen provider) integration in `/payments/intent` + `/payments/webhook` (signature verification active), production logging + Sentry equivalent, CI smoke pipeline | Siege resolution UI + Merchant Portal v0 (login → status → manual pay UX placeholder) + Admin Portal v0 (revenue card + merchant list) | A merchant can register on web, log in to mobile, and see their pending status; an admin can audit revenue. |
| **v2.13 / v3.0-MVP** | PostgreSQL + PostGIS migration, `geometry_json` → `Geometry('POLYGON')`, `ST_DWithin` replaces in-memory haversine sweep, Alembic for future migrations | ML camera flow: on-device MediaPipe pose estimation + `/activities/verify` preview + proof submission on action endpoints | An end-to-end pilot tester can complete a verified push-up bounty with on-device pose detection. |
| **Pilot launch** | App-store submissions, privacy policy, TOS, real-money compliance review (still virtual currency at this stage), Bedford onboarding event | Polish, A/B copy, error states, telemetry | First 50 testers in the field. |

**Critical-path dependencies (don't slip these):**
- Backend `/domains/nearby` blocks the entire frontend Map View. Ship in v2.10.
- `ActivityProofArchive` blocks any future ML training. Even though no model exists yet, every pilot workout that runs without it is permanently lost data. Ship in v2.10.
- Real payment provider integration requires a documented product, finance, security, and market-readiness review before v2.12 starts.

**Risks to flag now:**
- Single-developer frontend (Gagan in Antigravity) is the bottleneck for every cycle's user-visible bar. Backend can ship faster than frontend can consume. Don't accumulate backend velocity at the cost of unintegrated APIs.
- `fitness_mvp.db` is now schema-divergent across team members each time models change. Phase 2's Alembic migration is overdue.

---

## 4. Backlog — Phase 1

### Epic 2 — ML Referee
*Shipped v2.5 — see § 2.8.*

### Epic 3 — B2B Merchant Flow (residual)
- ⏳ Merchant Portal authentication (JWT)
- ⏳ Pilot fee billing / payment integration
- ⏳ Merchant analytics dashboard (chests claimed, coupons redeemed)

### Cross-Cutting
- ⏳ Trace-shatter on siege loss (currently keeps the challenger polygon — see Epic 5 simplifications)
- ✅ ~~`ActivityLog` model + nightly job → unlock 30-day rolling Party Stats~~ — shipped v2.7 (rolling on demand via `?window_days=N`; no nightly job needed)
- ✅ ~~Replace deprecated FastAPI `@app.on_event` with lifespan event handlers~~ — shipped v2.6

---

## 5. Backlog — Phase 2 (Production Readiness)

- ⏳ Migrate SQLite → PostgreSQL + PostGIS
- ⏳ Replace `geometry_json` string with PostGIS `Geometry('POLYGON')`; replace Shoelace with `ST_Area`
- ⏳ Replace in-memory haversine sweep on `/bounties/nearby` with `ST_DWithin`
- ⏳ JWT-based session tokens (replace stateless re-auth)
- ⏳ Mana Crystals → real-currency convertibility + compliance layer
- ⏳ Rate limiting on Vault, Bounty Complete, Siege Resolve endpoints
- ⏳ CI/CD + containerization
- ⏳ `PlatformRevenue` ledger for War Tax + pilot fees

---

## 6. Open Decisions

| Item | Owner | Status | Notes |
| :--- | :--- | :--- | :--- |
| XP reward per km² claimed | G. Thind | ✅ Decided | `area_sqkm × 100` on claim, `+500` bonus on siege win |
| Vault currency (USD vs Mana Crystals) | G. Thind | ✅ Decided | Phase 1 = Mana Crystals (virtual); Phase 2 = real-world convertible |
| Starter Mana Crystal balance | G. Thind | ✅ Decided | 100 crystals on onboarding |
| Siege loss split | G. Thind | ✅ Decided | 50% defender / 30% system / 20% retry-discount |
| Time source for user actions | G. Thind | ✅ Decided | Device-authoritative (`device_timestamp` required) |
| Default bounty XP / crystal rewards | G. Thind | ✅ Decided (v2.7, pending ack) | Daily: `xp=50`, `crystals=5`. Merchant chest: `xp=25`, `crystals=10`. Defaults applied in seed-data script and BountyCreate Pydantic. |
| Ownership Fee tier minimums | G. Thind | ✅ Decided (v2.7, pending ack) | Warden 10 / Lord 50 / High Lord 200 / Sovereign 1000 crystals. Currently advisory; enforcement deferred until Antigravity surfaces tier UI. |
| Trace-shatter on siege loss | G. Thind | ⏳ Phase 2 | MVP keeps challenger's polygon intact |

---

# Frontend

## 1. Active Sprint — Next Up (Frontend)

**Epic 1 — Frontend Scaffold & Core Systems**
- [x] Create `Osiris_frontend` directory and initialize Flutter project.
- [x] Generate and configure OpenAPI Dart client from FastAPI backend.
- [x] Set up routing system and core theme (Dark RPG Aesthetic).
- [x] Implement secure local storage for session management.

**Epic 2 — Onboarding & Auth ("The Awakening")**
- [x] Build Login Screen.
- [x] Build Registration/Onboarding Flow (Height, Weight, Age, Gender).
- [x] Implement Avatar Class selection (Strength / Cardio / Balance).
- [x] Wire up to `POST /api/v1/onboard` and `POST /api/v1/login`.

## 2. Backlog — Phase 1 (Frontend)

**Epic 3 — Map & Domain Expansion**
- [x] Build the Main Map View (centered on user's location).
- [x] Implement "Start Domain" GPS polling and breadcrumb drawing on the map.
- [x] Implement "Close Domain" logic (checking within 20m of start) and Defense Feat prompt.
- [x] Wire up `POST /api/v1/domains` for land claiming.

**Epic 4 — Bounty Board & Economy**
- [x] Build Bounty List/Map View (fetching from `GET /api/v1/bounties/nearby`).
- [x] Implement AR / Chest unlocking sequence when within range.
- [x] Wire up `POST /api/v1/bounties/{id}/complete` and display coupon codes.
- [x] Implement Vault UI to manage Mana Crystals and Ownership Fees.

**Epic 5 — Profile & Adventure Party**
- [x] Build Profile Screen showing STR / AGI / END / CON.
- [x] Fetch and display Party Role via `GET /api/v1/users/{id}/party-role`.
- [x] Display current Rank and progression.

## 8. How to Resume This Project (Cold-Start Guide)

If you're picking this up from scratch:

1. **Read `Documentation/Imp_and_US.md` end-to-end.** It is the source of truth for game mechanics and explains *why* the system is shaped the way it is.
2. **Skim § 1 and § 2 of this file** for the project layout and what's built.
3. **Run the backend locally:**

```sh
   cd Osiris_backend
   pip install fastapi uvicorn sqlalchemy bcrypt apscheduler pydantic[email]
   uvicorn main:app --reload
```

- First run creates `Osiris_backend/fitness_mvp.db` automatically.
   - If you see "no such column" errors, **delete `fitness_mvp.db`** and let it recreate (we don't have migrations yet — see § 5).
4. **Open `http://localhost:8000/docs`** for the auto-generated Swagger UI. You can exercise every endpoint from there.
5. **Suggested smoke test sequence:**
   1. `POST /api/v1/onboard` (with `device_timestamp`)
   2. `POST /api/v1/domains` (claim a small polygon)
   3. `POST /api/v1/merchants/register`
   4. `POST /api/v1/bounties` (seed a daily or merchant_chest)
   5. `GET /api/v1/bounties/nearby?lat=&lng=`
   6. `POST /api/v1/bounties/{id}/complete`
   7. `GET /api/v1/users/{id}/party-role`
6. **Pick the next ticket from § 3 (Active Sprint).**
7. **Frontend work happens in Google Antigravity, not here.** Coordinate via the OpenAPI spec; the contract is the only shared artifact.

### 8.1 Re-exporting the OpenAPI spec (after schema changes)

```sh
cd Osiris_backend
python scripts/export_openapi.py
# → "Wrote OpenAPI spec (N paths) to Documentation\openapi.json"
```

Commit `Documentation/openapi.json` so Antigravity can regenerate the Dart client without running the backend.

### 8.2 Running the ml_referee tests

```sh
cd Osiris_backend
python tests/test_ml_referee.py
# → "10 / 10 passed"
```

Exits non-zero on failure; safe to wire into CI later.

### 8.3 Verified-flow example (proof-attached domain claim)

When the Flutter client wants its score to be ML-Refereed, it attaches a `defense_proof` payload to the existing `POST /api/v1/domains` request:

```sh
curl -X POST http://localhost:8000/api/v1/domains \
  -H 'Content-Type: application/json' \
  -d '{
    "owner_id": 1,
    "device_timestamp": "2026-04-30T18:00:00Z",
    "defense_score": 30,
    "defense_type": "pushups",
    "coordinates": [
      {"lat": 43.50, "lng": -80.50, "timestamp": "2026-04-30T17:55:00Z"},
      {"lat": 43.501, "lng": -80.50, "timestamp": "2026-04-30T17:56:00Z"},
      {"lat": 43.501, "lng": -80.501, "timestamp": "2026-04-30T17:57:00Z"},
      {"lat": 43.50, "lng": -80.501, "timestamp": "2026-04-30T17:58:00Z"},
      {"lat": 43.50, "lng": -80.50, "timestamp": "2026-04-30T17:59:00Z"}
    ],
    "defense_proof": {
      "activity_type": "pushups",
      "declared_score": 30,
      "duration_seconds": 30,
      "device_timestamp": "2026-04-30T18:00:00Z",
      "accelerometer": [
        {"t_ms": 0,    "ax": 0, "ay": 0, "az": 9.8},
        {"t_ms": 500,  "ax": 0, "ay": 0, "az": 14.8},
        {"t_ms": 1000, "ax": 0, "ay": 0, "az": 9.8}
        /* ... ~600 samples total at 20Hz ... */
      ],
      "pose": {
        "rep_count": 30,
        "min_joint_angle_deg": 80,
        "max_joint_angle_deg": 170,
        "avg_rep_duration_ms": 1000
      }
    }
  }'
```

If `defense_proof` is omitted, the endpoint falls back to trusting `defense_score` (legacy mode). If it's present and rejected, the entire claim 400s with the verifier's flags as the detail. Same pattern for `challenger_proof` on `POST /api/v1/sieges/{id}/resolve` and `score_proof` on `POST /api/v1/bounties/{id}/complete`.

For a cheaper preview (no DB writes), `POST /api/v1/activities/verify` accepts the same `proof` shape and returns the verdict only.

---

## 9. Revision History

| Version | Date | Author | Summary |
| :--- | :--- | :--- | :--- |
| 1.0 | 2026-03-xx | G. Thind | Initial task list tracking Phase 1 progress |
| 2.0 | 2026-04-20 | G. Thind | Added Epic 5/6 plans, frontend workstream, open decisions; reformatted to corporate standard |
| 2.1 | 2026-04-20 | G. Thind | Epic 5 shipped; open decisions narrowed; pivoted next sprint to Epic 6 + Bounty Board |
| 2.2 | 2026-04-20 | G. Thind | Siege-loss split reworked (50/30/20) + Retry Discount; device-authoritative timestamps; Epic 6 shipped |
| 2.3 | 2026-04-20 | G. Thind | Epic 1 (Bounty Board) shipped; doc rewritten as a What/Why/How handoff guide with cold-start runbook (§ 8) |
| 2.3.1 | 2026-04-20 | G. Thind | Renamed backend folder `Osiris/` → `Osiris_backend/` to disambiguate from the Flutter app project; updated all path references in this doc |
| 2.4 | 2026-04-27 | AI | Restructured Task.md into # Backend and # Frontend sections; mapped Frontend Epics 1-5 |
| 2.5 | 2026-04-28 | G. Thind | Epic 2 (ML Referee) shipped — `ml_referee.py` heuristic verifier, `/activities/verify` preview endpoint, optional `proof` wired into 3 action endpoints. Backend Phase 1 now feature-complete; sprint pivoted to hardening + frontend support. |
| 2.6 | 2026-04-30 | G. Thind | Hardening sprint shipped — `PlatformRevenue` ledger + `/platform/revenue` audit endpoint; `lifespan` migration replacing `@app.on_event`; `tests/test_ml_referee.py` (10/10 pass); `scripts/export_openapi.py` writing `Documentation/openapi.json` (14 paths); verified-flow curl example added to § 8.3. |
| 2.7 | 2026-04-30 | G. Thind | `ActivityLog` table + `record_activity` helper wired through all three action endpoints; `?window_days=N` opt-in rolling Party Stats on `/users/{id}/party-role`; `ProofConsumed` table + replay-attack guard (409 on duplicate proof key) hashing user_id+timestamp+activity+score+accel samples; `_enforce_proof` refactored to surface confidence to call sites. Two open economy decisions ratified pending ack. |
| 2.8 | 2026-05-04 | G. Thind | Three-portal auth architecture — new `Admin` table; `POST /api/v1/auth/login` probes Admin → Merchant → Player and returns the matching `role` for Flutter UI routing; `scripts/seed_admin.py` for out-of-band admin creation (no public admin registration endpoint). End-to-end smoke verified all four cases (admin / merchant / player / 401) on `fitness_mvp.db`. |
| 2.9 | 2026-05-04 | G. Thind | Merchant payment lifecycle + JWT — Merchant model extended with `payment_status` / `payment_provider_id` / `pilot_fee_cents` / `last_payment_at`; new endpoints `/merchants/{id}` (self-profile), `/merchants/{id}/payments/intent`, `/payments/webhook`, `/admin/merchants` (list + activate + deactivate); `merchant_chest` bounty creation now 403s for inactive merchants; JWT actively used by `get_current_admin/merchant/player` dependencies; one-time `scripts/migrate_v2_9.py` adds the four new columns to existing SQLite. End-to-end smoke verified the full webhook flow (pending / successful / declined). |
| 2.10 | 2026-05-04 | G. Thind | Pilot-ready backend: full telemetry capture (`TelemetrySession` + `TelemetryData` for accel/gyro/mag/GPS/baro/pose, linked to ActivityLog); `GET /domains/nearby` (Flutter map unblocker); `GET /merchants/{id}/bounties` (analytics); JWT secret to `OSIRIS_JWT_SECRET` env var with prod fail-fast; webhook signature verification (`OSIRIS_WEBHOOK_SECRET` HMAC-SHA256); RBAC on `/users/{id}` and tightened on `/bounties` per-type. 23 OpenAPI paths, 29 routes, smoke verified end-to-end on real DB. |
| 2.11 | 2026-05-04 | G. Thind | Pilot demo prep: `scripts/seed_pilot.py` (3 players, 1 active merchant, 2 domains, 5 bounties around DeWolf Park, idempotent); `MAX_SAMPLES_PER_CHANNEL=20000` Pydantic DoS cap on `ActivityProof`; `process_telemetry_ttl()` nightly job purging `TelemetryData` older than `OSIRIS_TELEMETRY_TTL_DAYS` (default 90); `tests/test_v2_10_flows.py` (7/7) covering telemetry persistence, replay-attack 409, DoS cap, RBAC matrix. Sprint pivots to v2.12 (real payments + portal frontends). |
