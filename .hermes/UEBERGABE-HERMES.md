# Übergabe an Hermes Agent — Engram einrichten

**An den Agenten, der das hier liest:** Das ist ein Arbeitsauftrag, keine Erzählung.
Arbeite die Schritte 1–7 der Reihe nach ab, führe die Prüfungen wirklich aus und
vergleiche ihre Ausgabe mit dem, was hier steht. Wo etwas abweicht, melde es, statt
weiterzugehen. Am Ende steht ein Setup, das sich denselben Lernstand mit Claude Code
teilt und einmal täglich eine Fälligkeits-Nudge aufs Handy schickt.

> **Läuft auf diesem Rechner schon eine ältere Engram-Verdrahtung?** Dann ist das
> hier das falsche Dokument — `.hermes/UMSTELLUNG-HERMES.md` nehmen. Eine
> Neuinstallation über ein bestehendes Setup zu legen, hinterlässt zwei
> Verdrahtungen, von denen die ältere still nichts mehr tut.

Zeit: etwa 20 Minuten, davon der Großteil Warten auf `git clone` und das
Telegram-Bot-Setup.

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

## 1 · Profil `engram` anlegen

Alles Folgende gehört in ein **eigenes** Hermes-Profil, nicht in die Standard-
Installation. Ein Profil ist ein eigenes `HERMES_HOME` mit eigener `config.yaml`,
`.env`, `SOUL.md`, Sessions, Skills, Cron-Jobs und Gateway-Bot:

```bash
hermes profile create engram
```

Das legt `~/.hermes/profiles/engram/` an und einen Alias `~/.local/bin/engram` —
der Einstieg heißt ab hier `engram chat`, nicht `hermes chat`. Prüfen:

```bash
ls ~/.hermes/profiles/engram/            # erwartet: (leeres) Verzeichnis existiert
which engram                             # erwartet: ~/.local/bin/engram
```

**Warum ein eigenes Profil, nicht einfach Hooks in der Standard-Installation:**
Ohne Abgrenzung findet der Resolver in `.hermes/hooks/engram-env.sh` `$HOME/engram`
in JEDER Hermes-Session — auch einer über etwas völlig anderes — und injiziert das
Engram-Briefing. Ein Profil ist ein eigenes `HERMES_HOME`; die beiden Hooks werden
unten (Schritt 4) nur in dessen `config.yaml` registriert und feuern deshalb
nirgends sonst. Der Code-Riegel (`ENGRAM_HERMES=1`, gesetzt in Schritt 3) ist die
zweite, unabhängige Absicherung für den Fall eines Tippfehlers — das Profil ist
die strukturelle.

Alle folgenden Schritte (`.env`, `config.yaml`, `SOUL.md`) beziehen sich auf
`~/.hermes/profiles/engram/`, nicht auf `~/.hermes/` direkt.

---

## 2 · Voraussetzungen und Repos

### Prüfen, bevor irgendetwas geklont wird

```bash
hermes --version     # muss >= 0.5.0 sein: erst ab da feuern die Lifecycle-Hooks
python3 --version    # >= 3.8; die Engine ist stdlib-only, sonst nichts nötig
git --version
```

Ist Hermes älter als 0.5.0: erst aktualisieren. Ohne die Lifecycle-Hooks gibt es keinen
Auto-Save, und das ist genau der Teil, den dieses Setup braucht.

### Das Modell

Anmeldung über das Nous Portal: `hermes setup --portal` (OAuth, legt die Anmeldung
selbst ab). Danach das Modell setzen — für die Einrichtung **und** als Ausgangspunkt
für den Alltag:

```yaml
# ~/.hermes/profiles/engram/config.yaml
model:
  default: "minimax/minimax-m3"
  provider: "nous"
```

