# Osiris — User Stories

| Field | Value |
| :--- | :--- |
| **Document Type** | User Story Catalog |
| **Version** | 1.2 |
| **Last Updated** | 2026-05-04 |
| **Owner** | Gagandeep Thind |
| **Companion Docs** | `Imp_and_US.md` (GDD/TDD), `Task.md` (execution tracker) |

---

## How to Read This Doc

- **Status Legend:** ✅ shipped · 🚧 in progress · 📋 planned · ⏳ backlog
- Stories are grouped by Epic, then by actor.
- Backend stories generally start with *"As the system, I will…"* (server-side guarantee). Frontend stories start with *"As a [player/merchant/admin], I want to…"* (UI flow).
- Each backend story cross-references the endpoint or module that satisfies it.
- Each frontend story cross-references the backend endpoint(s) it consumes.
- Frontend status reflects the latest known state from `Task.md` `# Frontend` section. Gagan curates that — backend cannot verify Antigravity progress directly.

---

# Backend (`Osiris_backend/`)

## Epic 0 — Core User Lifecycle (Foundational)

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As the system, I will register a new player from height/weight/preferred-path input, assign an Avatar Class (Tank/Assassin/Mage), and grant 100 starter Mana Crystals. | `POST /api/v1/onboard` |
| ✅ | As the system, I will hash player passwords with bcrypt before storage and never persist plain text. | `get_password_hash()` |
| ✅ | As the system, I will authenticate a player by email + password and refresh their `last_activity_date` from the device clock. | `POST /api/v1/login` |
| ✅ | As the system, I will return a player's full profile (XP, Rank, Title, stats, crystals) on demand. | `GET /api/v1/users/{user_id}` |
| ✅ | As the system, I will downgrade any player to "F - The Dishonored" after 30 consecutive days of inactivity. | `get_rank()` |
| ✅ | As the system, I will deduct 5% of XP and reset the streak for any player inactive over 24 hours. | `process_daily_decay()` (APScheduler hourly) |
| ✅ | As the system, I will run the decay job via FastAPI's `lifespan` context manager (no deprecated `@app.on_event`). | v2.6 lifespan migration |

---

## Epic 1 — Bounty Board (B2C + B2B Foot Traffic)

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As an admin or merchant, I want to seed a bounty at specific GPS coordinates with reward + completion-cap settings. | `POST /api/v1/bounties` |
| ✅ | As the system, I will return active, non-expired, non-full bounties within a given radius (sorted nearest-first). | `GET /api/v1/bounties/nearby` |
| ✅ | As the system, I will enforce one-claim-per-user on every bounty completion. | `BountyCompletion` lookup before award |
| ✅ | As the system, I will validate the user's GPS proximity to the bounty's geofence at completion time. | Haversine check vs. `radius_m` |
| ✅ | As the system, I will enforce the score gate (`target_score > 0` requires a passing score). | Score check in `complete_bounty` |
| ✅ | As the system, I will issue a single-use cryptographically random coupon code on merchant_chest completion. | `secrets.token_urlsafe(8).upper()` |
| ✅ | As the system, I will award XP and Mana Crystals on bounty completion and recompute Rank. | `record_activity()` + rank recompute |
| ✅ | As a B2B partner, I want to register a merchant account so I can sponsor merchant_chest bounties. | `POST /api/v1/merchants/register` |

---

