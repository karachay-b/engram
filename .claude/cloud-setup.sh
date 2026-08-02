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
            "timeout": 60
          }
        ]
      }
    ]
  }
}
JSON

# Vorhandene Schlüssel nicht zerstören, falls dort schon etwas steht.
if [ -s "$CLAUDE_DIR/settings.json" ] && jq empty "$CLAUDE_DIR/settings.json" 2>/dev/null; then
  jq -s '.[0] * .[1]' "$CLAUDE_DIR/settings.json" "$NEW" > "$CLAUDE_DIR/settings.json.tmp" \
    && mv "$CLAUDE_DIR/settings.json.tmp" "$CLAUDE_DIR/settings.json"
else
  cp "$NEW" "$CLAUDE_DIR/settings.json"
fi
rm -f "$NEW"

exit 0
