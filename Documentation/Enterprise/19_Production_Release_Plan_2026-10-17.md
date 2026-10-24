# Production Release Plan — 2026-10-17

**Scope:** first public release of the player app (verified running, courses, challenges, quests, communities,
camera-verified exercises), the admin console and the API. Economy stays XP/badges only; Stripe stays in test mode
(ADR-005). Pilot market: Bedford / Halifax, Nova Scotia (PIPEDA).
**Inputs:** docs 04–12, `PLAN.md`, the code as of commit `6b4759a`, and the build run recorded in §6.

Every statement below about the code was checked against the repository on this date. Items marked **[human]** touch
the danger zones in `CLAUDE.md` (CI, Dockerfile, lockfiles, migrations, deploy runbook) and need a human commit.

---

## 1. Architecture and hosting

### 1.1 What the code can run on today

| Component | Reality in the repo | Consequence for hosting |
|---|---|---|
| API | FastAPI monolith (`main.py` ~4.2k lines + routers), Python 3.13, non-root image, `/healthz`, `/metrics` | Any container platform |
| Database | `database.py` hard-codes `sqlite:///fitness_mvp.db`. `OSIRIS_DATABASE_URL` is read only by `alembic/env.py`, so the **app cannot connect to PostgreSQL** even though ADR-002 requires it from SIT. No PostgreSQL driver in `requirements.txt`. | Blocker: fix before SIT (§5.1 item 1) |
| Background jobs | APScheduler **inside the web process**: XP decay (24 h), telemetry TTL (24 h), route-point TTL (24 h), challenge settlement (1 h) | Every extra API instance runs every job again. Decay applied twice = 9.75 % XP loss instead of 5 %. Keep **one instance** or externalise the jobs (§5.1 item 3) |
| Rate limiting | In-memory, per process, keyed on `request.client.host`. uvicorn is started **without `--proxy-headers`** | Behind any load balancer every player shares the balancer's IP: 10 logins/min **for the whole user base**. Blocker (§5.1 item 2) |
| Migrations | `alembic upgrade head` runs in the container `CMD` on every boot; 12 migrations, 9 use `batch_alter_table` (works on PostgreSQL, never exercised there) | Concurrent boots race on the schema. Run migrations as a separate job before traffic shift |
| Admin console | Static Vite build, token in `localStorage`, `VITE_API_BASE_URL` | Any static host; must sit behind an identity-aware proxy (§2.3) |
| Player app | Flutter, `API_BASE_URL` dart-define (default `http://10.0.2.2:8000`), `applicationId com.example.osiris_customer`, release build **signed with the debug key**, iOS bundle `com.example.osirisCustomer` | Not store-submittable as is (§2.5) |

### 1.2 Decision: managed containers on Google Cloud, Canadian region

