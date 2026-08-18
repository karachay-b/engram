import { describe, it, expect, beforeEach, afterEach } from "vitest"
import { tmpdir } from "node:os"
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, existsSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import v2Default, {
  createV2Setup,
  syncUpdateCommandV2,
  readUpdateSummary,
  resolveWorkspaceDirectory,
  registerHook,
  extractionScope,
  UPDATE_TOOL_INPUT,
} from "../.opencode-plugin/v2"

/** Minimal pending manifest — enough for readManifest + the existsSync gates. */
const PENDING_MANIFEST = JSON.stringify({
  from: "1.0.0",
  to: "1.1.0",
  source: "/nowhere",
  categories: { skills: { added: [], skipped: ["skills/learn.md"] } },
  state: "pending",
  applied: [],
  remaining: ["skills"],
})

/** Records every registration a V2 runtime would receive. `directory` mimics
 *  the { location, data } wrapper every location-scoped API responds with. */
function mkCtx(directory?: string) {
  const location = directory ? { directory, workspaceID: "ws_test" } : undefined
  const calls = {
    reloads: [] as string[],
    tools: [] as any[],
    disposed: [] as string[],
    sessionHooks: {} as Record<string, (input: any) => Promise<void> | void>,
    shellHooks: {} as Record<string, (input: any) => Promise<void> | void>,
  }
  const reg = (label: string) => ({ dispose: async () => { calls.disposed.push(label) } })
  const ctx = {
    command: {
      reload: async () => { calls.reloads.push("command") },
      transform: async () => reg("command.transform"),
      list: async () => ({ location, data: [] }),
    },
    skill: { reload: async () => { calls.reloads.push("skill") } },
    agent: { reload: async () => { calls.reloads.push("agent") }, list: async () => ({ location, data: [] }) },
    tool: {
      transform: async (cb: (draft: any) => void) => {
        cb({ add: (tool: any) => calls.tools.push(tool) })
        return reg("tool.transform")
      },
    },
    session: {
      hook: async (name: string, cb: any) => {
        calls.sessionHooks[name] = cb
        return reg(`session.${name}`)
      },
    },
    shell: {
      hook: async (name: string, cb: any) => {
        calls.shellHooks[name] = cb
        return reg(`shell.${name}`)
      },
    },
  }
  return { ctx, calls }
}

let tmp: string
beforeEach(() => {
  tmp = mkdtempSync(resolve(tmpdir(), "engram-v2-test-"))
  writeFileSync(resolve(tmp, "opencode.jsonc"), "{}")
})
afterEach(() => rmSync(tmp, { recursive: true }))

const target = () => resolve(tmp, ".opencode")

describe("v2 default export", () => {
  it("is a plain { id, setup } object — the V2 plugin contract", () => {
    expect(v2Default.id).toBe("engram")
    expect(typeof v2Default.setup).toBe("function")
  })
})

describe("syncUpdateCommandV2", () => {
  it("writes commands/engram-update.md with $TARGET resolved while manifest exists", () => {
    mkdirSync(target(), { recursive: true })
    writeFileSync(resolve(target(), ".engram-update.jsonc"), PENDING_MANIFEST)

    expect(syncUpdateCommandV2(target())).toBe(true)
    const file = resolve(target(), "commands", "engram-update.md")
    expect(existsSync(file)).toBe(true)
    const content = readFileSync(file, "utf-8")
    expect(content).not.toContain("$TARGET")
    expect(content).toContain(target())
    expect(content).toContain("engram_update")
  })

  it("is idempotent while the manifest is unchanged", () => {
    mkdirSync(target(), { recursive: true })
    writeFileSync(resolve(target(), ".engram-update.jsonc"), PENDING_MANIFEST)
    syncUpdateCommandV2(target())
    expect(syncUpdateCommandV2(target())).toBe(false)
  })

  it("removes the generated file once the manifest is resolved", () => {
    mkdirSync(target(), { recursive: true })
    writeFileSync(resolve(target(), ".engram-update.jsonc"), PENDING_MANIFEST)
    syncUpdateCommandV2(target())
    rmSync(resolve(target(), ".engram-update.jsonc"))

    expect(syncUpdateCommandV2(target())).toBe(true)
    expect(existsSync(resolve(target(), "commands", "engram-update.md"))).toBe(false)
  })

  it("never deletes a user's own engram-update.md — even one that QUOTES the heading", () => {
    mkdirSync(resolve(target(), "commands"), { recursive: true })
    const userFile = "my notes about `# /engram-update — apply Engram plugin updates` and how it works"
    writeFileSync(resolve(target(), "commands", "engram-update.md"), userFile)

    expect(syncUpdateCommandV2(target())).toBe(false)
    expect(readFileSync(resolve(target(), "commands", "engram-update.md"), "utf-8")).toBe(userFile)
  })

  it("never OVERWRITES a user's own engram-update.md while a manifest is pending", () => {
    mkdirSync(resolve(target(), "commands"), { recursive: true })
    writeFileSync(resolve(target(), "commands", "engram-update.md"), "my own command")
    writeFileSync(resolve(target(), ".engram-update.jsonc"), PENDING_MANIFEST)

    expect(syncUpdateCommandV2(target())).toBe(false)
    expect(readFileSync(resolve(target(), "commands", "engram-update.md"), "utf-8")).toBe("my own command")
  })

  it("never writes through a symlinked engram-update.md (dotfiles managers)", async () => {
    const { symlinkSync } = await import("node:fs")
    mkdirSync(resolve(target(), "commands"), { recursive: true })
    const dotfiles = resolve(tmp, "dotfiles-copy.md")
    writeFileSync(dotfiles, "dotfiles-managed content")
    symlinkSync(dotfiles, resolve(target(), "commands", "engram-update.md"))
    writeFileSync(resolve(target(), ".engram-update.jsonc"), PENDING_MANIFEST)

    expect(syncUpdateCommandV2(target())).toBe(false)
    expect(readFileSync(dotfiles, "utf-8")).toBe("dotfiles-managed content")

    rmSync(resolve(target(), ".engram-update.jsonc"))
    expect(syncUpdateCommandV2(target())).toBe(false)
    expect(existsSync(resolve(target(), "commands", "engram-update.md"))).toBe(true)
  })
})

