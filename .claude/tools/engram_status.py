#!/usr/bin/env python3
"""engram-status — eine Momentaufnahme des Lernstands, ein Aufruf, kein Geheimnis.

Gehört zum Cloud-Setup dieses Forks (alles unter .claude/), nicht zum Upstream-Code.

Entstanden, weil der erste `/engram-status`-Lauf zu lange brauchte: der Skill rief
vier `engram.py`-Kommandos einzeln auf (12.671 Byte Rohausgabe, größtenteils Prosa,
die keine Statusseite braucht) und tat das noch dazu über mehrere Bash-Zellen hinweg,
von denen jede ihre eigene Shell ist — der Bootstrap-Block einer Zelle war in der
nächsten schon wieder verschwunden. Dieses Werkzeug bündelt alles in EINEN Aufruf.

Wichtiger als die Geschwindigkeit: `engram.py due` liefert `probe`, `claim`, `rubric`
und `transfer_probe` im Volltext — genau das Material, das laut Skill niemals auf eine
teilbare Seite darf. Bisher hing die Grenze am Gedächtnis des Modells. Hier hängt sie
am Code: `build_due_entry()` kopiert nur eine feste Erlaubnisliste von Feldern, alles
andere erreicht die JSON-Ausgabe gar nicht erst. `selftest` prüft genau das.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import unicodedata

TOOL_VERSION = "engram-status 1.0"

# Felder, die aus einem `due`-Eintrag der Engine NIE übernommen werden dürfen —
# probe/claim/rubric sind Prüfungsinhalt, transfer_probe ist das Transferitem dazu.
# assert_no_forbidden() ist die Gegenprobe: sie durchsucht die fertige Ausgabe
# rekursiv nach genau diesen Schlüsseln, statt nur der Erlaubnisliste zu vertrauen.
FORBIDDEN_KEYS = {"probe", "claim", "rubric", "transfer_probe"}

# Dieses Skript liegt neben engram_source.py — resolve_state(), sources_dir() und
# der MAP.md-Parser (read_map) werden von dort importiert statt zweimal geschrieben.
# Ein zweiter, selbst gebauter Pfad-Resolver ist genau der Fehler, den
# engram_source.resolve_state() in seinem eigenen Docstring beschreibt.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engram_source as _es  # noqa: E402


def die(msg, code=2):
    sys.stderr.write("engram-status: %s\n" % msg)
    sys.exit(code)


def note(msg):
    sys.stderr.write("engram-status: %s\n" % msg)


# --------------------------------------------------------------------------- #
# Engine ansprechen — Subprozess für JSON-Kommandos, Import für die FSRS-Formel
# --------------------------------------------------------------------------- #

def resolve_engram_root():
    """Wie engram_source.engine_topics(), aber ohne an ein Kommando gebunden zu
    sein: ENGRAM_ROOT zuerst, sonst relativ zu diesem Werkzeug (.claude/tools/
    -> Repo-Wurzel). None, wenn dort kein scripts/engram.py liegt."""
    root = os.environ.get("ENGRAM_ROOT") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..")
    root = os.path.abspath(root)
    if not os.path.isfile(os.path.join(root, "scripts", "engram.py")):
        return None
    return root


def run_engine(engram_root, home, *cmd_args):
    """Ein `engram.py`-Subcommand, als geparstes JSON — oder None.

    ENGRAM_HOME wird wie in engine_topics() bewusst GESETZT statt geerbt: der
    Lernstand, über den diese Seite berichtet, ist der im State-Repo, nicht der
    einer zufälligen Umgebungsvariable. None heißt "nicht befragbar", nicht
    "leer" — der Aufrufer muss das unterscheiden, statt eine leere Antwort für
    einen leeren Lernstand zu halten.
    """
    script = os.path.join(engram_root, "scripts", "engram.py")
    env = dict(os.environ)
    env["ENGRAM_HOME"] = home
    try:
        out = subprocess.check_output([sys.executable, script, *cmd_args],
                                      env=env, stderr=subprocess.DEVNULL)
        return json.loads(out.decode("utf-8"))
    except Exception:
        return None


def try_import_engine(engram_root):
    """`scripts/engram.py` importieren, um die echte FSRS-Formel zu nutzen statt
    sie nachzubauen. `if __name__ == "__main__":` schützt main() — der Import
    selbst führt nichts aus. Schlägt er fehl (Upstream benennt retrievability()
    um, oder es gibt kein Engram hier), fehlt `recall_pct` einfach — degradieren,
    nicht sterben, wie überall in diesem Werkzeug."""
    scripts_dir = os.path.join(engram_root, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        import engram as _engram_engine
        return _engram_engine
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Die Vertraulichkeitsgrenze — Code, nicht Merksatz
# --------------------------------------------------------------------------- #

def build_due_entry(raw, engine=None, today=None):
    """Ein `due`-Eintrag der Engine, auf eine feste Erlaubnisliste reduziert.

    Das ist die einzige Stelle, die einen rohen `due`-Eintrag anfasst — jede
    andere Funktion sieht nur, was hier herauskommt. `probe`/`claim`/`rubric`/
    `transfer_probe` werden nicht ausgelassen, weil jemand daran dachte,
    sondern weil diese Funktion sie nie abfragt.
    """
    entry = {
        "topic": raw.get("topic"),
        "node": raw.get("id"),
        "due": raw.get("due"),
        "overdue_days": raw.get("overdue_days"),
        "threshold": bool(raw.get("threshold")),
        "s": raw.get("s"),
        "has_artifact": bool(raw.get("artifact")),
        "recall_pct": None,
    }
    last, s = raw.get("last"), raw.get("s")
    if engine is not None and last and isinstance(s, (int, float)):
        try:
            today = today or datetime.date.today()
            elapsed = (today - datetime.date.fromisoformat(last)).days
            entry["recall_pct"] = round(engine.retrievability(elapsed, s) * 100, 1)
        except Exception:
            pass  # recall_pct bleibt None — lieber fehlend als falsch
    return entry


def assert_no_forbidden(obj, path="$"):
    """Rekursive Gegenprobe: kein Schlüssel aus FORBIDDEN_KEYS irgendwo im
    Baum. Läuft im Selftest gegen echte Fixtures UND kann gegen die fertige
    Ausgabe eines echten Laufs verwendet werden (siehe CLAUDE.md-Verifikation)."""
    if isinstance(obj, dict):
        hit = FORBIDDEN_KEYS & set(obj.keys())
        if hit:
            return "%s enthält verbotene Schlüssel: %s" % (path, sorted(hit))
        for k, v in obj.items():
            bad = assert_no_forbidden(v, "%s.%s" % (path, k))
            if bad:
                return bad
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad = assert_no_forbidden(v, "%s[%d]" % (path, i))
            if bad:
                return bad
    return None


# --------------------------------------------------------------------------- #
# Vorschau kommender Fälligkeiten — `due` selbst kennt nur "heute und früher"
# --------------------------------------------------------------------------- #

def graphs_dir(home):
    return os.path.join(home, "graphs")


def nodes_within_horizon(graphs, today, horizon_days):
    """(topic, node-id, node-dict) für jeden Node mit `fsrs.due` echt in der
    Zukunft, höchstens `horizon_days` entfernt. Nodes ohne `due` (nie encodiert)
    und retired Nodes fallen raus — für sie gibt es keinen Termin zu zeigen.
    Bewusst EXKLUSIV von heute: die heute-und-überfällig-Liste liefert schon
    `due`, eine Überschneidung würde denselben Termin zweimal zeigen."""
    cutoff = today + datetime.timedelta(days=horizon_days)
    out = []
    for topic, g in graphs:
        for nid, node in (g.get("nodes") or {}).items():
            if node.get("state") == "retired":
                continue
            due_s = (node.get("fsrs") or {}).get("due")
            if not due_s:
                continue
            try:
                due_d = datetime.date.fromisoformat(due_s)
            except ValueError:
                continue
            if today < due_d <= cutoff:
                out.append((topic, nid, node))
    out.sort(key=lambda t: (t[2]["fsrs"]["due"], t[0], t[1]))
    return out


def load_graphs(home):
    d = graphs_dir(home)
    if not os.path.isdir(d):
        return []
    out = []
    for fname in sorted(os.listdir(d)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fname), encoding="utf-8") as fh:
                g = json.load(fh)
        except Exception:
            continue
        out.append((g.get("topic", fname[:-5]), g))
    return out


# --------------------------------------------------------------------------- #
# Auffälligkeiten
# --------------------------------------------------------------------------- #

DATE_RE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")


def goal_dates_passed(labeled_texts, today):
    """(label, Text) → Treffer, wenn der Text ein ISO-Datum in der
    Vergangenheit nennt. `label` ist mal ein Themen-Slug (Graph-`goal`), mal
    ein Index in `learner-model.json`s freier `goals`-Liste — DIE beiden
    Stellen, an denen ein Lernziel mit Datum stehen kann (docs/03
    unterscheidet "per-topic goal" von "flat list of standing aims"; ein
    Termin wie das Vorstellungsgespräch steht typischerweise in Letzterer,
    nicht im Graph — beide müssen durchsucht werden, sonst bleibt der
    häufigere Fall unentdeckt).

    Nur das Datum wandert in die Ausgabe, nie der Satz drumherum — der Skill
    entscheidet, wie viel vom Ziel er auf einer teilbaren Seite wiedergibt.
    Bewusst simpel (ein Regex, kein NLP): ein Ziel ohne erkennbares Datum ist
    kein Befund, kein falsches Alarmieren wert.
    """
    hits = []
    for label, text in labeled_texts:
        m = DATE_RE.search(text or "")
        if not m:
            continue
        try:
            d = datetime.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if d < today:
            hits.append({"label": label, "date": m.group(1)})
    return hits


def commitment_stale(model, today, min_days=2):
    """Ein gesetzter Vorsatz (`settings.commitment`), der seit `set_date` nie
    erneuert wurde. `renewed` ist eine Liste von Daten — nicht leer heißt
    schon einmal aufgefrischt, dann ist Alter kein Befund."""
    c = (model.get("settings") or {}).get("commitment") or {}
    set_s = c.get("set")
    if not set_s or c.get("renewed"):
        return None
    try:
        set_d = datetime.date.fromisoformat(set_s)
    except ValueError:
        return None
    age = (today - set_d).days
    if age < min_days:
        return None
    return {"cue": c.get("cue"), "action": c.get("action"),
            "set": set_s, "days_since": age}


# --------------------------------------------------------------------------- #
# Quellen — Titel/Umfang aus source.json, Zuordnung aus MAP.md
# --------------------------------------------------------------------------- #

def _fold(s):
    """Für den unscharfen Dateiname<->Titel-Abgleich: Akzente weg, klein,
    nur Buchstaben/Ziffern. Kein Anspruch auf Präzision — best effort, siehe
    collect_sources()."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def collect_sources(state):
    base = _es.sources_dir(state)
    _, map_rows = _es.read_map(state)
    by_source = {}
    for r in map_rows:
        by_source.setdefault(r["source"], []).append(r["topic"])

    raw_dir = os.path.join(state, "sources_raw")
    raw_files = sorted(os.listdir(raw_dir)) if os.path.isdir(raw_dir) else []
    raw_folded = [(f, _fold(f)) for f in raw_files]

    out = []
    if not os.path.isdir(base):
        return out
    for slug in sorted(os.listdir(base)):
        manifest = os.path.join(base, slug, "source.json")
        if not os.path.isfile(manifest):
            continue
        try:
            with open(manifest, encoding="utf-8") as fh:
                m = json.load(fh)
        except Exception:
            continue
        title_f = _fold(m.get("title", ""))
        raw_available = bool(title_f) and any(title_f in ff or ff in title_f
                                              for _, ff in raw_folded)
        out.append({
            "slug": slug,
            "title": m.get("title"),
            "author": m.get("author"),
            "pages": m.get("pages"),
            "chunks": m.get("chunks"),
            "words": m.get("words"),
            "topics": sorted(set(by_source.get(slug, []))),
            "raw_available": raw_available,
        })
    return out