| Layer | Choice | Why this and not the alternatives |
|---|---|---|
| Region | `northamerica-northeast1` (Montréal); DR copy of backups in `northamerica-northeast2` (Toronto) | PIPEDA pilot: keep personal and location data in Canada. Both regions offer every service below. |
| API | **Cloud Run** service `osiris-api`, 1 vCPU / 1 GiB, concurrency 40, `min-instances=1` (no cold start on the run-upload path), `max-instances=1` until §5.1 items 2–3 land, then 1–5 | Lowest-ops managed container with built-in revision traffic splitting (canary and one-command rollback), per-request billing, Google-managed TLS. GKE is overkill for one service and one team; a single VM (current runbook) has no PITR, no autoscale and a manual rollback. AWS App Runner / Fargate + RDS is equivalent; the only requirement is to pick one cloud, not split. |
| Database | **Cloud SQL for PostgreSQL 16** with PostGIS, `db-custom-1-3840` (pilot) → regional HA when real money or >1 city; 7-day PITR, automated daily backups, cross-region backup copy; private IP + Cloud SQL Auth connector, IAM database auth for the API service account | ADR-002. Single-writer SQLite p99 of 0.8–1.1 s at 20 writers (doc 12) disappears. SQLite in a volume cannot be restored to a point in time. |
| Secrets | Secret Manager, mounted as env vars into Cloud Run; rotation documented in §2.2 | The app already fails closed on missing secrets; no secret ever lives in an image or repo. |
| Jobs | Cloud Scheduler → authenticated `POST /internal/jobs/{name}` (OIDC, service-account only) **or** a Cloud Run Job per task. Pilot interim: `max-instances=1` with the in-process scheduler | Removes the N-instances problem and makes job runs visible and retryable. |
| Cache / shared limiter | None for the pilot; **Memorystore Redis (1 GiB basic)** when `max-instances` > 1 | Redis costs ~US$35/mo idle; not justified until horizontal scale. A PostgreSQL-backed limiter table is the zero-cost alternative. |
| Registry / build | Artifact Registry (`osiris/api`), images tagged `sha-<git>` and `v<semver>`, built by GitHub Actions with Workload Identity Federation (no long-lived keys) | Immutable, signed (cosign) artefacts; the rollback target is always a known digest. |
| Admin console | Static files on Cloud Storage + HTTPS load balancer **behind Identity-Aware Proxy** (Google Workspace SSO, MFA enforced) or Cloudflare Pages + Cloudflare Access (free ≤ 50 seats) | Satisfies the "admin MFA" production gate (doc 05 §4) without building MFA into the app first. Never expose the admin origin publicly. |
| Edge | Cloudflare (free plan) for DNS, WAF managed rules, bot fight mode, rate limit on `/api/v1/auth/*` and `/api/v2/events` as defence in depth; origin locked to Cloudflare IPs | Cheap L7 protection in front of a pilot with no SOC. |
| Mobile distribution | Google Play (internal → closed → production, staged 10/25/50/100 %), TestFlight → App Store phased release | Store review is 1–7 days; staged rollout is the mobile rollback mechanism. |
| Object storage | Not needed yet (route points and exercise summaries are rows); bucket reserved for exports and evidence when added | Avoid paying for unused services. |
| Observability | Cloud Logging (JSON logs already emitted), Managed Service for Prometheus sidecar scraping `/metrics`, Cloud Monitoring alerts + uptime checks, **Sentry** (backend + Flutter) for errors and crash-free sessions | Detail in §4. |

### 1.3 Environments

| Env | API | DB | Admin | App build | Data |
|---|---|---|---|---|---|
| Dev | local uvicorn, SQLite | file | `npm run dev` | emulator, `API_BASE_URL=http://10.0.2.2:8000` | synthetic |
| SIT | Cloud Run `osiris-api-sit`, auto-deploy from `master` | Cloud SQL `osiris-sit` (smallest, no HA) | `admin-sit.<domain>` behind IAP | internal track, `API_BASE_URL=https://api-sit.<domain>` | `seed_city.py` synthetic |
| UAT | Cloud Run `osiris-api-uat`, deploy on tag `v*-rc*` after approval | Cloud SQL `osiris-uat`, PITR on (restore drills happen here) | `admin-uat` behind IAP | closed testing track / TestFlight | synthetic + pilot testers, never prod copies |
| PROD | Cloud Run `osiris-api`, deploy on tag `v*` after two approvals, canary 10 % → 100 % | Cloud SQL `osiris-prod`, PITR 7 d, HA at money launch | `admin.<domain>` behind IAP | production track, staged rollout | real |

Separate GCP project per environment (`osiris-sit`, `osiris-uat`, `osiris-prod`): IAM, budgets, secrets and Stripe
mode cannot bleed across. Stripe stays in **test mode in every environment** until the real-money gate (ADR-005).

### 1.4 Scalability, availability and cost

- **Scale path.** Pilot ≤ 1 000 players, ~20 concurrent at peak: one Cloud Run instance at concurrency 40 covers it
  with the p95 < 500 ms budget (doc 12 numbers were measured on SQLite; re-run on PostgreSQL in SIT, PLAN item
  "SQLite single-writer tail latency"). Multi-city: Redis limiter, `max-instances` 2–10, Cloud SQL HA, read replica for
  leaderboards if needed. No service extraction before ADR-001's trigger (team or scale boundary).
- **Availability target for the pilot:** 99.5 % monthly on `/healthz` and the run-upload path (≈ 3.6 h/month). Cloud
  Run + zonal Cloud SQL deliver this; regional HA (99.95 %) is bought when money moves.
- **Offline tolerance.** The app already queues route points and exercise sets on the device and resyncs; short API
  outages lose no runs. This is the main reason the pilot does not need HA on day one.
- **Cost estimate (US$/month, pilot, verify in the pricing calculator before sign-off):**