## Epic 2 — ML Referee (Anti-Cheat Verification)

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As the system, I will validate accelerometer cadence and rhythm against per-activity profiles (push-ups, squats, sprint, run, walk, burpees, plank, hold). | `ml_referee.check_accelerometer_pattern()` |
| ✅ | As the system, I will validate MediaPipe pose summaries (range-of-motion ≥ 60°, depth ≤ 100°) for camera-verified exercises. | `ml_referee.check_pose_summary()` |
| ✅ | As the system, I will sanity-cap declared scores against the activity's max human rate per second. | `ml_referee.check_score_plausibility()` |
| ✅ | As the system, I will reject any proof aggregating below 0.85 confidence. | `CONFIDENCE_THRESHOLD = 0.85` |
| ✅ | As a client, I want a stateless preview endpoint to confirm a workout will pass before submitting the real action. | `POST /api/v1/activities/verify` |
| ✅ | As an action endpoint (`/domains`, `/sieges/{id}/resolve`, `/bounties/{id}/complete`), I will accept an optional ActivityProof and use the verified score in place of the client-trusted score. | `_enforce_proof()` helper |
| ✅ | As the system, I will reject any proof whose `activity_type` doesn't match the expected one (e.g., pushups proof on a squats challenge). | Type check in `_enforce_proof()` |
| ✅ | As the system, I will prevent the same workout proof from being consumed by more than one action endpoint (replay-attack defence). | `ProofConsumed` table + 409 on duplicate hash |

---

## Epic 4 — Domain Expansion (Territorial Claim)

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As the system, I will reject any submitted polygon that doesn't close within 20m of its start point. | Closure tolerance check |
| ✅ | As the system, I will reject any submission where average speed exceeded 25 km/h between samples (anti-vehicle-spoofing). | `check_velocity_violation()` |
| ✅ | As the system, I will calculate polygon area in km² via the Shoelace formula. | `calculate_polygon_area_sqkm()` |
| ✅ | As the system, I will reject domains smaller than 0.001 km² as anti-spam. | Area floor in `submit_domain` |
| ✅ | As the system, I will detect a siege when a new polygon completely encapsulates an existing domain (ray-casting Point-in-Polygon). | `is_polygon_swallowed()` |
| ✅ | As the system, I will award area-proportional claim XP (`floor(area_sqkm × 100)`) and recompute Rank. | `calculate_claim_xp()` |
| ✅ | As the system, I will aggregate cumulative area per user and update their Map Title (Warden / Lord / High Lord / Sovereign). | `get_title()` |
| ✅ | As the system, I will increment the matching Party Stat (STR/AGI/END/CON) from the polygon's `defense_type` and `defense_score`. | `record_activity()` |

---

## Epic 5 — Land Ownership & Siege Resolution

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As an owner, I want to lock Mana Crystals into my domain's Vault to protect it. | `POST /api/v1/domains/{id}/vault` |
| ✅ | As an owner, I want to top up my Vault to increase the moat against future challengers. | Top-up only path in `lock_vault` |
| ✅ | As a challenger, I want to resolve a pending siege by submitting a Defense Feat score. | `POST /api/v1/sieges/{id}/resolve` |
| ✅ | As the system, I will snapshot the defender's Defense Feat score at siege creation to prevent post-hoc edits. | `defender_score_snapshot` on `SiegeLog` |
| ✅ | As the system, I will distribute the siege-win pot 80% to the winner / 20% as War Tax to the platform. | `WAR_TAX_PCT = 0.20` |
| ✅ | As the system, I will distribute the siege-loss forfeit 50% to the defender / 30% to the platform / 20% as a retry-discount credit. | `LOSS_*_PCT` constants |
| ✅ | As the system, I will auto-apply any unconsumed retry-discount when the same challenger attacks the same target_domain again. | `SiegeDiscount` lookup in `resolve_siege` |
| ✅ | As a winner, I will receive a +500 XP bonus and Rank recompute. | `SIEGE_WIN_XP_BONUS = 500` |
| ✅ | As the system, I will erase the defender's polygon and decrement their cumulative area on a successful siege. | `db.delete(target_domain)` |
| ✅ | As the system, I will deny resolution of an already-resolved siege (status != "pending_feat"). | Status check in `resolve_siege` |

---

## Epic 6 — Party Attribute Stats (Adventure Party Roles)

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As the system, I will increment STR/AGI/END/CON on every verified activity, mapping `defense_type` → stat column. | `DEFENSE_TYPE_TO_STAT` + `increment_stat_from_activity()` |
| ✅ | As a player, I want my Party Role (Vanguard/Striker/Scout/Strategist) auto-assigned from my leading attribute. | `GET /api/v1/users/{user_id}/party-role` |
| ✅ | As a player, I want to optionally view my role from a rolling N-day window instead of lifetime totals. | `?window_days=N` opt-in via `ActivityLog` aggregation |
| ✅ | As the system, I will record one ActivityLog row per verified workout with confidence + source for downstream analytics. | `models.ActivityLog` |

