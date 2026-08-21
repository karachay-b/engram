#!/usr/bin/env bash
# SessionStart hook — makes Engram usable in Claude Code on the web.
#
#   0. prints ORIENTIERUNG.md — compact briefing on both repos, the five
#      commands, the binding rules
#   1. points ENGRAM_HOME at the private state repo, so the learning state
#      survives the container being reclaimed
#   2. runs `engram.py init` (idempotent)
#   3. surfaces due reviews — Engram's own two-line nudge, silent when nothing
#      is due — then a cached, at-most-daily check for whether upstream
#      (nagisanzenin/engram) has moved on
#   4. installs node deps so `bun run test` / `npx tsc --noEmit` work
#
# Runs synchronously: the due nudge has to be on screen before the first turn.
# MUST NEVER FAIL A SESSION — every path ends in exit 0.
set -u

# --- 0. registration marker ---------------------------------------------------
# Proof that the Engram hooks are registered in THIS session, published into the
# session environment so the alias bootstraps can test it. If this hook runs at
# all, the Stop hook is registered too — they come from the same settings file —
# and the auto-save works.
#
# Written FIRST, before any resolution: the marker is about hook registration,
# not about whether a checkout was found. Written unconditionally rather than
# only on success, for the same reason.
#
# Why not reuse ENGRAM_HOME as the signal: it is also set by the alias bootstrap
# itself and can be supplied as a plain environment variable in the cloud
# environment's settings. Either would make an unregistered session look
# registered and silently suppress the manual-save warning — the one warning
# that stands between the learner and a lost session.
[ -n "${CLAUDE_ENV_FILE:-}" ] && echo 'export ENGRAM_HOOKS_ACTIVE=1' >> "$CLAUDE_ENV_FILE"
export ENGRAM_HOOKS_ACTIVE=1

HOOK_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
# shellcheck source=engram-env.sh
. "$HOOK_DIR/engram-env.sh" 2>/dev/null || exit 0

[ -f "$ENGRAM_PROJECT/scripts/engram.py" ] || exit 0
command -v python3 >/dev/null 2>&1 || {
  echo "engram: python3 fehlt — die Engine kann nicht laufen."
  exit 0
}

# --- 0b. Briefing --------------------------------------------------------------
# Kompakte Orientierung vor allem anderen: was die beiden Repos tun, wie sie
# verzahnt sind, die fünf Kommandos, die drei bindenden Regeln. CLAUDE.md bleibt
# das ausführliche Nachschlagewerk; das hier ist das, was jede Session verlässlich
# lesen soll. Fehlt die Datei (älterer Checkout), einfach weiter.
[ -f "$ENGRAM_PROJECT/.claude/ORIENTIERUNG.md" ] && cat "$ENGRAM_PROJECT/.claude/ORIENTIERUNG.md"