| Item | Estimate |
|---|---|
| Cloud Run, 1 always-on instance, 1 vCPU/1 GiB, low traffic | 15–30 |
| Cloud SQL `db-custom-1-3840`, 20 GB SSD, PITR, daily backups | 45–60 (×2 with HA) |
| Secret Manager, Artifact Registry, Scheduler, Logging/Monitoring within free tiers | < 10 |
| Cloudflare free, IAP (no charge), Sentry developer tier | 0–30 |
| Stores: Google Play US$25 once, Apple US$99/year | ≈ 10 amortised |
| **Total pilot** | **≈ 80–140** |

Doubling to multi-city (HA DB, Redis, 3 instances) lands around US$250–350/month.

---

## 2. Security and compliance before the release build

### 2.1 Already in place (verified in code or by today's test run)

Fail-closed boot on missing `OSIRIS_JWT_SECRET`, `OSIRIS_WEBHOOK_SECRET`, Stripe keys (unknown `OSIRIS_ENV` is treated
as production). CORS allowlist from `OSIRIS_CORS_ORIGINS`. bcrypt password hashing. JWT HS256 with `iat`-based
"sign out everywhere" revocation. Suspension enforced on every player route (v1 and v2). Rate limits on login,
onboarding, verify, webhook, route upload, challenge actions, events. Stripe webhook signature verification and
event-id dedupe. Append-only audit events without coordinates. Consent records, export, erasure (ledger anonymised,
not deleted). Raw route points purged after 45 days. `/metrics` token-gated. Non-root container, dependencies pinned
by lockfile. JSON access logs with `X-Request-ID`, route templates only. Tokens on device in `flutter_secure_storage`.
Crystal ledger invariant checked in CI (`reconcile_ledger.py`). 15 backend suites, Flutter and admin builds green (§6).

### 2.2 Required hardening (release blockers unless marked otherwise)

| # | Control | Current state | Action | Owner |
|---|---|---|---|---|
| S1 | Correct client IP behind the load balancer | limiter keys on `request.client.host`; uvicorn lacks `--proxy-headers` | `CMD` → `uvicorn main:app --proxy-headers --forwarded-allow-ips='*'` (Cloud Run strips spoofed `X-Forwarded-For`); add a regression test that `X-Forwarded-For` buckets independently | **[human]** Dockerfile; agent test |
| S2 | Dependency vulnerabilities | `pip-audit` on the lock today: **pyjwt 2.12.1** (12 advisories, fix ≥ 2.15.0), **starlette 1.0.0** (fix ≥ 1.3.1), **urllib3 2.7.0** (fix 2.8.0). `npm audit --omit=dev`: **2 high** (`form-data` via axios), 6 high including dev deps | Bump and re-lock; re-run suites; make `pip-audit` and `npm audit --audit-level=high` CI steps | **[human]** lockfiles + CI |
| S3 | Access-token lifetime | 7 days, no refresh rotation | Minimum: 24 h access tokens plus the existing revocation. Target before money: 15 min access + rotating refresh tokens with reuse detection (doc 10 risk 6) | agent (minimum) / planned |
| S4 | Admin MFA | not built | Admin origin only reachable through IAP / Cloudflare Access with SSO MFA; API additionally restricts `role=admin` logins to an allow-listed email domain | human infra + agent |
| S5 | Admin password cap of 12 chars in `seed_admin.py` (doc 12 finding 14) | open | Allow ≥ 64 chars, minimum 12, no composition rules (NIST 800-63B) | agent |
| S6 | Security headers | none set by the app | At the edge: HSTS (1 year, preload after UAT), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, admin CSP `default-src 'self'; connect-src <api>` with no inline scripts, `frame-ancestors 'none'`. API: same minus CSP | infra + agent (middleware) |
| S7 | Transport encryption | HTTP in the container | TLS 1.2+ (1.3 preferred) terminated by Google-managed certificates; Cloud Run → Cloud SQL over the Auth connector (mTLS); Cloudflare "Full (strict)" | infra |
| S8 | Encryption at rest | n/a on a VM | Cloud SQL, backups, Secret Manager and Artifact Registry are AES-256 with Google-managed keys; CMEK not required for the pilot | infra |
| S9 | Secret rotation | manual | JWT secret, webhook secret, metrics token: 90-day rotation runbook (dual-secret window for JWT is not implemented → rotation logs everyone out; schedule it in a maintenance window). Stripe keys rotated on any exposure | human ops |
| S10 | App identity and signing | `com.example.*`, debug keystore | Set final `applicationId`/bundle id, Play App Signing with an upload keystore kept in Secret Manager, Apple distribution certificate in the team account; never in the repo | **[human]** |
| S11 | App network policy | default URL is cleartext emulator host | Release builds built with `--dart-define=API_BASE_URL=https://api.<domain>`; CI fails if the release artefact contains `http://10.0.2.2`; Android `usesCleartextTraffic` stays default (false) | agent + CI |
| S12 | Mobile hardening | not assessed | MobSF scan of the release APK/AAB and IPA; confirm R8/ProGuard shrinking in release; no debug logging of tokens or coordinates | human QA |
| S13 | SAST / secrets / container scanning | not in CI | Semgrep (or CodeQL) on PRs, gitleaks + GitHub push protection, Trivy on the built image (fail on HIGH/CRITICAL with fix available), Dependabot weekly | **[human]** CI |
| S14 | DAST | none | OWASP ZAP baseline against SIT on every `master` deploy; authenticated scan before UAT | human CI |
| S15 | Independent review | none | External penetration test or equivalent before PROD (doc 05 §4 gate); re-test findings rated high | human |
| S16 | Least-privilege IAM | n/a | Per-env projects; runtime SA with `cloudsql.client` + `secretmanager.secretAccessor` only; deployer SA via Workload Identity Federation; no human `Owner` outside a break-glass group with alerting | human infra |
| S17 | Legacy v1 game endpoints | still mounted (doc 10 risk 4, PLAN [human] product item) | Decide: remove, or gate behind `OSIRIS_LEGACY_V1=1` defaulting off in PROD | human decision → agent |
| S18 | Kill switch / minimum app version | no endpoint | `GET /api/v2/app-config` → `{min_version, maintenance, message}`; app blocks below `min_version` | agent |

