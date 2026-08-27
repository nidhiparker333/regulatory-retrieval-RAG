"""
Did the cuts land in sensible places?

Chunk counts tell you nothing about chunk quality. The only way to know is to
look at where one chunk ends and the next begins - a cut through the middle of
a sentence is invisible in the statistics and obvious to the eye.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
chunks = json.loads((ROOT / "data" / "clean" / "chunks.json").read_text(encoding="utf-8"))


def show_boundaries(section_id: str, limit: int = 3) -> None:
    parts = [c for c in chunks if c["section_id"] == section_id]
    if not parts:
        print(f"  (nothing for {section_id})")
        return
    print(f"\n{'=' * 74}")
    print(f"{parts[0]['citation'].split(' (')[0]} - split into {len(parts)} chunks")
    print("=" * 74)
    for c in parts[:limit]:
        body = c["text"].split("\n\n", 1)[-1]
        print(f"\n  --- {c['citation']} ({c['body_chars']:,} chars) ---")
        print(f"  STARTS: {body[:150]!r}")
        print(f"  ENDS  : ...{body[-110:]!r}")


# Does each chunk begin at something that looks like a real boundary?
STARTERS = re.compile(r"^(\d{1,2}\.|\([a-z]\)|[A-Z])")
clean_starts = 0
for c in chunks:
    body = c["text"].split("\n\n", 1)[-1].strip()
    if STARTERS.match(body):
        clean_starts += 1

print("=" * 74)
print("CHUNK BOUNDARY QUALITY")
print("=" * 74)
print(f"  chunks total                        : {len(chunks)}")
print(f"  starting at a capital, number or (a): {clean_starts} "
      f"({100*clean_starts/len(chunks):.1f}%)")

mid_word = [c for c in chunks
            if re.search(r"[a-z]$", c["text"].split('\n\n', 1)[-1].strip())
            and c["part"] < c["of_parts"]]
print(f"  ending mid-word or mid-clause       : {len(mid_word)}")

# Every chunk must still carry a citation, or it cannot be evaluated.
uncitable = [c for c in chunks if not c["citation"].strip()]
print(f"  chunks without a citation           : {len(uncitable)}")

# The link that matters most.
linked = [c for c in chunks if c["refs_annex"] or c["refs_article"]]
print(f"  chunks carrying cross-references    : {len(linked)}")

show_boundaries("art_6")
show_boundaries("art_3", limit=2)
