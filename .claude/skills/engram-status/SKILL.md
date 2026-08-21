---
name: engram-status
description: Momentaufnahme des Lernstands — Text sofort, optional als geteilte Seite. Welche Quellen eingebunden sind, wo jeder Lernpfad steht, was heute und in den kommenden Wochen fällig wird. Use when the user asks "wo stehe ich", "was ist fällig", "gib mir eine Übersicht", or wants a shareable status page, and when a session-start upstream-sync notice needs no separate command.
argument-hint: [text|kurz | seite|artefakt]
---

# /engram-status — Standortbestimmung

Kein Upstream-Pendant (wie `/engram-source`) — dieser Skill ist vollständig
Cloud-Fork-eigen. Er ersetzt **nicht** `/engram-coach dashboard`: Coach ist Telemetrie,
Strategie, Kalibrierung, Experimente, Tuning und das Engine-eigene
`engram.py report`-Dashboard (schreibt lokal nach `$ENGRAM_HOME/artifacts/dashboard.html`).
Status ist eine Momentaufnahme zur Orientierung — kennt zusätzlich die **Quellen** (die
Engine selbst hat keinen Quellenbegriff) und liefert wahlweise Text sofort oder einen
teilbaren, handytauglichen Link statt einer lokalen Datei.

## Jede Bash-Zelle startet eine neue Shell

**Bootstrap und Werkzeugaufruf gehören in denselben Block.** Ein Bootstrap in einer
eigenen Zelle ist im nächsten Aufruf wirkungslos — `$ENGRAM_ROOT` kommt dort leer an,
und der Werkzeugaufruf scheitert. (Genau das ist beim ersten Lauf dieses Skills passiert
und hat mehrere Runden gekostet.) Beide Schritte deshalb **immer in einem Block**:

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
python3 "$ENGRAM_ROOT/.claude/tools/engram_status.py" --text
```

Das genügt für den Normalfall: **ein** Bash-Aufruf, sofort lesbare Zahlen. Das Werkzeug
löst den State-Pfad selbst noch einmal auf (dieselbe Kette wie `engram-env.sh`, siehe
`engram_status.py`s `resolve_state`-Import aus `engram_source.py`) — der Bootstrap-Block
oben ist trotzdem Pflicht, weil er `ENGRAM_HOOKS_ACTIVE` prüft und die Alias-Skills
einheitlich hält (bewusste Duplizierung — siehe `CLAUDE.md`, „Updates vom Entwickler
übernehmen").

Argument `text`/`kurz` beim Skill-Aufruf: hier aufhören, nichts weiter tun.
Argument `seite`/`artefakt`: direkt zu „Seite bauen" unten, ohne zu fragen.
Ohne Argument: nach der Textausgabe fragen, ob eine Seite daraus werden soll.

## Warum ein eigenes Werkzeug statt einzelner `engram.py`-Aufrufe

`.claude/tools/engram_status.py` bündelt `topics`, `stats`, `due`, die
Fälligkeits-Vorschau (aus den Graph-Dateien — `due` selbst kennt keinen
Horizont-Schalter, nur „heute und früher") und die Quellen-Metadaten in **einem**
Aufruf. Das ist nicht nur schneller: `engram.py due` liefert `probe`, `claim`, `rubric`
und `transfer_probe` im Volltext — genau das Material aus dem nächsten Abschnitt. Das
Werkzeug lässt diese Felder gar nicht erst in seine Ausgabe (`build_due_entry()` kopiert
eine feste Erlaubnisliste; `selftest` prüft das). Wer stattdessen einzelne
`engram.py`-Kommandos aufruft, holt sich den Prüfungsinhalt zurück in den Kontext, bevor
noch irgendeine Regel greifen kann.

`--horizon N` (Vorgabe 30 Tage) ändert das Vorschau-Fenster. `python3
"$ENGRAM_ROOT/.claude/tools/engram_status.py" selftest` prüft das Werkzeug selbst — u. a.
genau die Vertraulichkeitsgrenze — und läuft, wie `engram_source.py selftest`, nicht in
`.github/workflows/test.yml` (Upstream-Datei, würde beim nächsten Merge kollidieren).

## Vertraulichkeit — harte Grenze

**Nur Metadaten auf die Seite.** Titel, Seitenzahl, Chunkzahl, Themenname, Fortschritt,
Fälligkeitsdatum sind unbedenklich. **Niemals**: Chunk-Text, wörtliche Zitate aus einem
Buch, Freitext-Antworten des Lernenden, Misconception-Wortlaut. Das Werkzeug hält
Probe/Claim/Rubrik/Transferitem strukturell aus der Ausgabe heraus; das `goal`-Feld
(Freitext des Lernenden, potenziell mit Namen oder Termine Dritter) kürzt es ebenso per
Code auf ~120 Zeichen (`shorten_goal()`/`GOAL_MAX_CHARS` in `engram_status.py`) — nicht
erst auf Modell-Disziplin verlassen. `engram-source/SKILL.md` verbietet Buch-Derivate in
einer Artifact-Seite ausdrücklich — das gilt hier identisch, weil eine Artifact-URL
potenziell teilbar ist und das State-Repo privat ist.

## Seite bauen

Nur wenn gewünscht (siehe oben). Denselben Bootstrap-Block noch einmal ausführen, diesmal
ohne `--text` (liefert JSON):

```bash
python3 "$ENGRAM_ROOT/.claude/tools/engram_status.py" > "$ENGRAM_STATUS_TMP"
```

(`$ENGRAM_STATUS_TMP` = eine temporäre Datei im Scratchpad-Verzeichnis der Session,
nicht `/tmp` — das entspricht der Umgebungskonvention für Cloud-Sessions.)

**Vor dem Schreiben den `artifact-design`-Skill laden** (Pflicht, wie bei jedem
Artifact). Publizieren mit dem `Artifact`-Tool, `favicon` z. B. 🧭. Ohne vorherige
Suche nach einer bestehenden Seite neu veröffentlichen — das ist hier bewusst schneller
als eine bestehende URL zu suchen und zu aktualisieren.

Anforderungen an die Seite:

- **Handy zuerst.** Karten statt breiter Tabellen; jede breite Tabelle/jeder Code in
  `overflow-x: auto`; die Seite selbst darf nie horizontal scrollen.
- **Theme-aware** (hell/dunkel), wie in `artifact-design` vorgegeben.
- Vier Abschnitte, direkt aus den JSON-Schlüsseln:
  1. **Quellen** (`sources[]`) — Titel, Seitenzahl, Chunkzahl, speist welche(s) Thema/
     Themen, ob das Original gesichert ist (`raw_available`).
  2. **Lernpfade** (`topics[]`) — Fortschrittsbalken aus `states`, Lernziel gekürzt,
     Node-Zahl.
  3. **Fällig & Vorschau** (`due[]`, `forecast[]`) — `recall_pct` ist schon die echte
     FSRS-Erinnerungsstärke, nicht selbst nachrechnen.
  4. **Auffälligkeiten** (`flags`) — `loop_never_closed`, `open_misconceptions` (nur die
     Zahl aus `flags.open_misconceptions`, nie ein Wortlaut), `goal_date_passed`,
     `commitment_stale`, `grader_unaudited`.
- Am Ende dem Nutzer den Artifact-Link geben plus einen Satz, was als Nächstes fällig
  wird.

Kein zusätzlicher Commit nötig — sowohl Textmodus als auch Seitenbau lesen nur; der
Stop-Hook committet wie immer etwaige Engine-Nebenwirkungen (i. d. R. keine, da nur
lesende Kommandos liefen).
