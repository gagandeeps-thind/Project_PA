# App Store billing on iOS (StoreKit 2)

The iOS half of App Store billing. The server half (endpoints, checks, notifications, Render
settings) is `docs/architecture/app-store-billing.md`; read that first.

**Status: written, not compiled.** The Swift has never been built (no Mac in the agent setup). The
server stays closed (503) until `APPLE_APP_STORE_ENVIRONMENT` is set, and a 503 never finishes a
transaction, so nothing is lost while either side is not ready.

## Code

| File | What it does |
|---|---|
| `ios_version/Osiris/Sources/Store/CrystalStore.swift` | StoreKit 2: products, purchase, `Transaction.updates`, retry, restore |
| `ios_version/Osiris/Sources/Store/CrystalStoreView.swift` | The Mana Crystal Store screen |
| `ios_version/Osiris.storekit` | Local products for Xcode runs (simulator), set on the scheme in `project.yml` |
| `App/RootView.swift` | Creates one `CrystalStore`, starts it at launch, retries after each sign-in |
| `App/Navigator.swift`, `Profile/ProfileView.swift` | `Route.store`; the sparkles button in the Profile toolbar opens it |

The shared code it uses (`shared/presentation/.../wallet/StoreSupport.kt`, reached as `graph.store()`):

- `appStoreAccountToken()`: the player's `appAccountToken`, `UUIDv5(NAMESPACE_URL, "osiris:<user id>")`;
  nil when signed out.
- `verifyAppStore(signedTransaction:)` (Kotlin `suspend`, so Swift `try await`): posts the JWS to
  `POST /api/v2/payments/app-store/verify`. `finish` is true only on a 200.
- `sellsPass`: `features.passProducts` from `config/environments/*.properties` (false everywhere today).

## Flow

1. **Products**: `Product.products(for:)` with the Android ids: `osiris_crystals_starter`,
   `osiris_crystals_adventurer`, `osiris_crystals_champion`; plus `osiris_founder_pack`,
   `osiris_pass_monthly`, `osiris_pass_annual` only when `sellsPass` is true (hidden, as on Android).
2. **Buy**: `product.purchase(options: [.appAccountToken(token)])`. No purchase starts while signed out.
3. **Verify, then finish**: every transaction (purchase result, `Transaction.updates`,
   `Transaction.unfinished`, `Transaction.currentEntitlements`) sends its `jwsRepresentation` to the
   server. `transaction.finish()` runs only after the server answers 200. On any error the
   transaction stays unfinished and StoreKit hands it back later.
4. **Retries**: at launch (`Transaction.updates` listener plus `Transaction.unfinished`), after each
   sign-in, and each time the store opens. Signed out, nothing is sent.
5. **Restore purchases** (App Review requires it): `AppStore.sync()`, then re-sends
   `Transaction.currentEntitlements` and anything unfinished. The server grants nothing twice.
6. The success banner shows the server's `crystals_credited` and `balance`, never app-side amounts.
7. Terms of Use and Privacy Policy links (`<api>/terms`, `<api>/privacy`) sit under the products; when
   a subscription is listed, the auto-renew text is shown too (guideline 3.1.2).

## Human steps

### 1. Apple Developer team and signing

1. Join the Apple Developer Program (organisation account if the seller should be the company).
2. **Certificates, Identifiers & Profiles > Identifiers**: register the App ID `osiris.fit`
   (explicit). In-App Purchase is on by default for every explicit App ID; no entitlement file needed.
3. Add the team to `ios_version/project.yml` under `targets.Osiris.settings.base`:
   `DEVELOPMENT_TEAM: <10-character team id>` (Membership page). Without it device, TestFlight and
   Archive builds fail to sign; the simulator works without it.

### 2. App Store Connect

1. **Business**: accept the Paid Apps agreement, fill in tax and banking. Until it is active, no
   product loads, not even in Sandbox (the store screen shows "The store is not available right now").
2. **Apps > +**: create the app with bundle id `osiris.fit`.
3. **Monetization > In-App Purchases**: create the three consumables with these exact ids and an
   English name, description, price and review screenshot each:

   | Product ID | Type | Name | Price |
   |---|---|---|---|
   | `osiris_crystals_starter` | Consumable | Starter Pouch (500 Mana Crystals) | $4.99 |
   | `osiris_crystals_adventurer` | Consumable | Adventurer's Cache (1,200 Mana Crystals) | $9.99 |
   | `osiris_crystals_champion` | Consumable | Champion's Hoard (2,600 Mana Crystals) | $19.99 |

   The crystal amounts are the server's (`CRYSTAL_PACKS`); keep the names in line with them.
