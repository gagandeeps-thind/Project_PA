# Operations and Incident Runbook

## 1. Minimum production observability

- API availability, latency, error rate, saturation, database health, queue lag, and storage growth.
- Run acceptance/rejection/review rates by verifier version and geography.
- Ledger debit/credit totals, reconciliation failures, duplicate webhook attempts, refunds, and chargebacks.
- Auth failures, refresh-token reuse, admin actions, export/delete volume, and suspicious route clusters.
- Mobile crash-free sessions, location permission denial, upload retry, battery impact, and offline queue age.

## 2. Severity model

| Severity | Example | Response |
|---|---|---|
| SEV-1 | Ledger duplication, mass privacy leak, account takeover, unsafe event | Page immediately; freeze affected feature; incident commander |
| SEV-2 | Challenge settlement wrong for a cohort, major API outage, route privacy issue | Respond during business hours; feature flag/rollback |
| SEV-3 | Individual verification dispute, degraded map, non-critical admin bug | Ticket and normal engineering response |

## 3. First response

1. Open incident record and assign incident commander, technical lead, communications lead, and privacy/finance lead as needed.
2. Preserve logs, audit events, database snapshots, webhook payload IDs, and deployment metadata.
3. Stop further harm with feature flags, challenge suspension, account/session revocation, or payment disablement.
4. Determine affected users, time window, data/economic impact, and whether legal notification is required.
5. Communicate only verified facts; do not expose private routes or raw health telemetry in tickets.
6. Restore service from known-good release or replay idempotent jobs after approval.
7. Complete root-cause analysis, user remediation, tests, and a blameless postmortem.

## 4. Backup and disaster recovery

- Encrypted PostgreSQL backups with point-in-time recovery in production.
- Object-storage versioning and lifecycle policies for raw evidence.
- Restore drill at least quarterly and after major schema/economy changes.
- Target pilot RPO ≤15 minutes and RTO ≤2 hours; validate against actual hosting plan.
- Never restore production data into an internet-accessible lower environment.

## 5. Operational launch checklist

- [ ] On-call schedule and escalation contacts exist.
- [ ] Health checks, dashboards, and alerts have been exercised.
- [ ] Rollback artifact and migration plan are tested.
- [ ] Support scripts explain accepted/rejected/review-required outcomes.
- [ ] Privacy requests and security incidents have owners and templates.
- [ ] Paid features remain behind feature flags until the documented finance, payment, app-store, privacy, and risk review is complete.
