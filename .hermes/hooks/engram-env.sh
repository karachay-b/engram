#!/usr/bin/env bash
# Gemeinsamer Resolver der Hermes-Verdrahtung. Wird von session-start.sh und
# engram-save.sh gesourct — nie direkt ausgeführt.
#
# Setzt, soweit möglich:
#   ENGRAM_PROJECT  absoluter Pfad des engram-Checkouts
#   ENGRAM_ROOT     derselbe Pfad, exportiert — der Notausgang, auf den auch der
#                   unveränderte Upstream-Resolver anspringt
#   ENGRAM_STATE    absoluter Pfad des engram-learning-Checkouts (State-Repo)
#   ENGRAM_HOME     $ENGRAM_STATE/learning — was engram.py liest und schreibt
#
# Schwestermodul: .claude/hooks/engram-env.sh. Die dortige Fassung ist die
# Referenz; hier stehen genau die Abweichungen, die Hermes erzwingt:
#
#   1. $CLAUDE_PROJECT_DIR und $CLAUDE_ENV_FILE gibt es nicht. Vor allem das
#      zweite fehlt ersatzlos: Ein Hermes-Hook kann KEINE Variable in die
#      Shell des Agenten exportieren. Deshalb trägt ~/.hermes/.env die drei
#      Pfade statisch — auf einem Desktop sind sie stabil, und das Problem aus
#      CLAUDE.md („Hooks laufen nicht in jeder Session") existiert hier nicht.
#      Dieser Resolver ist damit nicht der Weg, auf dem die Variablen zum
#      Agenten kommen, sondern der Weg, auf dem die HOOKS selbst sie finden —
#      auch dann, wenn .env fehlt oder falsch steht.
#   2. Der Standardpfad ist $HOME/engram (macOS/Linux-Desktop), nicht
#      /home/user/engram. Letzteres bleibt als letzter Kandidat stehen, damit
#      dasselbe Skript in einem Cloud-Container nicht plötzlich blind ist.
#   3. engram_state_sync_ok() kommt dazu — beide Hooks pullen und pushen, und
#      beide müssen vorher wissen, ob das Repo dafür überhaupt in der Verfassung
#      ist.

# --- das engram-Checkout ------------------------------------------------------
# Erster Treffer gewinnt. BASH_SOURCE steht weit vorn, weil es exakt ist, sobald
# diese Datei über ihren Pfad gesourct wird — und Hermes ruft Hooks immer mit
# absolutem Pfad auf (die Konfiguration verlangt es).
ENGRAM_PROJECT=""
for _p in "${ENGRAM_ROOT:-}" \
          "$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/../.." 2>/dev/null && pwd)" \
          "$PWD" \
          "$(git rev-parse --show-toplevel 2>/dev/null)" \
          "$HOME/engram" \
          "/home/user/engram"; do
  [ -n "$_p" ] || continue
  if [ -f "$_p/scripts/engram.py" ]; then
    ENGRAM_PROJECT="$(CDPATH= cd -- "$_p" 2>/dev/null && pwd)"
    break
  fi
done
unset _p

# Bei Fehlschlag werden geerbte Werte GELÖSCHT, nicht stehen gelassen. Ein aus der
# Umgebung mitgebrachtes ENGRAM_ROOT/ENGRAM_HOME überlebte sonst eine gescheiterte
# Auflösung und zeigte auf ein Checkout, das diese Session nie geprüft hat — und
# engram.py schreibt den Lernstand dorthin, wo ENGRAM_HOME hinzeigt. Ein
# Fehlschlag muss wie „hier ist kein engram" aussehen, nicht wie ein alter Treffer.
if [ -n "$ENGRAM_PROJECT" ]; then
  ENGRAM_ROOT="$ENGRAM_PROJECT"
  export ENGRAM_ROOT ENGRAM_PROJECT
else
  unset ENGRAM_ROOT ENGRAM_HOME 2>/dev/null || true
fi

# --- das State-Repo -----------------------------------------------------------
# Erster Treffer gewinnt. ENGRAM_STATE_REPO ist der Notausgang für ein Checkout an
# ungewohnter Stelle; die Kette ist zeichengleich zu .claude/hooks/engram-env.sh,
# nur um $HOME/engram-learning vorgezogen.
ENGRAM_STATE=""
for _c in "${ENGRAM_STATE_REPO:-}" \
          "$ENGRAM_PROJECT/../engram-learning" \
          "$HOME/engram-learning" \
          "/home/user/engram-learning"; do
  [ -n "$_c" ] || continue
  if [ -d "$_c/.git" ]; then
    ENGRAM_STATE="$(CDPATH= cd -- "$_c" 2>/dev/null && pwd)"
    break
  fi
done
unset _c

# Gleiche Regel wie oben: kein State-Repo heißt kein ENGRAM_HOME.
if [ -n "$ENGRAM_STATE" ]; then
  ENGRAM_HOME="$ENGRAM_STATE/learning"
  export ENGRAM_STATE ENGRAM_HOME
else
  unset ENGRAM_HOME 2>/dev/null || true
fi

# --- Zustand des State-Repos --------------------------------------------------
# Beantwortet genau eine Frage: Darf hier automatisch gepullt und gepusht werden?
#
# Ein laufender Rebase oder Merge ist das entscheidende Nein. Beides bedeutet, dass
# ein Mensch mitten in einer Konfliktauflösung steckt; ein Hook, der da hineinfährt,
# zerstört die halbfertige Auflösung, und zwar still. Ein abweichender Branch ist das
# zweite Nein: Diese Verdrahtung ist auf `main` festgelegt, und wer bewusst auf einem
# anderen Branch steht, hat einen Grund, den ein Hook nicht kennt.
#
# Gibt den Grund auf stdout aus (eine Zeile, leer bei ok) und 0/1 zurück.
engram_state_sync_ok() {
  [ -n "$ENGRAM_STATE" ] || { echo "kein State-Repo gefunden"; return 1; }
  local gd
  gd="$(git -C "$ENGRAM_STATE" rev-parse --git-dir 2>/dev/null)" || {
    echo "kein Git-Repo: $ENGRAM_STATE"; return 1; }
  case "$gd" in /*) ;; *) gd="$ENGRAM_STATE/$gd" ;; esac
  if [ -d "$gd/rebase-merge" ] || [ -d "$gd/rebase-apply" ] || [ -f "$gd/MERGE_HEAD" ]; then
    echo "im State-Repo läuft ein Rebase/Merge — Auflösung von Hand, der Hook fasst nichts an"
    return 1
  fi
  git -C "$ENGRAM_STATE" remote get-url origin >/dev/null 2>&1 || {
    echo "kein Remote 'origin' im State-Repo"; return 1; }
  local br
  br="$(git -C "$ENGRAM_STATE" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  [ "$br" = "main" ] || { echo "State-Repo steht auf '$br', nicht auf 'main'"; return 1; }
  return 0
}
