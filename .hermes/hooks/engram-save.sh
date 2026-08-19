#!/usr/bin/env bash
# Speicher-Hook für Hermes Agent — registriert auf `post_llm_call`.
#
# `post_llm_call` feuert einmal pro Turn, nachdem die Tool-Schleife durch ist. Das
# ist das genaue Gegenstück zum Stop-Hook in Claude Code, und deshalb steht hier
# dieselbe Arbeit: Was Engram aufgezeichnet hat, wird committet und nach `main`
# gepusht. Ohne das läge der Lernstand nur auf dieser Platte — und die zweite
# Plattform (Claude Code on the web) sähe ihn nie.
#
# Bei sauberem Baum ein stiller No-Op. Jeder Pfad endet mit exit 0 und `{}` auf
# stdout; alle Meldungen gehen auf stderr. (In der Claude-Fassung gehen sie auf
# stdout — hier würde das als Hook-Antwort gelesen.)
set -u

say() { printf '%s\n' "$*" >&2; }
done_() { printf '{}\n'; exit 0; }

HOOK_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
# shellcheck source=engram-env.sh
. "$HOOK_DIR/engram-env.sh" 2>/dev/null || done_

# Kein State-Repo — session-start.sh hat das bereits laut gesagt; nicht in jedem
# Turn nachtreten.
[ -n "${ENGRAM_STATE:-}" ] || done_
[ -n "${ENGRAM_HOME:-}" ] && [ -d "$ENGRAM_HOME" ] || done_

# Was persistiert wird. sources/ trägt die aufbereiteten Quellen (Chunks, Index,
# Manifeste) — abgeleitete Daten, aber neu ableiten ließe sich das nur aus dem
# Original-PDF, und das liegt nicht zwangsläufig vor. Also wie Zustand behandelt.
#
# Als Liste gebaut und nicht fest verdrahtet, weil `git add -- sources` FATAL ist,
# wenn das Verzeichnis fehlt — dann würde gar nichts gestaged, learning/ inklusive.
PATHS="learning"
[ -d "$ENGRAM_STATE/sources" ] && PATHS="$PATHS sources"

# Nichts geändert → nichts zu tun. Der häufigste Fall, und der billigste.
if [ -z "$(git -C "$ENGRAM_STATE" status --porcelain -- $PATHS 2>/dev/null)" ]; then
  done_
fi

# Vor jedem Schreiben: Ist das Repo in der Verfassung dafür? Ein laufender Rebase
# heißt, dass gerade ein Mensch einen Konflikt auflöst.
if ! reason="$(engram_state_sync_ok)"; then
  say "engram: Lernstand NICHT gespeichert — $reason."
  say "engram: Die Änderungen liegen unversehrt im Arbeitsbaum von $ENGRAM_STATE."
  done_
fi

# Identität als Rückfallebene: fehlt sie, scheitert der Commit, und die Arbeit der
# Session wäre still verloren.
git -C "$ENGRAM_STATE" config user.name  >/dev/null 2>&1 || git -C "$ENGRAM_STATE" config user.name  "Engram Hermes"
git -C "$ENGRAM_STATE" config user.email >/dev/null 2>&1 || git -C "$ENGRAM_STATE" config user.email "engram@localhost"

# Eine Commit-Message, die sagt, was sich tatsächlich geändert hat — direkt aus der
# Engine gelesen, nicht geschätzt.
SUMMARY="$(ENGRAM_HOME="$ENGRAM_HOME" python3 "$ENGRAM_PROJECT/scripts/engram.py" doctor 2>/dev/null \
  | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print("%s Themen, %s Konzepte, %s Receipts" % (d.get("topics",0), d.get("nodes",0), d.get("receipts",0)))
except Exception:
    print("Lernstand aktualisiert")' 2>/dev/null)"
[ -n "$SUMMARY" ] || SUMMARY="Lernstand aktualisiert"

