#!/bin/bash
# Setup-Skript der Cloud-Umgebung — NICHT vom Repo ausgeführt.
#
# Diese Datei ist die maßgebliche Fassung; ausgeführt wird eine Kopie, die im
# Web-Formular liegt. Auf claude.ai: Umgebungs-Selektor über dem Eingabefeld →
# Zahnrad an der Umgebung → Feld „Setup script". Inhalt hierher kopieren.
#
# ---------------------------------------------------------------------------
# WOFÜR
#
# `.claude/settings.json` dieses Repos — und damit beide Engram-Hooks — wird nur
# geladen, wenn das Projektverzeichnis der Session dieses Repo IST. Hängen
# `engram` und `engram-learning` gemeinsam an einer Session, ist das
# Projektverzeichnis der gemeinsame Elternordner (`/home/user`), und dann feuert
# kein Repo-Hook: kein ENGRAM_HOME, vor allem kein Auto-Save. Der Lernstand
# stirbt dann mit dem Container.
#
# Eine `~/.claude/settings.json` im Container wird dagegen unabhängig vom
# Projektverzeichnis gelesen (nachgemessen, nicht angenommen). Der Launcher der
# Umgebung benutzt für seine eigenen Hooks eine separate Datei
# (`launcher-settings.json`) und fasst `settings.json` nicht an — der Platz ist
# also frei.
#
# ---------------------------------------------------------------------------
# WANN ES LÄUFT
#
# Als root, vor dem Start von Claude Code, und nur beim Aufbau des
# Umgebungs-Caches: bei der ersten Session, nach jeder Änderung an Skript oder
# Netzwerk-Allowlist, und wenn der Cache nach etwa sieben Tagen verfällt.
# Danach wird das Dateisystem als Snapshot wiederverwendet — was hier
# geschrieben wird, liegt in jeder späteren Session bereits da. Eine schon
# laufende Session bekommt eine Änderung nicht mehr mit.
#
# Das Skript MUSS mit 0 enden, sonst startet die Session nicht. Deshalb überall
# der stille Ausstieg.
#
# ---------------------------------------------------------------------------
# NEBENWIRKUNGEN, BEWUSST IN KAUF GENOMMEN
#
# Die Registrierung gilt für die ganze Umgebung, also auch für Sessions zu
# völlig anderen Repos. Der Dispatcher findet dort kein Engram-Checkout und
# beendet sich geräuschlos — deshalb sucht er das Checkout auch erst zur
# Hook-Laufzeit und nicht hier: beim Cache-Aufbau ist noch nichts geklont.
#
# Läuft eine Session doch mit dem Repo als Projektverzeichnis, feuern Repo-Hook
# und User-Hook beide. Der zweite Lauf von engram-save.sh findet einen sauberen
# Baum und steigt sofort aus. Harmlos, aber gut zu wissen.
set -u

CLAUDE_DIR="/root/.claude"
mkdir -p "$CLAUDE_DIR"

cat > "$CLAUDE_DIR/engram-hook.sh" <<'SH'
#!/usr/bin/env bash
# Dispatcher für die Engram-Hooks. Sucht das Checkout zur Hook-Laufzeit und
# beendet sich still, wenn keines da ist. Siehe .claude/cloud-setup.sh im
# engram-Repo für die Begründung.
set -u

hook="${1:-}"
[ -n "$hook" ] || exit 0

for d in "${ENGRAM_ROOT:-}" /home/user/engram "$HOME/engram"; do
  [ -n "$d" ] || continue
  if [ -f "$d/.claude/hooks/$hook" ]; then
    bash "$d/.claude/hooks/$hook"
    exit 0
  fi
done

exit 0
SH
chmod +x "$CLAUDE_DIR/engram-hook.sh"

