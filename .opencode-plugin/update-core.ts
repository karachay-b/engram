/**
 * Engram — Deterministic Update Engine (host-agnostic core)
 * ==========================================================
 *
 * The execute logic behind the `engram_update` custom tool, shared verbatim
 * by both OpenCode adapters:
 *
 *   V1 — update-tool.ts wraps it with @opencode-ai/plugin's `tool()` API.
 *   V2 — v2.ts registers it via ctx.tool.transform (plain JSON Schema input).
 *
 * This module deliberately imports NOTHING from @opencode-ai/* — the V2
 * adapter must stay loadable even when the host's plugin package version
 * drifts, and the V1 wrapper provides its own SDK surface.
 *
 * --- Modes ---
 *
 * auto        — Deletes ALL files in every category's skipped array, then deletes
 *               the manifest + version guard. One-shot, no checkpoint needed.
 *               Called from STEP 4a (Auto mode) in the template.
 *
 * per_file    — Receives a decisions array (per-file delete/keep choices collected
 *               by the model via question tool). Validates every file path against
 *               manifest.categories.*.skipped — paths not in the manifest are
 *               rejected. Deletes or keeps, removes from skipped, and saves
 *               checkpoint (saveManifest). When all categories are empty,
 *               deletes manifest + version guard.
 *               Called from STEP 4b (Manual mode) in the template.
 *
 * keep_as_is  — Deletes manifest + version guard without touching any user files.
 *               User edits preserved. Next start = fresh extract via selfExtract.
 *               Called from STEP 4d (Keep as-is) and STEP 5 cleanup.
 *
 * skip        — Read-only: returns current state without modifying anything.
 *               Called from STEP 4c and STEP 5 (to show status before resume).
 *
 * checkpoint  — Sets manifest.state = "in_progress" and persists.
 *               Called once at the start of STEP 4b (Manual mode).
 *
 * --- Validation ---
 *
 * Every file path in per_file decisions is checked:
 *   1. Category extracted from path prefix (e.g., "skills/learn.md" → "skills")
 *   2. Category must exist in manifest.categories
 *   3. File must be present in the category's skipped[] array
 *   → Rejected paths are reported but never cause a crash.
 *
 * All operations are synchronous — if the process dies mid-execution (crash,
 * power loss), the manifest persists and STEP 5 resumes. In auto mode, files
 * already deleted are simply not re-deleted (existsSync check is idempotent).
 */

import { existsSync, unlinkSync, writeFileSync, renameSync, lstatSync, realpathSync } from "node:fs"
import { resolve, sep, dirname } from "node:path"
import { readManifest, saveManifest } from "./update.js"

export type UpdateMode = "auto" | "per_file" | "keep_as_is" | "skip" | "checkpoint" | "cleanup"

export interface UpdateDecision {
  file: string
  action: "delete" | "keep"
}

export interface UpdateArgs {
  target: string
  mode: UpdateMode
  decisions?: UpdateDecision[]
}

/**
 * Guards against path traversal — rejects paths that resolve outside the
 * target directory. Uses os-specific separator (path.sep) instead of
 * hardcoded "/" so that resolve works correctly on Windows (\\ separators).
 *
 * Manifest category paths (POSIX-style with /) don't need this treatment —
 * they are JSON keys from .engram-update.jsonc, not filesystem paths.
 * Only paths resolved via resolve() are subject to the guard.
 */
function isWithinTarget(target: string, filePath: string): boolean {
  const targetDir = resolve(target) + sep
  const resolved = resolve(target, filePath)
  return resolved.startsWith(targetDir)
}

/**
 * Deletes a manifest-listed file, refusing symlinks and symlinked parents.
 * isWithinTarget above is LEXICAL — resolve() does not follow links — so a
 * category directory that is itself a symlink (the contributor-checkout
 * pattern install.ts describes) would route the unlink outside the target
 * and delete a file the manifest never described. Same rule as applyUpdate,
 * selfExtract's transform loop, and syncUpdateCommandV2: a linked path is
 * by definition not our extracted copy, so it is never ours to delete.
 * Returns true only when the file was actually unlinked.
 */
