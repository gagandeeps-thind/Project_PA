# Osiris Enterprise Product Documentation

**Status:** Working baseline for product, engineering, operations, security, and counsel review  
**Date:** 2026-09-23  
**Scope:** Osiris health-improvement platform, starting with GPS-verified running challenges

This directory is the current startup-level source of truth for the next product direction. Existing prototype documents remain useful historical references; where they conflict with this package, the decision log and approved product requirements in this directory take precedence.

## Document map

| Document | Purpose |
|---|---|
| [01 Product Charter and PRD](01_Product_Charter_and_PRD.md) | Vision, personas, MVP boundaries, requirements, KPIs |
| [02 Current-State Gap Assessment](02_Current_State_Gap_Assessment.md) | Codebase audit against the target startup |
| [03 Domain and Economy Specification](03_Domain_and_Economy_Specification.md) | Route, challenge, rank, crystals, settlement, and unresolved economic decisions |
| [04 Architecture and Technical Strategy](04_Architecture_and_Technical_Strategy.md) | Target architecture, open-source stack, data model, APIs, reliability |
| [05 Security Privacy and Trust](05_Security_Privacy_and_Trust.md) | Threat model, privacy, anti-cheat, secure-by-default controls |
| [06 Delivery SDLC and Environment Promotion](06_Delivery_SDLC_and_Environment_Promotion.md) | Dev/SIT/UAT/PROD workflow, CI/CD, release gates, ownership |
| [07 End-to-End Delivery Backlog](07_End-to-End_Delivery_Backlog.md) | Sequenced implementation plan and acceptance gates |
| [08 Operations and Incident Runbook](08_Operations_and_Incident_Runbook.md) | Monitoring, support, incident response, rollback, and launch readiness |
| [09 Architecture Decision Records](09_Architecture_Decision_Records.md) | Decisions that prevent drift and re-litigation |

## Product north star

Osiris helps people improve their health by turning verified physical activity into a competitive, persistent world. A player records a real run, sees the route live, registers the completed course as a virtual territory, and opens that course to fair asynchronous challenges. Progression rewards consistency and performance; the system never treats health data, money, or physical safety as game abstractions.

## Non-negotiable launch principles

1. Launch with running/jogging only. Push-ups, squats, pose estimation, and live events are later product increments.
2. Any financial or competitive-value feature requires an explicit product, finance, and risk review before release.
3. Location and motion data are sensitive. Exact routes are private by default and public map views are deliberately generalized.
4. Server-authoritative state, append-only financial records, idempotent payments, and reproducible verification are required for production.
5. Safety beats engagement: no challenge design should encourage unsafe routes, traffic violations, dangerous weather exposure, or excessive exertion.
