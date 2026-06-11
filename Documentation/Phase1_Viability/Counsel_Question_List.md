# Osiris — Question List for Licensed Gaming / Payments Counsel

| Field | Value |
| :--- | :--- |
| **Document Type** | Scoped counsel question list (target: billable in **≤ 2 hours**) |
| **Date** | 2026-06-11 |
| **Prepared by** | Senior Compliance & Privacy Analyst (panel input) |
| **Audience** | Licensed gaming + payments lawyer (Canadian-qualified; Nova Scotia) |
| **Companion** | `Gambling_Analysis_Matrix.md` (the variant decomposition these questions reference) |

---

## How to use this (note to counsel)

Osiris is a pre-launch fitness game built by a solo developer in Bedford, Nova Scotia. **Phase 1 is virtual-currency-only** (no cash in or out of the game economy). **Phase 2** would make the in-game "Mana Crystals" **convertible to real currency**, let players **stake** them head-to-head, and take a **20% rake**. We need your read on whether/where that crosses into regulated gaming and what the payments obligations are. We have pre-decomposed the mechanic into three design variants in the companion matrix to save your time. **We are not asking you to design the product — only to classify the variants and flag the obligations.**

The single fact we most need weighed: the platform's "verified score" that decides a winner is produced by a heuristic referee from **client-supplied sensor data**, and our own security audit concludes it is **bypassable** — so the outcome is **partly outside an honest player's control.**

---

## Part A — Gaming / gambling classification (the core ask)

1. **Target markets.** We have not yet finalized our top-3 markets beyond Canada. Given a Nova Scotia base, **which 2–3 additional markets would you advise we model first**, and does your classification below change materially across them? *(This replaces the α/β/γ placeholders in our matrix.)*

2. **Variant 1 (convertible-crystal head-to-head wager + 20% rake):** Under **Criminal Code Part VII** and **Nova Scotia provincial gaming control**, is this **likely gaming/gambling requiring a licence**? Specifically, does staking **convertible** crystals on a contested outcome constitute "consideration + chance + prize"?

3. **The chance question (decisive).** Our referee's winner-determination is **partly outside the player's control** (documented bypassability, GPS/sensor variance). **Does that residual chance defeat a "game of skill" exemption** in your assessed markets, or can predominant-skill still carry it? **What evidentiary threshold of "predominant skill"** would we need to meet?

4. **Variant 2 (entry-fee skill contest, guaranteed prize pool, fixed admin fee not a rake):** Would reframing as a **skill contest with a pre-announced prize pool and a fixed administration fee** materially lower the classification risk versus Variant 1? What contest-rules formalities (published rules, eligibility, prize disclosure) are mandatory?

5. **Variant 3 (non-convertible crystals + no-purchase-necessary sweepstakes):** If crystals are **earned, never cash-convertible**, and prizes run via a **sweepstakes with a genuine free entry method**, do you agree the **player-vs-player loop is likely not gambling** (no money's-worth prize)? What makes a sweepstakes free-entry path compliant in our markets?

6. **Coupon-only vs. cash convertibility.** Does it matter, legally, whether crystals convert to **merchant coupons** (current built mechanic) versus **cash**? Is coupon-redeemable value still "money's-worth" / a "prize"?

7. **Rake structure.** Does a **20% rake on a player pot** independently push us toward "operator/licensee" treatment, regardless of the skill/chance outcome — i.e., is the *fee structure itself* a classification factor?

8. **Age.** Our pilot is adults in Bedford. **What is the minimum compliant age-verification** standard for a wagering-adjacent product, and does any chance element trigger a hard 18+/19+ (NS) gate?

9. **The one-sentence answer we need to act on:** *Given the chosen variant, can we launch real-money in Nova Scotia without a gaming licence — yes, no, or "only if you redesign to X"?* If "no/redesign," what is the **shortest compliant path** to letting players earn real value?

---

## Part B — Payments, money-services, KYC/AML, and chargebacks

10. **Money-services / MSB classification.** If Mana Crystals become **convertible to cash and move between users**, does Osiris become a **money-services business / money transmitter** (FINTRAC registration in Canada; equivalent in other markets)? At what point does holding player balances + facilitating player-to-player value transfer trigger registration?

11. **KYC/AML program scope.** If MSB obligations attach: what **identity-verification, record-keeping, and transaction-monitoring** minimums apply for a ~50-user pilot, and do they scale at thresholds we should plan for? Is there a de-minimis pilot exemption?

12. **Stripe gaming pre-approval.** Stripe lists **real-money gaming as a restricted business requiring pre-approval.** (a) How should we **categorize and disclose** Osiris to Stripe to avoid account termination / fund freezes? (b) If Stripe declines, what **gaming-capable PSP** alternatives fit a Canadian micro-pilot? (c) Does merely *holding convertible-but-not-yet-converted* crystals trigger the gaming category, or only the cash-out step?

13. **Chargeback model for siege/wager losses.** Core risk: a player **buys crystals with a card**, **loses them in a siege/wager**, then **disputes the original card charge.** (a) Who bears that chargeback — platform or winning player? (b) Can we contractually structure the purchase (crystals as a final, non-refundable digital good at point of sale, separate from the later wager) to limit dispute exposure? (c) Does a successful chargeback **after** crystals were paid out to a winner create a clawback or a platform loss we must reserve against?

14. **Segregation of player funds.** If we hold convertible crystal balances, must player funds be **segregated** from operating funds, and is there a **reserve/bonding** requirement in any target market?

15. **Tax/withholding.** When a player **cashes out** winnings, are we obligated to **report or withhold** (e.g., information returns) in any target market?

---

## Part C — Pre-read materials we will provide

- `Gambling_Analysis_Matrix.md` — the three variants decomposed against consideration/chance/prize with our stated uncertainty.
- `Viability_Memo.md` §2–§4 — precise mechanic restatement + the "what must be true to launch real money" gate.
- The siege/wance payout math: pot = defender vault + challenger match; **win 80/20**, **loss 50/30/20**; Challenge Board pot minus **20%** (`Imp_and_US.md` §4.4/§4.7).
- On request: the relevant audit excerpt (§2.3) documenting referee bypassability.

---

## Part D — Out of scope for this engagement (so we don't burn your hours)

- Drafting the gaming licence application (separate engagement if needed).
- Full KYC/AML program build (we want **scoping**, not the program, in this session).
- Privacy/PIPEDA review — handled by separate privacy counsel against `Privacy_Build_List.md`.
- Any opinion premised on facts we have **not** provided (e.g., crystal pricing, conversion rate — **these are currently undefined** and flagged in the memo §7; if your answer depends on them, please tell us what value-points change the classification).

---

## Efficiency note (why this should fit ≤2 hours)

The mechanic is pre-decomposed (Part C), the variants are pre-ranked, and our specific uncertainties are itemized per cell in the matrix. We are asking for **classification + obligation-flagging + a shortest-compliant-path sentence**, not original analysis from a blank page. Questions 2, 3, 9, 10, and 12 are the **must-answer five** if time runs short.
