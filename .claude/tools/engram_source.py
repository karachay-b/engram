#!/usr/bin/env python3
"""engram-source — PDFs zu seitenreferenzierten Chunks für den Curriculum-Architect.

Gehört zum Cloud-Setup dieses Forks (alles unter .claude/), nicht zum Upstream-Code.

Was es tut: ein PDF wird EINMAL deterministisch zerlegt in
  source.json   Manifest — sha256, Seiten, Scope, Werkzeugversionen
  index.md      das kleine Kartenblatt, das der Architect immer liest
  chunks/*.md   400–1200 Wörter je Datei, mit [S. n]-Markern an jedem Seitenumbruch

Warum kein Embedding-Index: der Konsument ist ein Agent mit Read + Grep, kein
Retrieval-Dienst. Bei ~40 Chunks pro Buch ist "Index lesen → grep → 3–10 Chunks
lesen" schneller, nachvollziehbar und übersteht den nächsten Container ohne
Neuaufbau. Aus demselben Grund kein Chunk-Overlap: wer ganze Chunks liest,
bekommt davon nur doppelten Kontext.

Die Seitenzuordnung wird nicht geschätzt. Alle bereinigten Seiten bilden EINEN
Dokumentstring; pro Seite ist (start, end, label) bekannt. Chunk-Grenzen sind
Zeichen-Offsets, die Seiten eines Chunks ergeben sich aus den überlappenden
Spans. Die Marker landen exakt auf den Span-Grenzen.

Der Inhalt landet im PRIVATEN Repo (engram-learning), niemals in diesem Fork.
"""

import argparse
import collections
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

TOOL_VERSION = "engram-source 1.1"

# Zielband für Chunks. Untergrenze, weil ein 80-Wort-Schnipsel dem Architect
# nichts sagt; Obergrenze, weil sein Kontext das Nadelöhr des ganzen Ablaufs ist.
MIN_WORDS = 400
MAX_WORDS = 1200
WINDOW_PAGES = 6          # Fallback-Fenster, wenn weder Outline noch Überschriften
SCAN_CHARS_PER_PAGE = 120  # darunter: keine Textebene, Chunking wäre Zeichensalat


# --------------------------------------------------------------------------- #
# Infrastruktur
# --------------------------------------------------------------------------- #

def die(msg, code=2):
    sys.stderr.write("engram-source: %s\n" % msg)
    sys.exit(code)


def note(msg):
    sys.stderr.write("engram-source: %s\n" % msg)


def warn_if_interests_empty(state):
    """Ein Ingest ist fast immer der Auftakt zu einem neuen Thema — und genau dort
    wird die Interessen-Frage aus dem Intake verschluckt (das Aufmerksamkeitsbudget
    steckt im Index und in den Seitenmarkern). Ohne Interessen baut der Architect
    still ein Thema ohne Analogien: nichts bricht, nichts warnt, es wird nur
    unpersönlicher. Also hier eine Zeile echter Werkzeugausgabe statt Prosa, die
    schon einmal überlesen wurde.

    Schluckt jeden Fehler. Ein Ingest darf daran nie scheitern — dieselbe Hausregel
    wie in den Hooks.
    """
    try:
        home = os.environ.get("ENGRAM_HOME") or os.path.join(state, "learning")
        with open(os.path.join(home, "learner-model.json"), encoding="utf-8") as fh:
            model = json.load(fh)
        if model.get("interests"):
            return
        note("learner-model: `interests` ist leer. Vor dem Themenaufbau nach 2–3 "
             "Interessen fragen und mit `engram.py model --add-interest \"…\"` "
             "speichern — sonst baut der Curriculum-Architect ein Thema ohne "
             "Analogien.")
    except Exception:
        pass