# --------------------------------------------------------------------------- #
# Alles zusammensetzen
# --------------------------------------------------------------------------- #

def collect(state, engram_root, horizon_days):
    home = os.path.join(state, "learning")
    today = datetime.date.today()

    topics_raw = run_engine(engram_root, home, "topics") if engram_root else None
    stats = run_engine(engram_root, home, "stats") if engram_root else None
    due_raw = run_engine(engram_root, home, "due") if engram_root else None
    engine_mod = try_import_engine(engram_root) if engram_root else None

    if topics_raw is None:
        note("Engine nicht befragbar (engram.py nicht gefunden oder Fehler) — "
             "topics/stats/due bleiben leer, nicht 'nichts fällig'.")
        topics_raw, due_raw = [], []

    topics_out = [{
        "topic": t.get("topic"), "title": t.get("title"), "goal": t.get("goal"),
        "nodes": t.get("nodes"), "states": t.get("states"), "due": t.get("due"),
    } for t in topics_raw]

    due_out = [build_due_entry(r, engine_mod, today) for r in (due_raw or [])]

    graphs = load_graphs(home)
    forecast = [{
        "topic": topic, "node": nid, "due": node["fsrs"]["due"],
        "days_until": (datetime.date.fromisoformat(node["fsrs"]["due"]) - today).days,
        "threshold": bool(node.get("threshold")),
    } for topic, nid, node in nodes_within_horizon(graphs, today, horizon_days)]

    model = {}
    model_path = os.path.join(home, "learner-model.json")
    if os.path.isfile(model_path):
        try:
            with open(model_path, encoding="utf-8") as fh:
                model = json.load(fh)
        except Exception:
            pass

    adherence = (stats or {}).get("adherence", {}) or {}
    loop = adherence.get("loop_closure", {}) or {}
    flags = {
        "loop_never_closed": bool(loop.get("encoded_past_due", 0) > 0
                                  and loop.get("first_review_done", 0) == 0),
        "loop_closure": {"encoded_past_due": loop.get("encoded_past_due"),
                         "first_review_done": loop.get("first_review_done")},
        "open_misconceptions": (stats or {}).get("misconceptions_open"),
        "grader_unaudited": bool(((stats or {}).get("grader_health") or {})
                                 .get("audited") is False),
        "goal_date_passed": goal_dates_passed(
            [("thema:%s" % t["topic"], t.get("goal")) for t in topics_out]
            + [("ziel:%d" % i, g) for i, g in enumerate(model.get("goals") or [])],
            today),
        "commitment_stale": commitment_stale(model, today),
    }

    sess = adherence.get("return", {}) or {}
    totals = {
        "topics": len(topics_out),
        "concepts": sum(t.get("nodes") or 0 for t in topics_out),
        "sources": None,  # unten nach dem Einsammeln der Quellen gesetzt
        "due_now": (stats or {}).get("due_now", len(due_out)),
        "receipts": (stats or {}).get("receipts"),
        "streak_days": (stats or {}).get("streak_days"),
        "days_since_last_session": sess.get("days_since_last_session"),
    }

    sources = collect_sources(state)
    totals["sources"] = len(sources)

    return {
        "tool": TOOL_VERSION,
        "generated": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%MZ"),
        "paths": {"engram": engram_root, "state": state, "home": home},
        "totals": totals,
        "topics": topics_out,
        "due": due_out,
        "forecast": forecast,
        "sources": sources,
        "flags": flags,
    }


