# Osiris — Gambling Analysis Matrix (Decision Aid for Licensed Counsel)

| Field | Value |
| :--- | :--- |
| **Document Type** | Decision matrix **for a licensed gaming lawyer** |
| **Date** | 2026-06-11 |
| **Prepared by** | Senior Compliance & Privacy Analyst (with PM + Economist panel) |
| **Status** | **DRAFT INPUT — NOT A LEGAL CONCLUSION** |

---

## CRITICAL DISCLAIMER (read before the matrix)

**This document does not conclude that any Osiris mechanic is or is not gambling.** The author is **not** a lawyer and explicitly does **not** opine on legality. This matrix exists to (a) decompose each design variant against the standard **consideration / chance / prize** test so a licensed gaming lawyer can rule efficiently, and (b) state, **per cell**, the author's own uncertainty so counsel knows exactly where the soft ground is. Every "likely classification" cell is a **hypothesis to be tested by counsel**, never a finding.

---

## 0. The mechanic being mapped (precise restatement)

From `Imp_and_US.md` §4.4–4.7, `User Story.md` Epic 5, `openapi.json` (`/sieges/{id}/resolve`, `/domains/{id}/vault`):

> Players stake a **convertible** currency (Mana Crystals, Phase 2). An outcome **partly outside their control** (the "verified score" is computed by a heuristic referee from client-supplied sensor data that the project's own audit calls *"trivially bypassable"* — `Deep_Audit_2026-06.md` §2.3) picks a winner. The platform **rakes 20%** ("War Tax").

The chance element is **load-bearing for the entire analysis** and is sourced from the project's own audit, not assumed.

---

## 1. Stated assumptions (so counsel can correct them)

1. **Phase-2 convertibility is real.** Today crystals are non-convertible (no buy/convert/withdraw endpoint exists in `openapi.json`). The matrix analyzes the **Phase-2** state the spec describes, where crystals convert to cash. If convertibility is dropped, the "prize" column collapses for most rows.
2. **Top-3 target markets are NOT specified in any provided file.** The Playbook asks for them; no surviving document names them. **The author refuses to invent them.** As a *placeholder for counsel to replace*, the matrix uses three **assumed** market archetypes by legal test, not by named country/state:
   - **Market α — "Predominant-purpose / dominant-factor skill test"** jurisdiction (skill game legal if skill predominates).
   - **Market β — "Any-chance / material-element test"** jurisdiction (any material chance element = gambling).
   - **Market γ — Canada federal + Nova Scotia provincial** (Criminal Code Part VII + provincial gaming control; the actual pilot home).
   - **→ Counsel action:** replace α/β/γ with the three real target markets once the business names them (see `Counsel_Question_List.md` Q1).
3. **"War Tax" 20% is a rake on a player-vs-player pot**, not a fixed admin fee on a guaranteed prize pool. This distinction is itself legally material and is called out per row.
4. The author treats "convertible crystal" as **money's-worth** for the prize element. Counsel to confirm whether convertibility-via-coupon vs. convertibility-to-cash are treated differently.

---

## 2. The matrix

> **Legend for uncertainty:** 🟥 high uncertainty — author has low confidence, counsel must drive · 🟧 medium · 🟨 lower (still counsel's call). Uncertainty describes the **author's** confidence in the cell hypothesis, never legal certainty.

### Variant 1 — Convertible-crystal HEAD-TO-HEAD WAGER + 20% rake (spec's Phase-2 design; Challenge Board §4.7 + paid siege)

| Element | Author's hypothesis | Per-cell uncertainty |
| :--- | :--- | :--- |
| **Consideration** | Present & unambiguous — player stakes convertible crystals with cash value. | 🟨 Lower — staking convertible value is hard to characterize as anything but consideration. Counsel confirms whether "earned, never purchased" crystals change this. |
| **Chance** | Present as a **material element** — winner depends partly on referee error/bypassability, GPS/sensor variance, device quality (audit §2.3). Skill also present (exercise performance). | 🟥 **High** — the whole case turns here. Is residual chance "material" (Market β) or subordinate to predominant skill (Market α)? Author cannot weigh this; it is the #1 counsel question. |
| **Prize** | Present — convertible crystals / cash to the winner. | 🟨 Lower. |
| **Likely classification (hypothesis)** | **Market α:** *possibly* a skill contest **only if** chance is driven down and "predominant skill" is provable. **Market β:** **likely gaming/gambling** (material chance + consideration + prize). **Market γ (NS/Canada):** **likely engages Criminal Code Part VII / provincial gaming control** — needs licence analysis. | 🟥 High across all three. This is the highest-risk variant and the reason Phase 1 exists. |
| **Platform-rake note** | A 20% rake on a player pot reads as **operator economics**, reinforcing a "gaming operator" characterization. | 🟧 Medium — counsel weighs whether rake structure affects classification or only licensing obligations. |

### Variant 2 — ENTRY-FEE SKILL CONTEST (fixed entry, guaranteed prize pool, admin fee not rake)

| Element | Author's hypothesis | Per-cell uncertainty |
| :--- | :--- | :--- |
| **Consideration** | Present (entry fee). But many skill-contest carve-outs **permit** consideration where skill predominates and the prize is pre-announced/guaranteed. | 🟧 Medium — depends entirely on the jurisdiction's contest exemption wording. |
| **Chance** | Must be **engineered down** to qualify. The audit's bypassable-referee finding is a **legal liability here, not just security** — uncontrolled chance defeats the skill framing and collapses this into Variant 1. | 🟥 **High** — qualification depends on a fact (degree of chance) the author cannot measure and the current referee makes worse. |
| **Prize** | Present — real money / cash-equivalent from a guaranteed pool. | 🟨 Lower. |
| **Likely classification (hypothesis)** | **Market α:** *possibly* permissible skill contest if predominant-skill is proven and contest rules are compliant. **Market β:** **still at risk** — "any material chance" markets may classify even skill contests as gaming if chance is material. **Market γ:** fact-specific; provincial contest/lottery rules apply. | 🟧 Medium — better than Variant 1 but jurisdiction-sensitive and contingent on killing the chance vector. |
| **Platform-rake note** | If the cut is a **transparent fixed administration fee on a guaranteed prize pool** (not a % rake on a player wager), the operator-economics signal is weaker. | 🟧 Medium — counsel confirms the fee structure matters. |

### Variant 3 — NON-CONVERTIBLE reward currency + SWEEPSTAKES overlay (no player-to-player cash; today's MVP + prizes)

| Element | Author's hypothesis | Per-cell uncertainty |
| :--- | :--- | :--- |
| **Consideration** | **Absent** for the core loop if crystals are earned-not-bought and never convert to cash. **Sweepstakes** requires a genuine **no-purchase-necessary / alternative method of entry** to keep consideration absent. | 🟧 Medium — hinges on (a) crystals truly having no cash value and (b) a compliant free entry path. If crystals become purchasable, consideration can re-attach. |
| **Chance** | Sweepstakes is **chance-based by design** — but that is fine *because* consideration is removed (no consideration → no gambling even with chance + prize). | 🟨 Lower — well-trodden sweepstakes path, but rules are exacting. |
| **Prize** | Present (sweepstakes prizes / coupons), but the **player-vs-player loop has no cash prize** — staked crystals have no money's-worth. | 🟨 Lower. |
| **Likely classification (hypothesis)** | **All markets:** **likely NOT gambling** for the PvP loop (no money's-worth prize) and **likely a compliant sweepstakes** for the prize overlay **if** the no-purchase path is genuine and rules are followed. **This is the lowest-risk variant.** | 🟨 Lower-medium — author is most confident here, but counsel must still validate sweepstakes mechanics per market and confirm crystals carry no cash value. |
| **Platform-rake note** | 20% "War Tax" on **non-convertible** crystals is an in-game sink, not revenue — no real-money rake. | 🟨 Lower. |

---

## 3. Cross-cutting questions the matrix cannot answer (for counsel)

1. **Does the audited "bypassable referee" chance element (§2.3) defeat a skill-game exemption** in a predominant-skill market? (Drives Variants 1 & 2.)
2. **Are "earned but cash-convertible" crystals "consideration"** even if the player never *purchased* them — i.e., does the *exit to cash* create consideration on the *entry* side?
3. **Does coupon-only convertibility** (redeem at merchants, never cash) sit differently from **cash convertibility** under each market's "money's-worth" definition?
4. **Does a 20% rake** force operator/licence treatment independent of the skill/chance classification?
5. For **Market γ (NS/Canada):** does any of this fall within **provincial lottery/gaming control monopoly** provisions such that even a "skill contest" framing is constrained?

---

## 4. One-line summary for counsel

**Variant 1 is high-risk across all assumed markets (the spec's current Phase-2 design); Variant 2 is medium and contingent on eliminating the audited chance vector; Variant 3 is the lowest-risk path but sacrifices the cash-livelihood pillar. The decisive, unresolved fact in every row is whether the referee's documented bypassability/variance constitutes legally "material" chance — the author cannot and does not decide this.**
