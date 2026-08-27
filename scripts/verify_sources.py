"""
Step 1: prove the sources are what they claim to be.

Two different questions, and both have to be answered:

  INTEGRITY - are the bytes the same ones the results were computed from?
              A sha256 per file answers this.

  IDENTITY  - is each file actually the document it is named after?
              A checksum cannot answer this. A truncated download, the wrong
              language edition, or the superseded 2024 text would all hash
              consistently and pass an integrity check forever.

Identity is the one that matters here. The AI Act is published in 24 languages
and in two formats, and it was amended in July 2026 - so "we downloaded the AI
Act" is not a claim a checksum can support. Each source below is therefore
checked against something only the correct document contains.

checksums.json covers the 18 source documents and deliberately does NOT cover
manifest.json. The manifest is repo-managed metadata that changes legitimately
(paths, notes); versioning it in git is the right mechanism. Checksumming it
here would mean every honest edit trips the integrity check and trains you to
ignore a failure - which is worse than not checking at all.

Run:  .venv\\Scripts\\python.exe scripts\\verify_sources.py
Exit code is non-zero if anything fails, so this can gate a build.
"""

import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

failures: list[str] = []
notes: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    """Record and print one assertion."""
    print(f"  [{'ok ' if ok else 'FAIL'}]  {label}{('   ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)
    return ok


def find(name: str) -> pathlib.Path | None:
    for p in (RAW / name, RAW / "owasp" / name):
        if p.exists():
            return p
    return None


# --------------------------------------------------------------------------
# 1. Integrity
# --------------------------------------------------------------------------
def verify_integrity() -> None:
    print("\n" + "=" * 72)
    print("1. INTEGRITY  -  are these the exact bytes the results came from?")
    print("=" * 72)

    recorded = json.loads((RAW / "checksums.json").read_text(encoding="utf-8"))
    ok = 0
    for name, meta in sorted(recorded.items()):
        path = find(name)
        if path is None:
            check(False, f"{name} present")
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest == meta["sha256"] and len(data) == meta["bytes"]:
            ok += 1
        else:
            check(False, f"{name} matches recorded sha256",
                  f"recorded {meta['sha256'][:12]}... got {digest[:12]}...")
    check(ok == len(recorded), f"all {len(recorded)} files match recorded sha256",
          f"({ok}/{len(recorded)})")


# --------------------------------------------------------------------------
# 2. Identity
# --------------------------------------------------------------------------
def verify_eu_ai_act() -> None:
    print("\n" + "=" * 72)
    print("2a. IDENTITY  -  EU AI Act: is this the CONSOLIDATED text?")
    print("=" * 72)

    html = (RAW / "eu_ai_act.html").read_text(encoding="utf-8", errors="replace")

    check("Regulation (EU) 2024/1689" in html, "names Regulation (EU) 2024/1689")

    # The decisive test. These six articles were inserted by the July 2026
    # amending regulation and do not exist in the original 2024 publication,
    # so their presence distinguishes the consolidated text from the version
    # most summaries and tooling still answer from.
    inserted = ["art_4a", "art_60a", "art_75a", "art_75b", "art_75c", "art_75d"]
    present = [a for a in inserted if f'id="{a}"' in html]
    check(len(present) == len(inserted),
          "amendment-only articles present (proves consolidated, not 2024)",
          f"{len(present)}/{len(inserted)}: {[a[4:] for a in present]}")

    check("2026/1744" in html, "cites amending Regulation (EU) 2026/1744")
    check("2026-07-27" in html, "carries consolidation date 2026-07-27")

    # Structural markup the parser depends on. If EUR-Lex ever changes its
    # HTML, this fails here rather than silently producing a thinner corpus.
    articles = len(re.findall(r'id="art_\d+', html))
    annexes = len(re.findall(r'id="anx_[IVX]+"', html))
    check(articles > 100, "article ids present for the parser", f"{articles} found")
    check(annexes == 14, "annex ids present", f"{annexes} found")

    # Annexes carry an id but no class - the bug that once returned zero
    # annexes while the pipeline appeared to work.
    check('id="anx_III"' in html, "Annex III reachable (referenced 54x by the Act)")


def verify_nist() -> None:
    print("\n" + "=" * 72)
    print("2b. IDENTITY  -  NIST: are these the right two publications?")
    print("=" * 72)

    import pypdf

    for filename, want_title, want_id in [
        ("nist_ai_100_1.pdf", "Risk Management Framework", "AI 100-1"),
        ("nist_ai_600_1.pdf", "Generative Artificial Intelligence Profile", "AI 600-1"),
    ]:
        reader = pypdf.PdfReader(str(RAW / filename))
        title = (reader.metadata or {}).get("/Title", "") or ""
        cover = (reader.pages[0].extract_text() or "").replace("\n", " ")
        check(want_title.lower() in title.lower(),
              f"{filename}: embedded PDF title", f"{title[:58]}")
        check(want_id.replace(" ", "") in cover.replace(" ", ""),
              f"{filename}: cover page names {want_id}", f"{len(reader.pages)} pages")


def verify_owasp() -> None:
    print("\n" + "=" * 72)
    print("2c. IDENTITY  -  OWASP: is this the 2026 edition?")
    print("=" * 72)

    files = sorted((RAW / "owasp").glob("*.md"))
    check(len(files) >= 13, "entry files present", f"{len(files)} markdown files")

    text = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files)

    # The 2026 edition renamed LLM08. In the 2025 list LLM08 was something
    # else entirely, so this heading is edition-specific rather than a date
    # string that could appear in any year's text.
    check("LLM08:2026 Hidden Context Exposure" in text,
          "LLM08 is 'Hidden Context Exposure' (2026-specific heading)")
    check("LLM01:2026" in text, "entries carry the :2026 edition tag")