---

## Cross-Cutting — Platform Audit & Hardening

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As the platform, I will record every War Tax cut and Loss-Keep cut in an append-only ledger. | `models.PlatformRevenue` + writes in `resolve_siege` |
| ✅ | As an admin, I want to audit total platform earnings with a breakdown by source. | `GET /api/v1/platform/revenue` (admin-gated since v2.10) |
| ✅ | As a developer, I want runnable unit tests for the ML Referee verifier. | `tests/test_ml_referee.py` (10/10 pass) |
| ✅ | As the frontend team, I want a checked-in OpenAPI spec to regenerate the Dart client offline. | `scripts/export_openapi.py` → `Documentation/openapi.json` |
| ✅ | As the system, I will accept device-authoritative timestamps on all user-initiated endpoints. | `device_timestamp` field + `_to_naive_utc()` |
| ✅ | As the system, I will load the JWT secret from `OSIRIS_JWT_SECRET` env var, fail-fast in production if unset, generate an ephemeral 48-byte secret in dev. | v2.10 boot-time logic |
| ✅ | As the system, I will verify HMAC-SHA256 `X-Provider-Signature` on `/payments/webhook` when `OSIRIS_WEBHOOK_SECRET` is set; bypass when unset (dev). | `verify_webhook_signature` dependency |
| ✅ | As the system, I will gate `/platform/revenue` to admin only; player profile reads to player-self or admin; `/bounties` POST per-type (daily admin-only, merchant_chest matches own merchant_id). | v2.10 RBAC tightening |

---

## Three-Portal Auth Architecture (v2.8)

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As the system, I will probe Admin → Merchant → Player on login and return the matching `role` for UI routing. | `POST /api/v1/auth/login` |
| ✅ | As Gagan (sole admin), I want admin accounts seeded out-of-band only — no public registration endpoint. | `scripts/seed_admin.py` |
| ✅ | As the system, I will return a generic 401 on bad credentials so callers cannot enumerate which table contains a given email. | `Invalid email or password` regardless of cause |
| ✅ | As the system, I will issue a 7-day HS256 JWT on successful login, encoding `sub` (user id) and `role`. | `create_access_token()` |
| ✅ | As an authenticated caller, I want role-specific dependencies (`get_current_admin/merchant/player`) to gate endpoints by JWT role. | Dependencies in `main.py` |
| ✅ | As the merchant portal (web, future), I want CORS configured so the browser can call backend APIs cross-origin. | `CORSMiddleware` (currently `allow_origins=["*"]` — tighten before prod) |

---

## Map Render & Domain Discovery (v2.10)

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As the system, I will return public game-state domains within a radius (owner_id, polygon, area, vault_balance, is_protected, distance_km), sorted nearest-first. | `GET /api/v1/domains/nearby` |
| ✅ | As the Flutter app, I want a no-auth read endpoint for the world-map render so I don't need a logged-in player to show the territory layer. | Public access on `/domains/nearby` |
| ✅ | As a player, I want centroid + polygon vertex data so I can render both filled territories and their geographic centers. | `centroid_lat` / `centroid_lng` / `geometry` fields on `DomainSummary` |

---

