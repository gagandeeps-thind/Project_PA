# Domain and Economy Specification

## 1. Canonical domain model

| Entity | Meaning |
|---|---|
| User | Account, consent, safety settings, progression identity |
| RunSession | One attempted physical activity with lifecycle and evidence |
| RoutePoint | Time-stamped location sample; raw access restricted |
| Course | Versioned normalized route/boundary registered from an accepted run |
| Challenge | Immutable terms published against a Course |
| Attempt | One user's participation in a Challenge |
| VerificationDecision | Rules/model outputs, evidence references, reason codes, reviewer state |
| Settlement | Idempotent outcome linking participants and ledger entries |
| CrystalLedger | Append-only closed-loop balance journal |
| AuditEvent | Security, admin, economy, and data-access trail |

## 2. State machines

### RunSession

`created → permissioned → active ↔ paused → submitted → verifying → accepted | rejected | review_required → closed`

No user or client may transition a session directly to accepted. A timeout, app crash, or upload retry must be safe and idempotent.

### Challenge

`draft → published → open → closed → settled | suspended | voided`

Published fields are immutable: course version, rules version, entry amount, time window, eligibility, privacy mode, and safety metadata. Corrections create a new challenge version.

### Attempt

`joined → started → submitted → accepted | rejected | review_required → won | lost | voided`

## 3. Verification policy for running MVP

The decision engine should combine, at minimum:

- server-received timestamps and monotonic client sequence numbers;
- GPS accuracy, sample continuity, impossible jumps, acceleration, and maximum speed thresholds;
- course start/finish boundary and route similarity to the course version;
- device clock skew and replay/idempotency key checks;
- OS location permission state and, where available, platform mock-location/device-integrity signals;
- optional accelerometer/cadence corroboration, never as the only source of truth;
- human review queue for borderline or financially material outcomes.

The result must include reason codes such as `ROUTE_CLOSED`, `GPS_ACCURACY_LOW`, `IMPOSSIBLE_SPEED`, `DUPLICATE_SUBMISSION`, or `REVIEW_REQUIRED`.

## 4. Progression

Use two separate concepts:

- **Performance rank:** Bronze, Silver, Gold, Platinum, Saint, Royal, Imperial, Divine. Thresholds are based on verified activity quality and consistency, not body size, BMI, gender, or protected characteristics.
- **Territory title:** Steward, Warden, Lord, High Lord, Sovereign. Based on accepted courses/territory under the published rules.

Ranks must be versioned, explainable, and protected from retroactive arbitrary changes. Health improvements are not guaranteed by rank; the product should encourage sustainable activity and rest.

## 5. Economy design guardrails

- Crystals are a server-controlled virtual unit; app-store policy, payments, tax, consumer-protection, and market requirements define permitted uses.
- The server owns pack prices, crystal issuance, debits, refunds, expiry policy, and settlement.
- No negative balances, hidden fees, or client-provided payout values.
- Every monetary/crystal transition is idempotent and reconciled against ledger totals.
- Minors and restricted jurisdictions are blocked from any paid competitive feature.
- A challenge displays the maximum possible cost, outcome treatment, refund/void policy, and platform fee before joining.

## 6. Unresolved economy decision

The request describes “the same amount,” “0.8%,” “1.8x,” and “0.3%,” but these values do not form a complete, mathematically consistent settlement and conflict with the existing 80/20 and 50/30/20 designs. No production implementation should infer the intended formula.

### Recommended launch-safe option

For the first pilot, use XP/badges and a fixed sponsor-funded reward pool. If crystals are tested, define their value, entry, refund, and platform-fee behavior in a separately approved product policy. This reduces financial ambiguity while validating the loop.

### Approval record required

Before enabling paid challenge entry, record:

- target markets and user eligibility;
- whether crystals are purchasable, withdrawable, transferable, or reward-bearing;
- exact integer settlement equation, including rounding and caps;
- tie, cancellation, injury, weather, GPS outage, fraud, and appeal rules;
- platform fee and tax treatment;
- product, payment processor, app-store, and insurance approvals;
- economic simulation results under collusion, botting, and mass-refund scenarios.
