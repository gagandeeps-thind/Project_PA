# Current-State Gap Assessment

## Executive conclusion

The repository is a useful prototype foundation, not yet the target startup product. It currently implements a fantasy fitness/bounty system with territory claims and sieges. The desired product is a verified running platform with first-class route sessions, public challenge discovery, and a defensible trust/economy layer.

## What aligns and should be retained

| Existing asset | Alignment | Direction |
|---|---|---|
| `Osiris_customer` Flutter app | Cross-platform mobile foundation; map, login, dashboard, bounty/domain surfaces exist. | Refactor around Run Session and Challenge flows. |
| FastAPI backend | Suitable for a modular monolith and ML integration. | Keep initially; split only at scale boundaries. |
| `Domain`, polygon closure, velocity checks | Useful spatial primitives for course registration. | Rename/reframe as Course/territory and harden with PostGIS. |
| `SiegeLog` and challenge resolution | Existing asynchronous competitive pattern. | Replace unclear siege semantics with versioned Challenge and Attempt. |
| Crystal ledger and Stripe adapter | Correct direction for server-authoritative accounting. | Preserve append-only design; complete the product, finance, and risk review for competitive value. |
| Telemetry and ML referee | Valuable for verification and future model training. | Separate run route verification from exercise pose verification. |
| CI, migrations, healthz, tests | Good engineering baseline. | Expand into four-environment promotion gates. |

## Key mismatches and blockers

| Area | Current state | Target gap | Priority |
|---|---|---|---|
| Product model | Bounties, domains, sieges, merchant chests. | Run, Course, Challenge, Attempt, Settlement. | P0 |
| Tracking | Existing client location service and polygon submission concept. | Durable run session lifecycle, sampling policy, offline queue, route versioning. | P0 |
| Verification | Heuristics accept client-submitted sensor proofs; audit identifies bypass risk. | Signed evidence, device integrity signals, server route reconstruction, review state. | P0 |
| Map privacy | Historical audit identifies unauthenticated exact territory exposure. | Authenticated/coarsened public map, owner privacy, safe-zone policies. | P0 |
| Economy | Conflicting 80/20, 50/30/20, and user-described percentages. | One approved settlement formula and immutable challenge terms. | P0 |
| Data model | SQLite-friendly scalar JSON geometry. | PostgreSQL/PostGIS, spatial indexes, event/audit records. | P0 before money |
| Authentication | JWT exists; prior audit notes revocation/rotation gaps. | Short-lived access tokens, refresh rotation, device sessions, revocation. | P0 |
| Privacy | Good analysis exists; implementation is incomplete. | Consent ledger, export, deletion/anonymization, retention enforcement. | P0 |
| Operations | Single-container pilot runbook and CI exist. | Separate Dev/SIT/UAT/Prod, secrets, backups, SLOs, alerting, DR. | P1 |
| Frontends | Customer, merchant, admin are separate but incomplete. | Customer-first MVP; admin trust console; defer merchant until validated. | P1 |
| Live events | Conceptual only. | Event operations and safety program. | P3 |

## Existing documentation conflicts to resolve

1. Rank names vary between physical grade, peerage, and user-requested bronze/silver/gold. Use one product-facing ladder and keep territory titles separate.
2. Economy percentages differ across `Imp_and_US.md`, current backend constants, and the new request. Do not code new settlement until [03](03_Domain_and_Economy_Specification.md) decision D-ECON-001 is approved.
3. Older documents describe UK GDPR for a Nova Scotia pilot. The current privacy baseline should be PIPEDA/Canadian privacy counsel-led, with a reusable extension for other regions.
4. BMI/avatar logic is not a health or fitness truth and should not drive rank or user treatment.
5. “ML verified” is stronger than the current client-supplied heuristic evidence supports. Product copy must say “verified under current checks” until the anti-cheat evidence chain is strengthened.

## Recommended immediate code sequence

1. Freeze new siege/bounty features.
2. Add route-session and challenge domain models alongside existing models.
3. Move the backend to PostgreSQL/PostGIS in SIT before real-money testing.
4. Close the audited authentication, map privacy, CORS, rate-limit, and consent gaps.
5. Build and instrument a non-stakes verified-run pilot.
6. Activate a controlled crystal experiment behind a feature flag after the product and risk review.
