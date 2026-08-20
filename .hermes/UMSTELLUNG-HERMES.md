# Umstellung an Hermes — bestehendes Engram-Setup aktualisieren

**An den Agenten, der das hier liest:** Arbeitsauftrag, keine Erzählung. Auf diesem
Rechner läuft bereits eine **ältere** Engram-Verdrahtung (global in `~/.hermes`,
ohne Profil). Sie wird auf die neue Fassung umgestellt: eigenes Profil `engram`,
Riegel gegen Fremdsessions, Nudge aufs Handy, ein einziger Schreiber auf `main`.

Für eine **Erstinstallation** ist das hier das falsche Dokument — dann
`.hermes/UEBERGABE-HERMES.md` nehmen.

Zeit: etwa 20 Minuten. **In einem Zug durcharbeiten**, Grund steht direkt darunter.

---

## Das Wichtigste zuerst

Der neue Code hat einen Riegel: Beide Hooks steigen still aus, wenn
`ENGRAM_HERMES=1` fehlt. Diese Variable gibt es im alten Setup nicht.

**Folge: In dem Moment, in dem Schritt 2 das Repo aktualisiert, hört der Auto-Save
auf — und zwar lautlos.** Nichts stürzt ab, nichts warnt, der Lernstand wird ab da
nur noch lokal geschrieben und nicht mehr gepusht. Erst Schritt 3 macht ihn wieder
scharf.

Deshalb: **Schritt 0 vor allem anderen**, und zwischen Schritt 2 und 4 nicht
pausieren. Wird die Umstellung in der Mitte abgebrochen, ist nichts verloren — aber
bis sie fertig ist, darf in Hermes nicht gelernt werden.

Der Riegel ist Absicht, kein Nebeneffekt: Ohne ihn fand der Resolver `~/engram`
in *jeder* Hermes-Session und injizierte das Engram-Briefing auch in Sessions über
völlig andere Themen.

---

## Schritt 0 · Lernstand sichern, bevor irgendetwas angefasst wird

```bash
git -C ~/engram-learning status --short
git -C ~/engram-learning rev-parse --abbrev-ref HEAD     # muss: main
git -C ~/engram-learning log --oneline -1
git -C ~/engram-learning push origin HEAD:main
```

- **Nicht `main`?** Anhalten und melden. Alles Weitere setzt `main` voraus; die
  neuen Hooks pushen ausschließlich dorthin.
- **`status` zeigt Änderungen?** Erst committen und pushen:
  `git -C ~/engram-learning add -A -- learning sources && git -C ~/engram-learning commit -m "engram: Stand vor der Umstellung" && git -C ~/engram-learning push origin HEAD:main`
- **`push` meldet „Everything up-to-date"?** Perfekt — der Stand liegt sicher auf
  dem Remote, und die Umstellung kann nichts mehr kosten.

Diese vier Zeilen sind die eigentliche Versicherung dieses Dokuments. Der Lernstand
lebt im Git-Repo, nicht in der Hermes-Konfiguration — ist er gepusht, ist jeder
weitere Schritt umkehrbar.

## Schritt 1 · Bestandsaufnahme — die alten Werte merken

```bash
cat ~/.hermes/.env | grep ENGRAM        # die drei Pfade
grep -n -A4 "engram" ~/.hermes/config.yaml
hermes --version                        # muss >= 0.5.0 sein
ls ~/.hermes/profiles/ 2>/dev/null      # existiert schon ein Profil?
```

Erwartet wird eine Verdrahtung wie diese (die alte Fassung):

- `~/.hermes/.env` mit `ENGRAM_ROOT`, `ENGRAM_HOME`, `ENGRAM_STATE_REPO`
- `~/.hermes/config.yaml` mit `skills.external_dirs: [~/engram/.hermes/skills]` und
  zwei Hooks (`pre_llm_call` → `session-start.sh`, `post_llm_call` → `engram-save.sh`)

**Die drei Pfadwerte notieren** — sie werden in Schritt 3 unverändert übernommen.
Sieht es anders aus als beschrieben, das Abweichende melden und nicht raten.

