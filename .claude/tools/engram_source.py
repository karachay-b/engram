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
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

TOOL_VERSION = "engram-source 1.0"

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
    """
    candidates = [
        explicit,
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

NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+\S")


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

    Die Schwelle darf NICHT bei "fast alle Seiten" liegen: ein laufender
    Kolumnentitel wechselt mit dem Kapitel, steht also nur auf dessen Seiten.
    Bei drei Kapiteln erreicht keiner davon 60 %. Deshalb: mindestens drei
    Seiten UND mindestens ein Fünftel des Buchs. Eine echte Überschrift kommt
    genau einmal vor und bleibt damit unangetastet.

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
            if 1 < len(key) <= 70:
                counts[key] = counts.get(key, 0) + 1
    threshold = max(3, 0.2 * len(pages))
    return {k for k, n in counts.items() if n >= threshold}


def is_heading(line):
    s = line.strip()
    if not (2 <= len(s) <= 90):
        return False
    if NUMBERED.match(s):
        return True
    if s.endswith((".", ",", ";", ":", "!", "?")):
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    if len(s) <= 60 and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return True
    return False


def heading_level(line):
    m = NUMBERED.match(line.strip())
    if m:
        return min(m.group(1).count(".") + 1, 4)
    return 1


def clean_page(raw, running):
    """Eine Seite → Blöcke [(kind, text)] mit kind in {"heading", "para"}.

    Überschriften werden VOR dem Umbruch erkannt und als eigener Block gehalten.
    Sonst verschmelzen sie beim Zusammenziehen der Zeilen mit dem Folgeabsatz —
    und die Heuristik-Gliederung hätte nichts mehr, woran sie schneiden kann.
    """
    text = normalize_chars(raw or "")
    lines = [l.rstrip() for l in text.split("\n")]

    # Kolumnentitel raus, aber nur am Seitenrand: dieselbe Zeichenfolge mitten im
    # Fließtext ist Inhalt, kein Kopfzeilen-Artefakt.
    if running:
        keep = []
        n = len(lines)
        for i, line in enumerate(lines):
            edge = i < 3 or i >= n - 3
            if edge and line.strip() and running_line_key(line) in running:
                continue
            keep.append(line)
        lines = keep

    # Silbentrennung am Zeilenende zusammenziehen — nur vor Kleinbuchstaben,
    # damit "Bayes-Regel" am Zeilenumbruch nicht zu "BayesRegel" wird.
    merged = []
    for line in lines:
        if merged and merged[-1].endswith("-") and line[:1].islower():
            merged[-1] = merged[-1][:-1] + line.lstrip()
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
        if is_heading(line) and (not buf or len(buf) == 0):
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
        blocks = clean_page(raw, running)
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
        # Derselbe Titel zweimal (Outlines doppeln Kapitel gern als ersten
        # Abschnitt) darf nicht zu "X › X" werden.
        parents = [s["title"] for s in stack if s["title"] != m["title"]]
        path = parents + [m["title"]]
        stack.append(m)
        end = marks[i + 1]["offset"] if i + 1 < len(marks) else doc_len
        if end > m["offset"]:
            sections.append({"path": path, "start": m["offset"], "end": end})
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

DEF_RE = re.compile(r"\b(Definition|Satz|Theorem|Lemma|Korollar|Axiom)\b", re.I)
EX_RE = re.compile(r"\b(Beispiel|Example)\b", re.I)
TASK_RE = re.compile(r"\b(Aufgabe|Übung|Exercise|Problem)\s*\d", re.I)
MATH_RE = re.compile(r"[=+×÷∑∫≤≥≠√±∞∂αβγδθλμσπΣΩ]")


def classify(text, path):
    head = " ".join(path).lower()
    lines = [l for l in text.split("\n") if l.strip()]

    dotted = sum(1 for l in lines if re.search(r"(\.{3,}|\s)\d{1,4}$", l.strip()))
    if lines and dotted / len(lines) > 0.4:
        return "toc-like"
    if len(TASK_RE.findall(text)) >= 2 or re.search(
            r"\b(aufgaben|übungen|exercises|problems)\b", head):
        return "exercise"
    if len(DEF_RE.findall(text)) >= 2 or DEF_RE.search(head):
        return "definition"
    if len(EX_RE.findall(text)) >= 2:
        return "example"
    if text and len(MATH_RE.findall(text)) / max(len(text), 1) > 0.012:
        return "formula-dense"
    return "prose"


# --------------------------------------------------------------------------- #
# Schreiben
# --------------------------------------------------------------------------- #

def yaml_list(items):
    return "[%s]" % ", ".join('"%s"' % str(i).replace('"', "'") for i in items)


def cell(text):
    return re.sub(r"\s+", " ", text).replace("|", "\\|").strip()


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


def write_index(root, slug, meta, rows):
    """Das Kartenblatt. Klein halten — es wird IMMER gelesen, die Chunks nicht."""
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
        "`kind: exercise` und `kind: toc-like` beim Kurrikulumbau überspringen.",
        "",
        "| id | Seiten | Überschrift | kind | W | Anfang |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        pages = r["pages"][0] if r["pages"][0] == r["pages"][-1] \
            else "%s–%s" % (r["pages"][0], r["pages"][-1])
        heading = " › ".join(r["path"])
        if r.get("also"):
            heading += " (+ %s)" % ", ".join(r["also"])
        out.append("| %s | %s | %s | %s | %d | %s |"
                   % (r["id"], pages, cell(heading), r["kind"],
                      r["words"], cell(r["preview"])))
    out.append("")
    path = os.path.join(root, "index.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
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
        "boundaries": boundary,
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
    print(idx)


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


def cmd_map_add(args):
    """Die einzige dauerhafte Verbindung Lernstand ↔ Quelle.

    Als Kommando und nicht als Handarbeit im Skill, weil ein Modell beim Editieren
    einer Tabelle zuverlässig irgendwann die Spaltenzahl verfehlt.
    """
    state = resolve_state(args.state)
    base = sources_dir(state)
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, "MAP.md")
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# Quellen ↔ Themen\n\n"
                     "Welches Engram-Thema aus welcher Quelle gebaut wurde. Das "
                     "Node-Schema hat kein Quellenfeld — diese Tabelle ist der "
                     "Ersatz.\n\n"
                     "| Thema | Quelle | Chunks | Datum |\n|---|---|---|---|\n")
    line = "| %s | %s | %s | %s |\n" % (args.topic, args.source,
                                        args.chunks or "—",
                                        datetime.date.today().isoformat())
    with open(path, encoding="utf-8") as fh:
        if line in fh.read():
            note("Zeile steht schon in MAP.md")
            return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
    print(path)


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

    p = sub.add_parser("map-add", help="Zeile in sources/MAP.md schreiben")
    p.add_argument("--topic", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--chunks")
    p.set_defaults(func=cmd_map_add)

    p = sub.add_parser("paths", help="State-Repo und sources/ auflösen")
    p.set_defaults(func=cmd_paths)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