# --- 1. state location --------------------------------------------------------
# ENGRAM_ROOT geht mit hinaus, nicht nur ENGRAM_HOME: Es ist der Notausgang, auf
# den der unveränderte Upstream-Resolver (skills/learn/SKILL.md) und
# resolve_engram_root() in engram_status.py anspringen. Ohne diese Zeile bleibt
# es in der Bash-Umgebung der Session leer, bis der Bootstrap-Block eines Alias-
# Skills es selbst setzt — der Block bleibt trotzdem Pflicht (er trägt die
# Hook-Warnung, siehe CLAUDE.md), das hier macht ihn nur redundant statt nötig.
if [ -n "$ENGRAM_PROJECT" ] && [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export ENGRAM_ROOT=\"$ENGRAM_PROJECT\"" >> "$CLAUDE_ENV_FILE"
fi
if [ -n "$ENGRAM_STATE" ]; then
  mkdir -p "$ENGRAM_HOME" 2>/dev/null
  export ENGRAM_HOME
  [ -n "${CLAUDE_ENV_FILE:-}" ] && echo "export ENGRAM_HOME=\"$ENGRAM_HOME\"" >> "$CLAUDE_ENV_FILE"
else
  # Loud on purpose. Silent data loss is the worst outcome here: the learner
  # would do the work and lose the schedule that work was for.
  echo "engram: WARNUNG — das private State-Repo (engram-learning) ist dieser Session nicht angehängt."
  echo "engram: Der Lernstand liegt nur im Container und ist nach dessen Ablauf weg. Siehe CLAUDE.md."
fi

# --- 1b. state repo pull (Symmetrie zu Hermes) ---------------------------------
# Hermes pullt den Lernstand bei Sessionstart (.hermes/hooks/session-start.sh)
# und pusht nach jedem Turn; diese Fassung pushte bisher nur (Stop-Hook), pullte
# nie. Beim Container-Start ist das egal (frischer Clone), aber bei einer
# RESUMED Session im selben Container kann die Engine sonst einen Stand lesen,
# den Hermes längst überholt hat — die Divergenz fällt erst beim nächsten Push
# auf, dann als Ablehnung, die der Stop-Hook selbst behebt, aber erst nach einer
# vollen Session mit veraltetem Stand im Kontext.
#
# Bewusst OHNE die Branch-main-Prüfung aus engram_state_sync_ok() — die ist eine
# Hermes-Eigenschaft (siehe CLAUDE.md, Begründung wie im Stop-Hook: das
# Cloud-Environment vergibt dem State-Repo hier so gut wie nie 'main'). Ein
# laufender Rebase/Merge bleibt die einzige Bedingung, die den Pull überspringt
# — dort steckt sonst möglicherweise ein Mensch mitten in einer
# Konfliktauflösung, in die ein automatischer Pull nicht hineinfahren darf.
if [ -n "$ENGRAM_STATE" ]; then
  _gd="$(git -C "$ENGRAM_STATE" rev-parse --git-dir 2>/dev/null)"
  if [ -n "$_gd" ]; then
    case "$_gd" in /*) ;; *) _gd="$ENGRAM_STATE/$_gd" ;; esac
    if [ -d "$_gd/rebase-merge" ] || [ -d "$_gd/rebase-apply" ] || [ -f "$_gd/MERGE_HEAD" ]; then
      echo "engram: State-Repo-Pull übersprungen — im State-Repo läuft ein Rebase/Merge."
    elif git -C "$ENGRAM_STATE" remote get-url origin >/dev/null 2>&1; then
      if ! git -C "$ENGRAM_STATE" pull --rebase --autostash origin main >/dev/null 2>&1; then
        git -C "$ENGRAM_STATE" rebase --abort >/dev/null 2>&1 || true
        echo "engram: WARNUNG — \`git pull --rebase origin main\` im State-Repo ist fehlgeschlagen (Rebase zurückgerollt)."
        echo "engram: Der lokale Stand ist unversehrt, kennt aber die Commits vom Remote nicht. Von Hand: git -C \"$ENGRAM_STATE\" pull --rebase origin main"
      fi
    fi
  fi
  unset _gd
fi

# --- 2./3. init + due nudge ---------------------------------------------------
# The engine prints upstream's command spelling (/learn, /review, /coach). Here the
# skills are namespaced to avoid colliding with the global `learn` skill and with
# Claude Code's built-in /review, so rewrite the names on the way out rather than
# patching upstream code — that keeps `git merge upstream/main` conflict-free.
python3 "$ENGRAM_PROJECT/scripts/engram.py" init >/dev/null 2>&1
python3 "$ENGRAM_PROJECT/scripts/engram.py" session-start 2>/dev/null \
  | sed -E 's#/(learn|review|coach)\b#/engram-\1#g' || true

# --- 3a. upstream sync check ----------------------------------------------------
# At most once/day (cached), non-fatal, never blocks: a network hiccup here must
# never delay or break the session. See engram-sync-check.sh for the ancestry test
# (git ls-remote + cat-file -e, no fetch, no remote added, no repo mutation).
[ -f "$HOOK_DIR/engram-sync-check.sh" ] && bash "$HOOK_DIR/engram-sync-check.sh" 2>/dev/null || true

# --- 3b. interests gate ---------------------------------------------------------
# Topics exist but `interests` is empty: that combination is the signature of a
# skipped intake step 3 — the architect built at least one topic with no analogy
# fuel. A fresh state with no topics must stay quiet, or the warning becomes noise
# on the very first session. Non-fatal like everything else here.
# ENGRAM_HOME is unset when no state repo is attached (engram-env.sh:35-37) — then
# the engine reads its own default, so check that instead. `set -u` is on: never
# expand ENGRAM_HOME bare.
python3 - "${ENGRAM_HOME:-$HOME/.claude/learning}" <<'PY' 2>/dev/null || true
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

# --- 4. node deps (non-fatal; the container image caches this) -----------------
# --no-save: bun.lock is currently out of sync with package.json upstream, and a
# rewrite would leave every session with a dirty tree and a future merge conflict.
if [ ! -d "$ENGRAM_PROJECT/node_modules" ] && command -v bun >/dev/null 2>&1; then
  (cd "$ENGRAM_PROJECT" && bun install --no-save --silent) >/dev/null 2>&1 || true
fi

exit 0
