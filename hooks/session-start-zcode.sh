#!/usr/bin/env bash
# Engram re-anchor hook for ZCode (SessionStart).
# ZCode reads each plugin's stock hooks/hooks.json — but its hook runner consumes
# ONLY JSON output (flat additionalContext or hookSpecificOutput); plain SessionStart
# stdout is discarded, exactly like DeepSeek Harness. This wrapper emits the
# hookSpecificOutput.additionalContext shape so the same nudge that reaches Claude
# Code users as two lines reaches ZCode sessions at all. Prints nothing (valid:
# silent) when no reviews are due; degrades to silence on any failure (art. 8).
#
# Double-nudge guard: hooks/hooks.json also carries the stock session-start.sh, and
# under Claude Code / Codex / OpenClaw's codex bundle THAT entry already delivers the
# nudge — those runtimes inject plain stdout, so here we exit before emitting a second
# copy. Under ZCode every plugin context sets ZCODE_PLUGIN_ROOT (alongside the legacy
# CLAUDE_PLUGIN_ROOT), which is why it is checked FIRST. The fallback branch below is
# the config-file route (a clone wired through ~/.zcode/cli/config.json), where no
# plugin-root env var exists.
set -u
command -v python3 >/dev/null 2>&1 || exit 0
ROOT="${ZCODE_PLUGIN_ROOT:-}"
if [ -z "$ROOT" ] && [ -n "${CLAUDE_PLUGIN_ROOT:-}${CODEX_PLUGIN_ROOT:-}" ]; then
  # A plain-stdout runtime reading the shared hooks.json — it already ran
  # session-start.sh; do not duplicate the nudge here.
  exit 0
fi
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
