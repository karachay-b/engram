import { describe, it, expect, beforeEach, afterEach } from "vitest"
import { tmpdir } from "node:os"
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, existsSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { runEngramUpdate } from "../.opencode-plugin/update-core"
import { readManifest } from "../.opencode-plugin/update"

/**
 * Input-validation guards, added after the v1.3.0 review: V2 hands the raw
 * model-supplied tool input straight to runEngramUpdate (no zod in front, and
 * the runtime may not enforce the JSON Schema). Malformed input must produce
 * a message — never a throw — and must never consume a manifest entry.
 */

let tmp: string
beforeEach(() => {
  tmp = mkdtempSync(resolve(tmpdir(), "engram-core-test-"))
  writeFileSync(resolve(tmp, ".engram-update.jsonc"), JSON.stringify({
    from: "1.0.0",
    to: "1.1.0",
    source: "/nowhere",
    categories: { skills: { added: [], skipped: ["skills/learn.md"] } },
    state: "pending",
    applied: [],
    remaining: ["skills"],
  }))
  mkdirSync(resolve(tmp, "skills"), { recursive: true })
  writeFileSync(resolve(tmp, "skills", "learn.md"), "user-edited content")
})
afterEach(() => rmSync(tmp, { recursive: true }))

describe("runEngramUpdate input validation", () => {
  it("a decision missing `action` is reported and NOT consumed from skipped[]", () => {
    const out = runEngramUpdate({ target: tmp, mode: "per_file", decisions: [{ file: "skills/learn.md" }] } as any)

    expect(out).toContain("malformed decision")
    const m = readManifest(tmp)!
    expect(m.categories.skills.skipped).toContain("skills/learn.md")
    expect(m.remaining).toContain("skills")
    expect(existsSync(resolve(tmp, "skills", "learn.md"))).toBe(true)
  })

  it("a non-array decisions value returns a message instead of throwing", () => {
    expect(runEngramUpdate({ target: tmp, mode: "per_file", decisions: "abc" } as any)).toContain("must be an array")
  })

  it("an unknown mode returns a message instead of routing", () => {
    expect(runEngramUpdate({ target: tmp, mode: "explode" } as any)).toBe("[engram] Unknown mode.")
  })

  it("a non-string target returns a message instead of throwing", () => {
    expect(runEngramUpdate({ target: 42, mode: "skip" } as any)).toContain("target must be a path string")
    expect(runEngramUpdate(null as any)).toContain("expected an object")
  })

  it("a manifest with the wrong SHAPE degrades to the corrupt message, never throws", () => {
    for (const bad of [
      { state: "pending", categories: null, remaining: [], applied: [] },
      { state: "pending", categories: { skills: {} }, remaining: [], applied: [] },
      { state: "pending", categories: { skills: { added: [], skipped: [] } }, remaining: "skills", applied: [] },
      { state: "pending", categories: [], remaining: [], applied: [] },
    ]) {
      writeFileSync(resolve(tmp, ".engram-update.jsonc"), JSON.stringify(bad))
      expect(runEngramUpdate({ target: tmp, mode: "auto" })).toContain("Corrupt manifest")
      expect(runEngramUpdate({ target: tmp, mode: "per_file", decisions: [{ file: "skills/learn.md", action: "delete" }] })).toContain("Corrupt manifest")
    }
  })

  it("cleanup clears a corrupt-JSON manifest — the template's STEP-2 recovery path", () => {
    writeFileSync(resolve(tmp, ".engram-update.jsonc"), "not-json}{")
    const out = runEngramUpdate({ target: tmp, mode: "cleanup" })
    expect(out).toContain("State cleaned")
    expect(existsSync(resolve(tmp, ".engram-update.jsonc"))).toBe(false)
  })

  it("cleanup clears a WRONG-SHAPE manifest (the v1.12.0 regression: the shape gate made this unrecoverable)", () => {
    writeFileSync(resolve(tmp, ".engram-update.jsonc"), JSON.stringify({ state: "pending", categories: null, remaining: [], applied: [] }))
    const out = runEngramUpdate({ target: tmp, mode: "cleanup" })
    expect(out).toContain("State cleaned")
    expect(existsSync(resolve(tmp, ".engram-update.jsonc"))).toBe(false)
  })

  it("checkpoint writes the manifest atomically (no .tmp left behind)", () => {
    runEngramUpdate({ target: tmp, mode: "checkpoint" })
    expect(existsSync(resolve(tmp, ".engram-update.jsonc"))).toBe(true)
    expect(existsSync(resolve(tmp, ".engram-update.jsonc.tmp"))).toBe(false)
    expect(JSON.parse(readFileSync(resolve(tmp, ".engram-update.jsonc"), "utf-8")).state).toBe("in_progress")
  })

  it("valid decisions still work end to end", () => {
    const out = runEngramUpdate({
      target: tmp,
      mode: "per_file",
      decisions: [{ file: "skills/learn.md", action: "keep" }],
    })
    expect(out).toContain("KEPT skills/learn.md")
    expect(existsSync(resolve(tmp, ".engram-update.jsonc"))).toBe(false)
  })
})
