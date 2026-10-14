# Delivery SDLC and Environment Promotion

## 1. Environment topology

| Environment | Purpose | Data | Deployment |
|---|---|---|---|
| Dev | Local feature development | Synthetic/local only | Docker Compose; no production secrets |
| SIT | Integrated system testing | Synthetic seeded data | Automatic from main after CI |
| UAT | Product, support, privacy, and business acceptance | Sanitized/synthetic; controlled pilot users only | Manual approval from release candidate |
| PROD | Real users | Production data | Two-person approval; progressive rollout |

Each environment has separate database, storage bucket, Redis, signing keys, payment account/mode, maps configuration, and admin identities. Never copy production data into Dev/SIT/UAT.

## 2. Branch and change policy

- Short-lived feature branches; pull request required.
- Required reviewers: code owner plus product/security reviewer for identity, location, economy, or privacy changes.
- Conventional commits and semantic versioning.
- Database migrations are forward-compatible, reversible where safe, and tested from an empty database.
- Feature flags gate paid economy, public challenges, ML models, and live events.

## 3. CI pipeline

1. Format/lint/type checks.
2. Unit tests and property tests for spatial/ledger logic.
3. API contract/OpenAPI drift check.
4. Migration-from-zero and migration-upgrade tests.
5. Integration tests with PostgreSQL/PostGIS and Redis.
6. Security checks: secret scan, dependency audit, SAST, image scan.
7. Build mobile/web/backend artifacts reproducibly.
8. Deploy ephemeral SIT candidate and run smoke/e2e tests.
9. Publish signed artifact and release notes.

## 4. Promotion gates

### Dev → SIT

CI green, tests cover changed paths, migration reviewed, no critical security findings, telemetry/privacy tests green.

### SIT → UAT

End-to-end run/challenge flow passes; failure/retry/offline cases pass; observability dashboards and alerts exist; test data reset procedure verified.

### UAT → PROD

Product owner acceptance, support playbook ready, backup/restore test green, security/privacy sign-off, performance budget met, rollback image identified, feature flags disabled for unapproved economy.

## 5. Release strategy

- Backend: canary or percentage rollout with backward-compatible migrations.
- Mobile: staged store rollout and remote kill switch.
- Economy: dark launch ledger events in test mode, then capped pilot cohort, then expansion only after reconciliation.
- Every release records commit SHA, migration head, config version, feature flags, verifier version, and approvers.

