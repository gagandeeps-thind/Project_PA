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

## Status on 2026-10-27

| Check | Result |
|---|---|
| `GET https://api.osiris.fit/healthz` | 200, database ok, migrations current (`a7c3e9f2b4d1`) |
| API memory | 90 MB of 512 MB |
| Database | 39 tables, RLS on for all, no grants to `anon` or `authenticated`, PostGIS 3.3.7 installed, 21 MB |
| Accounts | 0 players, **0 admins** (the admin console has no one who can sign in yet) |
| Supabase security advisor | Only "RLS enabled, no policy" (expected: only the API, as `postgres`, reads the tables) |
| Supabase performance advisor | One duplicate index (`run_sessions.finish_idempotency_key`), 15 unindexed foreign keys on legacy tables |
| Cloudflare | `api` and `admin` are **DNS-only** CNAMEs to Render: traffic reaches Render without passing the osiris.fit WAF |
| Origin lock | Off: `https://osiris-api-ownh.onrender.com` serves the API directly |
| Admin headers | No CSP, HSTS or frame protection yet (added in `render.yaml`, applied on the next Blueprint sync) |
| Supabase edge function `redis-cache` | Still deployed, unused (removed from the repo) |
| Render disk `osiris-data` (1 GB at `/data`) | Holds only the retired SQLite file |

## Open steps, in this order

Order matters for steps 1 to 3: turning on the origin lock before Cloudflare sends the header refuses
every request.

1. **Proxy the two hosts through Cloudflare.** Cloudflare, `osiris.fit`, DNS: switch `api` and `admin`
   from DNS only (grey cloud) to **Proxied** (orange). SSL/TLS: **Full (strict)**; Edge Certificates:
   Always Use HTTPS on, minimum TLS 1.2, HSTS on (max-age 12 months, include subdomains). Then check
   `https://api.osiris.fit/healthz` still answers 200.
2. **Add the origin header.** Generate a value once:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
   Rules, Transform Rules, Modify Request Header: when hostname equals `api.osiris.fit`, set static
   header `X-Origin-Verify` to that value.
3. **Turn the lock on in Render.** `osiris-api`, Environment: `OSIRIS_ORIGIN_SECRET` = the same value.
   After the deploy:
   - `https://api.osiris.fit/api/v2/rules` is 200 (through Cloudflare)
   - `https://osiris-api-ownh.onrender.com/api/v2/rules` is 403 (direct, refused)
   - `/healthz` is 200 on both (Render's health check calls it directly)

   This also makes rate limits per player. Before it, every player shares one bucket, because the
   API only sees Render's proxy address.
4. **WAF and rate rules** (Cloudflare, Security): managed ruleset on; a rate-limiting rule on
   `/api/v1/auth/login`, `/api/v2/auth/register` and `/api/v2/me/password` (for example 20 requests per
   minute per IP, block 10 minutes). Leave **Bot Fight Mode off**: it challenges the mobile app's HTTP
   client, which cannot solve a challenge.
5. **Upstash** (when you add a second API instance, or now): Upstash console, the database, REST API
   section. Copy the URL and the token into Render as `UPSTASH_REDIS_REST_URL` and
   `UPSTASH_REDIS_REST_TOKEN`. Pick the Upstash region nearest Oregon (us-west).
6. **Nightly backups to R2.**
   - Cloudflare, R2: create a private bucket `osiris-backups` and add a lifecycle rule that deletes
     objects after 35 days. Create an R2 API token with Object Read & Write on that bucket only.
   - Render, Blueprints, Sync: it creates the cron job `osiris-db-backup` and asks for `R2_ACCOUNT_ID`,
     `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` and `BACKUP_PASSPHRASE`. Store the passphrase in
     your password manager: without it no backup can be restored.
   - Trigger one run from the dashboard and check the log ends with `backup uploaded:`.
   - The same sync applies the admin console's security headers.
7. **Create the first admin.** Render, `osiris-api`, Shell:
   `python scripts/seed_admin.py` (prompts for email, password and name). Then sign in at
   https://admin.osiris.fit. Add Cloudflare Access on `admin.osiris.fit` (Zero Trust, Access,
   Applications) with your email and a one-time PIN, so the console asks for a second factor.
8. **Delete the unused edge function** (needs your confirmation):
   `npx supabase functions delete redis-cache --project-ref vhymfishiojgttlzcdgf`, then
   `npx supabase secrets unset UPSTASH_REDIS_REST_URL UPSTASH_REDIS_REST_TOKEN --project-ref vhymfishiojgttlzcdgf`.
9. **Stripe**: the webhook URL is `https://api.osiris.fit/api/v1/payments/stripe/webhook`.
   `OSIRIS_PUBLIC_BASE_URL` must be `https://api.osiris.fit` (share links and the app's `links.webHost`).
10. **Retire the disk** once you are sure the old SQLite file is not needed: download it first
    (Render Shell: `ls -l /data`), then remove the `disk:` block from `render.yaml` and the disk in the
    dashboard. Deleting it destroys the file.

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
