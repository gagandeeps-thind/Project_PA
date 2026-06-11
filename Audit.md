# Osiris — Architecture & Readiness Audit

| Field | Value |
| :--- | :--- |
| **Document Type** | Gap-tracking checklist (audit against current code) |
| **Version** | 1.0 |
| **Last Updated** | 2026-05-18 |
| **Reflects code state** | Task.md v2.11 (v2.10 + v2.11 shipped; v2.12 active) |
| **Owner** | Gagandeep Thind |
| **Companion docs** | [Task.md](Task.md), [Documentation/Imp_and_US.md](Documentation/Imp_and_US.md) |

> **How to use this doc:** Tick items as they're resolved. When a section is fully ticked, strike it and move to v1.x with the date. Every item links to the line of code that motivated it — re-verify the issue still exists before fixing, since the codebase moves faster than this doc.

> **Scope:** Audit covers macro-architecture, real-world edge cases, and operational friction — **above and beyond** the v2.12 sprint backlog already captured in [Task.md § 3](Task.md). Items already in that backlog are referenced but not re-listed.

---

## Status Legend

| Symbol | Meaning |
| :--- | :--- |
| ⛔ | Critical — block pilot launch until fixed |
| 🔥 | High — fix before v2.12 ships (real payments depend on it) |
| ⚠️ | Medium — schedule before Phase 2 (Postgres migration unblocks several) |
| 📎 | Hygiene — low risk individually, painful in aggregate |

---

## 1. Macro-architecture

