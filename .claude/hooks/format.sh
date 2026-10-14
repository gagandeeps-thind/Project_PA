#!/usr/bin/env bash
# PostToolUse (Edit|Write) hook: format the edited file only. Never blocks (always exit 0).
#
# No formatter is adopted in this repo yet: Osiris_backend/ruff.toml explicitly defers
# formatting to "a future `ruff format` pass", and neither the Flutter apps nor the admin
# web define a format command. Add a case below once a formatter is adopted.
input=$(cat)
if command -v jq >/dev/null 2>&1; then
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
else
  file=$(printf '%s' "$input" | python -c "import json,sys;print((json.load(sys.stdin).get('tool_input') or {}).get('file_path') or '')" 2>/dev/null)
fi
[ -n "$file" ] && [ -f "$file" ] || exit 0

case "$file" in
  # *.py)   <formatter> "$file" ;;
  *) ;;
esac
exit 0