### 2.3 Access-control model

- **People:** Google Workspace groups `osiris-admins` (IAP to admin console, break-glass GCP), `osiris-support`
  (IAP only), `osiris-deployers` (approve GitHub environments). MFA enforced at the identity provider.
- **Services:** one service account per workload (api runtime, migration job, scheduler invoker, CI deployer). The
  scheduler invokes job endpoints with an OIDC token; the API verifies audience and service-account email.
- **Application:** roles `player | admin | merchant` in the JWT (existing). Admin creation only via `seed_admin.py`
  run as a Cloud Run Job by a deployer, logged.
- **Data:** no direct database users for humans in PROD; read access through a read replica or exported, redacted
  reports. Every admin action already writes an audit event; keep audit rows for 24 months.

### 2.4 Privacy and compliance (PIPEDA)

- Data residency in Canada (§1.2). Processors with DPAs: Google Cloud, Stripe, Sentry, Cloudflare, Apple, Google Play.
- Privacy policy and in-app disclosures match what the code does: consent at sign-up, 45-day raw route retention,
  export, erasure with anonymised financial records, coarse public map (ADR-004), camera frames never leave the device.
- Sentry: `send_default_pii=false`, scrub coordinates and emails in `before_send`; Cloud Logging retention 30 days
  (audit table is the long-term record).
- Breach process: SEV-1 in doc 08; notification assessment within 72 h of confirmation; privacy officer named before PROD.
- Age gate before any paid or prize mechanic (doc 05 §3); not needed for the XP-only release.

### 2.5 Pre-release build checklist (security)

- [ ] S1, S2, S10, S11 merged and verified in UAT.
- [ ] Admin origin returns 302 to SSO when unauthenticated (S4) and CSP is present (S6).
- [ ] `pip-audit`, `npm audit --omit=dev --audit-level=high`, Trivy, gitleaks all clean on the release commit.
- [ ] Release APK/AAB and IPA scanned (S12); strings contain only the production API host.
- [ ] Secrets created in Secret Manager for PROD; no `.env` on any server; test-mode Stripe keys only.
- [ ] Pen-test report with no open high findings (S15).
- [ ] Restore drill from PITR completed in UAT within the RTO (§4.5).

---

## 3. Deployment and CI/CD

### 3.1 Target pipeline (GitHub Actions)

