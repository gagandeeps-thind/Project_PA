# Google Play Billing: server verification contract

The Android app buys through Play Billing; the API is the only place that grants anything.
Code: `Osiris_backend/routers/payments.py` (Google Play section), `services/google_play.py`,
`services/jobs.py` (`process_play_voided_purchases`), table `google_play_purchases` (migration
`e1a7c4d9b2f5`). Tests: `tests/test_google_play_billing.py`.

## Products

| Play product id | Kind | Grants |
|---|---|---|
| `osiris_crystals_starter` | consumable | 500 crystals |
| `osiris_crystals_adventurer` | consumable | 1200 crystals |
| `osiris_crystals_champion` | consumable | 2600 crystals |
| `osiris_founder_pack` | non-consumable | `founder_pack` entitlement |
| `osiris_pass_monthly`, `osiris_pass_annual` | subscription | `osiris_pass` entitlement |

Crystal amounts come from `CRYSTAL_PACKS` on the server; prices are whatever Play Console charges.
The server decides the kind from the product id; the app does not send it. A multi-quantity purchase
(one token, `quantity` N) is credited N packs.

## Account binding

The app passes `obfuscatedAccountId` to `launchBillingFlow`: the lowercase hex SHA-256 of the UTF-8
string `osiris:<user id>` (user id in decimal; `osiris:42` gives `df7e2e42...9e745d`). Google returns
it with the purchase. When it is present and is not the caller's, verify answers 409 and grants
nothing; a purchase without it is accepted. A token is also bound to the first account that verifies it.

## `POST /api/v2/payments/google-play/verify` (player JWT)

Request:

```json
{ "product_id": "osiris_crystals_starter", "purchase_token": "<Purchase.purchaseToken>" }
```

Send one request per product in the purchase. `product_id` matches `^[a-z0-9_.]+$`;
`purchase_token` matches `^[A-Za-z0-9._-]+$` (422 otherwise).

Response 200:

```json
{
  "product_id": "osiris_crystals_starter",
  "kind": "consumable",
  "state": "credited",
  "crystals_credited": 500,
  "balance": 600,
  "expires_at": null,
  "consume": true,
  "entitled": true
}
```

- `state`: `credited` (pack granted), `owned` (founder pack), `pending`, `canceled`, or for passes
  `active`, `in_grace_period`, `canceled` (auto-renew off, paid time still counts), `on_hold`,
  `paused`, `expired`.
- `crystals_credited` is what *this* call granted. A repeat call for the same token answers 200 with
  `crystals_credited: 0`, so retries are always safe.
- `consume: true`: call `consumeAsync` now, so the pack can be bought again. Never consume before this.
- The server acknowledges every granted purchase with Google itself. The app does not need
  `acknowledgePurchase`, but calling it does no harm.
- `pending`: nothing was granted. Verify again when Play Billing delivers the purchase as PURCHASED.

Errors: 400 Google does not know the token (or it is for another product), 403 a licence-test
purchase while `GOOGLE_PLAY_ALLOW_TEST_PURCHASES` is off, 404 unknown product id, 409 the purchase
belongs to another account or product, 429 more than 30 calls a minute from one IP, 502 Google
unreachable (retry later, keep the purchase unconsumed), 503 server has no Play credentials (fails
closed: nothing is granted). The `detail` text is fixed; Google's own error text only goes to the log.
A failed acknowledge after a successful grant is logged and the call still answers 200.

## `GET /api/v2/payments/entitlements` (player JWT)

Store-neutral path. `GET /api/v2/payments/google-play/entitlements` answers the same and is kept for
older builds.

```json
{
  "osiris_pass": true,
  "osiris_pass_product_id": "osiris_pass_monthly",
  "osiris_pass_state": "active",
  "osiris_pass_expires_at": "2026-12-01T12:00:00",
  "founder_pack": false
}
```

Use this to gate pass and founder content, not the local Play state. A pass past its stored expiry is
re-read from Google on this call (renewal or lapse), in case a notification was missed.

## Refunds and revocations

Two paths feed the same code (`services.google_play.void_purchase`), and either works alone:

- `POST /api/v2/payments/google-play/rtdn`: Real-time Developer Notifications pushed by Pub/Sub.
  The message is only a hint; the server re-reads the purchase from Google and stores what Google says.
- `jobs.process_play_voided_purchases`, every 6 hours: reads the Voided Purchases API (last 30 days).
  Does nothing when the Play credentials are not set.

What happens:

- Subscription (renewed, canceled, expired, revoked, on hold): the row takes Google's state and
  expiry, so a revoked pass stops unlocking at once.
