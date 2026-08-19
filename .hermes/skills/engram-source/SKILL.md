---
name: engram-source
description: Bücher und PDFs als Grundlage für Engram-Lernstoff aufbereiten — Ingest in seitenreferenzierte Chunks, Nachschlagen, Digest. Use when the user wants to learn from a book, PDF, script or paper, mentions einbinden/ingesten/Quelle/Buch/Skript/Kapitel, or asks what sources are available.
version: 1.0.0
argument-hint: add <pfad|url> | list | show <slug> | find <slug> <regex> | digest <slug> | verify <slug> <pfad>
---

# Engram — Quellen aufbereiten (Hermes)

Buch oder PDF in seitenreferenzierte Chunks zerlegen, nachschlagen, zuordnen.

**Dünner Alias in zwei Stufen.** Die Regeln dieses Forks stehen **einmal**, unter
`.claude/skills/`, und werden von hier gelesen statt kopiert — eine zweite Fassung
derselben Regeln liefe auseinander, und die stillere gewänne. Dupliziert ist nur, was
dupliziert sein muss: dieser Bootstrap-Block und die `description` im Frontmatter.

## Schritt 0 — Bootstrap. Jetzt, vor allem anderen.

Findet das Checkout, lädt die Umgebung, prüft den Auto-Save. **Bootstrap und
Werkzeugaufruf gehören in denselben Terminal-Block** — jede Zelle startet eine neue
Shell, ein Bootstrap in eigener Zelle ist beim nächsten Aufruf wirkungslos.

```bash
_env=""
for d in "${ENGRAM_ROOT:-}" "$PWD" "$(git rev-parse --show-toplevel 2>/dev/null)" \
         "$HOME/engram" /home/user/engram; do
  [ -n "$d" ] || continue
  # Beide Marker verlangt: Ein Verzeichnis ist nur dann ein engram-Checkout, wenn es
  # auch die Engine trägt. Nur auf den Hook-Pfad hin zu sourcen würde ausführen, was
  # ein fremdes Repo zufällig unter diesem Namen mitbringt.
  [ -f "$d/scripts/engram.py" ] && [ -f "$d/.hermes/hooks/engram-env.sh" ] || continue
  _env="$d/.hermes/hooks/engram-env.sh"; break
done
if [ -z "$_env" ]; then
  echo "engram: Checkout nicht gefunden — ENGRAM_ROOT in ~/.hermes/.env auf das engram-Verzeichnis setzen." >&2
else
  . "$_env"
  # Der Hermes-Ersatz für ENGRAM_HOOKS_ACTIVE: Ein Hook kann hier keine Variable in
  # die Agenten-Shell exportieren, also hinterlässt session-start.sh eine Datei.
  # Frisch heißt "die Hooks laufen"; fehlend oder älter als 12 h heißt: von Hand speichern.
  _m="${HERMES_HOME:-$HOME/.hermes}/.engram-hooks-active"
  if [ ! -e "$_m" ] || [ -n "$(find "$_m" -mmin +720 2>/dev/null)" ]; then
    echo "engram: WARNUNG — der Auto-Save-Hook lief in dieser Session nicht (Marker fehlt oder ist alt)." >&2
    echo "engram: Am Ende 'bash \"$ENGRAM_ROOT/.hermes/hooks/engram-save.sh\"' von Hand ausführen," >&2
    echo "engram: sonst bleibt der Lernstand auf dieser Platte und Claude Code sieht ihn nie." >&2
  fi
fi
echo "ENGRAM_ROOT=${ENGRAM_ROOT:-<leer>}  ENGRAM_HOME=${ENGRAM_HOME:-<leer>}"
```

Bleibt `ENGRAM_HOME` leer, ist das private State-Repo nicht da: **nicht weiterarbeiten**,
sondern `.hermes/UEBERGABE-HERMES.md`, Schritt 1 abarbeiten. Die Engine schriebe sonst in
ein Verzeichnis, das niemand pusht und Claude Code nie sieht.

## Die Lesekette

1. **`$ENGRAM_ROOT/.hermes/PLATTFORM.md` lesen** — die bindenden Übersetzungen
   Claude Code → Hermes: `delegate_task` statt Subagent-Spawn, Marker-Datei statt
   `ENGRAM_HOOKS_ACTIVE`, Heredoc statt Write-Tool, kein Artifact-Weg.
2. **`$ENGRAM_ROOT/.claude/skills/engram-source/SKILL.md` vollständig lesen** und wörtlich
   befolgen — mit den Übersetzungen aus Schritt 1. Dort stehen die Regeln dieses
   Forks; sie sind nicht zusammenfassbar.
3. Kein Upstream-Pendant — dieser Skill ist vollständig Fork-eigen. Die Kette
   endet bei Schritt 2.

Nichts davon zusammenfassen, abkürzen oder aus dem Gedächtnis rekonstruieren. Diese
Datei ist nur ein Name, der auf Hermes nicht kollidiert — der Skill steht woanders.