```
pull_request ─► lint (ruff) ─► mypy (blocking) ─► alembic upgrade head on SQLite AND PostgreSQL service
             ─► 15 backend suites on both DBs ─► ledger reconciliation ─► OpenAPI drift
             ─► admin: npm ci, npm run build, npm audit ─► app: flutter analyze, flutter test
             ─► pip-audit, gitleaks, semgrep ─► docker build, Trivy, boot + /healthz
push master  ─► build image sha-<git> ─► push Artifact Registry (cosign sign)
             ─► migrate job (SIT) ─► deploy Cloud Run SIT 100 % ─► smoke tests ─► ZAP baseline
tag v*-rc*   ─► [approval: product + eng] ─► migrate job (UAT) ─► deploy UAT ─► smoke + e2e
tag v*       ─► [approval: 2 of osiris-deployers] ─► migrate job (PROD) ─► deploy PROD revision at 0 %
             ─► 10 % for 30 min (auto-abort on alert) ─► 100 % ─► release record
```

Today CI covers the backend only and triggers on `master` pushes and backend-path PRs. Adding the app jobs, the GDPR
and exercise suites, PostgreSQL, scanners and the deploy jobs are **[human]** edits to `.github/workflows/`
(PLAN.md already lists them).

### 3.2 Build artefacts

| Artefact | Built by | Versioning |
|---|---|---|
| API image | CI from `Osiris_backend/Dockerfile`, lockfile install | `sha-<git>`, `v1.2.3`; digest recorded |
| Admin console | `npm run build` in CI with `VITE_API_BASE_URL` per env | folder per commit; previous kept for rollback |
| Android AAB / iOS IPA | CI (`flutter build appbundle --release --dart-define=API_BASE_URL=…`, Xcode Cloud or `flutter build ipa`) | `pubspec.yaml` `version: x.y.z+build`; build number = CI run |
| Release record | CI job writes `releases/<tag>.json` | commit, image digest, migration head, config version, feature flags, verifier `RULES_VERSION`, approvers (doc 06 §5) |

### 3.3 Database migration policy

1. Migrations run as a **Cloud Run Job** (`alembic upgrade head`) against the target DB **before** the new revision
   gets traffic. Remove the upgrade from the container `CMD` **[human]** so N instances never race.
2. Expand/contract: a release may add tables, nullable columns and indexes; renames and drops ship one release later,
   after the previous revision no longer reads them. The old revision must work on the new schema, or rollback is impossible.
3. Every migration is tested from zero and from the previous head on PostgreSQL in CI; every migration has a working
   `downgrade`.
4. Before the PROD migration job: automatic on-demand Cloud SQL backup, named after the tag.

### 3.4 Smoke tests (run against every environment after deploy)

`/healthz` 200 with `migrations: current`; `/metrics` with token 200, without 401; login with a seeded tester;
`GET /api/v2/me/today`; `GET /api/v2/challenges/nearby`; `GET /api/v2/rules`; `POST /api/v2/runs` create → finish
with a fixture route is accepted; unauthenticated admin origin redirects to SSO; Stripe webhook with a bad signature
returns 401. Failure of any step stops the pipeline and, in PROD, routes traffic back to the previous revision.

### 3.5 Rollback procedures

| Layer | Trigger | Procedure | Time |
|---|---|---|---|
| API (no schema change) | any §4.2 page during canary, smoke failure, or on-call decision | `gcloud run services update-traffic osiris-api --to-revisions=<previous>=100 --region northamerica-northeast1` | < 2 min |
| API (additive migration shipped) | same | Same command; schema stays (expand/contract guarantees the old revision runs). Forward-fix in the next release | < 2 min |
| API (destructive migration) | same | Not allowed in a release that also changes behaviour. If unavoidable: restore to the pre-migration on-demand backup into a new instance, repoint, accept data loss since the backup; SEV-2 declared | ≤ RTO 2 h |
| Database corruption / bad data job | ledger reconciliation alert, support reports | PITR clone to the timestamp before the event, verify in UAT project, swap connection name, SEV-1 | ≤ RTO 2 h, RPO ≤ 15 min |
| Admin console | broken page | re-publish previous build folder / Pages rollback | < 5 min |
| Mobile | crash-free < 99 % on the new version, or a server-incompatible build | Halt staged rollout in Play Console / App Store Connect; raise `min_version` only if the build is harmful; otherwise ship a hotfix with expedited review. The server must keep accepting the previous app version for 30 days | hours–days |
| Config / secret | bad value | redeploy same image with previous secret version (`:previous` alias) | < 2 min |

