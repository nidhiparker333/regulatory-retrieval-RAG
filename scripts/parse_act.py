"""
Step 2: turn 850KB of legal HTML into structured, labelled articles.

Why this matters more than it sounds: everything downstream depends on knowing
*which article* a piece of text came from. Without that label we can't cite,
and we can't measure whether retrieval found the right passage - which is the
entire free half of our evaluation.

We also record cross-references. When Article 6 says "referred to in Annex
III", we store that link. Later, retrieving Article 6 can automatically pull
in Annex III - which is how we solve multi-hop questions without an agent.

Run:  .venv\\Scripts\\python.exe scripts\\parse_act.py
"""

import json
import pathlib
import re

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "eu_ai_act.html"
OUT = ROOT / "data" / "clean" / "eu_ai_act.json"

# Article numbers can carry a letter suffix - Article 4a was inserted by the
# July 2026 amendment, so `\d+[a-z]?` rather than plain `\d+`.
RE_ANNEX_REF = re.compile(r"\bAnnex\s+([IVXL]+)\b")
RE_ARTICLE_REF = re.compile(r"\bArticle\s+(\d+[a-z]?)\b")


def _article_sort_key(ref: str) -> tuple[int, str]:
    """
    Order article references so 9 precedes 75 precedes 75a.

    The numeric part alone is not a total order: 75, 75a, 75b and 75d all
    reduce to 75, and the references arrive from a set, whose iteration order
    Python varies per process. Sorting on a non-total key left those ties in
    whatever order the set happened to yield, so parsing the same HTML twice
    produced corpus files with identical length and different bytes.

    That does not change which references get followed - membership of the set
    is what retrieval uses - but it does mean the corpus cannot be checksummed,
    which is the property the committed source bytes exist to provide.

    The letter suffix is the tiebreaker, making the key total and the output
    byte-identical across runs.
    """
    digits = re.sub(r"\D", "", ref)
    return (int(digits) if digits else 0, ref)

# EUR-Lex consolidation markers. On a consolidated text, "▼M1" opens a passage
# inserted or replaced by the first amending act - here, Regulation (EU)
# 2026/1744 - and "▼B" returns to the text of the basic act.
#
# They have to come out of the text: they would be embedded as content and
# could surface inside a quoted answer. But they must not be thrown away,
# because they identify precisely which passages the July 2026 amendment
# changed - which is otherwise invisible and is the most interesting thing
# about this version of the Act.
RE_MARKER = re.compile(r"[▼►]\s*([A-Z]\d*)")


def strip_markers(text: str) -> tuple[str, int, int]:
    """Remove consolidation markers. Returns (clean_text, n_amended, n_basic)."""
    found = RE_MARKER.findall(text)
    amended = sum(1 for m in found if m.startswith("M"))
    basic = sum(1 for m in found if m == "B")
    return RE_MARKER.sub(" ", text), amended, basic


def clean(s: str) -> str:
    """Collapse the whitespace that HTML-to-text conversion leaves behind."""
    return re.sub(r"\s+", " ", s).strip()


def clean_title(s: str) -> str:
    """
    Same, plus strip the stray quote marks EUR-Lex leaves on amended headings.
    Consolidated texts carry editorial marks around replaced wording, which is
    why 'Subject matter' arrived as "Subject matter'".
    """
    return clean(s).strip("'‘’“”\" ")


