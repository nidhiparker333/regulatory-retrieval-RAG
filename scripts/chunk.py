"""
Step 4: cut 403 sections into retrieval-sized chunks.

Two jobs, and the second is the interesting one:

  1. Make every piece small enough to hand to a model.
  2. Make every piece still *citable and connected* once it's been cut.

Job 2 is what separates this from naive chunking. A fragment of Article 6 with
no label is unusable - you can't cite it, and "high-risk classification" is
much harder to find in a paragraph that never says those words. So every chunk
carries its heading, its citation, and its cross-references, even though only
the first chunk of a section contained them originally.

No AI here. This is entirely string handling.

Run:  .venv\\Scripts\\python.exe scripts\\chunk.py
"""

import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
OUT = CLEAN / "chunks.json"

# Sizes in characters. Roughly 4 characters per token, so ~450 tokens target.
# Swept - see sweep_chunking.py and FINDINGS. 1800 and 2400 score alike; 1200
# and 900 both lose C01. Not because they fragment Article 9 (it splits into
# eight parts at every size) but because they change which passages win the
# top five, and Article 9 is only ever reached through a cross-reference from
# one of them. Chunk size moves multi-hop reach, which is not obvious.
TARGET = 1800
MAX = 2600
OVERLAP = 200
# Lower than TARGET on purpose - see split_list_items(). Substantial list
# items clear it and stand alone; one-line items group until useful.
LIST_TARGET = 600
MIN_KEEP = 120          # below this a chunk carries no usable information

# F10: large, keyword-dense, and incapable of answering anything. They would
# match many queries and occupy retrieval slots that should hold real content.
DROP_TITLES = {"references", "front matter"}


def is_junk(section: dict) -> bool:
    title = (section.get("title") or "").strip().lower()
    if title in DROP_TITLES:
        return True
    # NIST AI 600-1 Appendix B is a bibliography under a different title.
    if "appendix b" in title and section["source_group"] == "NIST":
        return True
    return False


# --- Boundary finders, best first ----------------------------------------
# The drafter numbered their own paragraphs. Those numbers are better semantic
# boundaries than anything we could infer, and they cost nothing to find.
RE_NUMBERED = re.compile(r"(?=(?:^|\s)\d{1,2}\.\s+[A-Z(])")
RE_LETTERED = re.compile(r"(?=\s\([a-z]\)\s)")
RE_SENTENCE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(])")


def split_on(text: str, pattern: re.Pattern) -> list[str]:
    parts = [p.strip() for p in pattern.split(text) if p and p.strip()]
    return parts if len(parts) > 1 else []


def pack(pieces: list[str]) -> list[str]:
    """
    Combine small pieces up to TARGET, starting a new chunk before MAX.

    Packing rather than cutting is what keeps whole provisions together - a
    three-sentence paragraph stays intact instead of being sliced at an
    arbitrary character count.
    """
    chunks, current = [], ""
    for piece in pieces:
        if not current:
            current = piece
        elif len(current) + len(piece) + 1 <= TARGET:
            current = f"{current} {piece}"
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def is_enumerated_list(text: str) -> bool:
    """
    Is this section a list of numbered categories rather than prose?

    Annex III is the case that matters: eight numbered areas, each defining a
    class of high-risk system. Packing those together to fill a chunk is
    actively harmful - it produced a chunk containing the tail of "Education"
    and the head of "Employment", which is about neither.
    """
    return len(RE_NUMBERED.split(text)) >= 4


