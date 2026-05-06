# Osiris — Master Game Design & Technical Document

| Field | Value |
| :--- | :--- |
| **Document Type** | Game Design Document / Technical Design Document (GDD/TDD) |
| **Version** | 2.0 |
| **Last Updated** | 2026-04-20 |
| **Owner** | Gagandeep Thind |
| **Status** | Active Development — Phase 1 MVP |
| **Classification** | Internal — Project Reference |

---

## Table of Contents
1. Executive Summary
2. Project Identity & Vision
3. Progression & Hierarchy System
4. Gameplay Loop & Party Mechanics
5. Economy & Business Model
6. Technical Architecture
7. SDLC — MVP Implementation Plan
8. Risk Register
9. Revision History

---

## 1. Executive Summary

Osiris is a high-stakes, real-world Action-RPG where verified physical effort translates into digital rank, territorial control, and financial rewards. An AI-driven "Referee" validates movement and exercise via GPS, IMU, and on-device pose estimation, establishing a true economy of effort and preventing the cheating common in standard fitness applications.

**The Hook:** *"Earn Your Awakening."*

**Strategic Moat:** Hybrid sensor fusion anti-cheat layer combined with a dual B2B/B2C economy that binds local foot-traffic to a persistent RPG world.

---

## 2. Project Identity & Vision

### 2.1 Vision Statement
Deliver a persistent virtual world overlaid on the real world, in which every square kilometer of land can be claimed, defended, or conquered through verified physical performance.

### 2.2 Core Pillars
- **Verified Effort:** No effort is rewarded unless the AI Referee confirms it.
- **Persistent Ownership:** Territory is a living asset backed by real money and real effort.
- **Dual Identity:** Players hold both a Physical Grade (raw power) and a Territorial Title (world influence).

---

## 3. Progression & Hierarchy System

### 3.1 Physical Grade (Combat Rank)
Calculated by the AI Referee from the user's completion of verified physical tasks.

| Rank | Title (Prestige) | Requirements & Decay Logic |
| :--- | :--- | :--- |
| **SSS / SS / S** | God, Emperor, King | Top 0.1% of Global Leaderboard + Unique Feats |
| **A / B** | Saint, Advanced | Consistent high-level output |
| **C / D** | Intermediate, Beginner | Baseline fitness; starting users ("The Awakened") |
| **F** | The Dishonored | Flagged for cheating or inactivity > 30 days |

### 3.2 Peerage (Territorial Title)
Titles are tied to **Cumulative Land Ownership** via Domain Expansion. Players trace GPS polygons in the real world to claim land.

| Title | Cumulative Area | Map Privilege | Real-World Feat Equivalent |
| :--- | :--- | :--- | :--- |
| **Warden** | 1.0 km² | Receives Base Tax from players inside | ~4 km perimeter run |
| **Lord** | 5.0 km² | Custom AR Flag on map center | ~9 km perimeter run (or 5 Wardens) |
| **High Lord** | 20.0 km² | Controls weather/spawn conditions | ~18 km perimeter run (or 4 Lords) |
| **Sovereign** | 100.0+ km² | Sovereign-only Guild Hall access | Massive Guild Coordination |

### 3.3 Party Attribute Stats (STR / AGI / END / CON)
Every verified activity feeds into a rolling 30-day attribute profile used for Party Role assignment and dungeon matchmaking.

| Stat | Abbreviation | Driver Activities | Used For |
| :--- | :--- | :--- | :--- |
| **Strength** | STR | Push-ups, squats, resistance work | Vanguard (Tank) role |
| **Agility** | AGI | Sprints, burpees, high-cadence movement | Striker (DPS) role |
| **Endurance** | END | Long-distance runs, sustained volume | Scout (Support) role |
| **Consistency** | CON | Streak, daily logins, precision holds (planks) | Strategist (Healer) role |

---

## 4. Gameplay Loop & Party Mechanics

### 4.1 Onboarding (The Awakening)
- **Input:** Height, Weight, Age, Gender.
- **Assessment Quest:** Baseline physical test (push-ups, running) verified by the AI.
- **Avatar:** User is assigned a 2D Sprite Class (Tank, Assassin, Mage) matching their chosen path (Strength / Cardio / Balance).

### 4.2 Daily Bounties & Dungeons
- **Bounties:** Low-stakes tasks ("Walk 5k steps," "Do 20 push-ups") to maintain XP and avoid Rank Decay.
- **Dungeons:** Premium GPS-gated zones. Users pay Mana Crystals to enter and clear a timed sequence of exercises for high-tier loot.

