# Competitor Teardown: Steppa (playsteppa.com) — 2026-10-18

**Purpose:** understand how Steppa works and what it offers, for comparison with Osiris.
**Scope:** public material only. This covers the website and its shipped JavaScript bundle, a runtime capture of the
homepage, the public API calls that page makes for every visitor, the App Store listing, and the published terms. The
iOS app binary was not obtained or analysed (App Store builds are encrypted and account-bound). Nothing behind a
login was touched. `robots.txt` explicitly allows AI crawlers, including Claude.

## Evidence ledger

| Source | What it is | Status |
|---|---|---|
| REA `analyze_javascript_application` on the site tree (CLI `ev_ae65ea3b…`/`ev_aaa6e945…`; MCP with a 6 GB worker heap `ev_25588f9e…`) | Static graph of the shipped bundle (`assets/index-BUmQ48xG.js`, 232 KB, artifact sha256 `dba05664…`) | **Incomplete:** the worker exhausted its heap on every run, even at 6 GB, and parsed 0 of 1 JS files. No graph facts were produced; this is not evidence of absence. |
| REA `capture_browser_scenario` (headless Chrome 155, empty profile), `ev_fc7b2d65…` | Runtime capture of a real page load: 22 network transactions with request and response bodies | **Observed** (controlled replay, 2026-10-18). This is the primary runtime evidence. |
| Inert text reading of the same bundle | URLs, API calls and UI copy, read as text and never executed | Observed |
| App Store listing (id 6755126064) | Developer-declared description, in-app purchases, age rating, privacy labels, version history | Observed (developer claims) |
| `legal.playsteppa.com/terms` | Operative rules | Observed (about 96% read; the end of the arbitration section was cut off) |

## What the page does at runtime (REA capture `ev_fc7b2d65…`)

All observed on one page load, with no clicks:

| Call | Purpose |
|---|---|
| `POST api.playsteppa.com/analytics/event` | Sends `AD_LANDING_VIEWED` with a fresh `anonymousId` UUID, `mode: site`, referer and user agent, **before any consent prompt**. This is ad-attribution tracking. The server returned 204; the capture marks the request aborted on its side. |
| `GET api.playsteppa.com/challenges/featured` | One live official challenge: "Corn Maze", $55, 7,500 steps/day. About 30 minutes apart it went from 484 to **489** players and from $26,620 to **$26,895** (exactly 489 × $55). The pool is live. |
| `GET api.playsteppa.com/reviews/stats` | Live App Store ratings aggregate: 4.57 across 2,285 ratings in 15 storefronts (US 1,700, CA 162, GB 108, IN 47 and others). Written reviews are **polarised: 149 five-star and 117 one-star**, with little in between. |
| `static.cloudflareinsights.com` + `/cdn-cgi/rum` | Cloudflare Web Analytics (real-user monitoring) |
| `img.playsteppa.com` | Challenge hero images in several sizes from an image CDN |

No other third-party SDKs were loaded (no Google Analytics, Meta pixel or Segment). There were no console errors and
no WebSockets. The marketing site is a small React (Vite) single-page app; the product itself lives in the iOS app.

## What Steppa is

A **real-money step-commitment app**: "Win Real Cash by Walking". Published by **Steppa LLC** (Newark, DE), iPhone
only, in Health & Fitness, rated **18+**. Its age-rating descriptors include *gambling* and *frequent contests*.
Version 1.0 shipped on 08 Dec 2025 and 1.8.1 on 6 Oct 2026: 22 releases in about 10 months. Marketing figures,
hard-coded in the bundle: 4B+ steps, 80k+ players, 20k+ challenges completed, **$800k+ won**.

## How it works (observed)

1. **Join:** pick a challenge (a daily step goal over fixed dates) and pay a stake of **$10–$500**. On top come a
   service fee (a flat amount plus a percentage) and, for public challenges, a creator fee.
2. **Walk:** steps come from **Apple HealthKit**; the terms also name Android Health Connect. Manual entries never
   count. Third-party wearables count only if they write to Apple Health, and failed syncs are not refunded.