## Telemetry Capture & ML Training Pipeline (v2.10)

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As the system, I will accept the full sensor suite (accelerometer, gyroscope, magnetometer, GPS, barometer, pose) on every `ActivityProof`. | Extended `ActivityProof` Pydantic model |
| ✅ | As the system, I will persist one `TelemetrySession` row per submitted workout with metadata (activity_type, sample counts, confidence, link to `ActivityLog`). | `_persist_telemetry()` in `record_activity()` |
| ✅ | As the system, I will persist raw sensor samples in `TelemetryData` rows keyed by `(session_id, sensor_type)` so ML training can selectively load channels. | `TelemetryData` writes |
| ✅ | As an ML researcher, I want session metadata (`sample_count_*`, `verified`, `confidence`) discoverable without loading raw samples. | Aggregate columns on `TelemetrySession` |
| ✅ | As the system, I will expire telemetry rows older than `OSIRIS_TELEMETRY_TTL_DAYS` (default 90) to manage storage. Metadata kept; raw samples deleted. | `process_telemetry_ttl()` nightly job |
| ✅ | As the system, I will reject ActivityProof payloads with > 20000 samples per channel as a DoS guard. | Pydantic `max_length=MAX_SAMPLES_PER_CHANNEL` validators |
| ⏳ | As the system, I will replace the heuristic `check_accelerometer_pattern` with a Scikit-learn anomaly detector trained on collected telemetry. | Post-pilot v3.0+ |

---

## Merchant Analytics (v2.10)

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As a merchant, I want to list all my bounties with completion counts and coupons-issued counts so the merchant portal can render an analytics view. | `GET /api/v1/merchants/{id}/bounties` |
| ✅ | As an admin, I want to see any merchant's bounty analytics for support / refund decisions. | Same endpoint, admin path |

---

## Merchant Payment Lifecycle (v2.9)

| Status | Story | Implementation |
| :---: | :--- | :--- |
| ✅ | As a newly-registered merchant, I default to inactive (`is_active=False`, `payment_status='payment_pending'`) until the pilot fee is paid. | `Merchant` defaults |
| ✅ | As a merchant, I want to fetch my own profile post-login to discover my activation + payment status. | `GET /api/v1/merchants/{id}` (merchant same-id or admin) |
| ✅ | As a merchant, I want to initiate a pilot-fee payment that returns a provider intent ID. | `POST /api/v1/merchants/{id}/payments/intent` |
| ✅ | As the payment provider, I will POST a webhook with one of three terminal statuses: `payment_successful` / `payment_pending` / `payment_declined`. | `POST /api/v1/payments/webhook` |
| ✅ | As the system, I will activate a merchant (`is_active=True`) ONLY on `payment_successful`; pending and declined leave them inactive. | Status branch in `payment_webhook` |
| ✅ | As the system, I will write a `merchant_pilot_fee` PlatformRevenue row on activation (idempotent — no double-credit). | Activation guard in `payment_webhook` |
| ✅ | As the system, I will block `merchant_chest` bounty creation for any merchant whose `is_active=False`, returning 403 with the current `payment_status`. | Gate in `create_bounty` |
| ✅ | As an admin, I want to list and filter merchants by activation status (`pending`/`active`/`declined`/`all`). | `GET /api/v1/admin/merchants` |
| ✅ | As an admin, I want to manually activate a merchant (out-of-band payment, demo seeding). | `POST /api/v1/admin/merchants/{id}/activate` |
| ✅ | As an admin, I want to manually deactivate a merchant (refund, policy violation). | `POST /api/v1/admin/merchants/{id}/deactivate` |

---

# Frontend (Flutter, Google Antigravity)

> Backend support is shipped for every story below — the API contract is in `Documentation/openapi.json`. **Status reflects the Flutter implementation in Antigravity.** Gagan curates this section; backend has no direct visibility into Antigravity progress.

## Onboarding & Authentication

| Status | Story | Backend Endpoint(s) |
| :---: | :--- | :--- |
| 📋 | As a new player, I want to go through "The Awakening" registration (height, weight, age, gender, path) and see my assigned Avatar Class. | `POST /api/v1/onboard` |
| 📋 | As a returning player, I want to log in with email + password and land on the game dashboard. | `POST /api/v1/auth/login` (or legacy `/api/v1/login`) |
| 📋 | As a merchant, I want to enter merchant credentials in the mobile app and be routed to the merchant portal UI instead of the game. | `POST /api/v1/auth/login` → `role=merchant` |
| 📋 | As Gagan (admin), I want to enter admin credentials in the mobile app and be routed to the admin portal UI. | `POST /api/v1/auth/login` → `role=admin` |
| 📋 | As any user, I want my JWT persisted in secure local storage and sent as `Authorization: Bearer …` on every API call. | All authenticated endpoints |
| 📋 | As any user, I want a clear "Invalid email or password" error on auth failure (no account-existence leakage). | 401 from `/auth/login` |

