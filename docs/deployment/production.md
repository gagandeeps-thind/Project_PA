# Production: Render, Supabase, Cloudflare, Upstash, R2

How Osiris runs in production, what was checked on 2026-10-27, and the steps that are still open.
For how a request travels through these services, see `docs/architecture/how-it-works.md`.

| Piece | Service | Where |
|---|---|---|
| API | Render web service `osiris-api` (Docker, `Osiris_backend/Dockerfile`), Starter, 1 instance, Oregon | https://api.osiris.fit |
| Admin console | Render static site `osiris-admin` (`Osiris_admin_web/dist`) | https://admin.osiris.fit |
| Database | Supabase PostgreSQL 17, project `vhymfishiojgttlzcdgf`, us-west-2, via the session pooler | |
| DNS, CDN, WAF | Cloudflare, zone `osiris.fit` | |
| Shared rate limits | Upstash Redis (REST API) | optional until a second API instance |
| Backups | Cloudflare R2, written nightly by the Render cron job `osiris-db-backup` | |
| Config | `render.yaml` (Blueprint); secrets live in the Render dashboard | |

## Status on 2026-10-31

| Check | Result |
|---|---|
| `GET https://api.osiris.fit/healthz` | 200 through Cloudflare |
| Cloudflare | `api` and `admin` are **Proxied**; WAF managed ruleset and auth rate-limit rules on |
| Origin lock | On: `https://osiris-api-ownh.onrender.com/api/v2/rules` answers 403, `/healthz` 200 |
| Admin console | First admin seeded; behind Cloudflare Access (email + one-time PIN) |
| Backups | `osiris-db-backup` uploads nightly to R2 (first run 2026-10-31 23:31 UTC) |
| Upstash | Configured for shared rate limits |
| Supabase edge function `redis-cache` | Deleted |
| Render disk `osiris-data` (1 GB at `/data`) | Still attached; holds only the retired SQLite file |
| Supabase performance advisor | Duplicate `run_sessions.finish_idempotency_key` constraint dropped by migration `b5d2e8f1a9c3`; missing `crystal_purchases` indexes (incl. the UNIQUE `stripe_payment_intent_id` guard) added by `d6f3a1c8e2b7`; 15 unindexed foreign keys on legacy tables remain |

## Setup steps

- [x] 1. **Proxy the two hosts through Cloudflare** (DNS Proxied, SSL Full (strict), Always Use HTTPS, TLS 1.2+, HSTS).
- [x] 2. **Origin header**: Transform Rule sets `X-Origin-Verify` on `api.osiris.fit`.
- [x] 3. **Origin lock** in Render: `OSIRIS_ORIGIN_SECRET` matches the header.
- [x] 4. **WAF and rate rules**: managed ruleset; rate limit on `/api/v1/auth/login`, `/api/v2/auth/register`,
  `/api/v2/me/password`. Bot Fight Mode stays **off** (the mobile app cannot solve a challenge).
- [x] 5. **Upstash**: `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` in Render.
- [x] 6. **Nightly backups to R2**: bucket `osiris-backups` (35-day lifecycle), cron job `osiris-db-backup`.
  `BACKUP_PASSPHRASE` lives in the password manager: without it no backup can be restored.
- [x] 7. **First admin** via `python scripts/seed_admin.py`; Cloudflare Access on `admin.osiris.fit`.
- [x] 8. **Unused edge function** `redis-cache` and its secrets deleted.
- [ ] 9. **Payments**: Stripe is removed. Purchases go through Google Play (Android) and the App Store (iOS).
  Delete the old webhook endpoint in the Stripe Dashboard and the `STRIPE_*` variables on Render. The
  `crystal_purchases` table stays as purchase history.
