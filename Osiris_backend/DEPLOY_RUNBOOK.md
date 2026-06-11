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
| `OSIRIS_WEBHOOK_SECRET` | always in prod (fatal if missing) | payment webhook signature key |
| `OSIRIS_ENV` | prod | set to `production` to enforce the two secrets above at boot |
| `OSIRIS_LOG_JSON` | containers | `1` → structured JSON access logs |
| `OSIRIS_LOG_LEVEL` | optional | default `INFO` |
| `OSIRIS_TELEMETRY_TTL_DAYS` | optional | raw-sample retention; `0` disables purge |

Generate a JWT secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

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
fresh-DB migration → both test suites → image build → container boots and answers `/healthz`
→ OpenAPI contract drift check against `Documentation/openapi.json`. Nothing merges red.
