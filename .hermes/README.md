# `.hermes/` — Engram auf Hermes Agent

Die Verdrahtung für [Hermes Agent](https://hermes-agent.nousresearch.com) (Desktop-App
und CLI, dieselbe Konfiguration). Gegenstück zu `.claude/`, dasselbe Prinzip: Der
Upstream-Code bleibt unangetastet, alles Plattformspezifische lebt in einem Verzeichnis,
das es upstream nicht gibt — deshalb kollidiert ein `git merge upstream/main` nie.

| Datei | Rolle |
|---|---|
| `UEBERGABE-HERMES.md` | **Hier anfangen.** Der Einrichtungsauftrag, Schritt 1–5, mit Prüfungen |
| `PLATTFORM.md` | die bindenden Übersetzungen Claude Code → Hermes (`delegate_task`, Marker-Datei, kein Artifact-Weg) |
| `config.snippet.yaml` | die Blöcke für `~/.hermes/config.yaml` |
| `hooks/engram-env.sh` | gemeinsamer Resolver (Checkout + State-Repo), von beiden Hooks gesourct |
| `hooks/session-start.sh` | `pre_llm_call`: Lernstand pullen, Briefing, Fälligkeits-Nudge — einmal pro Session |
| `hooks/engram-save.sh` | `post_llm_call`: committen und nach `main` pushen — nach jedem Turn |
| `skills/engram-*/SKILL.md` | die fünf Kommandos; dünne Aliase auf die Fassungen unter `.claude/skills/` |

Upstream hat einen eigenen, schlankeren Hermes-Pfad (`INSTALL-HERMES.md`: `skills/` per
`external_dirs`, ein Nudge-Hook). Der bleibt gültig und unangetastet. Was hier dazukommt,
ist der Teil, den nur dieser Fork hat: die fünf `engram-*`-Kommandos, die beiden
Zusatzwerkzeuge — und vor allem die Anbindung an das private State-Repo, ohne die beide
Plattformen getrennte Lernstände führen würden.