**Läuft dieser Rechner unter Windows (Git-Bash/MSYS)?** Dann vor Schritt 6
(Verifikation) einmal `.hermes/PLATTFORM.md` §7 lesen. Zwei Host-Eigenheiten dort —
ein Python-Store-Stub, der `python3` vortäuscht, aber nicht läuft, und `pwd`-Pfade,
die `git -C` nicht versteht — sind seit dem letzten Update der Verdrahtung im Code
selbst abgefangen (`ENGRAM_PY`/`_engram_native_path` in `engram-env.sh`), aber die
Verifikationsbefehle unten laufen von Hand im Terminal und damit außerhalb dieser
Absicherung. Wer §7 erst nach einem stillen Fehlschlag liest, hat die Ursache dann
schon gesucht, statt sie vorher zu kennen.

## Schritt 2 · Das Engine-Repo aktualisieren

```bash
git -C ~/engram status --short          # muss leer sein
git -C ~/engram pull --ff-only origin main
git -C ~/engram log --oneline -1
```

`--ff-only` mit Absicht: Gibt es lokale Commits im Fork, soll das **abbrechen**
statt zu mergen — dann melden, was da liegt, statt eine fremde Änderung zu
begraben.

**Ab hier ist der Auto-Save inaktiv** (siehe „Das Wichtigste zuerst"). Weiter mit
Schritt 3, ohne Umweg.

Gegenprobe, dass die neue Fassung da ist:

```bash
test -f ~/engram/.hermes/SOUL.snippet.md && test -f ~/engram/.hermes/hooks/engram-health.sh && echo "neue Fassung da"
```

## Schritt 3 · Profil `engram` anlegen und Konfiguration umziehen

```bash
hermes profile create engram            # → ~/.hermes/profiles/engram, Alias ~/.local/bin/engram
```

**Die `.env`** — `<DU>` durch den eigenen Benutzernamen ersetzen; die drei Pfade aus
Schritt 1 unverändert übernehmen, die vierte Zeile ist neu:

```bash
cat >> ~/.hermes/profiles/engram/.env <<'ENV'
ENGRAM_ROOT=/Users/<DU>/engram
ENGRAM_HOME=/Users/<DU>/engram-learning/learning
ENGRAM_STATE_REPO=/Users/<DU>/engram-learning
ENGRAM_HERMES=1
ENV
```

`ENGRAM_HERMES=1` ist der Riegel. Ohne diese eine Zeile bleibt alles Weitere still.

**Die `config.yaml`:** Inhalt von `~/engram/.hermes/config.snippet.yaml` nach
`~/.hermes/profiles/engram/config.yaml` übertragen, `<DU>` ersetzen. Hook-Kommandos
müssen **absolut** sein (bei `external_dirs` wird `~` expandiert, bei `command` nicht).

Gegenüber der alten globalen Fassung sind zwei Dinge neu: `hooks_auto_accept: true`
(Cron und Gateway laufen ohne TTY und könnten den Zustimmungs-Prompt nie
beantworten) und `timeout: 120` auch für den Speicher-Hook.

**Das `SOUL.md`:**

```bash
cp ~/engram/.hermes/SOUL.snippet.md ~/.hermes/profiles/engram/SOUL.md
```

Es wird in jeder Session dieses Profils geladen, unabhängig vom Arbeitsverzeichnis,
und trägt die drei bindenden Regeln. Existiert dort schon ein `SOUL.md`, **nicht
überschreiben** — Inhalte zusammenführen und das melden.

**In der Desktop-App das Profil aktiv umschalten.** Die App merkt sich das zuletzt
aktive Profil (bisher: das Standardprofil) und öffnet nicht automatisch `engram`,
nur weil es jetzt existiert. Umschalten über die **Profil-Leiste in der
Seitenleiste** (Profil `engram` anklicken) oder `⌘K` → Profil wechseln. Ohne diesen
Schritt läuft `/engram-status` weiterhin im Standardprofil, wo der Skill nicht
einmal im Index steht — die Umstellung sähe komplett aus, würde aber nichts davon
tatsächlich benutzen.

## Schritt 4 · Die alte globale Verdrahtung entfernen

Jetzt, nicht später. Sie ist seit Schritt 2 wirkungslos (der Riegel greift), aber
tote Konfiguration ist die, die beim nächsten Problem in die Irre führt.

Aus `~/.hermes/config.yaml` **entfernen**:

- den kompletten `hooks:`-Block mit `session-start.sh` und `engram-save.sh`
- den `~/engram/.hermes/skills`-Eintrag unter `skills.external_dirs`
  (steht dort sonst nichts mehr, kann `external_dirs` ganz weg)

Aus `~/.hermes/.env` **entfernen**: die drei `ENGRAM_*`-Zeilen.

**Andere Einträge nicht anfassen.** Die globale `config.yaml` gehört auch anderer
Arbeit; Modellwahl, Speicher- und Kompressionseinstellungen bleiben, wie sie sind.

Danach einmal prüfen, dass die globale Konfiguration noch gültiges YAML ist:

```bash
python3 -c "import yaml;yaml.safe_load(open('$HOME/.hermes/config.yaml'));print('YAML ok')"
```

## Schritt 5 · Modell im neuen Profil setzen

Das Profil startet mit der Standardwahl, nicht mit der des alten Setups.

```yaml
# ~/.hermes/profiles/engram/config.yaml
model:
  default: "minimax/minimax-m3"
  provider: "nous"
```

Begründung und Alternativen: `.hermes/UEBERGABE-HERMES.md`, Abschnitt „Das Modell".
Kurz: 0,30 $/M Input bei 1M Kontext, und die Ranglisten, die zu dieser Arbeit passen,
sind Terminal-Bench und MCP Atlas — nicht Prosa-Ranglisten.

Optional, spart im Dauerbetrieb:

```yaml
auxiliary:
  compression:
    model: "qwen/qwen3.7-flash"
    provider: "nous"
```

## Schritt 6 · Verifikation

Alle Prüfungen ausführen und die Ausgabe vergleichen. Die dritte und die vierte sind
die, für die diese Umstellung gemacht wird.

```bash
# 1 · Engine intakt
python3 ~/engram/scripts/engram.py selftest
#    erwartet: 315/315 (oder mehr) bestanden

# 2 · Zeigt die Engine ins private Repo?
HERMES_HOME=~/.hermes/profiles/engram python3 ~/engram/scripts/engram.py doctor \
  | python3 -m json.tool | grep home
#    erwartet: "home": "/Users/<DU>/engram-learning/learning"
#    steht da etwas mit ".claude/learning": .env hat einen Tippfehler. Anhalten.

# 3 · DER RIEGEL — greift er in beide Richtungen?
echo '{"session_id":"p1"}' | env -u ENGRAM_HERMES bash ~/engram/.hermes/hooks/session-start.sh
#    erwartet: genau {}   — eine fremde Session bekommt KEIN Briefing mehr
echo '{"session_id":"p2"}' | ENGRAM_HERMES=1 bash ~/engram/.hermes/hooks/session-start.sh \
  | python3 -m json.tool | head -3
#    erwartet: ein Objekt mit "context" (Briefing, ggf. Fälligkeiten)

# 4 · Speicher-Hook still bei sauberem Baum
echo '{"session_id":"p2"}' | ENGRAM_HERMES=1 bash ~/engram/.hermes/hooks/engram-save.sh
#    erwartet: {} auf stdout, nichts auf stderr

# 5 · Gesundheitscheck
ENGRAM_HERMES=1 bash ~/engram/.hermes/hooks/engram-health.sh
#    erwartet: keine Ausgabe (= Lernstand deckt sich mit origin/main)
```

Dann in Hermes selbst, **im neuen Profil**:

```bash
engram chat            # der von `hermes profile create` angelegte Alias
```

Dort `/engram-status` eingeben. Erwartet: Der Skill existiert, sein Bootstrap-Block
gibt `ENGRAM_ROOT` und `ENGRAM_HOME` **gefüllt** aus, und es kommt **keine** Warnung
über einen fehlenden Auto-Save-Hook.

Zuletzt die Gegenprobe, die das Ziel der Umstellung belegt — eine Session **außerhalb**
des Profils:

```bash
hermes chat            # Standardprofil, irgendeine belanglose Frage
```

Erwartet: **kein** Engram-Briefing, kein Nudge. Genau das war vorher kaputt.

## Schritt 7 · Der Nudge aufs Handy (neu, optional)

Die Fähigkeit, für die sich die Umstellung lohnt: FSRS steht und fällt damit, ob die
Wiederholung täglich passiert.

**Die Reihenfolge unten ist zwingend, nicht nur naheliegend.** Cron-Jobs feuern
NICHT, weil sie registriert sind — sie feuern, weil ein Gateway-Prozess läuft, der
sie jede Minute abklopft. `gateway setup` registriert nur den Telegram-Bot, startet
aber keinen Dienst. Ohne den Install-Schritt unten stehen die Jobs für immer
registriert und feuern nie — das sieht von außen genau wie „funktioniert, meldet
aber nichts" aus.

```bash
hermes -p engram gateway setup          # Telegram-Bot einrichten
hermes -p engram gateway install        # DEN TICKER als Dienst installieren
hermes -p engram gateway start          # und starten — ohne das: kein Tick, nie
hermes -p engram cron create --no-agent \
  --script ~/engram/.hermes/hooks/session-start.sh \
  --deliver telegram --schedule "0 8 * * *"
hermes -p engram cron create --no-agent \
  --script ~/engram/.hermes/hooks/engram-health.sh \
  --deliver telegram --schedule "0 8 * * 1"
hermes -p engram cron list
hermes -p engram gateway status         # muss "running" zeigen
```

Der erste Job schickt täglich um 8 Uhr „N Wiederholungen fällig" und **schweigt,
wenn nichts fällig ist**. Der zweite meldet montags, falls der Lernstand von
`origin/main` abweicht.

**Das Öffnen der Desktop-App ersetzt `gateway install`/`start` nicht.** Die
Scheduler-Ticks laufen ausschließlich im separaten Gateway-Prozess, nicht im
Chat-Fenster — ob dieser Prozess einen Neustart des Rechners übersteht oder
`gateway install` (statt nur `gateway start`) dafür nötig ist, ist
plattformabhängig und hier nicht geprüft.

Drei Dinge ehrlich dazu:

- **Es verlassen nur Metadaten den Rechner** — Zahlen, keine Lernerantworten.
  Wiederholungen selbst laufen weiter am Rechner; das ist eine bewusste Entscheidung
  wegen bindender Regel 2 und keine technische Grenze.
- **Nicht verifiziert.** Die Flags stammen aus der Hermes-Dokumentation, nicht aus
  einem beobachteten Lauf; upstream markiert genau diese Cron-Zustellung selbst als
  „not yet verified". Wenn die Zustellung ausbleibt: `hermes -p engram cron list`
  und der Gateway-Status sind die ersten Anlaufstellen — und es ist kein Zeichen
  dafür, dass die Umstellung schiefging.
- **Der Rechner muss laufen.** Ein Cron-Job auf einem zugeklappten Laptop feuert nicht.

---

## Wenn etwas schiefgeht — der Rückweg

Der Lernstand ist seit Schritt 0 auf `origin/main` und von alldem nicht betroffen.
Rückgängig zu machen ist nur die Verdrahtung:

1. `~/.hermes/config.yaml` wieder um die alten `hooks:`- und `external_dirs`-Einträge
   ergänzen, die drei `ENGRAM_*`-Zeilen zurück in `~/.hermes/.env`.
2. Zusätzlich `ENGRAM_HERMES=1` dort eintragen — **ohne diese Zeile bleibt auch die
   alte Verdrahtung mit dem neuen Code stumm.**
3. Das Profil kann stehen bleiben; es stört nichts.

Der Preis dieses Rückwegs ist genau der Defekt, wegen dem umgestellt wurde: Jede
Hermes-Session bekommt wieder das Engram-Briefing. Als Übergangslösung tragbar,
als Dauerzustand nicht.

## Was die Umstellung *nicht* mitnimmt

- **Chatverlauf und Sessions** des alten Setups bleiben im Standardprofil. Sie
  wandern nicht mit — und müssen es nicht: Der Lernstand liegt im Git-Repo, nicht im
  Gesprächsverlauf. Es geht nichts verloren, was Engram braucht.
- **Die Marker-Datei** `~/.hermes/.engram-hooks-active` des alten Setups wird
  bedeutungslos; die neue liegt im Profil und entsteht beim ersten Lauf von selbst.
- **`~/.hermes/shell-hooks-allowlist.json`** des Standardprofils behält die alten
  Zustimmungen für die beiden Hook-Kommandos. Harmlos — die Hooks sind dort ja
  ausgetragen. Wer aufräumen will, kann die zwei Einträge entfernen.