def split_list_items(text: str) -> list[str]:
    """
    Split at item boundaries, then group whole items - never splitting one.

    A chunk that is entirely "4. Employment, workers management and access to
    self-employment: (a) AI systems intended to be used for the recruitment or
    selection of natural persons..." is unambiguously about hiring. The same
    text merged with two other categories is not.

    But one-chunk-per-item is wrong when the items are one-liners: Annex VIII's
    registration list produced 26 chunks averaging 144 characters, which is
    barely a sentence and cannot answer anything.

    LIST_TARGET is deliberately low. Substantial items - Annex III's categories
    run 500-1,700 characters - exceed it immediately and stand alone, while
    short items accumulate until they are worth retrieving. Items are never cut.
    """
    items = [p.strip() for p in RE_NUMBERED.split(text) if p and p.strip()]

    grouped, current = [], ""
    for item in items:
        if len(item) > MAX:
            # Oversized single item: flush, then split it on inner boundaries.
            if current:
                grouped.append(current)
                current = ""
            grouped.extend(split_text(item))
        elif not current:
            current = item
        elif len(current) + len(item) + 1 <= LIST_TARGET:
            current = f"{current} {item}"
        else:
            grouped.append(current)
            current = item
    if current:
        grouped.append(current)
    return grouped


def split_text(text: str) -> list[str]:
    """Try boundaries in order of quality, stopping as soon as one works."""
    if len(text) <= MAX:
        return [text]

    # Checked before the general path: a list needs its items kept apart,
    # which is the opposite of what packing does.
    if is_enumerated_list(text):
        return split_list_items(text)

    for pattern in (RE_NUMBERED, RE_LETTERED, RE_SENTENCE):
        pieces = split_on(text, pattern)
        if pieces:
            packed = pack(pieces)
            # A boundary is only useful if it actually got us under the limit.
            if all(len(c) <= MAX for c in packed):
                return packed
            # Otherwise recurse into whichever pieces are still too large.
            out = []
            for c in packed:
                out.extend(split_text(c) if len(c) > MAX else [c])
            return out

    # Last resort: hard cut at word boundaries. Never mid-word.
    words, out, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > TARGET:
            out.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        out.append(current)
    return out


def merge_runts(pieces: list[str]) -> list[str]:
    """
    Fold pieces too short to stand alone into a neighbour, rather than dropping.

    The previous behaviour skipped anything under MIN_KEEP at write time, which
    had two consequences that were invisible in the output:

      Text was lost. Three pieces went, 290 characters, and two of them were
      operative provisions - Article 75a(8), a use limitation, and a sentence
      of Annex VII on examining technical documentation. Short is not the same
      as empty.

      Numbering broke. The loop kept enumerating over the unfiltered list, so
      parts came out gapped and `of_parts` counted pieces that were never
      written: Annex VII ran 1,3,4..8 labelled "of 8" with 7 chunks. Worse,
      Annex X lost part 1 entirely, and anchor expansion looks up `part == 1`
      to pull an article's opening - so that section could never be expanded,
      silently.

    Merging keeps every character, keeps parts contiguous, and keeps `of_parts`
    equal to the number of chunks actually written.
    """
    if len(pieces) < 2:
        return pieces

    merged: list[str] = []
    for piece in pieces:
        if len(piece) < MIN_KEEP and merged:
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)

    # A short first piece has no predecessor to fold into; fold it forward.
    if len(merged) > 1 and len(merged[0]) < MIN_KEEP:
        merged = [f"{merged[0]} {merged[1]}"] + merged[2:]
    return merged


def add_overlap(chunks: list[str]) -> list[str]:
    """
    Repeat the tail of each chunk at the head of the next.

    If an answer straddles a cut, one of the two chunks still contains it
    whole. Costs a little duplication, prevents a class of silent failure.
    """
    if len(chunks) < 2:
        return chunks
    out = [chunks[0]]
    for i in range(1, len(chunks)):
        tail = chunks[i - 1][-OVERLAP:]
        # Start the overlap at a word boundary so it doesn't open mid-word.
        space = tail.find(" ")
        if space > 0:
            tail = tail[space + 1:]
        out.append(f"{tail} {chunks[i]}")
    return out


