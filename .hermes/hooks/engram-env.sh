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
#   4. Ein Riegel auf ENGRAM_HERMES=1 kommt VOR allem anderen. Ohne eigenes
#      Hermes-Profil (siehe .hermes/UEBERGABE-HERMES.md, Schritt 1) findet dieser
#      Resolver $HOME/engram IMMER — jede Hermes-Session auf dem Rechner bekäme
#      sonst das Engram-Briefing injiziert, auch eine über etwas völlig anderes.
#      Die Variable gehört in die .env des Profils; ist sie nicht in die
#      Prozessumgebung vererbt (z. B. weil dieser Hook außerhalb von Hermes'
#      eigenem Start läuft — ein Cron-Skript ist genau so ein Fall), lädt der
#      Riegel sie selbst aus der Profil-.env nach, bevor er aufgibt.

# --- ENGRAM_HERMES-Riegel ------------------------------------------------------
# Fehlt die Variable, zuerst versuchen, sie (und die drei Pfade) aus der Profil-
# .env nachzuladen — NUR ENGRAM_*-Zeilen, per case/Schlüssel-Weiße-Liste, kein
# Sourcen der Datei: .env ist keine Shell und darf nicht blind ausgeführt werden.
# Ein bereits gesetzter Wert hat Vorrang vor der Datei, nicht umgekehrt.
if [ "${ENGRAM_HERMES:-}" != "1" ]; then
  _env_file="${HERMES_HOME:-$HOME/.hermes}/.env"
  if [ -f "$_env_file" ]; then
    while IFS='=' read -r _k _v; do
      case "$_k" in
        ENGRAM_HERMES)     [ -n "${ENGRAM_HERMES:-}" ]     || ENGRAM_HERMES="$_v" ;;
        ENGRAM_ROOT)       [ -n "${ENGRAM_ROOT:-}" ]       || ENGRAM_ROOT="$_v" ;;
        ENGRAM_HOME)       [ -n "${ENGRAM_HOME:-}" ]       || ENGRAM_HOME="$_v" ;;
        ENGRAM_STATE_REPO) [ -n "${ENGRAM_STATE_REPO:-}" ] || ENGRAM_STATE_REPO="$_v" ;;
      esac
    done < "$_env_file"
  fi
  unset _env_file _k _v
fi

# Immer noch nichts: Diese Session ist nicht das Profil engram, oder das Profil
# ist nicht eingerichtet. Beide Hooks sollen dann still bleiben — sie tun das,
# indem dieses gesourcte Skript mit Fehlschlag zurückkehrt (`return`, nicht
# `exit`: es wird gesourct, nie direkt ausgeführt) und die Aufrufer den
# bestehenden `|| done_` / `|| { …; exit 0; }`-Pfad nehmen, den sie ohnehin schon
# für einen Sourcing-Fehler haben.
if [ "${ENGRAM_HERMES:-}" != "1" ]; then
  return 1 2>/dev/null || exit 1
fi
export ENGRAM_HERMES

# --- Pfadnormalisierung, plattformabhängig ------------------------------------
# Windows/MSYS-Abweichung (gemessen 2026-08-20, siehe .hermes/PLATTFORM.md §7.2):
# `CDPATH= cd -- … && pwd` liefert dort `/c/Users/...`, was `git -C` nicht
# versteht (Exit 128). `cygpath -w` konvertiert zuverlässig nach `C:\Users\...`.
#
# `cygpath` existiert AUSSCHLIESSLICH unter MSYS/Cygwin — auf jedem macOS- oder
# Linux-Host (also auch jedem Nicht-Windows-Hermes-Desktop und jedem
# Linux-Container, der diese Datei zu Testzwecken sourct) gibt es den Befehl
# nicht. Ungated bricht `cygpath -w` dort mit „command not found", die
# Kommandosubstitution liefert leeren String, und der Resolver hält das für
# „kein Checkout gefunden" — obwohl eins da ist. Genau das geschah hier, bevor
# dieser Aufruf hinter `command -v cygpath` gestellt wurde: Diese Datei ist die
# EINE Verdrahtung für jede Hermes-Desktop-Installation, nicht nur für Windows,
# und ein host-spezifischer Fix ohne Gate bricht sie für jeden anderen Host.
_engram_native_path() {  # $1 = Pfad; auf stdout der normalisierte Pfad, leer bei Fehler
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1" 2>/dev/null
  else
    (CDPATH= cd -- "$1" 2>/dev/null && pwd)
  fi
}

# --- Interpreter-Auflösung, derselbe Gate-Fehler wie bei cygpath vermieden ----
# Windows/MSYS-Abweichung (gemessen, siehe .hermes/PLATTFORM.md §7.1): Auf einem
# Host mit installiertem Windows-Python-Store-Alias zeigt `python3` in
# `/c/Users/.../WindowsApps/python3` auf den Store-Hinweis statt auf eine echte
# Installation. `command -v python3` findet diesen Stub trotzdem — er ist ein
# ausführbares Ding im PATH, `command -v` prüft nicht, ob er funktioniert. Jeder
# `python3`-Aufruf aus einem Hook scheitert dann mit Exit 49, und die Hooks
# fallen lautlos auf ihren `|| exit 0`-Pfad: der Due-Nudge, die
# Interessen-Gate-Warnung und die echte Commit-Message-Statistik verstummen,
# ohne dass irgendwo ein Fehler sichtbar wird. Derselbe Fehlermodus wie beim
# ungegateten `cygpath` oben — hier deshalb derselbe Kniff: nicht nur prüfen, ob
# der Befehl EXISTIERT (`command -v`), sondern ob er tatsächlich LÄUFT (`-c ''`).
#
# Reihenfolge python3 → py -3 → python: unverändertes Verhalten auf jedem Host,
# auf dem `python3` schon funktioniert (macOS, Linux, jede normale
# Windows-Installation) — dort liefert schon der erste Versuch. `py -3` ist der
# Windows-Python-Launcher, Standardbestandteil jeder offiziellen
# Windows-Python-Installation und genau der Befehl, den §7.1 als zuverlässig
# nennt.
_engram_python() {  # stdout: lauffähiger Interpreter-Befehl; leer bei Fehlschlag
  command -v python3 >/dev/null 2>&1 && python3 -c '' >/dev/null 2>&1 && { echo "python3"; return 0; }
  command -v py      >/dev/null 2>&1 && py -3 -c ''    >/dev/null 2>&1 && { echo "py -3"; return 0; }
  command -v python  >/dev/null 2>&1 && python -c ''   >/dev/null 2>&1 && { echo "python"; return 0; }
  return 1
}
ENGRAM_PY="$(_engram_python)"
export ENGRAM_PY

# --- das engram-Checkout ------------------------------------------------------
# Erster Treffer gewinnt. BASH_SOURCE steht weit vorn, weil es exakt ist, sobald
# diese Datei über ihren Pfad gesourct wird — und Hermes ruft Hooks immer mit
# absolutem Pfad auf (die Konfiguration verlangt es).
ENGRAM_PROJECT=""
for _p in "${ENGRAM_ROOT:-}" \
          "$(_engram_native_path "$(dirname -- "${BASH_SOURCE[0]:-$0}")/../..")" \
          "$PWD" \
          "$(git rev-parse --show-toplevel 2>/dev/null)" \
          "$HOME/engram" \
          "/home/user/engram"; do
  [ -n "$_p" ] || continue
  if [ -f "$_p/scripts/engram.py" ]; then
    ENGRAM_PROJECT="$(_engram_native_path "$_p")"
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
    ENGRAM_STATE="$(_engram_native_path "$_c")"
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
