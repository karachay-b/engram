# Claude Code → Hermes: die bindenden Übersetzungen

Diese Datei wird von allen fünf `engram-*`-Skills unter `.hermes/skills/` gelesen,
direkt nach dem Bootstrap. Sie ist **bindend**, nicht erläuternd.

## Warum es sie gibt

Die Regeln dieses Forks — das Interessen-Gate, der Quellen-Spawn-Baustein, der
Recherche-Baustein mit seinen Belegstufen, die Shell-Sicherheitsregel — stehen
**einmal**, unter `.claude/skills/engram-*/SKILL.md`. Die Hermes-Skills kopieren sie
nicht, sie lesen sie. Eine zweite Fassung derselben Regeln liefe innerhalb weniger
Wochen auseinander, und die stillere der beiden Fassungen gewänne.

Dupliziert ist deshalb nur, was dupliziert sein **muss**: der Bootstrap-Block (er ist
genau das Stück Code, das den gemeinsamen Ort erst findet, und die beiden Plattformen
finden ihn verschieden) und die `description`-Zeilen im Frontmatter (der Skill-Index
liest sie, bevor irgendetwas anderes läuft).

## Die Lesekette

1. `.hermes/skills/engram-<x>/SKILL.md` — Bootstrap, dann hierher.
2. `$ENGRAM_ROOT/.claude/skills/engram-<x>/SKILL.md` — die Regeln des Forks.
   **Vollständig lesen, wörtlich befolgen**, mit den Übersetzungen unten.
3. Was jene Datei ihrerseits verlangt: bei `learn`/`review`/`coach` der unveränderte
   Upstream-Skill unter `$ENGRAM_ROOT/skills/<x>/SKILL.md`, ebenfalls vollständig.
   `engram-source` und `engram-status` haben kein Upstream-Pendant und enden bei 2.

## Die Übersetzungen

### 1 · Der Bootstrap-Block in Datei 2 ist bereits erledigt

Die Claude-Fassung beginnt mit einem eigenen Bootstrap-Block, der
`.claude/hooks/engram-env.sh` sucht. **Diesen Block nicht ausführen** — der
Hermes-Bootstrap hat `ENGRAM_ROOT` und `ENGRAM_HOME` bereits gesetzt, und beide
Resolver liefern dasselbe Ergebnis. Alles danach gilt unverändert.

Ebenso: `$CLAUDE_PROJECT_DIR` existiert auf Hermes nicht. Es kommt außerhalb der
Bootstrap-Blöcke nicht vor; taucht es doch auf, ist `$ENGRAM_ROOT` gemeint.

### 2 · `ENGRAM_HOOKS_ACTIVE` → Marker-Datei

Die Claude-Fassung prüft die Variable `ENGRAM_HOOKS_ACTIVE`, um zu erkennen, ob der
Auto-Save läuft. Auf Hermes gibt es sie nicht: **ein Hook kann hier keine Variable in
die Shell des Agenten exportieren.** An ihre Stelle tritt die mtime von
`${HERMES_HOME:-$HOME/.hermes}/.engram-hooks-active`, gesetzt von
`.hermes/hooks/session-start.sh`. Der Hermes-Bootstrap prüft das bereits und warnt,
wenn der Marker fehlt oder älter als 12 Stunden ist.

Warnt er: am Ende der Session einmal von Hand
`bash "$ENGRAM_ROOT/.hermes/hooks/engram-save.sh"` ausführen.

### 3 · Subagent-Spawn → `delegate_task`

Überall, wo Datei 2 oder 3 „spawne **engram-curriculum-architect** / **engram-assessor**
/ **engram-artifact-smith**" sagt, gilt auf Hermes:

```
delegate_task(
  goal:    "<die Rolle in einem Satz, z. B. 'Bewerte diese Produktionen als engram-assessor.'>",
  context: "<vollständiger Inhalt von $ENGRAM_ROOT/agents/engram-<rolle>.md>

             ENGRAM_ROOT=<Pfad aus dem Bootstrap>
             ENGRAM_HOME=<Pfad aus dem Bootstrap>   # vor jedem engram.py-Aufruf setzen

             <der jeweilige Baustein aus Datei 2 — Quellen oder Recherche>
             <die Aufgabe: Item, Rubrik, Stash-Datei, …>"
)
```

Drei Punkte daran sind nicht verhandelbar:

- **Die Rollendatei kommt als Text mit, nicht als Pfad allein.** Hermes registriert
  keine Agent-Definitionen; das Kind kennt nur, was im `context` steht. (Ein Pfad
  zusätzlich schadet nicht — der Text ersetzt ihn aber nicht.)
