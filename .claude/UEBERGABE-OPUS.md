# Übergabe an Opus — Review des Cloud-Setups (Stand 2026-08-01)

Dieses Dokument ist eine Arbeitsübergabe. Es beschreibt, was geprüft wurde, was
gefunden wurde — und vor allem, **wo die Grenzen der Arbeit liegen**. Lies zuerst
`CLAUDE.md` im Repo-Root; dieses Dokument setzt es voraus und wiederholt es nicht.

## Was dieses System ist — und was davon dir gehört

Zwei Repos:

- **`karachay-b/engram`** (öffentlicher Fork): Upstream-Lern-Engine plus Cloud-Setup.
  **Dein Arbeitsbereich ist ausschließlich `.claude/` und `CLAUDE.md`.** Alles
  andere — `scripts/`, `skills/`, `agents/`, `hooks/`, `docs/`, Tests — ist
  unveränderter Upstream-Code und wird **weder bewertet noch angefasst**. Updates
  kommen per `git merge upstream/main`; jede lokale Änderung dort erzeugt künftige
  Konflikte.
- **`karachay-b/engram-learning`** (privat): der Lernstand (`learning/`, gehört der
  Engine) und die aufbereiteten Quellen (`sources/`). Enthält Freitext-Antworten des
  Lernenden und Derivate eines urheberrechtlich geschützten Buchs. Nichts daraus
  darf in den öffentlichen Fork, in Artifacts oder in GitHub-Kommentare.

## Geprüfter Ist-Zustand

Alle Prüfungen am 2026-08-01 in einer Cloud-Session ausgeführt:

- `python3 scripts/engram.py selftest` → **302/302 bestanden**.
- `.claude/tools/engram_source.py paths` / `list` → funktioniert, findet das
  State-Repo ohne Umgebungsvariablen selbst; 1 Quelle (`systemisch-beratung`,
  151 Chunks, ~140k Wörter).
- Lernstand: 1 Topic (`problemtrance-unterbrechen`), 18 Nodes, 0 Receipts —
  Lernen hat gerade erst begonnen, das ist der erwartete Zustand, kein Defekt.
- Alias-Skills: `description`-Zeilen stimmen **wortgleich** mit den
  Upstream-Frontmatters überein (die eine bewusste Duplizierung ist synchron).
- Subagent-Symlinks unter `.claude/agents/` intakt.
- Hooks: `engram-save.sh` und `session-start.sh` gelesen und manuell ausgeführt;
  Verhalten wie dokumentiert (Retry mit Backoff, Identity-Fallback, laute Warnung
  bei fehlendem State-Repo, sed-Umschreibung der Kommandonamen).
- `engram_source.py`: einziger `subprocess`-Aufruf ist die pip-Nachinstallation;
  keine Shell-Injection-Fläche, kein `shell=True`, kein `eval`.

## Befunde

### B1 — Das Original-PDF liegt git-getrackt in `engram-learning/sources_raw/`