**Warum M3** (Stand 2026-08; Preise und Ranglisten altern schnell, vor einer
Neubewertung nachschlagen): 0,30 $/M Input und 1,20 $/M Output bei 1M Kontext — und
die Benchmarks, die zu *dieser* Aufgabe passen, sind Terminal-Bench (Kommandozeilen-
Agent, 66,0) und MCP Atlas (Werkzeugaufrufe, 74,2), nicht Prosa-Ranglisten. Die ganze
Einrichtung kostet damit grob 0,40 $. Zum Vergleich: dasselbe mit Claude Sonnet 4.6
läge bei etwa 4 $ — bei einer einmaligen Aufgabe ist der Unterschied Rauschen, weshalb
hier **Zuverlässigkeit** und nicht der Preis den Ausschlag gibt. M3 gewinnt auf beiden
Achsen.

Stolpert es doch — es meldet Erfolg, ohne die Prüfungen wirklich ausgeführt zu haben —
dann mitten in der Session `/model anthropic/claude-haiku-4.5` und weiter. Anthropic-
Modelle sind bei stur abzuarbeitenden Checklisten die konservativere Wahl, und unter
1,50 $ für den Rest.

**Nicht nehmen:** Nous' eigene Hermes-4-Modelle. Trotz stark rabattierter Preise sagt
die Portal-Doku ausdrücklich „not recommended for use inside Hermes Agent".

Optional, spart im Dauerbetrieb spürbar — die Kontextkompression auf ein billiges
Modell auslagern, statt sie mit dem Hauptmodell zu bezahlen:

```yaml
auxiliary:
  compression:
    model: "qwen/qwen3.7-flash"     # 0,03 $/M
    provider: "nous"
```

**Ein Vorbehalt für den Alltag danach.** Die Mechanik von Engram läuft auf jedem
Modell; die **Pädagogik ist so gut wie das Modell**. `/engram-review` ist mechanisch und
verträgt Sparsamkeit. `/engram-learn` nicht — dort entstehen Kurrikulum, Dialogführung
und die blinde Bewertung, und ein schwaches Modell erzeugt dort einen Lernpfad, dessen
Mängel erst Wochen später beim Behalten auffallen. Dafür `/model` mitten in der Session
nutzen, statt eine Einstellung für beides zu suchen.

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

## 3 · `~/.hermes/profiles/engram/.env`

Vier Zeilen anhängen, `<DU>` durch den eigenen Benutzernamen ersetzen (macOS
`/Users/<DU>`, Linux `/home/<DU>`) — **absolute Pfade, kein `~`**:

```bash
ENGRAM_ROOT=/Users/<DU>/engram
ENGRAM_HOME=/Users/<DU>/engram-learning/learning
ENGRAM_STATE_REPO=/Users/<DU>/engram-learning
ENGRAM_HERMES=1
```

Hermes lädt `.env` beim Start in seinen Prozess, und Terminal-Subprozesse erben die
Variablen — so erreichen sie die Shell-Kommandos der Skills. Das ist auf Hermes der
**einzige** Weg dorthin: Ein Hook kann hier, anders als in Claude Code, keine Variable
in die Session exportieren.

`ENGRAM_ROOT` ist zugleich der Notausgang, auf den der unveränderte Upstream-Resolver
anspringt. `ENGRAM_STATE_REPO` brauchen die beiden Zusatzwerkzeuge, falls das
Geschwister-Layout doch einmal nicht steht.

Die vierte Zeile ist der Code-Riegel aus `.hermes/hooks/engram-env.sh`: Fehlt sie,
bleiben beide Hooks in JEDER Session still — auch in diesem Profil. Sie ist die
Rückfallebene für den Fall, dass `.env` einmal nicht in die Prozessumgebung eines
Hooks vererbt wird (z. B. bei einem Cron-Skript, siehe Schritt 6): Der Resolver
lädt die Datei dann selbst nach, ausschließlich `ENGRAM_*`-Zeilen.

---

## 4 · `~/.hermes/profiles/engram/config.yaml`

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

