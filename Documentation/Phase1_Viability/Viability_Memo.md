# Osiris — Phase 1 Viability Memo

| Field | Value |
| :--- | :--- |
| **Document Type** | Viability memo (PM + Game Economist + Compliance panel) |
| **Phase** | Phase 1 — "Can this legally and financially exist?" |
| **Date** | 2026-06-11 |
| **Authors** | Principal PM · Principal Game Economist · Senior Compliance & Privacy Analyst (combined panel) |
| **Operating rule** | **Truth over agreement.** Uncertainty is stated as a finding. |
| **Disclaimer** | **No section of this document concludes legality.** It is structured input for a licensed gaming/payments lawyer and a privacy counsel. Where this memo says "likely gambling" it means "likely to require a lawyer's gambling analysis," not a legal conclusion. |
| **Companion deliverables** | `Gambling_Analysis_Matrix.md` · `Counsel_Question_List.md` · `Privacy_Build_List.md` |

---

## 0. Source-fidelity note (read first)

`Documentation/Osiris_Master_Spec.md` was **intentionally deleted by the operator**. This memo reconstructs the business model and economy constants from three surviving sources: `Deep_Audit_2026-06.md`, `Imp_and_US.md` (a GDD/TDD that carries the v2.x economy text), `User Story.md`, `MVP_plan.md`, and the committed `Documentation/openapi.json` contract. Every constant below is tagged with where it came from. **Facts that could not be found in any provided file are listed explicitly in §7 — they are NOT invented.**

---

## 1. Executive Summary

Osiris is a real-world fitness Action-RPG: players trace GPS polygons to claim territory, defend it with a "Vault" of Mana Crystals, and besiege each other's land. Today (Phase 1 MVP), **all crystals are virtual** — starter balance 100, no purchase path, no cash-out path exists anywhere in the code or the API contract (confirmed: `openapi.json` has no buy/convert/withdraw endpoint; `pilot_fee_cents` is the only money field, and it is B2B). In this state the product is a **virtual-currency game**, not gambling.

The viability question is entirely about **Phase 2**, where the spec states plainly (`Imp_and_US.md` §4.4): *"Mana Crystals become convertible to real-world currency."* The moment crystals are convertible **and** players stake them on a contested outcome **and** the platform rakes 20%, three independent legal regimes attach at once:

1. **Gambling / gaming control law** — the siege and Challenge-Board mechanics map onto the classic **consideration + chance + prize** test. The panel's honest read: at least one core mechanic (the head-to-head wager) is **gambling-adjacent enough that it cannot launch without a licensed gaming lawyer's sign-off.** We do not conclude it *is* gambling; we conclude it is squarely in the zone where only counsel may.
2. **Payments / money-services law** — convertible crystals that move between users and out to cash implicate money-transmission / MSB-style obligations and KYC/AML. Stripe lists real-money gaming as a **restricted/pre-approval business**; shipping on Stripe without disclosure risks account termination and frozen funds.
3. **Privacy law** — the pilot runs in **Bedford, Nova Scotia**, on ~50 real people, capturing continuous GPS + motion telemetry. The spec's "UK GDPR" framing is **wrong for this population** (see `Privacy_Build_List.md`); **PIPEDA + Nova Scotia law govern the actual pilot**, and the obligation attaches at tester #1, not at scale.

**Panel verdict on the core tension:** the product's "**earn a daily livelihood**" pillar is the single most expensive promise in the spec. Every design that delivers a *real* livelihood (cash-convertible, player-vs-player, raked) is the design most likely to be classified as gambling and to trigger money-services obligations. Every design that *de-risks* the legal classification (non-convertible currency, skill-only entry-fee contests, sweepstakes) **erodes or eliminates the livelihood pillar.** You cannot maximize both. This memo ranks three options on exactly that trade-off.