---

## Game — Map & Territory (Domain Expansion)

| Status | Story | Backend Endpoint(s) |
| :---: | :--- | :--- |
| 📋 | As a player, I want to see the world map centered on my current location with my own and other players' claimed domains overlaid. | (read endpoint TBD — currently no public list-domains route) |
| 📋 | As a player, I want to start a Domain run via a "Start Domain" button that polls GPS every ~5s and draws a breadcrumb trail. | client-side; submits to `POST /api/v1/domains` |
| 📋 | As a player, I want a "Close Domain" button that activates only when I'm within 20m of my start point. | client-side check |
| 📋 | As a player, I want to perform a Defense Feat (push-ups via on-device camera + MediaPipe) immediately after closing the polygon, then submit the trace + score + proof. | `POST /api/v1/domains` with optional `defense_proof` |
| 📋 | As a player, I want clear feedback if my domain is rejected (closure failure, velocity violation, too small, ML referee rejection). | 400 from `/api/v1/domains` |
| 📋 | As a player, I want to lock crystals into my domain's Vault via a UI control on the map. | `POST /api/v1/domains/{id}/vault` |
| 📋 | As a player, I want to see my Mana Crystal balance update immediately after a Vault lock or siege payout. | refreshed from `GET /api/v1/users/{id}` |

---

## Game — Combat & Sieges

| Status | Story | Backend Endpoint(s) |
| :---: | :--- | :--- |
| 📋 | As a player, I want to be notified when my latest polygon submission triggered one or more sieges. | `sieges_triggered` field on `DomainResponse` |
| 📋 | As a challenger, I want a UI to submit my Defense Feat score for a pending siege, with proof attached. | `POST /api/v1/sieges/{id}/resolve` |
| 📋 | As a player, I want to see the siege outcome (won / failed) with crystal payouts, XP gained, and any new retry discount banked. | `SiegeResolveResponse` fields |
| 📋 | As a re-challenger, I want to see how much retry-discount is being auto-applied on this attempt. | `discount_applied` field |

---

## Game — Bounties & AR Loot

| Status | Story | Backend Endpoint(s) |
| :---: | :--- | :--- |
| 📋 | As a player, I want to see active bounties within radius_km of my current location, sorted nearest-first, with reward preview. | `GET /api/v1/bounties/nearby` |
| 📋 | As a player, I want a UI to submit completion of a bounty when I'm within its geofence (proximity-only or score-gated). | `POST /api/v1/bounties/{id}/complete` |
| 📋 | As a player, I want to open my camera and "claim" an AR Treasure Chest (visual flourish over a successful merchant_chest completion). | client-side AR; chest reveal triggered by 200 OK |
| 📋 | As a player, I want to see and copy the coupon code I receive from a merchant_chest. | `coupon_code` field in response |
| 📋 | As a player, I want clear messaging if I'm outside the geofence, the bounty is full, or I've already claimed it. | 400 errors from the endpoint |

---

## Game — Profile, Stats & Party Role

| Status | Story | Backend Endpoint(s) |
| :---: | :--- | :--- |
| 📋 | As a player, I want a Profile screen showing Rank, Title, XP, Mana Crystals, cumulative_area, and STR/AGI/END/CON. | `GET /api/v1/users/{id}` |
| 📋 | As a player, I want to see my Party Role (Vanguard/Striker/Scout/Strategist) and the leading stat that drove it. | `GET /api/v1/users/{id}/party-role` |
| 📋 | As a player, I want to toggle between lifetime totals and a rolling 30-day view of my Party Role. | `?window_days=30` |
| 📋 | As a player, I want a streak indicator and a warning if I'm approaching the 30-day decay cliff. | `streak`, `last_activity_date` from profile |