describe("readUpdateSummary", () => {
  it("returns null without a manifest", () => {
    mkdirSync(target(), { recursive: true })
    expect(readUpdateSummary(target())).toBeNull()
  })

  it("announces a pending update", () => {
    mkdirSync(target(), { recursive: true })
    writeFileSync(resolve(target(), ".engram-update.jsonc"), PENDING_MANIFEST)
    expect(readUpdateSummary(target())).toContain("Updates Engram Available!")
  })

  it("announces an in-progress update", () => {
    mkdirSync(target(), { recursive: true })
    writeFileSync(
      resolve(target(), ".engram-update.jsonc"),
      PENDING_MANIFEST.replace('"state": "pending"', '"state": "in_progress"').replace('"pending"', '"in_progress"'),
    )
    expect(readUpdateSummary(target())).toContain("partially applied")
  })

  it("returns null on a corrupt manifest", () => {
    mkdirSync(target(), { recursive: true })
    writeFileSync(resolve(target(), ".engram-update.jsonc"), "not-json}{")
    expect(readUpdateSummary(target())).toBeNull()
  })
})

describe("engram_update input schema parity (three hand-maintained copies)", () => {
  it("V2 JSON Schema enums match the V1 zod schema exactly", async () => {
    const { engramUpdateTool } = await import("../.opencode-plugin/update-tool")
    const zodArgs = (engramUpdateTool as any).args
    const jsonProps = UPDATE_TOOL_INPUT.properties

    expect(zodArgs.mode.options ?? zodArgs.mode._def.values).toEqual([...jsonProps.mode.enum])
    const zodAction = zodArgs.decisions._def.innerType.element.shape.action
    expect(zodAction.options ?? zodAction._def.values).toEqual([...jsonProps.decisions.items.properties.action.enum])
  })
})

describe("workspace directory resolution (background service: cwd ≠ workspace)", () => {
  it("takes the directory from the agent domain's location-wrapped response", async () => {
    const { ctx } = mkCtx(tmp)
    expect(await resolveWorkspaceDirectory(ctx)).toBe(tmp)
  })

  it("falls back to the command domain when agent.list is unavailable", async () => {
    const { ctx } = mkCtx(tmp)
    delete (ctx.agent as any).list
    expect(await resolveWorkspaceDirectory(ctx)).toBe(tmp)
  })

  it("returns null — NOT process.cwd() — when no domain reports a location", async () => {
    const { ctx } = mkCtx()
    expect(await resolveWorkspaceDirectory(ctx)).toBeNull()
  })

  it("setup targets the ctx-reported workspace, not the service cwd", async () => {
    const { ctx } = mkCtx(tmp)
    await createV2Setup({ runNudge: async () => "" })(ctx)
    expect(existsSync(resolve(target(), "commands", "learn.md"))).toBe(true)
  })

  it("hooks-only mode: no location → nothing written anywhere, hooks still registered", async () => {
    const { ctx, calls } = mkCtx()
    await createV2Setup({ runNudge: async () => "" })(ctx)

    expect(existsSync(target())).toBe(false)
    expect(calls.sessionHooks["context"]).toBeDefined()
    expect(calls.shellHooks["create.before"]).toBeDefined()
  })
})

