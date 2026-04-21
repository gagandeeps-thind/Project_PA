# Osiris — Project Task Tracker

| Field | Value |
| :--- | :--- |
| **Document Type** | Project Task Tracker |
| **Version** | 2.2 |
| **Last Updated** | 2026-04-20 |
| **Owner** | Gagandeep Thind |
| **Phase** | Phase 1 — MVP (Backend + Auth + Territory) |
| **Companion Doc** | `Documentation/Imp_and_US.md` |

---

## Status Legend
| Symbol | Meaning |
| :--- | :--- |
| ✅ | Completed |
| 🚧 | In Progress |
| 📋 | Planned (Next Sprint) |
| ⏳ | Backlog |
| ❗ | Blocked / Needs Decision |

---

## 1. Completed Milestones

### 1.1 Documentation & Design
- ✅ Master GDD/TDD — mechanics for Titles, Ranks, Guilds, B2B/B2C economy
- ✅ Anti-Cheat Verification Matrix — Velocity Lock, Polygon Swallowing, Closure Tolerance

### 1.2 Database & Data Models
- ✅ Local DB — SQLite configured for rapid local dev
- ✅ `User` schema — RPG stats baseline
- ✅ `Domain` and `SiegeLog` schemas — territorial data

### 1.3 Backend Utilities
- ✅ Haversine distance (real-world km between GPS points)
- ✅ Shoelace algorithm (approximate polygon area in km²)
- ✅ Velocity Lock (anti-cheat: speed > 25 km/h)
- ✅ Ray-casting Point-in-Polygon + swallowing check

### 1.4 Core Backend APIs (Phase 1)
- ✅ `POST /api/v1/onboard` — BMI, Avatar Class, stat initialization (starter 100 Mana Crystals)
- ✅ `POST /api/v1/login` — bcrypt credential verification (max 12-char password — intentional)
- ✅ `GET /api/v1/users/{user_id}` — profile fetch (includes `mana_crystals`)
- ✅ `POST /api/v1/domains` — submission with closure + velocity validation, area calc, siege detection, claim XP
- ✅ Grade & Map Title stat engine
- ✅ `process_daily_decay` — XP/streak decay via APScheduler background job

### 1.5 Epic 5 — Land Ownership & Siege Resolution *(Shipped v2.1, Refined v2.2 — 2026-04-20)*
- ✅ Virtual currency confirmed for Phase 1: Mana Crystals
- ✅ `User.mana_crystals`, `Domain.vault_balance`, `SiegeLog.{defender_score_snapshot, challenger_fee, challenger_score, resolved_at}` schema extensions
- ✅ `POST /api/v1/domains/{id}/vault` — lock / top-up Ownership Fee
- ✅ `POST /api/v1/sieges/{id}/resolve` — Defense Feat submission, polygon erasure on win
- ✅ XP on claim (`area_sqkm × 100`) + siege-win bonus (`+500`) with automatic Rank recompute
- ✅ Defender score snapshotted at siege creation to prevent post-hoc edits
- ✅ **v2.2:** Siege-loss split reworked → 50% defender / 30% system / 20% retry-discount
- ✅ **v2.2:** `SiegeDiscount` model + auto-apply on re-attack of same target_domain

### 1.6 Epic 6 — Party Attribute Stats *(Shipped v2.2 — 2026-04-20)*
- ✅ `User.{str_stat, agi_stat, end_stat, con_stat}` columns
- ✅ `DEFENSE_TYPE_TO_STAT` mapping drives increments from `defense_type` + `defense_score`
- ✅ `increment_stat_from_activity()` wired into both claim (`submit_domain`) and siege resolve paths
- ✅ `get_party_role()` helper resolves Vanguard / Striker / Scout / Strategist
- ✅ `GET /api/v1/users/{id}/party-role` endpoint
- 📋 30-day rolling window (via `ActivityLog` table) deferred to Phase 2

### 1.7 Time-Source Policy *(Established v2.2)*
- ✅ All user-initiated endpoints accept a `device_timestamp` (client-authoritative)
- ✅ Server-owned clocks (decay, inactivity check) use `_now_naive_utc()`
- ✅ Replaced deprecated `datetime.utcnow()` throughout

---

## 2. Active Sprint — Next Up

### Sprint Goal
Kick off Epic 1 (Bounty / Quest Board) so users have more ways to earn XP and feed the stat engine, and start the Epic 2 (ML Referee) scaffolding.

### Sprint Backlog

