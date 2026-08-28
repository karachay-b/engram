#!/usr/bin/env bash
# Engram re-anchor hook: surfaces due reviews at session start.
# ONE registration (hooks/hooks.json), consumed differently per platform:
#   - Claude Code / Codex / OpenClaw's codex bundle inject PLAIN stdout into
#     context, so default output stays plain text.
#   - ZCode discards plain SessionStart stdout — its runner parses ONLY JSON
#     (hookSpecificOutput.additionalContext). Its plugin context also exports
#     ZCODE_PLUGIN_ROOT alongside the legacy CLAUDE_PLUGIN_ROOT, so that var is
#     both the runtime tell AND a working root: when present, emit the JSON
#     shape ZCode actually reads. Root resolution never assumes which of the
#     platform roots identified the runtime correctly, because they all point
#     at the same install path.
#   - The manual/config-file route has no plugin-root variable at all; users
#     who wire this script by hand set ENGRAM_HOOK_FORMAT=json themselves
#     (INSTALL-ZCODE.md documents exactly that command line).
# Prints at most two lines (or nothing) — ambient, never nagging (art. 8).
# Must never break a session: degrade to silence on any failure.
# Portable across Claude Code and Codex: uses the plugin-root env var if set,
# else self-resolves relative to this script's own location.
set -u
command -v python3 >/dev/null 2>&1 || exit 0
emit_json() {
  python3 - "$1" <<'PY' 2>/dev/null || true
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
}
ROOT="${ZCODE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-}}}"
if [ -z "$ROOT" ] || [ ! -f "$ROOT/scripts/engram.py" ]; then
  ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd)"
fi
[ -f "$ROOT/scripts/engram.py" ] || exit 0
NUDGE="$(python3 "$ROOT/scripts/engram.py" session-start 2>/dev/null || true)"
[ -n "$NUDGE" ] || exit 0                                   # silent when nothing is due —
case "${ENGRAM_HOOK_FORMAT:-}" in                           # valid output on every consumer
  json) emit_json "$NUDGE"; exit 0 ;;
esac
if [ -n "${ZCODE_PLUGIN_ROOT:-}" ]; then                    # ZCode eats plain text; give it
  emit_json "$NUDGE"                                        # the one shape it will parse
  exit 0
fi
printf '%s\n' "$NUDGE"
exit 0
