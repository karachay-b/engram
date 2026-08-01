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
  vor dem ersten Engine-Aufruf `. .claude/hooks/engram-env.sh` sourcen, sonst
  schreibt die Engine ins flüchtige `~/.claude/learning`.
- Das Repo `karachay-b/engram-learning` ist **privat** — es enthält Freitext-Antworten,
  Bewertungen und ein Misconception-Log. Es gehört niemals in diesen öffentlichen Fork.
- Den echten Pfad immer aus `python3 scripts/engram.py doctor` (Feld `home`) lesen.
  **Nie `~/.claude/learning` wörtlich ausgeben** — hier stimmt das nicht.

Der Stop-Hook (`.claude/hooks/engram-save.sh`) committet und pusht automatisch nach
jedem Turn. Meldet er einen fehlgeschlagenen Push, muss der Push manuell nachgeholt
werden, bevor die Session endet.

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
  Das ist die einzige dauerhafte Zuordnung Thema ↔ Quelle.

**Die Rolle des Buchs ist Inhalt, nicht Gliederung.** Der Curriculum-Architect nennt
Kapitel-Kopieren seinen kardinalen Fehler; der Spawn-Baustein im `engram-learn`-Alias
stellt das scharf. Das ist die **eine bewusste Kopplung an Upstream**: Ändert der
Upstream die Rollenbeschreibung des Architects grundlegend, muss dieser Baustein
nachgezogen werden — dieselbe Klasse von Duplizierung wie die `description`-Zeilen
der Alias-Skills.

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
`description`-Zeilen in `.claude/skills/engram-*/SKILL.md` nachgezogen werden; sie
sind die einzige bewusste Duplizierung im Setup.

## Tests

Wie CI (`.github/workflows/test.yml`):

```bash
bun install && bun run test && npx tsc --noEmit
python3 scripts/engram.py selftest
```
