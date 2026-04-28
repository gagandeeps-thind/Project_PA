# Osiris — Project Task Tracker & Handoff Guide

| Field | Value |
| :--- | :--- |
| **Document Type** | Project Task Tracker + Onboarding Handoff |
| **Version** | 2.4 |
| **Last Updated** | 2026-04-20 |
| **Owner** | Gagandeep Thind |
| **Phase** | Phase 1 — MVP (Backend complete through Epic 1) |
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
  - `models.py` — All ORM models (User, Domain, SiegeLog, SiegeDiscount, Merchant, Bounty, BountyCompletion).
  - `spatial_utils.py` — Pure-math helpers: `haversine_distance`, `calculate_polygon_area_sqkm` (Shoelace), `point_in_polygon` (ray casting), `is_polygon_swallowed`, `check_velocity_violation`.
  - `main.py` — FastAPI app: Pydantic schemas, business logic, all REST endpoints, `process_daily_decay` cron, and economy/stat constants.
- `Documentation/Imp_and_US.md` — Master Game Design + Technical Design Document. Source of truth for mechanics & user stories.
- `Task.md` — *(this file)* — execution tracker + onboarding doc.

**Stack:**
- **Backend:** Python 3, FastAPI, SQLAlchemy ORM, bcrypt (passwords), APScheduler (cron), SQLite (MVP) → PostgreSQL+PostGIS (Phase 2).
- **Frontend:** Flutter — built in **Google Antigravity** as a parallel workstream (not in this repo).

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

### 2.8 Time-Source Policy *(Established v2.2)*

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

### Sprint Goal
Stand up Epic 2 (ML Referee) so we can stop trusting client-submitted scores, **and** start the Flutter frontend in Google Antigravity.

### Sprint Backlog

**Epic 2 — ML Referee (Anti-Cheat)**
- 📋 Define `ActivityProof` Pydantic schema (raw accelerometer samples, video metadata, declared score).
- 📋 `POST /api/v1/activities/verify` — accept a proof, run validation, return verified score + confidence.
- 📋 Accelerometer frequency-pattern detector (Scikit-learn) — reject phone-shaking patterns.
- 📋 MediaPipe pose-estimation hook — for now, accept frontend-extracted keypoint counts and rule-check; on-device inference stays in Flutter.
- 📋 Wire verified scores into `submit_domain`, `resolve_siege`, `complete_bounty` (replace direct `score` trust).

**Frontend Track — Flutter (in Google Antigravity)**
- 📋 Bootstrap project; pull OpenAPI spec from FastAPI `/docs`.
- 📋 Screens: Awakening (register), Login, Dashboard, Map, Bounty list.
- 📋 Wire `device_timestamp` (use `DateTime.now().toUtc().toIso8601String()` on every activity call).

**Operational Follow-ups**
- ❗ **Delete `Osiris_backend/fitness_mvp.db`** before next backend run — Epic 1 added 3 new tables (`merchants`, `bounties`, `bounty_completions`). SQLAlchemy creates tables on startup but does **not** add columns to existing rows.
- 📋 Consider a `PlatformRevenue` ledger model to make War Tax / pilot fees auditable.
- 📋 Address `on_event` deprecation in `main.py` (FastAPI moved to `lifespan` handlers — non-blocking).

---

## 4. Backlog — Phase 1

### Epic 2 — ML Referee
*See Active Sprint above.*

### Epic 3 — B2B Merchant Flow (residual)
- ⏳ Merchant Portal authentication (JWT)
- ⏳ Pilot fee billing / payment integration
- ⏳ Merchant analytics dashboard (chests claimed, coupons redeemed)

### Cross-Cutting
- ⏳ Trace-shatter on siege loss (currently keeps the challenger polygon — see Epic 5 simplifications)
- ⏳ `ActivityLog` model + nightly job → unlock 30-day rolling Party Stats
- ⏳ Replace deprecated FastAPI `@app.on_event` with lifespan event handlers

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
| Default bounty XP / crystal rewards | G. Thind | ❗ Needs decision | Currently `xp_reward=50` default in Pydantic; product calibration TBD |
| Ownership Fee tier minimums | G. Thind | ❗ Needs decision | Proposal: Warden 10 / Lord 50 / High Lord 200 / Sovereign 1000 crystals |
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
- [ ] Build Bounty List/Map View (fetching from `GET /api/v1/bounties/nearby`).
- [ ] Implement AR / Chest unlocking sequence when within range.
- [ ] Wire up `POST /api/v1/bounties/{id}/complete` and display coupon codes.
- [ ] Implement Vault UI to manage Mana Crystals and Ownership Fees.

**Epic 5 — Profile & Adventure Party**
- [ ] Build Profile Screen showing STR / AGI / END / CON.
- [ ] Fetch and display Party Role via `GET /api/v1/users/{id}/party-role`.
- [ ] Display current Rank and progression.

## 8. How to Resume This Project (Cold-Start Guide)

If you're picking this up from scratch:

1. **Read `Documentation/Imp_and_US.md` end-to-end.** It is the source of truth for game mechanics and explains *why* the system is shaped the way it is.
2. **Skim § 1 and § 2 of this file** for the project layout and what's built.
3. **Run the backend locally:**
   ```bash
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
6. **Pick the next ticket from § 3 (Active Sprint).** Epic 2 (ML Referee) is the natural next step — it removes the last "trust the client" gap.
7. **Frontend work happens in Google Antigravity, not here.** Coordinate via the OpenAPI spec; the contract is the only shared artifact.

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
