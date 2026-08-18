/**
 * Engram — /engram-update Command Template (shared constants)
 * ============================================================
 *
 * The pseudo-command presented to the model while an update manifest exists.
 * Shared by both OpenCode adapters so the procedure can never drift between
 * V1 and V2:
 *
 *   V1 — index.ts registers it in-memory via cfg.command["engram-update"].
 *   V2 — v2.ts registers it for the V2 command surface.
 *
 * $TARGET is a placeholder replaced at registration time with the resolved
 * extraction target ({cwd}/.opencode/ or ~/.config/opencode/), so the model
 * always reads/writes the correct directory. No other interpolation happens.
 */

export const UPDATE_DESCRIPTION =
  "Review and apply pending Engram plugin updates — auto (all) or manual (per file)"

export const UPDATE_TEMPLATE = `# /engram-update — apply Engram plugin updates

## Procedure — execute in order; do NOT skip, reorder, or merge steps

### STEP 1 — Read manifest
Tool: Read
Path: $TARGET/.engram-update.jsonc

The Engram system consists of:
  AGENTS.md         — model behavioral rules (project root or global)
  skills/            — skill definitions (learn, review, coach)
  agents/            — subagent definitions (curriculum-architect, engram-assessor, artifact-smith)
  scripts/           — deterministic engine (engram.py)
  commands/          — command templates (learn, review-loop, coach)
  gold/              — bundled assessor ground truth (gold audit)
  experiments/       — pre-registered experiment presets
  docs/              — foundations the skills cite

Parse the JSON. Locate field: state.

### STEP 2 — If Read fails
Condition: file not found OR JSON.parse fails.
Then execute:
  Call tool: engram_update({ target: "$TARGET", mode: "cleanup" })
Output the tool's return message. Do NOT modify or paraphrase it.
STOP. Do not continue.

### STEP 3 — Route by manifest.state
  "pending"      → go to STEP 4.
  "in_progress"  → go to STEP 5.
  any other      → treat as corrupt → go to STEP 2.

### STEP 4 — State "pending": present choices
Output: "Engram {manifest.from} → {manifest.to}"
For each category in manifest.categories with a non-empty skipped array, output:
  "{name}: {skipped.length} preserved files differ from the shipped version"
Use the question tool:
  header: "Engram Update"
  question: "How to apply Engram {manifest.from} → {manifest.to}?"
  options:
    - "Auto (Recommended)" — refresh ALL preserved files
    - "Manual" — pick per file
    - "View changes" — inspect diff before deciding
    - "Skip" — defer, remind next session
    - "Keep as-is" — skip permanently
Route by selected option:
  "Auto" → STEP 4a
  "Manual" → STEP 4b
  "View changes" → STEP 4e
  "Skip" → STEP 4c
  "Keep as-is" → STEP 4d

### STEP 4a — Auto mode
Call tool: engram_update({ target: "$TARGET", mode: "auto" })
Output the tool's return message. Do NOT modify or paraphrase it.
STOP.

### STEP 4b — Manual mode (per-file)
Call tool: engram_update({ target: "$TARGET", mode: "checkpoint" })
For each category name in manifest.remaining, in order:
  For each file in manifest.categories.{name}.skipped:
    Use the question tool:
      header: "{name}"
      question: "Overwrite {file}?"
      options:
        - "Yes" — delete and refresh on next restart
        - "No" — keep current version
    Track the decision: { file: "{file}", action: "delete" or "keep" }
After ALL files in all remaining categories have been answered:
  Call tool: engram_update({ target: "$TARGET", mode: "per_file", decisions: [ALL_TRACKED_DECISIONS] })
  Output the tool's return message. Do NOT modify or paraphrase it.
  If the message says all files processed → "Manual update complete. Restart or reload."
  If the message says checkpoint saved → "Checkpoint saved. Continue with /engram-update on next session."
STOP.

### STEP 4c — Skip
Call tool: engram_update({ target: "$TARGET", mode: "skip" })
Output: "Update deferred. You'll be reminded next session."
STOP.

### STEP 4d — Keep as-is
Call tool: engram_update({ target: "$TARGET", mode: "keep_as_is" })
Output the tool's return message. Do NOT modify or paraphrase it.
STOP.

### STEP 4e — View changes
// Edge case: .engram-update.diff may not exist even when the manifest
// does — contentsMatch flags CRLF-only byte differences but diffLines
// normalizes them away. The Read guard below handles this gracefully.
Use Read tool: $TARGET/.engram-update.diff
If Read tool fails (file does not exist): say "No diff available — files may differ only in line endings. Proceed with the update options." Then go back to STEP 4.
Otherwise: summarize the changes to the user (which files changed and what the diffs show).
Then go back to STEP 4 and present the options again.

### STEP 5 — State "in_progress": resume
Output: "Resuming update — checkpoint found."
Call tool: engram_update({ target: "$TARGET", mode: "skip" })
This returns current state. Proceed with STEP 4b using only files still present in manifest.categories.{name}.skipped arrays.
If all skipped arrays are empty:
  Call tool: engram_update({ target: "$TARGET", mode: "keep_as_is" })
STOP.

## Constraints — MUST follow
- Use Read tool for the manifest. NEVER use Glob.
- Do NOT use Bash for file deletion or manifest updates. Use the engram_update tool instead.
- Do NOT delete AGENTS.md or scripts/engram.py directly.
- Do NOT add, modify, or rename any file.
- If a category.skipped array is empty, skip that category silently.
- Do NOT output text beyond what each step prescribes.`
