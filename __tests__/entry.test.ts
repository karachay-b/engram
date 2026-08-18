import { describe, it, expect } from "vitest"
import { readFileSync, existsSync } from "node:fs"
import { resolve } from "node:path"

/**
 * Issue #19 — one package key must satisfy both runtimes' loaders.
 *
 * These tests emulate the ACTUAL resolution + validation logic of both
 * OpenCode lines (quoted from source in entry.ts) against the real
 * package.json, then import whatever each chain resolves and run each
 * validator's checks on it. A regression in EITHER the exports map (e.g.
 * ./server pointing back at a V2-only file) or the module shape (entry.ts
 * losing server or setup) fails here.
 */

const pkgRoot = resolve(__dirname, "..")
const pkgJson = JSON.parse(readFileSync(resolve(pkgRoot, "package.json"), "utf-8"))

/** V1 shared.ts extractExportValue, verbatim behavior. */
function extractExportValue(value: any): string | undefined {
  if (typeof value === "string") return value
  if (typeof value !== "object" || value === null || Array.isArray(value)) return undefined
  for (const key of ["import", "default"]) {
    const nested = value[key]
    if (typeof nested === "string") return nested
  }
  return undefined
}

/** V1 resolvePackageEntrypoint for kind "server": exports["./server"] first, then main. */
function v1ResolveServerEntrypoint(): string | undefined {
  const exports = pkgJson.exports
  if (exports && typeof exports === "object") {
    const raw = extractExportValue(exports["./server"])
    if (raw) return raw
  }
  const main = pkgJson.main
  if (typeof main !== "string" || !main.trim()) return undefined
  return main.trim()
}

/** V1 readV1Plugin's checks on the loaded module. */
function v1Validate(mod: any) {
  expect(mod.default, "must default export an object").toBeTypeOf("object")
  expect(mod.default.server, "must default export an object with server()").toBeTypeOf("function")
  // "must default export either server() or tui(), not both"
  expect(mod.default.tui).toBeUndefined()
}

/** V2 PluginModule schema: id (string) + setup (function); extra keys tolerated. */
function v2Validate(mod: any) {
  expect(mod.default).toBeTypeOf("object")
  expect(mod.default.id).toBeTypeOf("string")
  expect(mod.default.setup).toBeTypeOf("function")
}

describe("issue #19 — combined entry satisfies every probe chain", () => {
  it("V1 chain: exports['./server'] wins over main and passes readV1Plugin", async () => {
    const raw = v1ResolveServerEntrypoint()
    expect(raw).toBeDefined()
    // The ./server key must exist — V1 probes it BEFORE main, so if it exists
    // it must be V1-valid; deleting the key would also be fine (main fallback)
    // but the current design keeps it for the older V2 line.
    expect(extractExportValue(pkgJson.exports["./server"])).toBe(raw)
    const file = resolve(pkgRoot, raw!)
    expect(existsSync(file)).toBe(true)
    v1Validate(await import(file))
  })

  it("V1 fallback: main alone also passes readV1Plugin", async () => {
    const main = pkgJson.main
    expect(main).toBeTypeOf("string")
    const file = resolve(pkgRoot, main)
    expect(existsSync(file)).toBe(true)
    v1Validate(await import(file))
  })

  it("V2 current line: bare-name resolution (exports['.']) passes the PluginModule schema", async () => {
    const raw = extractExportValue(pkgJson.exports["."])
    expect(raw).toBeDefined()
    const file = resolve(pkgRoot, raw!)
    expect(existsSync(file)).toBe(true)
    v2Validate(await import(file))
  })

  it("V2 earlier next line: exports['./server'] passes the PluginModule schema", async () => {
    const raw = extractExportValue(pkgJson.exports["./server"])
    const file = resolve(pkgRoot, raw!)
    v2Validate(await import(file))
  })

  it("./v2 stays a pure V2 adapter for explicit reference", async () => {
    const raw = extractExportValue(pkgJson.exports["./v2"])
    expect(raw).toBeDefined()
    const mod = await import(resolve(pkgRoot, raw!))
    v2Validate(mod)
  })

  it("the combined entry's STATIC module graph never links @opencode-ai/plugin", () => {
    // Review finding (HIGH, v1.13.2): update-tool.ts value-imports the V1 SDK
    // and calls tool() at module scope. A static path from entry.ts to it
    // links the SDK into the V2 load path, where the specifier can be absent
    // or its root export reshuffled (it moved once between beta lines) — an
    // ESM link error there kills the plugin before any try/catch runs.
    // The SDK must only load lazily, inside server(), which V1 alone calls.
    // Walked from the source, not from memory: every static import/export-from
    // reachable from entry.ts, comments stripped so a doc-comment code sample
    // cannot satisfy or trip the check.
    const seen = new Set<string>()
    const bare = new Set<string>()
    const walk = (file: string) => {
      if (seen.has(file)) return
      seen.add(file)
      const src = readFileSync(file, "utf-8").replace(/\/\*[\s\S]*?\*\//g, "")
      const specs: string[] = []
      for (const re of [
        /^import\s+(?!type\b)[^;'"]*?from\s*["']([^"']+)["']/gm,
        /^import\s*["']([^"']+)["']/gm,
        /^export\s+[^;'"]*?from\s*["']([^"']+)["']/gm,
      ]) {
        for (let m = re.exec(src); m; m = re.exec(src)) specs.push(m[1])
      }
      for (const spec of specs) {
        if (spec.startsWith(".")) {
          const next = resolve(file, "..", spec.replace(/\.js$/, ".ts"))
          if (existsSync(next)) walk(next)
        } else {
          bare.add(spec)
        }
      }
    }
    walk(resolve(pkgRoot, ".opencode-plugin", "entry.ts"))
    expect(seen.size).toBeGreaterThan(5) // the walker actually walked
    expect([...bare].filter(s => s.startsWith("@opencode-ai"))).toEqual([])
  })

  it("the combined entry reuses the real adapters, not copies", async () => {
    const entry = await import(resolve(pkgRoot, ".opencode-plugin", "entry.ts"))
    const v1 = await import(resolve(pkgRoot, ".opencode-plugin", "index.ts"))
    const v2 = await import(resolve(pkgRoot, ".opencode-plugin", "v2.ts"))
    expect(entry.default.server).toBe(v1.server)
    expect(entry.default.setup).toBe(v2.setup)
    expect(entry.default.id).toBe("engram")
  })
})