### Persistence & scale
- [ ] ⚠️ **No migration framework.** Schema changes today require deleting `fitness_mvp.db`. One ad-hoc [`scripts/migrate_v2_9.py`](Osiris_backend/scripts/migrate_v2_9.py) exists; every future model change accumulates the same liability. → *Adopt Alembic before next schema-touching change.*
- [ ] ⚠️ **Single SQLite file is system-of-record.** [database.py:11-16](Osiris_backend/database.py#L11-L16). No pooling, no replication, no backup. Pilot data loss is one bad migration away. → *Phase 2 Postgres migration; until then, scheduled snapshot of the .db file.*
- [ ] ⚠️ **APScheduler runs in-process.** [main.py:37-52](Osiris_backend/main.py#L37-L52). Any horizontal scale-out double-fires `process_daily_decay` and `process_telemetry_ttl`. → *Externalize cron to a single dedicated worker, or use a distributed lock.*
- [ ] ⚠️ **Decay job is uptime-relative, not wall-clock.** [main.py:45](Osiris_backend/main.py#L45) uses `'interval', hours=24`. A server restart shifts decay forever; a 25-hour outage skips a day. → *Switch to a cron trigger pinned to a fixed UTC hour.*
- [ ] ⚠️ **`db.query(...).all()` on hot paths.** [main.py:920](Osiris_backend/main.py#L920) (`/domains/nearby`), [main.py:1818-1823](Osiris_backend/main.py#L1818-L1823) (`/bounties/nearby`), [main.py:1967](Osiris_backend/main.py#L1967) (decay job). Fine at 50 testers; OOM at 50k. → *Replace with PostGIS `ST_DWithin` for spatial; batch the decay loop.*

### Code organization
- [ ] 📎 **`main.py` is 2,021 lines** mixing Pydantic schemas, endpoints, business logic, cron, economy constants. Importing for any helper triggers `models.Base.metadata.create_all(...)` at module load ([main.py:33](Osiris_backend/main.py#L33)). → *Split into `routers/`, `schemas/`, `services/`, `jobs/`.*
- [ ] 📎 **Two copies of `export_openapi.py`** — [Osiris_backend/export_openapi.py](Osiris_backend/export_openapi.py) and [Osiris_backend/scripts/export_openapi.py](Osiris_backend/scripts/export_openapi.py). → *Delete the duplicate.*

### Security boundaries
- [ ] 🔥 **CORS = wildcard + credentials.** [main.py:57-63](Osiris_backend/main.py#L57-L63). `allow_origins=["*"]` with `allow_credentials=True` is spec-violating and audit-failing. → *Pin to explicit dev + prod origins.*
- [ ] 🔥 **`/domains/nearby` is unauthenticated and leaks `owner_id` + polygons.** [main.py:909-952](Osiris_backend/main.py#L909-L952). Combined with email harvest elsewhere, this is a stalker vector — anyone can map a player's regular workout zone. → *Require player JWT; consider returning anonymized owner handle instead of `owner_id`.*
- [ ] 🔥 **No cross-table email uniqueness for the three auth tables.** [main.py:836-882](Osiris_backend/main.py#L836-L882). A duplicate email in {Admin, Merchant, User} silently makes the lower-priority account unreachable. → *Add a global `email_index` table or DB constraint.*
- [ ] ⚠️ **No GDPR posture.** No account-delete endpoint, no telemetry export, no consent record. Bedford pilot in the UK = UK GDPR applies day one. → *Build `DELETE /api/v1/users/{id}` with cascade + export endpoint.*

### Contract management
- [ ] ⚠️ **No OpenAPI sync check.** `Documentation/openapi.json` is committed but no CI regenerates or diffs it. Antigravity client drifts silently. → *Pre-commit / CI step that runs `python scripts/export_openapi.py` and fails if the file changed.*

---

## 2. Real-world edge cases

### Authentication & secrets
- [ ] ⛔ **Password field capped at 12 characters.** [main.py:195](Osiris_backend/main.py#L195), [main.py:204](Osiris_backend/main.py#L204), [main.py:215](Osiris_backend/main.py#L215), [main.py:415](Osiris_backend/main.py#L415). Docstring says 72 (bcrypt's real limit) — almost certainly a typo. Every user so far has a ≤12-char password. → *Change `max_length=12` to `max_length=72`. Audit existing accounts.*
- [ ] ⛔ **`auth_login` leaks tracebacks on 500.** [main.py:883-886](Osiris_backend/main.py#L883-L886). Returns `f"Server Error: {str(e)}\n{traceback.format_exc()}"` to the client. → *Log it server-side, return a generic 500.*
- [ ] ⚠️ **JWT has no revocation / rotation / jti.** Client-side `logout()` only deletes locally ([providers.dart:114-120](Osiris_frontend/lib/providers.dart#L114-L120)). A leaked token is good for 7 days. → *Add a token-version column on User/Admin/Merchant and check on each request, or add a Redis blacklist.*
- [ ] 📎 **`auth_login` runs up to 3 bcrypt compares per attempt** (~750 ms total). [main.py:836-882](Osiris_backend/main.py#L836-L882). Compounded with no rate limiting, this is a CPU-burn target. → *Probe a single `email_role` lookup table first; only run bcrypt for the matched role.*

### Payments
- [ ] 🔥 **Webhook is forge-able in dev.** [main.py:131-146](Osiris_backend/main.py#L131-L146). With `OSIRIS_WEBHOOK_SECRET` unset, anyone can POST `/api/v1/payments/webhook` with `payment_status=payment_successful` and activate any merchant. The merchant portal even has a [UI button](Osiris_merchant_web/src/App.tsx#L113-L132) that does exactly this — works for anyone, not just merchants. → *Make `OSIRIS_WEBHOOK_SECRET` fail-fast when `OSIRIS_ENV=production` (mirror the JWT pattern at [main.py:69-84](Osiris_backend/main.py#L69-L84)). Gate the simulate button behind a non-prod check.*
- [ ] 🔥 **No `event_id` dedup table.** [main.py:1638-1649](Osiris_backend/main.py#L1638-L1649). Stripe retries failed webhooks; the `already_active` check protects only the activate path, not a deactivate → reactivate sequence. → *Build `PaymentWebhookEvent` table (already in v2.12 backlog — confirm before shipping Stripe).*

### Spatial / anti-cheat
- [ ] 🔥 **ML Referee doesn't cross-check GPS-vs-polygon.** Proof's `gps` channel is persisted ([main.py:733-748](Osiris_backend/main.py#L733-L748)) but never compared against domain coordinates or bounty geofence. A user can do push-ups anywhere and attach the proof to a Bedford domain. → *Add a co-location check in `_enforce_proof`.*
- [ ] ⚠️ **`is_polygon_swallowed` is vertex-only.** [spatial_utils.py:76-85](Osiris_backend/spatial_utils.py#L76-L85). A defender whose vertices sit inside the challenger but whose edges bulge outside is "swallowed"; a defender that's geometrically engulfed but whose vertices straddle the boundary is not. → *Phase 2 PostGIS `ST_Within` is the real fix. Until then, also test edge midpoints.*
- [ ] ⚠️ **Time-trial sieges are unwinnable on free-tier domains.** [main.py:1175-1178](Osiris_backend/main.py#L1175-L1178). When `defender_score=0`, `challenger_score <= 0 AND > 0` is always false. Any free-tier run/walk/sprint domain is unbeatable. → *Either pick a sentinel "infinity" defender baseline for free tier, or block sieges on free-tier time-trial domains.*
- [ ] ⚠️ **Velocity-lock is a flat 25 km/h with no smoothing.** [main.py:987](Osiris_backend/main.py#L987), [spatial_utils.py:42-51](Osiris_backend/spatial_utils.py#L42-L51). A single GPS jitter spike between valid fixes hits 80 km/h apparent. Cyclists trigger it trivially. → *Outlier-reject single points; use rolling-window speed.*
- [ ] ⚠️ **No device attestation.** Entire chain trusts the client. A jailbroken phone + Postman = working cheat console. → *Integrate Play Integrity API + Apple DeviceCheck before pilot launch.*
- [ ] ⚠️ **No anti-multi-account.** Same person can register two emails, claim adjacent polygons, siege themselves for the 20% retry-discount loop. → *Device fingerprint + IP rate limit on `/onboard`; later, manual review queue.*

### Economy
- [ ] 🔥 **Coupons mint but never redeem.** [main.py:1925-1927](Osiris_backend/main.py#L1925-L1927). `secrets.token_urlsafe(8).upper()` is issued; no `BountyCompletion.coupon_redeemed_at`, no `/coupons/{code}/redeem` endpoint. Merchants have no API path to validate a coupon at the till. → *Add column + endpoint + merchant-portal UI.*
- [ ] ⚠️ **No player-side crystal ledger.** `User.mana_crystals` is mutable; `PlatformRevenue` is append-only but covers only the platform side. Player disputes ("I had 500, now I have 0") are unauditable. → *Add `CrystalLedger` append-only table mirroring `PlatformRevenue`.*

### Concurrency (Postgres-blocking)
- [ ] ⚠️ **Single-claim race on bounties.** [main.py:1864](Osiris_backend/main.py#L1864) checks `completions_count >= max_completions` then [main.py:1938](Osiris_backend/main.py#L1938) increments — safe under SQLite's serial lock, classic race on Postgres. → *Use `SELECT ... FOR UPDATE` or atomic UPDATE WHERE.*
- [ ] ⚠️ **Vault top-up race.** [main.py:1086-1094](Osiris_backend/main.py#L1086-L1094). Read-modify-write on `domain.vault_balance` and `user.mana_crystals`. → *Same fix.*
- [ ] ⚠️ **Siege resolve doesn't lock target_domain.** [main.py:1118-1132](Osiris_backend/main.py#L1118-L1132). Concurrent claim + resolve on the same domain can corrupt state on Postgres. → *Row-lock on read.*

### Data hygiene
- [ ] ⚠️ **Telemetry write is synchronous and large.** [main.py:701-755](Osiris_backend/main.py#L701-L755). Up to 5 × 20,000 samples × ~80 bytes JSON ≈ 8 MB serialized inside the action transaction. Slow uplinks will trip Dio's 10s timeout ([api_client.dart:11-12](Osiris_frontend/lib/api/api_client.dart#L11-L12)) before the server commits. → *Queue raw samples to object storage / background task; keep only the session metadata inline.*

---

## 3. Operational friction

### Repo hygiene
- [ ] 📎 **`fitness_mvp.db` is committed and modified in this branch.** Binary file in VCS = unmergeable conflicts the moment a second contributor edits it. → *Add to `.gitignore`, `git rm --cached`.*
- [ ] 📎 **`Osiris_backend/__pycache__/*.pyc` tracked in git.** Same fix.
- [ ] 📎 **`test_v2_10_flows.py` is untracked.** The "regression suite" cited in Task.md v2.11 is invisible to anyone cloning fresh. → *`git add` it.*

### Dev experience
- [ ] 📎 **No `requirements.txt` / `pyproject.toml`.** Install steps are inline prose in Task.md § 8. → *Pin deps with one of the two.*
- [ ] 📎 **No `.env.example`.** `OSIRIS_JWT_SECRET`, `OSIRIS_ENV`, `OSIRIS_WEBHOOK_SECRET`, `OSIRIS_TELEMETRY_TTL_DAYS`, and the future `OSIRIS_STRIPE_SECRET_KEY` are only discoverable by grepping `main.py`. → *Document in a checked-in template.*
- [ ] 📎 **No Dockerfile, no CI.** Tests in `Osiris_backend/tests/` exist but nothing runs them on push. → *GitHub Actions: `python tests/test_*.py` on PR.*

### Observability (covered by v2.12 backlog — listed for tracking)
- [ ] 🔥 **No `/healthz`.** See [Task.md § 3](Task.md) v2.12 sprint.
- [ ] 🔥 **No structured logging.** See v2.12 sprint. Today only `print(...)` calls in jobs ([main.py:81-84](Osiris_backend/main.py#L81-L84), [main.py:2015](Osiris_backend/main.py#L2015)).
- [ ] 🔥 **No rate limiting.** See v2.12 sprint. Auth, payment intent, bounty complete, domain claim, ML verify — all unthrottled.

### Frontend (Flutter)
- [ ] 🔥 **Base URL hardcoded to Android-emulator address.** [api_client.dart:7](Osiris_frontend/lib/api/api_client.dart#L7) — `http://10.0.2.2:8000`. Breaks iOS Simulator, physical device, and prod. → *`--dart-define=API_BASE_URL=...` plumbing.*
- [ ] ⚠️ **No 401 interceptor.** [providers.dart:43-49](Osiris_frontend/lib/providers.dart#L43-L49) handles only startup-time auth failure. Mid-session 401s bubble raw into the UI. → *Add Dio interceptor that kicks to login on 401.*

### Frontend (Merchant Web)
- [ ] ⚠️ **JWT in `localStorage`.** [api.ts:14-15](Osiris_merchant_web/src/api.ts#L14-L15). XSS-stealable. → *Move to httpOnly cookie or in-memory + refresh-token pattern.*
- [ ] ⚠️ **No axios timeout.** [api.ts:5-10](Osiris_merchant_web/src/api.ts#L5-L10). A backend stall freezes the UI silently. → *`timeout: 15000`.*
- [ ] ⛔ **"Simulate webhook" button calls the real webhook endpoint.** [App.tsx:113-132](Osiris_merchant_web/src/App.tsx#L113-L132). In production this lets any merchant self-activate. → *Gate behind `import.meta.env.DEV` (and fix the webhook-secret bypass — see Payments § above).*

### Operations
- [ ] ⚠️ **No backup of `fitness_mvp.db`.** Single file on the box. A bad migration loses every pilot tester's progress.
- [ ] 📎 **No incident runbook.** "Webhook arrived for unknown merchant", "decay job didn't fire", "DB file got 2 GB" — no documented response.

---

## 4. Pre-pilot critical-path (the ⛔ + 🔥 shortlist)

Pull-out view for grep'ing during a v2.12 sprint planning:

1. ⛔ [Password `max_length=12` typo](Osiris_backend/main.py#L195)
2. ⛔ [Auth traceback leak](Osiris_backend/main.py#L883-L886)
3. ⛔ [Merchant-web simulate-webhook button is public](Osiris_merchant_web/src/App.tsx#L113-L132)
4. 🔥 [Webhook signature bypass in non-prod is the default](Osiris_backend/main.py#L131-L146)
5. 🔥 [`PaymentWebhookEvent` dedup table](Osiris_backend/main.py#L1638-L1649) (in v2.12 backlog)
6. 🔥 [CORS wildcard + credentials](Osiris_backend/main.py#L57-L63)
7. 🔥 [`/domains/nearby` unauthenticated + leaks owner_id](Osiris_backend/main.py#L909-L952)
8. 🔥 [Cross-table email uniqueness](Osiris_backend/main.py#L836-L882)
9. 🔥 [ML Referee co-location check (GPS vs polygon)](Osiris_backend/main.py#L733-L748)
10. 🔥 [Coupon redemption endpoint](Osiris_backend/main.py#L1925-L1927)
11. 🔥 Flutter [hardcoded base URL](Osiris_frontend/lib/api/api_client.dart#L7)
12. 🔥 [Structured logging / rate limiting / `/healthz`](Task.md) (v2.12 backlog)

---

## 5. Revision History

| Version | Date | Author | Summary |
| :--- | :--- | :--- | :--- |
| 1.0 | 2026-05-18 | G. Thind + AI audit | Initial audit at Task.md v2.11 — macro-architecture, real-world edge cases, operational friction. |