**Epic 1 — Bounty Board (Foundation)**
- 📋 `Bounty` and `Merchant` DB models
- 📋 `GET /api/v1/bounties/nearby` — geofenced bounty list by GPS
- 📋 `POST /api/v1/bounties/{id}/complete` — mark bounty complete + award XP + stat increment

**Operational Follow-ups**
- ❗ Delete dev `Osiris/fitness_mvp.db` and let SQLAlchemy recreate it — v2.1/v2.2 added columns (`mana_crystals`, `vault_balance`, stat columns, `siege_discounts` table) that existing rows lack
- 📋 Flutter frontend: start consuming OpenAPI spec (include `device_timestamp` in every activity call)

---

## 3. Backlog — Phase 1

### Epic 1 — Bounties (Quest Board)
- ⏳ `Bounty` and `Merchant` DB models
- ⏳ `GET /api/v1/bounties/nearby` — geofenced bounty list by GPS
- ⏳ `POST /api/v1/bounties/{id}/complete` — mark bounty complete + award XP

### Epic 2 — ML Referee (Anti-Cheat)
- ⏳ Accept "Ghost Score" submissions (push-up counts) from Flutter client
- ⏳ Validate counts via MediaPipe pose-estimation metadata
- ⏳ Accelerometer frequency-pattern model (reject non-human rhythm)

### Epic 3 — B2B Merchant Flow
- ⏳ Merchant registration + auth
- ⏳ Chest placement endpoint (lat/lng, reward, max users, pilot fee)
- ⏳ Chest-unlock endpoint (10 m proximity check)

---

## 4. Backlog — Phase 2 (Production Readiness)

- ⏳ Migrate SQLite → PostgreSQL + PostGIS (spatial intersect queries)
- ⏳ Replace `geometry_json` string column with PostGIS `Geometry('POLYGON')`
- ⏳ Replace Shoelace approximation with `ST_Area`
- ⏳ JWT-based session tokens (replace stateless re-auth pattern)
- ⏳ Rate limiting + abuse detection on Vault endpoints
- ⏳ CI/CD pipeline + containerization

---

## 5. Newly Identified Features / Open Decisions

| Item | Owner | Status | Notes |
| :--- | :--- | :--- | :--- |
| XP reward per km² claimed | G. Thind | ✅ Decided | `area_sqkm × 100` on claim, `+500` bonus on siege win (see `CLAIM_XP_PER_SQKM`, `SIEGE_WIN_XP_BONUS`) |
| Vault currency (USD vs Mana Crystals) | G. Thind | ✅ Decided | Phase 1 = Mana Crystals (virtual); Phase 2 = convertible to real-world currency |
| Starter Mana Crystal balance | G. Thind | ✅ Decided | 100 crystals on onboarding |
| Ownership Fee tier amounts (recommended minimums) | G. Thind | ❗ Needs decision | Proposal: Warden 10 / Lord 50 / High Lord 200 / Sovereign 1000 crystals |
| Trace-shatter on siege loss | G. Thind | ⏳ Phase 2 | MVP keeps challenger's polygon intact to simplify state management |
| Frontend project bootstrap in Google Antigravity | G. Thind | 📋 Planned | Will consume OpenAPI spec from FastAPI `/docs` |

---

## 6. Frontend Track (Google Antigravity — Parallel Workstream)

- ⏳ Initialize Flutter project (`Osiris-App`) in Google Antigravity
- ⏳ Import OpenAPI client generated from FastAPI `/docs` as API contract
- ⏳ Screens: Awakening (register), Login, Dashboard
- ⏳ Map UI: Mapbox / Google Maps for territories + bounties
- ⏳ AR loot drops: ARCore / ARKit integration

---

## 7. Revision History

| Version | Date | Author | Summary |
| :--- | :--- | :--- | :--- |
| 1.0 | 2026-03-xx | G. Thind | Initial task list tracking Phase 1 progress |
| 2.0 | 2026-04-20 | G. Thind | Added Epic 5 (Ownership/Siege Resolution), Epic 6 (Attribute Stats), frontend workstream, open decisions log; reformatted to corporate standard |
| 2.1 | 2026-04-20 | G. Thind | Epic 5 shipped; open decisions narrowed (XP formula, starter balance, currency model); next sprint pivoted to Epic 6 + Bounty Board |
| 2.2 | 2026-04-20 | G. Thind | Epic 5 siege-loss split reworked (50/30/20) + Retry Discount; device-authoritative timestamps policy; Epic 6 (Party Stats + Party Role endpoint) shipped; sprint pivoted to Epic 1 Bounty Board |
