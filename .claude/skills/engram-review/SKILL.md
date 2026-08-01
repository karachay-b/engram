---
name: engram-review
description: Clear due memory reviews with free recall — the two-minute habit that makes learning permanent. Use when reviews are due, or the user wants to review, practice, or "do my engram reviews".
argument-hint: [quick | <topic>]
---

# Engram — the retention loop

This is a thin alias. The real skill is `skills/review/SKILL.md` in this repository —
kept unmodified so upstream updates (`git merge upstream/main`) never conflict.

**Do this now, before anything else:**

1. Resolve the repo root: `git rev-parse --show-toplevel` (or `$CLAUDE_PROJECT_DIR`).
2. **Read `<root>/skills/review/SKILL.md` in full.**
3. Follow it verbatim, from its first instruction — including the engine-resolver
   bash block, which must be run as written and not replaced by a guessed path.

Do not summarize, paraphrase, or shortcut that file. It is the skill; this file is
only a name that does not collide with Claude Code's built-in `/review`
(GitHub pull-request review), which stays reachable under its own name.

**Cloud specifics for this repository** — read `<root>/CLAUDE.md` for the full rules:

- `ENGRAM_HOME` points into the private `engram-learning` checkout, not
  `~/.claude/learning`. The variable often does not reach the Bash environment of
  cloud sessions — source `<root>/.claude/hooks/engram-env.sh` before the first
  engine call, or the engine silently falls back to the container-volatile
  `~/.claude/learning`. Take the real path from `python3 "$ENGRAM" doctor` (`home`
  field) and never print `~/.claude/learning` literally.
- Learning state only survives this container if it is committed and pushed to the
  `engram-learning` repo. The Stop hook does that automatically; if it reports a
  failure, push manually before the session ends.
- Never put learner free-text on a shell command line. Write JSON with the Write
  tool and pass `--file`, or pipe to `--json -` / `--production-file -`.
