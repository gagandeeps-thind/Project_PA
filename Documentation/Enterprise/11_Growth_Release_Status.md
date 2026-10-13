# Growth Release Status (G1–G6)

**Release:** Core habit loop, sharing, communities, and trust controls, built on top of R0–R2 (doc 10).
**Status:** Implemented and verified locally on 2026-09-27. Not committed or promoted; see "Before promotion".
**First promise:** *Complete verified local running challenges and build your fitness reputation.*
**Tagline in the product:** "Fitness, turned into quests."
**Economy:** XP, badges, rank, and partner perks (text only). No crystals, entry fees, stakes, or prizes.

## What a new player experiences

1. **Sign-up in three steps** (`POST /api/v2/auth/register`):
   1. Pick a goal: get fitter, run more, build a habit, or compete.
   2. Read a plain explanation of location use and choose on or off.
   3. Enter a name, email, password, and an optional invite code.

   No weight, height, or BMI is collected. v2 accounts start with no crystals.
2. **Today screen** (`GET /api/v2/me/today`):
   - Today's quest, with progress and a one-tap START.
   - This week's active days and the weekly streak.
   - Tomorrow's quest, one nearby free challenge, and a safety note.
3. **First quest:** "Walk or run 1 km". A guided first success is well under ten minutes.
4. **After a verified run:**
   - A celebration showing distance, time, XP, week progress, and tomorrow's quest.
   - A one-tap share, then the existing offer to turn the route into a course.

## Requirement coverage

| Brief item | Where it lives |
|---|---|
| Daily and weekly quests | `services/quests.py`, `growth_api.on_run_accepted` (idempotent `quest_awards`) |
| Streaks that do not punish rest | Weekly streak (≥3 active days per week); an in-progress week never breaks it |
| Safe quests | Target from the player's own 28-day history; capped at 10 km and 125% of the best recent day; optional recovery day after 3 active days |
| Identity | Goal maps to runner / explorer / challenger / athlete. There is no BMI identity. |
| Funnel analytics | `analytics_events`; the server emits milestone events. `GET /api/v2/admin/funnel` and the admin "Growth" page. |
| Shareable cards, "I completed this route" | `POST /api/v2/share`, public `/s/{token}` with link-preview tags. No route or location. Revocable. |
| Invite-a-friend challenges | `POST /api/v2/challenges/{id}/invites`, `/i/{token}`, invite stats |
| Referrals that do not encourage cheating | Reward only after the friend's first verified run of 1 km or more. No reward for a sign-up from the inviter's own install. Capped at 5 per 30 days. XP and badge only. |
| Public achievement pages | Opt-in `/p/{code}`: indexable, JSON-LD, HTML-escaped, no location |
| Clubs, gyms, universities, workplaces | `growth_communities.py`: branded page, member perk, verified mark (admin), private groups with join code |
| Team challenges / team goals | Weekly shared distance goal per community; featured community challenges |
| Local rankings | City chosen in the profile (never GPS). Opt-in names; others shown as "Private runner". |
| Seasonal events | City seasons, with a player board and a club board (average per entered member, at least 3 entered) |
| Network density | `scripts/seed_city.py` seeds official routes, challenges, verified partner groups, and a season through the real verification pipeline |
| Location consent | Consent step at sign-up; runs refused without it (v2 accounts); append-only `consent_records` |
| Export and deletion | `GET /api/v2/me/export` (includes raw points); `POST /api/v2/me/erase` (personal data removed; account row anonymised) |
| Reporting, blocking, abuse review | `growth_safety.py`; admin "Community" page. Three unsafe-route reports pause a challenge. |
| Session revocation | "Sign out everywhere" and password change revoke older tokens (`iat` vs `users.tokens_valid_after`) |
| Reward and refund rules | `GET /api/v2/rules`, shown in the app. States that verification is rules-based, not AI. |

## Code and migrations

- **Backend modules:**
  - Routers: `growth_api.py`, `growth_social.py`, `growth_communities.py`, `growth_safety.py`.
  - Services: `services/quests.py`, `services/leaderboards.py`, `services/player_safety.py`.
  - Import order: `main` imports `growth_api` last, and `growth_api` imports the other routers last. `main` itself only uses `services/player_safety.py`.
- **Migrations:** `b7d1e4f9a2c3` (G1), `c2f6a8d3b915` (G2), `d4a9c7e2f1b6` (G3), `e8b3f5a1c7d4` (G4).
- **Customer app:**
  - New screens: `today_screen.dart` (the new home), a rewritten `onboarding_screen.dart`, `communities_screen.dart`, `rankings_screen.dart`, `settings_screen.dart`.
  - Changed screens: challenge detail (invite, report, block, share) and the run screen (celebration, share).
- **Admin web:** new Growth and Community pages.

## Verification (2026-09-27)

- **Backend:** all 14 suites pass, including the new G1–G4 growth suites (27 tests), three consecutive runs.
- **Backend tooling:** ruff clean. OpenAPI regenerated (91 paths) with no drift. Every migration upgrades, downgrades, and re-upgrades on a fresh database.
- **Customer app:** `flutter analyze` clean, `flutter test` 7/7, `flutter build apk --debug` succeeds.
- **Admin web:** `tsc --noEmit` clean, `vite build` succeeds.
- **CI:** runs the four new growth suites.

## Residual risks (owner acceptance needed)

1. **v1 endpoints bypass the new controls.** Session revocation, suspension, consent, and blocks are enforced on v2 only. Legacy v1 endpoints should be gated or removed before pilot (same as doc 10 item 4).
2. **Referral device check is weak.** It compares app install ids, which a determined person can reset. The verified-run requirement and the cap are the real controls. Device-integrity signals are still not built.
3. **Erasure leaves legacy territories.** Legacy `domains` rows owned by an erased player are not deleted, because other legacy records reference them. The legacy features are behind a flag.
4. **Seed content is a placeholder.** `seeds/bedford_ns.example.json` uses straight-line geometry and fictional organisations. Real routes must be walked on the ground, and partners must agree to be listed, before launch.
5. **Sharing uses the clipboard.** A native share sheet (`share_plus`) is a one-file change in `services/share_helper.dart`.
6. **Funnel data is in the product database.** Fine for a single-city pilot. Move it to a warehouse before scale.
7. **Official challenges expire after 30 days.** `seed_city.py` must run monthly (cron or a scheduler job), or the map empties.

## Before promotion to SIT

- Commit the release. The working tree also contains unrelated uncommitted changes (email uniqueness, v1 GDPR endpoints, 80% geofence checks, Flutter edits), and `growth_api` depends on `_check_email_unique` from those changes.
- Everything in doc 10's "Before promotion to SIT" list still applies (PostgreSQL/PostGIS, retention job, v1 gating, field test).
- Field-test the activation path on a real phone: install, sign-up, first quest, verified run, share, and a friend joining through the link.
- Replace the example seed with the pilot city's surveyed routes and signed-up partners.
