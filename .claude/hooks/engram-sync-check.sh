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
if [ -f "$CACHE_FILE" ]; then
  cached_date="$(sed -n '1p' "$CACHE_FILE" 2>/dev/null)"
  if [ "$cached_date" = "$TODAY" ]; then
    cached_msg="$(sed -n '2p' "$CACHE_FILE" 2>/dev/null)"
    [ -n "$cached_msg" ] && echo "$cached_msg"
    exit 0
  fi
fi

command -v git >/dev/null 2>&1 || exit 0

# --- Upstream-main-Sha holen, hart begrenzt -----------------------------------
remote_line="$(timeout 10 git ls-remote "$UPSTREAM_URL" refs/heads/main 2>/dev/null)"
[ -n "$remote_line" ] || exit 0   # Netzwerk/Timeout: schweigen, Cache NICHT schreiben
remote_sha="${remote_line%%$'\t'*}"
[ -n "$remote_sha" ] || exit 0

# --- Liegt dieser Commit lokal schon vor? -------------------------------------
if git -C "$ENGRAM_PROJECT" cat-file -e "${remote_sha}^{commit}" 2>/dev/null; then
  printf '%s\n\n' "$TODAY" > "$CACHE_FILE"
  exit 0
fi

# --- Neuesten stabilen Tag ermitteln (best effort) ----------------------------
latest_tag=""
tags_raw="$(timeout 10 git ls-remote --tags "$UPSTREAM_URL" 2>/dev/null)"
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

printf '%s\n%s\n' "$TODAY" "$msg" > "$CACHE_FILE"
echo "$msg"
exit 0
