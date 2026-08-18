# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Engram — Cloud-Setup (Claude Code im Web)

Dieses Repo ist ein Fork von [nagisanzenin/engram](https://github.com/nagisanzenin/engram),
zusätzlich verdrahtet für die Nutzung in Claude Code on the web. Alles unter `.claude/`
und diese Datei gehören zum Cloud-Setup; alles andere ist unveränderter Upstream-Code.
Das folgende Kapitel „Upstream-Codebase" beschreibt diesen unveränderten Teil — die
eigentliche Lern-Engine hinter den drei Kommandos.

## Die Kommandos

| Hier | Upstream-Doku | Warum umbenannt |
|---|---|---|
| `/engram-learn <topic>` | `/learn` | `learn` kollidiert mit einem globalen Skill des Nutzers |
| `/engram-review` | `/review` | `review` kollidiert mit Claude Codes GitHub-PR-Review |
| `/engram-coach` | `/coach` | einheitliches Präfix |
| `/engram-source` | — | kein Upstream-Pendant; siehe „Quellen" unten |
| `/engram-status` | — | kein Upstream-Pendant; Momentaufnahme (Quellen, Lernpfad-Stand, Fälligkeiten) als geteilte Seite — siehe `.claude/skills/engram-status/SKILL.md`. Ersetzt nicht `/engram-coach dashboard` (Telemetrie/Tuning); ergänzt es um die Quellen-Sicht, die die Engine nicht kennt. |

`.claude/skills/engram-*/SKILL.md` sind dünne Aliase: sie enthalten nur Frontmatter
und die Anweisung, das echte `skills/<name>/SKILL.md` zu lesen und **wörtlich** zu
befolgen. Die Upstream-Skills bleiben unangetastet — deshalb kollidiert ein Update
nie. `engram-status` hat kein Upstream-Pendant und ist deshalb wie `engram-source`
vollständig selbst geschrieben, kein dünner Alias. Die Subagents unter `.claude/agents/`
sind Symlinks nach `agents/`.

## Lernstand: wo er liegt und warum er gepusht werden muss

Container in dieser Umgebung sind kurzlebig. Der Lernstand überlebt **nur**, wenn er
nach Git gepusht wird.

- `ENGRAM_HOME` = `<engram-learning-checkout>/learning`, gesetzt vom SessionStart-Hook.
  Die Variable kommt in der Bash-Umgebung von Cloud-Sessions nicht immer an — darum
  steht am Anfang jedes `engram-*`-Alias ein Bootstrap-Block, der das Checkout sucht
  und `.claude/hooks/engram-env.sh` sourct. Ohne ihn schreibt die Engine ins
  flüchtige `~/.claude/learning`. Den Block ausführen, nicht auf einen geratenen
  Pfad verkürzen.
- Das Repo `karachay-b/engram-learning` ist **privat** — es enthält Freitext-Antworten,
  Bewertungen und ein Misconception-Log. Es gehört niemals in diesen öffentlichen Fork.
- Den echten Pfad immer aus `python3 scripts/engram.py doctor` (Feld `home`) lesen.
  **Nie `~/.claude/learning` wörtlich ausgeben** — hier stimmt das nicht.

Der Stop-Hook (`.claude/hooks/engram-save.sh`) committet und pusht automatisch nach
jedem Turn. Meldet er einen fehlgeschlagenen Push, muss der Push manuell nachgeholt
werden, bevor die Session endet.

### Hooks laufen nicht in jeder Session

`.claude/settings.json` — und damit **beide** Hooks — wird nur geladen, wenn das
Projektverzeichnis der Session dieses Repo ist. Hängen `engram` und `engram-learning`
gemeinsam an einer Session, ist das Projektverzeichnis der gemeinsame Elternordner
(`/home/user`), und dann **feuert kein Engram-Hook**: kein `ENGRAM_HOME`, kein
Auto-Save. Repo-Roots liefern `CLAUDE.md`, Skills und Subagents — Hooks liefern sie
nicht.

Deshalb darf sich nichts darauf verlassen, dass ein Hook gelaufen ist:

- Der Bootstrap-Block der Alias-Skills setzt `ENGRAM_HOME` selbst und exportiert
  zusätzlich `ENGRAM_ROOT`, worauf der unveränderte Upstream-Resolver anspringt.
- Ob die Hooks registriert sind, erkennt er an `ENGRAM_HOOKS_ACTIVE`. Das setzt
  `session-start.sh` als Allererstes über `$CLAUDE_ENV_FILE`, noch vor jeder
  Auflösung — der Marker sagt also „ein Hook lief", nicht „ein Checkout wurde
  gefunden". Fehlt er, warnt der Block sichtbar, und dann gilt: am Ende der Session
  einmal `bash "$ENGRAM_ROOT/.claude/hooks/engram-save.sh"` von Hand ausführen.
  `ENGRAM_HOME` taugt als Signal **nicht** — der Bootstrap setzt es selbst, und es
  kann als schlichte Umgebungsvariable gesetzt sein; beides würde die Warnung genau
  dann verschlucken, wenn sie gebraucht wird.
- Dauerhaft behoben wird es nur außerhalb des Repos: Eine `~/.claude/settings.json`
  im Container wird unabhängig vom Projektverzeichnis gelesen, und dorthin
  geschrieben wird sie vom **Setup-Skript der Umgebung**. Die maßgebliche Fassung
  steht versioniert in `.claude/cloud-setup.sh` — sie wird vom Repo nicht
  ausgeführt, sondern auf claude.ai in das Feld „Setup script" kopiert
  (Umgebungs-Selektor über dem Eingabefeld → Zahnrad). Wirksam wird eine Änderung
  erst beim nächsten Aufbau des Umgebungs-Caches, also nicht in einer schon
  laufenden Session.

Der Repo-Hook bleibt trotzdem stehen: In Sessions, deren Projektverzeichnis
wirklich dieses Repo ist, greift er weiter, und er ist der einzige Weg, der ohne
die Cloud-Umgebung funktioniert — etwa lokal im Terminal. Feuern beide, ist das
harmlos; der zweite Lauf von `engram-save.sh` findet einen sauberen Baum.

**Dasselbe Problem trifft Subagents, und dort hilft kein Hook.** Architect, Assessor und
Artifact-Smith starten mit frischem Kontext in eigener Bash-Umgebung; der Resolver aus
`skills/learn/SKILL.md` greift dort ins Leere, sobald das Arbeitsverzeichnis der
Elternordner beider Checkouts ist. Deshalb verlangt der `engram-learn`-Alias, dass
`ENGRAM_ROOT` und `ENGRAM_HOME` in **jedem** Spawn-Prompt wörtlich als Text stehen.
Gemessen am 2026-08-03: Der Artifact-Smith fand die Engine nur über den Pfad aus seinem
Prompt — ohne ihn wäre `artifact set` ins flüchtige `~/.claude/learning` gelaufen, mit
`ok` in der Ausgabe und der Registrierung am falschen Ort.

### Wenn das State-Repo fehlt

Der SessionStart-Hook warnt sichtbar, wenn kein `engram-learning`-Checkout gefunden
wurde. Dann gilt für diese Session: **Lernstand ist flüchtig.** Behebung, in dieser
Reihenfolge:

1. Dauerhaft: `karachay-b/engram-learning` in den Umgebungs-Einstellungen auf
   claude.ai als zweite Quelle eintragen. Danach wird es bei jedem Container-Start
   automatisch geklont und ist push-berechtigt.
2. Für die laufende Session: `add_repo(owner="karachay-b", repo="engram-learning",
   access="push")` aufrufen, in `/home/user/engram-learning` klonen und
   `.claude/hooks/session-start.sh` erneut ausführen.

Der Suchpfad des Hooks: `$ENGRAM_STATE_REPO` → `<repo>/../engram-learning` →
`/home/user/engram-learning` → `$HOME/engram-learning`.

### Briefing und Upstream-Sync-Check beim Sessionstart

`session-start.sh` gibt vor der Fälligkeits-Nudge `.claude/ORIENTIERUNG.md` wörtlich
aus — ein kompaktes Briefing (beide Repos, ihre Verzahnung, die Kommandos, die drei
bindenden Regeln), gedacht als das, was jede Session verlässlich liest. Diese `CLAUDE.md`
bleibt das ausführliche Nachschlagewerk.

Nach der Nudge läuft `.claude/hooks/engram-sync-check.sh`: höchstens einmal pro Tag
(Cache unter `~/.cache/engram/upstream-check`) ein `git ls-remote` gegen
`nagisanzenin/engram`, ob `refs/heads/main` lokal bereits als Commit vorliegt
(`git cat-file -e <sha>^{commit}`, ohne `fetch`, ohne Remote anzulegen). Liegt er nicht
vor, meldet der Hook eine Zeile mit dem neuesten stabilen Tag (Release-Candidates wie
`-rc1` werden herausgefiltert). Jeder Netzwerkfehler bleibt still und schreibt den Cache
nicht — der nächste Sessionstart versucht es erneut. Stimmt der Nutzer der Meldung zu,
gilt die Prozedur aus „Updates vom Entwickler übernehmen" unten.

## Quellen: Bücher und PDFs als Lernstoff

Engram selbst kennt keine Quellen — die Engine speichert nur den Konzept-DAG und die
Receipts, das Node-Schema hat kein Zitatfeld. Das Quellen-System füllt diese Lücke,
ohne die Engine anzufassen.

- **Werkzeug:** `.claude/tools/engram_source.py`, getrieben von `/engram-source`.
  Ein PDF wird **einmal** deterministisch zerlegt: Manifest (`source.json`), ein
  kleines Kartenblatt (`index.md`) und Chunks von 400–1200 Wörtern mit
  `[S. n]`-Markern an jedem Seitenumbruch.
- **Ablage:** `<engram-learning>/sources/<slug>/` — neben `learning/`, nicht darin.
  `learning/` gehört der Engine; ein Fremdverzeichnis dort würde mit einer künftigen
  Upstream-Funktion kollidieren.
- **Originale bleiben draußen.** `sources/.gitignore` hält PDFs aus dem Git. Der
  `sha256` im Manifest ist der Wiedervorlage-Check (`engram-source verify`).
  **Dokumentierte Ausnahme:** `<engram-learning>/sources_raw/` liegt außerhalb von
  `sources/` und wird bewusst mitversioniert — dort abgelegte Original-PDFs
  überleben so den Container und stehen für `verify` und den Bild-Weg bei Scans
  wieder zur Verfügung. Befüllt wird das Verzeichnis manuell (z. B. per
  GitHub-Upload); der Stop-Hook committet es nicht. Das Repo ist privat — nur
  deshalb ist das vertretbar.
- **Nachschlagen statt laden:** Index lesen → `find` → 3–10 Chunks gezielt lesen.
  Kein Embedding-Index; bei ~40 Chunks pro Buch wäre er langsamer, undurchsichtig
  und müsste in jedem Container neu gebaut werden.
- **`kind` ist eine Leseempfehlung, kein Datum.** Das Etikett je Chunk steuert, was
  der Architect überspringt (`exercise`, `toc-like`) und was er zuerst liest
  (`definition`, `example`) — die erste Klasse löscht bei einem Fehltreffer Inhalt,
  die zweite kostet nur einen Platz im 10er-Budget. Deshalb ist sie schärfer
  eingestellt. Die Marker sind an deutscher Fachprosa gemessen; ein Text ohne
  ausgezeichnete Definitionen läuft auf `prose`, und `add`/`reclassify` sagen das
  in echter Werkzeugausgabe, statt es stillschweigend hinzunehmen.
  `reclassify <slug>` zieht eine schon ingestete Quelle nach, wenn die Heuristik
  sich geändert hat — **ohne das PDF**, das hier ohnehin meist fehlt, und ohne
  Chunk-IDs, Bodies oder Seitenmarker anzufassen; `MAP.md` bleibt gültig.
- **Verbindung zum Lernstand:** `sources/MAP.md` (via `engram-source map-add`).
  Das ist die einzige dauerhafte Zuordnung Thema ↔ Quelle — und eine **Chronik der
  Herkunft, keine Live-Ansicht**: Die Engine kennt die Tabelle nicht und fasst sie
  nie an. Ein retirtes Thema behält seine Zeile (`retire` ist reversibel und löscht
  nichts); eine falsch gewordene Zeile wird mit `map-remove` bzw.
  `map-add --replace` gerichtet, ein zweites Thema aus derselben Quelle ist schlicht
  eine weitere Zeile. `map-check` gleicht die Tabelle gegen Engine und `sources/` ab
  und meldet nur Zeilen, die ins Leere zeigen — ein Thema **ohne** Zeile ist kein
  Befund, denn ohne Buch gebaute Themen haben keine Quelle.

**Die Rolle des Buchs ist Inhalt, nicht Gliederung.** Der Curriculum-Architect nennt
Kapitel-Kopieren seinen kardinalen Fehler; der Spawn-Baustein im `engram-learn`-Alias
stellt das scharf.

**Interessen sind Vorbedingung, nicht Kür.** Der Quellen-Pfad verschluckt die
Intake-Frage nach den Interessen des Lernenden besonders leicht: Ingest, Index und
Seitenmarker verbrauchen genau das Aufmerksamkeitsbudget, in dem sie gestellt werden
müsste, und ein leeres `interests` scheitert still — der Architect baut klaglos
`analogous_to: []`. Deshalb steht das Gate im `engram-learn`-Alias
(`## Pflicht-Gate vor dem Architect-Spawn`), und `engram_source.py` sowie der
SessionStart-Hook melden ein leeres Feld in echter Werkzeugausgabe.

Beides sind die **bewussten Kopplungen an Upstream**: Ändert der Upstream die
Rollenbeschreibung des Architects grundlegend oder Intake-Schritt 3 / das
`--add-interest`-Flag, müssen Spawn-Baustein und Gate nachgezogen werden —
dieselbe Klasse von Duplizierung wie die `description`-Zeilen der Alias-Skills.

### Ohne Buch: der Recherche-Pfad

Der Normalfall ist quellenlos — der Stoff kommt aus dem Modellwissen des Architects.
Dafür steht im `engram-learn`-Alias ein zweiter Spawn-Baustein
(`## Recherche — wenn keine Quelle genannt wurde`), der **nicht** das ganze Thema
recherchiert, sondern drei Node-Klassen belegt: `arbitrary`/`fact` (nicht ableitbar),
`threshold` (Fehler vergiften alles danach) und den `error_bank`-Katalog. Budget:
höchstens 6 Netzwerkaufrufe, Verbrauch wird zurückgemeldet. Ableitbare `concept`-Nodes
bleiben unbelegt — die Ableitung ist die Prüfung; ein ableitbarer `threshold`-Node auch,
dann aber ausdrücklich vermerkt.

Drei Entscheidungen, die dahinter stehen:

- **Zwei Belegstufen, ehrlich getrennt.** `A` = Volltext abgerufen, wörtlich zitiert —
  nur das ist ein Nachweis. `B` = Suchergebnis-Snippet, Seite nicht abrufbar; wird
  protokolliert und zählt **nirgends** als geprüft. Literaturangaben aus dem Gedächtnis
  sind in beiden Stufen verboten: die gemessenen Raten erfundener Zitate liegen über
  ausgelieferte Modelle bei 11–57 %, und ein erfundener Beleg ist schlechter als keiner,
  weil er Prüfbarkeit vortäuscht. Die Stufe B existiert, weil der erste reale Lauf
  (2026-08-03) auf 3 von 3 Fundstellen HTTP 403 bekam — der Agent-Proxy dieser Umgebung
  blockt viele Hosts, und eine Regel mit nur einem erlaubten Ausgang wird dann entweder
  gebrochen oder liefert nichts.
- **Nachgelagert, nie davor.** Der Architect läuft gemessen ~7 Minuten still, und das
  ist laut Upstream-Skill der wahrscheinlichste Abbruchmoment. Ein Budget ohne Deckel
  würde genau die Stelle verlängern, die am wenigsten trägt. Mit Deckel gemessen:
  6 Nodes inklusive Recherche in 5,5 Minuten.
- **Ablage neben dem Graphen**, nicht darin: `sources/RESEARCH/<topic>.md`, geschrieben
  mit dem Write-Tool. Der Architect liefert die Belege unter dem Top-Level-Schlüssel
  `research`; der wird **vor** `add-topic` aus dem Payload genommen. `list` und
  `map-check` zählen nur Verzeichnisse mit `source.json` und sehen `RESEARCH/` nicht —
  insbesondere bleibt „ein Thema ohne `MAP.md`-Zeile ist kein Befund" unverändert wahr.

Einen automatischen Prüflauf gibt es bewusst nicht. Der Beleg leistet Auffindbarkeit:
Wird ein `claim` strittig, steht die Stelle da. Ein Verifier wäre bei ≤20 Nodes teurer
als der Schaden — und bei solchen Prüfern entscheidet die Falsch-Alarm-Rate über die
Brauchbarkeit, nicht die Trefferquote.

**Korrektur einer Begründung, die hier falsch stand:** Das Node-Schema bekommt kein
Quellenfeld — aber nicht, weil die Engine es verwürfe. Nachgemessen nimmt `add-topic`
unbekannte Felder klaglos an (`doctor` ok, Node-Felder überleben `--extend`). Der
tragende Grund ist, dass Durchreichen keine Zusage ist: Upstream belegt `source` schon
im Receipt-Schema und kann den Namen jederzeit am Node belegen — dann kollidiert es
still, mit Lerndaten daran.

Der Stop-Hook committet `sources/` zusammen mit `learning/`. Rechtlich gilt: Die
Derivate eines geschützten Buchs sind ebenso geschützt — sie gehören ins private
Repo und niemals in diesen öffentlichen Fork.

## Sicherheitsregel aus dem Upstream — gilt unverändert

**Niemals Lernertext auf die Kommandozeile.** Freitext (Antworten, Lernziele) erreicht
die Engine nur über eine Datei oder stdin: JSON mit dem Write-Tool schreiben und
`--file` übergeben, oder nach `--json -` / `--production-file -` pipen. Ein `'` oder
`$(…)` in einer Antwort wäre sonst eine Command-Injection.

## Updates vom Entwickler übernehmen

Der Lernstand liegt in einem anderen Repo, und das Cloud-Setup benutzt ausschließlich
Pfade, die es upstream nicht gibt (`.claude/`, `CLAUDE.md`). Ein Update kann deshalb
weder Lerndaten überschreiben noch Konflikte auslösen.

```bash
git remote add upstream https://github.com/nagisanzenin/engram.git   # einmalig
git fetch upstream
git merge upstream/main
python3 scripts/engram.py selftest    # muss 315/315 (oder mehr) bestehen
```

Alternativ der "Sync fork"-Button auf GitHub. Nach jedem Update den Selftest laufen
lassen — er ist die Gegenprobe, dass die Engine intakt ist.

Ändert Upstream die Namen oder Frontmatter-Beschreibungen der Skills, müssen die
`description`-Zeilen in `.claude/skills/engram-*/SKILL.md` nachgezogen werden.

Zweite bewusste Duplizierung: der **Bootstrap-Block** steht wörtlich in allen fünf
Alias-/Cloud-Skills (`engram-learn`, `engram-review`, `engram-coach`, `engram-source`,
`engram-status`). Ein gemeinsamer Ort ginge nicht — der Block ist genau das Stück Code,
das den gemeinsamen Ort erst findet. Upstream duplizert seinen eigenen Resolver aus
demselben Grund über `skills/{learn,review,coach}/SKILL.md`. Wer den Block ändert,
ändert ihn viermal.

## Upstream-Codebase: die Lern-Engine

Der Teil des Repos, den der Fork nicht anfasst. Engram ist ein Multi-Platform-Plugin
(Claude Code, OpenAI Codex, OpenCode v1/2.0, Hermes, Antigravity, OpenClaw, Pi, DSH) —
`.claude-plugin/`, `.codex-plugin/`, `.opencode-plugin/`, `dsh/`, `pi/` sind je ein
Adapter auf denselben drei Kommandos und denselben Zustand. In dieser Umgebung zählt
nur der Claude-Code-Pfad.

### Architektur in einem Satz

Deterministischer Python-Kern (`scripts/engram.py`, stdlib-only, FSRS-4.5-Scheduler +
State-Machine + Receipts) unter drei Markdown-Skills (`skills/{learn,review,coach}/`),
die die eigentliche Tutor-Konversation im Hauptkontext führen; drei Subagents
(`agents/engram-{curriculum-architect,assessor,artifact-smith}.md`) übernehmen genau
die Schritte, die frischen/blinden Kontext brauchen. Details, Diagramme und die
Design-Begründung stehen in `docs/03-architecture.md` (Pflichtlektüre vor Änderungen
an Skills, Agents oder dem State-Schema) — hier nur, was zum Navigieren reicht:

- **Der Tutor ist kein Subagent.** `/learn`- und `/review`-Dialoge laufen im Hauptchat
  unter der Dialog-Grammatik aus `skills/_shared/dialogue-grammar.md`, weil die
  Lernbeziehung Kontext über die Session hinweg braucht.
- **Grading ist getrennte Gewalt.** Bei Erstbegegnung (Encoding in `/learn`) grade nie
  der Tutor selbst — die Produktion geht blind an `engram-assessor`, der nur Item,
  Rubrik und die Worte des Lernenden sieht, nie den Dialog. Bei `/review` grade der
  Tutor selbst (Zwei-Minuten-Budget verträgt keinen Subagent-Umweg), mit Stichproben-Audit.
- **Zustand ist reiner JSON-Dateibaum**, global unter `~/.claude/learning/` (in diesem
  Fork umgeleitet nach `<engram-learning-checkout>/learning`, siehe oben):
  `learner-model.json` (offenes Lernermodell), `graphs/<topic>.json` (Konzept-DAG mit
  FSRS-State pro Node), `receipts/<topic>.jsonl` (append-only Prüfnachweise),
  `misconceptions.json`, `sessions.jsonl`, `experiments.json`.
- **`scripts/engram.py`** (~12.900 Zeilen, eine Datei, keine Dependencies) ist die
  einzige Stelle, die den State-Baum anfasst — FSRS-Mathematik, Schema-Migration und
  Validierung laufen als Code, nie als LLM-Arithmetik. Wichtigste Subcommands:
  `add-topic`, `next`, `due`, `rate`, `stash`, `receipt`, `model`, `artifact`,
  `experiment`, `stats`, `report`, `doctor`, `refit`, `capstone`, `transfer`,
  `assessor-audit`, `selftest`. `python3 scripts/engram.py <cmd> --help` für Details;
  `doctor` zuerst bei jeder State-Anomalie.

### Lernertext geht nie auf die Kommandozeile

Gilt für **jeden** Aufruf von `engram.py`, nicht nur für den Cloud-Fork (siehe
„Sicherheitsregel" oben): Freitext immer per `--file`/`--json -`/`--production-file -`,
nie als Shell-Argument.

### Wichtige Dateien zum Navigieren

| Pfad | Rolle |
|---|---|
| `scripts/engram.py` | deterministischer Kern: FSRS, State, Receipts, Stats, `selftest` |
| `skills/learn\|review\|coach/SKILL.md` | die drei Tutor-Skills (Upstream, unangetastet) |
| `skills/_shared/dialogue-grammar.md` | Dialog-Regeln des Tutors (predict→attempt→hint→resolve→self-explain→connect) |
| `skills/_shared/explorable-contract.md` | Pflicht-Spec für generierte HTML-Explorables |
| `skills/_shared/problem-grammar.md`, `subagents.md` | weitere gemeinsame Bausteine |
| `agents/engram-curriculum-architect.md` | Thema → Konzept-DAG (typisierte Kanten) |
| `agents/engram-assessor.md` | blinder Grader, rubrikgebunden, schreibt Receipts |
| `agents/engram-artifact-smith.md` | baut Explorables unter dem Explorable Contract |
| `hooks/session-start.{sh,ts}` | Re-Anchoring: Due-Count-Nudge beim Sessionstart |
| `.opencode-plugin/` | OpenCode-Adapter (V1 + 2.0), TypeScript, hier getestet |
| `docs/03-architecture.md` | die Design-Referenz — vor jeder strukturellen Änderung lesen |
| `docs/06-visual-encoding.md` | wann/wie Explorables gebaut werden (Visuals-Dial) |
| `gold/assessor-gold.jsonl` | Gold-Set für `assessor-audit` / Grader-Kalibrierung |

## Tests

Wie CI (`.github/workflows/test.yml`):

```bash
bun install && bun run test && npx tsc --noEmit
python3 scripts/engram.py selftest
```

`bun run test` führt `vitest run` über `__tests__/*.test.ts` aus (Tests für die
`.opencode-plugin/`-Adapter — Install/Update-Logik, Diff, Frontmatter-Parser,
Session-Start, Skills-Waterfall). Einzelne Datei oder einzelner Test:

```bash
npx vitest run __tests__/update.test.ts
npx vitest run -t "some test name"
```

`python3 scripts/engram.py selftest` ist der Test der eigentlichen Engine (FSRS-Mathe,
State-Übergänge, Schema-Migration) — ein einzelnes Modul lässt sich nicht isoliert
laufen lassen, `selftest` deckt den Kern komplett ab und meldet `N/N`.

Dazu der Selftest des Quellen-Werkzeugs — er prüft die `kind`-Heuristik gegen
Fixtures, die aus echtem Material gezogen sind:

```bash
python3 .claude/tools/engram_source.py selftest
```

Er hängt **nicht** in `.github/workflows/test.yml`, und das ist Absicht: Die
Workflow-Datei ist Upstream-Code, ein Schritt darin wäre der erste Konflikt beim
nächsten `git merge upstream/main`. Wer die Marker in `engram_source.py` anfasst,
ruft ihn von Hand auf.