---

## Game — ML Referee Integration

| Status | Story | Backend Endpoint(s) |
| :---: | :--- | :--- |
| 📋 | As a player performing a workout in-app, I want on-device MediaPipe pose estimation to count reps live. | client-side (MediaPipe); no backend call |
| 📋 | As a player, I want a real-time preview of whether my workout proof will pass verification (before final submission). | `POST /api/v1/activities/verify` (no DB writes) |
| 📋 | As a player whose proof was rejected, I want clear human-readable feedback (which sub-check failed: cadence, ROM, plausibility). | 400 detail with verifier flags |
| 📋 | As a player, I want to be informed if I accidentally try to submit the same workout twice (idempotency 409). | 409 from action endpoints |

---

## Merchant Portal (Mobile App + Web Registration)

| Status | Story | Backend Endpoint(s) |
| :---: | :--- | :--- |
| 📋 | As a business owner, I want to register on a web page (separate from mobile app) with name, email, password, business type. | `POST /api/v1/merchants/register` |
| 📋 | As a merchant, I want to log in via the same mobile app as players and be routed to the merchant UI. | `POST /api/v1/auth/login` → `role=merchant` |
| 📋 | As a merchant, I want to see my activation status and payment status front-and-center after login. | `GET /api/v1/merchants/{id}` |
| 📋 | As an inactive merchant, I want a "Pay Pilot Fee" CTA that creates a payment intent and redirects me to a payment form. | `POST /api/v1/merchants/{id}/payments/intent` |
| 📋 | As a merchant whose payment is `payment_pending`, I want a "checking…" UI so I know the status will auto-update. | poll or push from webhook |
| 📋 | As a merchant whose payment was `payment_declined`, I want to retry with a different card. | new payment intent |
| 📋 | As an active merchant, I want to create merchant_chest bounties pinned to my storefront's GPS. | `POST /api/v1/bounties` (bounty_type=merchant_chest) |
| 📋 | As an active merchant, I want to see analytics on my bounties (claims so far, coupons issued). | future `GET /api/v1/merchants/{id}/bounties` |

---

## Admin Portal (Mobile App)

| Status | Story | Backend Endpoint(s) |
| :---: | :--- | :--- |
| 📋 | As Gagan (admin), I want to log into the admin portal via the same mobile app and see admin-only navigation. | `POST /api/v1/auth/login` → `role=admin` |
| 📋 | As an admin, I want to see total platform revenue with a breakdown by source. | `GET /api/v1/platform/revenue` |
| 📋 | As an admin, I want to list all merchants and filter by activation status. | `GET /api/v1/admin/merchants?status=…` |
| 📋 | As an admin, I want to manually activate a merchant (for refunds, demos, or out-of-band payment confirmation). | `POST /api/v1/admin/merchants/{id}/activate` |
| 📋 | As an admin, I want to manually deactivate a merchant for policy violations. | `POST /api/v1/admin/merchants/{id}/deactivate` |
| 📋 | As an admin, I want a clear "Admin Only" banner so it's never confused with the player or merchant UI. | client-side |

---

## Revision History

| Version | Date | Author | Summary |
| :--- | :--- | :--- | :--- |
| 1.0 | 2026-05-04 | G. Thind | Initial catalog covering all backend functionality through v2.9 plus the corresponding frontend stories that consume the API contract. |
| 1.1 | 2026-05-04 | G. Thind | v2.10 backend stories added: Map Render & Domain Discovery (Epic 7), Telemetry Capture & ML Training Pipeline (Epic 8), Merchant Analytics. Cross-Cutting Hardening section flipped JWT-secret + webhook-sig + wider-RBAC items from 📋 to ✅. |
| 1.2 | 2026-05-04 | G. Thind | v2.11 stories: telemetry TTL + DoS cap flipped from 📋 to ✅. (Operational sprint — no new feature stories; new infrastructure: `seed_pilot.py`, `tests/test_v2_10_flows.py`, nightly `process_telemetry_ttl()`.) |
