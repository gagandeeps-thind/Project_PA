#!/usr/bin/env bash
# PreToolUse (Bash) hook: block danger-zone access, curl|sh, and pushes to main/master.
# Exit 2 blocks the command and shows the reason to Claude.
input=$(cat)
if command -v jq >/dev/null 2>&1; then
  cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
else
  cmd=$(printf '%s' "$input" | python -c "import json,sys;print((json.load(sys.stdin).get('tool_input') or {}).get('command') or '')")
fi
[ -n "$cmd" ] || exit 0

block() { echo "Blocked by .claude/hooks/guard.sh: $1. Ask a human (see CLAUDE.md > Danger zones)." >&2; exit 2; }

# Secrets: never read or write .env files (".venv" and "os.environ" do not match).
printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_])\.env([^[:alnum:]_]|$)' && block "command touches a .env secrets file"

# Remote script execution.
printf '%s' "$cmd" | grep -Eq '(curl|wget)[^|]*\|[[:space:]]*(sudo[[:space:]]+)?(ba|z|da|k)?sh([[:space:]]|$)' && block "piping a download into a shell"
printf '%s' "$cmd" | grep -Eq '(ba|z)?sh[[:space:]]+(-c[[:space:]]+)?["'\'']?(<\(|\$\()[[:space:]]*(curl|wget)' && block "executing a downloaded script"

# Pushes: never to main/master, never forced.
if printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])git[[:space:]]+push'; then
  printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+push.*([[:space:]:/]|^)(main|master)([[:space:]]|$)' && block "push to main/master"
  printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+push.*(--force|[[:space:]]-f([[:space:]]|$))' && block "force push"
  branch=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null)
  case "$branch" in main|master) block "push while on $branch" ;; esac
fi

printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])rm[[:space:]]+-[[:alpha:]]*(r[[:alpha:]]*f|f[[:alpha:]]*r)' && block "rm -rf"

# Migration authoring/rewinding is human-only; `alembic upgrade head` (CI step) stays allowed.
printf '%s' "$cmd" | grep -Eq 'alembic[[:space:]]+(revision|downgrade|stamp|merge)' && block "alembic revision/downgrade/stamp/merge"

# Other danger zones: read-only inspection is fine, anything else is blocked.
DANGER='alembic/versions|alembic\.ini|[[:alnum:]_]\.db([^[:alnum:]_]|$)|requirements\.lock\.txt|package-lock\.json|pubspec\.lock|\.github/workflows|Dockerfile|DEPLOY_RUNBOOK'
if printf '%s' "$cmd" | grep -Eq "$DANGER"; then
  readonly_cmd='^[[:space:]]*(git[[:space:]]+(diff|log|show|status|blame)|ls|cat|head|tail|grep|rg|wc|diff)([[:space:]]|$)'
  if ! printf '%s' "$cmd" | grep -Eq "$readonly_cmd" || printf '%s' "$cmd" | grep -Eq '>|;|&&|\|\||tee|xargs|sed[[:space:]]+-i'; then
    block "command touches a danger zone (migrations, lockfiles, DB, CI, Dockerfile, deploy runbook)"
  fi
fi
exit 0