**Bottom line:** Phase 1 MVP (virtual-only) can proceed to a supervised Bedford pilot **on privacy grounds being fixed** (consent/export/delete + correct PIPEDA framing — these block Phase 2 and should land before real testers' data is ML-retained). Phase 2 real-money **cannot** proceed without (a) a licensed gaming lawyer's written classification, (b) the append-only player ledger (audit §3.2), and (c) device attestation (audit §2.3) — the three gates the Agent Charter already names as the "money gate." This memo is the input to gate (a).

---

## 2. The mechanic under analysis (stated precisely, so counsel can rule on it)

Reconstructed from `Imp_and_US.md` §4.4–4.7, `User Story.md` Epic 5, and `openapi.json` (`/sieges/{id}/resolve`, `/domains/{id}/vault`):

- **Siege (paid tier):** Defender locks crystals into a **Vault**. A challenger must (a) geographically encapsulate the defender's polygon, (b) **match** the vault amount as a Challenge Fee, and (c) beat the defender's "Defense Feat" Ghost score (a verified exercise count).
  - **Win:** pot = defender vault + challenger match. Winner takes **80%**; platform keeps **20% "War Tax."** Defender's land erased, vault forfeited.
  - **Loss:** challenger's match splits **50% to defender vault / 30% to platform / 20% banked as a single-use retry-discount** vs. the same domain.
- **Challenge Board (head-to-head wager, `Imp_and_US.md` §4.7):** Player A posts a verified exercise count + a crystal wager. Player B matches and tries to beat it. Winner takes the pot **minus 20% War Tax.**

**The chance vector that matters for counsel:** the spec and audit both state the outcome is **not purely skill.** The audit (§2.3) documents that the "verified score" is computed from **client-supplied sensor data** through a heuristic referee that is *"trivially bypassable"* and *"defense-in-depth theatre against a determined actor."* So the winner is determined partly by exercise performance (skill) and partly by **referee error, GPS variance, device/sensor quality, and exploitability** — i.e., factors outside the honest player's control. **Whether that residual is enough "chance" to fail a skill-game exemption is the central question for the gaming lawyer.** The panel flags it; the panel does not resolve it.

---

## 3. Three economy-design options, ranked by regulatory risk (lowest → highest)

> Ranking is **by regulatory risk**, ascending. The livelihood pillar moves inversely.

### Option A — Non-convertible reward currency + sweepstakes overlay (LOWEST regulatory risk)

**Design:** Crystals stay **virtual and non-cashable forever** (as in today's MVP). Real value reaches players only through **merchant coupons** (already built: `/coupons/{code}/redeem`) and an optional **"no-purchase-necessary" sweepstakes** for periodic prizes, run to documented sweepstakes rules. No player-to-player cash flow. Sieges and Challenge Board remain crystal-only with no exit to cash.

- **Consideration:** none for cash purposes — crystals are earned, not bought-to-cash-out. (If crystals become *purchasable*, a free alternative-method-of-entry must exist for any sweepstakes — counsel item.)
- **Chance/Prize:** the prize is not money; the staked thing has no cash value. This is the standard **"virtual goods with no real-world value"** posture most fitness/F2P games rely on.
- **Regulatory posture:** Lowest. Avoids the gambling consideration-chance-prize trifecta because the **prize is not money or money's-worth** in the player-vs-player loop. Sweepstakes is a well-trodden compliance path with known rules. Payments exposure drops to ordinary card processing (coupon/B2B), not money transmission.
- **Cost to the livelihood pillar:** **Severe / near-fatal to it as written.** "Earn a daily livelihood" becomes "earn coupons + occasional sweepstakes prizes." This is the **product repositioning the Playbook's Phase-1 kill condition explicitly anticipates** (virtual economy + B2B merchant revenue). Honest framing: this keeps Osiris shippable and largely de-risked, at the cost of the headline promise.

### Option B — Entry-fee skill contest (paid tournament model) (MEDIUM regulatory risk)

**Design:** Reframe sieges/challenges as **skill contests with a fixed entry fee and a guaranteed prize pool**, where the platform's cut is an **administration fee, not a rake on a wager.** Emphasize and *engineer* skill dominance: remove or heavily dampen the chance vectors (deterministic scoring, attestation-hardened referee, published rubric), because the **skill-contest exemption lives or dies on "predominantly skill."**

- **Consideration:** present (entry fee). Many skill-contest carve-outs **permit** consideration *if* the outcome is predominantly skill and the prize is fixed/announced.
- **Chance:** must be driven **down** to qualify. This is where the audit's "referee is bypassable / GPS variance" findings become a **legal blocker, not just a security one** — uncontrolled chance pushes this back toward Option C's classification.
- **Prize:** real money / cash-equivalent — so the livelihood pillar partially survives.
- **Regulatory posture:** Medium, and **jurisdiction-sensitive.** Skill-game definitions vary sharply by market (the matrix flags "predominant purpose" vs. "any chance / material element" tests). Requires per-market counsel opinion. Provincial gaming control in NS and the federal Criminal Code Part VII both bear on this.
- **Cost to the livelihood pillar:** **Partial.** Players can win cash from skill contests, but the head-to-head *wager* framing must be abandoned for an *entry-fee/prize-pool* framing, and the platform economics change from "20% rake on every stake" to "admin fee on entries." Solvency math (see §6) shifts accordingly.

### Option C — Convertible-crystal head-to-head wager + 20% rake (HIGHEST regulatory risk — the spec's current Phase-2 design)

**Design:** Exactly what `Imp_and_US.md` §4.4/§4.7 describe: crystals convertible to cash, players stake them head-to-head, platform rakes 20%.

- **Consideration:** present and unambiguous (convertible crystals staked).
- **Chance:** present as a *material element* (referee error, sensor/GPS variance, exploitability — §2). Even if skill predominates, a **material-element** market would still classify this as gaming.
- **Prize:** real, convertible money.
- **Regulatory posture:** **Highest.** This is the **textbook three-element configuration.** The panel's honest assessment: in most plausible markets this lands in **"licensed gaming operator" territory**, which means a licence, regulated-operator obligations, KYC/AML, segregated player funds, responsible-gambling controls, and a payments stack built for gaming. A 20% rake is itself an operator economics signal.
- **Cost to the livelihood pillar:** **Fully delivers it** — and is the only option that does. It is also the option most likely to **trigger the Playbook kill condition** ("if you are unwilling to license or redesign, the livelihood pillar is dead").

**Panel recommendation (advisory, not legal):** Take **all three** to counsel, but build the pilot on **Option A** and treat **Option B** as the only path that preserves *any* livelihood promise without becoming a licensed operator. Option C should be costed as "become a regulated gaming operator" before any engineering, because that is what it is.

---

## 4. One page — "What must be true to launch real money"

This is the launch gate. Every line must be **closed in writing** before the first convertible-crystal transaction.

**Legal classification (the input this memo feeds):**
1. A **licensed gaming lawyer** has classified the chosen variant (A/B/C) under **Nova Scotia provincial gaming control law + Criminal Code Part VII (federal)** and the chosen target markets — *in writing*.
2. If the answer is "gaming/gambling": a decision is made and signed to **either license, redesign to a lower-risk option, or geo-restrict** to permissive markets. The 20% rake is explicitly reviewed against operator rules.
3. The "**outcome partly outside the player's control**" question (referee bypassability, GPS variance) has a documented legal opinion on whether it defeats any skill-game exemption.

**Payments & financial-crime:**
4. **Stripe (or alternative) gaming/real-money pre-approval** obtained in writing, with the business correctly categorized — not slipped through as generic SaaS.
5. **KYC/AML program** scoped: a lawyer has determined whether convertible crystals make Osiris a money-services business / money transmitter in each market, and if so the registration + identity-verification + transaction-monitoring obligations are in place.
6. **Chargeback model** for siege/wager losses defined: what happens when a losing challenger disputes the card charge that funded their crystals after the crystals were already lost in a siege.

**Engineering money-gate (from the Agent Charter — non-negotiable, independent of legal):**
7. **Append-only player crystal ledger** exists (audit §3.2 — does not exist today; `mana_crystals` is a mutable integer). Balance is *derived*, every movement is a ledger row.
8. **Device attestation** (Play Integrity / App Attest) gates all money-bearing actions (audit §2.3 — does not exist today).
9. The **payment-forgeability exploit is fixed** (audit §2.1 — webhook fails *open* today and the merchant app ships a self-activation button). Real money cannot ride on a fail-open webhook.

**Privacy (must be true before real testers, let alone real money):**
10. Correct **PIPEDA / NS** framing, consent capture, export + delete endpoints, and a **separate consent basis for ML training** (see `Privacy_Build_List.md`).
11. Players are **18+** screened (Playbook §6 gate — a wagering + location product has zero room for minors).

**If lines 1–3 come back "this is licensed gambling and you won't license":** invoke the Playbook kill condition — reposition on Option A (virtual + B2B) **before** any further money-path engineering. Knowing this now is the entire point of Phase 1.

---

## 5. Single biggest legal risk (panel's one-line answer)

**The Phase-2 convertible-crystal, player-vs-player, 20%-rake siege/wager mechanic is the textbook consideration-chance-prize configuration, and the audit's own finding that the "verified score" is computed from bypassable client sensor data injects a material chance element that a player cannot control — which is precisely the fact pattern that turns a "skill game" into regulated gaming.** It cannot be resolved by this panel; it must go to a licensed gaming lawyer, and it gates the entire money layer.

---

## 6. Unit Economics — Pilot P&L (qualitative + symbolic)

> **Hard constraint honored:** the provided files do **not** contain crystal purchase price, crystal→cash conversion rate, dungeon-entry costs, Tower Pass take in the pilot, or a defined merchant pilot-fee *count*. The MVP plan says **$50/merchant** and a **weekly revenue target of ~$250+**; `openapi.json` exposes `pilot_fee_cents` but **no default value**. Everything below that depends on missing constants is modeled **symbolically** and flagged.

### 6.1 Revenue (pilot is B2B-only in practice)

In the **virtual-only pilot** there is **no B2C cash revenue** — crystals don't convert, so War Tax/Black Market/Tower Pass produce *virtual* crystals, not dollars. Real pilot inflow is **merchant pilot fees only**:

- Let **M** = number of paying merchants, **f** = pilot fee (docs: **f ≈ $50 CAD**, "per weekend"), **w** = weekends a merchant pays.
- **Pilot gross revenue ≈ M × f × w.**
- MVP target of **$250+/week** implies **M × w ≥ 5 merchant-weekends** at $50. With a ~50-tester single-park pilot, **M is realistically low single digits** — finding even 5 paying Bedford merchant-weekends is the binding constraint, not the math.

### 6.2 Costs

- **Infra (I):** trivial at pilot scale — one small VM, SQLite→(eventually)Postgres, MediaPipe is **on-device** (no server GPU). Order of **tens of dollars/month**. Not the cost that matters.
- **Acquisition (A):** ~50 testers in one neighborhood — assume **near-zero paid CAC** (founder-led, local, word of mouth). Realistic pilot reality.
- **The dominant cost is not infra or CAC — it is Phase-2 legal spend (L):** the gaming-lawyer classification, payments pre-approval, and privacy review. This is **lumpy, upfront, and the entire reason Phase 1 exists.**

### 6.3 Qualitative P&L verdict

The pilot **does not and is not meant to make money.** `Pilot P&L ≈ (M·f·w) − I − A`, which is roughly **break-even-to-slightly-positive at best** ($250/wk gross vs. negligible infra), and that ignores the founder's time. **The pilot's product is data and de-risking, not profit.** The economic decision is therefore *forward-looking*: **is the Phase-2 legal spend (L) justified by the value of the validated loop?**

### 6.4 What retention/redemption numbers make Phase-2 legal spend worthwhile

Spend **L** on lawyers only if the pilot proves the loop is worth a real-money business. The panel's threshold tests (the numbers Phase 6 growth instrumentation must produce — `D1/D7/D30`, bounty completion, claim-to-siege conversion, merchant redemption):

1. **Retention:** **D7 ≥ ~25–30% and D30 ≥ ~10–15%** on the *core* loop (claim → defend → siege), measured on the ~50 cohort. Below this, there is no economy to regulate — you'd be paying lawyers to legalize a game nobody returns to.
2. **Merchant redemption:** **coupon redemption rate ≥ ~15–20%** of issued coupons AND **≥ 1 merchant renewing** the pilot fee unprompted. Merchant willingness to *re-pay* is the only validated dollar in the building; without renewal, Option A (the B2B-funded reposition) has no engine.
3. **Loop engagement, not just login:** **claim-to-siege conversion high enough that the PvP economy actually circulates** (sieges per active player per week ≥ ~1). If players claim land but never siege, the convertible-wager economy (Option C) has no volume to rake — and you'd be buying a gaming licence for a feature nobody uses.

**Solvency caveat for Option C specifically (Game Economist):** a head-to-head, zero-sum-minus-20%-rake loop **drains**: aggregate player crystals strictly decrease by the rake every cycle unless **new cash inflow** (purchases) replaces it. The required inflow rate to keep the pool from draining is a **function of rake (20%), churn, and average stake** — all three of which are **not specified in the provided files** (no crystal price, no churn data, no average stake). This is modeled symbolically and flagged in §7. **Do not greenlight Option C without a solvency model** built on real pilot stake/churn data — the Agent Charter (Role 14) red-lines exactly this.

---

## 7. Facts NOT found in the provided files (reported as gaps, not invented)

| # | Missing fact | Why it matters | Where it would normally live |
| :-- | :--- | :--- | :--- |
| 1 | **Crystal → cash conversion rate** | The entire gambling/payments analysis hinges on crystals having defined cash value. | Deleted `Osiris_Master_Spec.md` §6.2 (economy constants) |
| 2 | **Crystal purchase price** (cash → crystals) | Needed for solvency math (inflow rate) and for MSB/consideration analysis. | Same |
| 3 | **Merchant pilot-fee default value** | `openapi.json` has `pilot_fee_cents` with no default; docs say "$50" in prose only. | Spec / config |
| 4 | **Target markets beyond NS/Canada** | The Playbook asks for "top 3 target markets"; no file names them. The matrix **states assumptions** rather than inventing facts. | Deleted spec / business plan |
| 5 | **Dungeon entry cost, Tower Pass pilot economics, Black Market 15% fee mechanics** | Mentioned as B2C streams but no constants given for solvency modeling. | Deleted spec §5 |
| 6 | **Average stake / churn / current retention data** | Required to turn the symbolic solvency model into a real one. | Not yet measured (pre-pilot) |
| 7 | **Age-gate / 18+ enforcement mechanism** | Playbook §6 names it as a gate; no onboarding age field confirmed in the surviving stories (onboarding captures height/weight/age — *age is captured*, but no 18+ block is documented). | Onboarding spec |

---

## 8. Handoffs

- **To a licensed gaming/payments lawyer:** `Gambling_Analysis_Matrix.md` + `Counsel_Question_List.md`. Scoped to bill in ≤2 hours.
- **To the Backend agent (Phase 2/5):** `Privacy_Build_List.md` — the consent/export/delete/anonymization build, with the PIPEDA-not-UK-GDPR correction flagged.
- **To Gagan (operator):** the §4 launch gate and the §3 option ranking. The decision the panel cannot make for you: **do you license/redesign (Option C), reframe to skill-contest (Option B), or reposition to virtual + B2B (Option A)?**
