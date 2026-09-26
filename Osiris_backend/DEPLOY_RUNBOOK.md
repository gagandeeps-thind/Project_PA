# Osiris Backend — Deploy / Rollback Runbook (Phase 0)

Scope: the single-VM (or single-container) pilot deployment. This is intentionally minimal —
it is the "deploy is one VM for now" baseline the playbook calls for. Postgres, externalized
cron, and real observability arrive in Phase 3; this runbook is rewritten then.

---

## 1. What gets deployed

A single container built from `Osiris_backend/Dockerfile`:
- Python 3.13-slim, non-root user, deps installed from `requirements.lock.txt` (exact closure).
- On boot the entrypoint runs `alembic upgrade head` (idempotent) then `uvicorn main:app`.
- Listens on `:8000`. `/healthz` is the readiness probe (DB reachable + migrations current).

## 2. Required environment (secrets via env only — never baked into the image)

| Var | Required when | Purpose |
| :-- | :-- | :-- |
| `OSIRIS_JWT_SECRET` | always in prod (`OSIRIS_ENV=production` makes it fatal if missing) | 32+ byte HS256 signing key |
| `OSIRIS_WEBHOOK_SECRET` | always in prod (fatal if missing) | legacy generic webhook HMAC key (`/payments/webhook`) |
| `STRIPE_SECRET_KEY` | always in prod (fatal if missing) | Stripe server API key (`sk_live_…` / `sk_test_…`) |
| `STRIPE_WEBHOOK_SECRET` | always in prod (fatal if missing) | Stripe webhook signing secret (`whsec_…`) for `/payments/stripe/webhook` |
| `STRIPE_PUBLISHABLE_KEY` | optional | `pk_…` returned to the Flutter client to init the Stripe SDK (public, not a secret) |
| `OSIRIS_ENV` | prod | set to `production` to enforce the secrets above at boot (fail-closed, audit §2.1) |
| `OSIRIS_LOG_JSON` | containers | `1` → structured JSON access logs |
| `OSIRIS_LOG_LEVEL` | optional | default `INFO` |
| `OSIRIS_TELEMETRY_TTL_DAYS` | optional | raw-sample retention; `0` disables purge |

Generate a JWT secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

> **Stripe keys** come from the Stripe Dashboard: secret key under Developers → API keys; the
> webhook signing secret (`whsec_…`) under Developers → Webhooks after you add an endpoint
> pointing at `https://<host>/api/v1/payments/stripe/webhook` subscribed to
> `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.processing`.
> Start with **test-mode** keys; only swap to live keys at the real-money launch gate. A secret
> key that has ever been pasted into a chat/log/ticket must be rolled before go-live. Locally,
> put these in `Osiris_backend/.env` (gitignored) — see `.env.example`.

> NOTE (carried from Phase 0 findings): the SQLite database is a single file with **no PITR**.
> This is acceptable only for the pre-money pilot. Before any real-money movement, Phase 3's
> Postgres migration + tested restore is a hard prerequisite (and a money-layer red line).

## 3. Deploy

```bash
# from a clean checkout
docker build -t osiris-backend:<version> Osiris_backend

docker run -d --name osiris \
  -p 8000:8000 \
  -e OSIRIS_ENV=production \
  -e OSIRIS_JWT_SECRET="<secret>" \
  -e OSIRIS_WEBHOOK_SECRET="<secret>" \
  -e STRIPE_SECRET_KEY="<sk_…>" \
  -e STRIPE_WEBHOOK_SECRET="<whsec_…>" \
  -e STRIPE_PUBLISHABLE_KEY="<pk_…>" \
  -v osiris_data:/app \                # persist the SQLite file across restarts (pilot only)
  osiris-backend:<version>

# verify
curl -fs http://127.0.0.1:8000/healthz   # expect 200 {"status":"ok","migrations":"current",...}
```

A deploy is **healthy** only when `/healthz` returns 200 with `migrations: current`. If it
returns 503, read the JSON body: `db: down` (DB unreachable) or `migrations: behind` (the
image's migration head is ahead of the stamped DB — investigate before serving traffic).

## 4. Rollback

The migrations kept backward compatibility within Phase 0 (no destructive schema changes here),
so rollback is image-level:

```bash
docker stop osiris && docker rm osiris
docker run -d --name osiris ... osiris-backend:<previous-version>   # same env as §3
curl -fs http://127.0.0.1:8000/healthz
```

If a *future* deploy includes a migration, rollback order is:
1. Stop the new container.
2. `alembic downgrade <previous_head>` against the data volume (every migration must be
   reversible — this is a DBA red line in later phases).
3. Start the previous image.
Do not roll an image back past a migration without first downgrading the schema.

## 5. CI gate (what must be green before any deploy)

`.github/workflows/ci.yml` enforces, in order: ruff lint → mypy (advisory) →
fresh-DB migration → crystal-ledger reconciliation → test suites (ML referee, v2.10 flows,
Phase 2 security, Phase 3 Stripe payments) → OpenAPI contract drift check against
`Documentation/openapi.json` → image build → container boots and answers `/healthz`.
Nothing merges red.
