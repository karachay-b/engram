/**
 * Engram — OpenCode V2 Plugin Adapter
 * ====================================
 *
 * OpenCode 2.0 (beta, ships as the `opencode2` binary) replaces the V1 plugin
 * contract — default export `{ id, server }` returning mutable-config hooks —
 * with `{ id, setup(ctx) }`, where ctx exposes typed domains (command, skill,
 * agent, tool, session, shell, event) with transform/hook/reload methods.
 * V2 does not load V1 plugins. Both runtimes resolve the same package keys
 * (V1 probes exports["./server"] before main; V2 resolves exports["."] on
 * its current line, ./server on the earlier one), so the package entry is
 * the combined adapter in entry.ts — { id, server, setup } — and this file
 * stays reachable directly via ./v2 and local-checkout configs. See entry.ts
 * for the validator analysis (issue #19).
 *
 * Design rules for this adapter
 * -----------------------------
 *
 * 1. ZERO @opencode-ai/* imports. `Plugin.define` in the V2 SDK is the
 *    identity function (verified against @opencode-ai/plugin dist, next/dev
 *    lines), so a plain `{ id, setup }` object is a valid V2 plugin. Skipping
 *    the SDK import means this module cannot break when the beta package
 *    reshuffles its exports (it moved the V1 API to /v1 and the promise API
 *    to the root between the Aug-11 beta and Aug-14 next builds).
 *
 * 2. Feature-detect every domain, tolerate both hook call forms. The beta's
 *    context is still moving: the Aug-14 next build (what `opencode2` ships)
 *    has fn-form hooks — `session.hook("context", cb)` — while the older V2
 *    line types hooks as a mapped object — `session.hook.context(cb)`.
 *    registerHook() probes both. Every registration is optional-chained AND
 *    try/caught, including the transform callback bodies, which the runtime
 *    re-invokes after setup returns (outside setup's try/catch).
 *
 * 3. Reuse the V1 engine byte-for-byte. selfExtract / update manifest /
 *    engram_update logic are imported from the same modules the V1 entry
 *    uses. The extracted .opencode/ tree is shared state between both
 *    engines — a project can run `opencode` and `opencode2` side by side
 *    against one Engram install. Like V1 (since v1.10.1), extraction runs
 *    unconditionally and relies on selfExtract's own idempotency guard.
 *
 * What maps where (V1 → V2)
 * -------------------------
 *
 *   config hook self-extract        → setup() body (runs once per server start
 *                                     per workspace — plugins are instantiated
 *                                     per workspace)
 *   first-execution bridge          → not needed: extract to disk, then
 *     (cfg.agent/skills.paths/command)  domain reload() re-scans it
 *   command surface                 → unchanged: the shared selfExtract has
 *                                     generated commands/ (plural) since
 *                                     v1.10.x, which is also V2's canonical
 *                                     discovery dir — nothing V2-specific to
 *                                     write beyond the engram-update file
 *   cfg.command["engram-update"]    → commands/engram-update.md, written only
 *     (in-memory pseudo-command)      while a manifest exists, deleted when
 *                                     resolved (H1-guarded). Synced at setup
 *                                     AND once per session from the context
 *                                     hook + command.reload(), so an update
 *                                     landing mid-life (e.g. V1 running beside
 *                                     V2 extracts a version bump into the
 *                                     shared target) surfaces without a server
 *                                     restart.
 *   cfg.tools + cfg.permission      → ctx.tool.transform(d => d.add(…)) with a
 *     + tool: {…}                     plain JSON Schema input; registered when
 *                                     a manifest exists at setup or appears
 *                                     mid-life (same once-per-process guard).
 *                                     V1's permission allow/deny pair has no
 *                                     verified V2 vocabulary yet, so no
 *                                     options.permission is set; V2 may not
 *                                     validate the schema server-side either,
 *                                     so update-core validates its own input.
 *   experimental.chat.system.transform → session context hook pushing
 *                                     SystemPart objects ({type:"text", text}),
 *                                     once per sessionID — V1 ran one process
 *                                     per session, so per-session IS the V1
 *                                     cadence.
 *   shell.env hook                  → shell create.before hook mutating
 *                                     input.env
 *   session.idle → tui.showToast    → dropped: V2 plugins can subscribe to
 *                                     events but have no toast-publish API.
 *                                     The system-prompt notification covers it.
 *   AGENTS.md via disk              → unchanged: V2 discovers the global file
 *                                     (~/.config/opencode/AGENTS.md) and every
 *                                     project AGENTS.md up to $HOME natively
 *
 * Workspace directory (NOT process.cwd())
 * ----------------------------------------
 *
 * V2 runs plugins inside a background service shared across projects, so
 * process.cwd() is the service's directory, not the workspace — the first
 * cut used it and a smoke test extracted into ~/.config/opencode/ instead of
 * the project. Every location-scoped domain API response is wrapped as
 * { location: { directory, workspaceID, project }, data }; setup asks
 * ctx.agent.list(), then ctx.command.list(). If NEITHER reports a location
 * (older V2 SDK lines have no domain-level list() at all), the adapter goes
 * HOOKS-ONLY: nudge and shell-env still work (both can resolve per-call),
 * but nothing is extracted and no command files are written — a wrong-
 * directory write is strictly worse than a missing feature. The same rule
 * applies one level up: the service also instantiates plugins for locations
 * that are not the configuring project (its own root among them), so
 * extraction additionally requires the location to own an opencode config
 * file, or to be the global config dir itself (extractionScope()).
 *
 * Known V2 deltas (beta, re-verify at V2 GA)
 * ------------------------------------------
 *
 *   - Agent frontmatter: V2 deprecates `tools:` in favor of `permissions:`.
 *     Extracted agents keep the V1 shape (tools object + mode: subagent +
 *     hidden: true) because the same files must keep working under V1; V2
 *     ignores the legacy field and the assessor's blindness is enforced by
 *     its prompt, as on OpenClaw.
 *   - V2's command.transform update() does upsert, so an in-memory
 *     /engram-update port was possible; the file keeps it consistent with
 *     the other generated commands and visible to disk-level debugging.
 *
 * Error handling: the entire setup body, every hook callback body, and every
 * transform callback body are wrapped in try/catch — no Engram failure may
 * crash the host. setup returns a cleanup that disposes every registration
 * it made, so a host that cycles plugin generations cannot stack hooks.
 */

