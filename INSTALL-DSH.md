# Engram on DeepSeek Harness (dsh)

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (`dsh`) is DeepSeek's
everything-is-a-plugin agent harness (developer preview — its own README warns of
compatibility-breaking changes). Engram runs on it through surfaces dsh ships natively:
`SKILL.md` directory-bundle skills discovered from `~/.agents/skills`, `AGENTS.md`
instructions, an unmodified-Claude-Code hook bridge for the session nudge, and a subagent
tool for the blind assessor. No adapter code — the port is a clone, three symlinks, and one
optional patch block.

Verified against `@deepseek-ai/dsh` 0.1.0-rc.6 (npm, 2026-08-16; bridge package
`dsh-hooks-claude-code` 0.0.1-rc.5), web profile — dsh's own README promises
compatibility-breaking changes, so pin expectations to those versions.

## Install

**1 · Clone into the shared agent home** (`~/.agents` — dsh reads it natively; the skills'
engine-resolution waterfall knows this path since v1.13.0):

```sh
git clone https://github.com/nagisanzenin/engram ~/.agents/engram
```

**2 · Link the three skills into dsh's user skill root:**

```sh
mkdir -p ~/.agents/skills
for s in learn review coach; do
  if [ -e ~/.agents/skills/$s ] && [ ! -L ~/.agents/skills/$s ]; then
    echo "engram: ~/.agents/skills/$s already exists — move it aside first"; continue
  fi
  ln -sfn ~/.agents/engram/skills/$s ~/.agents/skills/$s
done
```

(The guard matters: `ln -sfn` into an existing real directory silently nests the link one
level deep, where dsh deliberately does not look — and `learn`/`review`/`coach` are generic
names in a shared namespace.)

dsh documents these roots as live-watched (no restart needed). The skills appear in the
session's skill catalog; invoke them as **`/learn`, `/review`, `/coach`** — dsh's `/` menu
lists user-invocable skills, and a hand-typed `/learn` anywhere in a message loads the
skill the same way. (A bare `learn` without the slash stays ordinary prose.)

**3 · The nudge (optional but recommended)** — dsh bridges Claude Code hooks, and Engram
ships a dsh-specific SessionStart wrapper (`hooks/session-start-dsh.sh`) that emits the
JSON `additionalContext` shape the bridge consumes — dsh discards plain hook stdout, so
the stock Claude Code hook would run but deliver nothing. Three steps, per profile you use
(`web`, `headless`); step order matters:

```sh
# 1 · the bridge + its out-of-closure peer (needs pnpm: `npm i -g pnpm` or corepack)
dsh plugin --profile web add @deepseek-ai/dsh-hooks-claude-code
dsh plugin --profile web add @deepseek-ai/dsh-hook-protocol
# 2 · open $DSH_HOME/profiles/web/cordis.patch.yml and REPLACE the trailing `[]`
#     with the insert block from ~/.agents/engram/dsh/cordis.patch.yml
#     (absolute paths — ~ is not expanded). Then: 3 · restart the profile.
```

Two failure modes worth knowing, both found the hard way: an *override*-style patch entry
(no `insert:`) naming an id that exists in no layer is skipped with only a loader warning
— it looks exactly like success — and appending after the template's `[]` is invalid YAML
(that one fails loud). The shipped block uses the insert form, which also fails loud on a
missing package. Verify with a hook **event**, not a clean boot: after your next prompt
the due-review line appears in the session (or
`grep -l hook $DSH_HOME/sessions/*/*/session.jsonl.zstd`).

**4 · Instructions (optional):** dsh discovers `AGENTS.md` (and `CLAUDE.md`) in the
project and the user-global `~/.dsh/AGENTS.md`. Appending Engram's block there makes the
tutor rules ambient; without it the skills carry everything they need.

## Model / auth

dsh needs a DeepSeek API key: `export DEEPSEEK_API_KEY=…` in the launching environment, or
enter it once in the Web UI's Settings → Models. There are no bundled free models.

## What's shared, what's different

- **State**: the same `~/.claude/learning/` as every other platform — learn in dsh, review
  in Claude Code, one schedule.
- **Engine resolution**: the skills resolve `scripts/engram.py` from the clone at
  `~/.agents/engram` — no environment variable needed. (It is the waterfall's LAST
  candidate, so any other Engram platform install on the same machine resolves first —
  same engine either way, but keep them updated together.)
- **Subagents** (architect, blind assessor, artifact smith): dsh registers `subagent`
  (fresh-context) AND `subagent_fork` (sees this conversation). Engram's skills use only
  the former — `skills/_shared/subagents.md` carries the dsh shape, including why a forked
  assessor would silently break the one guarantee (blindness) the receipts depend on.
- **Sandbox**: dsh defaults to `workspace-write` permissions. Engram's state lives in
  `~/.claude/learning/` (outside the workspace); approve that write when the harness asks,
  or run with `DSH_PERMISSION_MODE` per dsh's docs.

## Beta caveats

- dsh is a developer preview and its plugin surfaces move; this port deliberately uses only
  stock dsh capabilities (no Engram adapter code), so drift shows up as a missing surface,
  not a crash.
- `~` is not expanded in patch-config strings — the patch block must carry absolute paths
  (the shipped template says so in-line).
- Verified keyless on 2026-08-16 against the real runtime: skill discovery through the
  documented symlinks (three skills in `skill.list` AND in a live session's
  `<available_skills>` catalog, web profile), and the nudge chain — insert patch → bridge
  loads → SessionStart fires at agent start → a probe hook's JSON `additionalContext`
  injected into the session inbox; the shipped wrapper's own output was separately
  validated through the bridge's parse logic (quotes, newlines, CJK, no shell eval). **A model-driven session has NOT been run yet** — the
  learn loop, the subagent spawn route, and sandbox prompts around `~/.claude/learning`
  are exercised on every other platform but still owed here (the release's user-session
  report records this debt). If you run one before we do, an issue report — good or bad —
  closes that gap for everyone.
