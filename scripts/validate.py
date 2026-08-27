"""
Is what we have actually what was published?

Three separate questions, and they need different checks:

  1. PROVENANCE  - can we prove which bytes we used? (checksums)
  2. COVERAGE    - did parsing silently drop text? (character accounting)
  3. STRUCTURE   - are there holes? (article numbering, expected landmarks)

Coverage is the one that catches real disasters. A parser that quietly keeps
60% of a document still runs, still produces plausible sections, and every
answer it can't find is blamed on retrieval instead of on the loss that
happened here.

Run:  .venv\\Scripts\\python.exe scripts\\validate.py
"""

import hashlib
import json
import pathlib
import re

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"

OK, WARN, FAIL = "[ok]  ", "[warn]", "[FAIL]"
issues = []


def note(level: str, msg: str) -> None:
    print(f"  {level} {msg}")
    if level != OK:
        issues.append(msg)


def section(title: str) -> None:
    print(f"\n{'=' * 68}\n{title}\n{'=' * 68}")


# --------------------------------------------------------------------------
section("1. PROVENANCE  -  checksums of every raw file")
# A SHA-256 is a fingerprint. If EUR-Lex re-consolidates the Act next month,
# the fingerprint changes and we know our results came from a different text.
#
# Only the source documents are fingerprinted. checksums.json is excluded for
# the obvious reason, and manifest.json because it is repo-managed metadata:
# it records where each source came from and gets edited legitimately, so
# hashing it means every honest edit reports as a source change. A check that
# fires when nothing is wrong is one you learn to ignore.
NOT_A_SOURCE = {"checksums.json", "manifest.json"}

checksums = {}
for path in sorted(RAW.rglob("*")):
    if path.is_file() and path.name not in NOT_A_SOURCE:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rel = str(path.relative_to(RAW)).replace("\\", "/")
        checksums[rel] = {"sha256": digest, "bytes": path.stat().st_size}

for rel, info in list(checksums.items())[:4]:
    print(f"  {rel:<34} {info['sha256'][:16]}...  {info['bytes']:>9,} B")
print(f"  ... {len(checksums)} files fingerprinted")

prev_path = RAW / "checksums.json"
if prev_path.exists():
    prev = json.loads(prev_path.read_text(encoding="utf-8"))
    changed = [k for k in checksums if k in prev and prev[k]["sha256"] != checksums[k]["sha256"]]
    if changed:
        note(WARN, f"{len(changed)} source file(s) changed since last run: {changed[:3]}")
    else:
        note(OK, "all source files identical to the previous run")
else:
    note(OK, "first run - checksums recorded as the baseline")
