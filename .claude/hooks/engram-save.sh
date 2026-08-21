#!/usr/bin/env bash
# Speicher-Hook für Claude Code — registriert als Stop-Hook.
#
# Committet und pusht den Lernstand nach jedem Turn. Ohne das überlebt Engram den
# Container nicht — Container in dieser Umgebung sind kurzlebig.
#
# Seit dem Umzug der Lernarbeit nach Hermes (CLAUDE.md, Abschnitt „Zweite
# Plattform: Hermes Agent") ist dieser Hook nicht mehr der Hauptschreiber,
# sondern der Rückfallweg: Entsteht doch einmal Lernstand in einer
# Claude-Session, wäre stilles Nichtspeichern das schlechteste Ergebnis. Push-Ziel
# ist deshalb fest `main`, wie bei der Hermes-Fassung (.hermes/hooks/engram-save.sh)
# — nicht mehr der aktuelle Branch (in Web-Sessions `claude/…`), der für Hermes
# unsichtbar wäre und nach einem PR-Merge mit dessen Stand kollidieren könnte.
#
# MUSS NIE EINEN TURN BLOCKIEREN — jeder Pfad endet mit exit 0.
set -u

HOOK_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
# shellcheck source=engram-env.sh
. "$HOOK_DIR/engram-env.sh" 2>/dev/null || exit 0

# Kein State-Repo angehängt — session-start.sh hat das bereits gemeldet; nicht in
# jedem Turn nachtreten.
[ -n "$ENGRAM_STATE" ] || exit 0
[ -d "$ENGRAM_HOME" ] || exit 0

cd "$ENGRAM_STATE" 2>/dev/null || exit 0

# Was persistiert wird. sources/ trägt die aufbereiteten Quellen (Chunks, Index,
# Manifeste) — abgeleitete Daten, aber neu ableiten ginge nur aus dem
# Original-PDF, und das ist gitignored und stirbt mit dem Container. Also wie
# Zustand behandelt.
#
# Als Liste gebaut und nicht fest verdrahtet, weil `git add -- sources` FATAL ist,
# wenn das Verzeichnis fehlt — dann würde gar nichts gestaged, learning/
# inklusive. Ein Repo, das noch nie eine Quelle ingestet hat, muss trotzdem
# weiter seinen Lernstand speichern können.
PATHS="learning"
[ -d "$ENGRAM_STATE/sources" ] && PATHS="$PATHS sources"

# Nichts geändert → nichts zu tun.
if [ -z "$(git status --porcelain -- $PATHS 2>/dev/null)" ]; then
  exit 0
fi

