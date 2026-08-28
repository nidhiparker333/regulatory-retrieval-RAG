"""
Retrieval arms, so they can be compared instead of argued about.

Each arm is one retrieval strategy. Scoring them is free - no model, no API -
so a candidate fix can be measured before it is adopted, and dropped when it
turns out to buy nothing.

  dense    embedding similarity, brute force over all chunks
  bm25     sparse lexical scoring
  rrf      reciprocal rank fusion of the two

and two post-retrieval steps that can be layered on any of them:

  expand   anchor expansion + cross-reference following (the current default)
  diverse  guarantee each source group its best chunk in the result

Nothing here decides which arm is right. compare_arms.py measures that.
"""

import json
import pathlib
import re
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"

K_RRF = 60          # RRF smoothing constant; 60 is the standard default
CANDIDATE_K = 50    # per-retriever candidates before fusion

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


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------
# bm25s tokenises on `\b\w\w+\b` by default, which is the wrong pattern for
# this corpus: it drops every one- and two-character token, so "Article 6(2)"
# reduces to "article" and "Annex III" to "annex". The identifiers are the one
# thing BM25 is better at than embeddings, and the default tokeniser throws
# them away before scoring starts.
#
# Rather than loosen the pattern - which would flood the index with stray
# digits - citation forms are rewritten into single tokens and appended, so
# "Article 6(2)" also indexes as `article_6_2`.
RE_ARTICLE = re.compile(r"\bArticle\s+(\d+[a-z]?)(?:\((\d+)\))?", re.I)
RE_ANNEX = re.compile(r"\bAnnex\s+([IVXL]+)", re.I)
RE_OWASP = re.compile(r"\b(LLM\d{2})\b", re.I)
RE_NIST = re.compile(r"\bAI\s+(\d{3}-\d)\b", re.I)


def citation_tokens(text: str) -> list[str]:
    """Canonical single tokens for the identifiers in a passage or question."""
    out = []
    for num, sub in RE_ARTICLE.findall(text):
        out.append(f"article_{num.lower()}")
        if sub:
            out.append(f"article_{num.lower()}_{sub}")
    out += [f"annex_{n.lower()}" for n in RE_ANNEX.findall(text)]
    out += [m.lower() for m in RE_OWASP.findall(text)]
    out += [f"nist_{m.replace('-', '_')}" for m in RE_NIST.findall(text)]
    return out


def augment(text: str) -> str:
    toks = citation_tokens(text)
    return f"{text} {' '.join(toks)}" if toks else text


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------
class Retrieval:
    def __init__(self) -> None:
        self.chunks = json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8"))
        store = np.load(CLEAN / "index.npz", allow_pickle=True)
        self.vectors = store["vectors"]
        self.model_name = str(store["model"])
        self._embedder = None
        self._bm25 = None

    # -- lazily built, so a dense-only run never pays for either -------------
    @property
    def embedder(self):
        if self._embedder is None:
            from fastembed import TextEmbedding
            self._embedder = TextEmbedding(model_name=self.model_name)
        return self._embedder

    @property
    def bm25(self):
        if self._bm25 is None:
            import bm25s
            texts = [augment(c["text"]) for c in self.chunks]
            tokens = bm25s.tokenize(texts, stopwords="en", show_progress=False)
            retriever = bm25s.BM25()
            retriever.index(tokens, show_progress=False)
            self._bm25 = retriever
        return self._bm25

    # -- individual retrievers ----------------------------------------------
    def dense_rank(self, question: str, k: int) -> list[int]:
        q = np.array(list(self.embedder.query_embed([question])), dtype=np.float32)[0]
        q /= max(float(np.linalg.norm(q)), 1e-9)
        return list(np.argsort(-(self.vectors @ q))[:k])

    def dense_scores(self, question: str) -> np.ndarray:
        q = np.array(list(self.embedder.query_embed([question])), dtype=np.float32)[0]
        q /= max(float(np.linalg.norm(q)), 1e-9)
        return self.vectors @ q

    def bm25_rank(self, question: str, k: int) -> list[int]:
        import bm25s
        toks = bm25s.tokenize(augment(question), stopwords="en", show_progress=False)
        idx, _ = self.bm25.retrieve(toks, k=min(k, len(self.chunks)),
                                    show_progress=False)
        return [int(i) for i in idx[0]]

    # -- fusion --------------------------------------------------------------
    @staticmethod
    def rrf(rankings: list[list[int]], k: int = K_RRF) -> list[int]:
        """
        Fuse ranked lists by position, not score.

        BM25 scores are unbounded and cosine similarities sit in a narrow band;
        any attempt to normalise them into a common scale is doing hidden work
        that shifts per query. Rank is the one thing the two retrievers report
        on the same footing.
        """
        scores: dict[int, float] = defaultdict(float)
        for ranking in rankings:
            for rank, doc in enumerate(ranking, start=1):
                scores[doc] += 1.0 / (k + rank)
        return [d for d, _ in sorted(scores.items(), key=lambda x: -x[1])]

    # -- post-retrieval ------------------------------------------------------
    def expand(self, hits: list[dict]) -> list[dict]:
        """Anchor expansion, then cross-reference following. Unchanged."""
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
        slot: C01 returned five NIST passages and no Article 9, C05 returned
        the Act and no OWASP. In both cases the missing side was present in
        the corpus and simply out-ranked.

        This adds at most two chunks - the best from each source group not
        already represented - which is cheap and query-independent. Whether it
        actually recovers those questions is for compare_arms.py to say.
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

    # -- the arms ------------------------------------------------------------
    def search(self, question: str, arm: str = "dense", k: int = 5,
               expand: bool = True, diverse: bool = False) -> list[dict]:
        return self.search_traced(question, arm, k, expand, diverse)[0]

    def search_traced(self, question: str, arm: str = "dense", k: int = 5,
                      expand: bool = True, diverse: bool = False,
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

        if arm == "dense":
            order = list(np.argsort(-dense_s)[:k])
        elif arm == "bm25":
            order = self.bm25_rank(question, k)
        elif arm == "rrf":
            d = list(np.argsort(-dense_s)[:CANDIDATE_K])
            b = self.bm25_rank(question, CANDIDATE_K)
            order = self.rrf([d, b])[:k]
        else:
            raise ValueError(f"unknown arm: {arm}")

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
