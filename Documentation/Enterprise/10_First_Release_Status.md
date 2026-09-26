# First Release Implementation Status

**Release slice:** R0/R1 — verified running foundation  
**Status:** Backend and customer-app integration implemented; challenge publishing and paid economy remain outside this release slice.

## Delivered

- `RunSession`, `RoutePoint`, and `VerificationDecision` persistence models.
- Alembic migration `7c2a4b1d9e01_add_run_sessions.py`.
- Authenticated `/api/v2/runs` create/start/points/finish/status endpoints.
- Contiguous route sequence enforcement and finish idempotency.
- Server-authoritative distance, duration, speed, gap, accuracy, and route-hash calculation.
- Explainable rejection reason codes and immutable verification records.
- Accepted-run XP and endurance progression.
- Customer API client methods and map-screen start/finish run integration.
- OpenAPI contract regenerated.
- Direct regression coverage for accepted runs, rejected routes, authentication, and retries.

## Verification completed

- New run-release regression suite: passing.
- ML referee suite: passing.
- Phase 2 security suite: passing.
- Crystal ledger suite: passing.
- Replay guard suite: passing.
- Party statistics suite: passing after updating it for authenticated access.
- v2.10 flow suite: passing.
- Stripe suite: passing.
- Ruff checks on changed backend files: passing.
- Clean Alembic migration from zero: passing.
- Existing local database upgraded to the new migration head: passing.
- Flutter/Dart analyzer did not complete within the available execution window; run `flutter analyze` in the Flutter development environment before publishing a mobile build.

## Known next release items

- Durable mobile offline route queue with retry persistence.
- Course registration and challenge lifecycle APIs.
- Privacy-safe challenge map responses replacing legacy exact-domain exposure.
- PostgreSQL/PostGIS integration for SIT and production.
- Refresh-token rotation, admin MFA, and production observability expansion.