prev_path.write_text(json.dumps(checksums, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
section("2. COVERAGE  -  how much of the AI Act did we actually keep?")
html = (RAW / "eu_ai_act.html").read_text(encoding="utf-8", errors="replace")
soup = BeautifulSoup(html, "lxml")
source_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
source_chars = len(source_text)

act = json.loads((CLEAN / "eu_ai_act.json").read_text(encoding="utf-8"))
kept_chars = sum(s["chars"] for s in act)
pct = 100 * kept_chars / source_chars

print(f"  source HTML visible text : {source_chars:>9,} chars")
print(f"  captured into sections   : {kept_chars:>9,} chars")
print(f"  coverage                 : {pct:>9.1f}%")

if pct < 80:
    note(FAIL, f"only {pct:.1f}% of the Act was captured - parsing is losing text")
elif pct < 95:
    note(WARN, f"{100-pct:.1f}% of the Act is not in any section - identify what")
else:
    note(OK, f"{pct:.1f}% captured")

# What is the uncaptured text? Recitals are the usual answer, and they matter:
# they are interpretive, they discuss the same topics as the articles, and a
# system that cites a recital as a binding obligation is giving a wrong answer.
recital_markers = re.findall(r"\(\s*(\d{1,3})\s*\)\s+[A-Z]", source_text[:200000])
has_recital_word = "recital" in source_text.lower()
print(f"\n  numbered '(N) Text' markers in the first 200k chars: {len(recital_markers)}")
print(f"  the word 'recital' appears in the source: {has_recital_word}")

covered_ids = {s["id"] for s in act}
print(f"  sections parsed: {len(covered_ids)} ({len([s for s in act if s['type']=='article'])} articles, "
      f"{len([s for s in act if s['type']=='annex'])} annexes)")


# --------------------------------------------------------------------------
section("3. STRUCTURE  -  gaps, duplicates, landmarks")
articles = [s for s in act if s["type"] == "article"]
numbers = [a["number"] for a in articles]

dupes = {n for n in numbers if numbers.count(n) > 1}
note(FAIL if dupes else OK, f"duplicate article numbers: {sorted(dupes) if dupes else 'none'}")

# Base numbers should run 1..N with no holes. Letter suffixes (4a) are
# insertions made by amendments and are expected.
base = sorted({int(re.sub(r"[a-z]", "", n)) for n in numbers if n})
gaps = [i for i in range(1, max(base) + 1) if i not in base]
note(FAIL if gaps else OK,
     f"article numbers run 1-{max(base)}; missing: {gaps if gaps else 'none'}")

suffixed = [n for n in numbers if re.search(r"[a-z]", n or "")]
note(OK, f"amendment-inserted articles present: {suffixed}")

# Landmarks: specific things that must be there, checked by content not count.
LANDMARKS = [
    ("6", "high-risk", "Article 6 should discuss high-risk classification"),
    ("5", "prohibited", "Article 5 should discuss prohibited practices"),
    ("3", "definition", "Article 3 should contain definitions"),
    ("4a", "bias", "Article 4a (July 2026 amendment) should mention bias detection"),
]
print()
for num, needle, why in LANDMARKS:
    art = next((a for a in articles if a["number"] == num), None)
    if not art:
        note(FAIL, f"Article {num} missing entirely")
    elif needle not in (art["title"] + " " + art["text"]).lower():
        note(WARN, f"Article {num} present but '{needle}' not found - {why}")
    else:
        note(OK, f"Article {num}: {art['title'][:52]}")

# The cross-reference that the hardest questions depend on.
print()
art6 = next((a for a in articles if a["number"] == "6"), None)
anx3 = next((s for s in act if s["type"] == "annex" and s["number"] == "III"), None)
if art6 and anx3 and "III" in art6["refs_annex"]:
    note(OK, "Article 6 -> Annex III link intact (both present, reference recorded)")
else:
    note(FAIL, "Article 6 -> Annex III link broken")


# --------------------------------------------------------------------------
section("4. OTHER SOURCES")
for name, path, expect in [
    ("NIST", CLEAN / "nist.json", 20),
    ("OWASP", CLEAN / "owasp.json", 50),
]:
    data = json.loads(path.read_text(encoding="utf-8"))
    empty = [s for s in data if s["chars"] < 100]
    note(OK if len(data) >= expect else WARN,
         f"{name}: {len(data)} sections, {sum(s['chars'] for s in data):,} chars, "
         f"{len(empty)} under 100 chars")

# Every section must be citable, or it cannot be evaluated.
corpus = json.loads((CLEAN / "corpus.json").read_text(encoding="utf-8"))
uncitable = [s for s in corpus if not s.get("citation", "").strip()]
note(FAIL if uncitable else OK,
     f"sections without a citation: {len(uncitable)} of {len(corpus)}")


# --------------------------------------------------------------------------
section("VERDICT")
if not issues:
    print("  No problems found.")
else:
    print(f"  {len(issues)} thing(s) to look at:\n")
    for i, msg in enumerate(issues, 1):
        print(f"    {i}. {msg}")
print(f"\n  Checksums written to {prev_path}")
