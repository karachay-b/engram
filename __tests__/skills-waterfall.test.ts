import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

/**
 * The engine-resolution waterfall is duplicated verbatim across the three
 * skill files (each must be self-sufficient — a platform may load one skill
 * in isolation). Duplication means drift risk: a platform candidate added to
 * one copy and not the others strands that platform's users in whichever
 * skill was missed. These checks pin (a) the copies to each other and (b)
 * the candidates each shipped platform depends on.
 */

const SKILLS = ["learn", "review", "coach"] as const
const root = resolve(__dirname, "..")

/** Every file carrying a waterfall copy — DISCOVERED, not enumerated. The
 *  v1.13.0 release hardcoded the three skills here and missed the fourth
 *  copy in agents/engram-artifact-smith.md; §7.5 proved that copy strands a
 *  dsh-only machine on the visuals path. Discovery keeps platform nine from
 *  repeating this. */
function waterfallFiles(): string[] {
  const { execSync } = require("node:child_process")
  const out = execSync('grep -rl \'for d in "$OPENCODE_PLUGIN_ROOT"\' skills agents', { cwd: root, encoding: "utf-8" })
  const files = out.trim().split("\n").filter(Boolean)
  expect(files.length).toBeGreaterThanOrEqual(4)
  return files
}

function waterfallBlockAt(relPath: string): string {
  const content = readFileSync(resolve(root, relPath), "utf-8")
  const start = content.indexOf('for d in "$OPENCODE_PLUGIN_ROOT"')
  const end = content.indexOf("; do", start)
  expect(start, `${relPath}: candidate list missing`).toBeGreaterThan(-1)
  return content.slice(start, end)
}

function waterfallBlock(skill: string): string {
  const content = readFileSync(resolve(root, "skills", skill, "SKILL.md"), "utf-8")
  const start = content.indexOf("# Resolve the engine. RUN THIS BLOCK VERBATIM")
  const end = content.indexOf("```", start)
  expect(start, `${skill}: waterfall block missing`).toBeGreaterThan(-1)
  expect(end, `${skill}: waterfall block unterminated`).toBeGreaterThan(start)
  return content.slice(start, end)
}

/** The candidate list itself — `for d in … ; do` — is the drift-sensitive
 *  part. Comments and the commands that follow legitimately vary per skill. */
function candidateList(skill: string): string {
  const block = waterfallBlock(skill)
  const start = block.indexOf("for d in ")
  const end = block.indexOf("; do", start)
  expect(start, `${skill}: candidate list missing`).toBeGreaterThan(-1)
  expect(end, `${skill}: candidate list unterminated`).toBeGreaterThan(start)
  return block.slice(start, end)
}

describe("engine-resolution waterfall", () => {
  it("has an identical candidate list across all three skills", () => {
    const [learn, review, coach] = SKILLS.map(candidateList)
    expect(review).toBe(learn)
    expect(coach).toBe(learn)
  })

  it("carries every shipped platform's candidate — in EVERY discovered copy", () => {
    for (const file of waterfallFiles()) {
    const block = waterfallBlockAt(file)
    for (const candidate of [
      '"$OPENCODE_PLUGIN_ROOT"',
      '"$CLAUDE_PLUGIN_ROOT"',
      '"$CODEX_PLUGIN_ROOT"',
      '"$ENGRAM_ROOT"',
      '"${OPENCLAW_STATE_DIR:-$HOME/.openclaw}/extensions/engram"',
      '"$HOME/.gemini/config/plugins/engram"',
      '"$HOME/.pi/agent/git/github.com/nagisanzenin/engram"',
      '"$HOME/.agents/engram"',
    ]) {
      expect(block, `${file}: missing candidate ${candidate}`).toContain(candidate)
    }
    }
  })

  it("fails closed when no candidate resolves — in every skill", () => {
    for (const skill of SKILLS) {
      expect(waterfallBlock(skill), `${skill}: fail-closed guard missing`).toContain("FAIL CLOSED")
    }
  })

  it("keeps the working tree ahead of the shared-home clone (a contributor's checkout must win)", () => {
    const list = candidateList("learn")
    expect(list.indexOf('"$PWD"')).toBeGreaterThan(-1)
    expect(list.indexOf('"$HOME/.agents/engram"')).toBeGreaterThan(list.indexOf('"$PWD"'))
  })
})
