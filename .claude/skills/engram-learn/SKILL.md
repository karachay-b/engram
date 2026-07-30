---
name: engram-learn
description: Learn any topic properly — first-principles curriculum, generation-first tutoring, verified free recall, FSRS scheduling. Use when the user wants to learn, understand, study, or continue studying something.
argument-hint: <topic> | continue
---

# Engram — the acquisition loop

This is a thin alias. The real skill is `skills/learn/SKILL.md` in this repository —
kept unmodified so upstream updates (`git merge upstream/main`) never conflict.

**Do this now, before anything else:**

1. Resolve the repo root: `git rev-parse --show-toplevel` (or `$CLAUDE_PROJECT_DIR`).
2. **Read `<root>/skills/learn/SKILL.md` in full.**
3. Follow it verbatim, from its first instruction — including the engine-resolver
   bash block, which must be run as written and not replaced by a guessed path.

Do not summarize, paraphrase, or shortcut that file. It is the skill; this file is
only a name that does not collide with the user's global `learn` skill.

**Cloud specifics for this repository** — read `<root>/CLAUDE.md` for the full rules:

- `ENGRAM_HOME` points into the private `engram-learning` checkout, not
  `~/.claude/learning`. Take the real path from `python3 "$ENGRAM" doctor` (`home`
  field) and never print `~/.claude/learning` literally.
- Learning state only survives this container if it is committed and pushed to the
  `engram-learning` repo. The Stop hook does that automatically; if it reports a
  failure, push manually before the session ends.
- Never put learner free-text on a shell command line. Write JSON with the Write
  tool and pass `--file`, or pipe to `--json -` / `--production-file -`.
