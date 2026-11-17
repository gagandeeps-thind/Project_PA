# App Store billing (StoreKit 2): server verification contract

The iOS app buys through StoreKit 2; the API is the only place that grants anything.
Code: `Osiris_backend/routers/payments.py` (App Store section), `services/app_store.py`, table
`app_store_purchases` (migration `a7d2f4c9e1b6`). Tests: `tests/test_app_store_billing.py`.

**Status: closed by default.** Until `APPLE_APP_STORE_ENVIRONMENT` is set, both endpoints answer 503
and nothing is granted or stored. The iOS client does not exist yet (see "Not built" below).

## How a purchase is trusted

StoreKit hands the app a signed transaction (a JWS). The server never calls Apple. It accepts a JWS
only when all of these hold:

1. The `x5c` header holds three certificates; the intermediate is signed by the server's own copy
   of **Apple Root CA G3** (embedded in `services/app_store.py`, SHA-256
   `63343abf...3e9179`), and the leaf by the intermediate. The root sent in the header is ignored.
2. The intermediate and leaf carry Apple's marker extensions (`1.2.840.113635.100.6.2.1` and
   `1.2.840.113635.100.6.11.1`), and both were valid when the payload was signed.
3. The ES256 signature matches the leaf's key.
4. `bundleId` equals `APPLE_BUNDLE_ID` (default `osiris.fit`) and `environment` is one listed in
   `APPLE_APP_STORE_ENVIRONMENT`.

There is no setting that changes the trusted root. Not checked: OCSP revocation of Apple's own
certificates.

## Products

Same ids, kinds and grants as Google Play (`docs/architecture/google-play-billing.md`): the three
`osiris_crystals_*` consumables, `osiris_founder_pack` (non-consumable) and
`osiris_pass_monthly` / `osiris_pass_annual` (auto-renewable, one subscription group). The server
reads the product from Apple's signed payload; the app does not send it. `quantity` N credits N packs.

## Account binding

The app passes `appAccountToken` to `product.purchase(options:)`:
`UUIDv5(NAMESPACE_URL, "osiris:<user id>")`, user id in decimal (`osiris:42` gives
`3992d9c9-b83f-5732-b590-2b6edfe75473`). When the transaction carries a token that is not the
caller's, verify answers 409 and grants nothing; a transaction without one is accepted. A
transaction is also bound to the first account that verifies it.

## `POST /api/v2/payments/app-store/verify` (player JWT)

Request: `{ "signed_transaction": "<VerificationResult.jwsRepresentation>" }`

Response 200: the same body as the Google Play verify response (`product_id`, `kind`, `state`,
`crystals_credited`, `balance`, `expires_at`, `consume`, `entitled`).

- `state`: `credited` (pack granted), `owned` (founder pack), `active` or `expired` (pass),
  `refunded` (Apple refunded or revoked it).
- `crystals_credited` is what *this* call granted; a repeat answers 200 with 0, so retries are safe.
- **Call `transaction.finish()` after any 200.** Do not finish on any other status: StoreKit
  delivers the transaction again through `Transaction.updates` and the app retries.

| Status | Meaning |
|---|---|
| 400 | Not a transaction Apple signed for this app and environment |
| 403 | Account suspended |
| 404 | Product id the server does not know |
| 409 | Bound to another account |
| 422 | `signed_transaction` is not a JWS-shaped string (max 16384 characters) |
| 429 | Rate limit (30 per minute per IP) |
| 503 | App Store billing is not configured |

Subscriptions are stored once per `originalTransactionId`; renewals update that row. Send every
transaction from `Transaction.updates` and (for restore) `Transaction.currentEntitlements` here.

## `POST /api/v2/payments/app-store/notifications` (no JWT)

App Store Server Notifications **version 2**. The body is `{ "signedPayload": "<JWS>" }`, verified
exactly like a transaction, so no shared secret is needed.

- `REFUND`, `REVOKE` (or any transaction with a `revocationDate`): a crystal pack is clawed back
  through the ledger as `crystal_refund`, once, capped at the balance (same policy as Google Play);
  a founder pack or pass stops unlocking.
- `DID_RENEW`, `SUBSCRIBED` and other subscription types: the transaction's `expiresDate` extends
  the pass. `EXPIRED`, `GRACE_PERIOD_EXPIRED`: the pass ends.
- `TEST`, and purchases the app never sent to verify: 200 `{"status": "ignored"}`.
- Every type is applied from the signed transaction, so repeated and out-of-order deliveries
  change nothing. 400 on an unverifiable payload, 503 while unconfigured (Apple retries).

Known limits: `REFUND_REVERSED` is only logged (`app store refund reversal needs manual review`);
the billing grace period is not honoured (a pass in billing retry ends at its `expiresDate`); a
refund notification for a purchase the app has not verified yet is ignored.

## `GET /api/v2/payments/entitlements` (player JWT)

Store-neutral: `osiris_pass` and `founder_pack` are true when either store's purchases grant them.

## Setup (human steps)

1. **App Store Connect > Business**: accept the Paid Apps agreement and fill in tax and banking.
   Products cannot be bought, even in Sandbox, before this is active.
2. **App Store Connect > your app > Monetization**: create the six products with exactly the ids
   above. In-App Purchases: three consumables and one non-consumable. Subscriptions: one group
   holding `osiris_pass_monthly` and `osiris_pass_annual`. Add a price, a localisation and the
   review screenshot to each, or they stay in "Missing Metadata".
3. **Render > osiris-api > Environment**: set `APPLE_APP_STORE_ENVIRONMENT`.
   - `Production,Sandbox` while TestFlight testers and App Review buy. Both use the Sandbox
     environment and pay nothing, so they receive real crystals: the same trade-off as
     `GOOGLE_PLAY_ALLOW_TEST_PURCHASES`. App Review fails if Sandbox is refused.
   - `Production` once you no longer want free Sandbox grants. Turn Sandbox back on for each
     review of an update that touches purchases.
   - `APPLE_BUNDLE_ID` is already `osiris.fit`; change it only if the bundle id changes.
4. **App Store Connect > your app > App Information > App Store Server Notifications**: set both
   the Production and the Sandbox URL to
   `https://api.osiris.fit/api/v2/payments/app-store/notifications`, **Version 2**. Then send a
   test notification (App Store Server API "Request a Test Notification", or the button in App
   Store Connect where shown) and check the API log for a 200 on that path. Note: this path must
   stay reachable from Apple, which sends no `X-Origin-Verify` header (see "Origin lock").
5. Optional, not used by the server yet: **Users and Access > Integrations > In-App Purchase**,
   generate a key and store `APPLE_ISSUER_ID`, `APPLE_KEY_ID` and `APPLE_PRIVATE_KEY` (the `.p8`
   content) on Render. They are for future App Store Server API calls (transaction history,
   subscription status).

### Origin lock

`OSIRIS_ORIGIN_SECRET` makes the API refuse requests that did not come through Cloudflare. Apple's
notifications go to `api.osiris.fit`, which is behind Cloudflare, so they pass like Google's
Pub/Sub pushes do. Nothing to change unless the notification URL is ever pointed straight at Render.

## Not built

- The iOS StoreKit client and store screen (`ios_version/`), and the shared KMP `PaymentsApi` call
  for this endpoint.
- App Store Server API calls. Nothing needs them today: a lapsed pass fails its stored expiry
  check, and renewals arrive as signed notifications or through `Transaction.updates`.
