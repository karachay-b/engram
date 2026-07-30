---
name: engram-coach
description: Learning telemetry, strategy, and schedule — retention stats, calibration, grader audit, n-of-1 experiments, HTML dashboard. Use for "how am I doing", weekly check-ins, strategy questions, auditing the grader, or adjusting how Engram teaches.
argument-hint: [dashboard | audit | experiment | refit | schedule]
---

# Engram — the adaptation loop

This is a thin alias. The real skill is `skills/coach/SKILL.md` in this repository —
kept unmodified so upstream updates (`git merge upstream/main`) never conflict.

**Do this now, before anything else:**

1. Resolve the repo root: `git rev-parse --show-toplevel` (or `$CLAUDE_PROJECT_DIR`).
2. **Read `<root>/skills/coach/SKILL.md` in full.**
3. Follow it verbatim, from its first instruction — including the engine-resolver
   bash block, which must be run as written and not replaced by a guessed path.

Do not summarize, paraphrase, or shortcut that file. It is the skill; this file is
only a stable, collision-free name for it.

**Cloud specifics for this repository** — read `<root>/CLAUDE.md` for the full rules:

- `ENGRAM_HOME` points into the private `engram-learning` checkout, not
  `~/.claude/learning`. Take the real path from `python3 "$ENGRAM" doctor` (`home`
  field) and never print `~/.claude/learning` literally.
- `coach dashboard` writes `artifacts/dashboard.html` inside that checkout. In this
  cloud environment there is no browser: after generating it, offer to send the file
  to the user or publish it, rather than telling them to "open it locally".
- Learning state only survives this container if it is committed and pushed to the
  `engram-learning` repo. The Stop hook does that automatically; if it reports a
  failure, push manually before the session ends.
