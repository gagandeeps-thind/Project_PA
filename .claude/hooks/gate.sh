#!/usr/bin/env bash
# Stop hook: CI-derived quality gate (.github/workflows/ci.yml + documented app checks)
# plus security / production-readiness checks scoped to what changed.
# Exit 2 hands the failure back to Claude; exit 0 lets it stop.
# Expensive component checks re-run only when that component's working-tree diff differs from
# the last diff that passed. Diff-scoped checks (strict lint, secrets) run every stop; they are fast.
set -o pipefail
cd "$CLAUDE_PROJECT_DIR" || exit 0

MAX_ATTEMPTS=3   # gate re-runs after each fix; gives up (with a visible warning) after this many

input=$(cat)
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
json_get() {
  if command -v jq >/dev/null 2>&1; then jq -r "$1 // empty" 2>/dev/null
  else "$PY" -c "import json,sys;v=json.load(sys.stdin);[v:=(v or {}).get(k) for k in sys.argv[1].lstrip('.').split('.')];print('' if v is None else (str(v).lower() if isinstance(v,bool) else v))" "$1" 2>/dev/null
  fi
}

STAMPS="$(git rev-parse --git-dir 2>/dev/null)/claude-gate" || exit 0
mkdir -p "$STAMPS"

# Retry cap instead of "skip when stop_hook_active": the old early exit let Claude stop
# without the gate ever re-checking its fix.
if [ "$(printf '%s' "$input" | json_get '.stop_hook_active')" = "true" ]; then
  n=$(( $(cat "$STAMPS/attempts" 2>/dev/null || echo 0) + 1 ))
else
  n=1
fi
echo "$n" >"$STAMPS/attempts"
if [ "$n" -gt "$MAX_ATTEMPTS" ]; then
  printf '{"systemMessage":"Quality gate still failing after %s attempts; stopping anyway. Run .claude/hooks/gate.sh manually."}\n' "$MAX_ATTEMPTS"
  exit 0
fi

[ -x "$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe" ] && PY="$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe"
[ -x "$CLAUDE_PROJECT_DIR/.venv/bin/python" ] && PY="$CLAUDE_PROJECT_DIR/.venv/bin/python"
BIN=$(dirname "$PY")
RUFF=ruff; [ -x "$BIN/ruff.exe" ] && RUFF="$BIN/ruff.exe"; [ -x "$BIN/ruff" ] && RUFF="$BIN/ruff"
# Gradle needs a JDK; fall back to the one bundled with Android Studio.
JBR="/c/Program Files/Android/Android Studio/jbr"
[ -z "$JAVA_HOME" ] && ! command -v java >/dev/null 2>&1 && [ -d "$JBR" ] && export JAVA_HOME="$JBR"

# Same deterministic test env as CI.
export OSIRIS_JWT_SECRET=ci-fixed-secret-not-for-production-use-only OSIRIS_ENV=test OSIRIS_LOG_JSON=1

LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT

fail() { echo "GATE FAILED: $1" >&2; [ -n "$2" ] && printf '%s\n' "$2" | head -n 60 >&2; exit 2; }

fingerprint() {
  { git diff HEAD -- $1
    git ls-files -z -o --exclude-standard -- $1 | xargs -0 -r git hash-object --
  } 2>/dev/null | git hash-object --stdin
}
needs_check() { [ "$(fingerprint "$1")" != "$(cat "$STAMPS/$2" 2>/dev/null)" ]; }
mark_passed() { fingerprint "$1" >"$STAMPS/$2"; }

# Changed (modified/added/untracked, not deleted) files matching git pathspecs.
changed() {
  { git diff --name-only --diff-filter=d HEAD -- "$@"; git ls-files -o --exclude-standard -- "$@"; } 2>/dev/null |
    sort -u | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done
}

run() {
  local dir=$1; shift
  echo "== [$dir] $*" >>"$LOG"
  if ! (cd "$dir" && "$@") >>"$LOG" 2>&1; then
    fail "[$dir] $*" "$(tail -n 60 "$LOG")"
  fi
}

# Like run, but a network failure is a warning (not marked passed, so retried next stop).
run_net() {
  local dir=$1; shift
  local out; out=$(cd "$dir" && "$@" 2>&1) && return 0
  if printf '%s' "$out" | grep -qiE 'ENOTFOUND|EAI_AGAIN|ECONNRE|ETIMEDOUT|network|connection (error|refused)|Max retries exceeded|audit endpoint'; then
    echo "gate: skipped [$dir] $* (network unavailable)" >&2; return 1
  fi
  fail "[$dir] $*" "$(printf '%s' "$out" | tail -n 60)"
}

