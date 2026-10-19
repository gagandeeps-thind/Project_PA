# Environment configuration

Configuration lives here, not in code. Each file is one environment; the build compiles the one
selected by the Gradle property `osiris.env` (default `dev`, set in `gradle.properties`) into
`shared/core` as `GeneratedEnv`, and the apps read it through `AppConfig`.

| File | Use |
|---|---|
| `dev.properties` | Local backend (emulator: `10.0.2.2`, simulator: `localhost`) |
| `staging.properties` | SIT / staging |
| `prod.properties` | Release builds |
| `local.properties` | Your machine's overrides; git-ignored, applied on top of the selected file |

Build for another environment: `./gradlew :android_version:app:assembleRelease -Posiris.env=prod`.
Xcode builds pass the same property through `OSIRIS_ENV` (see `ios_version/README.md`).

Secrets (API keys, signing passwords) never go in these files: they are compiled into the app and
readable by anyone with the binary. The player app needs none; the backend keeps its own
`Osiris_backend/.env`, which is outside this mechanism.