# --------------------------------------------------------------------------- #
# Textzusammenfassung
# --------------------------------------------------------------------------- #

STATE_LABEL = {"review": "behalten", "learning": "im Lernen", "new": "unberührt"}


def format_text(data):
    lines = []
    t = data["totals"]
    lines.append("engram-status · %s" % data["generated"])
    lines.append("Themen: %s (%s Konzepte) · Quellen: %s · fällig heute: %s · "
                 "seit letzter Session: %s Tag(e)"
                 % (t["topics"], t["concepts"], t["sources"], t["due_now"],
                    t["days_since_last_session"]))
    lines.append("")

    if data["due"]:
        lines.append("FÄLLIG:")
        for d in data["due"]:
            mark = "†" if d["threshold"] else " "
            recall = ("~%s%% Erinnerung" % d["recall_pct"]
                      if d["recall_pct"] is not None else "Erinnerung unbekannt")
            lines.append("  ! %s%s (%s) — %s Tage überfällig, %s"
                         % (d["node"], mark, d["topic"], d["overdue_days"], recall))
    else:
        lines.append("FÄLLIG: nichts.")
    lines.append("")

    if data["forecast"]:
        lines.append("VORSCHAU:")
        for f in data["forecast"]:
            lines.append("  %s (%s) — in %s Tag(en), %s"
                         % (f["node"], f["topic"], f["days_until"], f["due"]))
    else:
        lines.append("VORSCHAU: keine geplanten Termine im Fenster.")
    lines.append("")

    lines.append("LERNPFADE:")
    for topic in data["topics"]:
        s = topic["states"] or {}
        lines.append("  %-32s %2d behalten · %2d im Lernen · %2d unberührt  (%s Konzepte)"
                     % (topic["topic"], s.get("review", 0), s.get("learning", 0),
                        s.get("new", 0), topic["nodes"]))
    lines.append("")

    lines.append("QUELLEN:")
    for s in data["sources"]:
        tag = "Original gesichert" if s["raw_available"] else "Original nicht im Container"
        lines.append("  %-24s %s S. · %s Chunks → %s (%s)"
                     % (s["slug"], s["pages"], s["chunks"],
                        ", ".join(s["topics"]) or "—", tag))
    lines.append("")

    fl = data["flags"]
    findings = []
    if fl["loop_never_closed"]:
        findings.append("Lernschleife nie geschlossen (%s fällig, %s wiederholt)"
                        % (fl["loop_closure"]["encoded_past_due"],
                           fl["loop_closure"]["first_review_done"]))
    if fl["open_misconceptions"]:
        findings.append("%s offene Fehlvorstellung(en) (Inhalt privat)"
                        % fl["open_misconceptions"])
    if fl["grader_unaudited"]:
        findings.append("Grader nie auditiert")
    for g in fl["goal_date_passed"]:
        findings.append("Zieltermin %s (%s) liegt in der Vergangenheit"
                        % (g["date"], g["label"]))
    if fl["commitment_stale"]:
        c = fl["commitment_stale"]
        findings.append("Vorsatz „%s\" seit %s (%s Tage) nicht erneuert"
                        % (c["cue"], c["set"], c["days_since"]))
    lines.append("AUFFÄLLIGKEITEN:")
    if findings:
        lines.extend("  - %s" % f for f in findings)
    else:
        lines.append("  keine.")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Selftest — hermetisch, ohne den echten State-Repo zu berühren
