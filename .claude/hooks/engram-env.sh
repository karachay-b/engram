#!/usr/bin/env bash
# Shared resolver for the cloud setup: finds the Engram checkout and the private
# state repo. Sourced by session-start.sh and engram-save.sh — never run directly.
#
# Sets, when it can:
#   ENGRAM_PROJECT  absolute path of this engram checkout
#   ENGRAM_ROOT     same path, exported — upstream's own escape hatch
#   ENGRAM_STATE    absolute path of the engram-learning checkout (state repo)
#   ENGRAM_HOME     $ENGRAM_STATE/learning  — what engram.py reads
#
# Leaves ENGRAM_STATE empty when the state repo isn't attached to the session.
# Callers must handle that: learning state then lives in the container only and
# dies with it.

# --- the engram checkout ------------------------------------------------------
# First hit wins. Neither of the two signals this used to rely on is dependable:
# $CLAUDE_PROJECT_DIR never reaches the Bash tool's environment, and `git rev-parse`
# returns nothing when the session's working directory is the parent of both
# checkouts (/home/user) rather than the repo itself. BASH_SOURCE stays high in the
# list because it is exact whenever this file is sourced by path; the fixed paths at
# the end are the backstop for that parent-directory case — same precedent as
# resolve_state() in engram_source.py, which hardcodes /home/user/engram-learning
# for the state repo. (Named, not numbered: a line number here goes stale the
# first time that file grows, and silently.)
ENGRAM_PROJECT=""
for _p in "${ENGRAM_ROOT:-}" \
          "${CLAUDE_PROJECT_DIR:-}" \
          "$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/../.." 2>/dev/null && pwd)" \
          "$PWD" \
          "$(git rev-parse --show-toplevel 2>/dev/null)" \
          "/home/user/engram" \
          "$HOME/engram"; do
  [ -n "$_p" ] || continue
  if [ -f "$_p/scripts/engram.py" ]; then
    ENGRAM_PROJECT="$(CDPATH= cd -- "$_p" 2>/dev/null && pwd)"
    break
  fi
done
unset _p

# Upstream's resolver (skills/learn/SKILL.md) checks $ENGRAM_ROOT as its fourth
# candidate and, on failure, tells the reader to set exactly this variable. Exporting
# it here makes the unmodified upstream block resolve on its first real hit — no edit
# to skills/, so `git merge upstream/main` stays conflict-free.
#
# On failure the inherited values must be CLEARED, not left standing. An
# ENGRAM_ROOT or ENGRAM_HOME carried in from the environment would otherwise
# survive a failed resolution and point the engine at a checkout this session
# never validated — and engram.py writes learning state to wherever ENGRAM_HOME
# says. Failing to resolve must look like "no engram here", not like a stale hit.
if [ -n "$ENGRAM_PROJECT" ]; then
  ENGRAM_ROOT="$ENGRAM_PROJECT"
  export ENGRAM_ROOT ENGRAM_PROJECT
else
  unset ENGRAM_ROOT ENGRAM_HOME 2>/dev/null || true
fi

# --- the state repo -----------------------------------------------------------
# First hit wins. ENGRAM_STATE_REPO is the escape hatch for a non-standard clone.
ENGRAM_STATE=""
for _c in "${ENGRAM_STATE_REPO:-}" \
          "$ENGRAM_PROJECT/../engram-learning" \
          "/home/user/engram-learning" \
          "$HOME/engram-learning"; do
  [ -n "$_c" ] || continue
  if [ -d "$_c/.git" ]; then
    ENGRAM_STATE="$(CDPATH= cd -- "$_c" 2>/dev/null && pwd)"
    break
  fi
done
unset _c

# Same rule as above: no state repo means no ENGRAM_HOME. Leaving an inherited
# one in place would send the engine's writes to a checkout that is not the one
# this resolution found — silently, and with the learner's data.
if [ -n "$ENGRAM_STATE" ]; then
  ENGRAM_HOME="$ENGRAM_STATE/learning"
  export ENGRAM_STATE ENGRAM_HOME
else
  unset ENGRAM_HOME 2>/dev/null || true
fi