Rollback drills run in UAT on every release candidate; the drill result is part of the release record.

### 3.6 Release checklist

**Pre-deploy**
- [ ] CI green on the release commit (all jobs in §3.1) and the gate passes locally.
- [ ] PLAN.md has no unchecked non-`[human]` items for this release; `[human]` decisions recorded.
- [ ] §2.5 security checklist complete; OpenAPI contract committed; `RULES_VERSION` unchanged or bumped deliberately.
- [ ] Migration reviewed, tested on a UAT PITR clone, expand-only.
- [ ] Release notes, support copy for accepted / rejected / review-required outcomes, rollback owner named.
- [ ] On-call engineer and product owner available for the canary window.

**Deploy**
- [ ] SIT auto-deploy + smoke green. UAT deploy, e2e run → course → challenge → attempt loop on a physical phone.
- [ ] PROD: on-demand backup → migration job → revision at 0 % → smoke → 10 % for 30 min → 100 %.
- [ ] Mobile: internal track → closed testing (pilot cohort) → production 10 % → 50 % → 100 % over ≥ 3 days.

**Post-deploy**
- [ ] 24 h: error rate, p95, run acceptance ratio and crash-free sessions at baseline (§4.1).
- [ ] Release record written; stakeholders notified; previous revision kept for 30 days.

---

## 4. Monitoring, logging and maintenance

### 4.1 SLOs (pilot)

| SLI | Target | Source |
|---|---|---|
| Availability of `/healthz` and `POST /api/v2/runs/{id}/points` | 99.5 % / 30 d | uptime checks + `osiris_http_requests_total` |
| Read latency (`/me/today`, `/challenges/nearby`, `/leaderboards/local`) | p95 < 500 ms | `osiris_http_request_duration_seconds` |
| Write latency (points, finish, exercise submit) | p95 < 500 ms, p99 < 1 s | same |
| 5xx share | < 1 % | `osiris_http_requests_total{status=~"5.."}` |
| Crash-free sessions (app) | ≥ 99.5 % | Sentry |
| Ledger invariant | 0 non-reconciling users | nightly `reconcile_ledger.py --check` job |

### 4.2 Alerts (Cloud Monitoring → PagerDuty/phone for page, Slack/email for ticket)

| Alert | Condition | Severity |
|---|---|---|
| API down | uptime check fails from 2 regions for 2 min | page |
| 5xx burn | > 1 % for 10 min, or > 5 % for 2 min | page |
| Latency | p95 > 0.5 s for 10 min on read routes | page in canary, ticket otherwise |
| Rejection wave | `osiris_run_verifications_total{status="rejected"}` share > 2× the 7-day baseline for 1 h | page (verifier regression or spoofing) |
| Review queue | `review_required` share > 10 % for 1 h, or queue age > 24 h | ticket |
| Ledger | nightly reconciliation non-zero, or any `apply_crystal_delta` error log | page (SEV-1 class) |
| Stripe | webhook 4xx/5xx > 0 in 15 min, or signature failures > 5/h | page |
| Auth abuse | 429s on `login` > 100/h from distinct IPs, admin login from outside the allow-listed domain | ticket / page |
| Jobs | decay, TTL, settlement, `seed_city` not completed in their window | ticket |
| Infra | Cloud SQL CPU > 80 % 15 min, storage > 80 %, connections > 80 % of max, backup failed, cert expiry < 14 d | ticket / page for backup |
| Budget | 50 / 90 / 100 % of monthly budget | email |
| Mobile | crash-free < 99 % on a version with > 100 sessions; new crash signature affecting > 1 % | ticket, halts staged rollout |

### 4.3 Dashboards

1. **Service**: requests, 5xx, p50/p95/p99 by route template, instance count, Cloud SQL CPU/connections/replication.
2. **Trust**: verification outcomes and rejection reasons by `RULES_VERSION`, review queue depth and age, exercise
   outcomes per exercise, suspensions and reports per day.