# ---------- 1. Secrets & key material (every stop, diff-only, <1s) ----------
SECRET_RE='AKIA[0-9A-Z]{16}|(sk|rk)_live_[0-9A-Za-z]{10,}|whsec_[0-9A-Za-z]{20,}|-----BEGIN ([A-Z]+ )?PRIVATE KEY-----|gh[pousr]_[0-9A-Za-z]{36}|xox[abprs]-[0-9A-Za-z-]{10,}'
hits=$( { git diff HEAD -U0 --no-color 2>/dev/null | grep -E '^\+' | grep -v '^+++'
          changed . | grep -vE '(^|/)(package-lock\.json|.*\.lock)$' | tr '\n' '\0' | xargs -0 -r grep -IEHn -- "$SECRET_RE" 2>/dev/null
        } | grep -E -- "$SECRET_RE" | grep -v 'gate:allow-secret' )
[ -n "$hits" ] && fail "possible secret in changed code. Move it to env/secret store (or mark a test fixture line 'gate:allow-secret')." "$hits"

keyfiles=$(changed . | grep -E '(^|/)\.env(\.[^/]+)?$|\.(pem|key|p12|pfx|jks|keystore)$' | grep -vE '\.(example|sample|template)$')
[ -n "$keyfiles" ] && fail "env/key files must not be committed; add them to .gitignore." "$keyfiles"

# ---------- 2. Strict backend lint on changed source (every stop, <1s) ----------
# S = bandit security rules (SQL injection, verify=False, missing request timeouts, hardcoded creds,
#     unsafe yaml/pickle/subprocess), ASYNC = blocking calls inside async handlers (kills throughput
#     under load), B = bugbear, BLE = blind except, T20 = print() instead of structured logging.
# Applied only to changed non-test files so existing code doesn't block unrelated work.
mapfile -t py_changed < <(changed 'Osiris_backend/*.py' | grep -v '^Osiris_backend/tests/')
if [ ${#py_changed[@]} -gt 0 ]; then
  run . "$RUFF" check --extend-select S,ASYNC,B,BLE,T20 "${py_changed[@]}"
fi

# ---------- 3. Component checks (fingerprinted) ----------
BACKEND_TESTS="test_ml_referee test_v2_10_flows test_phase2_security test_phase3_stripe test_phase2_ledger
test_replay_guard test_party_stats test_run_release test_challenge_release test_growth_core_loop
test_growth_sharing test_growth_communities test_growth_safety test_exercise_sessions test_settings test_growth_hub test_support_chat test_public_base_url test_origin_guard test_rate_limits"
BACKEND_DEPS="Osiris_backend/requirements*.txt Osiris_backend/pyproject.toml Osiris_backend/*.lock"
ADMIN_DEPS="Osiris_admin_web/package.json Osiris_admin_web/package-lock.json"
KMP_PATHS="shared android_version build.gradle.kts gradle config"

check_backend=0; check_admin=0; check_kmp=0; check_pydeps=0; check_npmdeps=0
needs_check Osiris_backend backend && check_backend=1
needs_check Osiris_admin_web admin && check_admin=1
needs_check "$KMP_PATHS" kmp && check_kmp=1
needs_check "$BACKEND_DEPS" pydeps && check_pydeps=1
needs_check "$ADMIN_DEPS" npmdeps && check_npmdeps=1

# Fastest first.
[ $check_backend = 1 ] && run Osiris_backend "$RUFF" check .                 # lint, <1s
[ $check_admin = 1 ] && run Osiris_admin_web npm run build                   # tsc typecheck + vite build, ~6s
if [ $check_backend = 1 ]; then                                              # ~80s
  run Osiris_backend "$PY" -m alembic upgrade head
  # Model changes without a migration = schema drift in prod. Needs alembic>=1.9.
  run Osiris_backend "$PY" -m alembic check
  for t in $BACKEND_TESTS; do run Osiris_backend "$PY" "tests/$t.py"; done
  mark_passed Osiris_backend backend
fi
[ $check_admin = 1 ] && mark_passed Osiris_admin_web admin

# Known-CVE dependency audit, only when dependency manifests change (network).
if [ $check_pydeps = 1 ]; then
  "$PY" -c 'import pip_audit' 2>/dev/null ||
    fail "pip-audit missing: run '$PY -m pip install pip-audit' (dev-only tool)."
  run_net Osiris_backend "$PY" -m pip_audit --progress-spinner off && mark_passed "$BACKEND_DEPS" pydeps
fi
if [ $check_npmdeps = 1 ] && [ -f Osiris_admin_web/package-lock.json ]; then
  run_net Osiris_admin_web npm audit --omit=dev --audit-level=high && mark_passed "$ADMIN_DEPS" npmdeps
fi

if [ $check_kmp = 1 ]; then                                                  # ~3 min cold
  run . ./gradlew --console=plain -q detekt :shared:core:jvmTest :shared:domain:jvmTest :shared:data:jvmTest :shared:presentation:jvmTest
  mark_passed "$KMP_PATHS" kmp
fi

rm -f "$STAMPS/attempts"
exit 0