### 4.3 Domain Expansion (Territory Wars)
*Strava Art meets Splatoon.* Players convert physical runs/walks into closed GPS polygons. The enclosed area becomes Virtual Property.

- **The Cast:** User pays Mana Crystals, traces a path via GPS (polled every 5 s), and closes the loop (returning to start within 20 m).
- **The Imprint:** On closure, player performs a "Defense Feat" (e.g., max push-ups in 2 min) verified by the AI Referee to set the defending Ghost score.
- **Guild Empires:** Intersecting domains of Guild members merge into a unified "Guild Empire."

### 4.4 Land Ownership Economy *(New — v2.0)*

At world launch, the entire real-world map is **unclaimed**. Ownership is acquired by running a closed polygon; however, the security of that ownership depends on whether the player elects to pay the **Ownership Fee**.

| Ownership State | Mechanic | Siege Rule |
| :--- | :--- | :--- |
| **Unclaimed Land** | Default state of all global territory at launch | Any player may claim by closing a polygon |
| **Claimed — Free Tier** | Polygon claimed but no Ownership Fee paid | Any challenger may siege and take the land by re-running the same closed polygon |
| **Claimed — Paid Tier (Vault)** | Owner has locked an Ownership Fee (Mana Crystals in Phase 1) in the Vault | Challenger must (a) encapsulate the polygon, (b) pay a matched Challenge Fee, AND (c) beat the Defense Feat Ghost score |

**Currency Model:**
- **Phase 1 (MVP):** All fees, vaults, and payouts use virtual Mana Crystals. Starter balance: 100 crystals per new user.
- **Phase 2 (Production):** Mana Crystals become convertible to real-world currency; regulatory compliance layer added.

