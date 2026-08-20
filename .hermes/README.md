# `.hermes/` — Engram auf Hermes Agent

Die Verdrahtung für [Hermes Agent](https://hermes-agent.nousresearch.com) (Desktop-App
und CLI, dieselbe Konfiguration). Gegenstück zu `.claude/`, dasselbe Prinzip: Der
Upstream-Code bleibt unangetastet, alles Plattformspezifische lebt in einem Verzeichnis,
das es upstream nicht gibt — deshalb kollidiert ein `git merge upstream/main` nie.

**Gehört in ein eigenes Hermes-Profil `engram`** (`hermes profile create engram`,
Übergabedatei Schritt 1), nicht in die Standard-Installation. Ohne die Abgrenzung
fände der Resolver in `hooks/engram-env.sh` `$HOME/engram` in jeder Hermes-Session
auf dem Rechner und injizierte das Engram-Briefing auch dort, wo es nicht hingehört
— der Code-Riegel `ENGRAM_HERMES=1` in derselben Datei ist die zweite, unabhängige
Absicherung dafür, das Profil die strukturelle.

| Datei | Rolle |
|---|---|
| `UMSTELLUNG-HERMES.md` | **Läuft hier schon eine ältere Fassung?** Dann hier anfangen — Umstellung eines bestehenden Setups auf Profil, Riegel und Nudge |
| `UEBERGABE-HERMES.md` | **Hier anfangen.** Der Einrichtungsauftrag, Schritt 1–7, mit Prüfungen |
| `PLATTFORM.md` | die bindenden Übersetzungen Claude Code → Hermes (`delegate_task`, Marker-Datei, kein Artifact-Weg) |
| `SOUL.snippet.md` | Vorlage für `~/.hermes/profiles/engram/SOUL.md` — Rolle + die drei bindenden Regeln, geladen unabhängig vom Arbeitsverzeichnis |
| `config.snippet.yaml` | die Blöcke für `~/.hermes/profiles/engram/config.yaml`, inkl. `hooks_auto_accept` und der Cron-Kommandos für den Fälligkeits-Nudge aufs Handy |
| `hooks/engram-env.sh` | gemeinsamer Resolver (Checkout + State-Repo) samt `ENGRAM_HERMES`-Riegel, von allen drei Hooks gesourct |
| `hooks/session-start.sh` | `pre_llm_call`: Lernstand pullen, Briefing, Fälligkeits-Nudge — einmal pro Session, per Cron auch als tägliche Telegram-Zustellung |
| `hooks/engram-save.sh` | `post_llm_call`: committen und nach `main` pushen — nach jedem Turn |
| `hooks/engram-health.sh` | Wochen-Cron: meldet, wenn das State-Repo von `origin/main` abweicht — die zweite Meldeleitung, falls ein Push je still scheitert |
| `skills/engram-*/SKILL.md` | die fünf Kommandos; dünne Aliase auf die Fassungen unter `.claude/skills/` |

Upstream hat einen eigenen, schlankeren Hermes-Pfad (`INSTALL-HERMES.md`: `skills/` per
`external_dirs`, ein Nudge-Hook). Der bleibt gültig und unangetastet. Was hier dazukommt,
ist der Teil, den nur dieser Fork hat: die fünf `engram-*`-Kommandos, die beiden
Zusatzwerkzeuge — und vor allem die Anbindung an das private State-Repo, ohne die beide
Plattformen getrennte Lernstände führen würden.
