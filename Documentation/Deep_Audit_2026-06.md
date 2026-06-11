# Osiris — Deep Production-Readiness Audit

| Field | Value |
| :--- | :--- |
| **Document Type** | Full-stack security + readiness audit (verified against live code) |
| **Date** | 2026-06-09 |
| **Reviewer** | AI audit (full backend + 3 frontends read) |
| **Code state** | Backend post-v2.12 work; `Osiris_customer`, `Osiris_merchant` (Flutter), `Osiris_admin_web` (React) |
| **Supersedes** | `Audit.md` v1.0 (2026-05-18) — ~8 of its findings now fixed; see § 1 |

> **Method:** Every finding below was re-verified against the current code, not carried over from the prior audit. Line numbers are as of this read. Severity: ⛔ blocks any real deployment · 🔥 fix before pilot · ⚠️ fix before Phase 2 / scale · 📎 hygiene.

---

## 0. Executive Summary

The **backend is functionally complete and notably more mature than three weeks ago** — Alembic is adopted, payment webhook dedup exists, coupon redemption is wired, password/traceback bugs are fixed, GPS co-location checking was added. Credit where due (§ 1).

But **it is not production-ready**, and the gap is concentrated in five areas:

1. **Payment activation is forgeable by design in the default config** — and the merchant app ships a button that exploits it. (§ 2.1)
2. **No deployment substrate at all** — no dependency manifest, no rate limiting, no health check, no structured logs, no CI. (§ 4)
3. **The entire anti-cheat trust chain is client-side** — no device attestation, and the one location check is trivially bypassable. (§ 2.3)
4. **Privacy/GDPR posture is absent** for a UK pilot, and `/domains/nearby` is an unauthenticated location-leak. (§ 2.2, § 3.4)
5. **Concurrency correctness depends on SQLite's global lock** — several economy paths race the moment you move to Postgres. (§ 3.3)

**Honest readiness:** ~90% for a *controlled, friendly* Bedford pilot you personally supervise; **~45%** for an unsupervised public launch. The blockers are not "more features" — they're hardening, ops, and trust.

---

## 1. Fixed since Audit.md v1.0 (verified)

Don't re-do these — they're done:

| Prior finding | Status |
| :--- | :--- |
| Password `max_length=12` typo | ✅ Now `min_length=8, max_length=72` ([main.py:217](Osiris_backend/main.py#L217)) |
| `auth_login` leaks tracebacks on 500 | ✅ Now logs server-side, returns opaque 500 |
| No `PaymentWebhookEvent` dedup | ✅ Table + unique `provider_event_id` + race-catch on commit |
| ML referee never checks GPS-vs-polygon | ✅ `_enforce_proof_gps_in_polygon` added (but weak — see § 2.3) |
| Coupons mint but never redeem | ✅ `POST /coupons/{code}/redeem` + redemption columns |
| No migration framework | ✅ Alembic adopted, 3 revisions in `alembic/versions/` |
| Webhook/JWT secret prod fail-fast | ✅ Both raise at boot when `OSIRIS_ENV=production` |
| Flutter JWT in insecure storage | ✅ `Osiris_customer` uses `flutter_secure_storage` |
| No HTTP client timeouts | ✅ Dio has 15s connect/receive timeouts |

---

## 2. Critical & High — Security

### 2.1 ⛔ Payment activation is forgeable, and the merchant app exploits it

Three facts combine into one exploit:

1. The webhook signature check is **disabled whenever `OSIRIS_WEBHOOK_SECRET` is unset** ([main.py:158-159](Osiris_backend/main.py#L158-L159)). The fail-fast only fires if `OSIRIS_ENV=production` is *explicitly* set — a deploy that forgets that env var has a wide-open webhook.
2. `/api/v1/payments/webhook` takes **no JWT** (correct for real providers) — so when the secret is unset, *any unauthenticated caller* can POST `payment_status=payment_successful` for *any* `merchant_id` and activate them for free.
3. The **merchant Flutter app ships "succeeded"/"failed" buttons** that call exactly this endpoint ([merchant_dashboard_screen.dart:243-269](Osiris_merchant/lib/screens/merchant_dashboard_screen.dart#L243-L269)). It's not a hidden debug path — it's in the merchant dashboard UI.

**Impact:** every merchant self-activates without paying; anyone who reads the OpenAPI spec activates arbitrary merchants. The $50 pilot fee is unenforceable.

**Fix:**
- Make `OSIRIS_WEBHOOK_SECRET` **required unless `OSIRIS_ENV` is explicitly `dev`/`test`** (invert the default — fail closed, not open).
- Remove the simulate buttons from the merchant app, or compile them out with a Dart `--dart-define=ALLOW_SIMULATE=false` guard that defaults to off.

### 2.2 🔥 `/domains/nearby` is unauthenticated and leaks owner identity + exact territory

[main.py:940-983](Osiris_backend/main.py#L940-L983) returns `owner_id`, full polygon `geometry`, and `vault_balance` for any lat/lng, no token required. Two problems:

- **Location privacy:** a domain polygon *is* a map of where a specific person repeatedly exercises. `owner_id` + repeated polling = a stalking primitive. For a UK pilot this is a GDPR special-category risk (location → routine → identifiable individual).
- **Economic recon:** `vault_balance` tells an attacker exactly which domains are worth besieging and for how much, with zero cost or auth.

**Fix:** require a player JWT; return an opaque per-domain handle instead of the raw `owner_id`; consider coarsening geometry for non-owners (centroid + area, not vertices).

### 2.3 🔥 The GPS co-location check is trivially bypassable

[main.py:1490-1502](Osiris_backend/main.py#L1490-L1502) averages the proof's GPS samples and checks the **centroid** is inside the polygon. Two bypasses:

1. Empty GPS channel → check is skipped entirely (`if not proof.gps: return`). A cheating client just omits GPS.
2. Send **one** fake sample inside the polygon → centroid = that point → passes, while the actual workout happened anywhere.

Combined with **no device attestation** (the whole chain trusts a client that can be Postman), the anti-cheat is defense-in-depth theatre against a determined actor. It stops casual cheating, not real cheating.

**Fix (layered):** require GPS for outdoor `activity_type`s; check that *most* samples (not the centroid) are inside; cross-check GPS timestamps against `duration_seconds`; and add Play Integrity / App Attest before any real-money phase.

### 2.4 🔥 JWT has no revocation, rotation, or `jti`

Tokens are valid 7 days ([main.py:98](Osiris_backend/main.py#L98)). There is no token-version column, no blacklist, no `jti`. Consequences:

- A leaked token works for a week with no kill switch.
- A **deleted/banned user's token keeps working** until expiry — there's no server-side check that the `sub` still exists/is active on each request (`get_current_user_token` only decodes; it never reloads the row).
- Client `logout()` only deletes locally.

**Fix:** add a `token_version` int on User/Admin/Merchant, embed it in the JWT, compare on each request; bump it to revoke. Or a Redis denylist keyed on `jti`.

### 2.5 🔥 CORS: wildcard origin + credentials

[main.py:68-74](Osiris_backend/main.py#L68-L74): `allow_origins=["*"]` with `allow_credentials=True`. This is a spec violation (browsers refuse to send credentials to a `*` origin), it will fail a security review, and it signals "any site may call us with the user's session." 

**Fix:** pin an explicit allowlist (dev localhost ports + the prod web origins) and keep credentials only for those.

### 2.6 ⚠️ No cross-table email uniqueness

Each of `users`, `merchants`, `admins` has its own `unique` email, but nothing prevents the *same* email existing in two tables. `auth_login` probes Admin → Merchant → User in order ([main.py auth_login](Osiris_backend/main.py)), so a collision silently shadows the lower-priority account — that user can never log in and gets a confusing "invalid password."

**Fix:** a shared `identities(email UNIQUE, role, ref_id)` table, or a pre-insert check across all three.

### 2.7 📎 `auth_login` runs up to 3 bcrypt verifies per attempt

Worst case (player login) does an Admin miss + Merchant miss + User hit = up to 3 bcrypt comparisons (~600–900 ms). With **no rate limiting** (§ 4.3) this is a cheap CPU-exhaustion target. Probe a cheap `email→role` lookup first, then one bcrypt.

---

## 3. Correctness & Data Integrity

### 3.1 🔥 Free-tier time-trial domains are unwinnable

[main.py:1218-1223](Osiris_backend/main.py#L1218-L1223): for time-trial types (run/walk/sprint), `challenger_won = challenger_score <= defender_score AND challenger_score > 0`. A free-tier domain has `defender_score = 0`, so the condition is `score <= 0 AND score > 0` → **always false**. Any free-tier run/walk/sprint domain can never be conquered. (Pushup free-tier domains are fine — different branch.)

**Fix:** treat `defender_score == 0` on a time-trial as "no baseline set → any positive score wins," or block sieges on unscored time-trial domains.

### 3.2 ⚠️ No player-side crystal ledger

`User.mana_crystals` is a mutable integer touched by claims, vault locks, siege payouts, bounty rewards. `PlatformRevenue` audits only the *platform's* cut. A player dispute ("I had 500, now 0") is **unauditable** — there's no append-only record of player balance deltas. This becomes a real support/trust problem the moment crystals have value.

**Fix:** `CrystalLedger(user_id, delta, reason, balance_after, created_at)` written on every mutation.

### 3.3 ⚠️ Read-modify-write races (latent until Postgres)

Safe today only because SQLite serializes writes. On Postgres these corrupt:

- **Bounty single-claim:** `completions_count >= max_completions` check and the later increment aren't atomic — two concurrent claims both pass the cap.
- **Vault top-up:** read `vault_balance` + `mana_crystals`, modify, write — classic lost update.
- **Siege resolve:** target domain isn't row-locked; a concurrent claim + resolve interleave.

**Fix:** `SELECT … FOR UPDATE` on the row, or atomic `UPDATE … WHERE completions_count < max_completions`.

### 3.4 ⚠️ No GDPR mechanics for a UK pilot

No account-delete, no data-export, no consent record — and you're capturing **continuous location + full motion telemetry** of identifiable people in Bedford. UK GDPR applies from tester #1. Minimum: `DELETE /users/{id}` with cascade, a telemetry export endpoint, and a recorded consent timestamp at onboarding.

### 3.5 ⚠️ Telemetry write is synchronous and large

`_persist_telemetry` serializes up to 5 channels × 20,000 samples inside the action transaction — potentially multi-MB JSON committed before the HTTP response. On a weak uplink this races the client's 15s Dio timeout, and it holds the DB write lock the whole time. Queue raw samples to a background task / object storage; keep only session metadata inline.

---

## 4. Production Substrate (mostly *absent*, not broken)

### 4.1 ⛔ No dependency manifest

There is **no `requirements.txt` and no `pyproject.toml`**. Install steps are prose in `Task.md`. Builds are unreproducible; you cannot pin a CVE-patched FastAPI; a fresh machine can't `pip install -r` anything. This blocks any container/CI/deploy.

### 4.2 🔥 No `/healthz`, no structured logging

Your own v2.12 plan lists these; they're not in the code yet. No liveness/readiness probe for any orchestrator; logs are stdlib + bare `print()` in jobs. You'll be blind in production.

### 4.3 🔥 No rate limiting anywhere

`/auth/login`, `/payments/intent`, `/payments/webhook`, `/domains`, `/bounties/{id}/complete`, `/activities/verify` — all unthrottled. Brute-force, webhook spam, and the bcrypt CPU-burn (§ 2.7) are all open.

### 4.4 📎 No CI, no Dockerfile, no `.env.example`

Tests exist (`tests/test_*.py`, good) but nothing runs them on push. Five `OSIRIS_*` env vars are discoverable only by grepping `main.py`. No container recipe.

### 4.5 ⚠️ In-process scheduler + hot-path full-table scans

`APScheduler` runs in-process — horizontal scale double-fires decay and TTL jobs. `/domains/nearby`, `/bounties/nearby`, and the decay loop all do `db.query(...).all()` — fine at 50 testers, OOM at scale. (PostGIS `ST_DWithin` + externalized cron are the Phase-2 fixes.)

---

## 5. Frontend

### 5.1 🔥 Hardcoded base URLs (all three apps)

- `Osiris_customer`: `http://10.0.2.2:8000` ([api_client.dart:6](Osiris_customer/lib/api/api_client.dart#L6)) — Android-emulator only; breaks iOS sim, physical devices, prod.
- `Osiris_merchant`: same `10.0.2.2:8000` default.
- `Osiris_admin_web`: `http://localhost:8000` ([client.ts:13](Osiris_admin_web/src/api/client.ts#L13)).

**Fix:** `--dart-define=API_BASE_URL=…` for Flutter; `import.meta.env.VITE_API_BASE_URL` for the web app.

### 5.2 ⚠️ Admin web stores JWT in `localStorage`

[client.ts:22](Osiris_admin_web/src/api/client.ts#L22) — XSS-stealable, and this is the *admin* token (highest privilege). Prefer in-memory + refresh, or an httpOnly cookie.

### 5.3 ⚠️ Customer app has no 401 interceptor

The Dio client only sets `onRequest` ([api_client.dart:20-29](Osiris_customer/lib/api/api_client.dart#L20-L29)). A mid-session 401 (expired/revoked token) bubbles raw into the UI instead of kicking to login.

### 5.4 ⚠️ Merchant app ships the self-activation exploit (see § 2.1)

---

## 6. Code Quality / Anti-patterns

- 📎 **`main.py` is 2,312 lines** — schemas, endpoints, business logic, jobs, economy constants, security helpers all in one module. Importing any helper triggers `create_all()` at module load. Split into `routers/ schemas/ services/ jobs/`.
- 📎 **`create_all()` runs at import alongside Alembic** ([main.py:44](Osiris_backend/main.py#L44)) — two sources of schema truth. `create_all` silently masks a forgotten migration in dev, then prod (Alembic-only) diverges. Pick one; gate `create_all` behind a dev flag.
- 📎 **Duplicate `export_openapi.py`** (root + `scripts/`) per the prior audit — verify and delete one.
- 📎 **No OpenAPI drift check** — `openapi.json` is committed but nothing regenerates/diffs it in CI; the Antigravity clients drift silently.
- 📎 **Economy constants are module-level magic numbers** in `main.py` — fine now, but they belong in a config the product owner can tune without editing code.

---

## 7. Prioritized Action Plan

**Gate 1 — before ANY non-local deploy (the ⛔/🔥 shortlist):**
1. Invert webhook-secret default to fail-closed + strip merchant simulate buttons (§ 2.1)
2. `requirements.txt`/`pyproject.toml` with pinned versions (§ 4.1)
3. Authenticate `/domains/nearby` + stop leaking `owner_id` (§ 2.2)
4. Pin CORS origins (§ 2.5)
5. Rate limiting on auth + payment + proof endpoints (§ 4.3)
6. `/healthz` + structured logging (§ 4.2)
7. Per-app base-URL config (§ 5.1)
8. Fix free-tier time-trial siege (§ 3.1)

**Gate 2 — before pilot testers touch it:**
9. JWT revocation / token-version (§ 2.4)
10. GDPR delete + export + consent (§ 3.4)
11. Strengthen GPS co-location + plan device attestation (§ 2.3)
12. Cross-table email uniqueness (§ 2.6)
13. Async telemetry write (§ 3.5)

**Gate 3 — before public / real-money / scale:**
14. Postgres + PostGIS, fix the three races (§ 3.3), externalize cron (§ 4.5)
15. CrystalLedger (§ 3.2)
16. Device attestation + anti-multi-account
17. Split `main.py`; CI with OpenAPI drift check; Dockerfile

---

## 8. Revision History

| Version | Date | Author | Summary |
| :--- | :--- | :--- | :--- |
| 1.0 | 2026-06-09 | AI audit | Full re-verification against post-v2.12 code + all three frontends. ~8 prior findings confirmed fixed; new criticals on payment forgeability (with merchant-app exploit), GPS-check bypass, dependency manifest, JWT revocation, free-tier siege. |
