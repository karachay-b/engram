#!/usr/bin/env bash
# Gesundheitsprüfung des State-Repos — als Wochen-Cron mit `--deliver telegram`
# gedacht (siehe .hermes/UEBERGABE-HERMES.md, Schritt 6 „Gateway/Cron einrichten").
#
# Mit Hermes als einzigem Schreiber auf einem Laptop ist ein still fehlgeschlagener
# Push der Weg, auf dem Wochen Arbeit verschwinden. engram-save.sh meldet einen
# gescheiterten Push zwar auf stderr, aber ob das in der Desktop-App überhaupt
# sichtbar wird, ist offen — dieser Hook ist die zweite, unabhängige Meldeleitung.
#
# Bewusst klein gehalten: nur `git status --porcelain` (uncommittete Änderungen)
# und `git rev-list --count origin/main..HEAD` (lokale Commits, die noch nicht
# gepusht sind). Kein `git fetch` — der zuletzt bekannte Stand von origin/main
# reicht (beide Save-Hooks halten ihn ohnehin frisch), und ein zusätzlicher
# Netzwerkaufruf ist hier nicht der Auftrag.
#
# Bei allem in Ordnung: keine Ausgabe, exit 0. Läuft nie im Hook-Modus
# (pre_llm_call/post_llm_call) und braucht deshalb kein JSON — nur als
# eigenständiger Cron-Job im Klartext-Modus wie session-start.sh ihn kennt.
set -u

HOOK_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
# shellcheck source=engram-env.sh
. "$HOOK_DIR/engram-env.sh" 2>/dev/null || exit 0

[ -n "${ENGRAM_STATE:-}" ] || { echo "engram: Gesundheitscheck — kein State-Repo gefunden."; exit 0; }
# `-e` statt `-d`: in einem Git-Worktree ist `.git` eine Datei, keine
# Verzeichnis — `resolve_state()` akzeptiert Worktrees ausdrücklich, dieser
# Check soll sie nicht stillschweigend ausschließen.
[ -e "$ENGRAM_STATE/.git" ] || exit 0

STATUS="$(git -C "$ENGRAM_STATE" status --porcelain 2>/dev/null)"
AHEAD="$(git -C "$ENGRAM_STATE" rev-list --count origin/main..HEAD 2>/dev/null || echo 0)"

if [ -n "$STATUS" ] || [ "${AHEAD:-0}" -gt 0 ]; then
  echo "engram: Gesundheitscheck — $ENGRAM_STATE weicht von origin/main ab (uncommittete Änderungen: $([ -n "$STATUS" ] && echo ja || echo nein), $AHEAD Commit(s) nicht gepusht). Prüfen: git -C \"$ENGRAM_STATE\" status"
fi

exit 0