- [ ] 9a. **Google Play Billing** (steps in `docs/architecture/google-play-billing.md`): set
  `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` (without it purchases answer 503 and nothing is granted), create the
  Pub/Sub topic and push subscription for `/api/v2/payments/google-play/rtdn` with `GOOGLE_PLAY_RTDN_TOKEN`,
  and set `GOOGLE_PLAY_ALLOW_TEST_PURCHASES=false` at public launch.
  `OSIRIS_PUBLIC_BASE_URL` must be `https://api.osiris.fit` (share links and the app's `links.webHost`).
  The mobile app only picks up `https://api.osiris.fit` in a new release build.
- [ ] 9b. **App Store billing** (steps in `docs/architecture/app-store-billing.md`): closed until
  `APPLE_APP_STORE_ENVIRONMENT` is set (verify and notifications answer 503, nothing is granted). Set it to
  `Production,Sandbox` for TestFlight and App Review, register
  `https://api.osiris.fit/api/v2/payments/app-store/notifications` in App Store Connect (Version 2, both
  environments), and switch to `Production` after approval.
- [ ] 9c. **Supabase RLS check** after the deploy that runs migration `b8e3f1a6c2d4`: Supabase dashboard >
  Advisors > Security shows no "RLS disabled in public" error, and the API still answers (the backend role
  owns the tables, so RLS without policies does not apply to it). The migration only touches tables that
  role owns; a table someone created in the SQL editor as another role keeps RLS off and is listed there.
- [ ] 10. **Retire the disk**: download the SQLite file first (Render Shell: `ls -l /data`), then remove the
  `disk:` block from `render.yaml` and the disk in the dashboard. Deleting it destroys the file.
- [ ] 11. **Deploys only for relevant commits**: `render.yaml` now has a `buildFilter` per service (API:
  `Osiris_backend/**`; admin: `Osiris_admin_web/**` and `infrastructure/docker/admin*`; backup cron:
  `infrastructure/backup/**`). Sync the Blueprint (Dashboard > Blueprints > Sync) and check each service's
  Settings > Build Filters shows them. A change to `render.yaml` alone still needs a manual sync.
- [ ] 12. **Performance migration `c5e9a3d7f1b2`** (domain centroids and 14 indexes) runs at the next boot. On
  PostgreSQL it builds every index with `CREATE INDEX CONCURRENTLY IF NOT EXISTS`, so writes are not blocked.
  Afterwards run in the Supabase SQL editor
  `SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;` and expect no rows. An index left
  INVALID by an interrupted build is skipped by a rerun: `DROP INDEX CONCURRENTLY <name>;` and redeploy.

## Backups and restore

`infrastructure/backup/backup.sh` runs `pg_dump --format=custom --schema=public` through the pooler,
encrypts the stream with AES-256 (`openssl enc -pbkdf2`, key from `BACKUP_PASSPHRASE`) and uploads it
to `s3://<R2_BUCKET>/osiris/<yyyy>/<mm>/osiris-<timestamp>.dump.enc`.

Restore into an empty database (a new Supabase project or branch), from any machine with the AWS CLI,
OpenSSL and PostgreSQL 17 client tools:

```
aws s3 cp s3://osiris-backups/osiris/2026/10/osiris-<timestamp>.dump.enc backup.enc \
  --endpoint-url https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in backup.enc -out backup.dump   # asks for the passphrase
pg_restore --no-owner --no-privileges -d "postgresql://postgres.<ref>:<password>@<pooler-host>:5432/postgres" backup.dump
```

Then point `OSIRIS_DATABASE_URL` at it; the API's boot runs `alembic upgrade head`, which is a no-op on
a restored schema. Practise this once before real players depend on it.

## Security settings the API enforces at boot and per request

- Outside dev/test, `OSIRIS_JWT_SECRET` (32+ bytes) and `OSIRIS_WEBHOOK_SECRET` are required, and with
  `OSIRIS_ENV=production` so is `OSIRIS_ORIGIN_SECRET` (escape hatch `OSIRIS_ALLOW_NO_CDN=1`). A deploy
  missing one fails its boot, and Render keeps the previous version running.
- `/docs`, `/redoc` and `/openapi.json` are served in dev/test only; the contract is `Documentation/openapi.json`.
- Every response carries `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a CSP that allows
  only inline styles and same-origin images, and HSTS outside dev (`core/security_headers.py`).
- Admin tokens last 12 hours. Admin and merchant tokens stop working when the row is deleted or the password
  changes (re-running `scripts/seed_admin.py`, 12+ characters). Tokens issued before this release carry no
  password fingerprint and stay valid until they expire.
- The legacy `POST /api/v1/payments/webhook` requires `provider_event_id` outside dev/test; a replayed signed
  body repeats a stored event id and changes nothing.

## Performance, scaling and CDN

What the API already does: GZip for responses over 1 KB, a weak ETag and `304` on every JSON GET
(`http_cache.py`), a 60 s in-process cache of the global leaderboards (`services/ttl_cache.py`,
`OSIRIS_LEADERBOARD_CACHE_SECONDS`), and a pooled database connection with pre-ping and recycle
(`OSIRIS_DB_POOL_*`, see `.env.example`). `python scripts/perf_audit.py` prints SQL statements per hot
endpoint, and `tests/test_query_budget.py` fails if one of them grows with the data.

Responses a shared cache may store (everything else is `private, no-cache`, because it is per player):

| Path | Cache-Control |
|---|---|
| `/privacy`, `/terms`, `/account-deletion` | `public, max-age=3600` |
| `/.well-known/assetlinks.json` | `public, max-age=3600` |
| `/api/v2/rules` | `public, max-age=300` |
| `/api/v2/arise/domains/{id}/photo` | `public, max-age=300` |

**[human] CDN caching (Cloudflare).** Cloudflare does not cache HTML or JSON by default, so these pass through
today. To serve them from the edge:
1. Cloudflare > `osiris.fit` > Caching > Cache Rules > Create rule "API public GETs": hostname equals
   `api.osiris.fit` AND request method is GET AND URI path is in `/privacy`, `/terms`, `/account-deletion`,
   `/.well-known/assetlinks.json`, `/api/v2/rules`, or starts with `/api/v2/arise/domains/` and ends with `/photo`.
2. Action: Eligible for cache; Edge TTL "Use cache-control header if present"; Browser TTL "Respect origin".
3. Leave every other path ineligible: never cache a request that carries `Authorization`.
4. Check: `curl -sI https://api.osiris.fit/terms` twice; the second answer shows `cf-cache-status: HIT`.
   After a legal text change, Caching > Configuration > Purge by URL.

**[human] More than one API instance (load balancing).** Render's proxy balances across instances by itself;
raising `numInstances` (or autoscaling) on `osiris-api` is all it takes, but only after these three:
1. **Retire the disk** (step 10). A Render service with a persistent disk runs exactly one instance and gets
   no zero-downtime deploys.
2. **Run the scheduler once.** `main.py` starts the background jobs (daily decay, challenge settlement, TTL
   cleanup, Play voided purchases) in every process. Render gives every instance the same environment, so
   `OSIRIS_RUN_SCHEDULER=0` cannot be set on some instances only. Move the jobs to a Render background
   worker (same image, `OSIRIS_RUN_SCHEDULER=1`, command running the scheduler only) and set
   `OSIRIS_RUN_SCHEDULER=0` on `osiris-api`, or add a PostgreSQL advisory lock around each job. Until then
   two instances apply the daily decay twice.
3. **Connections.** Each instance opens up to `OSIRIS_DB_POOL_SIZE + OSIRIS_DB_MAX_OVERFLOW` (5 + 5 in
   `render.yaml`). Keep that times the instance count under the Supabase pooler's limit (Supabase > Database
   > Settings > Connection pooling), or lower the pool per instance.
Shared rate limits already work across instances (Upstash). The in-process leaderboard cache is per
instance, which only means each instance recomputes a board once a minute. Migrations run at every boot;
with several instances prefer Render's `preDeployCommand: alembic upgrade head` (paid plans) so they run once.

## Changing the schema

Only through Alembic (`Osiris_backend/alembic/versions`, human-reviewed): the API runs
`alembic upgrade head` on every boot. New tables inherit the locked-down default privileges; check the
Supabase security advisor after each migration.