describe("setup — registrations against a recording ctx", () => {
  const mkSetup = (nudge = "") => createV2Setup({ runNudge: async () => nudge, directory: tmp })

  it("registers engram_update tool only while a manifest exists", async () => {
    mkdirSync(target(), { recursive: true })
    writeFileSync(resolve(target(), ".engram-update.jsonc"), PENDING_MANIFEST)

    const { ctx, calls } = mkCtx()
    await mkSetup()(ctx)

    expect(calls.tools).toHaveLength(1)
    expect(calls.tools[0].name).toBe("engram_update")
    expect(calls.tools[0].input).toBe(UPDATE_TOOL_INPUT)
    expect(calls.tools[0].options).toEqual({ codemode: false })

    const result = await calls.tools[0].execute({ target: target(), mode: "skip" })
    expect(result.content).toContain("[engram]")
    expect(result.output).toBeUndefined()
  })

  it("does NOT register the tool without a manifest", async () => {
    const { ctx, calls } = mkCtx()
    await mkSetup()(ctx)
    expect(calls.tools).toHaveLength(0)
  })

  it("surfaces a manifest that lands MID-LIFE: tool + command file + reload on next session", async () => {
    const { ctx, calls } = mkCtx()
    await mkSetup()(ctx)
    expect(calls.tools).toHaveLength(0)

    writeFileSync(resolve(target(), ".engram-update.jsonc"), PENDING_MANIFEST)
    const sc = { sessionID: "s1", system: [] as any[] }
    await calls.sessionHooks["context"](sc)

    expect(calls.tools).toHaveLength(1)
    expect(existsSync(resolve(target(), "commands", "engram-update.md"))).toBe(true)
    expect(calls.reloads.filter((r) => r === "command").length).toBeGreaterThan(0)
    expect(sc.system.map((p) => p.text).join("")).toContain("Updates Engram Available!")
  })

  it("pushes the nudge as a SystemPart once per session, not once per request", async () => {
    const { ctx, calls } = mkCtx()
    await mkSetup("2 reviews due")(ctx)

    const hook = calls.sessionHooks["context"]
    expect(hook).toBeDefined()

    const first = { sessionID: "s1", system: [] as any[] }
    await hook(first)
    expect(first.system).toEqual([{ type: "text", text: "\n[engram] 2 reviews due" }])

    const secondRequestSameSession = { sessionID: "s1", system: [] as any[] }
    await hook(secondRequestSameSession)
    expect(secondRequestSameSession.system).toHaveLength(0)

    const newSession = { sessionID: "s2", system: [] as any[] }
    await hook(newSession)
    expect(newSession.system).toHaveLength(1)
  })

  it("adds the update notification to the system parts while pending", async () => {
    mkdirSync(target(), { recursive: true })
    writeFileSync(resolve(target(), ".engram-update.jsonc"), PENDING_MANIFEST)

    const { ctx, calls } = mkCtx()
    await mkSetup("")(ctx)

    const sc = { sessionID: "s1", system: [] as any[] }
    await calls.sessionHooks["context"](sc)
    expect(sc.system).toHaveLength(1)
    expect(sc.system[0].text).toContain("Updates Engram Available!")
  })

  it("injects ENGRAM_ROOT / OPENCODE_PLUGIN_ROOT on shell create.before", async () => {
    const { ctx, calls } = mkCtx()
    await mkSetup()(ctx)

    const hook = calls.shellHooks["create.before"]
    expect(hook).toBeDefined()

    const shell = { cwd: tmp, env: {} as Record<string, string> }
    await hook(shell)
    expect(shell.env["ENGRAM_ROOT"]).toBeDefined()
    expect(shell.env["OPENCODE_PLUGIN_ROOT"]).toBe(shell.env["ENGRAM_ROOT"])
  })

  it("points the shell env at the extracted target once engram.py is local", async () => {
    mkdirSync(resolve(target(), "scripts"), { recursive: true })
    writeFileSync(resolve(target(), "scripts", "engram.py"), "# engine")

    const { ctx, calls } = mkCtx()
    await mkSetup()(ctx)

    const shell = { cwd: tmp, env: {} as Record<string, string> }
    await calls.shellHooks["create.before"](shell)
    expect(shell.env["ENGRAM_ROOT"]).toBe(target())
  })

  it("degrades to silence on a runtime with no domains at all", async () => {
    await expect(mkSetup()({} as any)).resolves.not.toThrow
    await expect(mkSetup()(undefined as any)).resolves.not.toThrow
    const cleanup = await mkSetup()({} as any)
    if (cleanup) await cleanup()
  })
})

