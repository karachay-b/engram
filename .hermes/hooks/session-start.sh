#!/usr/bin/env bash
# Sessionstart-Hook für Hermes Agent — registriert auf `pre_llm_call`.
#
# Tut in einer Session genau einmal, was der SessionStart-Hook in Claude Code bei
# jedem Start tut:
#   1. den Lernstand vom Remote nachziehen (pull --rebase), damit Hermes nicht auf
#      einem Stand ohne die Claude-Web-Sessions weiterarbeitet
#   2. das Briefing .claude/ORIENTIERUNG.md ausgeben, plus die Hermes-Abweichungen
#   3. `engram.py init` (idempotent) und den Due-Nudge
#   4. den täglichen Upstream-Sync-Check
#   5. das Interessen-Gate
#   6. den Marker setzen, an dem die Skills erkennen, dass die Hooks laufen
#
# Zwei Modi, automatisch erkannt — übernommen aus hooks/session-start-hermes.sh
# (Upstream), damit beide Hooks sich gleich verhalten:
#   Hook-Modus (stdin trägt Hermes' JSON): {"context": "<text>"} beim ersten Aufruf
#     der Session, {} bei jedem weiteren.
#   Klartext-Modus (stdin leer, z.B. `hermes cron create --no-agent --script …`):
#     der Text roh auf stdout, ohne Dedupe.
#
# Vertrag (wie upstream): ambient, nie nörgelnd — höchstens ein Nudge pro Session,
# und bei JEDEM Fehler Verstummen statt Wiederholung. Jeder Pfad endet mit exit 0.
set -u

emit_json() {  # $1 = Kontexttext (leer → {})
  if [ -z "${1:-}" ]; then printf '{}\n'; return 0; fi
  printf '%s' "$1" | python3 -c 'import sys,json; print(json.dumps({"context": sys.stdin.read().strip()}))' 2>/dev/null \
    || printf '{}\n'
}

command -v python3 >/dev/null 2>&1 || { printf '{}\n'; exit 0; }

payload="$(cat - 2>/dev/null || true)"

HOOK_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
# shellcheck source=engram-env.sh
. "$HOOK_DIR/engram-env.sh" 2>/dev/null || { [ -n "$payload" ] && printf '{}\n'; exit 0; }

if [ -z "${ENGRAM_PROJECT:-}" ] || [ ! -f "$ENGRAM_PROJECT/scripts/engram.py" ]; then
  [ -n "$payload" ] && printf '{}\n'
  exit 0
fi

# --- Dedupe zuerst ------------------------------------------------------------
# Vor der Arbeit, nicht danach: Der teure Teil (pull, init, Nudge, Sync-Check) soll
# in einer Session genau einmal laufen, nicht bei jedem LLM-Aufruf. Schlüssel ist die
# bereinigte session_id; misslingt die Extraktion, die PID des Elternprozesses —
# damit fällt die Sperre GESCHLOSSEN aus (höchstens einmal pro Hermes-Prozess) und
# nie offen (einmal pro Aufruf).
if [ -n "$payload" ]; then
  session_id="$(printf '%s' "$payload" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("session_id") or "")
except Exception: print("")' 2>/dev/null | tr -c 'A-Za-z0-9_-' '_' | cut -c1-80)" || session_id=""
  [ -n "$session_id" ] || session_id="pid-${PPID:-0}"

  marker="${TMPDIR:-/tmp}/engram-session-${session_id}"
  [ -e "$marker" ] && { printf '{}\n'; exit 0; }
  # Marker nicht schreibbar → wir könnten uns nicht merken, dass wir schon geredet
  # haben. Dann lieber schweigen als in jedem Turn dasselbe Briefing ausgeben.
  { : > "$marker"; } 2>/dev/null || { printf '{}\n'; exit 0; }
fi

OUT=""
add() { [ -n "${1:-}" ] || return 0; OUT="${OUT}${OUT:+$'\n\n'}$1"; }

# --- 1. Lernstand nachziehen --------------------------------------------------
# Vor allem anderen. Der Nudge und `doctor` sollen den Stand zeigen, der nach dem
# Pull gilt — sonst meldet Hermes Fälligkeiten, die eine Web-Session längst
# abgearbeitet hat.
#
# Konflikte werden NICHT automatisch aufgelöst: receipts/*.jsonl wäre als Union
# auflösbar, graphs/*.json trägt FSRS-State und ist es nicht. Eine Automatik hier
# wäre eine Maschine für stillen Datenverlust. Bei Konflikt: Rebase zurückrollen,
# laut melden, den Rest der Session normal weiterlaufen lassen.
if [ -n "${ENGRAM_STATE:-}" ]; then
  if sync_block="$(engram_state_sync_ok)"; then
    if ! git -C "$ENGRAM_STATE" pull --rebase --autostash origin main >/dev/null 2>&1; then
      git -C "$ENGRAM_STATE" rebase --abort >/dev/null 2>&1 || true
      add "engram: WARNUNG — \`git pull --rebase origin main\` im State-Repo ist fehlgeschlagen (Rebase zurückgerollt).