def main() -> None:
    corpus = json.loads((CLEAN / "corpus.json").read_text(encoding="utf-8"))

    dropped = [s for s in corpus if is_junk(s)]
    kept = [s for s in corpus if not is_junk(s)]

    chunks = []
    split_count = 0

    for section in kept:
        as_list = is_enumerated_list(section["text"]) and len(section["text"]) > MAX
        pieces = split_text(section["text"])
        # Fold runts before overlap and before numbering, so `part` and
        # `of_parts` describe the chunks that actually get written.
        pieces = merge_runts(pieces)
        if len(pieces) > 1:
            # Overlap helps prose, where an answer can straddle a cut. It
            # hurts a list, where the whole point is keeping items apart -
            # prepending the tail of "Education" to the "Employment" chunk
            # reintroduces exactly the contamination we just removed.
            if not as_list:
                pieces = add_overlap(pieces)
            split_count += 1

        for i, piece in enumerate(pieces):
            # Every chunk gets the heading stamped on it. Chunk 4 of Article 6
            # never says "high-risk classification" in its own text - without
            # this, it is nearly unfindable and completely uncitable.
            header = section["citation"]
            if section["title"] and section["title"] not in header:
                header = f"{header} - {section['title']}"
            part = f" (part {i+1} of {len(pieces)})" if len(pieces) > 1 else ""

            chunks.append({
                "id": f"{section['id']}__{i:02d}",
                "section_id": section["id"],
                "source_group": section["source_group"],
                "citation": section["citation"] + part,
                "title": section["title"],
                # `text` is what gets embedded and shown to the model. The
                # header is part of it on purpose, not metadata alongside it.
                "text": f"{header}\n\n{piece}",
                "body_chars": len(piece),
                "chars": len(header) + 2 + len(piece),
                "part": i + 1,
                "of_parts": len(pieces),
                # Carried onto every part, not just the one that mentioned it.
                # This is how the Article 6 -> Annex III link survives cutting.
                "refs_annex": section["refs_annex"],
                "refs_article": section["refs_article"],
                "page_start": section.get("page_start"),
            })

    OUT.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- Report ----------------------------------------------------------
    sizes = sorted(c["chars"] for c in chunks)
    by_group = collections.Counter(c["source_group"] for c in chunks)
    total = sum(c["chars"] for c in chunks)

    print("=" * 68)
    print("CHUNKING")
    print("=" * 68)
    print(f"  dropped as junk       : {len(dropped)} sections "
          f"({sum(s['chars'] for s in dropped):,} chars)")
    for s in dropped:
        print(f"      - {s['citation'][:44]:<46} {s['chars']:>7,}")
    print(f"  sections in           : {len(kept)}")
    print(f"  sections that split   : {split_count}")
    print(f"  chunks out            : {len(chunks)}")
    print()
    for group in ("EU AI Act", "NIST", "OWASP"):
        if by_group[group]:
            print(f"  {group:<12} {by_group[group]:>5} chunks")
    print()
    print(f"  size: smallest {sizes[0]:,}, median {sizes[len(sizes)//2]:,}, largest {sizes[-1]:,}")
    print(f"  total {total:,} chars (~{total//4:,} tokens)")
    # Report both honestly. Overlap prepends up to OVERLAP characters to every
    # chunk after the first, so a chunk cut exactly at MAX legitimately lands
    # slightly above it. The previous line counted only chunks above
    # MAX + OVERLAP while announcing them as "over the 2,600 limit", which
    # printed 0 when three chunks were over 2,600.
    over_max = [c for c in chunks if c["chars"] > MAX]
    over_budget = [c for c in chunks if c["chars"] > MAX + OVERLAP]
    print(f"  chunks over MAX ({MAX:,}): {len(over_max)}"
          f"  - explained by overlap, which adds up to {OVERLAP}")
    print(f"  chunks over MAX+overlap ({MAX + OVERLAP:,}): {len(over_budget)}"
          f"  - these would be real violations")

    # Did the cross-reference links survive being cut?
    art6 = [c for c in chunks if c["section_id"].startswith("art_6") and c["section_id"] == "art_6"]
    print(f"\n  Article 6 became {len(art6)} chunk(s). Reference field on each:")
    for c in art6:
        print(f"    {c['citation'][:46]:<48} refs_annex={c['refs_annex']}")

    big = sorted(chunks, key=lambda c: -c["of_parts"])[:5]
    print("\n  Most-split sections:")
    for c in big:
        print(f"    {c['citation'][:52]:<54} {c['of_parts']} parts")

    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