3. **Settle:** everyone who finishes every day splits the pool equally. Shares are rounded down to the cent; Steppa
   keeps the remainder, and the whole pool if nobody finishes. Players who miss a day forfeit their stake to the pool.
   In the current "up-front fee" model, 100% of stakes go to winners. Challenges created before 18 Jun 2026 used a
   legacy model: a completion-weighted platform fee of 15% falling to 5%, and a creator cut of 5–10%.
4. **Cash out:** winnings reach the in-app wallet within 24 hours. Withdrawals go to PayPal, Venmo, US ACH (Mercury)
   or international via Whop, with a $25 minimum and limits of $500 a day and $2,000 a week. A 1099 is issued for
   $600+ a year.

**Monetisation:** service fees, creator fees, $25 to create a public challenge, sponsor fees (up to 15%), and the
**Steppa Pro** subscription ($4.99–$119.99 tiers). Pro allows 5 concurrent challenges instead of 1, waives the
service fee, includes one free public challenge creation a month, and adds cosmetic perks.

## Feature inventory

| Area | Steppa (observed) |
|---|---|
| Activity | Daily step count only. No GPS route, course, or exercise form |
| Verification | Trusts HealthKit/Health Connect. Bans jailbroken, emulated or spoofed devices and VPNs. Voids "implausible patterns" and coordinated accounts. Audit requests with a 24 h window, clawback, and fraud termination that forfeits the whole balance |
| Challenge types | Official, user-created public, private, sponsored, charity fundraiser, teams, early-bird hours, bonus prizes, tiers, participant caps (all fields in the challenge JSON) |
| Social / growth | Invite codes (`join.playsteppa.com/join/<CODE>`), referral rewards (cash or a free entry), creator economy, comparing progress with friends |
| Privacy (App Store label) | Linked to identity: health, purchases, financial info, coarse location, name/email/address, photos, user ID. Used for tracking: purchases, contact info, identifiers |
| Compliance posture | Describes itself as "skill-based… NOT a gambling service" and "a commitment device". 18+ (19/21 where required), region-gated, KYC/AML at payout thresholds, Delaware law, AAA arbitration, class-action waiver |

## Comparison with Osiris

| | Steppa | Osiris |
|---|---|---|
| Core loop | Pay to commit, walk daily steps, split the pool | Verified GPS runs, quests, courses and challenges, XP and rank |
| Money | **Real cash in and out** | XP and badges only. Crystals are a one-way top-up, and cash-out was deliberately not built (ADR-005, Phase 1 viability memo) |
| Evidence | Step totals from HealthKit (trusted) | Server-verified GPS route, on-device pose checks for exercises |
| Location | Coarse only | Exact route, kept private (trimmed, generalised markers, 45-day retention) |
| Platforms | iPhone only today | Android and iOS (Flutter, moving to KMP) |
| Maturity | Shipping, about 80k players, monetising | Pilot-stage build |

**What it tells us (inference, not legal advice):**

- Steppa runs at scale on the exact model the Osiris viability memo flagged for legal review: player stakes pooled
  and paid out. It manages the risk with skill-based framing, 18+ and region gating, KYC/AML, 1099s, arbitration and
  Apple's *gambling* descriptor. That is a working template, but it carries compliance cost and real legal risk.
  ADR-005 remains the right default until counsel signs off.
- Its anti-cheat leans on trusted OS health data plus enforcement through the terms. Osiris's server-side route
  verification is stronger evidence but harder for players to satisfy.
- Written reviews are polarised, with 117 one-star out of 336. Payout delays, sync failures that are not refunded,
  and fraud voids are the likely causes given the terms, but that is an inference: the review text was not read.
- Growth patterns worth borrowing that do not involve money: invite-code landing links, creator- and
  sponsor-funded challenges, charity challenges, team scoring, and HealthKit/Health Connect step import as a
  low-friction second activity type.

## Unknowns

- In-app behaviour beyond the terms and the listing (the app binary was not analysed).
- Exact service and creator fee percentages, excluded jurisdictions, and KYC thresholds.
- How "implausible patterns" are detected.
- Whether the 80k / $800k figures are current: they are hard-coded marketing numbers, not live data.
