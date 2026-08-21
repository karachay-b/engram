#!/usr/bin/env bash
# Prüft höchstens 1x/Tag, ob nagisanzenin/engram (Upstream) weitergezogen ist.
# Sourcet nichts, mutiert kein Repo, legt kein Remote an — reine Leseprüfung per
# `git ls-remote` gegen die URL. Cache verhindert einen Netzwerkabruf pro Session.
#
# MUSS NIE EINE SESSION SCHEITERN LASSEN: jeder Fehlerpfad -> exit 0, still.
set -u

UPSTREAM_URL="https://github.com/nagisanzenin/engram.git"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/engram"
CACHE_FILE="$CACHE_DIR/upstream-check"
TODAY="$(date -u +%F)"

ENGRAM_PROJECT="${ENGRAM_PROJECT:-${ENGRAM_ROOT:-}}"
[ -n "$ENGRAM_PROJECT" ] && [ -f "$ENGRAM_PROJECT/package.json" ] || exit 0

mkdir -p "$CACHE_DIR" 2>/dev/null || exit 0

# --- Cache: heute schon geprüft? ----------------------------------------------
# Zeile 3 trägt den remote_sha von damals. Vor der Ausgabe der gecachten Meldung
# wird lokal (kein Netzwerk) erneut geprüft, ob dieser Commit inzwischen vorliegt
# — sonst behauptet der Cache bis Mitternacht (UTC) weiter "Upstream ist weiter",
# auch wenn der Nutzer den Sync direkt nach der ersten Meldung gemacht hat.
if [ -f "$CACHE_FILE" ]; then
  cached_date="$(sed -n '1p' "$CACHE_FILE" 2>/dev/null)"
  if [ "$cached_date" = "$TODAY" ]; then
    cached_msg="$(sed -n '2p' "$CACHE_FILE" 2>/dev/null)"
    cached_sha="$(sed -n '3p' "$CACHE_FILE" 2>/dev/null)"
    if [ -n "$cached_msg" ] && [ -n "$cached_sha" ] && [ -n "$ENGRAM_PROJECT" ] \
       && git -C "$ENGRAM_PROJECT" cat-file -e "${cached_sha}^{commit}" 2>/dev/null; then
      # Inzwischen lokal vorhanden (z.B. der Nutzer hat gemergt) — Meldung
      # unterdrücken und die Cache-Zeile leeren, damit kein weiterer Lauf heute
      # sie erneut ausgibt.
      printf '%s\n\n\n' "$TODAY" > "$CACHE_FILE"
      exit 0
    fi
    [ -n "$cached_msg" ] && echo "$cached_msg"
    exit 0
  fi
fi

command -v git >/dev/null 2>&1 || exit 0

# `timeout` fehlt auf macOS ohne coreutils (nur `gtimeout`) — ungegated läuft die
# Kommandosubstitution dort leer, der Check verstummt für immer und der Cache wird
# nie geschrieben. Derselbe Fehlermodus wie der cygpath-Bug in
# .hermes/hooks/engram-env.sh; dasselbe Gate-Muster. Ohne timeout läuft
# `git ls-remote` ungedeckelt — akzeptabel, weil jeder Fehlerpfad hier ohnehin
# still geschluckt wird.
_to=""
command -v timeout  >/dev/null 2>&1 && _to="timeout 10"
[ -z "$_to" ] && command -v gtimeout >/dev/null 2>&1 && _to="gtimeout 10"

# --- Upstream-main-Sha holen, hart begrenzt -----------------------------------
remote_line="$($_to git ls-remote "$UPSTREAM_URL" refs/heads/main 2>/dev/null)"
[ -n "$remote_line" ] || exit 0   # Netzwerk/Timeout: schweigen, Cache NICHT schreiben
remote_sha="${remote_line%%$'\t'*}"
[ -n "$remote_sha" ] || exit 0

# --- Liegt dieser Commit lokal schon vor? -------------------------------------
if git -C "$ENGRAM_PROJECT" cat-file -e "${remote_sha}^{commit}" 2>/dev/null; then
  printf '%s\n\n\n' "$TODAY" > "$CACHE_FILE"
  exit 0
fi

# --- Neuesten stabilen Tag ermitteln (best effort) ----------------------------
latest_tag=""
tags_raw="$($_to git ls-remote --tags "$UPSTREAM_URL" 2>/dev/null)"
if [ -n "$tags_raw" ]; then
  latest_tag="$(printf '%s\n' "$tags_raw" \
    | sed -n 's#.*refs/tags/##p' \
    | grep -v '\^{}$' \
    | grep -viE 'rc[0-9]*$|beta[0-9]*$|alpha[0-9]*$' \
    | sort -V | tail -1)"
fi

local_version="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
  "$ENGRAM_PROJECT/package.json" 2>/dev/null | head -1)"

short_sha="${remote_sha:0:7}"
if [ -n "$latest_tag" ]; then
  msg="[engram] Upstream ist weiter (main: $short_sha). Neuester stabiler Tag: $latest_tag · lokal: ${local_version:-?}. Sag „sync\", dann hole ich die Änderungen und lasse den Selftest laufen."
else
  msg="[engram] Upstream ist weiter (main: $short_sha, lokal: ${local_version:-?}). Sag „sync\", dann hole ich die Änderungen und lasse den Selftest laufen."
fi

printf '%s\n%s\n%s\n' "$TODAY" "$msg" "$remote_sha" > "$CACHE_FILE"
echo "$msg"
exit 0