hooks_auto_accept: true
```

Danach `SOUL.md` einspielen — das ist der einzige Kanal, der unabhängig vom
Arbeitsverzeichnis in jeder Session dieses Profils geladen wird:

```bash
cp ~/engram/.hermes/SOUL.snippet.md ~/.hermes/profiles/engram/SOUL.md
```

Kein Einsortieren wie bei `config.yaml` — `SOUL.md` ist eine eigenständige Datei,
kein Abschnitt in einer bestehenden.

Drei Fallen:

- Bei `external_dirs` wird `~` expandiert, bei `command` **nicht**. Hook-Kommandos
  deshalb absolut schreiben.
- Beim ersten Feuern fragt Hermes je (Event, Kommando) einmal nach Zustimmung und
  merkt sie sich in `~/.hermes/profiles/engram/shell-hooks-allowlist.json`. Mit
  `hooks_auto_accept: true` (siehe oben) entfällt das hier — begründet in
  `config.snippet.yaml` selbst: Cron und der Gateway-Bot haben kein TTY für den
  Prompt.
- `hooks_auto_accept: true` gilt nur in diesem Profil — in `~/.hermes/config.yaml`
  (ohne `-p engram`) darf dieser Schlüssel nicht stehen, sonst gilt er global.

Danach Hermes neu starten (Desktop-App: beenden und öffnen, nicht nur das Fenster
schließen). Die Desktop-App und die CLI teilen sich `~/.hermes` als Datenverzeichnis
vollständig — was hier in `~/.hermes/profiles/engram/` eingerichtet wird, ist für
beide sichtbar. **Das reicht aber nicht, um es auch zu benutzen:**

**In der Desktop-App das Profil aktiv umschalten.** Die App öffnet nach dem
Neustart nicht automatisch `engram` — sie behält das zuletzt aktive Profil (in
der Regel das Standardprofil). Umschalten über die **Profil-Leiste in der
Seitenleiste** (Profil `engram` anklicken) oder `⌘K` → Profil wechseln. Erst
danach laufen `/engram-status` & Co. dort, wo die beiden Hooks tatsächlich
registriert sind — im Standardprofil sind die Skills nicht einmal im Index,
`/engram-status` würde dort schlicht nicht existieren, ohne dass irgendetwas
eine Fehlermeldung zeigt.

**Kontrollfrage, bevor es weitergeht:** Zeigt die Profil-Leiste `engram` als
aktiv? Erst wenn ja, macht Schritt 5 unten überhaupt Sinn.

---

## 5 · Verifikation

Alle sieben Prüfungen ausführen und die Ausgabe vergleichen. Die dritte (jetzt: fünfte)
ist die wichtigste — sie beweist die ganze Verdrahtung auf einmal.

```bash
# 0a · Riegel — außerhalb des Profils bleiben beide Hooks still
echo '{"session_id":"probe-0a"}' | env -u ENGRAM_HERMES -u HERMES_HOME \
  bash ~/engram/.hermes/hooks/session-start.sh
#    erwartet: {}  — auch wenn ENGRAM_HERMES in der Profil-.env steht: dieser Aufruf
#    hat keine Hermes-Prozessumgebung und kein HERMES_HOME, findet die Datei also nicht.

# 0b · innerhalb des Profils antwortet der Hook wirklich
echo '{"session_id":"probe-0b"}' | HERMES_HOME=~/.hermes/profiles/engram \
  bash ~/engram/.hermes/hooks/session-start.sh | python3 -m json.tool | head -5
#    erwartet: ein JSON-Objekt mit "context" — das Briefing. Das ist der Beweis,
#    dass Riegel UND Profil-Isolation beide wie vorgesehen funktionieren.

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
#    steht dort etwas mit ".claude/learning", ist Schritt 3 nicht angekommen:
#    Hermes wurde nicht neu gestartet, oder .env hat einen Tippfehler. NICHT weitergehen.

# 4 · Der Sessionstart-Hook antwortet gültig — innerhalb des Profils, wie 0b:
# ohne HERMES_HOME auf die Profil-.env zu zeigen, greift seit dem Riegel (Schritt 1/3)
# derselbe stille {}-Pfad wie in 0a, auch wenn dieser Aufruf sonst alles richtig macht.
echo '{"session_id":"probe-1"}' | HERMES_HOME=~/.hermes/profiles/engram \
  bash ~/engram/.hermes/hooks/session-start.sh | python3 -m json.tool | head -5
