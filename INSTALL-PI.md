# Engram on Pi

Engram is an **omni-repo**: one codebase that runs on Claude Code, OpenAI Codex, OpenCode, Hermes Agent, Google Antigravity, OpenClaw — and [Pi](https://pi.dev), Earendil's minimal, extensible coding agent. The core is the same everywhere: `skills/` (Agent Skills `SKILL.md`) plus the dependency-free `scripts/engram.py`. This file covers the Pi-specific glue.

> Verified against **pi 0.83.0** (current) and **pi 0.74.2** (the `legacy-node20` line) on Linux — 20/20 harness checks on both. What was and wasn't proven is itemised in [honest status](#honest-status-of-the-pi-glue) — including the two things that need a live model and therefore aren't ticked.

Pi is the friendliest port so far. It reads the Agent Skills standard natively, its package manager understands a plain git repo, and its extension API has exactly the two hooks the nudge needs. There is no self-extract, no bundle-format trap, no manifest precedence puzzle — the whole port is one manifest key, one extension file, and three prompt templates.

## What ships for Pi

```
skills/                     # SHARED — the same three skills every platform uses
scripts/engram.py           # SHARED — the same engine, same state, same schedule
pi/engram.ts                # Pi extension: exports ENGRAM_ROOT + the due-review nudge
pi/prompts/                 # /learn, /review, /coach as Pi prompt templates
skills/_shared/subagents.md # how to spawn the blind assessor where no agent registry exists
agents/*.md                 # prompt sources the spawned children read
```

Wired up by the `pi` key in `package.json` — Pi reads `skills`, `extensions`, and `prompts` from it and ignores everything else in the repo.

## Requirements

- **pi ≥ 0.74** (earlier versions not tested; the extension uses `before_agent_start`'s injected-message return, which is present in 0.74.x).
- **Node ≥ 22.19** for current pi. On Node 20 (≥ 20.6), npm serves pi's `legacy-node20` line (0.74.2) instead — Engram is verified on both.
- **`python3`** on PATH (stock macOS/Linux is fine; the engine is stdlib-only).

## Install

```bash
pi install git:github.com/nagisanzenin/engram
```

That's the install. Pi clones the repo to `~/.pi/agent/git/github.com/nagisanzenin/engram`, runs `npm install` there (engram's extension has zero runtime dependencies — the install exists for the OpenCode half of the omni-repo), and registers the package in `~/.pi/agent/settings.json`. `pi update` tracks the default branch; pin with `@<tag>` if you want to stay put.

A local clone works too — `pi install /path/to/engram` adds the path without copying, which is the route for hacking on engram itself. `pi remove <source>` undoes either.

## Invoking the skills

| You want | Type |
|---|---|
| to learn a topic | `/learn <topic>` — or just say "teach me X" |
| a review session | `/review` |
| stats & coaching | `/coach` |

`/learn`, `/review`, and `/coach` are prompt templates that point the model at the corresponding skill. The skills are also first-class Agent Skills in Pi, which buys two more doors: `/skill:learn <topic>` invokes one explicitly, and the descriptions sit in the system prompt so natural language ("teach me Kalman filters") activates them without any command at all.

## The nudge

Engram's ambient re-anchor — "[engram] 7 reviews due · ~4 min" — is `pi/engram.ts`, auto-loaded from the package manifest:

- On **session start** (launch, `/new`, `--resume`) it runs `engram.py session-start`. If nothing is due, total silence.
- If reviews are due, you see one TUI notice immediately (the nudge's first line), and the full text is injected as a visible custom message alongside your **first prompt** (or the next one, if the engine was slow to answer — the probe never blocks startup), so the model knows what you know and can offer to `/review` (Constitution art. 8: ambient, never nagging — at most one nudge per session, and any failure degrades to silence, never repetition).
- It also exports `ENGRAM_ROOT` into Pi's process environment, which is how the skills' engine-resolution block finds `scripts/engram.py` from any bash call, wherever the package landed. **If your shell already exports `ENGRAM_ROOT`** (the dev-override convention on every platform), the extension respects it and the skills will use *that* checkout's engine — while the nudge always runs the installed package's own copy. Two checkouts, one store, is a versions-split you chose; unset the variable if you didn't mean to choose it.
- In non-interactive runs (`-p`, `--mode json`) and in spawned children (`ENGRAM_CHILD=1`) the extension is deliberately inert — see the next section for why that matters.

## The assessor (blind grading) on Pi

**This is the part that needs your attention**, because it is the part a careless port would quietly drop.

Pi ships no subagent mechanism — deliberately. So `engram-assessor`, `engram-curriculum-architect`, and `engram-artifact-smith` are **not registered** as agents here. What Pi does have is the one primitive isolation actually needs: **a fresh process is a fresh context.** The skills spawn the blind grader as a non-interactive pi run through the bash tool:

```bash
ENGRAM_CHILD=1 pi --no-session --no-skills --no-context-files -p \
  "Read <ENGRAM_ROOT>/agents/engram-assessor.md and follow it exactly.
   Grade the items in <path>. Write the receipt JSON to <receipt path>."
```

The child sees the agent file, the items file, and nothing else — no tutoring dialogue, no project context files, no skills, no nudge (`ENGRAM_CHILD=1` plus print mode keep engram's own extension silent in the child). The receipt comes back through a file, not stdout, because models garnish stdout with prose. The full contract, including why each flag is load-bearing and why extensions stay **on** (custom model providers arrive as extensions), is in [`skills/_shared/subagents.md`](skills/_shared/subagents.md).

Each spawned child bills as a normal `pi -p` run against your configured default model.

## Where state lives

`engram.py` keeps state in `~/.claude/learning` (override with `ENGRAM_HOME`). Learn in Claude Code at your desk, clear the reviews in pi after lunch — same schedule, one memory. This is the point of the omni-repo.

## Verify the install

```bash
python3 ~/.pi/agent/git/github.com/nagisanzenin/engram/scripts/engram.py selftest
                                    # 307/307 — same engine everywhere
pi config                           # engram listed, with skills/extension/prompts enabled
pi                                  # then type /  — learn, review, coach in the picker
```

## Honest status of the Pi glue

**Verified on pi 0.83.0 and pi 0.74.2** (Linux; 20/20 harness checks on each). The method: a mock OpenAI-compatible provider (`models.json` + a local server), so every payload pi was about to send a model could be captured and inspected, plus RPC mode for the interactive-equivalent paths. Every claim below is either one of the 20 checks or is labeled as a separate observation.

*Packaging* — `pi install` of this repo; manifest-driven discovery of exactly three skills (`learn`, `review`, `coach` — `_shared/` correctly ignored), the extension, and the three prompt templates. (`engram.py selftest` — 302/302 **at v1.11.0**, unchanged by the Pi port — is run alongside the harness, not one of its checks.)

*Skills* — all three present in the captured system prompt in Agent Skills XML form (`<available_skills>` asserted), with correct absolute paths into the installed package.

*Nudge* — on a seeded store, the extension ran `session-start`, emitted the RPC notify request (asserted), and the captured first-prompt payload contained the injected `engram-nudge` message as a **user-role** message (asserted — that is how pi converts custom messages for the LLM); on an empty store, no notify and no nudge text anywhere in the payload — asserted **over RPC with the UI live**, the one mode where the nudge machinery actually runs (a print-mode-only version of this check would be vacuous; the extension is inert there regardless of the store). Separately — a one-off manual observation, not a harness check — a run against a real store reproduced the production nudge text with live due counts. `ENGRAM_ROOT` was observed propagating through pi's **actual bash execution path** (driven directly via RPC's `bash` command, no model in the loop).

*Templates* — `/learn`, `/review`, `/coach` each expanded to the pointing-prompt with arguments in place, in print mode's initial prompt.

*Blind grading* — the spawn shape (`ENGRAM_CHILD=1 pi --no-session --no-skills --no-context-files -p …`) was exercised against the mock provider **with a deliberately seeded store**: the child booted, loaded no skills, injected no nudge, read no project context files, and its payload carried nothing of engram's beyond the task text. The context-file exclusion is proved, not assumed: a canary `AGENTS.md` sits in the cwd, one check asserts it **present** in the parent-shaped run and another asserts it **absent** in the child — the flag, not luck, is what excluded it. **The blindness is structural** — a fresh process cannot see a transcript it was never given.

**Not verified:** a complete live `/learn` tutoring session and a real-model assessor round-trip (both need a live LLM doing multi-turn tool work; the transport under them is what the harness proved). Reports welcome — open an issue with what you see.

### A note for maintainers: the frontmatter trap

Pi parses prompt-template and skill frontmatter as **real YAML**, and a template whose frontmatter fails to parse is **silently skipped** — `/learn` then reaches the model as literal text and nothing tells you why. An unquoted `description:` containing a second colon (`Engram — learn any topic properly: first-principles …`) is exactly that failure. Keep every frontmatter value in `pi/prompts/*.md` double-quoted. (Engram's own skills' frontmatter is colon-free after the name, so the skills load fine as written — with one nuance worth knowing: the shared skills' unquoted `argument-hint: [quick | <topic>]` parses as a YAML *flow sequence*, not a string. Pi ignores that key on skills, so it is benign here — but the same rule applies if a skill description ever grows a colon, and any platform that reads `argument-hint` as a string would want it quoted.)