# --------------------------------------------------------------------------- #

def _fixture_engine():
    """Ein Objekt mit derselben Signatur wie das echte engram-Modul, aber
    ohne die echte FSRS-Konstante zu kennen — der Test prüft, DASS
    build_due_entry() recall_pct füllt, nicht auf welchen exakten Wert."""
    class _E:
        @staticmethod
        def retrievability(elapsed_days, s):
            return max(0.0, 1.0 - elapsed_days / (s * 20.0))
    return _E()


def cmd_selftest(_args):
    failures = []

    def check(name, ok, detail=""):
        if not ok:
            failures.append((name, detail))

    # 1: verbotene Felder werden nie übernommen
    raw = {"topic": "t", "id": "n", "due": "2026-08-05", "overdue_days": 3,
          "threshold": True, "s": 2.0, "last": "2026-08-02", "artifact": True,
          "probe": "GEHEIM", "claim": "GEHEIM", "rubric": ["GEHEIM"],
          "transfer_probe": "GEHEIM"}
    entry = build_due_entry(raw, _fixture_engine(),
                            today=datetime.date(2026, 8, 5))
    bad = assert_no_forbidden(entry)
    check("build_due_entry lässt verbotene Felder weg", bad is None, bad or "")

    # 2: erlaubte Felder kommen korrekt an
    check("build_due_entry: erlaubte Felder",
         entry["topic"] == "t" and entry["node"] == "n"
         and entry["overdue_days"] == 3 and entry["threshold"] is True
         and entry["has_artifact"] is True,
         json.dumps(entry, ensure_ascii=False))

    # 3: recall_pct wird berechnet, wenn ein Engine-Modul da ist
    check("build_due_entry: recall_pct gesetzt", entry["recall_pct"] is not None)

    # 4: ohne Engine-Modul bleibt recall_pct None statt zu crashen
    entry2 = build_due_entry(raw, None, today=datetime.date(2026, 8, 5))
    check("build_due_entry ohne Engine: recall_pct None", entry2["recall_pct"] is None)

    # 5/6: assert_no_forbidden erkennt einen geplanten Verstoß und lässt Sauberes durch
    check("assert_no_forbidden erkennt Verstoß",
         assert_no_forbidden({"a": {"claim": "x"}}) is not None)
    check("assert_no_forbidden: sauberer Baum",
         assert_no_forbidden({"a": [{"b": 1}, {"c": "x"}]}) is None)

    # 7/8: Horizont-Filter — Grenze mit drin, ein Tag drüber raus, ohne Termin raus
    today = datetime.date(2026, 8, 18)
    grenz_nodes = {
        "in-grenze": {"fsrs": {"due": (today + datetime.timedelta(days=30)).isoformat()}},
    }
    graphs = [("topic-a", {"nodes": grenz_nodes})]
    within = nodes_within_horizon(graphs, today, 30)
    check("Vorschau: Grenztag (heute+Horizont) ist drin",
         any(n == "in-grenze" for _, n, _ in within))

    drueber_nodes = {
        "drueber": {"fsrs": {"due": (today + datetime.timedelta(days=31)).isoformat()}},
        "ohne-termin": {"fsrs": {}},
        "retired": {"state": "retired",
                   "fsrs": {"due": (today + datetime.timedelta(days=5)).isoformat()}},
    }
    graphs2 = [("topic-a", {"nodes": drueber_nodes})]
    within2 = nodes_within_horizon(graphs2, today, 30)
    check("Vorschau: Tag drüber, ohne Termin, retired bleiben draußen",
         within2 == [], [n for _, n, _ in within2])

    # 9: Zieldatum-Regex findet ein vergangenes, aber kein zukünftiges Datum —
    # geprüft an beiden Quellen (Themen-goal UND learner-model.goals-Liste),
    # weil genau deren Verwechslung der reale Fehler beim ersten Testlauf war.
    labeled = [("thema:a", "Termin am 2020-01-01 fest eingeplant."),
              ("thema:b", "Termin am 2099-01-01, noch lange hin."),
              ("ziel:0", "kein Datum hier.")]
    hits = goal_dates_passed(labeled, today)
    check("goal_dates_passed findet nur vergangene Daten",
         [h["label"] for h in hits] == ["thema:a"], hits)

    # 10/11: Vorsatz-Frische — nie erneuert und alt löst aus, kürzlich erneuert nicht
    stale = commitment_stale(
        {"settings": {"commitment": {"cue": "x", "action": "y",
                                    "set": "2026-08-01", "renewed": []}}}, today)
    check("commitment_stale: alt und nie erneuert löst aus", stale is not None)
    fresh = commitment_stale(
        {"settings": {"commitment": {"cue": "x", "action": "y",
                                    "set": "2026-08-01", "renewed": ["2026-08-17"]}}}, today)
    check("commitment_stale: erneuert löst nicht aus", fresh is None)

    total = 11
    for name, detail in failures:
        sys.stderr.write("FAIL  %s%s\n" % (name, (": %s" % detail) if detail else ""))
    print("%d/%d Fixtures bestanden" % (total - len(failures), total))
    if failures:
        sys.exit(1)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def cmd_status(args):
    state = _es.resolve_state(args.state)
    engram_root = resolve_engram_root()
    if engram_root is None:
        note("engram-Checkout nicht gefunden (ENGRAM_ROOT setzen) — "
             "Themen/Fälligkeiten/Erinnerungswerte bleiben leer.")
    data = collect(state, engram_root, args.horizon)
    if args.text:
        print(format_text(data))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    # Bewusst KEINE Subparser-pro-Kommando wie in engram_source.py: dieses
    # Werkzeug hat nur einen Zweck (Status) mit zwei Ausgabeformen plus
    # `selftest` — ein optionales Positional ist hier lesbarer als eine
    # zweite Ebene Subparser nur für einen Modusschalter.
    ap = argparse.ArgumentParser(
        prog="engram-status",
        description="Momentaufnahme des Lernstands — ein Aufruf, nur Metadaten.")
    ap.add_argument("--state", help="Pfad zum engram-learning-Checkout")
    ap.add_argument("--horizon", type=int, default=30,
                    help="Vorschau-Fenster in Tagen (Vorgabe: 30)")
    ap.add_argument("--text", action="store_true",
                    help="knappe Textzusammenfassung statt JSON")
    ap.add_argument("cmd", nargs="?", choices=["selftest"], default=None)
    args = ap.parse_args()

    if args.cmd == "selftest":
        cmd_selftest(args)
    else:
        cmd_status(args)


if __name__ == "__main__":
    main()