3. **Economy (test mode)**: ledger debit/credit totals, reconciliation status, webhook events by type, duplicate attempts.
4. **Product**: sign-ups, consent given/withdrawn, first verified run within 24 h, D1/D7 retention, exports and erasures.
5. **Mobile**: crash-free sessions, location-permission denial rate, upload-queue age, cold start, APK size per release.

### 4.4 Logging and tracing

- JSON logs (`OSIRIS_LOG_JSON=1`) to Cloud Logging; log-based metrics for `route-point-ttl`, settlement, erasure.
  Retention 30 days; an exclusion filter drops `/healthz` 200s. No coordinates, tokens or emails in log lines: add a
  CI test that greps the access-log formatter and job logs for those fields.
- Request correlation via `X-Request-ID` end to end: the app and admin client send it, Cloud Run's trace header is
  logged alongside.
- Tracing: OpenTelemetry FastAPI + SQLAlchemy instrumentation exporting to Cloud Trace at 10 % sampling, after the
  PostgreSQL move (not a release blocker).
- Errors: Sentry SDK in the API (`traces_sample_rate=0`, PII off) and Flutter (`SentryFlutter.init`), release tagged
  with the git SHA and app version so regressions map to a deploy.

### 4.5 Backup, DR and maintenance protocols

| Protocol | Cadence | Owner |
|---|---|---|
| Automated Cloud SQL backups + PITR, cross-region copy | daily / continuous | platform |
| Restore drill (PITR clone into UAT, run suites + reconciliation against it) | quarterly and before any money launch; RTO ≤ 2 h, RPO ≤ 15 min | on-call |
| Dependency updates (Dependabot PRs, `pip-audit`, `npm audit`, Flutter `pub outdated`) | weekly review, security fixes within 7 days (critical 48 h) | eng |
| Base image refresh (`python:3.13-slim`) and rebuild | monthly or on CVE | **[human]** Dockerfile |
| Secret rotation (JWT, webhook, metrics token; Stripe on exposure) | 90 days, maintenance window | ops |
| `seed_city.py` for official challenges (expire after 30 days, doc 11 risk 7) | monthly Cloud Scheduler job | product + ops |
| Retention jobs verification (route points 45 d, telemetry TTL) | weekly check of job logs and a row-age query | eng |
| Ledger reconciliation | nightly job + alert | eng |
| Load test on PostgreSQL (20 users, p99 < 500 ms writes) | each release that touches runs or DB | eng |
| On-call: one engineer, business hours during pilot, 24/7 only for SEV-1 pages; escalation to product owner | continuous | eng lead |
| Postmortem for every SEV-1/2 within 5 working days; actions tracked in PLAN.md | per incident | incident commander |
| Capacity and cost review (instances, DB size, budget alerts) | monthly | eng lead |
| Store compliance: Play Data Safety form, App Store privacy labels updated on every data change | per release | product |

---

## 5. Work breakdown to reach the release build

### 5.1 Engineering (in order; each is one PLAN.md item and one commit)

1. **Backend: PostgreSQL support in the app** — `database.py` reads `OSIRIS_DATABASE_URL`, SQLite pragmas only for
   SQLite, pool settings for PostgreSQL; add `psycopg[binary]` (**[human]** lockfile); run all suites against a local
   PostgreSQL; fix any SQLite-only SQL. Acceptance: suites + ledger check pass on both engines.
2. **Backend: trust proxy headers and test the limiter per client** (S1; Dockerfile part **[human]**).
3. **Backend: externalise scheduled jobs** behind `POST /internal/jobs/{name}` with OIDC/service-token auth and a
   PostgreSQL advisory lock, keeping the APScheduler path for dev. Acceptance: running two processes executes each job once.
4. **Backend: `GET /api/v2/app-config`** with `min_version` and maintenance flag; app honours it (S18).
5. **Backend: access-token lifetime 24 h** and security-header middleware (S3 minimum, S6).
6. **Backend: admin password policy** (S5).
7. **Customer: production build configuration** — final application id, release signing from CI secrets (**[human]**
   keystore), `API_BASE_URL` enforced https in release, cleartext check in CI (S10, S11).
8. **Admin: CSP-compatible build** (no inline scripts) and `X-Request-ID` propagation.
9. **CI** (**[human]**): PostgreSQL service, app jobs, GDPR + exercise suites, blocking mypy, scanners, image deploy
   jobs with GitHub environments and required reviewers.
