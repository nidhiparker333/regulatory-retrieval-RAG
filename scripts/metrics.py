"""
The full metric set: accuracy, latency, cost, index.

Reads the saved evaluation results rather than re-running, so this is a
report of a specific measured run and can be regenerated for free.

Latency is reported split, because retrieval and generation have completely
different profiles - one is milliseconds and free, the other is seconds and
costs money. A single end-to-end number hides which is which, and hides that
only one of them is worth optimising.

Percentiles rather than averages: a mean latency is dominated by the fast
cases and tells you nothing about the experience of waiting.

Run:  .venv\\Scripts\\python.exe scripts\\metrics.py
"""

import json
import pathlib
import statistics as stats

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"
CLEAN = ROOT / "data" / "clean"

data = json.loads((EVAL / "full_eval_results.json").read_text(encoding="utf-8"))
rows = [r for r in data["results"] if "error" not in r]
chunks = json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8"))
corpus = json.loads((CLEAN / "corpus.json").read_text(encoding="utf-8"))
index_bytes = (CLEAN / "index.npz").stat().st_size

answerable = [r for r in rows if r["category"] != "out_of_corpus"]
ooc = [r for r in rows if r["category"] == "out_of_corpus"]


def pct(vals, p):
    if not vals:
        return 0
    return float(np.percentile(vals, p))


def rule(t):
    print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")


print("=" * 72)
print("GOVERNANCE RAG - MEASURED RESULTS")
print("=" * 72)
print(f"  Question set : {len(rows)} questions, answer keys written from the")
print(f"                 source documents before any retrieval was run")
print(f"  Corpus       : {len(corpus)} sections -> {len(chunks)} chunks")

# --------------------------------------------------------------- accuracy
rule("BEHAVIOUR AND GROUNDING")

# Neither column is "accuracy", and the heading used to say it was.
#
#   answered  - did the system attempt an answer rather than refuse? That is
#               all `behaved` records. It never inspects what the answer says,
#               so a fluent, wrong, well-cited answer scores here exactly like
#               a right one. Reported as "correct" under a heading of
#               "ACCURACY", it claimed something no code in this repo checks.
#
#   grounded  - did the answer cite at least one section the answer key
#               requires? That does inspect citations, and it is the stronger
#               of the two - but it is still "cited something required", not
#               "is correct". A question needing Article 6 and Annex III
#               scores grounded on either one alone.
#
# Judging correctness would need a human read or a scored rubric. Until that
# exists, these are the two things actually measured, named for what they are.
CATS = [("direct", "Answer in one section"),
        ("cross_ref", "Answer spans linked sections"),
        ("cross_doc", "Answer spans different documents")]

print(f"  {'':38} {'answered':>9} {'grounded':>10}")
for cat, name in CATS:
    sub = [r for r in rows if r["category"] == cat]
    ok = sum(1 for r in sub if r["behaved"])
    gr = [r for r in sub if r["grounded"] is not None]
    grounded = sum(1 for r in gr if r["grounded"])
    g = f"{grounded}/{len(gr)}" if gr else "n/a"
    print(f"  {name:<38} {f'{ok}/{len(sub)}':>9} {g:>10}")

ok = sum(1 for r in answerable if r["behaved"])
gr = [r for r in answerable if r["grounded"] is not None]
grounded = sum(1 for r in gr if r["grounded"])
print(f"  {'-' * 60}")
print(f"  {'ANSWERABLE QUESTIONS':<38} {f'{ok}/{len(answerable)}':>9} "
      f"{f'{grounded}/{len(gr)}':>10}")

refused_ok = sum(1 for r in ooc if r["behaved"])
print(f"\n  {'Unanswerable, correctly refused':<38} {f'{refused_ok}/{len(ooc)}':>9}")

uncited = [r for r in answerable if r["n_citations"] == 0 and not r["refused"]]
print(f"  {'Answers with no citation':<38} {len(uncited):>9}")

wrong_refusals = [r for r in answerable if r["refused"]]
print(f"  {'Refused when it could have answered':<38} {len(wrong_refusals):>9}"
      f"   {[r['id'] for r in wrong_refusals]}")

# --------------------------------------------------------------- latency
rule("LATENCY")

search = [r["search_ms"] for r in rows if r.get("search_ms")]
gen = [r["generate_ms"] for r in rows if r.get("generate_ms")]
total = [r["elapsed_ms"] for r in rows if r.get("elapsed_ms")]

if search and gen and total:
    print(f"  {'':22} {'p50':>9} {'p95':>9} {'min':>9} {'max':>9}")
    for name, vals in [("Retrieval", search), ("Generation", gen), ("End to end", total)]:
        unit = "ms" if name == "Retrieval" else "s"
        div = 1 if name == "Retrieval" else 1000
        fmt = (lambda v: f"{v/div:.0f}{unit}") if div == 1 else (lambda v: f"{v/div:.1f}{unit}")
        print(f"  {name:<22} {fmt(pct(vals,50)):>9} {fmt(pct(vals,95)):>9} "
              f"{fmt(min(vals)):>9} {fmt(max(vals)):>9}")

    share = stats.median(gen) / stats.median(total) * 100
    print(f"\n  Generation is {share:.0f}% of the wait. Retrieval is "
          f"{stats.median(search):.0f}ms - not worth optimising.")
else:
    print("  No timing data in the saved results - re-run run_full_eval.py")

# --------------------------------------------------------------- cost
rule("COST")

costs = [r["cost_usd"] for r in rows if r.get("cost_usd")]
tin = [r["tokens_in"] for r in rows if r.get("tokens_in")]
tout = [r["tokens_out"] for r in rows if r.get("tokens_out")]

print(f"  Per question          ${stats.mean(costs):.4f}   "
      f"(min ${min(costs):.4f}, max ${max(costs):.4f})")
print(f"  Full evaluation run   ${sum(costs):.2f}")
if tin:
    print(f"  Tokens in / out       {stats.mean(tin):,.0f} / {stats.mean(tout):,.0f} per question")
print(f"  Embedding             $0.00  (local model, CPU)")
print(f"  Vector database       $0.00  (none - a {index_bytes/1_000_000:.1f} MB file)")
print(f"\n  1,000 questions would cost ${stats.mean(costs)*1000:.0f}.")

# --------------------------------------------------------------- system
rule("SYSTEM")
store = np.load(CLEAN / "index.npz", allow_pickle=True)
v = store["vectors"]
print(f"  Index                 {v.shape[0]} x {v.shape[1]} float32, "
      f"{index_bytes/1_000_000:.1f} MB on disk")
print(f"  Embedding model       {str(store['model'])} (local, no API)")
print(f"  Generation model      claude-sonnet-5")
print(f"  Infrastructure        none - no vector database, no server for search")

rule("WHAT IS NOT MEASURED")
print("""  - Answer quality beyond citation grounding. Whether an answer is a
    good summary, not merely supported, is unassessed.
  - Performance on any corpus but this one.
  - Anything at scale. 26 questions is a small sample and every figure
    above should be read as a fraction, not a percentage.
  - Whether the answer keys are the only defensible ones. They are one
    reading of what a complete answer requires.""")
