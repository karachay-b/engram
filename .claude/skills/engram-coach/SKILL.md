---
name: engram-coach
description: Learning telemetry, strategy, and schedule — retention stats, calibration, grader audit, n-of-1 experiments, HTML dashboard. Use for "how am I doing", weekly check-ins, strategy questions, auditing the grader, or adjusting how Engram teaches.
argument-hint: [dashboard | audit | experiment | refit | schedule]
---

# Engram — the adaptation loop

This is a thin alias. The real skill is `skills/coach/SKILL.md` in this repository —
kept unmodified so upstream updates (`git merge upstream/main`) never conflict.

**Do this now, before anything else.** Run this block — it locates the checkout and
loads the shared environment. Neither `$CLAUDE_PROJECT_DIR` (never reaches the Bash
tool) nor `git rev-parse` (empty when the session's cwd is the parent of both
checkouts) is dependable on its own, so do not shorten it to either:

```bash
_env=""
for d in "${ENGRAM_ROOT:-}" "${CLAUDE_PROJECT_DIR:-}" "$PWD" \
         "$(git rev-parse --show-toplevel 2>/dev/null)" /home/user/engram "$HOME/engram"; do
  [ -n "$d" ] && [ -f "$d/.claude/hooks/engram-env.sh" ] && _env="$d/.claude/hooks/engram-env.sh" && break
done
if [ -z "$_env" ]; then
  echo "engram: Checkout nicht gefunden — ENGRAM_ROOT auf das engram-Verzeichnis setzen." >&2
else
  _preset="${ENGRAM_HOME:-}"
  . "$_env"
  [ -n "$_preset" ] || echo "engram: WARNUNG — der Auto-Save-Hook läuft in dieser Session nicht. Am Ende 'bash $ENGRAM_ROOT/.claude/hooks/engram-save.sh' ausführen, sonst geht der Lernstand verloren." >&2
fi
echo "ENGRAM_ROOT=${ENGRAM_ROOT:-<leer>}  ENGRAM_HOME=${ENGRAM_HOME:-<leer>}"
```

The warning is precise, not a blanket disclaimer: `session-start.sh` publishes
`ENGRAM_HOME` through `$CLAUDE_ENV_FILE`, so the variable arriving already set is proof
that the hooks are registered — and its absence is proof that they are not.

Then:

1. **Read `$ENGRAM_ROOT/skills/coach/SKILL.md` in full.**
2. Follow it verbatim, from its first instruction — including the engine-resolver
   bash block, which must be run as written and not replaced by a guessed path. It
   resolves on `$ENGRAM_ROOT`, which the block above exported.

Do not summarize, paraphrase, or shortcut that file. It is the skill; this file is
only a stable, collision-free name for it.

**Cloud specifics for this repository** — read `$ENGRAM_ROOT/CLAUDE.md` for the full rules:

- `ENGRAM_HOME` points into the private `engram-learning` checkout, not
  `~/.claude/learning`. The block above set it. If a later call runs in a shell that
  lost it, re-run that block rather than guessing a path — the engine otherwise falls
  back silently to the container-volatile `~/.claude/learning`. Take the real path
  from `python3 "$ENGRAM" doctor` (`home` field) and never print `~/.claude/learning`
  literally.
- `coach dashboard` writes `artifacts/dashboard.html` inside that checkout. In this
  cloud environment there is no browser: after generating it, offer to send the file
  to the user or publish it, rather than telling them to "open it locally".
- Learning state only survives this container if it is committed and pushed to the
  `engram-learning` repo. The Stop hook does that automatically **only where it is
  registered**, which is not every session — the block above says so when it is not.
  In that case run `bash "$ENGRAM_ROOT/.claude/hooks/engram-save.sh"` yourself before
  the session ends. If the hook does run but reports a failed push, push manually.
