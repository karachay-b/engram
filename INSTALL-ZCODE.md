# Engram on ZCode

[ZCode](https://z.ai) is the agentic coding client you are reading this in — and its
extension model is Claude Code-compatible by construction: a plugin manifest at
`.zcode-plugin/plugin.json` (or the legacy `.claude-plugin/` one Engram already ships),
native `SKILL.md` directory-bundle skills discovered at user and workspace scope, a
`SessionStart` hook runner, and `AGENTS.md` instruction files. The port adds exactly
three things: a ZCode manifest, one hook wrapper, and this document. No adapter code.

Verified against **ZCode 3.9.2** (macOS, August 2026) — statically against the shipped
runtime's own plugin/skill/hook loading paths, plus the live `engram.py selftest`
(315/315). A live model-driven session is not yet on record: if you run one before we
do — good or bad — an issue report closes that gap for everyone (see the
[user-session protocol](docs/user-sessions/) note in [RELEASE_PROTOCOL.md](RELEASE_PROTOCOL.md)).

## Install

### Route A · plugin marketplace (recommended)

ZCode reads this repository itself as a marketplace (it consumes
`.claude-plugin/marketplace.json`, which ships here for Claude Code; no ZCode-specific
marketplace file is needed):

1. Open **Settings → Plugin Management → Discover**, press **`+`**, and add the source:
   `https://github.com/nagisanzenin/engram` (a Git URL or local clone path work too).
2. Select **Engram** and click **Install**.
3. Restart ZCode (or start a new session) so skills re-scan.

That's everything. The install gives you, with zero config:

- **The three skills** — invoked as `/learn`, `/review`, `/coach`. On builds that
  namespace plugin skills, use `/engram:learn` etc.; both spellings resolve to the
  same skill. Requires nothing else — every skill carries its full discipline inline.
- **The nudge.** ZCode loads each installed plugin's `hooks/hooks.json`, and it enables
  the hook runner automatically when a plugin contributes hooks — unlike config-file
  hooks, no `hooks.enabled` flag is needed. One subtlety drove a real design decision:
  **ZCode discards plain SessionStart stdout** (unlike Claude Code, which prints it into
  context), so Engram ships [`hooks/session-start-zcode.sh`](hooks/session-start-zcode.sh)
  alongside the stock hook — same two-line output, wrapped in the JSON
  `hookSpecificOutput.additionalContext` contract ZCode actually parses. The shared
  `hooks/hooks.json` registers both; the ZCode wrapper exits immediately when it detects
  a runtime that already delivers the plain-stdout version, so no platform ever sees
  two nudges.

Optionally add the tutor rules as ambient instructions so they apply even outside
skill invocations: append an Engram block from any of the skills'
[`_shared/dialogue-grammar.md`](skills/_shared/dialogue-grammar.md) headers to
`~/.zcode/AGENTS.md`. The skills carry everything they need on their own; without it,
nothing degrades.

### Route B · clone + symlink (no plugin system)

Useful when your ZCode build restricts marketplaces, or to track `main` directly:

```sh
git clone https://github.com/nagisanzenin/engram ~/.agents/engram
```

Then link the three skills into either discovery root:

```sh
mkdir -p ~/.agents/skills          # or ~/.zcode/skills for ZCode-only installs
for s in learn review coach; do
  if [ -e ~/.agents/skills/$s ] && [ ! -L ~/.agents/skills/$s ]; then
    echo "engram: ~/.agents/skills/$s already exists — move it aside first"; continue
  fi
  ln -sfn ~/.agents/engram/skills/$s ~/.agents/skills/$s
done
```

(The guard matters: `ln -sfn` into an existing real directory silently nests the link
one level deep, where discovery deliberately does not look — and `learn`/`review`/
`coach` are generic names in a shared namespace.)

`~/.agents/skills` is the cross-tool root: the same three links light the skills up in
ZCode *and* the DeepSeek Harness port ([INSTALL-DSH.md](INSTALL-DSH.md)), which clones
into the same home. If you'd rather not share, put the links under `~/.zcode/skills/`.

**The nudge on route B** is optional wiring through the user configuration file
(`~/.zcode/cli/config.json`) — and here the flag is mandatory:

```json
{
  "hooks": {
    "enabled": true,
    "events": {
      "SessionStart": [
        {
          "matcher": "startup|resume|clear",
          "hooks": [
            {
              "type": "command",
              "command": "\"/Users/you/.agents/engram/hooks/session-start-zcode.sh\""
            }
          ]
        }
      ]
    }
  }
}
```

Absolute paths — the hook environment does not expand `~`, and there is no plugin-root
variable in this route, but the script self-resolves relative to its own location
anyway. `enabled: true` is the step people forget: config-file hooks are disabled by
default, so without it the hook runs nowhere and looks like an engram bug.

## Model / auth

Whatever provider your ZCode session already uses — there is nothing to configure, and
the engine never talks to the network (its AST-scanned no-network guarantee covers the
hook wrapper too). `python3` must be on PATH; stock macOS/Linux Python is fine.

## What's shared, what's different

- **State**: the same `~/.claude/learning/` as every other platform — learn in ZCode,
  review in Claude Code, one schedule. (`ENGRAM_HOME` overrides the location.)
- **Engine resolution**: skills resolve `scripts/engram.py` through their waterfall —
  `$ZCODE_PLUGIN_ROOT` first (checked before `$CLAUDE_PLUGIN_ROOT`, because ZCode sets
  both to the same install root), then the working tree, then `~/.agents/engram` last so
  the clone route shadows nothing.
- **Subagents**: register like everyone else's *conceptually*, constructed like dsh's.
  Engram's agent definitions ship inside the plugin (visible in Settings → Subagents /
  the plugin reference some builds inject), but ZCode treats declared plugin agents as
  diagnostic-only in this build — so the skills do not rely on named types. They spawn
  the blind assessor as a fresh-context `general-purpose` child pointed at the agent
  file, per ["The ZCode shape"](skills/_shared/subagents.md). Freshness comes from the
  Agent tool's process boundary; blindness comes from passing items by file path and
  keeping dialogue out of the prompt. If a child were forked instead, the receipt would
  look valid and be worthless — never accept a graded claim from a grader that saw the
  lesson.
- **Sandbox / permissions**: Engram writes state outside your workspace
  (`~/.claude/learning/`). Under default permission modes, approve that write when the
  harness asks, once per path.

## Verification checklist

```sh
# engine + state sane
python3 ~/.agents/engram/scripts/engram.py doctor      # or your checkout/plugin cache root

# the nudge emits what ZCode parses (empty output = nothing due = correct)
python3 <root>/scripts/engram.py session-start | head -1     # what will ride inside the JSON
<root>/hooks/session-start-zcode.sh                          # run under ZCode: prints {"hookSpecificOutput"...}
```

In-session checks: the skill appears in the `/` menu; after starting a session with
reviews due, the `[engram] N reviews due` line lands near the top of the conversation;
with zero reviews due the hook stays silent (Constitution art. 8).

## Caveats

- Verified against 3.9.2; ZCode ships fast. Drift shows up as a missing surface (nudge
  lost, skill unlisted), not a crash — the port deliberately uses only stock surfaces.
- Both SessionStart entries fire under ZCode-as-plugin; the stock entry's output is
  discarded by design, so this costs one extra ~100 ms script spawn per session, kept
  as the price of one shared hooks file across every platform that reads one.
- A model-driven user session has not been recorded yet (see top). Until one lands,
  treat the learn loop's ZCode behavior as high-confidence-but-unexercised rather than
  proven-on-platform.
