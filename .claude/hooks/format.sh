#!/usr/bin/env bash
# PostToolUse (Edit|Write) hook: format the edited file only. Never blocks (always exit 0).
#
#   *.py              -> ruff format   (reads Osiris_backend/ruff.toml via hierarchical discovery)
#   *.dart            -> dart format   (skips generated *.g.dart / *.freezed.dart / *.mocks.dart)
#   *.ts/tsx/js/...   -> prettier      (only the project-local binary; never downloads)
#
# A missing formatter is a silent no-op. Run a one-time repo-wide format commit before
# enabling this, or every first edit to a file will rewrite the whole file.
input=$(cat)
if command -v jq >/dev/null 2>&1; then
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
else
  py=$(command -v python3 || command -v python) || exit 0
  file=$(printf '%s' "$input" | "$py" -c "import json,sys;print((json.load(sys.stdin).get('tool_input') or {}).get('file_path') or '')" 2>/dev/null)
fi
[ -n "$file" ] && [ -f "$file" ] || exit 0

# Only touch files inside the project.
root=${CLAUDE_PROJECT_DIR:-$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)}
[ -n "$root" ] && case "$(cd "$(dirname "$file")" && pwd -P)/" in "$(cd "$root" && pwd -P)/"*) ;; *) exit 0 ;; esac

run() { timeout 30 "$@" >/dev/null 2>&1; }

# Nearest node_modules/.bin/prettier walking up from the file, stopping at the project root.
find_prettier() {
  local d; d=$(cd "$(dirname "$file")" && pwd -P)
  while :; do
    [ -x "$d/node_modules/.bin/prettier" ] && { printf '%s' "$d/node_modules/.bin/prettier"; return 0; }
    [ "$d" = "/" ] || [ "$d" = "$(cd "$root" 2>/dev/null && pwd -P)" ] && return 1
    d=$(dirname "$d")
  done
}

case "$file" in
  *.g.dart|*.freezed.dart|*.mocks.dart|*.gr.dart|*.config.dart) ;;
  *.py)
    if command -v ruff >/dev/null 2>&1; then run ruff format --quiet "$file"
    elif command -v uv >/dev/null 2>&1; then run uv run --no-sync ruff format --quiet "$file"
    fi ;;
  *.dart)
    command -v dart >/dev/null 2>&1 && run dart format "$file" ;;
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.css|*.scss|*.html|*.vue|*.json)
    p=$(find_prettier) && run "$p" --write "$file" ;;
  *) ;;
esac
exit 0