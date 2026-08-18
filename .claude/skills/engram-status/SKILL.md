---
name: engram-status
description: Momentaufnahme des Lernstands als geteilte Seite — welche Quellen eingebunden sind, wo jeder Lernpfad steht, was heute und in den kommenden Wochen fällig wird. Use when the user asks "wo stehe ich", "was ist fällig", "gib mir eine Übersicht", or wants a shareable status page, and when a session-start upstream-sync notice needs no separate command.
argument-hint: (keine Argumente)
---

# /engram-status — Standortbestimmung

Kein Upstream-Pendant (wie `/engram-source`) — dieser Skill ist vollständig
Cloud-Fork-eigen. Er ersetzt **nicht** `/engram-coach dashboard`: Coach ist Telemetrie,
Strategie, Kalibrierung, Experimente, Tuning und das Engine-eigene
`engram.py report`-Dashboard (schreibt lokal nach `$ENGRAM_HOME/artifacts/dashboard.html`).
Status ist eine Momentaufnahme zur Orientierung — kennt zusätzlich die **Quellen** (die
Engine selbst hat keinen Quellenbegriff) und liefert einen teilbaren, handytauglichen
Link statt einer lokalen Datei.

**Zuerst die Umgebung laden — vor jedem Werkzeugaufruf.** Wörtlich derselbe Block wie in
den anderen Alias-Skills (bewusste Duplizierung — siehe `CLAUDE.md`, „Updates vom
Entwickler übernehmen"):

```bash
_env=""
for d in "${ENGRAM_ROOT:-}" "${CLAUDE_PROJECT_DIR:-}" "$PWD" \
         "$(git rev-parse --show-toplevel 2>/dev/null)" /home/user/engram "$HOME/engram"; do
  [ -n "$d" ] || continue
  [ -f "$d/scripts/engram.py" ] && [ -f "$d/.claude/hooks/engram-env.sh" ] || continue
  _env="$d/.claude/hooks/engram-env.sh"; break
done
if [ -z "$_env" ]; then
  echo "engram: Checkout nicht gefunden — ENGRAM_ROOT auf das engram-Verzeichnis setzen." >&2
else
  _hooks="${ENGRAM_HOOKS_ACTIVE:-}"
  . "$_env"
  [ -n "$_hooks" ] || echo "engram: WARNUNG — der Auto-Save-Hook läuft in dieser Session nicht." >&2
fi
echo "ENGRAM_ROOT=${ENGRAM_ROOT:-<leer>}  ENGRAM_HOME=${ENGRAM_HOME:-<leer>}"
```

Den echten State-Pfad danach immer aus `python3 "$ENGRAM_ROOT/scripts/engram.py" doctor`
(Feld `home`) bestätigen — nie `~/.claude/learning` annehmen.

## Daten einsammeln (alles lesend, keine Schreiboperation)

| Was | Woher |
|---|---|
| Themen, Titel, Ziel, Node-Zahl, Zustände, fällig | `engram.py topics` (JSON) |
| Streak, `due_now`, offene Misconceptions, `adherence.loop_closure` | `engram.py stats` (JSON) |
| heute Fälliges | `engram.py due` (JSON) |
| **Vorschau kommender Fälligkeiten** | `$ENGRAM_HOME/graphs/<topic>.json` direkt lesen, Feld `fsrs.due` je Node — `due` selbst kennt keinen Horizont-Schalter, nur „heute und früher" |
| Quellen | `$ENGRAM_STATE/sources/<slug>/source.json` (Titel, Seiten, Chunks, sha256), `sources/MAP.md` (Thema↔Quelle), `sources_raw/` auflisten (welche Originale den Container überleben) |

```bash
python3 "$ENGRAM_ROOT/scripts/engram.py" topics
python3 "$ENGRAM_ROOT/scripts/engram.py" stats
python3 "$ENGRAM_ROOT/scripts/engram.py" due
```

Für die Vorschau jeden Graphen einlesen und `nodes[*].fsrs.due` gegen heute + N Tage
prüfen (dasselbe Prinzip wie `engram.py report`s „Nächste 7 Tage"-Leiste, nur ohne die
Engine erneut aufzurufen). Für Quellen `sources/MAP.md` lesen und mit
`ls "$ENGRAM_STATE/sources_raw"` abgleichen, welche Originale noch bereitstehen.

## Vertraulichkeit — harte Grenze

**Nur Metadaten auf die Seite.** Titel, Seitenzahl, Chunkzahl, Themenname, Fortschritt,
Fälligkeitsdatum sind unbedenklich. **Niemals**: Chunk-Text, wörtliche Zitate aus einem
Buch, Freitext-Antworten des Lernenden, Misconception-Wortlaut. `engram-source/SKILL.md`
verbietet Buch-Derivate in einer Artifact-Seite ausdrücklich — das gilt hier identisch,
weil eine Artifact-URL potenziell teilbar ist und das State-Repo privat ist.

## Seite bauen

**Vor dem Schreiben den `artifact-design`-Skill laden** (Pflicht, wie bei jedem
Artifact). Publizieren mit dem `Artifact`-Tool, `favicon` z. B. 📊.

Anforderungen an die Seite:

- **Handy zuerst.** Karten statt breiter Tabellen; jede breite Tabelle/jeder Code in
  `overflow-x: auto`; die Seite selbst darf nie horizontal scrollen.
- **Theme-aware** (hell/dunkel), wie in `artifact-design` vorgegeben.
- Vier Abschnitte:
  1. **Quellen** — pro Quelle: Titel, Seitenzahl, Chunkzahl, welche(s) Thema/Themen sie
     speist (aus `MAP.md`), ob das Original in `sources_raw/` liegt.
  2. **Lernpfade** — pro Thema: Fortschrittsbalken (behalten/im Lernen/unberührt),
     Lernziel, Node-Zahl.
  3. **Fällig & Vorschau** — heute fällig, dann kommende Wochen (aus `fsrs.due`).
  4. **Auffälligkeiten** — offene Misconceptions, `adherence.loop_closure` falls die
     Schleife nie geschlossen wurde, abgelaufene Ziele (`goals` mit vergangenem Datum
     im `learner-model.json`).
- Am Ende dem Nutzer den Artifact-Link geben plus einen Satz, was als Nächstes fällig
  wird.

Kein zusätzlicher Commit nötig — die Seite liest nur; der Stop-Hook committet wie immer
etwaige Engine-Nebenwirkungen (i. d. R. keine, da nur lesende Kommandos liefen).
