#!/usr/bin/env bash
# Proves the Kotlin (shared/domain) and Dart (Osiris_customer) rep engines agree rep for rep:
# the Kotlin tests export a corpus of pose streams with their verdicts, then the Dart engine
# replays the same streams. Needs a Dart SDK on PATH (or DART=/path/to/dart).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
dart_bin="${DART:-dart}"
cd "$root"
./gradlew -q :shared:domain:jvmTest --tests '*EngineParityExportTest*'
"$dart_bin" run tools/parity/dart_engine_replay.dart "$root"
