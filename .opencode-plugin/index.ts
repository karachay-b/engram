/**
 * Engram — OpenCode Plugin
 * =========================
 *
 * Self-extract + first-execution bridge
 * -------------------------------------
 *
 * NPM mode (installed via "plugin": ["git+…/engram.git"] in opencode.json):
 *   The package lives under ~/.cache/opencode/node_modules/. OpenCode does NOT
 *   treat the npm cache as a config directory, so no disk discovery happens there.
 *
 *   → The config hook triggers selfExtract() which copies files into the
 *     project's (or global) .opencode/ directory.
 *   → On the first execution (freshlyExtracted), a bridge registers agents,
 *     commands, and skills via cfg.* so they work immediately.
 *   → Disk discovery picks up .opencode/ on the next OpenCode start.
 *
 * Self-extract (install.ts)
 * -------------------------
 *
 * copyMissing() — never overwrites existing files. On version bump:
 *   skills/   → merged (new files added, existing files preserved)
 *   agents/   → merged + transformed (custom tools string → YAML objects,
 *              mode: subagent, hidden: true injected)
 *   scripts/  → merged (engram.py)
 *   gold/     → merged (bundled assessor ground truth — engine reads it from
 *              _plugin_root(), issue #20)
 *   experiments/ → merged (pre-registered presets — same root)
 *   docs/     → merged (cited by the extracted skills)
 *
 * Generated (always overwritten on extract):
 *   command/  → command/{learn,review-loop,coach}.md
 *   AGENTS.md → versioned marker block (project root or ~/.config/opencode/)
 *   .engram-version.jsonc → idempotency: {version, previous, installed_at, source}
 *   .engram-update.jsonc  → per-category diff manifest (only on version bump)
 *
 *   /engram-update is a temporary pseudo-command: never written as a file.
 *   Registered only via cfg.command when .engram-update.jsonc exists on disk.
 *   This prevents OpenCode's disk-discovery cache from locking a stale definition
 *   — the solution found for preserving user-edited skills/agents/scripts across
 *   plugin version bumps without silently clobbering them.
 *
 * Target detection:
 *   cwd has opencode.json/jsonc → {cwd}/.opencode/     (project-level)
 *   otherwise → ~/.config/opencode/                    (global)
 *
 * Config hook + bridge
 * --------------------
 *
 *   1. selfExtract() — idempotent via .engram-version.jsonc.
 *   2. First-execution bridge (freshlyExtracted):
 *      agents   → registerAgents(cfg, root) — reads agents/*.md frontmatter,
 *                 parses custom tools strings to OpenCode object format.
 *      skills   → cfg.skills.paths.push(target/skills) — {paths: []}.
 *      commands → cfg.command[name] = { template, description } — 3 inline.
 *      engram-update → registered conditionally when manifest exists.
 *      Shape note: targets the OpenCode v1 SDK config layer (skills.paths,
 *      command singular, agent singular). v2 uses skills: string[] and
 *      commands: plural. The bridge shapes are intentional.
 *   After first exec: bridge off, disk discovery handles everything.
 *
 * AGENTS.md (no bridge needed)
 * ------------------------------
 *
 *   AGENTS.md is written directly to disk by selfExtract. No cfg.instructions
 *   registration is required because both V1 and V2 discover it natively:
 *
 *     V1 (HTTP API / CLI) — fs.findUp("AGENTS.md") every request.
 *     V2 (InstructionContext) — fs.up({ targets: ["AGENTS.md"] }) every turn.
 *
 *   The file is re-read from disk on every LLM request — no bridge, no cache,
 *   no restart needed. Changes or creation take effect immediately.
 *
 *   selfExtract also:
 *     - Adds AGENTS.md to .git/info/exclude so the file is never committed
 *       (per-repo local gitignore, no hook, no working-tree mutation).
 *     - Warns if CLAUDE.md exists at the project root — AGENTS.md takes
 *       discovery priority over CLAUDE.md (first filename match wins).
 *
 * Update system (update.ts)
 * -------------------------
 *
 * On version bump, selfExtract writes .engram-update.jsonc with a per-category
 * diff (skills, agents, scripts, commands, gold, experiments, docs — files
 * added vs preserved).
 *
 * Notification (session-start.ts):
 *   system.transform — injects "Updates Engram Available!" + "Run
 *   /engram-update" into the system prompt on every session while a pending
 *   update exists (manifest file present).
 *
 *   session.idle — fires tui.toast.show with the same message. Visible toast
 *   notification in the TUI on every session while update is pending.
 *
 * /engram-update command (pseudo-command + custom tool):
 *
 *   Conditional twins — both only active when .engram-update.jsonc exists:
 *     cfg.command["engram-update"] = { description, template }   ← pseudo-command
 *     cfg.tools["engram_update"] = true                           ← custom tool
 *   Both disappear on next session when manifest is resolved/deleted.
 *
 *   $TARGET resolution — the template uses $TARGET as a placeholder which is
 *   replaced at config-hook time via UPDATE_TEMPLATE.replace(/$TARGET/g, target).
 *   This resolves to {cwd}/.opencode/ (project-level) or ~/.config/opencode/
 *   (global), so the model always reads/writes the correct target directory.
 *
 *   Template flow:
 *     STEP 1 — Read manifest at $TARGET/.engram-update.jsonc
 *     STEP 2 — Error cleanup (Bash: rm -f hardcoded paths, no interpolation)
 *     STEP 3 — Route by manifest.state (pending / in_progress)
 *     STEP 4 — question tool presents 4 options (auto/manual/skip/keep-as-is)
 *     STEP 4a-4d — call engram_update tool (auto/per_file/keep_as_is/skip modes)
 *     STEP 5 — resume: reads state, continues per-file from checkpoint
 *   Zero Bash for destructive operations — all file deletion, manifest checkpoint,
 *   and cleanup are handled by the deterministic engram_update custom tool.
 *
 *   Full lifecycle:
 *     Manifest exists (version bump detected by selfExtract)
 *       → config hook: pseudo-command registered + tool enabled
 *       → /engram-update executed by user
 *       → engram_update tool processes files, deletes manifest + version guard
 *       → next reload:
 *           existsSync → false → pseudo-command gone, tool hidden
 *           .engram-version.jsonc deleted → selfExtract treats as fresh install
 *           copyMissing with existsSync guard → user edits preserved forever
 *     If interrupted mid-execution (crash, power loss):
 *       → manifest persists with state="in_progress" + per-file checkpoint
 *       → STEP 5 resumes exactly where it stopped
 *       → rm -f is idempotent via existsSync guard in the tool
 *
 * Error handling
 * --------------
 *
 * Every hook is wrapped in try/catch — no plugin error can crash the host:
 *   config, system.transform, event, shell.env — top-level try/catch.
 *   registerAgents — per-file try/catch (corrupt agent skipped).
 *   selfExtract — try/catch around entire extract + manifest generation.
 *   readUpdateSummary — returns null on corrupt manifest.
 *   tui.showToast — .catch(() => {}) (toast is best-effort, non-critical).
 *
 * OPENCODE_PLUGIN_ROOT (shell-env.ts)
 * -----------------------------------
 *
 * Resolved at every shell execution via input.cwd:
 *   Check if {target}/scripts/engram.py exists.
 *   true  → use target (self-extract done, engine is local).
 *   false → use packageRoot (pre-extract, engine not yet local).
 *
 * Nudge (session-start.ts)
 * ------------------------
 *
 * system.transform → first call runs `engram.py session-start`. Injects
 *   review-due message + update notification into system prompt.
 *   Single hook, no shared state, no ordering dependency.
 *
 * session.idle → toast notification if update pending.
 *
 * What was deliberately removed
 * -----------------------------
 *
 *   cfg.references            → all paths local; AGENTS.md covers it.
 *   cfg.permission            → no external paths remain post-extract.
 *   cfg.{skills,commands,agents} → disk discovery (bridge on first exec).
 *   cfg.instructions push     → dropped — V1 and V2 both discover AGENTS.md
 *                               natively (re-read from disk every request).
 *   copyDir / cpSync          → copyMissing (never overwrite user files).
 *
 * Known OpenCode bug
 * ------------------
 *   anomalyco/opencode#36681 — external_directory auto-allow.
 *   Not relevant post-extract since all paths are local.
 */

