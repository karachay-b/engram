import { describe, it, expect, beforeEach, afterEach } from "vitest"
import { tmpdir } from "node:os"
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, existsSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { symlinkSync } from "node:fs"
import { selfExtract } from "../.opencode-plugin/install"
import { runEngramUpdate } from "../.opencode-plugin/update-core"

/**
 * Issue #20 — the engine reads gold/assessor-gold.jsonl and
 * experiments/<preset>.json from _plugin_root() (engram.py's own location),
 * so an extraction that omits them fails 10 selftest checks on every fresh
 * opencode install. docs/ is cited by the extracted skills and promised by
 * the AGENTS.md block. All three must extract, with the same new-files-only
 * semantics as the incumbent dirs.
 */
describe("issue #20 — selfExtract ships gold/, experiments/, docs/", () => {
  let tmp: string
  let pkg: string

  beforeEach(() => {
    tmp = mkdtempSync(resolve(tmpdir(), "engram-test-"))
    writeFileSync(resolve(tmp, "opencode.jsonc"), "{}")
    pkg = resolve(tmp, "pkg")
    mkdirSync(resolve(pkg, "skills"), { recursive: true })
    writeFileSync(resolve(pkg, "skills", "SKILL.md"), "skill")
    mkdirSync(resolve(pkg, "agents"), { recursive: true })
    writeFileSync(resolve(pkg, "agents", "agent.md"), "agent")
    mkdirSync(resolve(pkg, "scripts"), { recursive: true })
    writeFileSync(resolve(pkg, "scripts", "engram.py"), "script")
    mkdirSync(resolve(pkg, "gold"), { recursive: true })
    writeFileSync(resolve(pkg, "gold", "assessor-gold.jsonl"), '{"id":"g_001"}\n')
    mkdirSync(resolve(pkg, "experiments"), { recursive: true })
    writeFileSync(resolve(pkg, "experiments", "interleaving-vs-blocked.json"), "{}")
    mkdirSync(resolve(pkg, "docs"), { recursive: true })
    writeFileSync(resolve(pkg, "docs", "05-affective-layers.md"), "docs")
    writeFileSync(resolve(pkg, "package.json"), JSON.stringify({ version: "1.13.2" }))
  })
  afterEach(() => rmSync(tmp, { recursive: true }))

  it("fresh install extracts the engine's gold set, presets, and docs", () => {
    selfExtract(pkg, tmp, "1.13.2")
    const target = resolve(tmp, ".opencode")
    expect(existsSync(resolve(target, "gold", "assessor-gold.jsonl"))).toBe(true)
    expect(existsSync(resolve(target, "experiments", "interleaving-vs-blocked.json"))).toBe(true)
    expect(existsSync(resolve(target, "docs", "05-affective-layers.md"))).toBe(true)
  })

  it("never overwrites an existing extracted gold file (new-files-only)", () => {
    const target = resolve(tmp, ".opencode")
    mkdirSync(resolve(target, "gold"), { recursive: true })
    writeFileSync(resolve(target, "gold", "assessor-gold.jsonl"), "locally-edited\n")

    selfExtract(pkg, tmp, "1.13.2")
    expect(readFileSync(resolve(target, "gold", "assessor-gold.jsonl"), "utf-8")).toBe("locally-edited\n")
  })

  it("version bump manifests gold/experiments/docs so bundled updates can land", () => {
    const target = resolve(tmp, ".opencode")
    // Simulate an older install whose extracted copies differ from the package.
    mkdirSync(resolve(target, "gold"), { recursive: true })
    writeFileSync(resolve(target, "gold", "assessor-gold.jsonl"), "old-gold\n")
    mkdirSync(resolve(target, "experiments"), { recursive: true })
    writeFileSync(resolve(target, "experiments", "interleaving-vs-blocked.json"), "old")
    mkdirSync(resolve(target, "docs"), { recursive: true })
    writeFileSync(resolve(target, "docs", "05-affective-layers.md"), "old")
    writeFileSync(resolve(target, ".engram-version.jsonc"), JSON.stringify({ version: "1.13.1" }))

    selfExtract(pkg, tmp, "1.13.2")

    const manifest = JSON.parse(readFileSync(resolve(target, ".engram-update.jsonc"), "utf-8"))
    expect(manifest.categories.gold.skipped).toContain("gold/assessor-gold.jsonl")
    expect(manifest.categories.experiments.skipped).toContain("experiments/interleaving-vs-blocked.json")
    expect(manifest.categories.docs.skipped).toContain("docs/05-affective-layers.md")
  })

  it("auto update deletes stale copies and the NEXT extract restores every one", () => {
    // The invariant behind auto mode: every category writeUpdateManifest can
    // put in skipped[] must be restorable — DIRS for the six merged dirs,
    // generateCommands for commands/. A category outside that set would have
    // its files deleted by auto and never re-created (bug class #2, silent
    // data loss). This drives the full round-trip rather than asserting the
    // lists match, so a future category addition without a restore path
    // fails here.
    const target = resolve(tmp, ".opencode")
    for (const [dir, file] of [
      ["skills", "SKILL.md"], ["agents", "agent.md"], ["scripts", "engram.py"],
      ["gold", "assessor-gold.jsonl"], ["experiments", "interleaving-vs-blocked.json"],
      ["docs", "05-affective-layers.md"],
    ] as const) {
      mkdirSync(resolve(target, dir), { recursive: true })
      writeFileSync(resolve(target, dir, file), "stale-old-copy")
    }
    writeFileSync(resolve(target, ".engram-version.jsonc"), JSON.stringify({ version: "1.13.1" }))

    selfExtract(pkg, tmp, "1.13.2")
    const manifest = JSON.parse(readFileSync(resolve(target, ".engram-update.jsonc"), "utf-8"))
    const allSkipped: string[] = Object.values(manifest.categories).flatMap((c: any) => c.skipped)
    expect(allSkipped.length).toBeGreaterThanOrEqual(6)

    runEngramUpdate({ target, mode: "auto" })
    for (const f of allSkipped) expect(existsSync(resolve(target, f)), `${f} deleted`).toBe(false)

    selfExtract(pkg, tmp, "1.13.2")
    for (const f of allSkipped) expect(existsSync(resolve(target, f)), `${f} restored`).toBe(true)
  })

  it("a checkpointed per-file DELETE heals on the next extract — never a hole across restarts", () => {
    // Review finding (MED-HIGH): per_file deleted the file, checkpointed with
    // categories remaining, and left the version guard in place — so
    // selfExtract early-returned forever and gold/ stayed empty across
    // restarts while the gold audit ran against nothing and exited 0
    // (issue #20's symptom re-entered through the update flow).
    const target = resolve(tmp, ".opencode")
    selfExtract(pkg, tmp, "1.13.2")
    writeFileSync(resolve(target, ".engram-version.jsonc"), JSON.stringify({ version: "1.13.1" }))
    // Make gold AND scripts differ so the manifest has two categories pending.
    writeFileSync(resolve(target, "gold", "assessor-gold.jsonl"), "old-gold\n")
    writeFileSync(resolve(target, "scripts", "engram.py"), "old-engine")
    selfExtract(pkg, tmp, "1.13.2")

    const out = runEngramUpdate({ target, mode: "per_file", decisions: [
      { file: "gold/assessor-gold.jsonl", action: "delete" },
    ] })
    expect(out).toContain("Checkpoint saved")
    expect(existsSync(resolve(target, "gold", "assessor-gold.jsonl"))).toBe(false)
    // The heal: the version guard must be gone, so the next session start…
    expect(existsSync(resolve(target, ".engram-version.jsonc"))).toBe(false)
    selfExtract(pkg, tmp, "1.13.2")
    // …restores the deleted file with the NEW content, keeps the preserved one,
    // and the manifest survives for the remaining decision.
    expect(readFileSync(resolve(target, "gold", "assessor-gold.jsonl"), "utf-8")).toBe('{"id":"g_001"}\n')
    expect(readFileSync(resolve(target, "scripts", "engram.py"), "utf-8")).toBe("old-engine")
    const manifest = JSON.parse(readFileSync(resolve(target, ".engram-update.jsonc"), "utf-8"))
    expect(manifest.remaining).toContain("scripts")
  })

  it("delete paths refuse a symlinked category dir — the unlink must never escape the target", () => {
    // Review finding: isWithinTarget is lexical; a symlinked docs/ (the
    // contributor-checkout pattern) routed unlinkSync to the real file
    // outside the target.
    const target = resolve(tmp, ".opencode")
    mkdirSync(target, { recursive: true })
    const outside = resolve(tmp, "real-docs")
    mkdirSync(outside, { recursive: true })
    writeFileSync(resolve(outside, "05-affective-layers.md"), "the real file")
    symlinkSync(outside, resolve(target, "docs"))
    writeFileSync(resolve(target, ".engram-update.jsonc"), JSON.stringify({
      from: "1.13.1", to: "1.13.2", source: pkg, state: "pending", applied: [],
      remaining: ["docs"],
      categories: { docs: { added: [], skipped: ["docs/05-affective-layers.md"] } },
    }))

    runEngramUpdate({ target, mode: "auto" })
    expect(existsSync(resolve(outside, "05-affective-layers.md")), "auto escaped").toBe(true)

    writeFileSync(resolve(target, ".engram-update.jsonc"), JSON.stringify({
      from: "1.13.1", to: "1.13.2", source: pkg, state: "pending", applied: [],
      remaining: ["docs"],
      categories: { docs: { added: [], skipped: ["docs/05-affective-layers.md"] } },
    }))
    const out = runEngramUpdate({ target, mode: "per_file", decisions: [
      { file: "docs/05-affective-layers.md", action: "delete" },
    ] })
    expect(existsSync(resolve(outside, "05-affective-layers.md")), "per_file escaped").toBe(true)
    expect(out).toContain("not ours to delete")
  })

  it("docs/ extracts top-level only — internal subdirectories stay out of tree AND manifest", () => {
    mkdirSync(resolve(pkg, "docs", "release-audits"), { recursive: true })
    writeFileSync(resolve(pkg, "docs", "release-audits", "v1.10.0-numbers-audit.md"), "internal")
    const target = resolve(tmp, ".opencode")

    selfExtract(pkg, tmp, "1.13.2")
    expect(existsSync(resolve(target, "docs", "05-affective-layers.md"))).toBe(true)
    expect(existsSync(resolve(target, "docs", "release-audits"))).toBe(false)

    // The manifest walk must agree with the copy — otherwise every bump
    // lists "added" files extraction never places.
    rmSync(resolve(target, ".engram-version.jsonc"))
    writeFileSync(resolve(target, ".engram-version.jsonc"), JSON.stringify({ version: "0.9.0" }))
    writeFileSync(resolve(target, "docs", "05-affective-layers.md"), "user-touched")
    selfExtract(pkg, tmp, "1.13.2")
    const manifest = JSON.parse(readFileSync(resolve(target, ".engram-update.jsonc"), "utf-8"))
    const docsFiles = [...manifest.categories.docs.added, ...manifest.categories.docs.skipped]
    expect(docsFiles).toContain("docs/05-affective-layers.md")
    expect(docsFiles.some((f: string) => f.includes("release-audits"))).toBe(false)
  })
})