- **`ENGRAM_ROOT` und `ENGRAM_HOME` stehen wörtlich als Text im Prompt.** Das Kind
  bekommt eine **eigene Terminal-Session** und erbt weder Variablen noch
  Arbeitsverzeichnis. Gemessen am 2026-08-03 in Claude Code: Der Artifact-Smith fand
  die Engine ausschließlich über den Pfad aus seinem Prompt — ohne ihn wäre
  `artifact set` in ein flüchtiges Verzeichnis gelaufen, mit `ok` in der Ausgabe und
  der Registrierung am falschen Ort. Auf Hermes ist die Isolation stärker, das Risiko
  also größer, nicht kleiner.
- **Die Blindheit des Assessors bleibt.** Nichts aus dem Tutoring-Dialog gehört in
  seinen `context` — nur Item, Rubrik und die Worte des Lernenden. `delegate_task`
  startet Kinder mit frischem Kontext; diese Eigenschaft ist der Grund, warum die
  Receipts überhaupt etwas wert sind. Sie wird hier nicht aus Bequemlichkeit
  aufgeweicht.

Upstream beschreibt in `$ENGRAM_ROOT/skills/_shared/subagents.md` dieselbe Konstruktion
für Plattformen ohne registrierte Agents (OpenClaw, Pi, DSH) — **eine Hermes-Sektion
hat die Datei noch nicht**, dieser Abschnitt hier ist sie. Der Abschnitt „Rules that do
not bend" dort gilt unverändert.

### 4 · Freitext erreicht die Engine über Dateien — auch ohne „Write-Tool"

Datei 2 und 3 sagen „mit dem Write-Tool schreiben". Gemeint ist die Regel, nicht das
Werkzeug: **Lernertext, Buchtext, Zitate und URLs gehen nie auf die Kommandozeile.**
Auf Hermes ist der Weg dorthin das Datei-Schreibwerkzeug oder ein Heredoc im Terminal:

```bash
cat > /tmp/engram-production.json <<'JSON'
{ … }
JSON
python3 "$ENGRAM" rate --file /tmp/engram-production.json
```

Das Heredoc mit **quotiertem** Delimiter (`<<'JSON'`) ist der Punkt: Ohne die
Anführungszeichen expandiert die Shell `$(…)` im Text des Lernenden. Genau davor
schützt die Regel.

### 5 · `/engram-status`: kein Artifact-Weg

Die Claude-Fassung kann die Statusseite als geteilte Artifact-Seite publizieren. **Auf
Hermes gibt es das nicht.** Zwei Ausgabewege bleiben:

- **Text** — der Normalfall, unverändert.
- **Lokale HTML-Datei** unter `$ENGRAM_HOME/artifacts/status-<datum>.html`, dem
  Nutzer als Pfad genannt. Kein Link, keine Teilbarkeit — und genau deshalb auch
  keine der Vertraulichkeitsfragen, die eine teilbare URL aufwirft.

Die Vertraulichkeitsgrenze gilt trotzdem wörtlich weiter: `probe`, `claim`, `rubric`
und `transfer_probe` gehören in **keine** Ausgabe, auch nicht in eine lokale Datei.
Eine Datei, die auf der Platte liegt, wird irgendwann verschickt.

Dasselbe für den **engram-artifact-smith**: Der baut ohnehin eine lokale HTML-Datei und
registriert sie mit `engram.py artifact set` — das ist plattformneutral und ändert sich
auf Hermes nicht.

### 6 · Jede Terminal-Zelle ist eine neue Shell

Gilt auf Hermes wie in Claude Code: **Bootstrap und Werkzeugaufruf gehören in denselben
Block.** Ein Bootstrap in einer eigenen Zelle ist im nächsten Aufruf wirkungslos —
`$ENGRAM_ROOT` kommt dort leer an. Auf Hermes federt `~/.hermes/.env` das meist ab, aber
verlassen darf sich nichts darauf: `.env` kann fehlen, veraltet sein oder auf ein
anderes Checkout zeigen.

## Was auf Hermes NICHT anders ist

Damit die Liste oben nicht als Freibrief gelesen wird — unverändert gültig sind:

- das **Pflicht-Gate Interessen** vor jedem Architect-Spawn,
- der **Quellen-Spawn-Baustein** samt „die Struktur kommt rückwärts vom Ziel",
- der **Recherche-Baustein** mit Budget (6 Aufrufe) und den Belegstufen A/B,
- die **Dialog-Grammatik** und die Trennung der Gewalten beim Bewerten,
- **Quellen-Derivate bleiben privat** — nichts davon in den öffentlichen Fork,
- **Pfade nie raten** — der echte Pfad steht in `engram.py doctor`, Feld `home`.