10. **Dependencies** (**[human]**): bump pyjwt, starlette, urllib3, axios; re-lock; re-run everything.

### 5.2 Human decisions still open (from PLAN.md)

Legacy v1 endpoints (retire or gate), pause/resume design, Android 13+ notification permission, zero-rep set upload,
ML Kit model delivery, formatter and admin lint adoption, launch principle 1 vs the camera feature, physical-device QA
on Android and iPhone, pilot city seed content and partner consent, privacy officer and on-call roster.

### 5.3 Go / no-go gates

- **SIT:** items 1–3 merged; CI runs on PostgreSQL; smoke tests green on Cloud Run.
- **UAT:** items 4–10 merged; §2.5 complete except pen test; restore drill and rollback drill done; physical-device e2e passed.
- **PROD:** pen test closed; admin behind SSO MFA; alerts exercised with a synthetic incident; two-person approval recorded; stores approved with staged rollout configured.

---

## 6. Build run on 2026-10-17 (this environment)

Linux container, Python 3.13.16, Node 22.22.0, Flutter 3.47.7 (downloaded for this run; no Android SDK, so no APK),
no Docker daemon (image build and the container `/healthz` boot could not be executed here; CI covers them).

| Check | Result |
|---|---|
| `ruff check .` | pass |
| `mypy … main.py models.py spatial_utils.py ml_referee.py` | 0 errors |
| `alembic upgrade head` from an empty database | pass (head `a7c3e9f2b4d1`) |
| `reconcile_ledger.py --check` before and after suites | pass |
| 13 CI suites + `test_mvp_gdpr_and_email_uniqueness` + `test_exercise_sessions` | all pass |
| `check_openapi_drift.py` | in sync |
| `npm run build` (tsc + vite) | pass, 280 kB JS / 87 kB gzip |
| `flutter test`, `flutter analyze` | 61 tests pass; no issues |
| `pip-audit` (lock) | pyjwt, starlette, urllib3 advisories (S2) |
| `npm audit --omit=dev` | 2 high (S2) |

---

## 7. Android / iOS parity (2026-10-17)

"Identical" here means the same app, version, permissions, behaviour and backend contract on both platforms. The
binaries themselves differ by nature (AAB vs IPA, different signing). No Android SDK or macOS exists in the build
environment, so neither binary was produced here; parity is enforced by `test/platform_parity_test.dart`, which
runs in `flutter test` and therefore in the gate.

**Fixed**

| Gap | Fix |
|---|---|
| Store name differed ("Osiris" vs "Osiris Customer") | iOS display name is now "Osiris"; test compares both files |
| API default `10.0.2.2` only works on the Android emulator | `resolveApiBaseUrl`: debug uses 10.0.2.2 (Android) or 127.0.0.1 (iOS simulator) |
| A release build could ship with a dev or cleartext API host | Release throws at start unless `API_BASE_URL` is an https URL (closes S11 in the app) |
| iOS Keychain survives uninstall, Android does not: a reinstall restored the old session on iOS only | First-launch marker in SharedPreferences; missing marker clears stored credentials. Existing test installs are signed out once on upgrade |

**Already equivalent (now asserted by tests):** version and build number both come from `pubspec.yaml`;
location uses the same consent model (while-in-use, no background-location permission; Android foreground service,
iOS background mode with the system indicator); camera permission with the "nothing is saved or uploaded" purpose
text; no cleartext or arbitrary-loads opt-in; one bundle id per platform.

**Open, needs a human (S10)**
- Final application id. Android `com.example.osiris_customer` and iOS `com.example.osirisCustomer` are the same
  string up to platform rules (underscores are illegal in bundle ids), but both are placeholders and the store
  identity cannot change after first upload. Choose the production domain, then change both together; the test
  keeps them in step.
- Release signing: Android uses the debug key, iOS has no team. Play App Signing upload key and the Apple
  distribution certificate must be created by the account owner.
- Android 13+ notification permission (PLAN.md): the recording notification is hidden until granted; iOS has no equivalent step.
- Deliberate platform differences that stay: camera image format (NV21 vs BGRA), Android foreground-service
  notification vs iOS location indicator, ML Kit minimum OS (iOS 15.5).
- Physical-device runs of the same script on one Android phone and one iPhone remain a UAT gate; the iOS simulator
  and a macOS build agent are not available in this environment.
