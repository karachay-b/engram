/**
 * Engram — Deterministic Update Tool (OpenCode V1 wrapper)
 * =========================================================
 *
 * Custom OpenCode tool (registered via @opencode-ai/plugin's `tool()` API)
 * that handles ALL destructive operations for the update system — file deletion,
 * manifest checkpoint, and cleanup — in deterministic TypeScript with zero LLM
 * interpolation risk.
 *
 * The logic lives in update-core.ts (host-agnostic, shared with the V2
 * adapter in v2.ts); this file only binds it to the V1 SDK surface.
 *
 * The tool is registered statically in the server return but conditionally
 * enabled/disabled via cfg.tools["engram_update"] in the config hook, using
 * the same existsSync gate as the /engram-update pseudo-command.
 *
 * When the manifest is resolved and deleted, cfg.tools["engram_update"] = false
 * + cfg.permission["engram_update"] = "deny" hides the tool from the LLM on
 * the next session.
 *
 * --- Lifecycle ---
 *
 * Manifest exists (version bump detected by selfExtract)
 *   → config hook: cfg.command["engram-update"] registered + cfg.tools["engram_update"] = true
 *   → /engram-update executed by user
 *   → model calls this tool via template instructions
 *   → tool processes files, deletes manifest + version guard
 *   → next reload:
 *       existsSync → false → pseudo-command gone
 *       cfg.tools["engram_update"] = false + cfg.permission["engram_update"] = "deny" → tool hidden
 *       .engram-version.jsonc deleted → selfExtract treats as fresh install
 *       copyMissing with existsSync guard → user edits preserved
 */

import { tool } from "@opencode-ai/plugin"
import { runEngramUpdate, type UpdateArgs } from "./update-core.js"

export const engramUpdateTool = tool({
  description: "Apply Engram plugin updates — delete preserved files and update the manifest. Only call when the /engram-update command instructs you.",
  args: {
    target: tool.schema.string().describe("Target .opencode directory"),
    mode: tool.schema.enum(["auto", "per_file", "keep_as_is", "skip", "checkpoint", "cleanup"]).describe("Update mode"),
    decisions: tool.schema.array(tool.schema.object({
      file: tool.schema.string().describe("Relative file path from manifest categories"),
      action: tool.schema.enum(["delete", "keep"]).describe("What to do with this file"),
    })).optional().describe("Per-file decisions (required for per_file mode)"),
  },
  async execute(args) {
    return runEngramUpdate(args as UpdateArgs)
  },
})