def verify_glyph_expectations() -> None:
    """
    Not a pass/fail on the sources - a record of what the parser must remove.

    PDF extraction returns typographic ligatures as single codepoints, so
    "configuration" arrives as con + U+FB01 + guration. It looks correct and
    can never be found: no search for "fi" matches U+FB01. Counting them here
    means the cleaning step has a number to be checked against.
    """
    print("\n" + "=" * 72)
    print("3. GLYPHS  -  what the cleaning step has to remove")
    print("=" * 72)

    import collections
    import pypdf

    raw = "".join(f.read_text(encoding="utf-8", errors="replace")
                  for f in sorted((RAW / "owasp").glob("*.md")))
    for name in ("nist_ai_100_1.pdf", "nist_ai_600_1.pdf"):
        reader = pypdf.PdfReader(str(RAW / name))
        raw += "\n".join((p.extract_text() or "") for p in reader.pages)

    problem = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
               "ﬃ": "ffi", "ﬄ": "ffl",
               "●": "table dot (filled)", "○": "table dot (open)",
               "�": "replacement char"}
    counts = collections.Counter(c for c in raw if c in problem)
    for ch, n in counts.most_common():
        print(f"         U+{ord(ch):04X}  {problem[ch]:22} {n:>5}")
    total = sum(counts.values())
    notes.append(f"{total} glyphs in raw text must be normalised by the parser")
    print(f"\n         {total} total - the cleaned corpus must contain none of these")


def main() -> int:
    print("Verifying sources in", RAW)
    verify_integrity()
    verify_eu_ai_act()
    verify_nist()
    verify_owasp()
    verify_glyph_expectations()

    print("\n" + "=" * 72)
    print("VERDICT")
    print("=" * 72)
    for n in notes:
        print(f"  note: {n}")
    if failures:
        print(f"\n  {len(failures)} CHECK(S) FAILED:")
        for f in failures:
            print(f"    - {f}")
        return 1
    print("\n  All source checks passed. Integrity and identity both verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
