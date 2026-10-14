# Architecture and Technical Strategy

## 1. Recommended architecture

Start as a modular monolith with explicit service boundaries. This keeps the team fast while protecting future extraction points.

```text
Flutter Customer App ─┐
Admin Web Console ────┼─ HTTPS/API ── FastAPI Modular Backend
                     │                    ├─ Identity & Consent
                     │                    ├─ Run/Route Ingestion
                     │                    ├─ Verification & Review
                     │                    ├─ Course/Challenge
                     │                    ├─ Progression
                     │                    ├─ Economy/Ledger
                     │                    └─ Notifications
                     │                         │
                     └────────────── PostgreSQL + PostGIS
                                           Object storage (encrypted)
                                           Redis (rate limits/jobs)
                                           OpenTelemetry/Prometheus/Grafana
```

## 2. Open-source/free-first stack

| Layer | Baseline | Notes |
|---|---|---|
| Mobile | Flutter/Dart | Existing customer app; secure storage and platform location plugins |
| Web admin | React + TypeScript + Vite | Existing admin foundation |
| API | Python 3.13 + FastAPI + Pydantic | Existing backend; modular packages required |
| Database | PostgreSQL + PostGIS | Spatial queries, constraints, backups, mature ecosystem |
| Cache/jobs | Redis + Celery/RQ or PostgreSQL-backed worker | Keep settlement jobs durable and observable |
| Migrations | Alembic | Existing; every migration reviewed and tested from zero |
| Maps | MapLibre GL + OpenStreetMap-compatible provider | Provider terms, tile load, attribution, and privacy reviewed before scale |
| ML/CV | MediaPipe Tasks / ONNX Runtime / scikit-learn | On-device first; model registry and evaluation later |
| Observability | OpenTelemetry, Prometheus, Grafana, Loki/Vector | Self-hostable; redact location and secrets |
| Security | Argon2id/bcrypt compatibility, libsodium, dependency scanners, Semgrep, Trivy | Defense in depth; no claim of absolute security |
| Deployment | Docker + Compose for local, Kubernetes or managed containers later | Use the simplest production platform with backups and isolation |

“Open-source and free” does not mean zero operational cost or automatically secure. Maps, email, payment, storage, hosting, app stores, backups, and incident response still have cost and supplier risk.

## 3. API direction

Add a new `/api/v2` contract rather than overloading legacy endpoints.

| Endpoint | Purpose |
|---|---|
| `POST /api/v2/runs` | Create run session |
| `POST /api/v2/runs/{id}/start` | Start after permission/start-zone checks |
| `POST /api/v2/runs/{id}/points` | Chunked signed route telemetry |
| `POST /api/v2/runs/{id}/finish` | Submit completion with idempotency key |
| `GET /api/v2/runs/{id}` | Status and safe summary |
| `POST /api/v2/courses` | Register accepted run as course proposal |
| `GET /api/v2/challenges/nearby` | Coarsened challenge discovery |
| `POST /api/v2/challenges` | Publish challenge |
| `POST /api/v2/challenges/{id}/join` | Join with immutable terms snapshot |
| `POST /api/v2/challenges/{id}/attempts` | Link a run to an attempt |
| `GET /api/v2/me/export` | Data export |
| `POST /api/v2/consents` | Versioned consent decision |

All mutation endpoints require authorization, idempotency where retriable, server timestamps, audit events, and structured error codes.

## 4. Data and reliability rules

- PostGIS stores normalized geometry; raw route samples live in encrypted object storage or partitioned tables with TTL.
- Public map responses never include exact owner identity, vault balance, or exact private route unless the user is authorized.
- Use database transactions and row locks for wallet/settlement operations.
- Outbox events guarantee notifications and settlement workers do not lose state.
- Backups are encrypted, tested, and restored in UAT on a schedule.
- Partition high-volume route/telemetry data by time and apply retention policies.

