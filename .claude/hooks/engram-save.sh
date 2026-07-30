#!/usr/bin/env bash
# Stop hook — persists the learning state.
#
# Without this, everything Engram records dies with the container. Runs at the end
# of every turn: commits and pushes the private engram-learning repo when it has
# changes, silent no-op when it doesn't.
#
# MUST NEVER BLOCK A TURN — every path ends in exit 0.
set -u

HOOK_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
# shellcheck source=engram-env.sh
. "$HOOK_DIR/engram-env.sh" 2>/dev/null || exit 0

# No state repo attached — session-start.sh already said so; don't nag every turn.
[ -n "$ENGRAM_STATE" ] || exit 0
[ -d "$ENGRAM_HOME" ] || exit 0

cd "$ENGRAM_STATE" 2>/dev/null || exit 0

# Nothing changed under learning/ → nothing to do.
if [ -z "$(git status --porcelain -- learning 2>/dev/null)" ]; then
  exit 0
fi

# Identity fallback: the remote environment normally sets this, but a missing
# identity would make the commit fail and silently lose the session's work.
git config user.name  >/dev/null 2>&1 || git config user.name  "Engram Cloud"
git config user.email >/dev/null 2>&1 || git config user.email "engram@localhost"

# A message that says what actually changed, read straight from the engine.
SUMMARY="$(ENGRAM_HOME="$ENGRAM_HOME" python3 "$ENGRAM_PROJECT/scripts/engram.py" doctor 2>/dev/null \
  | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print("%s Themen, %s Konzepte, %s Receipts" % (d.get("topics",0), d.get("nodes",0), d.get("receipts",0)))
except Exception:
    print("Lernstand aktualisiert")' 2>/dev/null)"
[ -n "$SUMMARY" ] || SUMMARY="Lernstand aktualisiert"

git add -A -- learning >/dev/null 2>&1
git commit -q -m "engram: $SUMMARY" >/dev/null 2>&1 || exit 0

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
[ -n "$BRANCH" ] && [ "$BRANCH" != "HEAD" ] || BRANCH=main

# Network flakiness is the expected failure here, so back off and retry.
for delay in 2 4 8 16 0; do
  if git push -u origin "$BRANCH" >/dev/null 2>&1; then
    exit 0
  fi
  [ "$delay" = "0" ] && break
  sleep "$delay"
done

echo "engram: Lernstand committet, aber der Push nach engram-learning ist fehlgeschlagen."
echo "engram: Bitte 'git -C $ENGRAM_STATE push -u origin $BRANCH' ausführen, sonst geht der Stand verloren."
exit 0
