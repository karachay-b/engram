# Engram — Kurzbriefing für diese Session

Zwei Repos, eine Aufgabe: **Der Nutzer lernt, die Engine merkt sich den Stand.**

| Repo | Rolle | Sichtbarkeit |
|---|---|---|
| `engram` | Lern-Engine (`scripts/engram.py`) + Cloud-Verdrahtung unter `.claude/` | öffentlich |
| `engram-learning` | Lernstand (`learning/`) + aufbereitete Quellen (`sources/`) | **privat** |

**Die Verzahnung:** `ENGRAM_HOME` zeigt aus dem Engine-Repo in das State-Repo
(`<engram-learning>/learning`). Die Engine liest und schreibt nur dort. Der Stop-Hook
committet und pusht nach jedem Turn dorthin — **ohne Push ist der Lernstand mit dem
Container weg.** Meldet er einen fehlgeschlagenen Push, muss er von Hand nachgeholt
werden, bevor die Session endet.

**Gelernt wird auf Hermes.** Das Profil `engram` führt `/engram-learn` & Co. aus
und pusht den Lernstand nach jedem Turn. Diese Claude-Code-Session hier ist für
Setup-Arbeit da — Upstream-Merges, Refactorings, Änderungen an `.claude/`/`.hermes/`
— nicht für den täglichen Lernpfad. Die Kommandos laufen trotzdem: Der Stop-Hook
speichert weiterhin, jetzt als Rückfallweg (siehe `CLAUDE.md`).

## Die fünf Kommandos

| Kommando | Wozu |
|---|---|
| `/engram-learn <thema>` | Neues lernen oder fortsetzen — Kurrikulum, Tutoring, blinde Bewertung |
| `/engram-review` | Fällige Wiederholungen abarbeiten (die Zwei-Minuten-Gewohnheit) |
| `/engram-coach` | Telemetrie, Strategie, Kalibrierung, Experimente, Tuning |
| `/engram-source` | Buch/PDF als Lernstoff aufbereiten (Chunks mit Seitenverweisen) |
| `/engram-status` | Momentaufnahme: Quellen, Lernpfad-Stand, kommende Fälligkeiten als Seite |

## Drei bindende Regeln

1. **Lernertext nie auf die Kommandozeile.** Freitext (Antworten, Lernziele, Buchtext)
   erreicht `engram.py` nur über `--file`, `--json -` oder `--production-file -`.
   Ein `'` oder `$(…)` in einer Antwort wäre sonst eine Command-Injection.
2. **Quellen-Derivate bleiben privat.** Buchtext, wörtliche Zitate und Lernerantworten
   gehören nie in den öffentlichen Fork, nie in eine Artifact-Seite, nie in einen
   GitHub-Kommentar. Metadaten (Titel, Seitenzahl, Chunkzahl) sind unbedenklich.
3. **Pfade nie raten.** Den echten State-Pfad immer aus `engram.py doctor` (Feld `home`)
   lesen. `~/.claude/learning` stimmt hier **nicht**.

## Wenn oben eine Upstream-Meldung steht

Der Sessionstart prüft höchstens einmal täglich, ob `nagisanzenin/engram` weitergezogen
ist. Steht dort eine Meldung und der Nutzer stimmt zu:

```bash
cd /home/user/engram
git remote add upstream https://github.com/nagisanzenin/engram.git   # einmalig, evtl. schon da
git fetch upstream && git merge upstream/main
python3 scripts/engram.py selftest        # muss N/N bestehen — die Gegenprobe
```

Konflikte sind unwahrscheinlich: Das Cloud-Setup lebt ausschließlich in `.claude/` und
`CLAUDE.md` — Pfade, die es upstream nicht gibt. Nach dem Merge prüfen, ob Upstream die
Skill-Namen oder deren `description`-Zeilen geändert hat; dann die Aliase nachziehen.

**Ausführliche Fassung von allem: `CLAUDE.md` im Repo-Root.**
