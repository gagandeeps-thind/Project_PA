#!/usr/bin/env bash
# Stop hook: CI-derived quality gate (.github/workflows/ci.yml + documented app checks).
# Exit 2 hands the failure back to Claude; exit 0 lets it stop.
# A component (backend / admin web / customer app) is only re-checked when its working-tree
# diff differs from the last diff that passed, so turns with no code changes stay fast.
set -o pipefail
cd "$CLAUDE_PROJECT_DIR" || exit 0

input=$(cat)
json_get() {
  if command -v jq >/dev/null 2>&1; then jq -r "$1 // empty"
  else python -c "import json,sys;v=json.load(sys.stdin);[v:=(v or {}).get(k) for k in sys.argv[1].lstrip('.').split('.')];print('' if v is None else (str(v).lower() if isinstance(v,bool) else v))" "$1"
  fi
}
[ "$(printf '%s' "$input" | json_get '.stop_hook_active')" = "true" ] && exit 0

PY=python
[ -x "$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe" ] && PY="$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe"
[ -x "$CLAUDE_PROJECT_DIR/.venv/bin/python" ] && PY="$CLAUDE_PROJECT_DIR/.venv/bin/python"
BIN=$(dirname "$PY")
RUFF=ruff; [ -x "$BIN/ruff.exe" ] && RUFF="$BIN/ruff.exe"; [ -x "$BIN/ruff" ] && RUFF="$BIN/ruff"

# Same deterministic test env as CI.
export OSIRIS_JWT_SECRET=ci-fixed-secret-not-for-production-use-only OSIRIS_ENV=test OSIRIS_LOG_JSON=1

STAMPS="$(git rev-parse --git-dir)/claude-gate"
mkdir -p "$STAMPS"
LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT

fingerprint() {
  { git diff HEAD -- "$1"
    git ls-files -z -o --exclude-standard -- "$1" | xargs -0 -r git hash-object --
  } 2>/dev/null | git hash-object --stdin
}
needs_check() {
  local fp; fp=$(fingerprint "$1")
  [ "$fp" != "$(cat "$STAMPS/$2" 2>/dev/null)" ]
}
mark_passed() { fingerprint "$1" >"$STAMPS/$2"; }

run() {
  local dir=$1; shift
  echo "== [$dir] $*" >>"$LOG"
  if ! (cd "$dir" && "$@") >>"$LOG" 2>&1; then
    echo "GATE FAILED: [$dir] $*" >&2
    tail -n 60 "$LOG" >&2
    exit 2
  fi
}

BACKEND_TESTS="test_ml_referee test_v2_10_flows test_phase2_security test_phase3_stripe test_phase2_ledger
test_replay_guard test_party_stats test_run_release test_challenge_release test_growth_core_loop
test_growth_sharing test_growth_communities test_growth_safety"

check_backend=0; check_admin=0; check_customer=0
needs_check Osiris_backend backend && check_backend=1
needs_check Osiris_admin_web admin && check_admin=1
needs_check Osiris_customer customer && check_customer=1

# Fastest first.
[ $check_backend = 1 ] && run Osiris_backend "$RUFF" check .                 # lint, <1s
[ $check_admin = 1 ] && run Osiris_admin_web npm run build                   # tsc typecheck + vite build, ~6s
[ $check_customer = 1 ] && run Osiris_customer flutter test                  # ~8s
if [ $check_backend = 1 ]; then                                              # ~80s
  run Osiris_backend "$PY" -m alembic upgrade head
  for t in $BACKEND_TESTS; do run Osiris_backend "$PY" "tests/$t.py"; done
  mark_passed Osiris_backend backend
fi
[ $check_admin = 1 ] && mark_passed Osiris_admin_web admin
if [ $check_customer = 1 ]; then
  run Osiris_customer flutter analyze                                        # ~110s
  mark_passed Osiris_customer customer
fi
exit 0
