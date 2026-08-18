#!/usr/bin/env bash
# Engram re-anchor hook for DeepSeek Harness's Claude Code hook bridge.
# dsh's bridge consumes ONLY the JSON hookSpecificOutput.additionalContext
# shape — plain SessionStart stdout is discarded (documented dsh limitation),
# so this wrapper emits what Claude Code's JSON hook contract allows and dsh
# actually reads. Degrades to silence on any failure; prints nothing (valid:
# no output) when no reviews are due.
set -u
command -v python3 >/dev/null 2>&1 || exit 0
ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$ROOT" ] || [ ! -f "$ROOT/scripts/engram.py" ]; then
  ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd)"
fi
[ -f "$ROOT/scripts/engram.py" ] || exit 0
NUDGE="$(python3 "$ROOT/scripts/engram.py" session-start 2>/dev/null || true)"
[ -n "$NUDGE" ] || exit 0
python3 - "$NUDGE" <<'PY' 2>/dev/null || true
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
exit 0
