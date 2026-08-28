"""
Retrieval, and the post-retrieval steps layered on it.

Search is dense: every chunk is a 384-number vector, the question becomes one
too, and similarity is a single matrix multiply over all 856 of them. Brute
force, exact, and sub-millisecond at this size - there is no vector database
and nothing to run.

Two steps are layered on top of the raw ranking, and both were adopted because
they were measured, not because they sounded right:

  expand   pull in an article's opening paragraph when retrieval landed in the
           middle of it, then follow the references the retrieved passages make
  diverse  give each source group its best chunk, so a question needing two
           documents cannot be answered from one

compare_arms.py scores these against the question set, for free, so a candidate
change can be checked before it is adopted.
"""

import json
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"

# Cross-reference following used to stop after four references. Measured on the
# question set, that cap cost three questions: cross_ref went 5/8 at cap 4 and
# 7/8 uncapped, because the fourth reference is not reliably the useful one -
# they are collected in corpus order, not by relevance.
#
# Bounding by context size instead of by count targets the thing that actually
# matters. Passage count is a proxy for cost; characters are the cost. At this
# budget nothing on the current set is truncated (the largest question builds
# 41,564 characters) while a pathological question still cannot run away.
MAX_CONTEXT_CHARS = 60_000


class Retrieval:
    def __init__(self) -> None:
        self.chunks = json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8"))
        store = np.load(CLEAN / "index.npz", allow_pickle=True)
        self.vectors = store["vectors"]
        self.model_name = str(store["model"])
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            from fastembed import TextEmbedding
            self._embedder = TextEmbedding(model_name=self.model_name)
        return self._embedder

    def dense_scores(self, question: str) -> np.ndarray:
        q = np.array(list(self.embedder.query_embed([question])), dtype=np.float32)[0]
        q /= max(float(np.linalg.norm(q)), 1e-9)
        return self.vectors @ q

    # -- post-retrieval ------------------------------------------------------
    def expand(self, hits: list[dict]) -> list[dict]:
        """
        Add an article's opening, then follow the references it makes.

        Legal drafting states the general rule in paragraph 1 and the
        exceptions after it, so landing mid-article is a distinct failure from
        missing the article: the opening of an article is always relevant
        context for any part of it.

        Following references is what closes a multi-hop question. Retrieving
        any part of Annex III pulls in Article 6, because Annex III's own
        heading cites it - a link recorded when the document was parsed, not
        one a model decided on.
        """
        chunks = self.chunks
        out = list(hits)

        have_chunks = {h["id"] for h in out}
        anchors = []
        for h in out:
            if h.get("part", 1) == 1 or h.get("of_parts", 1) == 1:
                continue
            first = next((c for c in chunks
                          if c["section_id"] == h["section_id"] and c["part"] == 1), None)
            if first and first["id"] not in have_chunks:
                anchors.append(dict(first, score=None))
                have_chunks.add(first["id"])
        out += anchors

        have = {h["section_id"] for h in out}
        want_anx = {a for h in out for a in h.get("refs_annex", [])}
        want_art = {a for h in out for a in h.get("refs_article", [])}

        budget = MAX_CONTEXT_CHARS - sum(len(h["text"]) for h in out)
        followed = []
        for c in chunks:
            sid = c["section_id"]
            if sid in have:
                continue
            if (sid.startswith("anx_") and sid[4:] in want_anx) or \
               (sid.startswith("art_") and sid[4:] in want_art):
                if len(c["text"]) > budget:
                    continue
                budget -= len(c["text"])
                followed.append(dict(c, score=None))
                have.add(sid)
        return out + followed

    def diversify(self, hits: list[dict], scores: np.ndarray) -> list[dict]:
        """
        Give every source group its best chunk.

        A question spanning two documents fails when one of them wins every
        slot: one returned five NIST passages and no Article 9, another the Act
        and no OWASP. In both cases the missing side was present in the corpus
        and simply out-ranked.

        This adds at most two chunks - the best from each source group not
        already represented - which is cheap and query-independent. Measured:
        cross-document questions went 0/2 to 2/2.
        """
        present = {h["source_group"] for h in hits}
        have = {h["id"] for h in hits}
        extra = []
        for group in {c["source_group"] for c in self.chunks} - present:
            idx = [i for i, c in enumerate(self.chunks) if c["source_group"] == group]
            if not idx:
                continue
            best = max(idx, key=lambda i: scores[i])
            if self.chunks[best]["id"] not in have:
                extra.append(dict(self.chunks[best], score=float(scores[best])))
        return hits + extra

    # -- entry points --------------------------------------------------------
    def search(self, question: str, k: int = 5,
               expand: bool = True, diverse: bool = True) -> list[dict]:
        return self.search_traced(question, k, expand, diverse)[0]

    def search_traced(self, question: str, k: int = 5,
                      expand: bool = True, diverse: bool = True,
                      ) -> tuple[list[dict], list[dict]]:
        """
        Same retrieval, plus the step-by-step record the answer path shows.

        answer.py used to carry its own copy of this logic. Two
        implementations of the same thing drift - which is exactly how the two
        scorers came to disagree about which questions were gradable - so the
        evaluation and the answering path now run the same code.
        """
        import time
        steps: list[dict] = []

        t0 = time.perf_counter()
        dense_s = self.dense_scores(question)
        search_ms = (time.perf_counter() - t0) * 1000

        order = list(np.argsort(-dense_s)[:k])
        hits = [dict(self.chunks[i], score=float(dense_s[i])) for i in order]
        steps.append({
            "step": "search",
            "detail": f"compared the question against all {len(self.chunks)} passages",
            "ms": round(search_ms, 2),
            "results": [{"citation": h["citation"], "score": round(h["score"], 3),
                         "source": h["source_group"]} for h in hits],
        })

        if diverse:
            before = {h["id"] for h in hits}
            hits = self.diversify(hits, dense_s)
            added = [h for h in hits if h["id"] not in before]
            if added:
                steps.append({
                    "step": "source_diversity",
                    "detail": "a source with no passage in the top results was given its best one",
                    "results": [{"citation": a["citation"], "source": a["source_group"]}
                                for a in added],
                })

        if expand:
            before = {h["id"] for h in hits}
            seen_sections = {h["section_id"] for h in hits}
            hits = self.expand(hits)
            anchors = [h for h in hits if h["id"] not in before
                       and h["section_id"] in seen_sections]
            followed = [h for h in hits if h["id"] not in before
                        and h["section_id"] not in seen_sections]
            if anchors:
                steps.append({
                    "step": "anchor_expansion",
                    "detail": "landed mid-article, so the article's opening paragraph was added",
                    "results": [{"citation": a["citation"], "source": a["source_group"]}
                                for a in anchors],
                })
            if followed:
                steps.append({
                    "step": "follow_cross_references",
                    "detail": "the retrieved passages cite these, so they were pulled in too",
                    "results": [{"citation": f["citation"], "source": f["source_group"]}
                                for f in followed],
                })

        return hits, steps
