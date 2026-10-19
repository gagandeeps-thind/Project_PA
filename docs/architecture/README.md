# Player app architecture (Kotlin Multiplatform)

The player app is Kotlin Multiplatform. Both phones run the same business logic from `shared/`;
each platform only draws screens and adapts its own services (GPS, camera, share sheet, secure
storage). The earlier Flutter app (`Osiris_customer/`) was retired on 2026-10-19 after the native
apps reached parity; it remains in git history.

```
config/environments/   dev | staging | prod .properties  →  GeneratedEnv (compiled into shared/core)
shared/
  core/          AppConfig, AppError, Outcome, Logger, Platform, secure ids          (no dependencies)
  domain/        models, repository interfaces, rep engine, Format, Daylight          → core
  data/          Ktor ApiClient + one service per area, repositories, SQLDelight,      → domain
                 settings / Keychain / Keystore, offline run queue, DataGraph
  presentation/  SharedViewModel + one StateFlow view model per screen, AppGraph,      → data
                 iOS framework "OsirisShared"
android_version/app/   Jetpack Compose UI + Android services                          → presentation
ios_version/           SwiftUI UI + iOS services (skeleton)                            → OsirisShared
Osiris_backend/        FastAPI server (one backend for both phones and the admin)
Osiris_admin_web/      admin console
```

Dependencies only point down the list. Nothing in `shared/` imports Android, iOS or UI code.

## Layers

**core.** `AppError` is the only error type above the network: `Offline`, `Timeout`,
`Unauthorized`, `Http(status, detail)`, `InvalidResponse`, `Storage`, `Validation`, `Permission`,
`Unexpected`. Each carries a `userMessage` that is safe to show. `Outcome<T>` is `Success` or
`Failure(AppError)`; `outcomeOf {}` converts exceptions and rethrows cancellation.

**domain.** Plain models (kotlinx-serialization) and the repository interfaces screens depend on
(`AuthRepository`, `PlayerRepository`, `RunRepository`, `ChallengeRepository`,
`CommunityRepository`, `PrivacyRepository`, `ExerciseRepository`). The rep engine counts camera
exercise reps from pose frames; it is was verified bit-for-bit against the retired Dart
engine (72/72) before the Flutter app was removed.

**data.** `ApiClient` owns the HTTP client: base URL and timeouts from `AppConfig`, the bearer
token, JSON, and mapping every failure to an `AppError` (a 401 signs the player out). Endpoints
are grouped in `network/api/` (`AuthApi`, `RunApi`, `ChallengeApi`, `MeApi`, `CommunityApi`,
`ExerciseApi`), so adding an endpoint is one method in one file. Repositories combine the API
with local state and return `Outcome`:
- Runs are saved point by point in settings and uploaded in batches; an interrupted run resumes,
  a 409 resyncs from the server's point count, and finishing offline waits until points are sent.
- Exercise sets are stored in SQLDelight first and synced later; permanent rejections stop
  retrying, transient ones retry.
- The signed-in profile is cached so the app opens offline.
`DataGraph` wires everything by constructor injection from `PlatformDependencies`
(`AndroidPlatform.create`, `IosPlatform.create`, `JvmPlatform.create` for tests).

**presentation.** One view model per screen, built on `SharedViewModel`: a coroutine scope,
`state: StateFlow<…>` and `message: StateFlow<UiMessage?>`. Dialogs, share requests and
navigation requests are part of the state, not one-shot events, so nothing is lost on rotation
or when SwiftUI re-renders. `Loadable<T>` (`Loading`, `Ready`, `Failed(message, canRetry)`) is
the shape of every loaded screen. `AppGraph` is the composition root both apps create once.

**Navigation and design.** `AppNavigatorViewModel` is the route guard at the app root:
`RootState` is the permission primer on first launch, sign-in, or the tabbed app, and a restored
session goes straight to Home. `DeepLinkParser` accepts `osiris://…` and the backend's public
`https://<links.webHost>/i/…` and `/join/…` pages only; a link opened while signed out waits for
sign-in, and invite/referral links prefill account creation. FrostMatte design tokens live in
`shared/core` (`FrostMatte`), so Compose (Haze backdrop blur, matte fallback below Android 12) and
SwiftUI (system materials) draw from one set of values. The tabs are Home, Discover, Social, Wallet and Profile; Wallet exists only
in builds with `features.walletDemo` (dev, staging), backed by `MockWalletRepository`: card and bank
entry stand in for the payment provider's own sheet, so no card number ever reaches the app.

**Android.** `rememberShared { graph.today() }` keeps a view model in an androidx `ViewModel`
and clears it with the screen. Screens collect `state` with `collectAsStateWithLifecycle`.
Platform adapters live in `platform/`: fused location and the run foreground service, CameraX +
ML Kit pose, permissions, share sheet.

**iOS.** `Observed<VM, State>` wraps a view model as an `ObservableObject` using
`StateFlow.watch` from `presentation/src/iosMain`. See `ios_version/README.md`.

## Configuration

`config/environments/<env>.properties` holds the API base URL per platform, timeouts, logging
and feature flags. The build reads the file chosen by `-Posiris.env=dev|staging|prod` (default
`dev`) and generates `GeneratedEnv`. Machine-specific overrides go in
`config/environments/local.properties` (git-ignored). No secrets belong in these files: the
apps hold none, and the backend keeps its own in `Osiris_backend/.env`.

## Testing

| What | Command |
|---|---|
| All shared tests (JVM) | `./gradlew :shared:core:jvmTest :shared:domain:jvmTest :shared:data:jvmTest :shared:presentation:jvmTest` |
| iOS type-check | `./gradlew :shared:presentation:compileKotlinIosSimulatorArm64` |
| Android build (needs SDK) | `./gradlew :android_version:app:assembleDebug` |

`shared/data` tests run the real repositories against a Ktor `MockEngine` (`FakeServer`), and
`ContractTest` checks every endpoint path and model against `Documentation/openapi.json`, so a
server change that breaks the app fails here. View model tests use fake repositories and a test
dispatcher.

## Adding a feature

1. Model and repository method in `shared/domain`.
2. Endpoint in the matching `network/api/*Api.kt`, implementation in the repository, a
   `FakeServer` test; `ContractTest` covers the path and shape.
3. View model in `shared/presentation` with state, a factory in `AppGraph`, and a test.
4. A Compose screen in `android_version/app/.../ui/<area>/` and a SwiftUI view in
   `ios_version/Osiris/Sources/<Area>/`, both only rendering state and calling the view model.
