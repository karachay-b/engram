import { describe, it, expect, beforeEach, afterEach } from "vitest"
import { tmpdir } from "node:os"
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, readFileSync, symlinkSync, existsSync } from "node:fs"
import { resolve } from "node:path"
import { selfExtract } from "../.opencode-plugin/install"
import { applyUpdate } from "../.opencode-plugin/update"

/**
 * Regression guard for the v1.3.0 review's symlink finding: writeFileSync and
 * copyFileSync FOLLOW symlinks, and a contributor checkout links
 * extracted-target agents/*.md files to the canonical agents/ tree (the
 * pre-v1.10.1 checkout did exactly that). Without the lstat
 * guards, self-extraction (and applyUpdate) rewrite the canonical files —
 * the ones every other platform ships — through the link.
 */

let tmp: string
beforeEach(() => { tmp = mkdtempSync(resolve(tmpdir(), "engram-symlink-test-")) })
afterEach(() => rmSync(tmp, { recursive: true }))

const CANONICAL = "---\nname: engram-assessor\ndescription: canonical\ntools: Read\n---\n\nCanonical body.\n"

/** A fake npm-installed package root ("node_modules" in the path → npm mode). */
function stagePackage(): string {
  const pkgRoot = resolve(tmp, "node_modules", "opencode-engram-learning")
  mkdirSync(resolve(pkgRoot, "agents"), { recursive: true })
  writeFileSync(resolve(pkgRoot, "package.json"), JSON.stringify({ version: "9.9.9" }))
  writeFileSync(resolve(pkgRoot, "agents", "assessor.md"), CANONICAL)
  return pkgRoot
}

describe("agent transform never writes through a symlink", () => {
  it("selfExtract leaves the canonical file behind a symlinked agent untouched", () => {
    const pkgRoot = stagePackage()
    const project = resolve(tmp, "project")
    mkdirSync(project, { recursive: true })
    writeFileSync(resolve(project, "opencode.jsonc"), "{}")

    const canonical = resolve(tmp, "canonical-assessor.md")
    writeFileSync(canonical, CANONICAL)
    const agentsDir = resolve(project, ".opencode", "agents")
    mkdirSync(agentsDir, { recursive: true })
    symlinkSync(canonical, resolve(agentsDir, "assessor.md"))

    selfExtract(pkgRoot, project, "9.9.9")

    expect(readFileSync(canonical, "utf-8")).toBe(CANONICAL)
  })

  it("selfExtract still transforms real files in the same directory", () => {
    const pkgRoot = stagePackage()
    const project = resolve(tmp, "project")
    mkdirSync(project, { recursive: true })
    writeFileSync(resolve(project, "opencode.jsonc"), "{}")

    selfExtract(pkgRoot, project, "9.9.9")

    const extracted = readFileSync(resolve(project, ".opencode", "agents", "assessor.md"), "utf-8")
    expect(extracted).toContain("mode: subagent")
    expect(extracted).toContain("hidden: true")
  })

  it("transforming an already-transformed agent is a no-op (tools: survives a second bump)", () => {
    const pkgRoot = stagePackage()
    const project = resolve(tmp, "project")
    mkdirSync(project, { recursive: true })
    writeFileSync(resolve(project, "opencode.jsonc"), "{}")

    selfExtract(pkgRoot, project, "9.9.9")
    const extracted = resolve(project, ".opencode", "agents", "assessor.md")
    const afterFirst = readFileSync(extracted, "utf-8")
    expect(afterFirst).toContain("tools:")
    expect(afterFirst).toContain("Read: true")

    rmSync(resolve(project, ".opencode", ".engram-version.jsonc"))
    selfExtract(pkgRoot, project, "10.0.0")
    const afterSecond = readFileSync(extracted, "utf-8")
    expect(afterSecond).toBe(afterFirst)
  })

  it("selfExtract leaves a valid version file and no temp file behind", () => {
    const pkgRoot = stagePackage()
    const project = resolve(tmp, "project")
    mkdirSync(project, { recursive: true })
    writeFileSync(resolve(project, "opencode.jsonc"), "{}")

    selfExtract(pkgRoot, project, "9.9.9")
    const vf = resolve(project, ".opencode", ".engram-version.jsonc")
    expect(JSON.parse(readFileSync(vf, "utf-8")).version).toBe("9.9.9")
    expect(existsSync(vf + ".tmp")).toBe(false)
  })

  it("applyUpdate skips a symlinked destination", () => {
    const source = resolve(tmp, "pkg")
    mkdirSync(resolve(source, "agents"), { recursive: true })
    writeFileSync(resolve(source, "agents", "assessor.md"), "---\nname: new\n---\n\nNew body.\n")

    const target = resolve(tmp, "target")
    mkdirSync(resolve(target, "agents"), { recursive: true })
    const canonical = resolve(tmp, "canonical2.md")
    writeFileSync(canonical, CANONICAL)
    symlinkSync(canonical, resolve(target, "agents", "assessor.md"))
    writeFileSync(resolve(target, ".engram-update.jsonc"), JSON.stringify({
      from: "1.0.0", to: "9.9.9", source,
      categories: { agents: { added: [], skipped: ["agents/assessor.md"] } },
      state: "pending", applied: [], remaining: ["agents"],
    }))

    const count = applyUpdate(target, "agents", ["agents/assessor.md"])

    expect(count).toBe(0)
    expect(readFileSync(canonical, "utf-8")).toBe(CANONICAL)
  })
})