#    erwartet: ein JSON-Objekt mit "context" (Briefing + ggf. Fälligkeiten)
echo '{"session_id":"probe-1"}' | HERMES_HOME=~/.hermes/profiles/engram \
  bash ~/engram/.hermes/hooks/session-start.sh
#    erwartet: genau {}  — die Dedupe-Sperre greift, kein zweites Briefing pro Session

# 5 · Der Speicher-Hook ist bei sauberem Baum still
echo '{"session_id":"probe-1"}' | HERMES_HOME=~/.hermes/profiles/engram \
  bash ~/engram/.hermes/hooks/engram-save.sh
#    erwartet: {} auf stdout und nichts auf stderr

# 6 · SOUL.md ist eingespielt
head -3 ~/.hermes/profiles/engram/SOUL.md
#    erwartet: die Überschrift "# SOUL.md — Profil `engram`"

# 7 · Die Verdrahtung steht NICHT global
grep -q "engram" ~/.hermes/config.yaml && echo "FEHLER: engram-Hooks stehen in der globalen config.yaml" || echo "ok: global sauber"
#    erwartet: "ok: global sauber" — sonst feuert die Verdrahtung wieder überall,
#    genau der Defekt, den das eigene Profil beheben sollte.
```

Dann in Hermes selbst: `/engram-status` eingeben. Der Skill muss auftauchen (er kommt
aus `external_dirs`) und mit einem Bootstrap-Block starten, der `ENGRAM_ROOT` und
`ENGRAM_HOME` **gefüllt** ausgibt.

**Abweichung von Prüfungen 4/5 vor diesem Umzug:** Vor dem eigenen Profil liefen diese
beiden Aufrufe ohne `HERMES_HOME`-Präfix — der Riegel aus Schritt 1 macht sie seither
davon abhängig, sonst antworten sie still mit `{}` statt mit dem Briefing, und das sähe
wie ein Fehler in der Kette aus, ist aber nur die fehlende Profil-Umgebung in einem
manuell gestarteten Terminal.

---

## 6 · Gateway/Cron einrichten

Die Fähigkeit, für die sich der Umzug lohnt: eine Fälligkeits-Nudge aufs Handy,
plus eine wöchentliche Gesundheitsmeldung, falls der Auto-Save je scheitert.

**Die Reihenfolge unten ist zwingend, nicht nur naheliegend.** Cron-Jobs feuern
NICHT, weil sie registriert sind — sie feuern, weil ein Gateway-Prozess läuft,
der sie jede Minute abklopft. Weder die Desktop-App selbst noch `gateway setup`
allein starten diesen Prozess; `gateway setup` registriert nur den Telegram-Bot.
Ohne den Install-Schritt unten stehen die Jobs für immer registriert und feuern
nie — und das sieht von außen genau wie „funktioniert, meldet aber nichts".

```bash
hermes -p engram gateway setup                        # Telegram-Bot, interaktiv
hermes -p engram gateway install                       # DEN TICKER als Dienst installieren
hermes -p engram gateway start                          # und starten — ohne das: kein Tick, nie
hermes -p engram cron create --no-agent \
  --script ~/engram/.hermes/hooks/session-start.sh \
  --deliver telegram --schedule "0 8 * * *"            # täglich 8 Uhr: Fälligkeiten
hermes -p engram cron create --no-agent \
  --script ~/engram/.hermes/hooks/engram-health.sh \
  --deliver telegram --schedule "0 8 * * 1"             # montags 8 Uhr: Sync-Gesundheit
