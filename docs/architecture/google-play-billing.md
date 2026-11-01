# Google Play Billing: server verification contract

The Android app buys through Play Billing; the API is the only place that grants anything.
Code: `Osiris_backend/routers/payments.py` (Google Play section), `services/google_play.py`,
table `google_play_purchases` (migration `e1a7c4d9b2f5`). Tests: `tests/test_google_play_billing.py`.

## Products

| Play product id | Kind | Grants |
|---|---|---|
| `osiris_crystals_starter` | consumable | 500 crystals |
| `osiris_crystals_adventurer` | consumable | 1200 crystals |
| `osiris_crystals_champion` | consumable | 2600 crystals |
| `osiris_founder_pack` | non-consumable | `founder_pack` entitlement |
| `osiris_pass_monthly`, `osiris_pass_annual` | subscription | `osiris_pass` entitlement |

Crystal amounts come from `CRYSTAL_PACKS` on the server; prices are whatever Play Console charges.
The server decides the kind from the product id; the app does not send it.

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

Errors: 400 Google does not know the token (or it is for another product), 404 unknown product id,
409 the token is already linked to another account or product, 502 Google unreachable (retry later,
keep the purchase unconsumed), 503 server has no Play credentials.

## `GET /api/v2/payments/google-play/entitlements` (player JWT)

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
re-read from Google on this call (renewal or lapse).

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
3. Render, `osiris-api`, Environment: `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` = the key file's JSON.
   `GOOGLE_PLAY_PACKAGE_NAME` defaults to `com.osiris.player`.

## Not built yet

- Real-time Developer Notifications (Pub/Sub). Without them a refund or cancel is only seen the next
  time the app verifies or reads entitlements.
- Voided Purchases API: crystals from a refunded pack are not clawed back.
- Play revenue is not written to `platform_revenue`. Google reports it in Play Console.