def main() -> None:
    soup = BeautifulSoup(SRC.read_text(encoding="utf-8", errors="replace"), "lxml")

    articles = []
    # Each article sits in a div marked .eli-subdivision whose id starts
    # with "art_". We found this by inspecting the document, not by guessing.
    for div in soup.select("div.eli-subdivision"):
        div_id = div.get("id", "")
        if not div_id.startswith("art_"):
            continue

        # The article's own number/title live in these two classes.
        num_el = div.select_one(".title-article-norm")
        title_el = div.select_one(".stitle-article-norm")
        if not num_el:
            continue

        label = clean(num_el.get_text(" "))          # e.g. "Article 6"
        title = clean_title(title_el.get_text(" ")) if title_el else ""

        m = re.search(r"(\d+[a-z]?)", label)
        number = m.group(1) if m else None

        body, n_amended, n_basic = strip_markers(clean(div.get_text(" ")))
        body = clean(body)
        # Strip the heading off the front so the body is just the substance.
        for prefix in (label + " " + title, label):
            if body.startswith(prefix):
                body = body[len(prefix):].strip()
                break

        # --- cross-references: the payload of this whole script ----------
        annex_refs = sorted(set(RE_ANNEX_REF.findall(body)))
        # An article always mentions itself in passing; drop self-references.
        article_refs = sorted(
            {a for a in RE_ARTICLE_REF.findall(body) if a != number},
            key=_article_sort_key,
        )

        articles.append({
            "id": div_id,
            "type": "article",
            "number": number,
            "label": label,
            "title": title,
            "text": body,
            "chars": len(body),
            "refs_annex": annex_refs,
            "refs_article": article_refs,
            # True where the July 2026 amendment inserted or replaced text.
            # Section-level, not passage-level: a marker anywhere in the
            # article flags the whole article. Coarse, but honest and stated.
            "amended_2026": n_amended > 0,
            "amendment_markers": n_amended,
        })

    # --- Annexes ---------------------------------------------------------
    # Annex containers carry id="anx_III" but NO class - they are not
    # .eli-subdivision elements like the articles are. Selecting on the id
    # prefix directly is what works. The `"." not in id` test drops nested
    # sub-elements such as "anx_III.tit_1", keeping only the containers.
    annexes = []
    for div in soup.select('div[id^="anx_"]'):
        div_id = div.get("id", "")
        if "." in div_id:
            continue

        number = div_id.replace("anx_", "")
        body, n_amended, n_basic = strip_markers(clean(div.get_text(" ")))
        body = clean(body)

        # The heading sits in <p class="title-annex-1">; the descriptive
        # subtitle, where present, is the element right after it.
        head_el = div.select_one(".title-annex-1")
        title = ""
        if head_el:
            nxt = head_el.find_next(["p", "div", "span"])
            if nxt:
                candidate = clean_title(nxt.get_text(" "))
                # Only treat it as a title if it reads like one, not a
                # paragraph of body text that happens to come next.
                if 0 < len(candidate) < 160:
                    title = candidate
            head_text = clean(head_el.get_text(" "))
            if body.startswith(head_text):
                body = body[len(head_text):].strip()

        annexes.append({
            "id": div_id,
            "type": "annex",
            "number": number,
            "label": f"Annex {number}",
            "title": title,
            "text": body,
            "chars": len(body),
            "refs_annex": sorted(set(RE_ANNEX_REF.findall(body)) - {number}),
            "refs_article": sorted(
                set(RE_ARTICLE_REF.findall(body)),
                key=_article_sort_key,
            ),
            "amended_2026": n_amended > 0,
            "amendment_markers": n_amended,
        })

    sections = articles + annexes
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(sections, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- Report what we got, so we can sanity-check it -------------------
    total_chars = sum(s["chars"] for s in sections)
    with_refs = [s for s in sections if s["refs_annex"] or s["refs_article"]]

    print(f"Articles parsed:   {len(articles)}")
    print(f"Annexes parsed:    {len(annexes)}")
    print(f"Total text:        {total_chars:,} chars  (~{total_chars // 4:,} tokens)")
    print(f"Sections that reference something else: {len(with_refs)} of {len(sections)}")
    print()

    if articles:
        sizes = sorted(a["chars"] for a in articles)
        print(f"Article size - smallest {sizes[0]:,}, median {sizes[len(sizes)//2]:,}, largest {sizes[-1]:,} chars")
        biggest = max(articles, key=lambda a: a["chars"])
        print(f"  largest is {biggest['label']}: {biggest['title'][:60]}")
        print()

    if annexes:
        print("Annexes:")
        for anx in annexes:
            print(f"  {anx['label']:<12} {anx['title'][:50]:<52} {anx['chars']:>7,} chars")
        print()

    # Article 6 -> Annex III is our canonical cross-reference case. Check that
    # both ends of it now exist, because that pair is what the hardest
    # evaluation questions depend on.
    art6 = next((a for a in articles if a["number"] == "6"), None)
    anx3 = next((a for a in annexes if a["number"] == "III"), None)

    if art6:
        print(f"{art6['label']}: {art6['title']}")
        print(f"  points to annexes:  {art6['refs_annex']}")
        print(f"  points to articles: {art6['refs_article'][:10]}")
    else:
        print("!! Article 6 not found - the parser needs work.")

    if anx3:
        print(f"\n{anx3['label']}: {anx3['title']}")
        print(f"  length: {anx3['chars']:,} chars")
        print(f"  opens: {anx3['text'][:300]}...")
        print("\n  -> Article 6 and Annex III are both present and linked.")
    else:
        print("\n!! Annex III still missing.")

    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
