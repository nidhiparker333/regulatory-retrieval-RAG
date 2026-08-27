"""
Final step of the data layer: merge the three cleaned sources into one file.

Everything downstream - chunking, embedding, retrieval, evaluation - reads
this single file. Which means from here on, nothing needs to know that the
Act was HTML, NIST was PDF, and OWASP was markdown. That messiness stops here.

Every section carries a `citation` string. That is what an answer will point
at, and what we check against our answer key when measuring retrieval. If a
section can't be cited, it can't be evaluated.

Run:  .venv\\Scripts\\python.exe scripts\\build_corpus.py
"""

import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
OUT = CLEAN / "corpus.json"

SOURCES = [
    ("eu_ai_act.json", "EU AI Act", "Regulation (EU) 2024/1689, consolidated 27 July 2026"),
    ("nist.json", "NIST", "NIST AI 100-1 and AI 600-1"),
    ("owasp.json", "OWASP", "OWASP LLM Top 10 (2026)"),
]


def citation_for(section: dict, source_group: str) -> str:
    """A human-checkable pointer to exactly where this text came from."""
    if source_group == "EU AI Act":
        # "Article 6" / "Annex III" - the article IS the citation unit.
        return section["label"]
    if source_group == "NIST":
        # A PDF has no articles, so the page is the citation unit.
        num = f"{section['number']} " if section.get("number") else ""
        return f"{section['source']}, {num}p.{section['page_start']}"
    return f"{section['label']} - {section['title'][:50]}"


def main() -> None:
    corpus = []

    for filename, group, full_name in SOURCES:
        path = CLEAN / filename
        if not path.exists():
            print(f"  ! missing {filename} - run its parser first")
            continue

        sections = json.loads(path.read_text(encoding="utf-8"))
        for s in sections:
            corpus.append({
                "id": s["id"],
                "source_group": group,
                "source_full": full_name,
                "type": s["type"],
                "label": s.get("label", ""),
                "title": s.get("title", ""),
                "citation": citation_for(s, group),
                "text": s["text"],
                "chars": s["chars"],
                # Only the Act has these; kept on every record so downstream
                # code never has to check which source it's holding.
                "refs_annex": s.get("refs_annex", []),
                "refs_article": s.get("refs_article", []),
                "page_start": s.get("page_start"),
            })

    OUT.write_text(json.dumps(corpus, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- Report ----------------------------------------------------------
    by_group = collections.Counter(s["source_group"] for s in corpus)
    chars_by_group = collections.Counter()
    for s in corpus:
        chars_by_group[s["source_group"]] += s["chars"]

    total_chars = sum(s["chars"] for s in corpus)

    print("=" * 62)
    print("CORPUS BUILT")
    print("=" * 62)
    print(f"{'Source':<14} {'Sections':>9} {'Characters':>12} {'~Tokens':>10}")
    print("-" * 62)
    for group in ("EU AI Act", "NIST", "OWASP"):
        if by_group[group]:
            print(f"{group:<14} {by_group[group]:>9} {chars_by_group[group]:>12,} {chars_by_group[group]//4:>10,}")
    print("-" * 62)
    print(f"{'TOTAL':<14} {len(corpus):>9} {total_chars:>12,} {total_chars//4:>10,}")

    sizes = sorted(s["chars"] for s in corpus)
    print(f"\nSection size: smallest {sizes[0]:,}, median {sizes[len(sizes)//2]:,}, largest {sizes[-1]:,}")
    oversized = [s for s in corpus if s["chars"] > 8000]
    print(f"Sections over 8,000 chars (will need splitting): {len(oversized)}")

    linked = [s for s in corpus if s["refs_annex"] or s["refs_article"]]
    print(f"Sections that cross-reference another section:    {len(linked)}")

    print("\nSample citations - this is what an answer will point at:")
    for s in (corpus[5], corpus[125], corpus[200], corpus[-40]):
        print(f"  {s['citation'][:58]:<60} {s['chars']:>6,} chars")

    print(f"\nWrote {OUT}")
    print("\nData layer complete. Next: chunking.")


if __name__ == "__main__":
    main()
