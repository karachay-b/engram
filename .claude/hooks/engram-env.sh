#!/usr/bin/env bash
# Shared resolver for the cloud setup: finds the Engram checkout and the private
# state repo. Sourced by session-start.sh and engram-save.sh — never run directly.
#
# Sets, when it can:
#   ENGRAM_PROJECT  absolute path of this engram checkout
#   ENGRAM_STATE    absolute path of the engram-learning checkout (state repo)
#   ENGRAM_HOME     $ENGRAM_STATE/learning  — what engram.py reads
#
# Leaves ENGRAM_STATE empty when the state repo isn't attached to the session.
# Callers must handle that: learning state then lives in the container only and
# dies with it.

# --- the engram checkout ------------------------------------------------------
ENGRAM_PROJECT="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$ENGRAM_PROJECT" ] || [ ! -f "$ENGRAM_PROJECT/scripts/engram.py" ]; then
  ENGRAM_PROJECT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/../.." 2>/dev/null && pwd)"
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

if [ -n "$ENGRAM_STATE" ]; then
  ENGRAM_HOME="$ENGRAM_STATE/learning"
fi