import { existsSync } from "node:fs"
import { resolve, dirname, basename } from "node:path"
import { fileURLToPath } from "node:url"
import type { Plugin } from "@opencode-ai/plugin"
import { registerAgents } from "./agents.js"
import { createSessionStartHooks } from "../hooks/session-start.js"
import { createShellEnvHook } from "../hooks/shell-env.js"
import { selfExtract, getVERSION, syncProjectState } from "./install.js"
import { createPluginLogger } from "./logger.js"
import { UPDATE_DESCRIPTION, UPDATE_TEMPLATE } from "./update-command.js"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..")

const COMMANDS: Record<string, { description: string; template: string }> = {
  learn: {
    description:
      "Learn any topic properly — first-principles curriculum, generation-first tutoring, verified free recall, FSRS scheduling",
    template: `# /learn — acquisition loop

LOAD AND FOLLOW the \`learn\` skill. Teach the learner the requested topic.

Topic: $ARGUMENTS`,
  },
  "review-loop": {
    description:
      "Review due concepts — free recall interleaved across topics, blind graded, FSRS scheduled",
    template: `# /review-loop — review loop

LOAD AND FOLLOW the \`review\` skill. Review due concepts with the learner.

Arguments: $ARGUMENTS`,
  },
  coach: {
    description:
      "Learning analytics — retention stats, dashboard, schedule tuning, experiments, audit",
    template: `# /coach — coaching & analytics

LOAD AND FOLLOW the \`coach\` skill. Show learning analytics and insights.

Arguments: $ARGUMENTS`,
  },
}