function safeUnlink(target: string, relFile: string): boolean {
  const filePath = resolve(target, relFile)
  try {
    if (lstatSync(filePath).isSymbolicLink()) return false
  } catch {
    return false // absent
  }
  try {
    const realParent = realpathSync(dirname(filePath))
    const realTarget = realpathSync(resolve(target))
    if (realParent !== realTarget && !realParent.startsWith(realTarget + sep)) return false
  } catch {
    return false
  }
  unlinkSync(filePath)
  return true
}

const MODES: readonly UpdateMode[] = ["auto", "per_file", "keep_as_is", "skip", "checkpoint", "cleanup"]

/**
 * Input arrives from the model. V1 has zod in front of this (update-tool.ts);
 * V2 hands the raw tool input straight through, and the V2 runtime may not
 * enforce the JSON Schema server-side — so the core validates for itself.
 * Malformed input must produce a message, never a throw, and never consume a
 * manifest entry (the v1.3.0 review found a missing `action` field marking a
 * file KEPT while silently draining it from skipped[]).
 */
function validateArgs(args: any): string | null {
  if (!args || typeof args !== "object") return "[engram] Invalid input: expected an object."
  if (typeof args.target !== "string" || !args.target) return "[engram] Invalid input: target must be a path string."
  if (!MODES.includes(args.mode)) return "[engram] Unknown mode."
  if (args.decisions !== undefined && !Array.isArray(args.decisions)) {
    return "[engram] Invalid input: decisions must be an array."
  }
  return null
}

/** True for a well-formed per-file decision; anything else is reported and skipped. */
function isValidDecision(d: any): d is UpdateDecision {
  return !!d && typeof d.file === "string" && (d.action === "delete" || d.action === "keep")
}

/** Structural check for a hand-editable manifest: every field the mode
 *  handlers dereference must have the type they assume. */
function isManifestShaped(m: any): boolean {
  if (!m || typeof m !== "object") return false
  if (!m.categories || typeof m.categories !== "object" || Array.isArray(m.categories)) return false
  for (const diff of Object.values(m.categories) as any[]) {
    if (!diff || typeof diff !== "object" || !Array.isArray((diff as any).skipped) || !Array.isArray((diff as any).added)) {
      return false
    }
  }
  if (!Array.isArray(m.remaining) || !Array.isArray(m.applied)) return false
  return true
}