describe("extraction scope (second wrong-directory class: non-workspace locations)", () => {
  it("refuses a location that owns no opencode config — the service root would fall through to the global dir", async () => {
    // HOME is sandboxed so the assertion can SEE the global fallback: without
    // the extractionScope guard, setup extracts into {HOME}/.config/opencode —
    // the exact pollution the release e2e caught on a real machine. The first
    // version of this test only checked the bare dir and stayed green with the
    // guard reverted (the wrong write goes global, not local) — a fake check.
    const bare = mkdtempSync(resolve(tmpdir(), "engram-v2-bare-"))
    const fakeHome = mkdtempSync(resolve(tmpdir(), "engram-v2-home-"))
    const realHome = process.env.HOME
    process.env.HOME = fakeHome
    try {
      const { ctx, calls } = mkCtx(bare)
      await createV2Setup({ runNudge: async () => "" })(ctx)

      expect(existsSync(resolve(bare, ".opencode"))).toBe(false)
      expect(existsSync(resolve(bare, "AGENTS.md"))).toBe(false)
      expect(existsSync(resolve(fakeHome, ".config", "opencode", "AGENTS.md"))).toBe(false)
      expect(existsSync(resolve(fakeHome, ".config", "opencode", "skills"))).toBe(false)
      expect(calls.sessionHooks["context"]).toBeDefined()
      expect(calls.shellHooks["create.before"]).toBeDefined()
    } finally {
      process.env.HOME = realHome
      rmSync(bare, { recursive: true })
      rmSync(fakeHome, { recursive: true })
    }
  })

  it("allows a config-owning workspace and the global config dir itself", () => {
    expect(extractionScope(tmp)).toBe(tmp)
    const home = process.env.HOME || process.env.USERPROFILE || "/tmp"
    const globalDir = resolve(home, ".config", "opencode")
    expect(extractionScope(globalDir)).toBe(globalDir)
    expect(extractionScope(null)).toBeNull()
  })
})

describe("mid-session update resolution heals without a restart", () => {
  it("the next session re-extracts what /engram-update removed", async () => {
    const { ctx, calls } = mkCtx(tmp)
    await createV2Setup({ runNudge: async () => "" })(ctx)
    expect(existsSync(resolve(target(), "skills", "learn", "SKILL.md"))).toBe(true)

    // /engram-update auto mode deletes refreshed files + the version guard.
    rmSync(resolve(target(), "skills", "learn", "SKILL.md"))
    rmSync(resolve(target(), ".engram-version.jsonc"))
    calls.reloads.length = 0

    const sc = { sessionID: "s-next", system: [] as any[] }
    await calls.sessionHooks["context"](sc)

    expect(existsSync(resolve(target(), "skills", "learn", "SKILL.md"))).toBe(true)
    expect(calls.reloads).toContain("skill")
    expect(calls.reloads).toContain("command")
  })

  it("is a no-op on a normal session (version guard intact)", async () => {
    const { ctx, calls } = mkCtx(tmp)
    await createV2Setup({ runNudge: async () => "" })(ctx)
    const before = readFileSync(resolve(target(), ".engram-version.jsonc"), "utf-8")
    calls.reloads.length = 0

    const sc = { sessionID: "s-quiet", system: [] as any[] }
    await calls.sessionHooks["context"](sc)

    expect(readFileSync(resolve(target(), ".engram-version.jsonc"), "utf-8")).toBe(before)
    expect(calls.reloads).not.toContain("skill")
  })
})

describe("SDK drift tolerance", () => {
  it("registerHook supports the mapped-object hook form of the older V2 line", async () => {
    const seen: string[] = []
    const domain = {
      hook: {
        context: async (cb: any) => {
          seen.push("registered")
          await cb({ sessionID: "s1", system: [] })
          return { dispose: async () => {} }
        },
      },
    }
    const r = await registerHook(domain, "context", () => { seen.push("fired") })
    expect(seen).toEqual(["registered", "fired"])
    expect(r).toBeDefined()
  })

  it("registerHook returns undefined for absent domains and hooks", async () => {
    expect(await registerHook(undefined, "context", () => {})).toBeUndefined()
    expect(await registerHook({}, "context", () => {})).toBeUndefined()
  })

  it("a tool draft without add() does not throw out of the transform callback", async () => {
    mkdirSync(target(), { recursive: true })
    writeFileSync(resolve(target(), ".engram-update.jsonc"), PENDING_MANIFEST)

    const { ctx } = mkCtx()
    ;(ctx.tool as any).transform = async (cb: (draft: any) => void) => {
      cb({})
      return { dispose: async () => {} }
    }
    await expect(createV2Setup({ runNudge: async () => "", directory: tmp })(ctx)).resolves.not.toThrow
  })

  it("setup returns a cleanup that disposes every registration", async () => {
    const { ctx, calls } = mkCtx(tmp)
    const cleanup = await createV2Setup({ runNudge: async () => "" })(ctx)
    expect(typeof cleanup).toBe("function")

    await (cleanup as () => Promise<void>)()
    expect(calls.disposed).toContain("session.context")
    expect(calls.disposed).toContain("shell.create.before")
  })
})