NEW="$(mktemp)"
cat > "$NEW" <<'JSON'
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear",
        "hooks": [
          {
            "type": "command",
            "command": "bash /root/.claude/engram-hook.sh session-start.sh",
            "timeout": 120
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash /root/.claude/engram-hook.sh engram-save.sh",
            "timeout": 120
          }
        ]
      }
    ]
  }
}
JSON

# Vorhandene Registrierungen erhalten.
#
# `jq '.[0] * .[1]'` täte das NICHT: Der Multiplikations-Operator verschmilzt zwar
# Objekte rekursiv, ersetzt Arrays aber komplett. Ein bereits eingetragener
# SessionStart- oder Stop-Hook — etwa aus einem anderen Setup derselben Umgebung —
# verschwände damit wortlos. Deshalb werden die Arrays pro Event aneinandergehängt.
#
# Reines `unique_by(tojson)` reicht dafür NICHT: Es dedupliziert nur exakt
# gleiche Einträge. Ändert sich an einem Engram-Eintrag etwas anderes als der
# Befehl selbst — z.B. der `matcher` oder ein `timeout` —, bekäme der neue
# Eintrag einen anderen JSON-Fingerabdruck als der alte und beide blieben nebeneinander
# stehen, sobald ein alter Cache-Snapshot die Vorgängerfassung schon enthält. Ein alter
# `command`-Wert identifiziert denselben Engram-Hook eindeutig — deshalb ersetzt
# `merge_event` Alteinträge mit demselben `command` durch den neuen, statt nur zu
# deduplizieren; `unique_by(tojson)` am Ende bleibt als reine Absicherung gegen
# einen Doppellauf mit identischem Ergebnis.
if [ ! -s "$CLAUDE_DIR/settings.json" ]; then
  cp "$NEW" "$CLAUDE_DIR/settings.json"
elif ! command -v jq >/dev/null 2>&1; then
  # Fail closed: lieber ohne Auto-Save weiterlaufen als eine fremde Konfiguration
  # überschreiben. Die Alias-Skills warnen dann sichtbar, dass der Hook fehlt.
  echo "engram-setup: jq fehlt — ~/.claude/settings.json bleibt unangetastet." >&2
elif ! jq empty "$CLAUDE_DIR/settings.json" 2>/dev/null; then
  # Kaputtes JSON nicht stillschweigend wegwerfen: beiseitelegen, dann neu schreiben.
  cp "$CLAUDE_DIR/settings.json" "$CLAUDE_DIR/settings.json.bak.$(date +%s)" 2>/dev/null || true
  echo "engram-setup: ~/.claude/settings.json war kein gültiges JSON — Sicherung angelegt." >&2
  cp "$NEW" "$CLAUDE_DIR/settings.json"
else
  if jq -s '
        def merge_event($old; $new):
          ($new // []) as $newarr
          | [$newarr[].hooks[]?.command] as $new_cmds
          | (($old // []) | map(select(
              ([.hooks[]?.command] | any(. as $x | $new_cmds | index($x) != null)) | not
            ))) as $kept_old
          | ($kept_old + $newarr) | unique_by(tojson);
        .[0] as $a | .[1] as $b
        | $a
        | .hooks = (($a.hooks // {}) + ($b.hooks // {}))
        | .hooks.SessionStart = merge_event($a.hooks.SessionStart; $b.hooks.SessionStart)
        | .hooks.Stop         = merge_event($a.hooks.Stop;         $b.hooks.Stop)
      ' "$CLAUDE_DIR/settings.json" "$NEW" > "$CLAUDE_DIR/settings.json.tmp" 2>/dev/null \
     && [ -s "$CLAUDE_DIR/settings.json.tmp" ]; then
    mv "$CLAUDE_DIR/settings.json.tmp" "$CLAUDE_DIR/settings.json"
  else
    rm -f "$CLAUDE_DIR/settings.json.tmp"
    echo "engram-setup: Merge fehlgeschlagen — ~/.claude/settings.json bleibt unangetastet." >&2
  fi
fi
rm -f "$NEW"

exit 0