Der lokale Stand ist unversehrt, aber er kennt die Commits vom Remote nicht. Vor dem Weiterlernen von Hand klären:
\`git -C \"$ENGRAM_STATE\" pull --rebase origin main\` — bei Konflikten in learning/graphs/*.json entscheidet der NEUERE FSRS-Stand, learning/receipts/*.jsonl wird als Vereinigung BEIDER Seiten aufgelöst (append-only, nichts löschen)."
    fi
  else
    add "engram: Hinweis — der automatische Abgleich des State-Repos ist ausgesetzt: ${sync_block}."
  fi
else
  # Laut, mit Absicht. Stiller Datenverlust ist hier das schlimmste Ergebnis.
  add "engram: WARNUNG — kein engram-learning-Checkout gefunden. Der Lernstand landet dann in einem
Verzeichnis, das weder gepusht noch von Claude Code gesehen wird. Siehe .hermes/UEBERGABE-HERMES.md, Schritt 1."
fi

# --- 2. Briefing --------------------------------------------------------------
# Wörtlich dieselbe Datei wie in Claude Code — eine Quelle, zwei Plattformen. Die
# Hermes-Abweichungen stehen als kurzer Nachsatz dahinter, statt das Briefing zu
# gabeln: eine zweite Fassung liefe garantiert auseinander.
if [ -f "$ENGRAM_PROJECT/.claude/ORIENTIERUNG.md" ]; then
  add "$(cat "$ENGRAM_PROJECT/.claude/ORIENTIERUNG.md")"
  add "## Auf Hermes abweichend

- Die Kommandos heißen hier genauso (\`/engram-learn\`, \`/engram-review\`, \`/engram-coach\`,
  \`/engram-source\`, \`/engram-status\`) — die Skills liegen unter \`\$ENGRAM_ROOT/.hermes/skills\`.
- **Subagents heißen \`delegate_task\`.** Wo ein Skill „spawne den engram-assessor\" sagt, wird
  \`delegate_task\` mit dem Inhalt von \`\$ENGRAM_ROOT/agents/engram-<rolle>.md\` als \`context\`
  aufgerufen. Das Kind hat eigenen Kontext UND eine eigene Terminal-Session: \`ENGRAM_ROOT\` und
  \`ENGRAM_HOME\` gehören wörtlich in jeden Spawn-Prompt, sonst findet es die Engine nicht.
- Der Lernstand wird beim Sessionstart gepullt und nach **jedem Turn** nach \`main\` gepusht."
fi

# --- 3. init + Due-Nudge ------------------------------------------------------
# Die Engine druckt die Upstream-Schreibweise (/learn, /review, /coach). Hier heißen
# die Kommandos engram-*, also wird die Ausgabe umgeschrieben statt Upstream-Code
# gepatcht — das hält `git merge upstream/main` konfliktfrei.
python3 "$ENGRAM_PROJECT/scripts/engram.py" init >/dev/null 2>&1
add "$(python3 "$ENGRAM_PROJECT/scripts/engram.py" session-start 2>/dev/null \
        | sed -E 's#/(learn|review|coach)\b#/engram-\1#g' || true)"

# --- 4. Upstream-Sync-Check ---------------------------------------------------
# Wiederverwendet, nicht kopiert: das Skript ist plattformneutral (git ls-remote +
# cat-file -e, Cache unter ~/.cache/engram/upstream-check, kein fetch, kein Remote).
if [ -f "$ENGRAM_PROJECT/.claude/hooks/engram-sync-check.sh" ]; then
  add "$(bash "$ENGRAM_PROJECT/.claude/hooks/engram-sync-check.sh" 2>/dev/null || true)"
fi

# --- 5. Interessen-Gate -------------------------------------------------------
# Themen da, `interests` leer: die Signatur eines übersprungenen Intake-Schritts 3.
# Ein frischer Stand ohne Themen bleibt still, sonst wäre die Warnung schon in der
# allerersten Session Rauschen.
add "$(python3 - "${ENGRAM_HOME:-$HOME/.claude/learning}" <<'PY' 2>/dev/null || true
import json, os, sys
home = sys.argv[1]
try:
    with open(os.path.join(home, "learner-model.json"), encoding="utf-8") as fh:
        if json.load(fh).get("interests"):
            sys.exit(0)
    graphs = os.path.join(home, "graphs")
    if not any(f.endswith(".json") for f in os.listdir(graphs)):
        sys.exit(0)
except Exception:
    sys.exit(0)
print("engram: `interests` im learner-model ist leer, obwohl schon Themen existieren "
      "— neue Themen bekommen so keine Analogien. `model --add-interest` beim "
      "nächsten /engram-learn nachholen.")
PY
)"

# --- 6. Marker für die Skills -------------------------------------------------
# Der Hermes-Ersatz für ENGRAM_HOOKS_ACTIVE: Ein Hook kann hier keine Variable in
# die Shell des Agenten exportieren, also hinterlässt er eine Datei. Der
# Bootstrap-Block der Skills prüft ihre mtime — frisch heißt „die Hooks laufen",
# fehlend oder alt heißt „am Ende von Hand speichern".
#
# Zuletzt gesetzt, aber unabhängig vom Rest: Er sagt aus, dass DIESER HOOK GELAUFEN
# ist, nicht dass irgendetwas davon geklappt hat. Genau das ist die Frage, die die
# Skills stellen.
_hh="${HERMES_HOME:-$HOME/.hermes}"
[ -d "$_hh" ] && : > "$_hh/.engram-hooks-active" 2>/dev/null || true

if [ -n "$payload" ]; then
  emit_json "$OUT"
else
  [ -n "$OUT" ] && printf '%s\n' "$OUT"
fi
exit 0
