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

`.claude/skills/engram-*/SKILL.md` sind dünne Aliase: sie enthalten nur Frontmatter
und die Anweisung, das echte `skills/<name>/SKILL.md` zu lesen und **wörtlich** zu
befolgen. Die Upstream-Skills bleiben unangetastet — deshalb kollidiert ein Update
nie. Die Subagents unter `.claude/agents/` sind Symlinks nach `agents/`.

## Lernstand: wo er liegt und warum er gepusht werden muss

Container in dieser Umgebung sind kurzlebig. Der Lernstand überlebt **nur**, wenn er
nach Git gepusht wird.

- `ENGRAM_HOME` = `<engram-learning-checkout>/learning`, gesetzt vom SessionStart-Hook.
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