- Founder pack refunded: state `refunded`, `founder_pack` is false.
- Crystal pack refunded: state `refunded` and the granted crystals are taken back with one
  `crystal_refund` ledger entry. **If the player already spent them, the clawback is capped at the
  current balance**: the wallet goes to 0, never below, and the shortfall is written in the ledger
  note and logged as `google play refund shortfall`. No debt is carried. Repeat offenders are a
  moderation matter (search the logs for that line).
- A `refunded` purchase is never granted again, whatever a later verify says.
- Applying the same refund twice changes nothing.
- Not automated: a partial refund of a multi-quantity purchase (`refundType` 2) is only logged as
  `google play partial refund needs manual review`.

The endpoint is authenticated by the shared token `GOOGLE_PLAY_RTDN_TOKEN`, sent as `?token=` (Pub/Sub
push cannot set custom headers) or as the `X-Osiris-Rtdn-Token` header. Unset: 503 (closed). Wrong: 403.
200 `{"status": "ok" | "ignored"}`; 502/503 make Pub/Sub deliver again.

## Account erasure

Erasing an account (`POST /api/v2/me/erase`, `DELETE /api/v1/users/{id}`) keeps its purchase rows as
anonymous accounting records but replaces the Play `purchase_token` and the App Store `transaction_id`
with `erased:<sha256 of the value>` and clears `order_id` (`services/google_play.erase_store_purchases`).
Verify looks up both forms, so the same purchase sent again from another account answers 409 and is
never credited twice. Notifications and the refund job no longer find those rows, so a refund after
erasure is not clawed back (the account's wallet is gone). Erasure does not cancel a subscription at the
store; the account-deletion page and the terms tell the player to cancel it in Google Play or the App Store.

## App flow

1. `launchBillingFlow`. On `onPurchasesUpdated`, and on every app start, query owned purchases with
   `queryPurchasesAsync`.
2. For each purchase in state PURCHASED: `POST /verify`. Only grant UI from the response.
3. If `consume` is true, call `consumeAsync`. If the call failed (no network, 5xx), keep the purchase
   and retry on the next start: the token stays valid and a retry never double-credits.

## Server setup (once)

1. Google Cloud: create a service account and a JSON key.
2. Play Console, Users and permissions: invite the service-account email with "View financial data"
   and "Manage orders and subscriptions".
   These two cover verification, acknowledgement and the Voided Purchases API. The account needs no
   Google Cloud IAM role.
3. Render, `osiris-api`, Environment: `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` = the key file's JSON.
   `GOOGLE_PLAY_PACKAGE_NAME` defaults to `osiris.fit`. Restart the service after rotating the key
   (the authorised session is cached for the life of the process).
4. `GOOGLE_PLAY_ALLOW_TEST_PURCHASES` defaults to `true`, so licence testers can buy during internal
   testing (their crystals are real). Set it to `false` for the public launch: test purchases then
   answer 403.

The voided-purchases job needs nothing more: it starts working as soon as step 3 is done.

## Real-time Developer Notifications setup (once)

1. Render, `osiris-api`, Environment: copy the generated value of `GOOGLE_PLAY_RTDN_TOKEN`.
2. Google Cloud console, in the project linked to the Play Console account: enable the Cloud Pub/Sub
   API and create a topic, for example `osiris-play-rtdn`.
3. On the topic, Permissions: add the principal
   `google-play-developer-notifications@system.gserviceaccount.com` with the role **Pub/Sub Publisher**.
4. Create a subscription on the topic: delivery type **Push**, endpoint URL
   `https://api.osiris.fit/api/v2/payments/google-play/rtdn?token=<GOOGLE_PLAY_RTDN_TOKEN>`,
   acknowledgement deadline 30 seconds, retry policy exponential backoff. Leave push authentication
   off (the token in the URL is the authentication). The URL must be the Cloudflare hostname: with
   the origin lock on, the `onrender.com` hostname answers 403.
5. Play Console, Monetize with Play, Monetization setup, Real-time developer notifications: enter
   the topic name `projects/<project id>/topics/osiris-play-rtdn`, choose "Subscriptions, voided
   purchases and all one-time products", save, then **Send test notification**. The API log shows
   `POST /api/v2/payments/google-play/rtdn` with status 200.

To rotate the token: change `GOOGLE_PLAY_RTDN_TOKEN` on Render and edit the subscription's endpoint URL.
Until both match, pushes answer 403 and Pub/Sub retries them (it keeps messages for 7 days).

## Not built yet

- Partial refunds of multi-quantity purchases are logged, not clawed back.
- A notification for a purchase the app never sent to `/verify` is ignored (there is no row to update).
- Play revenue is not written to `platform_revenue`. Google reports it in Play Console.
