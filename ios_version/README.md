# Osiris for iOS

SwiftUI app on top of the shared Kotlin code (`shared/`), which Swift imports as the
`OsirisShared` framework. All business logic, networking, storage and screen state live in
`shared/`; this folder only renders state and adapts iOS services.

**Status: every player screen written, not yet compiled.** The screens follow the Android app
(`android_version/app/.../ui/`) one to one in copy and behaviour, each wrapping its shared view
model with `Observed`. The Swift code has not been compiled or run: it needs a Mac with Xcode.
The shared Kotlin code does compile for iOS (`iosArm64`, `iosSimulatorArm64`) on any machine.

## Build (on a Mac)

```sh
brew install xcodegen
cd ios_version && xcodegen          # writes Osiris.xcodeproj from project.yml
open Osiris.xcodeproj               # Run builds OsirisShared through Gradle first
```

The dev environment points the simulator at `http://localhost:8000`. Choose another with
`-Posiris.env=staging` (see `config/environments/`).

## Design system

FrostMatte tokens (colors, blur, radii, spacing) come from the shared core (`FrostMatte`), so both apps
use one set of values. `Common/Frost.swift` maps them to SwiftUI: `FrostBackground` and `.frostCard()`
(system `.ultraThinMaterial` blur plus the token fill, hairline and shadow).
Type is Manrope and Geist Mono, the same files as Android (`android_version/app/src/main/res/font/`,
added to the bundle by `project.yml` and registered with `UIAppFonts`): `FrostFont` sets each
weight on the variable `wght` axis, and `HeroMetric` is the 72 pt focal number.

## How Swift talks to the shared code

- `AppGraph` is created once in `OsirisApp`; screens call `graph.login()`, `graph.today()`, …
- `Observed<VM, State>` subscribes to the view model's `state` and `message` flows
  (`FlowWatchKt.watch`) on the main thread and calls `vm.clear()` when released.
- Kotlin sealed types arrive as classes: check them with `is` / `as` (`AuthStateSignedIn`,
  `LoadableReady`, `LoadableFailed`).

## Screens

| Screen | Shared view model | iOS |
|---|---|---|
| Root: primer, sign-in or tabs; `osiris://` links | `AppNavigatorViewModel` | `App/RootView.swift` |
| Permission primer (before sign-in, each one optional) | `PermissionPrimerViewModel` | `Permission/PermissionPrimerView.swift` |
| Sign-in | `LoginViewModel` | `Session/LoginView.swift` |
| Onboarding (goal, location, account) | `OnboardingViewModel` | `Session/OnboardingView.swift` |
| Home (Today) and shortcuts to screens without a tab | `TodayViewModel` | `Today/TodayView.swift` |
| Run (MapKit, Core Location, every run dialog) | `RunViewModel` | `Run/RunView.swift`, `Run/LocationTracker.swift`, `Map/RunMap.swift` |
| Challenges, challenge, my courses | `ChallengeBoard/ChallengeDetail/CoursesViewModel` | `Challenge/*.swift` |
| Clubs, club, rankings (week, season) | `Communities/CommunityDetail/RankingsViewModel` | `Community/*.swift` |
| Discover: live, upcoming, community, finished; create button | `DiscoverViewModel` | `Discover/DiscoverView.swift` |
| Social: global distance, Pace Index, reps, rewards boards | `GlobalBoardsViewModel` | `Social/SocialView.swift` |
| Wallet (demo builds only, mock adapters) | `WalletViewModel` | `Wallet/WalletView.swift` |
| Profile: rank, XP gauge, metrics, badges | `ProfileViewModel` | `Profile/ProfileView.swift` |
| Live support chat (WebSocket stub) | `SupportChatViewModel` | `Support/SupportChatView.swift` |
| Settings (incl. two-step erase) | `SettingsViewModel` | `Settings/SettingsView.swift` |
| Bodyweight hub, consent, camera set | `ExerciseHub/ExerciseSessionViewModel` | `Exercise/*.swift` |

Each tab has its own `NavigationStack` driven by `Route` (`App/Navigator.swift`).

## Platform adapters

- **Location**: `LocationTracker` streams Core Location fixes with `CLLocation.timestamp` as
  `LocationFix.at` (built by `IosSupport.locationFix`). While recording it turns on background
  updates (the `location` background mode) with only "while in use" permission, like Android.
- **Map**: `RunMap` is an `MKMapView` (iOS 16 has no SwiftUI polyline overlays): course line,
  green start and red finish zones, the live trace and nearby challenge markers.
- **Camera set**: `PoseCamera` runs AVFoundation at VGA, portrait and unmirrored, and Apple
  Vision `VNDetectHumanBodyPoseRequest` synchronously on the capture queue, so one frame is in
  flight and late frames are dropped. Vision joints map to the 13 landmark names the shared
  rep engine reads (`nose`, `left_`/`right_` shoulder, elbow, wrist, hip, knee, ankle), in
  top-left image pixels, with Vision's confidence as the likelihood.
- `shared/presentation/src/iosMain/.../IosSupport.kt` holds the small Kotlin helpers Swift
  needs (building `LocationFix` from epoch millis, permission errors, local challenge times,
  loading an exercise from the catalog).