if [ -d "$ENGRAM_STATE/sources" ]; then
  N_SRC="$(find "$ENGRAM_STATE/sources" -mindepth 2 -maxdepth 2 -name source.json 2>/dev/null | wc -l | tr -d ' ')"
  [ "${N_SRC:-0}" -gt 0 ] && SUMMARY="$SUMMARY, $N_SRC Quellen"
fi

git -C "$ENGRAM_STATE" add -A -- $PATHS >/dev/null 2>&1
git -C "$ENGRAM_STATE" commit -q -m "engram (hermes): $SUMMARY" >/dev/null 2>&1 || done_

# --- Push ---------------------------------------------------------------------
# Ziel ist fest `main`: Beide Plattformen schreiben in denselben Branch, sonst sieht
# keine die Arbeit der anderen ohne einen Merge von Hand.
#
# Zwei Fehlerarten, und sie werden AUSEINANDERGEHALTEN statt gleich behandelt:
#
#   abgelehnt  — jemand (die andere Plattform) hat inzwischen gepusht. Sofort rebasen
#                und genau einmal neu versuchen. Blind zu warten hilft hier nie: Der
#                nächste Versuch wird aus demselben Grund abgelehnt. Schlimmer noch,
#                dieser Hook hat ein Zeitbudget (`timeout` in der Hook-Konfiguration) —
#                30 Sekunden Backoff vor dem Rebase brächten ihn genau im häufigsten
#                Fall in Gefahr, abgeschnitten zu werden.
#   sonst      — Netzwerkflattern. Dafür ist der Backoff da.
#
# Der Rebase wird bei Konflikt zurückgerollt, nie "gelöst": graphs/*.json trägt
# FSRS-State, den kein Skript zusammenführen kann.
push_once() {  # Ausgabe auf stdout, damit der Aufrufer sie prüfen kann
  git -C "$ENGRAM_STATE" push origin HEAD:main 2>&1
}
is_rejection() {
  printf '%s' "$1" | grep -qiE '\[rejected\]|non-fast-forward|fetch first|Updates were rejected|behind its remote'
}

# Genau einmal, egal über welchen Weg hierher gerufen wurde. Ein zweiter Anlauf würde
# denselben Konflikt erneut produzieren — und die Meldung dazu ein zweites Mal drucken,
# was wie zwei verschiedene Fehler aussieht.
REBASE_TRIED=0
rebase_and_retry() {
  [ "$REBASE_TRIED" = "1" ] && return 1
  REBASE_TRIED=1
  if git -C "$ENGRAM_STATE" pull --rebase --autostash origin main >/dev/null 2>&1; then
    push_once >/dev/null 2>&1 && return 0
    say "engram: Rebase auf origin/main hat geklappt, der Push danach nicht."
  else
    git -C "$ENGRAM_STATE" rebase --abort >/dev/null 2>&1 || true
    say "engram: Push abgelehnt und der Rebase auf origin/main hat Konflikte (zurückgerollt)."
    say "engram: Auflösung von Hand — learning/graphs/*.json: der NEUERE FSRS-Stand gewinnt;"
    say "engram: learning/receipts/*.jsonl: Vereinigung BEIDER Seiten, append-only, nichts löschen."
  fi
  return 1
}

for delay in 2 4 8 16 0; do
  if err="$(push_once)"; then
    done_
  fi
  # Ablehnung: warten ändert nichts, also gar nicht erst warten.
  if is_rejection "$err"; then
    rebase_and_retry && done_
    break
  fi
  [ "$delay" = "0" ] && break
  sleep "$delay"
done

# Netzwerkversuche erschöpft, ohne dass es je nach Ablehnung aussah — trotzdem einmal
# die Ablehnungs-Hypothese prüfen: Manche Git-Versionen und Remotes formulieren anders,
# als das Muster oben erwartet. Lief der Rebase in der Schleife schon, ist das hier ein
# stiller No-Op (REBASE_TRIED).
rebase_and_retry && done_

say "engram: Der Lernstand ist lokal committet, aber NICHT auf origin/main."
say "engram: Nachholen mit: git -C \"$ENGRAM_STATE\" push origin HEAD:main"
done_
