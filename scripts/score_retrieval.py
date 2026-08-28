"""
Score retrieval against the question set.

No model, no API, no cost. For each question we already wrote down which
sections must be retrieved; this checks whether they came back.

PREDICTION, recorded before the first run so it can be checked rather than
rationalised afterwards:
    - direct lookups score high
    - cross-reference scores noticeably lower
    - out-of-corpus is the worst of the four
    - cross-reference following (--follow) helps cross_ref and nothing else
If cross_ref beats direct, either the system or the test is wrong.

Two metrics, because they answer different questions:
    strict  - every expected section retrieved. What a complete answer needs.
    partial - fraction of expected sections retrieved. Shows near-misses that
              strict scoring hides, e.g. finding Annex III but not Article 6.

Run:  .venv\\Scripts\\python.exe scripts\\score_retrieval.py
"""

import collections
import json
import pathlib

import numpy as np
from fastembed import TextEmbedding

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
EVAL = ROOT / "data" / "eval"

chunks = json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8"))
store = np.load(CLEAN / "index.npz", allow_pickle=True)
vectors = store["vectors"]
questions = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]

model = TextEmbedding(model_name=str(store["model"]))


def retrieve(question: str, k: int, follow: bool):
    """Returns (retrieved_chunks, top_score)."""
    q = np.array(list(model.query_embed([question])), dtype=np.float32)[0]
    q /= max(float(np.linalg.norm(q)), 1e-9)
    scores = vectors @ q
    order = np.argsort(-scores)[:k]
    hits = [chunks[i] for i in order]
    top = float(scores[order[0]])

    if follow:
        have = {c["section_id"] for c in hits}
        want_anx = {a for c in hits for a in c.get("refs_annex", [])}
        want_art = {a for c in hits for a in c.get("refs_article", [])}
        for c in chunks:
            sid = c["section_id"]
            if sid in have:
                continue
            if (sid.startswith("anx_") and sid[4:] in want_anx) or \
               (sid.startswith("art_") and sid[4:] in want_art):
                hits.append(c)
                have.add(sid)
    return hits, top


def score(q: dict, hits: list) -> tuple[bool, float]:
    """Did we get what the answer needs? Returns (strict, partial)."""
    got_sections = {c["section_id"] for c in hits}
    got_sources = {c["source_group"] for c in hits}

    need_sections = q.get("expect_sections", [])
    need_sources = q.get("expect_sources", [])

    found = [s for s in need_sections if s in got_sections]
    found_src = [s for s in need_sources if s in got_sources]

    total_need = len(need_sections) + len(need_sources)
    total_found = len(found) + len(found_src)
    if total_need == 0:
        return True, 1.0          # out_of_corpus handled separately
    return total_found == total_need, total_found / total_need


def run(k: int, follow: bool) -> dict:
    rows = []
    for q in questions:
        hits, top = retrieve(q["question"], k, follow)
        strict, partial = score(q, hits)
        rows.append({**q, "strict": strict, "partial": partial, "top_score": top,
                     "n_retrieved": len(hits)})
    return rows


CONFIGS = [(5, False), (5, True), (10, False), (10, True)]
results = {f"k={k}{' +follow' if f else ''}": run(k, f) for k, f in CONFIGS}

CATS = ["direct", "cross_ref", "cross_doc"]

print("=" * 78)
print("RETRIEVAL BASELINE   (semantic search only, no tuning applied)")
print("=" * 78)

print(f"\n{'config':<14}", end="")
for c in CATS:
    print(f"{c:>14}", end="")
print(f"{'ALL':>10}")
print("-" * 78)

for name, rows in results.items():
    print(f"{name:<14}", end="")
    answerable = [r for r in rows if r["category"] != "out_of_corpus"]
    for c in CATS:
        sub = [r for r in rows if r["category"] == c]
        n = sum(1 for r in sub if r["strict"])
        print(f"{f'{n}/{len(sub)}':>14}", end="")
    n = sum(1 for r in answerable if r["strict"])
    print(f"{f'{n}/{len(answerable)}':>10}")

print("\n\nPARTIAL CREDIT  (fraction of required sections found)")
print("-" * 78)
print(f"{'config':<14}", end="")
for c in CATS:
    print(f"{c:>14}", end="")
print()
for name, rows in results.items():
    print(f"{name:<14}", end="")
    for c in CATS:
        sub = [r for r in rows if r["category"] == c]
        print(f"{np.mean([r['partial'] for r in sub]):>14.2f}", end="")
    print()

# --- wording, compared only inside `direct` where the split is 5/5 ---------
print("\n\nWORDING  (inside `direct` only - the one clean 5/5 comparison)")
print("-" * 78)
rows = results["k=5"]
for w in ("plain", "term_of_art"):
    sub = [r for r in rows if r["category"] == "direct" and r.get("wording") == w]
    n = sum(1 for r in sub if r["strict"])
    print(f"  {w:<14} {n}/{len(sub)}   mean partial {np.mean([r['partial'] for r in sub]):.2f}")

# --- out of corpus: is there a usable confidence signal? -------------------
print("\n\nOUT-OF-CORPUS  (retrieval always returns something - can we tell?)")
print("-" * 78)
rows = results["k=5"]
ooc = [r for r in rows if r["category"] == "out_of_corpus"]
ans = [r for r in rows if r["category"] != "out_of_corpus"]
print(f"  answerable questions   top score: mean {np.mean([r['top_score'] for r in ans]):.3f}"
      f"   min {min(r['top_score'] for r in ans):.3f}")
print(f"  unanswerable questions top score: mean {np.mean([r['top_score'] for r in ooc]):.3f}"
      f"   max {max(r['top_score'] for r in ooc):.3f}")
gap = min(r["top_score"] for r in ans) - max(r["top_score"] for r in ooc)
print(f"\n  separation: {gap:+.3f}", end="  ")
print("(positive = a threshold exists)" if gap > 0
      else "(negative = OVERLAP - no threshold can separate them)")
print("\n  unanswerable, individually:")
for r in ooc:
    print(f"    {r['id']}  top {r['top_score']:.3f}   {r['question'][:56]}")

# --- per question ----------------------------------------------------------
print("\n\nEVERY QUESTION  (k=5 +follow)")
print("-" * 78)
rows = results["k=5 +follow"]
for r in rows:
    if r["category"] == "out_of_corpus":
        continue
    mark = "PASS" if r["strict"] else ("part" if r["partial"] > 0 else "MISS")
    print(f"  {r['id']}  {mark:<5} {r['partial']:.2f}  top {r['top_score']:.3f}  {r['question'][:52]}")

(EVAL / "baseline_results.json").write_text(
    json.dumps({k: [{kk: vv for kk, vv in r.items() if kk != "notes"} for r in v]
                for k, v in results.items()}, indent=2),
    encoding="utf-8",
)
print(f"\nWrote {EVAL / 'baseline_results.json'}")
print("Cost: $0.00")