hermes -p engram gateway status                          # muss "running" zeigen
```

`session-start.sh` erkennt leeres stdin automatisch (Klartext-Modus, siehe die
Kommentare am Kopf der Datei) und schweigt, wenn nichts fällig ist — der Cron
verschickt dann einfach nichts. `engram-health.sh` verschickt grundsätzlich nur
bei einer Abweichung.

**Das Öffnen der Desktop-App ersetzt `gateway install`/`start` nicht.** Die
Scheduler-Ticks laufen ausschließlich im separaten Gateway-Prozess, nicht im
Chat-Fenster — offene Frage, in „Grenzen" unten festgehalten: ob dieser Prozess
einen Neustart des Rechners übersteht, oder ob `gateway install` (statt nur
`gateway start`) dafür nötig ist, ist plattformabhängig und hier nicht geprüft.

**Nicht verifiziert.** Upstream markiert genau diese Art Cron-Zustellung
(`--deliver telegram` an ein `--no-agent`-Skript) ausdrücklich als „not yet
verified" — die Flags oben stammen aus der Hermes-Dokumentation, nicht aus einem
beobachteten Lauf. Nach der Einrichtung von Hand nachsehen:

```bash
hermes -p engram cron list
#    erwartet: beide Jobs mit dem richtigen Schedule
```

und danach abwarten (oder testweise einen Job mit `hermes -p engram cron run
<id>` manuell auslösen, falls dieser Unterbefehl existiert) und in Telegram
prüfen, ob die Nachricht wirklich ankommt. Kommt nichts an, obwohl `cron list`
den Job zeigt: `hooks_auto_accept` in Schritt 4 prüfen (ohne `true` bleibt der
Job beim Zustimmungs-Prompt hängen, den niemand beantwortet) und ob
`gateway setup` wirklich abgeschlossen wurde.

**Es verlassen nur Metadaten den Rechner** — Fälligkeits-Zahlen, keine
Lernerantworten. `engram-health.sh` verschickt nur Pfade und Zählwerte.

**Der Rechner muss laufen.** Ein Cron-Job auf einem zugeklappten Laptop feuert
nicht — das gilt für beide Jobs oben.

---

## 7 · Der erste echte Lauf

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
`post_llm_call`-Hook ist nicht bestätigt. Dann Schritt 4 nachsehen.

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
hält. Genau dafür sind Schritt 5 und 7 da — sie sind keine Formsache. Upstream markiert
seinen eigenen Hermes-Teil aus demselben Grund teilweise als „not yet verified"; diese
Ehrlichkeit wird hier fortgeschrieben, nicht überschrieben.

- **Der `ENGRAM_HERMES`-Riegel ist nur gegen die Dokumentation geschrieben, nicht
  gegen eine echte Hermes-Installation verifiziert** — insbesondere, ob Hermes
  `.env` tatsächlich so an Cron-Subprozesse vererbt (oder eben nicht) wie
  angenommen. Die Prüfungen 0a/0b in Schritt 5 sind der Ersatz dafür; sie zeigen
  nur, dass die Hook-Logik selbst korrekt reagiert, nicht dass Hermes sie in der
  Praxis genauso aufruft.
- **Ob `hermes profile create` und `hermes -p engram` sich wie hier beschrieben
  verhalten, ist ebenfalls nur gegen die Dokumentation geschrieben.** Kein Lauf
  gegen eine echte Installation lag vor. Schritt 1 und 6 tragen deshalb dasselbe
  Risiko wie der Cron-Teil oben.
- **`gateway install` vs. `gateway start` — welches einen Neustart des Rechners
  übersteht, ist plattformabhängig und hier nicht geprüft.** `install` richtet
  laut Dokumentation einen systemd-/launchd-Dienst ein, `start` läuft nur
  vordergründig für die Dauer der Shell-Sitzung. Feuert der Nudge nach dem
  nächsten Neustart nicht mehr: `hermes -p engram gateway status` prüfen und
  bei Bedarf `gateway install` nachholen.
- **Die Profil-Leiste der Desktop-App (Schritt 4) ist ebenfalls nur gegen die
  Dokumentation geschrieben**, nicht gegen eine laufende App gesehen. Zeigt die
  Sidebar keine Profil-Leiste (ältere Desktop-Version?), bleibt der CLI-Weg
  (`engram chat`, der Alias aus Schritt 1) der verlässliche Rückweg.

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