def _pip(*packages):
    return subprocess.call(
        [sys.executable, "-m", "pip", "install", "--quiet"] + list(packages),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ensure_pypdf():
    """pypdf ist im Container-Image nicht vorhanden, pip läuft aber durch den Proxy.

    Zwei Fehlerbilder, beide gesehen und beide hier behandelt:
      ImportError  — pypdf fehlt schlicht (Normalfall im frischen Container)
      alles andere — pypdf ist da, aber sein Krypto-Provider bricht beim Import.
                     Das Image liefert ein `cryptography` ohne `_cffi_backend`;
                     der Import endet dann in einem pyo3-Panic, nicht in einem
                     ImportError. Ein Stacktrace wäre hier die falsche Antwort:
                     `pip install cffi` repariert es.
    """
    try:
        import pypdf  # noqa: F401
        return
    except ImportError:
        note("pypdf fehlt — installiere es nach (einmal pro Container)")
        if _pip("pypdf") != 0:
            die("pypdf konnte nicht installiert werden (Netz?). "
                "Manuell: pip install pypdf")
    except BaseException:
        note("pypdf importiert nicht (defektes cryptography im Image) — repariere cffi")
        _pip("--upgrade", "cffi")

    try:
        import pypdf  # noqa: F401
    except BaseException as exc:
        die("pypdf ist weiterhin nicht importierbar: %s\n"
            "Manuell versuchen: pip install --upgrade pypdf cffi" % exc)


def resolve_state(explicit=None):
    """Findet das private State-Repo. Gleiche Reihenfolge wie .claude/hooks/engram-env.sh.

    Der Hook ist die Referenz; wer hier eine eigene Suche erfindet, baut den
    zweiten Pfad, der bei der nächsten Umgebungsänderung auseinanderläuft.

    `--state` ist davon ausgenommen und gilt absolut: Trägt der Pfad kein
    Checkout, bricht der Aufruf ab, statt auf die Suchkette zurückzufallen. Der
    Unterschied ist kein Feinschliff — beim Testen von `reclassify` lief genau
    dieser Rückfall auf das ECHTE Repo, während die Ausgabe wie ein bestandener
    Isolationstest aussah. Ein Argument, das der Aufrufer ausdrücklich setzt,
    darf nicht stillschweigend umgeleitet werden.

    Die Umgebungsvariablen bleiben Teil der Suchkette: Dort ist das
    Durchfallen gewollt und im Hook so dokumentiert ("first hit wins",
    ENGRAM_STATE_REPO als Notausgang für ein Checkout an ungewohnter Stelle).
    """
    if explicit:
        chosen = os.path.abspath(explicit)
        if not os.path.isdir(os.path.join(chosen, ".git")):
            die("--state %s ist kein Git-Checkout (kein .git/ darin). Ohne "
                "Repo hätten die Quellen keinen Ort, der den Container "
                "überlebt — und stillschweigend woanders hin zu schreiben "
                "wäre schlimmer als der Abbruch." % explicit)
        return chosen

    candidates = [
        os.environ.get("ENGRAM_STATE"),
        os.environ.get("ENGRAM_STATE_REPO"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                     "engram-learning"),
        "/home/user/engram-learning",
        os.path.join(os.path.expanduser("~"), "engram-learning"),
    ]
    for c in candidates:
        if not c:
            continue
        c = os.path.abspath(c)
        if os.path.isdir(os.path.join(c, ".git")):
            return c
    die("kein engram-learning-Checkout gefunden. Ohne das private Repo hätten die "
        "Quellen keinen Ort, der den Container überlebt (siehe CLAUDE.md).")


def sources_dir(state):
    return os.path.join(state, "sources")


def slugify(text, fallback="quelle"):
    text = text.strip().lower()
    text = (text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                .replace("ß", "ss"))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text[:60] or fallback


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Seitentext bereinigen
# --------------------------------------------------------------------------- #

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
             "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}

# Gliederungsnummer einer ÜBERSCHRIFT — bewusst enger als "Zahl am Zeilenanfang".
#
# Ein Sachbuch ist voller nummerierter Aufzählungen ("3. Konstruktneutralität",
# "18. Wählen Sie selbst ein Thema."), und die als Abschnittsgrenze zu lesen
# zerhackt das Buch an genau den Stellen, an denen es zusammengehört. Der
# typografische Unterschied trägt: Eine Gliederungsnummer ist entweder mehrstufig
# ("2.1.1 Titel") oder einstufig OHNE Punkt ("3 Die Basistechniken") — ein
# Listenpunkt schreibt sich "3.".
NUMBERED_PLAIN = re.compile(r"^(\d+(?:\.\d+)+)\s+\S|^(\d+)\s+\S")

# …aber diese Typografie ist nicht universell. Behördennahe deutsche Dokumente
# (Konzepte, Berichte, Anträge) nummerieren ihre Kapitel regelmäßig "1. Titel"
# MIT Punkt. Für sie ist die Regel oben genau falsch herum: Sie verwirft die
# echten Kapitel und lässt nur die tiefer gestaffelten "7.1"-Unterpunkte übrig.
#
# Beide Konventionen gleichzeitig zu bedienen geht nicht — dieselbe Zeichenfolge
# ist im einen Dokument Kapitel, im anderen Listenpunkt. Deshalb `--numbered-dot`
# als Schalter pro Dokument, per Vorgabe aus. Gemessen am Konzept einer
# Adaptionseinrichtung: ohne Schalter 3 von 15 Kapiteln erkannt, mit Schalter 15.
NUMBERED_DOTTED = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+\S|^(\d+)\.?\s+\S")

NUMBERED = NUMBERED_PLAIN
DOTTED_HEADINGS = False


def set_heading_style(dotted):
    """`--numbered-dot` scharfstellen. Nur `cmd_add` ruft das."""
    global NUMBERED, DOTTED_HEADINGS
    DOTTED_HEADINGS = bool(dotted)
    NUMBERED = NUMBERED_DOTTED if dotted else NUMBERED_PLAIN

# Die MEHRSTUFIGE Form allein ("2.1.1 Titel"). Sie ist die einzige, die stark
# genug ist, um einen laufenden Absatz zu unterbrechen — siehe clean_page().
# Die einstufige Form darf das nicht: "1990 war das Jahr, in dem …" beginnt am
# Zeilenumbruch genauso, und aus einer Jahreszahl eine Kapitelgrenze zu machen
# wäre schlimmer als die Überschrift zu verpassen.
NUMBERED_MULTI = re.compile(r"^\d+(?:\.\d+)+\s+\S")

# Inhaltsverzeichnis-Zeile: Punktführung (auch gesperrt gesetzt: ". . . . .")
# und am Ende die Seitenzahl. Sieht einer nummerierten Überschrift zum
# Verwechseln ähnlich — und ein Inhaltsverzeichnis als Gliederungsquelle zu
# nehmen wäre die Kapitelkopie in Reinform, zwanzig Ebenen tief.
TOC_LINE = re.compile(r"(\.\s?){4,}\s*\d{1,4}\s*$")
TOC_LINE_ANY = re.compile(r"(\.\s?){4,}\s*\d{1,4}\b")

# Inhaltsverzeichnis OHNE erkennbare Punktführung: Titel, Leerraum, Seitenzahl.
# Zwei Dokumente verlangen dasselbe Muster, und beide Messungen stehen hier —
# aus ihnen ergeben sich die zwei Lockerungen gegenüber der naheliegenden Form:
#
#   "15. Supervision         31"  (Word-Export, gemessen: neun Leerzeichen)
#   "… Mediation und Beratung   22"
#   "… zeigen?  ...  426"         (Punktführung nur als Rest überlebt)
#
# Deshalb ZWEI Leerzeichen als Untergrenze, nicht drei, und ein optionaler
# Punktrest davor. Die dritte Fundstelle ist die, die eine Schwelle von drei
# verpasst; TOC_LINE greift dort nicht, weil vier Punkte verlangt sind.
#
# Was diese Lockerung tragbar macht, ist NICHT die Zahl, sondern der Ort: Das
# Muster wird ausschließlich auf Zeilen angewandt, die schon als nummeriert
# erkannt sind (siehe is_toc_line). Eine Versalzeile wie "KAPITEL   2" oder eine
# Überschrift wie "Anlage 7" kommt gar nicht erst hier an — sie trägt keine
# Gliederungsnummer. Ein angeklebter Fußnotenzeiger ("… Transaktionsanalyse17")
# hat den Abstand nicht und bleibt ohnehin eine Überschrift.
TOC_SPACED = re.compile(r"\S\s{2,}[.\s]*\d{1,4}\s*$")


def is_toc_line(line):
    """Verzeichniszeile: Titel, dann abgesetzt die Seitenzahl.

    **Nur auf nummerierte Zeilen anwenden.** `TOC_SPACED` erkennt ein Verzeichnis
    am Leerraum vor der Zahl, und dieses Merkmal allein ist zu schwach: Es trifft
    auch "KAPITEL   2" und "ABBILDUNG  12". Erst zusammen mit der Gliederungs-
    nummer wird daraus ein Beleg. Alle drei Aufrufer prüfen die Nummer vorher —
    `numbered_toc_page` über `NUMBERED`, `breaks_paragraph` über
    `NUMBERED_MULTI`, `is_heading` im `--numbered-dot`-Zweig über `numbered`.

    Wo eine Zeile ohne diese Vorprüfung als Verzeichniszeile gelten soll, ist
    `TOC_LINE` das richtige Muster: Vier Punkte Punktführung sind für sich
    genommen eindeutig, Leerraum ist es nicht.
    """
    s = line.strip()
    return bool(TOC_LINE.search(s) or TOC_SPACED.search(s))


def numbered_toc_page(lines, minimum=3):
    """Steht auf dieser Seite ein Verzeichnis, das selbst Gliederungsnummern trägt?

    Der Grund ist eine Lücke, die keine Zeilenregel schließen kann: Ein
    Verzeichniseintrag, der über zwei Zeilen läuft, trägt seine Seitenzahl auf der
    ZWEITEN. Die erste sieht dann aus wie eine makellose Überschrift —
    "5.6 Phase 6: Themen sortieren, Bearbeitungsreihenfolge", und die Zahl steht
    erst hinter "und Beratungsziele klären ....... 341". Gemessen an Lindemann:
    13 solcher Geister-Überschriften, alle im Inhaltsverzeichnis, alle mehrstufig
    nummeriert — und keine einzige davon einer Zeilenheuristik zugänglich.

    Was sie verrät, ist die Nachbarschaft: Wo die Verzeichniszeilen ringsum
    ihrerseits mit "5.6", "6.4.2" beginnen, ist eine nummerierte Zeile ein
    Verzeichniseintrag, kein Abschnitt.

    Die Nummer der NACHBARN ist dabei das Entscheidende, nicht die Dichte der
    Verzeichniszeilen. Ein Register im Nachspann ("Übung 1: … 49",
    "Mediations-Tipp 3: … 296") besteht zu 90 % aus Verzeichniszeilen, und die
    echten Überschriften darin — "10.1 Übungen", "10.4 Beratungs-Tipps" — sind
    die einzigen nummerierten Zeilen weit und breit. Eine reine Dichteregel
    löschte genau sie.
    """
    return sum(1 for l in lines
               if NUMBERED.match(l.strip()) and is_toc_line(l)) >= minimum


def breaks_paragraph(line):
    """Darf diese Zeile einen laufenden Absatz aufbrechen?

    Nur die mehrstufige Gliederungsnummer — und auch die nur, wenn nichts an der
    Zeile nach Fließtext aussieht. `is_heading` prüft die Schlusszeichen erst NACH
    dem Nummerntreffer, was am Blockanfang harmlos ist: Dort steht ohnehin keine
    umbrochene Klammer. Mitten im Absatz ist genau das der Normalfall — "(siehe
    Kapitel 3.3.5 »Utilisation«)." bricht so um, dass die Folgezeile mit der
    Nummer beginnt. Gemessen: 19 solcher Treffer im Testbuch, alle falsch.
    """
    s = line.strip()
    if not NUMBERED_MULTI.match(s):
        return False
    if s.endswith((".", ",", ";", ":", "!", "?", ")", "»", "«")):
        return False
    if is_toc_line(s) or TOC_LINE_ANY.search(s):
        return False
    return True


def normalize_chars(text):
    for lig, repl in LIGATURES.items():
        text = text.replace(lig, repl)
    text = text.replace(" ", " ").replace("​", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def running_line_key(line):
    """Kopf-/Fußzeilen unterscheiden sich meist nur in der Seitenzahl."""
    return re.sub(r"\d+", "#", line.strip().lower())


def detect_running_lines(pages):
    """Zeilen am Seitenrand, die sich über viele Seiten wiederholen: Kolumnentitel.

    Genau das, was der Architect nicht lesen soll — auf jeder Seite derselbe
    Kapiteltitel ist Rauschen, das sich sonst durch jeden Chunk zieht.

    Die Schwelle ist ABSOLUT gedeckelt, nicht bloß anteilig. Ein Kolumnentitel
    wechselt mit dem Kapitel und steht nur auf dessen Seiten: In einem Buch mit
    467 Seiten erreicht kein einziger 20 % — eine reine Quotenregel findet dort
    gar nichts und lässt jede Kopfzeile im Text stehen (an echtem Material genau
    so passiert). Deshalb: mindestens 3 Seiten, aber nie mehr als 8 verlangt.
    Eine echte Überschrift kommt genau einmal vor und bleibt unangetastet.

    Zusätzlich fällt hier der wichtigste Nebeneffekt an: solange der Kolumnentitel
    im Text steht, ist er überschriftenförmig — die Outline-Auflösung würde eine
    Kapitelmarke auf ihn setzen statt auf die echte Überschrift.
    """
    if len(pages) < 3:
        return set()
    counts = {}
    for raw in pages:
        lines = [l.strip() for l in normalize_chars(raw or "").split("\n") if l.strip()]
        for line in set(lines[:3] + lines[-3:]):
            key = running_line_key(line)
            if 1 < len(key) <= 120:
                counts[key] = counts.get(key, 0) + 1
    threshold = max(3, min(0.2 * len(pages), 8))
    return {k for k, n in counts.items() if n >= threshold}


def detect_printed_labels(pages, running, fallback, page_base=1):
    """Die im Buch GEDRUCKTE Seitenzahl aus den Kolumnentiteln gewinnen.

    Der Anlass ist kein Randfall, sondern der Normalfall bei Sachbüchern: Ein
    Vorspann (Titelei, Inhalt, Vorwort) verschiebt die gedruckte Nummer gegen die
    physische. Liefert das PDF keine echten /PageLabels — und viele liefern nur
    "1, 2, 3, …" —, dann wäre jedes Zitat um den Vorspann verschoben. Ein Verweis
    "S. 61", der im Buch auf Seite 60 steht, ist schlimmer als gar keiner: Er sieht
    richtig aus.

    Die Zahl steht im Kolumnentitel, den wir ohnehin gleich entfernen, mal vorn
    ("60 Definitionen"), mal hinten ("Systemisches Denken … 61"). Also erst lesen,
    dann wegwerfen.

    Robust gegen Ausreißer (Kapitelöffnungsseiten zeigen oft nur die Kapitelnummer):
    entscheidend ist nicht die einzelne Seite, sondern der HÄUFIGSTE Versatz
    zwischen gedruckter und physischer Nummer. Er muss auf der Mehrheit der
    auswertbaren Seiten gelten, sonst bleibt es bei den physischen Nummern.
    """
    if not running:
        return fallback, None
    offsets = {}
    for idx, raw in enumerate(pages):
        lines = [l.strip() for l in normalize_chars(raw or "").split("\n") if l.strip()]
        for line in lines[:2] + lines[-2:]:
            if running_line_key(line) not in running:
                continue
            m = re.match(r"^(\d{1,4})\s+\D", line) or re.search(r"\D\s+(\d{1,4})$", line)
            if not m:
                continue
            printed = int(m.group(1))
            if 0 < printed < 10000:
                off = printed - (page_base + idx)
                offsets[off] = offsets.get(off, 0) + 1
            break
    if not offsets:
        return fallback, None
    best, hits = max(offsets.items(), key=lambda kv: kv[1])
    total = sum(offsets.values())
    # Mehrheitsregel: ein Versatz, der sich nicht durchsetzt, ist geraten.
    if hits < 0.6 * total or hits < 3 or abs(best) > 200:
        return fallback, None
    return [str(page_base + i + best) for i in range(len(pages))], best


def heading_number(line):
    """Die Gliederungsnummer einer Überschrift, oder None."""
    m = NUMBERED.match(line.strip())
    return (m.group(1) or m.group(2)) if m else None


def is_heading(line, in_numbered_toc=False):
    s = line.strip()
    if not (2 <= len(s) <= 90):
        return False
    # Hier nur die Punktführung: Sie ist für sich genommen eindeutig. Der
    # Leerraum-Marker aus `is_toc_line` braucht eine Gliederungsnummer neben
    # sich und darf deshalb erst hinter der Nummernprüfung stehen — ungeprüft
    # verwürfe er "KAPITEL   2" und "ABBILDUNG  12".
    if TOC_LINE.search(s):
        return False
    numbered = NUMBERED.match(s)
    if numbered and in_numbered_toc:
        # Auf einer Verzeichnisseite mit nummerierten Einträgen zählt die Nummer
        # nicht mehr als Beleg — dort ist sie das Merkmal des Eintrags selbst.
        # Siehe numbered_toc_page().
        return False
    if DOTTED_HEADINGS and numbered:
        # In diesem Modus ist die Nummer kein Beweis mehr — "13. Waschen und
        # Trocknen sind nur im dafür vorgesehenen Raum erlaubt." trägt dieselbe
        # Nummernform wie ein Kapitel. Der Satzschluss trennt beide: Eine
        # Überschrift endet nicht auf Satzzeichen, ein Listensatz schon.
        #
        # Nur für NUMMERIERTE Zeilen — `--numbered-dot` erweitert, was als Nummer
        # zählt, und darf deshalb auch nur dort strenger sein. Ungeprüft griff
        # der Leerraum-Marker sonst auf unnummerierte Versalzeilen über und
        # verwarf "KAPITEL   2" allein wegen des Modus.
        if is_toc_line(s) or s.endswith((".", ",", ";", ":", "!", "?")):
            return False
    if numbered:
        return True
    if s.endswith((".", ",", ";", ":", "!", "?")):
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    # Versalzeile als Überschrift — aber mindestens zwei Wörter. Ein einzelnes
    # Akronym mitten im Text ("CLEAR", "GFK") ist keine Abschnittsgrenze.
    if (len(s) <= 60 and len(s.split()) >= 2
            and sum(c.isupper() for c in letters) / len(letters) > 0.8):
        return True
    return False


def heading_level(line):
    m = NUMBERED.match(line.strip())
    if m:
        return min((m.group(1) or m.group(2)).count(".") + 1, 4)
    return 1


def is_page_number_line(line, label):
    """Randzeile, die die gedruckte Seitenzahl dieser Seite trägt.

    Der zweite Durchgang der Kolumnentitel-Erkennung, und der genauere: Sobald der
    Seitenversatz bekannt ist, weiß man für JEDE Seite, welche Zahl auf ihr steht.
    Eine kurze Randzeile, die mit genau dieser Zahl beginnt oder endet, ist der
    Kolumnentitel — auch dann, wenn sein Text nur auf fünf Seiten vorkommt und die
    Häufigkeitsregel ihn deshalb verfehlt (Vorspann, kurze Kapitel).
    """
    s = line.strip()
    if not label or len(s) > 120:
        return False
    return bool(re.match(r"^%s\b" % re.escape(label), s)
                or re.search(r"\b%s$" % re.escape(label), s))


def clean_page(raw, running, label=None):
    """Eine Seite → Blöcke [(kind, text)] mit kind in {"heading", "para"}.

    Überschriften werden VOR dem Umbruch erkannt und als eigener Block gehalten.
    Sonst verschmelzen sie beim Zusammenziehen der Zeilen mit dem Folgeabsatz —
    und die Heuristik-Gliederung hätte nichts mehr, woran sie schneiden kann.
    """
    text = normalize_chars(raw or "")
    lines = [l.rstrip() for l in text.split("\n")]

    # VOR jeder Bereinigung entscheiden: Der Silbentrennungs-Merge zieht die
    # Folgezeile mitsamt ihrer Punktführung hoch und verwischt genau das Merkmal,
    # an dem eine Verzeichniszeile zu erkennen ist.
    in_toc = numbered_toc_page(lines)

    # Kolumnentitel raus, aber nur am Seitenrand: dieselbe Zeichenfolge mitten im
    # Fließtext ist Inhalt, kein Kopfzeilen-Artefakt.
    keep, n = [], len(lines)
    seen_edge = 0
    for i, line in enumerate(lines):
        edge = i < 3 or i >= n - 3
        if edge and line.strip():
            if running_line_key(line) in running:
                continue
            # Nur die äußersten Randzeilen per Seitenzahl prüfen, sonst könnte ein
            # Absatz, der zufällig mit dieser Zahl beginnt, verschwinden.
            if (i < 2 or i >= n - 2) and is_page_number_line(line, label):
                seen_edge += 1
                continue
        keep.append(line)
    lines = keep

    # Silbentrennung am Zeilenende zusammenziehen — nur vor Kleinbuchstaben,
    # damit "Bayes-Regel" am Zeilenumbruch nicht zu "BayesRegel" wird.
    merged = []
    for line in lines:
        if merged and merged[-1].endswith("-") and line[:1].islower():
            # .rstrip() nach dem Strich ist nicht kosmetisch: manche Setzer
            # trennen als "durchgän -", und ohne das bliebe "durchgän gig"
            # stehen — ein Wort, das es nicht gibt, mitten im Zitat.
            merged[-1] = merged[-1][:-1].rstrip() + line.lstrip()
        else:
            merged.append(line)
    lines = merged

    filled = [l for l in lines if l.strip()]
    if not filled:
        return []
    median = sorted(len(l) for l in filled)[len(filled) // 2]

    blocks, buf = [], []

    def flush():
        if buf:
            para = " ".join(x.strip() for x in buf).strip()
            para = re.sub(r"\s{2,}", " ", para)
            if para:
                blocks.append(("para", para))
            del buf[:]

    for line in lines:
        if not line.strip():
            flush()
            continue
        # Überschriften sonst nur am Blockanfang: Eine kurze Versalzeile mitten im
        # Absatz ist Inhalt, keine Grenze. Eine MEHRSTUFIGE Gliederungsnummer bricht
        # dagegen auch mitten im Puffer.
        #
        # Gemessen an Lindemann, 467 S.: Die alte Bedingung erkannte 50 der 148
        # numerierten Abschnitte. In einem durchlaufenden Buchsatz folgt die
        # Überschrift direkt auf die letzte Zeile des vorigen Absatzes — leer war
        # der Puffer nur dort, wo diese Zeile zufällig kurz genug für den
        # Satzspiegel-Flush war. Zwei Drittel der Gliederung gingen so verloren,
        # und mit ihnen die Genauigkeit von `(<slug> §<heading>, S. n)`: Der Verweis
        # nannte den zuletzt erkannten Abschnitt, nicht den, in dem der Satz steht.
        if is_heading(line, in_toc) and (not buf or breaks_paragraph(line)):
            flush()
            blocks.append(("heading", line.strip()))
            continue
        buf.append(line)
        # Deutlich kürzere Zeile als der Satzspiegel = Absatzende. Viele PDFs
        # liefern keine Leerzeilen, dann ist das die einzige Absatzinformation.
        if median and len(line) < 0.6 * median:
            flush()
    flush()
    return blocks


# --------------------------------------------------------------------------- #
# Dokumentmodell: ein String, exakte Seiten-Spans
# --------------------------------------------------------------------------- #

def build_doc(pages, labels, running):
    """Baut den Dokumentstring und merkt sich pro Seite (start, end, label)."""
    parts, spans, headings, offset = [], [], [], 0
    for idx, raw in enumerate(pages):
        blocks = clean_page(raw, running,
                            labels[idx] if idx < len(labels) else None)
        page_start = offset
        for kind, text in blocks:
            if kind == "heading":
                headings.append({"offset": offset, "text": text,
                                 "level": heading_level(text)})
            chunk = text + "\n\n"
            parts.append(chunk)
            offset += len(chunk)
        spans.append({"page": idx + 1, "label": labels[idx] if idx < len(labels)
                      else str(idx + 1), "start": page_start, "end": offset})
    return "".join(parts), spans, headings


def pages_for(spans, a, b):
    hit = [s for s in spans if s["start"] < b and s["end"] > a]
    return hit or [spans[0]]


def render(doc, spans, a, b):
    """Chunktext mit [S. n] an jeder Seitengrenze — der Verweis-Mechanismus."""
    out = []
    for s in pages_for(spans, a, b):
        piece = doc[max(a, s["start"]):min(b, s["end"])].strip()
        if piece:
            out.append("[S. %s] %s" % (s["label"], piece))
    return "\n\n".join(out)


# --------------------------------------------------------------------------- #
# Abschnittsgrenzen
# --------------------------------------------------------------------------- #

def flatten_outline(reader):
    """PDF-Outline → [{title, level, page}] — der beste verfügbare Gliederungsbeleg."""
    entries = []

    def walk(items, level):
        for item in items:
            if isinstance(item, list):
                walk(item, level + 1)
                continue
            try:
                title = str(item.title).strip()
                page = reader.get_destination_page_number(item)
            except Exception:
                continue
            if not title:
                continue
            # Eine nummerierte Überschrift trägt ihre Hierarchie selbst: "2.2" ist
            # Geschwister von "2.1", egal wie tief der Outline-Baum sie hängt.
            # Die Verschachtelungstiefe ist bei realen PDFs oft schlampig gesetzt
            # (und bei manchen Erzeugern schlicht falsch), die Nummer nie.
            lvl = heading_level(title) if NUMBERED.match(title) else level
            entries.append({"title": title, "level": lvl, "page": page})

    try:
        walk(reader.outline, 1)
    except Exception:
        return []
    entries.sort(key=lambda e: (e["page"], e["level"]))
    return entries


def find_offset(doc, spans, headings, title, page_idx):
    """Offset einer Outline-Überschrift: erkannter Heading-Block, sonst Fuzzy-Suche."""
    if page_idx >= len(spans):
        return None
    start = spans[page_idx]["start"]
    end = spans[min(page_idx + 1, len(spans) - 1)]["end"]
    norm = re.sub(r"\s+", " ", title).strip().lower()
    for h in headings:
        if start <= h["offset"] < end:
            if re.sub(r"\s+", " ", h["text"]).strip().lower().startswith(norm[:30]):
                return h["offset"]
    words = [w for w in re.split(r"\s+", title.strip()) if w][:6]
    if words:
        pattern = r"\s*".join(re.escape(w) for w in words)
        m = re.compile(pattern, re.I).search(doc, start, end)
        if m:
            return m.start()
    return start


def sections_from_outline(doc, spans, headings, entries):
    marks = []
    for e in entries:
        off = find_offset(doc, spans, headings, e["title"], e["page"])
        if off is None:
            continue
        marks.append({"offset": off, "title": e["title"], "level": e["level"]})
    marks.sort(key=lambda m: m["offset"])
    return marks_to_sections(marks, len(doc))


def sections_from_headings(doc, headings):
    marks = [{"offset": h["offset"], "title": h["text"], "level": h["level"]}
             for h in headings]
    return marks_to_sections(marks, len(doc))


def marks_to_sections(marks, doc_len):
    """Marken → Abschnitte mit Überschriftpfad (Elternebenen bleiben sichtbar)."""
    sections, stack = [], []
    seen = set()
    marks = [m for m in marks if not (m["offset"] in seen or seen.add(m["offset"]))]
    for i, m in enumerate(marks):
        while stack and stack[-1]["level"] >= m["level"]:
            stack.pop()

        # Die Nummer schlägt die Ebene. Ein zweizeilig gesetzter Kapitelkopf
        # ("3" / "Die Basistechniken") wird nicht als Überschrift erkannt; ohne
        # diese Prüfung erbt dann jeder Abschnitt von Kapitel 3 die letzte Marke
        # aus Kapitel 2 als Elternebene, und der Index behauptet
        # "2.3 … › 3.1.2 …". An echtem Material genau so passiert.
        num = heading_number(m["title"])
        if num:
            while stack:
                pnum = heading_number(stack[-1]["title"])
                if pnum and (num + ".").startswith(pnum + "."):
                    break          # echter Vorfahre: "3.1" trägt "3.1.2"
                stack.pop()

        # Derselbe Titel zweimal (Outlines doppeln Kapitel gern als ersten
        # Abschnitt) darf nicht zu "X › X" werden.
        parents = [s["title"] for s in stack if s["title"] != m["title"]]
        path = parents + [m["title"]]
        stack.append(m)
        end = marks[i + 1]["offset"] if i + 1 < len(marks) else doc_len
        if end > m["offset"]:
            sections.append({"path": path, "start": m["offset"], "end": end})

    # Was VOR der ersten Marke steht — Titelei, Inhaltsverzeichnis, Vorwort —
    # gehört in einen eigenen Abschnitt und nicht in den Papierkorb. Es ist selten
    # Lernstoff, aber der Index muss abbilden, was in der Quelle steht; sonst
    # verschwindet Text, ohne dass es jemand bemerkt.
    if sections and sections[0]["start"] > 0:
        sections.insert(0, {"path": ["(Vorspann)"], "start": 0,
                            "end": sections[0]["start"]})
    return sections


def sections_from_windows(spans, window=WINDOW_PAGES):
    sections = []
    for i in range(0, len(spans), window):
        block = spans[i:i + window]
        sections.append({"path": ["S. %s–%s" % (block[0]["label"], block[-1]["label"])],
                         "start": block[0]["start"], "end": block[-1]["end"]})
    return sections


def wc(text):
    return len(text.split())


def normalize_sizes(sections, doc):
    """Zielband durchsetzen: Große an Absatzgrenzen teilen, kleine Nachbarn verschmelzen."""
    split = []
    for sec in sections:
        text = doc[sec["start"]:sec["end"]]
        words = wc(text)
        if words <= MAX_WORDS:
            split.append(sec)
            continue
        parts = max(2, -(-words // MAX_WORDS))
        target = len(text) // parts
        cuts, pos = [sec["start"]], sec["start"]
        for _ in range(parts - 1):
            want = pos + target
            if want >= sec["end"]:
                break
            # An der nächsten Absatzgrenze schneiden, nicht mitten im Satz.
            nxt = doc.find("\n\n", want)
            cut = nxt + 2 if 0 <= nxt < sec["end"] else want
            if cut <= pos:
                break
            cuts.append(cut)
            pos = cut
        cuts.append(sec["end"])
        total = len(cuts) - 1
        for n in range(total):
            path = list(sec["path"])
            path[-1] = "%s (%d/%d)" % (path[-1], n + 1, total)
            split.append({"path": path, "start": cuts[n], "end": cuts[n + 1]})

    merged = []
    for sec in split:
        if merged:
            prev = merged[-1]
            prev_w = wc(doc[prev["start"]:prev["end"]])
            this_w = wc(doc[sec["start"]:sec["end"]])
            if prev_w < MIN_WORDS and prev_w + this_w <= MAX_WORDS \
                    and prev["end"] == sec["start"]:
                # Der Titel des GRÖSSEREN Beitrags führt. Sonst firmiert ein
                # Chunk unter einer Kapitelzeile, die nur zwei Wörter beisteuert,
                # und der Index verspricht etwas anderes als der Chunk enthält.
                loser = prev["path"] if this_w > prev_w else sec["path"]
                winner = sec["path"] if this_w > prev_w else prev["path"]
                also = prev.get("also", []) + [loser[-1]]
                prev["end"] = sec["end"]
                prev["path"] = winner
                prev["also"] = [a for a in also if a != winner[-1]]
                continue
        merged.append(dict(sec))

    # Winzige Reste an den Vorgänger hängen statt sie wegzuwerfen. Ein Filter,
    # der kurze Abschnitte verwirft, verliert Text lautlos — und niemand merkt,
    # dass die Quelle unvollständig im Index steht.
    out = []
    for sec in merged:
        if out and wc(doc[sec["start"]:sec["end"]]) < 20 \
                and out[-1]["end"] == sec["start"]:
            out[-1]["end"] = sec["end"]
            continue
        out.append(sec)
    return out


# --------------------------------------------------------------------------- #
# Chunk-Art
# --------------------------------------------------------------------------- #

# `Satz` ohne Nummer ist im Deutschen ein Allerweltswort — "ein Satz", "der Satz
# fiel spät", "Glaubenssätze". Gemessen an Lindemann: 7 Treffer, kein einziger ein
# Lehrsatz, und Chunk 0090 ("4.3.4 Überzeugungen, Leit- und Glaubenssätze") trug
# sein `definition` allein daraus. Was "Satz 3.1" zum Lehrsatz macht, ist die
# Nummer — dasselbe Idiom, mit dem TASK_RE unten "Übung 4" von "Übung" trennt.
DEF_RE = re.compile(r"\b(?:Definition|Theorem|Lemma|Korollar|Axiom)\b|\bSatz\s*\d", re.I)

# Definitorische SATZRAHMEN statt Stichwörter — der Zugang zu Fachprosa, die ihre
# Definitionen nicht auszeichnet. Der Unterschied ist gemessen, nicht vermutet:
# `bezeichnet` und `Der Begriff` als blanke Stichwörter hätten 11 Chunks neu
# etikettiert, und die Stichprobe zeigte sie überwiegend als Fehltreffer — "Der
# Begriff der Attraktivität bringt einen weiteren Aspekt ein" ist keine
# Definition. Erst Begriff PLUS definierendes Verb trägt: dann bleiben zwei
# Chunks, beide Herkunftsdefinitionen (Coaching, Supervision, Mediation).
#
# Die Zeichenklasse [^.] hält jeden Rahmen im Satz. Über einen Punkt hinweg
# würde "Der Begriff X. Später bezeichnet man …" zusammenlaufen, und der Rahmen
# wäre keiner mehr.
DEF_FRAME = re.compile(
    r"Der Begriff\s+[^.]{0,60}?"
    r"(?:stammt|bezeichnet|meint|geht zurück|leitet sich|wird verwendet)"
    r"|Unter\s+[^.]{2,60}?\s+versteht man"
    r"|wird\s+(?:als|auch)\s+[^.]{2,60}?\s+bezeichnet"
    r"|bezeichnet man als"
    r"|\bBegriffsbestimmung\b"
    r"|\bdefiniert\s+(?:als|man)\b"
    r"|\bper definitionem\b",
    re.I)

# Fallvokabular. In Medizin und Psychologie ist die Kasuistik die tragende
# Textsorte; `Beispiel` allein greift dort nicht, und `\bBeispiel\b` trifft
# "Fallbeispiel" wegen der Wortgrenze ohnehin nicht. In beiden vorhandenen
# Korpora: null Treffer — die Erweiterung ist für den Bestand nachweislich
# folgenlos und zielt allein auf Genres, für die hier kein Korpus liegt.
EX_RE = re.compile(
    r"\b(?:Beispiel|Example|Fallbeispiel|Fallvignette|Kasuistik|Praxisbeispiel)\b",
    re.I)

# Überschriften wiegen schwerer als Fließtext: Ein Abschnitt, der "Definition"
# oder "Klassifikation" HEISST, ist einer — ein Fließtextwort ist nur ein Indiz.
# Genau hier liegt die Brücke zu den ungetesteten Genres: Lehrbücher der Medizin
# und der Wissenschaftstheorie führen feste Abschnittsnamen, wo Fachprosa gar
# keine Marker setzt.
#
# Für den vorhandenen Bestand ist das folgenlos, und das ist die ehrliche Zahl:
# EIN Treffer auf 183 Überschriften ("2.2.1 Was ist ein »System«?"), und der
# Chunk trug `definition` schon über die Fließtext-Marker. Diese Muster sind
# also ein begründeter Vorschuss auf Genres, für die hier kein Korpus liegt —
# belegt sind sie erst, wenn ein solches Buch ingestet wird. Bis dahin ist
# `kind_report` die Absicherung, nicht diese Regex.
#
# Kein abschließendes \b: deutsche Überschriften komponieren
# ("Klassifikationssysteme", "Grundbegriffe der Testtheorie").
HEAD_DEF = re.compile(
    r"\b(?:definition|begriffsbestimmung|grundbegriffe|terminologie|nomenklatur"
    r"|klassifikation|was ist|was sind)", re.I)
HEAD_EX = re.compile(
    r"\b(?:fallbeispiel|fallvignette|kasuistik|praxisbeispiel)", re.I)

TASK_RE = re.compile(r"\b(Aufgabe|Übung|Exercise|Problem)\s*\d", re.I)
MATH_RE = re.compile(r"[=+×÷∑∫≤≥≠√±∞∂αβγδθλμσπΣΩ]")


def classify(text, path):
    head = " ".join(path).lower()
    lines = [l for l in text.split("\n") if l.strip()]

    # Punktführungen zählen, nicht Zeilen: Absätze werden beim Bereinigen zu
    # Fließtext zusammengezogen, ein Inhaltsverzeichnis landet dadurch in einer
    # einzigen langen Zeile — eine zeilenbasierte Quote sähe dort nichts.
    leaders = len(TOC_LINE_ANY.findall(text))
    if leaders >= 5 and leaders / max(len(text.split()), 1) > 0.02:
        return "toc-like"
    dotted = sum(1 for l in lines if re.search(r"(\.{3,}|\s)\d{1,4}$", l.strip()))
    if lines and dotted / len(lines) > 0.4:
        return "toc-like"
    # `exercise` heißt ÜBUNGSTEIL, nicht "enthält Übungen". Ein Sachbuch streut
    # Übungskästen mitten in seine Fachabschnitte; zwei Treffer genügen dort
    # längst nicht. An echtem Material trug "3.5.6 Zirkuläre Fragen" — 1057
    # Wörter Definition, Beispielkatalog und Perspektiventabelle — das Etikett
    # und wäre dem Architect damit entzogen worden. Also Dichte statt Vorkommen,
    # oder die Überschrift sagt es ausdrücklich.
    tasks = len(TASK_RE.findall(text))
    dense = tasks >= 2 and tasks >= max(len(text.split()), 1) / 150.0
    if dense or re.search(r"\b(aufgaben|übungen|exercises|problems)\b", head):
        return "exercise"
    # Ab hier sind die Etiketten billig: `definition` und `example` steuern nur die
    # LESEREIHENFOLGE des Architects, `exercise` und `toc-like` oben lassen ihn
    # überspringen. Deshalb darf hier breiter gegriffen werden als dort — ein
    # Fehltreffer verdrängt einen besseren Chunk aus dem 10er-Budget, er löscht
    # keinen. Die Schwelle von zwei Treffern bleibt trotzdem: Ein einzelner Rahmen
    # steht in fast jedem Fachtext.
    if len(DEF_RE.findall(text)) + len(DEF_FRAME.findall(text)) >= 2 \
            or DEF_RE.search(head) or HEAD_DEF.search(head):
        return "definition"
    if len(EX_RE.findall(text)) >= 2 or HEAD_EX.search(head):
        return "example"
    if text and len(MATH_RE.findall(text)) / max(len(text), 1) > 0.012:
        return "formula-dense"
    return "prose"


# --------------------------------------------------------------------------- #
# Schreiben
# --------------------------------------------------------------------------- #

def yaml_list(items):
    return "[%s]" % ", ".join('"%s"' % str(i).replace('"', "'") for i in items)


def norm(text):
    """Der Zellwert, wie er gemeint ist — ohne Escaping.

    Getrennt von `cell()`, weil MAP.md nicht nur geschrieben, sondern auch gelesen
    und verglichen wird: verglichen wird gegen den gemeinten Wert, escapt erst beim
    Schreiben. Beides in einer Funktion hieße, `a|b` mit `a\\|b` zu vergleichen.
    """
    return re.sub(r"\s+", " ", text).strip()


def cell(text):
    return norm(text).replace("|", "\\|")


def write_source(state, slug, meta, doc, spans, sections, pdf_path, keep_pdf):
    root = os.path.join(sources_dir(state), slug)
    chunk_dir = os.path.join(root, "chunks")
    if os.path.isdir(chunk_dir):
        shutil.rmtree(chunk_dir)
    os.makedirs(chunk_dir, exist_ok=True)

    rows, total_words = [], 0
    for n, sec in enumerate(sections, 1):
        body = render(doc, spans, sec["start"], sec["end"])
        pages = pages_for(spans, sec["start"], sec["end"])
        labels = [p["label"] for p in pages]
        words = wc(body)
        total_words += words
        kind = classify(body, sec["path"])
        cid = "%s-%04d" % (slug, n)
        name = "%04d-%s.md" % (n, slugify(sec["path"][-1], "abschnitt")[:40])

        front = [
            "---",
            "id: %s" % cid,
            "source: %s" % slug,
            "pages: %s" % yaml_list([labels[0], labels[-1]]),
            "heading: %s" % yaml_list(sec["path"]),
        ]
        # Verschmolzene Nachbarabschnitte gehören sichtbar gemacht: sonst
        # verspricht die Überschrift weniger, als der Chunk tatsächlich enthält.
        if sec.get("also"):
            front.append("also: %s" % yaml_list(sec["also"]))
        front += [
            "kind: %s" % kind,
            "words: %d" % words,
            "---",
            "",
        ]
        with open(os.path.join(chunk_dir, name), "w", encoding="utf-8") as fh:
            fh.write("\n".join(front) + body + "\n")

        preview = re.sub(r"^\[S\. [^\]]+\]\s*", "", body).strip()[:90]
        rows.append({"id": cid, "file": name, "pages": labels,
                     "path": sec["path"], "also": sec.get("also", []),
                     "kind": kind, "words": words, "preview": preview})

    meta["chunks"] = len(rows)
    meta["words"] = total_words
    with open(os.path.join(root, "source.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    write_index(root, slug, meta, rows)

    if keep_pdf and pdf_path:
        pdf_dir = os.path.join(root, "pdf")
        os.makedirs(pdf_dir, exist_ok=True)
        target = os.path.join(pdf_dir, os.path.basename(pdf_path))
        if os.path.abspath(pdf_path) != os.path.abspath(target):
            shutil.copy2(pdf_path, target)
    return root, rows


def render_index(slug, meta, rows):
    """Das Kartenblatt. Klein halten — es wird IMMER gelesen, die Chunks nicht.

    Getrennt vom Schreiben, weil `reclassify` den Index aus den vorhandenen
    Chunks NACHBAUEN können muss, ohne ihn anzufassen: Nur wenn der Nachbau des
    unveränderten Standes zeichengleich herauskommt, ist bewiesen, dass das
    Zurücklesen des Frontmatters verlustfrei war.
    """
    out = ["# %s" % (meta.get("title") or slug), ""]
    if meta.get("author"):
        out.append("**Autor:** %s  " % meta["author"])
    scope = meta.get("scope") or {}
    out.append("**Slug:** `%s` · **Seiten:** %s · **Chunks:** %d · **Wörter:** %d"
               % (slug, scope.get("label") or meta.get("pages"), meta["chunks"],
                  meta["words"]))
    out += [
        "",
        "Chunks liegen in `chunks/`. Jeder trägt `[S. n]`-Marker an jedem Seitenumbruch —",
        "daraus wird der Verweis `(%s §<heading>, S. <n>)`." % slug,
        "Beim Kurrikulumbau: `kind: toc-like` überspringen, `kind: exercise` "
        "nachrangig lesen",
        "(Übungskataloge sind Rohstoff für `transfer_probe`), "
        "`kind: definition` zuerst.",
        "",
    ]

    # Kapitelübersicht vor der Chunk-Tabelle. Bei einem 460-Seiten-Buch sind das
    # zwanzig Zeilen statt zweihundert — genug, um zu entscheiden, wo man
    # überhaupt nachschlägt, bevor man die große Tabelle liest.
    chapters = []
    for r in rows:
        # "(2/5)" ist ein Größen-Split, kein eigenes Kapitel.
        top = re.sub(r"\s*\(\d+/\d+\)$", "", r["path"][0])
        if not chapters or chapters[-1][0] != top:
            chapters.append([top, r["id"], r["id"], r["pages"][0], r["pages"][-1]])
        else:
            chapters[-1][2] = r["id"]
            chapters[-1][4] = r["pages"][-1]
    if len(chapters) > 1:
        out.append("## Kapitel")
        out.append("")
        for top, first_id, last_id, p0, p1 in chapters:
            span = first_id.rsplit("-", 1)[1]
            if last_id != first_id:
                span += "–" + last_id.rsplit("-", 1)[1]
            out.append("- **%s** — S. %s–%s, Chunks %s" % (cell(top), p0, p1, span))
        out.append("")

    out += [
        "## Alle Chunks",
        "",
        "| id | Seiten | Überschrift | kind | W | Anfang |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        pages = r["pages"][0] if r["pages"][0] == r["pages"][-1] \
            else "%s–%s" % (r["pages"][0], r["pages"][-1])
        # Der Index ist das eine Dokument, das IMMER vollständig gelesen wird.
        # Eine Zelle, die dreißig verschmolzene Abschnitte aufzählt, frisst genau
        # das Kontextbudget, das er sparen soll — deshalb gedeckelt.
        heading = " › ".join(r["path"][-2:])
        if r.get("also"):
            extra = r["also"][:2]
            heading += " (+ %s%s)" % (", ".join(extra),
                                      " …" if len(r["also"]) > 2 else "")
        out.append("| %s | %s | %s | %s | %d | %s |"
                   % (r["id"], pages, cell(heading), r["kind"],
                      r["words"], cell(r["preview"])))
    out.append("")
    return "\n".join(out)


def write_index(root, slug, meta, rows):
    path = os.path.join(root, "index.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_index(slug, meta, rows))
    return path


# --------------------------------------------------------------------------- #
# Kommandos
# --------------------------------------------------------------------------- #

def fetch_if_url(target):
    if not re.match(r"^https?://", target):
        return target, False
    import tempfile
    import urllib.request
    note("lade %s" % target)
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        with urllib.request.urlopen(target, timeout=120) as resp, \
                open(tmp, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    except Exception as exc:
        die("Download fehlgeschlagen: %s" % exc)
    return tmp, True


def cmd_add(args):
    ensure_pypdf()
    from pypdf import PdfReader

    set_heading_style(getattr(args, "numbered_dot", False))

    state = resolve_state(args.state)
    path, temp = fetch_if_url(args.pdf)
    if not os.path.isfile(path):
        die("keine Datei: %s" % path)

    try:
        reader = PdfReader(path)
    except Exception as exc:
        die("PDF nicht lesbar: %s" % exc)
    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0:
                die("PDF ist passwortgeschützt — bitte entschlüsselt bereitstellen")
        except Exception:
            die("PDF ist verschlüsselt und lässt sich nicht öffnen")

    total = len(reader.pages)
    first, last = 1, total
    if args.pages:
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", args.pages.strip())
        if not m:
            die("--pages erwartet A-B, z.B. 51-190")
        first, last = int(m.group(1)), int(m.group(2))
        if not (1 <= first <= last <= total):
            die("--pages %s liegt außerhalb von 1-%d" % (args.pages, total))

    try:
        labels = list(reader.page_labels)
    except Exception:
        labels = [str(i + 1) for i in range(total)]

    raw = []
    for i in range(first - 1, last):
        try:
            raw.append(reader.pages[i].extract_text() or "")
        except Exception:
            raw.append("")
    scoped_labels = labels[first - 1:last]

    chars = sum(len(t) for t in raw)
    if raw and chars / len(raw) < SCAN_CHARS_PER_PAGE:
        die("Ø %d Zeichen pro Seite — dieses PDF hat keine brauchbare Textebene "
            "(Scan). Chunking würde Zeichensalat erzeugen. Bild-Weg nehmen: Seiten "
            "mit pypdfium2 zu PNG rendern und vom Modell lesen lassen (pdf2image "
            "scheitert hier an fehlendem poppler)." % (chars / len(raw)))

    running = detect_running_lines(raw)
    # Erst die gedruckte Seitenzahl aus den Kolumnentiteln lesen, dann bereinigen.
    scoped_labels, page_offset = detect_printed_labels(raw, running, scoped_labels,
                                                       page_base=first)
    if page_offset:
        note("gedruckte Seitenzahlen erkannt: Versatz %+d gegenüber der PDF-Seite"
             % page_offset)
    doc, spans, headings = build_doc(raw, scoped_labels, running)
    if not doc.strip():
        die("nach der Bereinigung ist kein Text übrig")

    entries = [e for e in flatten_outline(reader)
               if first - 1 <= e["page"] <= last - 1]
    for e in entries:
        e["page"] -= (first - 1)

    if entries:
        sections, boundary = sections_from_outline(doc, spans, headings, entries), "outline"
    elif len(headings) >= 3:
        sections, boundary = sections_from_headings(doc, headings), "headings"
    else:
        sections, boundary = sections_from_windows(spans), "windows"
    if not sections:
        sections, boundary = sections_from_windows(spans), "windows"
    sections = normalize_sizes(sections, doc)

    slug = args.slug or slugify(args.title or os.path.splitext(
        os.path.basename(path))[0])
    meta = {
        "slug": slug,
        "title": args.title or os.path.splitext(os.path.basename(path))[0],
        "author": args.author or "",
        "sha256": sha256_of(path),
        "bytes": os.path.getsize(path),
        "pages": total,
        "scope": {"pages": [first, last],
                  "label": args.scope_label or ("S. %d–%d" % (first, last)
                                                if (first, last) != (1, total)
                                                else "vollständig")},
        "ingested": datetime.date.today().isoformat(),
        "tool": TOOL_VERSION,
        "extractor": "pypdf %s" % __import__("pypdf").__version__,
        "text_layer": "native",
        "page_labels": ("gedruckt (Versatz %+d)" % page_offset) if page_offset
                       else "PDF-Seitenzahl",
        "boundaries": boundary,
        "heading_style": "1. Titel" if DOTTED_HEADINGS else "1 Titel",
        "outline": bool(entries),
        "rights": "urheberrechtlich geschützt — Derivate privat, nicht weitergeben",
    }

    root, rows = write_source(state, slug, meta, doc, spans, sections, path,
                              args.keep_pdf)
    if temp and not args.keep_pdf:
        os.unlink(path)

    idx = os.path.join(root, "index.md")
    note("%s: %d Chunks, %d Wörter, Grenzen aus %s, index.md %.1f KB"
         % (slug, meta["chunks"], meta["words"], boundary,
            os.path.getsize(idx) / 1024.0))
    small = sum(1 for r in rows if r["words"] < MIN_WORDS)
    big = sum(1 for r in rows if r["words"] > MAX_WORDS)
    if small or big:
        note("außerhalb des Zielbands: %d zu klein, %d zu groß" % (small, big))
    kind_report(rows)
    warn_if_interests_empty(state)
    print(idx)   # bleibt die letzte Zeile: der maschinenlesbare Rückgabewert


def cmd_list(args):
    state = resolve_state(args.state)
    base = sources_dir(state)
    if not os.path.isdir(base):
        note("noch keine Quellen (%s)" % base)
        return
    for slug in sorted(os.listdir(base)):
        meta_path = os.path.join(base, slug, "source.json")
        if not os.path.isfile(meta_path):
            continue
        with open(meta_path, encoding="utf-8") as fh:
            m = json.load(fh)
        print("%-28s %-34s %s · %d Chunks · %d Wörter"
              % (slug, (m.get("title") or "")[:34],
                 (m.get("scope") or {}).get("label", "?"),
                 m.get("chunks", 0), m.get("words", 0)))


def cmd_show(args):
    state = resolve_state(args.state)
    root = os.path.join(sources_dir(state), args.slug)
    if not os.path.isdir(root):
        die("unbekannte Quelle: %s (list zeigt alle)" % args.slug)
    if not args.chunks:
        with open(os.path.join(root, "index.md"), encoding="utf-8") as fh:
            sys.stdout.write(fh.read())
        return
    m = re.match(r"^(\d+)(?:\s*-\s*(\d+))?$", args.chunks.strip())
    if not m:
        die("--chunks erwartet N oder A-B")
    lo = int(m.group(1))
    hi = int(m.group(2) or m.group(1))
    files = sorted(os.listdir(os.path.join(root, "chunks")))
    for name in files:
        n = int(name[:4])
        if lo <= n <= hi:
            with open(os.path.join(root, "chunks", name), encoding="utf-8") as fh:
                sys.stdout.write(fh.read())
                sys.stdout.write("\n")


def cmd_find(args):
    state = resolve_state(args.state)
    chunk_dir = os.path.join(sources_dir(state), args.slug, "chunks")
    if not os.path.isdir(chunk_dir):
        die("unbekannte Quelle: %s" % args.slug)
    try:
        rx = re.compile(args.pattern, re.I)
    except re.error as exc:
        die("ungültiger Ausdruck: %s" % exc)
    hits = 0
    for name in sorted(os.listdir(chunk_dir)):
        with open(os.path.join(chunk_dir, name), encoding="utf-8") as fh:
            body = fh.read()
        cid = re.search(r"^id: (\S+)", body, re.M)
        cid = cid.group(1) if cid else name
        page = "?"
        for line in body.split("\n"):
            marker = re.match(r"^\[S\. ([^\]]+)\]", line)
            if marker:
                page = marker.group(1)
            if rx.search(line) and not line.startswith(("---", "id:", "source:",
                                                        "pages:", "heading:",
                                                        "also:", "kind:",
                                                        "words:")):
                shown = re.sub(r"^\[S\. [^\]]+\]\s*", "", line)
                print("%s  S. %s  %s" % (cid, page, cell(shown)[:200]))
                hits += 1
                if hits >= args.limit:
                    note("Abbruch bei %d Treffern" % args.limit)
                    return
    if not hits:
        note("keine Treffer")


def cmd_verify(args):
    state = resolve_state(args.state)
    meta_path = os.path.join(sources_dir(state), args.slug, "source.json")
    if not os.path.isfile(meta_path):
        die("unbekannte Quelle: %s" % args.slug)
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    if not os.path.isfile(args.pdf):
        die("keine Datei: %s" % args.pdf)
    actual = sha256_of(args.pdf)
    if actual == meta.get("sha256"):
        print("ok — identische Datei, die Seitenverweise stimmen")
        return
    print("ABWEICHUNG — andere Datei als beim Ingest")
    print("  erwartet: %s" % meta.get("sha256"))
    print("  bekommen: %s" % actual)
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Nachträgliches Etikettieren
# --------------------------------------------------------------------------- #

def kind_report(rows):
    """Die `kind`-Verteilung sichtbar machen — und melden, wenn sie nichts taugt.

    Für Genres, an denen die Heuristik nie gemessen wurde, kann sie nicht
    zusagen, dass sie greift. Sie kann aber sagen, dass sie es nicht tat: Eine
    Quelle ohne einen einzigen `definition`- oder `example`-Chunk hat entweder
    wirklich keine Definitionen — oder ein Satzbild, das die Marker nicht setzen.
    Beides führt zur selben Handlung, und die soll dastehen, statt durch
    Nachzählen von Hand herauszukommen.
    """
    dist = collections.Counter(r["kind"] for r in rows)
    note("kind: %s" % ", ".join("%s %d" % (k, dist[k]) for k in sorted(dist)))
    if len(rows) >= 20 and not dist["definition"] and not dist["example"]:
        note("WARNUNG — %d Chunks, davon kein einziger `definition` oder "
             "`example`. Für dieses Buch taugt `kind` nicht als Filter; beim "
             "Kurrikulumbau gezielt über `find` einsteigen, statt nach "
             "`kind: definition` zu greifen." % len(rows))


def parse_chunk(path):
    """Eine Chunk-Datei in genau die Felder zurücklesen, die `write_index` braucht.

    Der Umkehrschluss zu `yaml_list`: Listen sind dort mit `", "` verbunden und
    tragen kein einziges echtes Anführungszeichen mehr im Inneren — `yaml_list`
    ersetzt es beim Schreiben durch ein einfaches. Deshalb ist das Trennen an
    dieser Zeichenfolge hier verlustfrei und nicht bloß meistens richtig.

    Ob es das wirklich war, entscheidet trotzdem nicht dieses Argument, sondern
    der Nachbau-Vergleich in `cmd_reclassify`.
    """
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        die("Chunk ohne Frontmatter: %s" % path)
    front, body = m.group(1), m.group(2)

    def scalar(key):
        hit = re.search(r"^%s:[ ]?(.*)$" % key, front, re.M)
        return hit.group(1).strip() if hit else None

    def listval(key):
        val = scalar(key)
        if not val or not (val.startswith("[") and val.endswith("]")):
            return []
        inner = val[1:-1].strip()
        return [p.strip().strip('"') for p in inner.split('", "')] if inner else []

    cid, kind, words = scalar("id"), scalar("kind"), scalar("words")
    if not cid or not kind or words is None:
        die("Chunk mit unvollständigem Frontmatter: %s" % path)
    return {
        "id": cid,
        "file": os.path.basename(path),
        "pages": listval("pages"),
        "path": listval("heading"),
        "also": listval("also"),
        "kind": kind,
        "words": int(words),
        "preview": re.sub(r"^\[S\. [^\]]+\]\s*", "", body).strip()[:90],
        "front": front,
        "body": body,
        "raw": raw,
    }


def cmd_reclassify(args):
    """`classify` erneut auf vorhandene Chunks anwenden — ohne das PDF.

    Warum überhaupt: Die Marker-Heuristik wird weiterentwickelt, das Original
    aber ist gitignored und überlebt den Container nicht. Ein erneuter Ingest
    wäre der einzige andere Weg und scheitert genau dann, wenn er gebraucht wird.

    Was hier NICHT passiert: Die Segmentierung wird nicht angefasst. `classify`
    läuft in `write_source` nachgelagert und speist die Abschnittsgrenzen nicht —
    Chunk-IDs, Seitenmarker und Bodies bleiben deshalb Zeichen für Zeichen
    stehen, und damit bleiben auch die Chunk-Bereiche in `MAP.md` gültig.
    """
    state = resolve_state(args.state)
    root = os.path.join(sources_dir(state), args.slug)
    meta_path = os.path.join(root, "source.json")
    if not os.path.isfile(meta_path):
        die("unbekannte Quelle: %s" % args.slug)
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)

    chunk_dir = os.path.join(root, "chunks")
    files = sorted(f for f in os.listdir(chunk_dir) if f.endswith(".md"))
    if not files:
        die("keine Chunks in %s" % chunk_dir)
    chunks = [parse_chunk(os.path.join(chunk_dir, f)) for f in files]

    # Der Nachbau-Beweis, vor jeder Änderung: Wenn der Index aus dem ZURÜCK-
    # GELESENEN Stand nicht zeichengleich herauskommt, hat das Parsen etwas
    # verloren — und dann darf hier nichts geschrieben werden, sonst wäre der
    # Verlust nach dem Neuschreiben nicht mehr sichtbar.
    idx_path = os.path.join(root, "index.md")
    if os.path.isfile(idx_path):
        with open(idx_path, encoding="utf-8") as fh:
            current = fh.read()
        if render_index(args.slug, meta, chunks) != current:
            die("Nachbau des Index weicht vom Bestand ab. Entweder wird das "
                "Frontmatter nicht verlustfrei zurückgelesen, oder chunks/ und "
                "index.md sind bereits uneinig — in beiden Fällen würde ein "
                "Neuschreiben den Unterschied verdecken. Abbruch ohne Änderung; "
                "zum Eingrenzen `git diff` auf die Quelle.")

    changed = []
    for c in chunks:
        new_kind = classify(c["body"], c["path"])
        if new_kind != c["kind"]:
            changed.append((c, c["kind"], new_kind))
        c["kind"] = new_kind

    for c, old, new in changed:
        note("  %s  %s → %s   %s"
             % (c["id"], old, new, (c["path"] or [""])[-1][:56]))
    if changed:
        before = collections.Counter(old for _, old, _ in changed)
        after = collections.Counter(new for _, _, new in changed)
        note("%s: %d von %d Chunks neu etikettiert (%s)"
             % (args.slug, len(changed), len(chunks),
                ", ".join("%s %+d" % (k, after[k] - before[k])
                          for k in sorted(set(before) | set(after)))))
    else:
        note("%s: keine Änderung (%d Chunks geprüft)" % (args.slug, len(chunks)))

    # Nach der Änderungsliste, nicht davor: So liest sich die Verteilung als
    # Ergebnis. Im Dry-Run ist sie der Stand, der herauskäme.
    kind_report(chunks)
    if not changed:
        return
    if args.dry_run:
        note("--dry-run: nichts geschrieben")
        return

    for c, _, _ in changed:
        front = re.sub(r"^kind: .*$", "kind: %s" % c["kind"], c["front"],
                       count=1, flags=re.M)
        with open(os.path.join(chunk_dir, c["file"]), "w",
                  encoding="utf-8") as fh:
            fh.write("---\n" + front + "\n---\n" + c["body"])
    write_index(root, args.slug, meta, chunks)
    # Provenienz getrennt halten: `tool` sagt, womit ingestet wurde, und das
    # bleibt wahr. Womit zuletzt etikettiert wurde, ist eine andere Aussage.
    meta["reclassified"] = {"date": datetime.date.today().isoformat(),
                            "tool": TOOL_VERSION}
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(idx_path)


# --------------------------------------------------------------------------- #
# Selftest der kind-Heuristik
# --------------------------------------------------------------------------- #
#
# Warum inline und nicht in der CI: `.github/workflows/test.yml` ist Upstream-
# Datei. Alles außerhalb von `.claude/` und `CLAUDE.md` soll bei
# `git merge upstream/main` konfliktfrei bleiben — ein Schritt dort wäre der
# erste Konflikt, den ein Update auslöst. Der Aufruf steht stattdessen in
# CLAUDE.md unter „Tests".
#
# Die Fälle sind keine erfundenen Beispiele: 2, 3 und 5 sind die Fehltreffer und
# Beinahe-Fehltreffer, die an Lindemann tatsächlich gemessen wurden.

PADDING = " ".join(["Fließtext"] * 320)

KIND_FIXTURES = [
    ("Rahmen ×2 → definition",
     "Der Begriff »Coach« stammt von dem englischen Wort für Kutsche. "
     "Unter Supervision versteht man die Reflexion beruflichen Handelns.",
     ["3 Beratungsformen"], "definition"),

    ("ein Rahmen allein reicht nicht",
     "Der Begriff »Coach« stammt von dem englischen Wort für Kutsche. "
     + PADDING,
     ["3 Beratungsformen"], "prose"),

    # Gemessen an Lindemann 0069: `Der Begriff` als blankes Stichwort hätte hier
    # zugeschlagen. Ohne definierendes Verb ist es keine Definition.
    ("»Der Begriff X bringt …« ist keine Definition",
     "Der Begriff der Attraktivität bringt einen weiteren Aspekt in die "
     "Zielerreichung ein. Der Begriff der Machbarkeit meldet sich dort "
     "ebenfalls zu Wort. " + PADDING,
     ["3.7.5 Weitere Kriterien"], "prose"),

    # Gemessen an Lindemann 0090: trug `definition` allein aus zwei »Satz«.
    ("»Satz« als Fließtextwort → prose",
     "Dieser Satz fiel spät im Gespräch. Ein Satz allein trägt noch nichts. "
     + PADDING,
     ["4.3.4 Überzeugungen und Glaubenssätze"], "prose"),

    ("»Satz 3.1« ist ein Lehrsatz → definition",
     "Satz 3.1 besagt, dass die Folge konvergiert. Satz 3.2 folgt daraus. "
     + PADDING,
     ["3 Konvergenz"], "definition"),

    # Der Kapitel-10-Fall: ein Übungsregister ist ein Verzeichnis, kein
    # Übungsteil. `toc-like` muss vor `exercise` greifen.
    ("Übungsregister mit Punktführung → toc-like",
     "\n".join("Übung %d: Spiegeln ............................ %d"
               % (i, 40 + i) for i in range(1, 8)),
     ["10.1 Übungen"], "toc-like"),

    # Der Querverweis-Fall: 15 Chunks bei Lindemann sahen so aus. Zwei Nennungen
    # in einem langen Fachabschnitt sind Verweise, kein Übungsteil — würde
    # `exercise` hier greifen, verlöre der Architect den Abschnitt.
    ("zwei Übungsverweise im Fachtext → prose",
     "Vergleiche dazu Übung 4 weiter unten. Siehe auch Übung 7. " + PADDING,
     ["3.5.6 Zirkuläre Fragen"], "prose"),

    ("dichter Aufgabenblock → exercise",
     "Aufgabe 1: Rollen benennen. Aufgabe 2: Perspektive wechseln. "
     "Aufgabe 3: Hypothese bilden. Aufgabe 4: Auftrag klären.",
     ["7 Übungsteil"], "exercise"),

    ("Überschrift Kasuistik → example",
     "Eine 43-jährige Patientin stellt sich mit anhaltender Erschöpfung vor. "
     + PADDING,
     ["5 Kasuistik"], "example"),

    ("Überschrift Klassifikation → definition",
     "Die Einteilung folgt den gebräuchlichen Kategorien. " + PADDING,
     ["2 Klassifikation der Störungen"], "definition"),

    ("Fallvokabular im Text → example",
     "Ein Fallbeispiel verdeutlicht das. Ein zweites Fallbeispiel folgt. "
     + PADDING,
     ["5 Anwendung"], "example"),

    ("Formelsatz bleibt formula-dense",
     "x = y + z ≤ a ± b ∑ c ∫ d √ e ≥ f ≠ g ∂ h α β γ δ θ λ μ σ π",
     ["4 Notation"], "formula-dense"),

    ("neutraler Fachtext bleibt prose",
     "Die Beratung verläuft in Phasen, die aufeinander aufbauen. " + PADDING,
     ["2.3 Beratung als Prozess"], "prose"),
]


def selftest_resolve_state():
    """`--state` muss absolut gelten — der Rückfall war ein stiller Fehlschlag.

    Der Fall braucht echte Verzeichnisse, weil genau das Dateisystem-Prädikat
    geprüft wird (`.git/` vorhanden oder nicht). Ein Mock würde die Zusage
    nicht belegen.
    """
    import io
    import tempfile
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        ohne = os.path.join(tmp, "kein-checkout")
        os.makedirs(ohne)
        saved, sys.stderr = sys.stderr, io.StringIO()
        try:
            got = resolve_state(ohne)
            bad.append(("--state ohne .git bricht ab", "Abbruch", got))
        except SystemExit:
            pass
        finally:
            sys.stderr = saved

        mit = os.path.join(tmp, "checkout")
        os.makedirs(os.path.join(mit, ".git"))
        got = resolve_state(mit)
        if got != os.path.abspath(mit):
            bad.append(("--state mit .git wird übernommen",
                        os.path.abspath(mit), got))
    return bad


def cmd_selftest(args):
    failures = [(name, expected, classify(text, path))
                for name, text, path, expected in KIND_FIXTURES
                if classify(text, path) != expected]
    failures += selftest_resolve_state()
    total = len(KIND_FIXTURES) + 2
    for name, expected, got in failures:
        sys.stderr.write("FAIL  %s: erwartet %s, bekommen %s\n"
                         % (name, expected, got))
    print("%d/%d Fixtures bestanden" % (total - len(failures), total))
    if failures:
        sys.exit(1)


# --------------------------------------------------------------------------- #
# MAP.md — die einzige dauerhafte Verbindung Lernstand ↔ Quelle
# --------------------------------------------------------------------------- #
#
# Als Kommandos und nicht als Handarbeit im Skill, weil ein Modell beim Editieren
# einer Tabelle zuverlässig irgendwann die Spaltenzahl verfehlt. Sobald aber ein
# Kommando Zeilen SUCHT statt schreibt, müssen Schreiber und Leser dasselbe Format
# meinen — deshalb steht es hier an einer Stelle und nicht als Format-String in
# jedem Kommando.

MAP_INTRO = ("# Quellen ↔ Themen\n\n"
             "Welches Engram-Thema aus welcher Quelle gebaut wurde. Das "
             "Node-Schema hat kein Quellenfeld — diese Tabelle ist der "
             "Ersatz.\n\n"
             "| Thema | Quelle | Chunks | Datum |\n|---|---|---|---|\n")

NO_CHUNKS = "—"


def map_path(state):
    return os.path.join(sources_dir(state), "MAP.md")


def map_row(topic, source, chunks, date=None):
    """Die eine Stelle, die weiß, wie eine Zeile aussieht.

    `cell()` ist dasselbe Escaping wie im Index: ein `|` im Themennamen würde die
    Spalten sonst sprengen — genau der Fehler, den diese Kommandos verhindern.
    """
    return "| %s | %s | %s | %s |\n" % (
        cell(topic), cell(source), cell(chunks or NO_CHUNKS),
        date or datetime.date.today().isoformat())


def split_row(line):
    """Eine Markdown-Tabellenzeile in ihre Zellen — Gegenstück zu `cell()`.

    Split auf unescapte `|`, damit ein escaptes `\\|` in der Zelle bleibt.
    """
    body = line.strip()
    if not (body.startswith("|") and body.endswith("|")):
        return None
    cells = [c.strip().replace("\\|", "|")
             for c in re.split(r"(?<!\\)\|", body[1:-1])]
    return cells if len(cells) == 4 else None


def read_map(state):
    """→ (lines, rows). Jede Zeile trägt ihren Index, damit remove/replace sie
    an Ort und Stelle treffen, statt die Datei neu zu schreiben."""
    path = map_path(state)
    if not os.path.isfile(path):
        return [], []
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    rows = []
    for i, line in enumerate(lines):
        cells = split_row(line)
        if not cells:
            continue
        if cells[0] == "Thema" or all(re.match(r"^:?-{2,}:?$", c) for c in cells):
            continue                      # Kopf- und Trennzeile
        rows.append({"idx": i, "topic": cells[0], "source": cells[1],
                     "chunks": cells[2], "date": cells[3], "line": line})
    return lines, rows


def write_map(state, lines):
    path = map_path(state)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    return path


def engine_topics(state):
    """Die Themen-Slugs aus der Engine — oder None, wenn sie nicht antwortet.

    `ENGRAM_HOME` wird bewusst auf `<state>/learning` GESETZT statt aus der
    Umgebung übernommen: MAP.md liegt in genau diesem Repo, und eine Tabelle aus
    Repo A gegen den Lernstand aus einem fremden Home zu prüfen, meldet lauter
    Themen als verwaist, die es gibt. Der Rückgabewert None heißt „nicht geprüft"
    und ist deshalb nicht dasselbe wie die leere Menge.
    """
    root = os.environ.get("ENGRAM_ROOT") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..")
    script = os.path.join(os.path.abspath(root), "scripts", "engram.py")
    if not os.path.isfile(script):
        return None
    env = dict(os.environ)
    env["ENGRAM_HOME"] = os.path.join(state, "learning")
    try:
        out = subprocess.check_output([sys.executable, script, "topics"],
                                      env=env, stderr=subprocess.DEVNULL)
        return set(t["topic"] for t in json.loads(out.decode("utf-8")))
    except Exception:
        return None


def cmd_map_add(args):
    state = resolve_state(args.state)
    lines, rows = read_map(state)
    if not lines:
        lines = [MAP_INTRO]
    chunks = norm(args.chunks or NO_CHUNKS)
    hit = [r for r in rows
           if r["topic"] == norm(args.topic) and r["source"] == norm(args.source)]

    # Schlüssel ist (Thema, Quelle) — NICHT die ganze Zeile. Ein Vergleich, der das
    # Datum einschließt, hält dieselbe Zuordnung morgen für eine neue.
    if any(r["chunks"] == chunks for r in hit):
        note("steht schon in MAP.md: %s" % hit[0]["line"].strip())
        return
    if hit and not args.replace:
        die("%s ↔ %s steht schon mit anderer Chunk-Angabe in MAP.md:\n  %s\n"
            "Mit --replace ersetzen oder erst `map-remove` aufrufen."
            % (args.topic, args.source, hit[0]["line"].strip()))

    row = map_row(args.topic, args.source, args.chunks)
    if hit:
        lines[hit[0]["idx"]] = row                    # an Ort und Stelle
        for r in hit[1:]:
            lines[r["idx"]] = None                    # Altlasten desselben Paars
        lines = [l for l in lines if l is not None]
    else:
        # Anker ist die letzte TABELLENZEILE, nicht die letzte Datenzeile: sonst
        # landet der erste Eintrag hinter Prosa, die unter einer leeren Tabelle steht.
        table = [i for i, l in enumerate(lines) if split_row(l)]
        at = table[-1] + 1 if table else len(lines)
        if at == len(lines) and lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.insert(at, row)
    print(write_map(state, lines))


def cmd_map_remove(args):
    """Der fehlende Gegenpart zu `map-add`.

    Engram kennt kein Löschen von Themen, nur `retire` — eine Zeile hier zu
    entfernen ist also fast immer eine Korrektur, kein Nachvollzug. Ohne Treffer
    bricht das Kommando ab: eine stille Erfolgsmeldung auf einen Tippfehler wäre
    schlimmer als die Karteileiche, die sie hinterlässt.
    """
    state = resolve_state(args.state)
    lines, rows = read_map(state)
    hit = [r for r in rows if r["topic"] == norm(args.topic)
           and (args.source is None or r["source"] == norm(args.source))]
    if not hit:
        die("keine Zeile für Thema %s%s in MAP.md (`map-check` zeigt den Stand)"
            % (args.topic, "" if args.source is None else
               " mit Quelle %s" % args.source))
    for r in hit:
        print("entfernt: %s" % r["line"].strip())
    drop = set(r["idx"] for r in hit)
    print(write_map(state, [l for i, l in enumerate(lines) if i not in drop]))


def cmd_map_check(args):
    """Gleicht die Tabelle gegen Engine und Quellenverzeichnis ab.

    Ein Thema OHNE Zeile ist ausdrücklich kein Befund: Themen aus Websuche haben
    legitim keine Quelle. Befunde sind nur Zeilen, die ins Leere zeigen, und
    doppelte Paare.
    """
    state = resolve_state(args.state)
    lines, rows = read_map(state)
    if not lines:
        note("noch keine MAP.md (%s)" % map_path(state))
        return

    topics = engine_topics(state)
    base = sources_dir(state)
    slugs = set(s for s in os.listdir(base)
                if os.path.isfile(os.path.join(base, s, "source.json"))
                ) if os.path.isdir(base) else set()

    print("MAP.md: %d Zeile(n) · Lernstand: %s"
          % (len(rows), os.path.join(state, "learning")))
    if topics is None:
        note("Engine nicht befragbar (engram.py nicht gefunden oder Fehler) — "
             "der Themen-Abgleich wurde ÜBERSPRUNGEN, nicht bestanden.")

    findings, seen = [], {}
    for r in rows:
        key = (r["topic"], r["source"])
        if key in seen:
            findings.append(("doppelt", r, "schon in Zeile %d" % (seen[key] + 1)))
        else:
            seen[key] = r["idx"]
        if topics is not None and r["topic"] not in topics:
            findings.append(("verwaistes Thema", r, "kein Graph in der Engine"))
        if r["source"] not in slugs:
            findings.append(("verwaiste Quelle", r,
                             "kein sources/%s/source.json" % r["source"]))

    for kind, r, why in findings:
        print("  %-17s Zeile %d: %s ↔ %s (%s)"
              % (kind, r["idx"] + 1, r["topic"], r["source"], why))

    mapped_topics = set(r["topic"] for r in rows)
    if topics:
        loose = sorted(topics - mapped_topics)
        if loose:
            print("  Hinweis: Themen ohne Zeile (ok, wenn ohne Buch gebaut): %s"
                  % ", ".join(loose))
    loose_src = sorted(slugs - set(r["source"] for r in rows))
    if loose_src:
        print("  Hinweis: Quellen ohne Zeile (noch keinem Thema zugeordnet): %s"
              % ", ".join(loose_src))

    if findings:
        print("%d Befund(e) — Zeilen mit `map-remove` oder `map-add --replace` "
              "richten." % len(findings))
        sys.exit(1)
    print("ok — keine verwaisten oder doppelten Zeilen")


def cmd_paths(args):
    state = resolve_state(args.state)
    print(json.dumps({"state": state, "sources": sources_dir(state),
                      "tool": TOOL_VERSION}, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(
        prog="engram-source",
        description="PDFs zu seitenreferenzierten Chunks für den Curriculum-Architect.")
    ap.add_argument("--state", help="Pfad zum engram-learning-Checkout")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="PDF ingesten")
    p.add_argument("pdf", help="Pfad oder http(s)-URL")
    p.add_argument("--slug")
    p.add_argument("--title")
    p.add_argument("--author")
    p.add_argument("--pages", help="Scope, z.B. 51-190")
    p.add_argument("--scope-label", help="lesbare Scope-Angabe, z.B. 'Kap. 3–7'")
    p.add_argument("--numbered-dot", action="store_true",
                   help="Kapitel sind '1. Titel' MIT Punkt (deutsche Konzept- "
                        "und Berichtstypografie). Vorgabe aus — in Sachbüchern "
                        "ist '1.' ein Listenpunkt, kein Kapitel.")
    p.add_argument("--keep-pdf", action="store_true",
                   help="Original nach <slug>/pdf/ kopieren (gitignored)")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="Quellen auflisten")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="Index oder einzelne Chunks ausgeben")
    p.add_argument("slug")
    p.add_argument("--chunks", help="N oder A-B")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("find", help="Volltextsuche mit Chunk-ID und Seitenzahl")
    p.add_argument("slug")
    p.add_argument("pattern")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("verify", help="sha256 eines wieder bereitgestellten PDFs")
    p.add_argument("slug")
    p.add_argument("pdf")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("reclassify",
                       help="kind neu vergeben, ohne das PDF (Bodies bleiben)")
    p.add_argument("slug")
    p.add_argument("--dry-run", action="store_true",
                   help="nur zeigen, was sich änderte")
    p.set_defaults(func=cmd_reclassify)

    p = sub.add_parser("selftest", help="Fixtures der kind-Heuristik prüfen")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("map-add", help="Zeile in sources/MAP.md schreiben")
    p.add_argument("--topic", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--chunks")
    p.add_argument("--replace", action="store_true",
                   help="bestehende Zeile desselben Paars (Thema, Quelle) "
                        "an ihrer Position ersetzen")
    p.set_defaults(func=cmd_map_add)

    p = sub.add_parser("map-remove", help="Zeile(n) aus sources/MAP.md entfernen")
    p.add_argument("--topic", required=True)
    p.add_argument("--source", help="nur die Zeile dieser Quelle")
    p.set_defaults(func=cmd_map_remove)

    p = sub.add_parser("map-check",
                       help="MAP.md gegen Engine und sources/ abgleichen")
    p.set_defaults(func=cmd_map_check)

    p = sub.add_parser("paths", help="State-Repo und sources/ auflösen")
    p.set_defaults(func=cmd_paths)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
