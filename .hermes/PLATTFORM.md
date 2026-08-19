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
| **Pfade nie raten** — der echte Pfad steht in `engram.py doctor`, Feld `home`.

## 7 · Windows-Spezifika (gemessen am 2026-08-20)

Diese Host-Eigenheiten sind keine Hermes-Abweichungen — sie betreffen jede
Git-Bash-Umgebung auf Windows (MSYS2 / Git for Windows), in der Engram-Hooks
laufen. Sie stehen hier, nicht in `.claude/PLATTFORM.md`, weil Claude Code in
der Cloud auf Linux-Containern läuft und sie dort nie trifft. **Wer das Setup
auf einer anderen Windows-Maschine wiederholt, sollte diese drei Punkte zuerst
lesen** — sie sind genau das, was eine scheinbar korrekte Verdrahtung in
„funktioniert, schreibt aber nichts" verwandelt.

### 7.1 · `python3` zeigt auf den Microsoft-Store-Hinweis

Auf diesem Host zeigt der `python3`-Stub in
`/c/Users/.../WindowsApps/python3` auf den Store-Hinweis statt auf eine echte
Installation. Jeder `python3`-Aufruf aus einem Hook (und davon gibt es viele)
scheitert mit Exit 49, und die Hook-Skripte fallen auf ihren `|| exit 0`-Pfad
mit `{}` auf stdout zurück — **lautloser No-Op**.

`python` (ohne die 3) ist die echte Installation unter
`C:/Python311/python.exe` und funktioniert.

**Workaround:** Ein Wrapper unter `/c/Users/<DU>/bin/python3` (im `PATH` **vor**
dem WindowsApps-Stub), der die echte Python-Installation aufruft. Der genaue
Pfad ist egal — `py -3` löst ihn auf diesem Host zu `C:\Python313\python.exe`
auf, auf anderen Maschinen zu `C:\Python311\python.exe` oder
`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`:

```bash
_py="$(py -3 -c 'import sys; print(sys.executable)' 2>/dev/null \
      || echo 'C:/Python311/python.exe')"
cat > /c/Users/<DU>/bin/python3 <<SH
#!/usr/bin/env bash
exec "$_py" "\$@"
SH
chmod +x /c/Users/<DU>/bin/python3
```

**Verifikation:** `python3 --version` muss eine echte Python-Version
ausgeben, nicht die Microsoft-Store-Meldung. Dann
`python3 "$ENGRAM_ROOT/scripts/engram.py" selftest` — muss `N/N` bestehen.

### 7.2 · `pwd` liefert MSYS-Pfade, `git -C` versteht sie nicht

In MSYS-Bash normalisiert `cd … && pwd` jeden Pfad nach `/c/Users/...`. `git -C
/c/Users/...` schlägt aber mit Exit 128 fehl („No such file or directory") —
`git -C` bekommt keine MSYS-Pfadkonversion. Die Folge: `engram-env.sh` setzt
`ENGRAM_STATE=/c/Users/...`, jeder `git -C "$ENGRAM_STATE"`-Aufruf im Hook
scheitert, der State-Sync meldet „kein Git-Repo", `doctor` zeigt einen
„kein Git-Repo"-Hinweis, und der Auto-Save schreibt nichts.

**Patch in `.hermes/hooks/engram-env.sh`** — zwei Stellen, an denen
`CDPATH= cd -- "$_x" 2>/dev/null && pwd` steht (Z. 36, 43, 72 in der
Upstream-Fassung), ersetzen durch `cygpath -w "$_x"`. `cygpath` ist in jeder
MSYS-Installation vorhanden und konvertiert sowohl `C:/...` als auch `/c/...`
zuverlässig nach `C:\...`, mit dem `git -C` und `engram.py` problemlos
arbeiten.

**Bewusst NICHT angefasst:** `.claude/hooks/engram-env.sh` hat denselben Bug
auf Windows, wird aber von Claude-Code-Cloudsessions gebraucht (die laufen
unter Linux und sehen den Bug nie). Eine Änderung dort wäre eine
Cloud-Container-Modifikation und gehört in deren Setup-Pfad.

### 7.3 · Bootstrap zeigt `C:\…\engram-learning/learning`

Aus der Kombination von 7.2 (`cygpath -w` für `ENGRAM_STATE`) und dem
Resolver-Anhängsel `/learning` entsteht das gemischte Format
`C:\Users\andre\engram-learning/learning`. Funktional unbedenklich — `engram.py
doctor` akzeptiert es, `os.path.join` macht daraus überall den gleichen Pfad.
Wenn es stört, hilft ein `cygpath -w "$ENGRAM_STATE/learning"` direkt vor dem
`export ENGRAM_HOME`.

### 7.4 · Erkennung: drei Symptome, eine Ursache

Wenn beim ersten `/engram-status` **alle drei** dieser Meldungen gleichzeitig
auftauchen, ist es 7.1 + 7.2:

1. Bootstrap meldet `ENGRAM_HOME=<leer>` oder „Checkout nicht gefunden" — die
   Hook-Resolver-Kette ist gescheitert.
2. `engram.py doctor` zeigt `"home": "/c/Users/..."` statt `"home":
   "C:\\Users\\..."`, oder `"writable": false`.
3. Im State-Repo-Log taucht nach einer Lern-Session kein `engram (hermes):`-Commit
   auf, obwohl die Engine schreiben hätte müssen.

Beheben in dieser Reihenfolge: 7.1 (Wrapper), 7.2 (Patches), 7.3 (kosmetisch).