**Reward on Successful Siege (Paid Tier):**
- Challenger claims the land (defender's polygon erased).
- Pot = defender's Vault + challenger's matched Fee. Winner takes **80%**, platform retains **20% War Tax**.
- Previous owner forfeits the Vault entirely.

**Penalty on Failed Siege (Paid Tier):** *(updated v2.2)*
The challenger's matched Fee is split three ways:

| Portion | Destination | Purpose |
| :--- | :--- | :--- |
| **50%** | Defender's Vault | Rewards successful defense; grows the moat |
| **30%** | Platform (System) | War Tax revenue, retained outright |
| **20%** | Retry Discount | Banked as `SiegeDiscount` credit for the **same challenger vs. the same domain**; auto-applied on the next attempt |

The Retry Discount reduces the challenger's out-of-pocket cost on re-attempt but the full match is still treated as the pot basis for payout math — the system subsidizes the gap as a loyalty rebate to aggressive re-challengers. Discount credits are single-use and evaporate automatically when the defender's domain is erased (win) or consumed (retry).

### 4.5 Siege Resolution Flow *(New — v2.0)*

1. **Trigger:** Challenger submits a domain that encapsulates an existing domain (ray-casting check). A `SiegeLog` row is created with `status = pending_feat`.
2. **Defense Feat:** Challenger is prompted to perform the same exercise type as the defender's Ghost score, verified by the AI Referee.
3. **Resolution:**
   - *Win:* Defender's polygon is erased; challenger claims the area; Vault payout executes.
   - *Loss:* Challenger's trace shatters; Mana Crystals and Challenge Fee are lost.
4. **Audit:** `SiegeLog.status` transitions to `won` or `failed`, with timestamp and score snapshots retained for disputes.

### 4.6 Adventure Party (Role Assignment)
When players group for Dungeons or Raid Bosses, the System assigns roles based on the **verified 30-day attribute profile** (§ 3.3):

- **Vanguard (Tank) →** Highest STR. Explosive, heavy-resistance movements to block boss attacks.
- **Striker (DPS) →** Highest AGI. High-speed movement (sprinting, burpees) for burst damage.
- **Scout (Support) →** Highest END. Sustained volume (long-distance) provides party buffs.
- **Strategist (Healer) →** Highest CON. Precision holds (planks) restore the party's time limit.

---

## 5. Economy & Business Model

Osiris operates on a dual B2B/B2C revenue model, blending real-world local business with an RPG economy.

### 5.1 B2C — The Adventurer's Economy
| Stream | Mechanic | Platform Cut |
| :--- | :--- | :--- |
| **Defender's Vault & Challenge Tax** | Real money locked to hold a Territorial Title; challenger matches. Winner takes title + 80% of pot. | **20% War Tax** |
| **Black Market** | User-to-user trading hub for rare digital loot (Skins, Artifacts). | **15% transaction fee** |
| **Tower Pass** | Subscription: XP boosters, Decay Shields, premium cosmetics. | **$9.99 / month** |

### 5.2 B2B — Foot Traffic as a Service
- **Merchant Portal:** Web dashboard where local businesses pay (~$50) to host a Legendary Chest.
- **The Conversion:** Chests unlock when a player is within 10 m of the shop. Inside: XP + digital coupon (e.g., "20% off a protein smoothie").

---

## 6. Technical Architecture

### 6.1 Verification Matrix (The Moat)
| Threat | Countermeasure |
| :--- | :--- |
| **Vehicle GPS Spoofing** | Velocity Lock: if Velocity > 25 km/h for > 10 s, Domain Trace shatters |
| **Invalid Polygons** | Closure Tolerance: must return to origin within 20 m |
| **Polygon Swallowing** | Ray-Casting Algorithm: all target vertices must fall inside challenger shape |
| **Accelerometer Spoofing** | Frequency-pattern matching rejects non-human rhythm |

### 6.2 Sensor Compute Cost
| Exercise | Primary Sensor | Logic | Compute Cost |
| :--- | :--- | :--- | :--- |
| Sprinting / Running | GPS + Accelerometer | Speed/Cadence validation; Velocity filter (< 25 km/h) | Low |
| Skipping / Jumping | Accelerometer / IMU | Frequency (Hz) pattern matching | Low |
| Push-ups / Squats | Camera (MediaPipe) | On-device pose estimation @ 15 FPS | Medium / High |
| Dungeon Clearing | Geofencing | Radius-based entry/exit triggers | Low |

### 6.3 Tech Stack
| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Frontend / Mobile** | Flutter (developed in Google Antigravity) | Cross-platform; strong AR + Maps support |
| **Backend** | Python + FastAPI (developed in VS Code) | High-performance ML integration; async-ready |
| **Database — MVP** | SQLite | Zero-setup local development |
| **Database — Prod** | PostgreSQL + PostGIS | Required for `ST_Area` and spatial intersect |
| **ML / CV** | MediaPipe (on-device) + Scikit-learn (anomaly detection) | Battery-efficient, privacy-first |
| **Contract** | OpenAPI 3.0 (auto-generated by FastAPI at `/docs`) | Single source of truth shared with frontend |

### 6.6 Three-Portal Auth Architecture *(Established v2.8)*

A single Flutter mobile-app codebase serves three distinct UIs, chosen at login by which database table the credentials match:

| Portal | Audience | Registration Surface | Login Surface | Returned `role` |
| :--- | :--- | :--- | :--- | :--- |
| **Game (Player)** | End users / pilot testers | In-app onboarding (`POST /api/v1/onboard`) | In-app login | `"player"` |
| **Merchant** | Local businesses (cafes, gyms, retail) | Web portal *(Phase 2)* | Same in-app login | `"merchant"` |
| **Admin** | Gagan only — single tenant | None (seeded via CLI: `scripts/seed_admin.py`) | Same in-app login | `"admin"` |

**Routing contract:** `POST /api/v1/auth/login` probes Admin → Merchant → User in that order and returns `{role, id, email, name}`. The Flutter app uses `role` to decide which navigator stack to push. On 401, the response is generic ("Invalid email or password") so callers cannot enumerate which table contains a given email.

**Why this shape:**
- Admin access is enforced at the data layer — there is no public registration endpoint, so an attacker cannot grant themselves admin rights via the API.
- Merchants and admins log in through the same mobile app as players (single binary to maintain), but the server, not the client, decides which UI they see.
- `/api/v1/login` (player-only, legacy) is kept for backward compatibility while clients migrate to `/auth/login`.

### 6.4 Frontend–Backend Collaboration Model
- Backend is authored in VS Code (this workspace) and exposes a versioned REST API (`/api/v1/...`).
- Frontend (Flutter) is authored in Google Antigravity and consumes the REST API.
- FastAPI's auto-generated OpenAPI spec at `/docs` is the contract both sides code against.
- CORS must remain permissive during MVP development; lock down before public launch.

### 6.5 Time-Source Policy *(New — v2.2)*
Activity timestamps are **client-authoritative**. Every endpoint that records a user-initiated event requires a `device_timestamp` (ISO 8601) field captured on the mobile device:

| Endpoint | Uses `device_timestamp` for |
| :--- | :--- |
| `POST /api/v1/onboard` | `users.last_activity_date` |
| `POST /api/v1/login` | `users.last_activity_date` |
| `POST /api/v1/domains` | `users.last_activity_date` |
| `POST /api/v1/sieges/{id}/resolve` | `sieges_log.resolved_at`, `users.last_activity_date` |

**Server-owned clocks** (no device input): the nightly decay job (`process_daily_decay`) and the Rank inactivity check (`get_rank`) both use server `now` — relying on device clocks for decay would be trivially exploitable.

All stored timestamps are naive UTC for SQLite compatibility; Phase 2 PostgreSQL migration will switch to `TIMESTAMPTZ`.

---

## 7. SDLC — MVP Implementation Plan

### 7.1 Scope (The Bedford Pilot)
- **Zone:** DeWolf Park to Sunnyside Mall.
- **Users:** ~50 testers per bounty.
- **Constraint:** Avoid live-road speed quests. Rely on "Stay in the Zone" park quests.

### 7.2 Core User Stories

**Epic 1 — Participation** *(Backend implemented — v2.3)*
- ✅ *1.1* As a user, I want to see nearby bounties on a map so I can choose a challenge. → `GET /api/v1/bounties/nearby?lat&lng&radius_km`
- 📋 *1.2* As a user, I want to open my camera after a quest to claim an AR Treasure Chest. → Frontend (Antigravity) — backend already issues coupon codes via merchant_chest bounties.
- ✅ *1.3* As an admin/merchant, I want to seed bounties at specific GPS coordinates with reward + completion-cap settings. → `POST /api/v1/bounties`, `POST /api/v1/merchants/register`
- ✅ *1.4* As the system, I will enforce one-claim-per-user, geofence proximity (haversine), score gate, and coupon issuance on `POST /api/v1/bounties/{id}/complete`.

**Epic 2 — Verification (Anti-Cheat)** *(Implemented — v2.4)*
- ✅ *2.1* As the system, I will verify GPS coordinates within a 30 m polygon to ensure physical presence. → Closure tolerance + Velocity Lock in `submit_domain`; geofence proximity check in `complete_bounty`.
- ✅ *2.2* As the system, I will analyze accelerometer arrays to classify human stride vs. phone shaking (85% confidence required). → `Osiris_backend/ml_referee.py` (`check_accelerometer_pattern`, `CONFIDENCE_THRESHOLD = 0.85`).
- ✅ *2.3* As the system, I will accept a MediaPipe pose summary from the client and reject incomplete reps (range-of-motion + min-angle gates).
- ✅ *2.4* As the system, I will sanity-cap declared scores against the activity's max human rate per second.
- ✅ *2.5* As a client, I can preview verification via `POST /api/v1/activities/verify` before submitting an action.
- ✅ *2.6* As an action endpoint (`/domains`, `/sieges/{id}/resolve`, `/bounties/{id}/complete`), I will accept an optional `proof` field; if present, the verified_score replaces the client-trusted score, and rejection 400s the request.

**Epic 3 — Business Flow** *(Partially implemented — v2.3)*
- ✅ *3.1* As a merchant, I want to define reward amount, max users, and place a chest at my storefront. → Covered by `bounty_type='merchant_chest'` on `POST /api/v1/bounties`. Pilot-fee billing deferred.
- 📋 *3.2* Merchant Portal web dashboard (separate frontend workstream).
- 📋 *3.3* Pilot-fee invoicing / payment integration.

**Epic 4 — Domain Expansion (Territory Wars)**
- *4.1* As a user, I want to press "Start Domain" and see a breadcrumb trail of my path on the map.
- *4.2* As the system, I will enable "Close Domain" when the user is within 20 m of the start point.
- *4.3* As the backend, I will reject any domain submission where average speed exceeded 25 km/h.
- *4.4* As the backend, I will use Point-in-Polygon logic to detect a swallowing event and trigger a Siege.
- *4.5* As the system, I will aggregate `area_sqkm` per user and update their Map Title automatically.

**Epic 5 — Land Ownership & Siege Resolution** *(Implemented — v2.1)*
- ✅ *5.1* As a user, I want to optionally lock an Ownership Fee on a claimed domain to protect it. → `POST /api/v1/domains/{id}/vault`
- ✅ *5.2* As the system, I will match a challenger's fee against the defender's Vault before allowing a siege. → Enforced in `resolve_siege`.
- ✅ *5.3* As the system, I will resolve a pending siege when the challenger submits a valid Defense Feat score. → `POST /api/v1/sieges/{id}/resolve`
- ✅ *5.4* As the system, I will distribute Vault payouts (80% to winner, 20% War Tax) and erase the losing polygon. → `WAR_TAX_PCT = 0.20`; defender's domain deleted on loss.
- ✅ *5.5* As the system, I will award claim XP (`area_sqkm × 100`) and a siege-win XP bonus (`+500`), recomputing Rank on each award.

**Epic 6 — Party Attribute Stats** *(Implemented — v2.2)*
- ✅ *6.1* As the system, I will increment STR / AGI / END / CON on every verified activity. → `increment_stat_from_activity()` called from `submit_domain` and `resolve_siege`.
- 📋 *6.2* As the system, I will recompute the user's 30-day profile nightly. → MVP uses lifetime totals; 30-day rolling deferred to Phase 2 (requires an `ActivityLog` table).
- ✅ *6.3* As the party engine, I will assign Vanguard / Striker / Scout / Strategist based on the highest stat. → `GET /api/v1/users/{id}/party-role`.

### 7.3 Risk Mitigation
| Risk | Mitigation |
| :--- | :--- |
| GPS Spoofing | Cross-check sudden coordinate jumps with realistic acceleration constraints |
| Cheating (Shaking) | Train ML model on accelerometer frequency patterns to reject non-human rhythms |
| Live Betting Latency | MVP betting/challenges are asynchronous (beat a Ghost score), not live 1v1 video |
| Avatar Body-Shaming | No strict BMI visual morphing; users choose a Class Path (Strength / Cardio / Balance) |
| Vault Dispute / Fraud | All Vault transactions logged in `SiegeLog` with immutable audit trail |

---

## 8. Risk Register
See § 7.3 above. Risks are reviewed at the end of every sprint and promoted to the Task tracker if mitigation work is required.

---

## 9. Revision History

| Version | Date | Author | Summary |
| :--- | :--- | :--- | :--- |
| 1.0 | 2026-03-xx | G. Thind | Initial consolidated GDD/TDD |
| 2.0 | 2026-04-20 | G. Thind | Added Land Ownership Economy (§ 4.4), Siege Resolution flow (§ 4.5), Party Attribute Stats (§ 3.3, Epic 6), Frontend–Backend collaboration model (§ 6.4); reformatted to corporate standard |
| 2.1 | 2026-04-20 | G. Thind | Epic 5 shipped: virtual Mana Crystals currency confirmed for Phase 1; Vault Lock + Siege Resolve endpoints live; XP-on-claim and siege-win bonus wired; Pot/War-Tax payout formalized |
| 2.2 | 2026-04-20 | G. Thind | Siege-loss split reworked to 50/30/20 (defender/system/retry-discount); `SiegeDiscount` model + auto-apply on re-attack; device-authoritative timestamps (§ 6.5); Epic 6 shipped — Party Attribute Stats (STR/AGI/END/CON) + `GET /users/{id}/party-role` |
| 2.3 | 2026-04-20 | G. Thind | Epic 1 (Bounty Board) shipped — `Merchant`/`Bounty`/`BountyCompletion` models; merchant registration; bounty seeding; geofenced nearby discovery; proximity + score-gate completion with coupon issuance |
| 2.4 | 2026-04-28 | G. Thind | Epic 2 (ML Referee) shipped — `ml_referee.py` heuristic verification (accelerometer cadence + rhythm, MediaPipe pose ROM, score plausibility); `POST /api/v1/activities/verify` preview endpoint; optional `proof` field auto-overrides client-trusted scores on `/domains`, `/sieges/{id}/resolve`, `/bounties/{id}/complete` |
| 2.5 | 2026-04-30 | G. Thind | Hardening sprint — `PlatformRevenue` ledger persists War Tax + Loss-Keep cuts (audit endpoint `GET /api/v1/platform/revenue`); `@app.on_event` migrated to `lifespan`; first runnable test suite (`tests/test_ml_referee.py`, 10/10 pass); OpenAPI export script writes `Documentation/openapi.json` for Antigravity consumption |
| 2.6 | 2026-04-30 | G. Thind | `ActivityLog` table + `record_activity` helper unblock 30-day rolling Party Stats via `GET /api/v1/users/{id}/party-role?window_days=N`; `ProofConsumed` table + replay-attack guard 409s any re-submission of the same workout proof across `/domains`, `/sieges/{id}/resolve`, `/bounties/{id}/complete` |
| 2.7 | 2026-05-04 | G. Thind | Three-portal auth (§ 6.6) — `Admin` model, `POST /api/v1/auth/login` returns `{role, id, email, name}` after probing Admin → Merchant → Player. Public admin registration intentionally absent; admins seeded via `scripts/seed_admin.py`. |
| 2.8 | 2026-05-04 | G. Thind | Merchant payment lifecycle + JWT — three payment statuses (pending/successful/declined), only `payment_successful` flips `is_active`; webhook-driven activation with admin manual fallback; merchant_chest bounties 403 if merchant inactive; JWT auth actively gating per-endpoint via `get_current_admin/merchant/player` dependencies. |
