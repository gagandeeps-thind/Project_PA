# Osiris for iOS

SwiftUI app on top of the shared Kotlin code (`shared/`), which Swift imports as the
`OsirisShared` framework. All business logic, networking, storage and screen state live in
`shared/`; this folder only renders state and adapts iOS services.

**Status: skeleton, not yet built.** It has the app entry, session routing, sign-in and the
Today screen. The other screens follow the Android app (`android_version/app/.../ui/`) one to
one, each wrapping its shared view model with `Observed`. The Swift code has not been compiled:
it needs a Mac with Xcode. The shared Kotlin code does compile for iOS (`iosArm64`,
`iosSimulatorArm64`) on any machine.

## Build (on a Mac)

```sh
brew install xcodegen
cd ios_version && xcodegen          # writes Osiris.xcodeproj from project.yml
open Osiris.xcodeproj               # Run builds OsirisShared through Gradle first
```

The dev environment points the simulator at `http://localhost:8000`. Choose another with
`-Posiris.env=staging` (see `config/environments/`).

## How Swift talks to the shared code

- `AppGraph` is created once in `OsirisApp`; screens call `graph.login()`, `graph.today()`, …
- `Observed<VM, State>` subscribes to the view model's `state` and `message` flows
  (`FlowWatchKt.watch`) on the main thread and calls `vm.clear()` when released.
- Kotlin sealed types arrive as classes: check them with `is` / `as` (`AuthStateSignedIn`,
  `LoadableReady`, `LoadableFailed`).

## Screens

| Screen | Shared view model | iOS |
|---|---|---|
| Sign-in | `LoginViewModel` | done |
| Today | `TodayViewModel` | done (no nav grid yet) |
| Onboarding | `OnboardingViewModel` | to do |
| Run (MapKit, Core Location) | `RunViewModel` | to do |
| Challenges, detail, my courses | `ChallengeBoard/Detail/CoursesViewModel` | to do |
| Clubs, club, rankings | `Communities/CommunityDetail/RankingsViewModel` | to do |
| Progress, settings | `ProgressViewModel`, `SettingsViewModel` | to do |
| Exercise hub, camera (Vision body pose) | `ExerciseHub/ExerciseSessionViewModel` | to do |