describe("upgrade honesty — agents diff through the extraction transform", () => {
  let tmp: string
  let pkg: string
  const AGENT_SRC = `---\nname: engram-assessor\ndescription: blind grader\ntools: Read, Bash\n---\n\nGrade blindly.\n`

  beforeEach(() => {
    tmp = mkdtempSync(resolve(tmpdir(), "engram-test-"))
    writeFileSync(resolve(tmp, "opencode.jsonc"), "{}")
    pkg = resolve(tmp, "pkg")
    mkdirSync(resolve(pkg, "agents"), { recursive: true })
    writeFileSync(resolve(pkg, "agents", "engram-assessor.md"), AGENT_SRC)
    mkdirSync(resolve(pkg, "scripts"), { recursive: true })
    writeFileSync(resolve(pkg, "scripts", "engram.py"), "engine-v2")
    writeFileSync(resolve(pkg, "package.json"), JSON.stringify({ version: "1.13.2" }))
  })
  afterEach(() => rmSync(tmp, { recursive: true }))

  it("an UNCHANGED agent is not manifested just because extraction transformed it", () => {
    // Review finding (MED): the extracted copy can never byte-match the
    // packaged source (mode: subagent etc. injected), so a raw compare told
    // every upgrader all agents were "preserved, needs decision" on every
    // bump — and rendered the transform backwards in the diff.
    selfExtract(pkg, tmp, "1.13.2")
    const target = resolve(tmp, ".opencode")
    writeFileSync(resolve(target, ".engram-version.jsonc"), JSON.stringify({ version: "1.13.1" }))
    writeFileSync(resolve(pkg, "scripts", "engram.py"), "engine-v3") // force a manifest

    selfExtract(pkg, tmp, "1.13.2")
    const manifest = JSON.parse(readFileSync(resolve(target, ".engram-update.jsonc"), "utf-8"))
    expect(manifest.categories.agents.skipped).toEqual([])
    expect(manifest.remaining).not.toContain("agents")
  })

  it("a genuinely changed agent IS manifested, and its diff never shows the transform backwards", () => {
    selfExtract(pkg, tmp, "1.13.2")
    const target = resolve(tmp, ".opencode")
    writeFileSync(resolve(target, ".engram-version.jsonc"), JSON.stringify({ version: "1.13.1" }))
    writeFileSync(resolve(pkg, "agents", "engram-assessor.md"),
      AGENT_SRC.replace("Grade blindly.", "Grade blindly. Round down."))

    selfExtract(pkg, tmp, "1.13.2")
    const manifest = JSON.parse(readFileSync(resolve(target, ".engram-update.jsonc"), "utf-8"))
    expect(manifest.categories.agents.skipped).toEqual(["agents/engram-assessor.md"])

    const diff = readFileSync(resolve(target, ".engram-update.diff"), "utf-8")
    expect(diff).toContain("Round down.")
    expect(diff).not.toContain("-mode: subagent")
    expect(diff).not.toContain("-hidden: true")
  })
})