export function runEngramUpdate(args: UpdateArgs): string {
  const invalid = validateArgs(args)
  if (invalid) return invalid
  const manifestPath = resolve(args.target, ".engram-update.jsonc")
  const versionPath = resolve(args.target, ".engram-version.jsonc")
  const diffPath = resolve(args.target, ".engram-update.diff")

  // cleanup is the template's STEP-2 recovery path for a manifest that
  // cannot be read — so it must run BEFORE any gate that requires reading
  // the manifest. v1.12.0's shape gate made corrupt-but-parseable state
  // unrecoverable: every mode returned "Corrupt manifest: run
  // /engram-update to clean up", which is the command the user had just
  // run. Caught by the post-release review (§7.5).
  if (args.mode === "cleanup") {
    if (existsSync(versionPath)) unlinkSync(versionPath)
    if (existsSync(manifestPath)) unlinkSync(manifestPath)
    if (existsSync(diffPath)) unlinkSync(diffPath)
    return "[engram] No pending updates. State cleaned. Restart to apply."
  }

  let manifest = readManifest(args.target)
  if (!manifest) {
    if (existsSync(manifestPath)) {
      return "[engram] Corrupt manifest: run /engram-update to clean up."
    }
    return "[engram] No pending update. Manifest not found."
  }
  // The manifest is hand-editable JSON: valid JSON with the wrong SHAPE must
  // degrade to the corrupt-manifest message, never throw out of a tool call
  // (the v1.3.0 review put 14 of 19 hostile shapes through the old code).
  if (!isManifestShaped(manifest)) {
    return "[engram] Corrupt manifest: run /engram-update to clean up."
  }

  switch (args.mode) {
    case "auto": {
      let deleted = 0
      for (const diff of Object.values(manifest.categories)) {
        for (const file of diff.skipped) {
          if (!isWithinTarget(args.target, file)) continue
          if (safeUnlink(args.target, file)) deleted++
        }
      }
      if (existsSync(versionPath)) unlinkSync(versionPath)
      unlinkSync(manifestPath)
      if (existsSync(diffPath)) unlinkSync(diffPath)
      return `[engram] Auto update applied. ${deleted} files deleted. Restart OpenCode or reload plugins.`
    }

    case "per_file": {
      if (!args.decisions || !args.decisions.length) {
        return "[engram] decisions array required for per_file mode."
      }

      const results: string[] = []
      let anyDeleted = false
      for (const d of args.decisions) {
        // Invalid decisions are reported and MUST NOT fall through to the
        // skipped[] filter below — consuming the entry would tell the user
        // the file was handled when it was neither refreshed nor kept.
        if (!isValidDecision(d)) {
          results.push(`SKIP ${JSON.stringify(d)}: malformed decision (need {file, action: delete|keep})`)
          continue
        }
        if (!isWithinTarget(args.target, d.file)) {
          results.push(`SKIP ${d.file}: path outside target`)
          continue
        }
        const category = d.file.split("/")[0]
        const cat = manifest.categories[category]
        if (!cat || !cat.skipped.includes(d.file)) {
          results.push(`SKIP ${d.file}: not in manifest skipped list`)
          continue
        }

        if (d.action === "delete") {
          const filePath = resolve(args.target, d.file)
          if (!existsSync(filePath)) {
            results.push(`SKIP ${d.file}: already deleted`)
          } else if (safeUnlink(args.target, d.file)) {
            results.push(`DELETED ${d.file}`)
            anyDeleted = true
          } else {
            results.push(`SKIP ${d.file}: symlinked — not ours to delete`)
          }
        } else {
          results.push(`KEPT ${d.file}`)
        }

        cat.skipped = cat.skipped.filter((f: string) => f !== d.file)
      }

      for (const [name, diff] of Object.entries(manifest.categories)) {
        if (diff.skipped.length === 0) {
          const idx = manifest.remaining.indexOf(name)
          if (idx > -1) {
            manifest.remaining.splice(idx, 1)
            if (!manifest.applied.includes(name)) {
              manifest.applied.push(name)
            }
          }
        }
      }

      if (manifest.remaining.length === 0) {
        if (existsSync(versionPath)) unlinkSync(versionPath)
        unlinkSync(manifestPath)
        if (existsSync(diffPath)) unlinkSync(diffPath)
        return `[engram] All files processed.\n${results.join("\n")}\n\nRestart OpenCode or reload plugins.`
      }

      // A checkpoint that deleted files must ALSO drop the version guard:
      // selfExtract early-returns while it matches, so the deletions would
      // otherwise persist across restarts until the update completes — for
      // gold/ and experiments/ that is a silently degraded engine (the gold
      // audit runs against an empty set and exits 0), issue #20's exact
      // symptom re-entered through the update flow. With the guard gone the
      // next session re-extracts: deleted files return as the NEW version,
      // preserved files are untouched (copyMissing never overwrites), and
      // the manifest — written only on a version bump, which a guardless
      // extract is not — survives for the remaining decisions.
      if (anyDeleted && existsSync(versionPath)) unlinkSync(versionPath)

      saveManifest(args.target, manifest)
      return `[engram] Checkpoint saved.\n${results.join("\n")}\n\nRemaining: ${manifest.remaining.join(", ")}. Continue with /engram-update.`
    }

    case "keep_as_is": {
      if (existsSync(versionPath)) unlinkSync(versionPath)
      if (existsSync(manifestPath)) unlinkSync(manifestPath)
      if (existsSync(diffPath)) unlinkSync(diffPath)
      return "[engram] Update skipped permanently. Restart for fresh extract."
    }

    case "skip": {
      return `[engram] Update deferred. State: ${manifest.state}. ${manifest.remaining.length} categories remaining.`
    }

    case "checkpoint": {
      manifest.state = "in_progress"
      writeFileSync(manifestPath + ".tmp", JSON.stringify(manifest, null, 2))
      renameSync(manifestPath + ".tmp", manifestPath)
      return `[engram] State set to in_progress. ${manifest.remaining.length} categories pending.`
    }


    default:
      return "[engram] Unknown mode."
  }
}
