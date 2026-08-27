"""
Step 4: split the OWASP markdown into sections.

The easiest of the three sources - it is already markdown, and markdown says
outright where its headings are. This is what a well-structured source looks
like, and it's a useful contrast with the PDFs.

Run:  .venv\\Scripts\\python.exe scripts\\parse_owasp.py
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "owasp"
OUT = ROOT / "data" / "clean" / "owasp.json"

# Skip the empty file and the bare reference list - neither answers a question.
SKIP = {"Appendix_B_LLM_Application_Architecture_and_Threat_Modeling.md", "references.md"}

RE_H = re.compile(r"^(#{2,4})\s+(.+?)\s*$")


# The framework-mapping appendix uses filled and hollow circles in tables to
# indicate mapping strength. As plain text they carry no meaning, and 474 of
# them were being embedded as content.
TABLE_GLYPHS = {"●": "", "○": "", "◐": "", "•": "-"}

# Same ligature problem as the NIST PDFs, in case any survive conversion.
LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}


def clean(s: str) -> str:
    for bad, good in {**TABLE_GLYPHS, **LIGATURES}.items():
        s = s.replace(bad, good)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def main() -> None:
    sections = []

    for path in sorted(SRC.glob("*.md")):
        if path.name in SKIP or path.stat().st_size < 1000:
            print(f"  skip {path.name}")
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        # "LLM01_PromptInjection.md" -> "LLM01"
        entry = path.stem.split("_")[0]

        current = {"heading": path.stem, "level": 2, "lines": []}
        file_sections = []

        def flush() -> None:
            body = clean("\n".join(current["lines"]))
            if len(body) < 80:
                return
            file_sections.append({
                "id": f"owasp_{entry.lower()}_{len(file_sections):02d}",
                "type": "owasp_section",
                "source": "OWASP LLM Top 10 (2026)",
                "number": entry,
                # The heading carries the entry code so a chunk can be cited
                # without needing its neighbours for context.
                "label": f"OWASP {entry}",
                "title": current["heading"],
                "text": body,
                "chars": len(body),
                "refs_annex": [],
                "refs_article": [],
            })

        for line in text.splitlines():
            m = RE_H.match(line)
            if m:
                flush()
                current = {"heading": m.group(2), "level": len(m.group(1)), "lines": []}
            else:
                current["lines"].append(line)
        flush()

        print(f"  {path.name:<50} -> {len(file_sections)} sections")
        sections.extend(file_sections)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(sections, indent=2, ensure_ascii=False), encoding="utf-8")

    total = sum(s["chars"] for s in sections)
    print(f"\nTotal: {len(sections)} sections, {total:,} chars (~{total//4:,} tokens)")

    # The entry most relevant to what we're building.
    vec = [s for s in sections if s["number"] == "LLM09"]
    if vec:
        print(f"\nLLM09 (Vector and Embedding Weaknesses) - {len(vec)} sections:")
        for s in vec[:5]:
            print(f"  {s['title'][:60]:<62} {s['chars']:>6,} chars")

    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
