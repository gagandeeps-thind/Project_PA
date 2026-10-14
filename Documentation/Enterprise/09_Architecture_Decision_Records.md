# Architecture Decision Records

## ADR-001 — Modular monolith first

**Decision:** Keep FastAPI as a modular monolith with explicit domain packages until scaling or team boundaries justify extraction.  
**Reason:** The team needs fast product learning, while route verification, challenge state, and ledger transactions benefit from local consistency.  
**Consequence:** Enforce package boundaries and contract tests now; do not share ORM writes casually.

## ADR-002 — PostgreSQL/PostGIS before paid production

**Decision:** SQLite remains a local/dev convenience only. SIT onward uses PostgreSQL/PostGIS.  
**Reason:** concurrent settlement, spatial queries, constraints, backups, and restore operations exceed the safe SQLite envelope.  
**Consequence:** Migration and integration work is required before real-money testing.

## ADR-003 — Running is the first-class MVP activity

**Decision:** The first commercial product increment is GPS-verified running/jogging.  
**Reason:** It matches the clearest user vision and existing location/map foundation. Pose estimation is deferred until route trust and retention are proven.

## ADR-004 — Privacy-safe public map

**Decision:** Public discovery exposes challenge abstractions, not owner identity, vault balances, or exact private route history.  
**Reason:** repeated routes can reveal homes, workplaces, and routines. Privacy is a product requirement, not an optional hardening task.

## ADR-005 — No inferred economy percentages

**Decision:** The implementation team must not infer or ship the requested 0.8%, 1.8x, or 0.3% mechanics.  
**Reason:** the values are ambiguous, mathematically incomplete, and legally material.  
**Consequence:** use non-stakes or sponsor-funded pilot rewards until the settlement equation is approved and versioned.