`sources/.gitignore` hält PDFs korrekt aus `sources/` heraus — aber im Repo-Root
liegt **kein** `.gitignore`, und unter `sources_raw/` ist das Original
(„Systemisch-lösungsorientierte Gesprächsführung in Beratung.pdf", 5,8 MB) per
GitHub-Web-Upload committet worden (Commit „Add files via upload"). Das
widerspricht dem dokumentierten Design („Originale bleiben draußen") — hat aber
einen nachvollziehbaren Grund: nur so überlebt das Original den Container, und
`engram-source verify` sowie der Bild-Weg für Scans brauchen es gelegentlich wieder.

**Entschieden (2026-08-01): Andre behält das PDF bewusst.** Die Ausnahme ist in
`CLAUDE.md` (Abschnitt „Quellen") dokumentiert: `sources_raw/` ist der manuelle,
mitversionierte Ablageort für Originale im privaten Repo. Damit ist dieser Befund
geschlossen — **nicht löschen, keine History umschreiben, kein Root-`.gitignore`
nachrüsten.** Der Stop-Hook committet `sources_raw/` weiterhin nicht (nur
`learning/` und `sources/`); Befüllung bleibt ein manueller Weg.

### B2 — `ENGRAM_HOME` kommt nicht in der Bash-Umgebung der Cloud-Session an

Empirisch in dieser Session: `CLAUDE_PROJECT_DIR` und `CLAUDE_ENV_FILE` sind in
Bash-Aufrufen **unset**, `ENGRAM_HOME` ebenfalls. Ein naives
`python3 scripts/engram.py …` fällt dann auf `~/.claude/learning` zurück —
container-flüchtig und leer. Der Ausweg existiert bereits und ist eine Zeile:

```bash
. .claude/hooks/engram-env.sh   # setzt ENGRAM_PROJECT, ENGRAM_STATE, ENGRAM_HOME
```

Kleinster sinnvoller Fix, falls Andre ihn will: je **ein Satz** in den vier
Alias-Skills und in `CLAUDE.md`, der vor jedem Engine-Aufruf das Sourcen von
`engram-env.sh` vorschreibt. **Nicht**: Wrapper-Skripte, neue Hooks, Änderungen an
der Engine oder am Env-Mechanismus der Plattform.

### B3 — Der State-Repo-Checkout steht in Task-Sessions auf dem Task-Branch

Die Remote-Umgebung checkt **beide** Quellen auf dem Task-Branch aus (hier:
`claude/opus5-scope-review-2a0gup`). Der Stop-Hook pusht bewusst auf den
aktuellen Branch — Lernstand aus einer solchen Session landet also auf einem
Seitenbranch von `engram-learning` und muss danach nach `main` gemergt werden.
Das ist Umgebungsverhalten, kein Hook-Fehler. **Den Hook nicht umbauen**, damit er
immer nach `main` pusht — das würde in echten Lern-Sessions stilles
Branch-Überschreiben bedeuten. Es reicht, das Verhalten zu kennen und nach
Task-Sessions den Merge zu prüfen.

## Absichtlich so — nicht „verbessern"

Jeder Punkt hier sieht aus wie eine Verbesserungsgelegenheit und ist keine:

- **Die Alias-Skills sind dünn und redundant.** Frontmatter-Duplizierung und der
  Spawn-Baustein sind die zwei dokumentierten, bewussten Kopplungen an Upstream.
  Kein DRY-Refactoring, keine gemeinsame Include-Datei, kein Generator.
- **Kein Embedding-Index für Quellen.** Bei ~40–150 Chunks pro Buch ist
  Index + grep schneller, nachvollziehbar und containerfest. Begründung steht im
  Docstring von `engram_source.py`.
- **`bun install --no-save`** im SessionStart-Hook ist Absicht: `bun.lock` ist
  upstream out of sync, ein Rewrite hieße dauerhaft schmutziger Tree.
- **Die sed-Umschreibung** (`/learn` → `/engram-learn`) im SessionStart-Hook ist
  Absicht: Upstream-Code bleibt unangetastet, nur die Ausgabe wird umbenannt.
- **Hooks enden immer mit `exit 0`.** Sie dürfen niemals eine Session oder einen
  Turn blockieren. Kein „richtiges" Error-Handling nachrüsten.
- **`digest` ist kein Skript-Unterkommando.** Verdichten ist Modellarbeit; das
  steht so im Source-Skill. Nicht implementieren.
- **Das Node-Schema hat kein Quellenfeld** und darf keins bekommen — die Engine
  würde es verwerfen. `sources/MAP.md` ist der Ersatz.

## Leitplanken für deine Arbeit

1. **Nur tun, was ein Auftrag benennt.** Ein Befund oben ist eine Vorlage für
   Andre, kein Arbeitsauftrag an dich. Erst fragen, dann ändern.
2. **Kleinster Diff, der den Auftrag erfüllt.** Wenn eine Änderung mehr als die
   im Auftrag genannten Dateien berührt, ist das ein Stoppsignal.
3. **Niemals Upstream-Dateien ändern** (alles außer `.claude/` und `CLAUDE.md`
   im Fork). Niemals die Struktur von `engram-learning` umbauen.
4. **Keine neuen Skills, Agents, Hooks, Tools oder Abstraktionen** ohne
   ausdrücklichen Wunsch. Das Setup ist bewusst klein.
5. **Privates bleibt privat**: nichts aus `engram-learning` in den Fork, in
   Artifacts oder Kommentare. Lernertext und Buchtext nie auf die Kommandozeile
   (Datei oder stdin, siehe `CLAUDE.md`).
6. **Nach jeder Änderung die Gegenprobe**: `bun run test`, `npx tsc --noEmit`,
   `python3 scripts/engram.py selftest` (≥ 302/302) — wie CI.
