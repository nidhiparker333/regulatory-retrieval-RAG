"""
Step 3: pull text out of the two NIST PDFs.

PDFs are harder than HTML. HTML says "this is a heading"; a PDF just says
"draw these letters here". So there is no structure to read - we have to infer
it from how the text looks.

We keep page numbers. For a PDF, the page is the citation - saying "NIST AI
100-1, p.14" is what makes an answer checkable.

Run:  .venv\\Scripts\\python.exe scripts\\parse_nist.py
"""

import json
import pathlib
import re

from pypdf import PdfReader

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "clean" / "nist.json"

# `split_rmf` is per-document on purpose. AI 100-1 already has clean numbered
# sections, and splitting it on RMF function names as well shattered it into
# 77 fragments with a median of 221 characters. AI 600-1 needs it, because its
# largest block is an unnumbered table. Same corpus, different treatment - that
# is normal, and pretending one rule fits both is what produced the mess.
DOCS = [
    {
        "file": "nist_ai_100_1.pdf",
        "source": "NIST AI 100-1",
        "name": "AI Risk Management Framework 1.0",
        "split_rmf": False,
    },
    {
        "file": "nist_ai_600_1.pdf",
        "source": "NIST AI 600-1",
        "name": "Generative AI Profile",
        "split_rmf": True,
    },
]

# NIST numbers its sections two ways across the two documents:
#   AI 100-1:  "1.2.2 Risk Tolerance"      (no dot after the number)
#   AI 600-1:  "2.5. Environmental Impacts" (dot after the number)
# The `\.?` is what makes one pattern cover both. Missing it is why AI 600-1
# produced a single 85,000-character "section".
RE_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][^\n]{2,58})$")
RE_APPENDIX = re.compile(r"^(Appendix\s+[A-Z])[:.]?\s*([^\n]{0,58})$", re.I)

# AI 600-1's largest block is a suggested-actions table with no numbered
# headings at all - which is why it came out as one 80,000-character section.
# It does have structure, just NIST's own: every row hangs off one of the four
# AI RMF functions, e.g. "GOVERN 1.5: Ongoing monitoring and periodic review".
# Splitting on those turns an unusable blob into the most actionable content
# in the document.
RE_RMF_FUNCTION = re.compile(
    r"^((?:GOVERN|MAP|MEASURE|MANAGE)\s+[\d.]+)\s*:\s*(.+)$"
)

# A table-of-contents line is a heading followed by its page number:
#   "1.2.2 Risk Tolerance 7"
# Structurally identical to a heading, so length and shape can't separate
# them - the trailing page number is the only reliable tell.
RE_TOC_TAIL = re.compile(r"\s+\d{1,3}$")

# Repeated on every page; carries no meaning and pollutes every chunk.
RUNNING_HEADERS = re.compile(
    r"^(NIST AI \d+-\d+.*|NIST Trustworthy and Responsible AI.*|\d{1,3})$"
)


def looks_like_heading(line: str, split_rmf: bool = False) -> re.Match | None:
    """A heading, or something merely shaped like one?"""
    # Checked first, and only where the document needs it: these rows can run
    # longer than a normal heading, so the length guard below would reject them.
    if split_rmf:
        rmf = RE_RMF_FUNCTION.match(line)
        if rmf:
            return rmf

    if "http" in line or len(line) > 70:
        return None
    if RE_TOC_TAIL.search(line):          # table-of-contents entry
        return None

    m = RE_HEADING.match(line) or RE_APPENDIX.match(line)
    if not m:
        return None

    # Section numbers are small. "100 Bureau Drive (Mail Stop 8900)..." parses
    # as section 100 otherwise, and NIST's postal address becomes a chapter.
    first = m.group(1).split(".")[0]
    if first.isdigit() and int(first) > 20:
        return None
    return m


# PDF text extraction returns typographic ligatures as single characters:
# "configuration" arrives as "con" + U+FB01 + "guration". The word looks right
# and is not searchable - "fi" will never match U+FB01, because they are
# different characters. 373 of these were present across the two NIST PDFs.
LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
    "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
}

# Table markers from NIST's own layout. They carry no meaning in plain text
# and would otherwise be embedded as content.
TABLE_GLYPHS = {"●": " ", "○": " ", "•": " "}


def clean(s: str) -> str:
    for bad, good in LIGATURES.items():
        s = s.replace(bad, good)
    for bad, good in TABLE_GLYPHS.items():
        s = s.replace(bad, good)
    # PDF extraction leaves hyphens where words were broken across lines.
    s = re.sub(r"-\n\s*", "", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def main() -> None:
    sections = []

    for doc in DOCS:
        path = RAW / doc["file"]
        if not path.exists():
            print(f"  ! missing {path.name}")
            continue

        reader = PdfReader(str(path))
        n_pages = len(reader.pages)
        print(f"\n{doc['source']} - {doc['name']}")
        print(f"  pages: {n_pages}")

        # current section accumulates lines until the next heading appears
        current = {"heading": "Front matter", "number": None, "page_start": 1, "lines": []}
        doc_sections = []

        def flush(page_end: int) -> None:
            text = clean("\n".join(current["lines"]))
            if len(text) < 120:      # drop title pages, blank runs
                return
            doc_sections.append({
                "id": f"{doc['source'].replace(' ', '_').lower()}_{len(doc_sections):03d}",
                "type": "nist_section",
                "source": doc["source"],
                "number": current["number"],
                "label": f"{doc['source']} p.{current['page_start']}",
                "title": current["heading"],
                "page_start": current["page_start"],
                "page_end": page_end,
                "text": text,
                "chars": len(text),
                "refs_annex": [],
                "refs_article": [],
            })

        for page_no, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            for line in raw.splitlines():
                stripped = line.strip()
                if not stripped or RUNNING_HEADERS.match(stripped):
                    continue
                m = looks_like_heading(stripped, doc.get("split_rmf", False))
                if m:
                    flush(page_no)
                    # Titles are kept short for display; the full line stays
                    # in the section body either way.
                    title = (clean(m.group(2)) or clean(m.group(1)))[:90]
                    current = {
                        "heading": title,
                        "number": m.group(1),
                        "page_start": page_no,
                        "lines": [],
                    }
                else:
                    current["lines"].append(line)

        flush(n_pages)
        print(f"  sections found: {len(doc_sections)}")
        if doc_sections:
            sizes = sorted(s["chars"] for s in doc_sections)
            print(f"  size: smallest {sizes[0]:,}, median {sizes[len(sizes)//2]:,}, largest {sizes[-1]:,} chars")
            print("  first few headings:")
            for s in doc_sections[:6]:
                num = f"{s['number']} " if s["number"] else ""
                print(f"    p.{s['page_start']:<3} {num}{s['title'][:56]}")

        sections.extend(doc_sections)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(sections, indent=2, ensure_ascii=False), encoding="utf-8")

    total = sum(s["chars"] for s in sections)
    print(f"\nTotal: {len(sections)} sections, {total:,} chars (~{total//4:,} tokens)")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