# Zwei Dinge dürfen den Commit verhindern: ein laufender Rebase/Merge (dieser
# Guard) und eine erkannte Löschung (weiter unten, eigener Guard). Sonst nichts
# — der Normalfall ist, dass die Engine nur ändert oder ergänzt.
#
# Rebase/Merge zuerst: Dann löst gerade ein Mensch einen Konflikt auf, und ein
# `git commit` mitten hinein zerstört die halbfertige Auflösung.
#
# Bewusst NICHT übernommen aus der Hermes-Fassung: deren Prüfung auf
# `branch == main`. Dort ist sie richtig — auf dem Desktop kontrolliert der Nutzer
# das Checkout, und ein Nebenbranch hat einen Grund, den der Hook nicht kennt.
# HIER wäre sie ein Datenverlust-Automat: In Claude Code on the web vergibt die
# UMGEBUNG den Branchnamen des State-Repos (sie spiegelt den Namen des
# Code-Branches, z. B. `claude/…`). Der Name trägt also keine Absicht des
# Nutzers — die Prüfung würde schlicht immer verweigern, und zwar VOR dem Commit.
# Gemessen am 2026-08-20: Genau so gebaut, ließ der Hook den Lernstand
# uncommittet im Arbeitsbaum liegen und meldete dabei „liegt unversehrt" — in
# einem kurzlebigen Container heißt das „ist beim nächsten Ablauf weg".
#
# Der Branchname wird für die Korrektheit auch nicht gebraucht: Gepusht wird
# ohnehin fest nach `HEAD:main` (siehe unten), unabhängig davon, wie der lokale
# Branch heißt.
#
# Ein fehlender Remote blockiert den Commit ebenfalls nicht — er ist ein
# Push-Problem und wird dort behandelt. Ein Commit ohne Push ist wenig wert,
# aber immer noch mehr als eine ungespeicherte Änderung.
_gd="$(git rev-parse --git-dir 2>/dev/null)"
if [ -n "$_gd" ]; then
  case "$_gd" in /*) ;; *) _gd="$ENGRAM_STATE/$_gd" ;; esac
  if [ -d "$_gd/rebase-merge" ] || [ -d "$_gd/rebase-apply" ] || [ -f "$_gd/MERGE_HEAD" ]; then
    echo "engram: Lernstand NICHT committet — im State-Repo läuft ein Rebase/Merge."
    echo "engram: Erst die Konfliktauflösung in $ENGRAM_STATE abschließen, dann speichert der nächste Turn."
    exit 0
  fi
fi

# Identität als Rückfallebene: fehlt sie, scheitert der Commit, und die Arbeit
# der Session wäre still verloren.
git config user.name  >/dev/null 2>&1 || git config user.name  "Engram Cloud"
git config user.email >/dev/null 2>&1 || git config user.email "engram@localhost"

# Eine Commit-Message, die sagt, was sich tatsächlich geändert hat — direkt aus
# der Engine gelesen, nicht geschätzt.
SUMMARY="$(ENGRAM_HOME="$ENGRAM_HOME" python3 "$ENGRAM_PROJECT/scripts/engram.py" doctor 2>/dev/null \
  | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print("%s Themen, %s Konzepte, %s Receipts" % (d.get("topics",0), d.get("nodes",0), d.get("receipts",0)))
except Exception:
    print("Lernstand aktualisiert")' 2>/dev/null)"
[ -n "$SUMMARY" ] || SUMMARY="Lernstand aktualisiert"

# Quellen nur zählen, nicht interpretieren — ein Verzeichnis mit source.json ist eine.
if [ -d "$ENGRAM_STATE/sources" ]; then
  N_SRC="$(find "$ENGRAM_STATE/sources" -mindepth 2 -maxdepth 2 -name source.json 2>/dev/null | wc -l | tr -d ' ')"
  [ "${N_SRC:-0}" -gt 0 ] && SUMMARY="$SUMMARY, $N_SRC Quellen"
fi

# Löschungs-Wächter. Vorfall 2026-08-20 (Commit 88954cd): eine lokale Löschung
# unbekannter Ursache wurde vom routinemäßigen Sichern kommentarlos nach
# origin/main gepusht — stiller Datenverlust. Ein Fund hier heißt NICHT
# committen, sondern die Pfade laut auflisten und auf manuelle Prüfung
# verweisen; der Normalfall (Engine ändert/ergänzt nur) bleibt unberührt, weil
# `D` in der Statusspalte nur bei einer echten Löschung auftaucht. Läuft nach
# dem Rebase/Merge-Guard und vor `git add -A`, damit die Löschung noch
# ungestaged ist, wenn sie gemeldet wird.
DELETED="$(git status --porcelain -- $PATHS 2>/dev/null | grep -E '^.D|^D.' || true)"
if [ -n "$DELETED" ]; then
  echo "engram: Lernstand NICHT committet — gelöschte Pfade erkannt:"
  echo "$DELETED"
  echo "engram: Absichtlich? Von Hand committen und pushen. Sonst: git -C \"$ENGRAM_STATE\" checkout -- <Pfad>."
  exit 0
fi

git add -A -- $PATHS >/dev/null 2>&1
git commit -q -m "engram: $SUMMARY" >/dev/null 2>&1 || exit 0

# --- Push ---------------------------------------------------------------------
# Ziel ist fest `main` (nicht mehr der aktuelle Branch): Seit dem Umzug der
# Lernarbeit nach Hermes ist diese Session nur noch der Rückfallweg, falls doch
# einmal in einer Claude-Session Lernstand entsteht — und der muss dort landen,
# wo Hermes ihn sieht, nicht auf einem `claude/…`-Branch, den niemand mergt.
#
# Zwei Fehlerarten, auseinandergehalten wie in der Hermes-Fassung:
#   abgelehnt — jemand (Hermes) hat inzwischen gepusht. Sofort rebasen und genau
#               einmal neu versuchen. Blind warten hilft hier nie: Der nächste
#               Versuch wird aus demselben Grund abgelehnt.
#   sonst     — Netzwerkflattern. Dafür ist der Backoff da.
#
# Der Rebase wird bei Konflikt zurückgerollt, nie "gelöst": graphs/*.json trägt
# FSRS-State, den kein Skript zusammenführen kann.
push_once() {
  git push origin HEAD:main 2>&1
}
is_rejection() {
  printf '%s' "$1" | grep -qiE '\[rejected\]|non-fast-forward|fetch first|Updates were rejected|behind its remote'
}

REBASE_TRIED=0
rebase_and_retry() {
  [ "$REBASE_TRIED" = "1" ] && return 1
  REBASE_TRIED=1
  if git pull --rebase --autostash origin main >/dev/null 2>&1; then
    push_once >/dev/null 2>&1 && return 0
    echo "engram: Rebase auf origin/main hat geklappt, der Push danach nicht."
  else
    git rebase --abort >/dev/null 2>&1 || true
    echo "engram: Push abgelehnt und der Rebase auf origin/main hat Konflikte (zurückgerollt)."
    echo "engram: Auflösung von Hand — learning/graphs/*.json: der NEUERE FSRS-Stand gewinnt;"
    echo "engram: learning/receipts/*.jsonl: Vereinigung BEIDER Seiten, append-only, nichts löschen."
  fi
  return 1
}

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "engram: Lernstand committet, aber es gibt keinen Remote 'origin' — nichts zu pushen."
  exit 0
fi

for delay in 2 4 8 16 0; do
  if err="$(push_once)"; then
    exit 0
  fi
  # Ablehnung: warten ändert nichts, also gar nicht erst warten.
  if is_rejection "$err"; then
    rebase_and_retry && exit 0
    break
  fi
  [ "$delay" = "0" ] && break
  sleep "$delay"
done

# Netzwerkversuche erschöpft, ohne dass es je nach Ablehnung aussah — trotzdem
# einmal die Ablehnungs-Hypothese prüfen: Manche Git-Versionen und Remotes
# formulieren anders, als das Muster oben erwartet. Lief der Rebase in der
# Schleife schon, ist das hier ein stiller No-Op (REBASE_TRIED).
rebase_and_retry && exit 0

echo "engram: Lernstand committet, aber NICHT auf origin/main."
echo "engram: Nachholen mit: git -C \"$ENGRAM_STATE\" push origin HEAD:main"
exit 0