import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync, lstatSync } from "node:fs"
import { resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"
import { execFile } from "node:child_process"
import { selfExtract, getExtractTarget, getVERSION, syncProjectState } from "./install.js"
import { readManifest } from "./update.js"
import { runEngramUpdate, type UpdateArgs } from "./update-core.js"
import { UPDATE_DESCRIPTION, UPDATE_TEMPLATE } from "./update-command.js"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..")


// ---------------------------------------------------------------------------
// V2 command surface — .opencode/commands/ (plural)
// ---------------------------------------------------------------------------

/**
 * The /engram-update pseudo-command, V2 edition.
 *
 * V1 keeps it purely in-memory (cfg.command) so OpenCode's disk-discovery
 * cache can never lock a stale definition. V2's command cache can be
 * refreshed explicitly via ctx.command.reload(), so the same lifecycle works
 * with a real file: written (with $TARGET resolved) only while the update
 * manifest exists, deleted — H1-guarded — the moment it is gone.
 *
 * Returns true when the file was created or removed (reload needed).
 */
export function syncUpdateCommandV2(target: string): boolean {
  const commandFile = resolve(target, "commands", "engram-update.md")
  const pending = existsSync(resolve(target, ".engram-update.jsonc"))

  if (pending) {
    const content = `---\ndescription: ${UPDATE_DESCRIPTION}\n---\n\n${UPDATE_TEMPLATE.replace(/\$TARGET/g, target).trimEnd()}\n`
    if (existsSync(commandFile)) {
      // Ownership guard on the WRITE path too: a user's own file with this
      // name (or a symlink a dotfiles manager planted — writeFileSync would
      // follow it out of the target) is never overwritten. Ownership means
      // the file byte-starts with our exact generated header; a file that
      // merely QUOTES the H1 somewhere is the user's.
      try { if (lstatSync(commandFile).isSymbolicLink()) return false } catch { return false }
      const body = readFileSync(commandFile, "utf-8")
      if (body === content) return false
      if (!isEngramUpdateCommand(body)) return false
    }
    mkdirSync(resolve(target, "commands"), { recursive: true })
    writeFileSync(commandFile, content)
    return true
  }

  if (existsSync(commandFile)) {
    try {
      if (lstatSync(commandFile).isSymbolicLink()) return false
      const body = readFileSync(commandFile, "utf-8")
      if (isEngramUpdateCommand(body)) {
        unlinkSync(commandFile)
        return true
      }
    } catch {}
  }
  return false
}

/** Ownership = the file byte-starts with our exact generated header (the
 *  frontmatter open + our description line). Stronger than the old
 *  includes(H1) check, which deleted any user file that merely quoted the
 *  heading. */
function isEngramUpdateCommand(body: string): boolean {
  return body.startsWith(`---\ndescription: ${UPDATE_DESCRIPTION}\n---`)
}

// ---------------------------------------------------------------------------
// Nudge + update notification (session context hook)
// ---------------------------------------------------------------------------

/** Same summary session-start.ts produces for V1 — kept behaviourally
 *  identical (readManifest tolerates absent/corrupt manifests). */
export function readUpdateSummary(target: string): string | null {
  const m = readManifest(target)
  if (!m) return null
  if (m.state === "in_progress") {
    return "Update partially applied. Run /engram-update to continue"
  }
  return "Updates Engram Available!\nRun /engram-update"
}

export type NudgeRunner = (engramPy: string) => Promise<string>

/** Runs `engram.py session-start` — V2 has no host shell executor (V1's `$`),
 *  so plain execFile. Silent on every failure: no python3, no script, timeout. */
export const defaultNudgeRunner: NudgeRunner = (engramPy) =>
  new Promise((done) => {
    try {
      execFile("python3", [engramPy, "session-start"], { timeout: 15000 }, (err, stdout) => {
        done(err ? "" : String(stdout ?? "").trim())
      })
    } catch {
      done("")
    }
  })

// ---------------------------------------------------------------------------
// engram_update custom tool (V2 registration)
// ---------------------------------------------------------------------------

/** Plain JSON Schema for the tool input — V2's ValueSchema accepts raw JSON
 *  Schema, which keeps this adapter free of the SDK's zod/effect re-exports.
 *  Mirrors the V1 zod schema in update-tool.ts exactly (a vitest check pins
 *  the two enums together). The schema may not be enforced by the runtime;
 *  update-core.ts validates its own input regardless. */
export const UPDATE_TOOL_INPUT = {
  type: "object",
  properties: {
    target: { type: "string", description: "Target .opencode directory" },
    mode: {
      type: "string",
      enum: ["auto", "per_file", "keep_as_is", "skip", "checkpoint", "cleanup"],
      description: "Update mode",
    },
    decisions: {
      type: "array",
      description: "Per-file decisions (required for per_file mode)",
      items: {
        type: "object",
        properties: {
          file: { type: "string", description: "Relative file path from manifest categories" },
          action: { type: "string", enum: ["delete", "keep"], description: "What to do with this file" },
        },
        required: ["file", "action"],
        additionalProperties: false,
      },
    },
  },
  required: ["target", "mode"],
  additionalProperties: false,
} as const

// ---------------------------------------------------------------------------
// Hook registration across SDK lines
// ---------------------------------------------------------------------------

/**
 * Registers a hook on a domain, tolerating both call forms seen across V2
 * builds: fn-form `domain.hook(name, cb)` (the shipping next line) and
 * mapped-object form `domain.hook[name](cb)` (the older V2 SDK line).
 * Returns the Registration (or undefined when the domain/hook is absent) —
 * an optional-CALL alone would throw on the object form, and that throw
 * would cost the hook silently.
 */
export async function registerHook(
  domain: any,
  name: string,
  cb: (input: any) => Promise<void> | void,
): Promise<{ dispose?: () => Promise<void> } | undefined> {
  if (!domain) return undefined
  const hook = domain.hook
  if (typeof hook === "function") return await hook.call(domain, name, cb)
  if (hook && typeof hook[name] === "function") return await hook[name](cb)
  return undefined
}

// ---------------------------------------------------------------------------
// Workspace directory resolution
// ---------------------------------------------------------------------------

/**
 * Resolves the workspace directory from the plugin context. Every
 * location-scoped domain API responds with { location, data }; the agent
 * list is the cheapest always-available one on the shipping line.
 *
 * Returns null when no domain reports a location — older V2 SDK lines have
 * no domain-level list() at all, and process.cwd() there is the SHARED
 * background service's directory. Extracting into it once wrote Engram into
 * ~/.config/opencode/ during the smoke test; the caller treats null as
 * "hooks only, touch no disk".
 */
export async function resolveWorkspaceDirectory(ctx: any): Promise<string | null> {
  for (const domain of [ctx?.agent, ctx?.command]) {
    try {
      const res = await domain?.list?.()
      const dir = res?.location?.directory
      if (typeof dir === "string" && dir) return dir
    } catch {}
  }
  return null
}


/**
 * Second wrong-directory class, caught by the release e2e: the background
 * service instantiates plugins for locations beyond the configuring project
 * (its own root among them). A config-less directory would fall through
 * getExtractTarget's global fallback and extract Engram into the user's real
 * ~/.config/opencode/ — which is how a project-only install polluted the
 * global config during testing. So extraction requires the location to OWN
 * an opencode config file (a project install always does — the plugins entry
 * lives in that very file), or to BE the global config dir itself. Anything
 * else gets hooks, not files.
 */
export function extractionScope(dir: string | null): string | null {
  if (!dir) return null
  const home = process.env.HOME || process.env.USERPROFILE || "/tmp"
  const globalDir = resolve(home, ".config", "opencode")
  if (resolve(dir) === globalDir) return dir
  if (existsSync(resolve(dir, "opencode.json")) || existsSync(resolve(dir, "opencode.jsonc"))) return dir
  return null
}

// ---------------------------------------------------------------------------
// setup
// ---------------------------------------------------------------------------

export interface V2SetupDeps {
  runNudge?: NudgeRunner
  /** Overrides the directory used for target detection (tests). */
  directory?: string
}

/**
 * Builds the V2 setup function. The default export uses real deps; tests
 * inject a fake nudge runner and a sandbox directory — same seam V1 got for
 * free from its host-injected `$` and `client`.
 */
export function createV2Setup(deps: V2SetupDeps = {}) {
  const runNudge = deps.runNudge || defaultNudgeRunner

  return async function setup(ctx: any): Promise<(() => Promise<void>) | void> {
    const registrations: Array<{ dispose?: () => Promise<void> } | undefined> = []
    try {
      const dir = deps.directory || (await resolveWorkspaceDirectory(ctx))

      let target: string | null = null
      let toolRegistered = false

      // The transform callback runs again on later tool-list assemblies —
      // outside setup's try/catch — so its body carries its own guards.
      const registerUpdateTool = async () => {
        if (toolRegistered) return
        toolRegistered = true
        try {
          const r = await ctx?.tool?.transform?.((draft: any) => {
            try {
              if (typeof draft?.add !== "function") return
              draft.add({
                name: "engram_update",
                description:
                  "Apply Engram plugin updates — delete preserved files and update the manifest. Only call when the /engram-update command instructs you.",
                input: UPDATE_TOOL_INPUT,
                // The shipping V2 build routes default-options tools through
                // the codemode meta-tool; only codemode:false tools are
                // callable BY NAME, which is what the /engram-update template
                // instructs. Without this the tool is advertised yet every
                // direct call fails "Unknown tool" (found live, not in docs).
                options: { codemode: false },
                execute: async (input: UpdateArgs) => {
                  let message: string
                  try {
                    message = runEngramUpdate(input)
                  } catch (e) {
                    // update-core validates args and manifest shape, so this
                    // is the last-resort net: a rejection out of execute is
                    // host-version-dependent territory we never enter.
                    message = `[engram] Update failed: ${String(e)}`
                  }
                  // content, not output: the runtime rejects a result that
                  // declares `output` when the tool has no output schema
                  // ("Tool result declared output without an output schema",
                  // found live). content is the free-form result field.
                  return { content: message }
                },
              })
            } catch {}
          })
          if (r) registrations.push(r)
        } catch {}
      }

      const extractDir = extractionScope(dir)
      if (extractDir) {
        // Unconditional like V1 since v1.10.1 — selfExtract's own
        // .engram-version.jsonc guard makes it idempotent, and extraction is
        // what makes the command surface below legitimate.
        const result = selfExtract(root, extractDir, getVERSION(root), undefined)
        target = result.target
        const freshlyExtracted = result.freshlyExtracted

        try { syncProjectState(target, () => {}) } catch {}

        let commandsChanged = false
        try { commandsChanged = syncUpdateCommandV2(target) } catch {}

        if (freshlyExtracted) {
          try { await ctx?.skill?.reload?.() } catch {}
          try { await ctx?.agent?.reload?.() } catch {}
        }
        if (freshlyExtracted || commandsChanged) {
          try { await ctx?.command?.reload?.() } catch {}
        }

        if (existsSync(resolve(target, ".engram-update.jsonc"))) {
          await registerUpdateTool()
        }
      }

      // Session-start nudge + update surface, once per SESSION — V1 ran one
      // process per session, so per-session is the original cadence. The
      // update state is re-checked here because a manifest can land mid-life
      // (V1 running beside V2 extracts a version bump into the shared
      // target); binding it to server start left updates invisible until a
      // service restart.
      const nudgedSessions = new Set<string>()
      try {
        const r = await registerHook(ctx?.session, "context", async (sc: any) => {
          try {
            const sessionID = String(sc?.sessionID ?? "")
            if (nudgedSessions.has(sessionID)) return
            if (nudgedSessions.size > 512) nudgedSessions.clear()
            nudgedSessions.add(sessionID)

            const engramPy = resolve(root, "scripts", "engram.py")
            const nudge = await runNudge(engramPy)
            if (nudge) sc.system.push({ type: "text", text: `\n[engram] ${nudge}` })

            if (target && extractDir) {
              // Re-extraction is idempotent (version-file guard), so this is
              // a no-op on every normal session — but after /engram-update
              // resolves (version file deleted), it restores the refreshed
              // files on the NEXT session instead of the next service
              // restart. v1.12.0 left the tree holed until restart (§7.5).
              try {
                const re = selfExtract(root, extractDir, getVERSION(root), undefined)
                if (re.freshlyExtracted) {
                  try { await ctx?.skill?.reload?.() } catch {}
                  try { await ctx?.agent?.reload?.() } catch {}
                  try { await ctx?.command?.reload?.() } catch {}
                }
              } catch {}
              try { if (syncUpdateCommandV2(target)) await ctx?.command?.reload?.() } catch {}
              if (existsSync(resolve(target, ".engram-update.jsonc"))) {
                await registerUpdateTool()
                const updateSummary = readUpdateSummary(target)
                if (updateSummary) {
                  sc.system.push({ type: "text", text: `\n[engram] ${updateSummary}` })
                }
              }
            }
          } catch {}
        })
        if (r) registrations.push(r)
      } catch {}

      // ENGRAM_ROOT / OPENCODE_PLUGIN_ROOT on every shell execution — the
      // V1 shell.env hook, reshaped to V2's create.before input (env lives on
      // the single mutable input object). Resolution is per-execution via the
      // shell's own cwd, so this works even in hooks-only mode.
      try {
        const r = await registerHook(ctx?.shell, "create.before", (shell: any) => {
          try {
            const base = shell.cwd || dir
            const shellTarget = base ? getExtractTarget(base) : null
            const pluginRoot =
              shellTarget && existsSync(resolve(shellTarget, "scripts", "engram.py")) ? shellTarget : root
            shell.env["ENGRAM_ROOT"] = pluginRoot
            shell.env["OPENCODE_PLUGIN_ROOT"] = pluginRoot
            if (process.env.ENGRAM_HOME) shell.env["ENGRAM_HOME"] = process.env.ENGRAM_HOME
            if (process.env.ENGRAM_TODAY) shell.env["ENGRAM_TODAY"] = process.env.ENGRAM_TODAY
          } catch {}
        })
        if (r) registrations.push(r)
      } catch {}
    } catch {}

    return async () => {
      for (const registration of registrations) {
        try { await registration?.dispose?.() } catch {}
      }
    }
  }
}

export const setup = createV2Setup()

export default {
  id: "engram",
  setup,
}
