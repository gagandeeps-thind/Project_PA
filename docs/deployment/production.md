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
- [x] 9. **Stripe**: the webhook URL is `https://api.osiris.fit/api/v1/payments/stripe/webhook`.
  `OSIRIS_PUBLIC_BASE_URL` must be `https://api.osiris.fit` (share links and the app's `links.webHost`).
  The mobile app only picks up `https://api.osiris.fit` in a new release build.
- [ ] 10. **Retire the disk**: download the SQLite file first (Render Shell: `ls -l /data`), then remove the
  `disk:` block from `render.yaml` and the disk in the dashboard. Deleting it destroys the file.

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

## Changing the schema

Only through Alembic (`Osiris_backend/alembic/versions`, human-reviewed): the API runs
`alembic upgrade head` on every boot. New tables inherit the locked-down default privileges; check the
Supabase security advisor after each migration.
