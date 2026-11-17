# Environment configuration

Configuration lives here, not in code. Each file is one environment; the build compiles the one
selected by the Gradle property `osiris.env` into `shared/core` as `GeneratedEnv`, and the apps read
it through `AppConfig`. Without the property the build uses `dev`, or `prod` when a release task is
requested. Android release tasks refuse any environment other than `prod`.

| File | Use |
|---|---|
| `dev.properties` | Local backend (emulator: `10.0.2.2`, simulator: `localhost`) |
| `staging.properties` | SIT / staging |
| `prod.properties` | Release builds |
| `local.properties` | Your machine's overrides; git-ignored, applied on top of the selected file. Ignored for `prod`, except `MAPBOX_ACCESS_TOKEN` |

Feature flags, required in every file:

| Flag | Meaning |
|---|---|
| `features.poseRecording` | Landmark recording for device QA; never in `prod` |
| `features.walletDemo` | The mock wallet tab (sample balances and methods); never in `prod` |
| `features.passProducts` | Osiris Pass subscriptions and the Founder Pack in the store. `false` in every file until they unlock real perks: the apps then neither query nor show them and sell crystal packs only |

Build for another environment: `./gradlew :android_version:app:assembleDebug -Posiris.env=staging`.
Xcode builds pass the same property through `OSIRIS_ENV` (see `ios_version/README.md`).

Secrets (API keys, signing passwords) never go in these files: they are compiled into the app and
readable by anyone with the binary. The player app needs none; the backend keeps its own
`Osiris_backend/.env`, which is outside this mechanism.