export const server: Plugin = async ({ client, $, directory }) => {
  // Loaded here, NOT at module top: update-tool.ts value-imports
  // @opencode-ai/plugin (and calls tool() at module scope), and this module
  // sits in the combined entry's static graph. A static import links the V1
  // SDK into the V2 load path, where the specifier may be absent or its root
  // export reshuffled (it has moved once already) — an ESM link error there
  // kills the plugin before any try/catch runs. server() only ever executes
  // under V1, the runtime that ships the SDK.
  const { engramUpdateTool } = await import("./update-tool.js")
  const cwd = directory || process.cwd()
  const sessionStartHooks = createSessionStartHooks($, root, client)
  const shellEnvHooks = createShellEnvHook(root)

  return {
    async config(input) {
      try {
        const cfg = input as any
      const logger = createPluginLogger(client)
      const result = selfExtract(root, cwd, getVERSION(root), logger)
      const target = result.target
      const freshlyExtracted = result.freshlyExtracted

      // Every session, not just on a version bump — see syncProjectState().
      try { syncProjectState(target, createPluginLogger(client)) } catch {}

      if (freshlyExtracted) {
        registerAgents(cfg, root)
        cfg.skills = cfg.skills || {}
        cfg.skills.paths = cfg.skills.paths || []
        cfg.skills.paths.push(resolve(target, "skills"))
        cfg.command = cfg.command || {}
        for (const [name, def] of Object.entries(COMMANDS)) {
          if (!cfg.command[name]) cfg.command[name] = def
        }
      }

      if (existsSync(resolve(target, ".engram-update.jsonc"))) {
        cfg.command = cfg.command || {}
        cfg.command["engram-update"] = {
          description: UPDATE_DESCRIPTION,
          template: UPDATE_TEMPLATE.replace(/\$TARGET/g, target),
        }
      }
      cfg.tools = cfg.tools || {}
      const hasUpdate = existsSync(resolve(target, ".engram-update.jsonc"))
      cfg.tools["engram_update"] = hasUpdate
      cfg.permission = cfg.permission || {}
      cfg.permission["engram_update"] = hasUpdate ? "allow" : "deny"
      } catch {}
    },
    tool: {
      engram_update: engramUpdateTool,
    },
    ...sessionStartHooks,
    ...shellEnvHooks,
  }
}

export default {
  id: "engram",
  server,
}