4. Later, only together with `features.passProducts=true`: `osiris_founder_pack` (Non-Consumable) and
   a subscription group "Osiris Pass" holding `osiris_pass_monthly` (1 month) and `osiris_pass_annual`
   (1 year). The pass prices in `Osiris.storekit` ($4.99, $39.99) are placeholders for local testing.
5. Attach the products to the first app version you submit (the version page, "In-App Purchases and
   Subscriptions"). New products are reviewed only together with a binary.
6. **App Information > App Store Server Notifications**: Production and Sandbox URL
   `https://api.osiris.fit/api/v2/payments/app-store/notifications`, **Version 2**. Then follow
   steps 3 and 4 of "Setup" in `app-store-billing.md` (`APPLE_APP_STORE_ENVIRONMENT` on Render, test
   notification).
7. **Users and Access > Sandbox > Test Accounts**: create a Sandbox tester for device testing.

### 3. Build on a Mac

```sh
brew install xcodegen
cd ios_version && xcodegen          # writes Osiris.xcodeproj and the Osiris scheme
open Osiris.xcodeproj
```

- **Simulator, no App Store Connect needed**: Run. The scheme uses `Osiris.storekit`, so the store
  lists local products and buys instantly. The server rejects those transactions (they are signed by
  Xcode, not Apple), so expect "could not be confirmed" and an unfinished transaction: that tests the
  retry path. Debug > StoreKit > Manage Transactions shows and deletes them.
- **Device with a Sandbox tester**: Edit Scheme > Run > Options > StoreKit Configuration: None, so
  StoreKit talks to the Sandbox. Point the app at an API with Sandbox allowed
  (`APPLE_APP_STORE_ENVIRONMENT=Production,Sandbox`).
- **TestFlight / App Store**: Product > Archive (Release, which compiles `-Posiris.env=prod`), then
  Distribute App. TestFlight purchases use the Sandbox.

### 4. If it does not compile

The store is isolated: everything is in `Store/` plus a few lines in `RootView.swift`, one route in
`Navigator.swift` and one toolbar button in `ProfileView.swift`. Check in this order:

1. **`OsirisShared` symbols**: build the framework first (the pre-build script does), then look up
   `StoreSupport` and `StoreVerifyResult` in the generated header
   (`shared/presentation/build/xcode-frameworks/<config>/<sdk>/OsirisShared.framework/Headers/OsirisShared.h`).
   Expected Swift names: `graph.store()`, `appStoreAccountToken() -> String?`,
   `verifyAppStore(signedTransaction:) async throws -> StoreVerifyResult`, `sellsPass: Bool`,
   `StoreVerifyResult.finish`, `.verification`, `.error`; `PurchaseVerification.crystalsCredited` is
   `Int32` and `.balance` is `KotlinInt?`. If the async form is missing, the header has
   `verifyAppStoreSignedTransaction:completionHandler:`; wrap it in `withCheckedThrowingContinuation`.
2. **Main actor**: `CrystalStore` is `@MainActor` with a `nonisolated init` (RootView builds it in
   its own init). If Xcode reports an isolation error there, drop `nonisolated` and mark
   `RootView.init` `@MainActor`.
3. **Name clashes**: StoreKit's `Transaction` and `Product` are used unqualified. If a shared Kotlin
   class with the same name appears later, write `StoreKit.Transaction` / `StoreKit.Product`.
4. **Quick way out**: delete the toolbar button in `ProfileView.swift`, `case store` and its
   destination in `Navigator.swift`, the `store` lines in `RootView.swift`, and the `Store/` folder.
   The rest of the app does not depend on them.

## Known limits

- No "Manage subscription" link yet (`AppStore.showManageSubscriptions`); add it with the pass.
- No crystal balance on the store screen; the banner shows the balance after a purchase.
- A purchase whose verify keeps failing (400, 404, 409) stays unfinished and is resent at each launch
  and sign-in; it grants nothing. Apple refunds nothing automatically for it: handle by support.
- StoreKit's own local verification is not trusted; the server checks Apple's signature itself.
