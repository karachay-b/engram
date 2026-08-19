# Übergabe an Hermes Agent — Engram einrichten

**An den Agenten, der das hier liest:** Das ist ein Arbeitsauftrag, keine Erzählung.
Arbeite die Schritte 1–5 der Reihe nach ab, führe die Prüfungen wirklich aus und
vergleiche ihre Ausgabe mit dem, was hier steht. Wo etwas abweicht, melde es, statt
weiterzugehen. Am Ende steht ein Setup, das sich denselben Lernstand mit Claude Code
teilt.

Zeit: etwa 15 Minuten, davon die Hälfte Warten auf `git clone`.

---

## 0 · Was dieses System ist

Zwei Repositories, eine Aufgabe: **Der Nutzer lernt, die Engine merkt sich den Stand.**

| Repo | Rolle | Sichtbarkeit |
|---|---|---|
| `karachay-b/engram` | Lern-Engine (`scripts/engram.py`) + die Verdrahtung unter `.claude/` und `.hermes/` | öffentlich |
| `karachay-b/engram-learning` | Lernstand (`learning/`) + aufbereitete Quellen (`sources/`) | **privat** |

Die Engine ist ein deterministischer Python-Kern ohne Abhängigkeiten: FSRS-4.5-Scheduler,
Zustandsautomat, append-only Prüfnachweise („Receipts"). Sie rechnet, sie tutort nicht.
Das Tutoring führen Markdown-Skills im Hauptkontext; drei Rollen (Curriculum-Architect,
Assessor, Artifact-Smith) laufen als Kinder mit frischem Kontext.

**Die Verzahnung, die alles trägt:** `ENGRAM_HOME` zeigt aus dem Engine-Repo in das
State-Repo (`<engram-learning>/learning`). Die Engine liest und schreibt **nur dort**.
Zeigt die Variable woanders hin, funktioniert alles scheinbar — und der Lernstand
zerfällt in zwei Hälften, die nichts voneinander wissen.

### Drei bindende Regeln

Sie gelten in jeder Session, auf jeder Plattform, ohne Ausnahme:

1. **Lernertext nie auf die Kommandozeile.** Freitext — Antworten, Lernziele, Buchtext,
   Zitate, URLs — erreicht `engram.py` nur über `--file`, `--json -` oder
   `--production-file -`. Ein `'` oder `$(…)` in einer Antwort wäre sonst eine
   Command-Injection. Der Weg dorthin ist das Datei-Schreibwerkzeug oder ein Heredoc mit
   **quotiertem** Delimiter (`<<'JSON'`).
2. **Quellen-Derivate bleiben privat.** Buchtext, wörtliche Zitate und Lernerantworten
   gehören nie in den öffentlichen Fork, nie in eine geteilte Seite, nie in einen
   GitHub-Kommentar. Metadaten (Titel, Seitenzahl, Chunkzahl) sind unbedenklich.
3. **Pfade nie raten.** Den echten State-Pfad immer aus `engram.py doctor` lesen, Feld
   `home`. Die Upstream-Dokumentation nennt `~/.claude/learning` — **hier stimmt das
   nicht**, und es nachzuplappern schickt den Lernstand ins Nirgendwo.

---

## 1 · Voraussetzungen und Repos

### Prüfen, bevor irgendetwas geklont wird

```bash
hermes --version     # muss >= 0.5.0 sein: erst ab da feuern die Lifecycle-Hooks
python3 --version    # >= 3.8; die Engine ist stdlib-only, sonst nichts nötig
git --version
```

Ist Hermes älter als 0.5.0: erst aktualisieren. Ohne die Lifecycle-Hooks gibt es keinen
Auto-Save, und das ist genau der Teil, den dieses Setup braucht.

Das Modell kommt über das Nous Portal: `hermes setup --portal` (OAuth, legt die
Anmeldung selbst ab). Die Mechanik von Engram läuft auf jedem Modell — die **Pädagogik
ist so gut wie das Modell**. Für `/engram-learn` das fähigste verfügbare wählen.

### Klonen — Geschwister-Layout, nicht ineinander

```bash
git clone https://github.com/karachay-b/engram.git            ~/engram
git clone https://github.com/karachay-b/engram-learning.git   ~/engram-learning
```

Beide **nebeneinander** in `$HOME`. Das ist kein Geschmack: Die beiden Zusatzwerkzeuge
(`engram_source.py`, `engram_status.py`) suchen das State-Repo unter anderem über
`<tools>/../../../engram-learning` — im Geschwister-Layout treffen sie es ohne jede
Umgebungsvariable. Ein Checkout **innerhalb** des anderen bräche außerdem beide
Git-Repos übereinander.

`engram-learning` ist **privat**. Der Klon braucht also Zugang — SSH-Key oder ein
Personal Access Token mit `repo`-Recht. Schlägt der Klon mit „repository not found"
fehl, ist das fast immer fehlende Authentifizierung, nicht ein falscher Name.

Danach im State-Repo prüfen, dass `main` ausgecheckt ist und ein Remote steht:

```bash
git -C ~/engram-learning rev-parse --abbrev-ref HEAD   # muss: main
git -C ~/engram-learning remote get-url origin
git -C ~/engram-learning config user.name              # leer? dann setzen:
# git -C ~/engram-learning config user.name  "…"
# git -C ~/engram-learning config user.email "…"
```

**`main` ist Bedingung, nicht Empfehlung.** Beide Hooks weigern sich, auf einem anderen
Branch automatisch zu pullen oder zu pushen — auf einem Nebenbranch würde die Arbeit
gesammelt und niemand sähe sie.

Im Engine-Repo noch den Upstream eintragen, damit Updates später einen Weg haben:

```bash
git -C ~/engram remote add upstream https://github.com/nagisanzenin/engram.git
```

---

## 2 · `~/.hermes/.env`

Drei Zeilen anhängen, `<DU>` durch den eigenen Benutzernamen ersetzen (macOS
`/Users/<DU>`, Linux `/home/<DU>`) — **absolute Pfade, kein `~`**:

```bash
ENGRAM_ROOT=/Users/<DU>/engram
ENGRAM_HOME=/Users/<DU>/engram-learning/learning
ENGRAM_STATE_REPO=/Users/<DU>/engram-learning
```

Hermes lädt `.env` beim Start in seinen Prozess, und Terminal-Subprozesse erben die
Variablen — so erreichen sie die Shell-Kommandos der Skills. Das ist auf Hermes der
**einzige** Weg dorthin: Ein Hook kann hier, anders als in Claude Code, keine Variable
in die Session exportieren.

`ENGRAM_ROOT` ist zugleich der Notausgang, auf den der unveränderte Upstream-Resolver
anspringt. `ENGRAM_STATE_REPO` brauchen die beiden Zusatzwerkzeuge, falls das
Geschwister-Layout doch einmal nicht steht.

---

## 3 · `~/.hermes/config.yaml`

Vorlage: `~/engram/.hermes/config.snippet.yaml`. Die beiden Blöcke dort in die
**bestehende** `config.yaml` einsortieren — `skills:` und `hooks:` sind
Top-Level-Schlüssel, und ein zweiter Schlüssel gleichen Namens verschluckt den ersten
stillschweigend. Gibt es die Schlüssel schon, die Einträge **ergänzen**.

```yaml
skills:
  external_dirs:
    - ~/engram/.hermes/skills

hooks:
  pre_llm_call:
    - command: "/Users/<DU>/engram/.hermes/hooks/session-start.sh"
      timeout: 120
  post_llm_call:
    - command: "/Users/<DU>/engram/.hermes/hooks/engram-save.sh"
      timeout: 120
```

Zwei Fallen:

- Bei `external_dirs` wird `~` expandiert, bei `command` **nicht**. Hook-Kommandos
  deshalb absolut schreiben.
- Beim ersten Feuern fragt Hermes je (Event, Kommando) einmal nach Zustimmung und
  merkt sie sich in `~/.hermes/shell-hooks-allowlist.json`. **Beide bestätigen** —
  wird der `post_llm_call`-Hook abgelehnt, läuft alles weiter, nur wird nichts mehr
  gespeichert. Das ist der eine Fehler, der sich erst Wochen später zeigt.

Danach Hermes neu starten (Desktop-App: beenden und öffnen, nicht nur das Fenster
schließen). Die Desktop-App und die CLI teilen sich `~/.hermes` vollständig — was hier
eingerichtet wird, gilt für beide.

---

## 4 · Verifikation

Alle fünf Prüfungen ausführen und die Ausgabe vergleichen. Die dritte ist die
wichtigste — sie beweist die ganze Verdrahtung auf einmal.

```bash
# 1 · Die Engine ist intakt
python3 ~/engram/scripts/engram.py selftest
#    erwartet: eine Zeile, die mit N/N endet (alle bestanden, N ist dreistellig)

# 2 · Die beiden Zusatzwerkzeuge
python3 ~/engram/.claude/tools/engram_source.py selftest
python3 ~/engram/.claude/tools/engram_status.py selftest
#    erwartet: jeweils bestanden, ohne Zugriff auf das echte State-Repo

# 3 · DIE ENTSCHEIDENDE — zeigt die Engine ins private Repo?
python3 ~/engram/scripts/engram.py doctor | python3 -m json.tool | head -20
#    erwartet: "home": "/Users/<DU>/engram-learning/learning"
#    steht dort etwas mit ".claude/learning", ist Schritt 2 nicht angekommen:
#    Hermes wurde nicht neu gestartet, oder .env hat einen Tippfehler. NICHT weitergehen.

# 4 · Der Sessionstart-Hook antwortet gültig
echo '{"session_id":"probe-1"}' | bash ~/engram/.hermes/hooks/session-start.sh | python3 -m json.tool | head -5
#    erwartet: ein JSON-Objekt mit "context" (Briefing + ggf. Fälligkeiten)
echo '{"session_id":"probe-1"}' | bash ~/engram/.hermes/hooks/session-start.sh
#    erwartet: genau {}  — die Dedupe-Sperre greift, kein zweites Briefing pro Session

# 5 · Der Speicher-Hook ist bei sauberem Baum still
echo '{"session_id":"probe-1"}' | bash ~/engram/.hermes/hooks/engram-save.sh
#    erwartet: {} auf stdout und nichts auf stderr
```

Dann in Hermes selbst: `/engram-status` eingeben. Der Skill muss auftauchen (er kommt
aus `external_dirs`) und mit einem Bootstrap-Block starten, der `ENGRAM_ROOT` und
`ENGRAM_HOME` **gefüllt** ausgibt.

---

## 5 · Der erste echte Lauf

```
/engram-status      → wo steht der Lernstand, welche Quellen sind eingebunden
/engram-review      → die fälligen Wiederholungen, zwei Minuten
```

Danach die Gegenprobe, dass der Auto-Save wirklich läuft:

```bash
git -C ~/engram-learning log --oneline -3
```

Steht dort ein frischer Commit `engram (hermes): … Themen, … Konzepte, … Receipts`,
funktioniert die Kette vollständig: Engine → State-Repo → `origin/main` → Claude Code.
Steht er nicht da, war die Session ohne Änderung (dann ist das korrekt) — oder der
`post_llm_call`-Hook ist nicht bestätigt. Dann Schritt 3 nachsehen.

---

## Die fünf Kommandos

| Kommando | Wozu | Auf Hermes |
|---|---|---|
| `/engram-learn <thema>` | Neues lernen oder fortsetzen — Kurrikulum, Tutoring, blinde Bewertung | Architect und Assessor laufen über `delegate_task` |
| `/engram-review` | Fällige Wiederholungen (die Zwei-Minuten-Gewohnheit) | unverändert |
| `/engram-coach` | Telemetrie, Kalibrierung, Grader-Audit, Experimente | Dashboard als lokale HTML-Datei |
| `/engram-source` | Buch/PDF als Lernstoff aufbereiten | braucht `pypdf`, installiert es bei Bedarf selbst |
| `/engram-status` | Momentaufnahme: Quellen, Lernpfad-Stand, Fälligkeiten | Text oder lokale HTML-Datei, **keine teilbare Seite** |

Die Namen sind bewusst mit `engram-` präfigiert. Auf Hermes ist das zusätzlich nötig:
**`/learn` ist ein Builtin** (es baut neue Skills aus Quellen) und lässt sich nicht
überschreiben.

---

## Grenzen — ehrlich benannt

**Geprüft** (Linux-Container, gegen ein Wegwerf-Repo, nicht nur gelesen): die
Git-Logik des Speicher-Hooks in allen vier Zuständen — No-Op bei sauberem Baum, sauberer
Push nach `main`, abgelehnter Push mit Rebase und zweitem Versuch, und der echte Konflikt
(Rebase zurückgerollt, lokaler Stand unversehrt, laute Meldung, Rückgabewert 0). Dazu
Syntax beider Hooks, ihr JSON auf stdout, die Dedupe-Sperre des Sessionstarts, die
Weigerung beider Hooks auf einem Nicht-`main`-Branch, und die Selftests von Engine
(315/315) und beiden Werkzeugen.

**Nicht geprüft, weil keine Hermes-Installation vorlag:** ob die fünf Skills im Index
landen, ob Hermes die Hooks tatsächlich feuert, und ob `delegate_task` den Assessor blind
hält. Genau dafür sind Schritt 4 und 5 da — sie sind keine Formsache. Upstream markiert
seinen eigenen Hermes-Teil aus demselben Grund teilweise als „not yet verified"; diese
Ehrlichkeit wird hier fortgeschrieben, nicht überschrieben.

Weiter:

- **Kein Artifact-Publishing.** `/engram-status` und der Artifact-Smith schreiben lokale
  HTML-Dateien. Für den Smith ändert das nichts (er hat immer lokal geschrieben und mit
  `engram.py artifact set` registriert); `/engram-status` verliert den teilbaren Link.
- **Subagents werden explizit ausgelöst, nicht geroutet.** In Claude Code genügt „spawne
  den engram-assessor", weil die Agents registriert sind. Auf Hermes muss der Inhalt von
  `agents/engram-<rolle>.md` als `context` in `delegate_task` mitgegeben werden.
  `.hermes/PLATTFORM.md` §3 hat die Form; sie ist bindend, nicht beispielhaft.
- **Sync-Konflikte sind Handarbeit.** Beide Hooks pullen und pushen, aber **lösen keinen
  Konflikt auf**. Der Grund: `learning/receipts/*.jsonl` ist append-only und ließe sich
  als Vereinigung auflösen, `learning/graphs/*.json` trägt FSRS-State und ließe sich das
  nicht — eine Automatik über beides wäre eine Maschine für stillen Datenverlust. Bei
  einem Konflikt rollen die Hooks den Rebase zurück, lassen den lokalen Stand
  unversehrt und sagen es. Auflösung von Hand:
  **`graphs/*.json`** → der neuere FSRS-Stand gewinnt;
  **`receipts/*.jsonl`** → beide Seiten behalten, nichts löschen.
  Vermeiden lässt sich das meiste, indem man nicht auf beiden Plattformen gleichzeitig
  lernt und offene PRs im State-Repo zeitnah merget.
- **`sources_raw/` zieht ein Original-PDF mit** (rund 6 MB). Das ist so gewollt und
  dokumentiert: nur so überlebt das Original und steht für `engram-source verify` wieder
  zur Verfügung. Das Repo ist privat — **nur deshalb** ist es vertretbar. Nichts daraus
  wandert in den öffentlichen Fork.
- **`pypdf`** fehlt anfangs und wird von `engram_source.py` bei Bedarf selbst
  nachinstalliert. Ohne Netzzugang beim ersten `/engram-source add` schlägt das fehl;
  dann `python3 -m pip install pypdf` von Hand.

---

## Was in Claude Code unverändert gilt

Damit die beiden Plattformen nicht auseinanderlaufen:

- **Der Lernstand ist geteilt, nicht kopiert.** Beide schreiben nach
  `karachay-b/engram-learning`, Branch `main`. Hermes pullt beim Sessionstart und pusht
  nach jedem Turn.
- **`.claude/` bleibt die Heimat der Regeln.** Die Hermes-Skills lesen sie von dort. Wer
  eine Regel ändert, ändert sie in `.claude/skills/engram-*/SKILL.md` — und sie gilt
  sofort auf beiden Plattformen. Dupliziert sind nur der Bootstrap-Block und die
  `description`-Zeilen; wer die anfasst, fasst sie in `.claude/` **und** `.hermes/` an.
- **Upstream-Updates** laufen weiter über `git merge upstream/main` im Engine-Repo,
  danach `python3 scripts/engram.py selftest`. Konflikte sind unwahrscheinlich:
  `.claude/`, `.hermes/` und `CLAUDE.md` gibt es upstream nicht.
- **Ausführliche Fassung von allem:** `CLAUDE.md` im Repo-Root, und für die
  Hermes-Besonderheiten `.hermes/PLATTFORM.md`.
