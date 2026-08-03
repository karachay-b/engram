# Engram — Cloud-Setup (Claude Code im Web)

Dieses Repo ist ein Fork von [nagisanzenin/engram](https://github.com/nagisanzenin/engram),
zusätzlich verdrahtet für die Nutzung in Claude Code on the web. Alles unter `.claude/`
und diese Datei gehören zum Cloud-Setup; alles andere ist unveränderter Upstream-Code.

## Die drei Kommandos

| Hier | Upstream-Doku | Warum umbenannt |
|---|---|---|
| `/engram-learn <topic>` | `/learn` | `learn` kollidiert mit einem globalen Skill des Nutzers |
| `/engram-review` | `/review` | `review` kollidiert mit Claude Codes GitHub-PR-Review |
| `/engram-coach` | `/coach` | einheitliches Präfix |
| `/engram-source` | — | kein Upstream-Pendant; siehe „Quellen" unten |

`.claude/skills/engram-*/SKILL.md` sind dünne Aliase: sie enthalten nur Frontmatter
und die Anweisung, das echte `skills/<name>/SKILL.md` zu lesen und **wörtlich** zu
befolgen. Die Upstream-Skills bleiben unangetastet — deshalb kollidiert ein Update
nie. Die Subagents unter `.claude/agents/` sind Symlinks nach `agents/`.

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
python3 scripts/engram.py selftest    # muss 302/302 (oder mehr) bestehen
```

Alternativ der "Sync fork"-Button auf GitHub. Nach jedem Update den Selftest laufen
lassen — er ist die Gegenprobe, dass die Engine intakt ist.

Ändert Upstream die Namen oder Frontmatter-Beschreibungen der Skills, müssen die
`description`-Zeilen in `.claude/skills/engram-*/SKILL.md` nachgezogen werden.

Zweite bewusste Duplizierung: der **Bootstrap-Block** steht wörtlich in allen vier
Alias-Skills. Ein gemeinsamer Ort ginge nicht — der Block ist genau das Stück Code,
das den gemeinsamen Ort erst findet. Upstream duplizert seinen eigenen Resolver aus
demselben Grund über `skills/{learn,review,coach}/SKILL.md`. Wer den Block ändert,
ändert ihn viermal.

## Tests

Wie CI (`.github/workflows/test.yml`):

```bash
bun install && bun run test && npx tsc --noEmit
python3 scripts/engram.py selftest
```
