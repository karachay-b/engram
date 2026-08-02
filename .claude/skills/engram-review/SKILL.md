---
name: engram-review
description: Clear due memory reviews with free recall — the two-minute habit that makes learning permanent. Use when reviews are due, or the user wants to review, practice, or "do my engram reviews".
argument-hint: [quick | <topic>]
---

# Engram — the retention loop

This is a thin alias. The real skill is `skills/review/SKILL.md` in this repository —
kept unmodified so upstream updates (`git merge upstream/main`) never conflict.

**Do this now, before anything else.** Run this block — it locates the checkout and
loads the shared environment. Neither `$CLAUDE_PROJECT_DIR` (never reaches the Bash
tool) nor `git rev-parse` (empty when the session's cwd is the parent of both
checkouts) is dependable on its own, so do not shorten it to either:

```bash
_env=""
for d in "${ENGRAM_ROOT:-}" "${CLAUDE_PROJECT_DIR:-}" "$PWD" \
         "$(git rev-parse --show-toplevel 2>/dev/null)" /home/user/engram "$HOME/engram"; do
  [ -n "$d" ] || continue
  # Beide Marker verlangt: Ein Verzeichnis ist nur dann ein engram-Checkout, wenn
  # es auch die Engine trägt. Nur auf den Hook-Pfad hin zu sourcen würde ausführen,
  # was ein fremdes Repo zufällig unter diesem Namen mitbringt.
  [ -f "$d/scripts/engram.py" ] && [ -f "$d/.claude/hooks/engram-env.sh" ] || continue
  _env="$d/.claude/hooks/engram-env.sh"; break
done
if [ -z "$_env" ]; then
  echo "engram: Checkout nicht gefunden — ENGRAM_ROOT auf das engram-Verzeichnis setzen." >&2
else
  _hooks="${ENGRAM_HOOKS_ACTIVE:-}"
  . "$_env"
  [ -n "$_hooks" ] || echo "engram: WARNUNG — der Auto-Save-Hook läuft in dieser Session nicht. Am Ende 'bash $ENGRAM_ROOT/.claude/hooks/engram-save.sh' ausführen, sonst geht der Lernstand verloren." >&2
fi
echo "ENGRAM_ROOT=${ENGRAM_ROOT:-<leer>}  ENGRAM_HOME=${ENGRAM_HOME:-<leer>}"
```

The warning is precise, not a blanket disclaimer: `session-start.sh` publishes
`ENGRAM_HOOKS_ACTIVE` through `$CLAUDE_ENV_FILE` before it resolves anything, so the
variable arriving already set proves the hooks are registered — and both hooks come
from the same settings file, so it proves the auto-save runs. `ENGRAM_HOME` would not:
the bootstrap sets it itself, and it can also be supplied as a plain environment
variable, either of which would suppress the warning in a session that needs it.

Then:

1. **Read `$ENGRAM_ROOT/skills/review/SKILL.md` in full.**
2. Follow it verbatim, from its first instruction — including the engine-resolver
   bash block, which must be run as written and not replaced by a guessed path. It
   resolves on `$ENGRAM_ROOT`, which the block above exported.

Do not summarize, paraphrase, or shortcut that file. It is the skill; this file is
only a name that does not collide with Claude Code's built-in `/review`
(GitHub pull-request review), which stays reachable under its own name.

**Cloud specifics for this repository** — read `$ENGRAM_ROOT/CLAUDE.md` for the full rules:

- `ENGRAM_HOME` points into the private `engram-learning` checkout, not
  `~/.claude/learning`. The block above set it. If a later call runs in a shell that
  lost it, re-run that block rather than guessing a path — the engine otherwise falls
  back silently to the container-volatile `~/.claude/learning`. Take the real path
  from `python3 "$ENGRAM" doctor` (`home` field) and never print `~/.claude/learning`
  literally.
- Learning state only survives this container if it is committed and pushed to the
  `engram-learning` repo. The Stop hook does that automatically **only where it is
  registered**, which is not every session — the block above says so when it is not.
  In that case run `bash "$ENGRAM_ROOT/.claude/hooks/engram-save.sh"` yourself before
  the session ends. If the hook does run but reports a failed push, push manually.
- Never put learner free-text on a shell command line. Write JSON with the Write
  tool and pass `--file`, or pipe to `--json -` / `--production-file -`.
