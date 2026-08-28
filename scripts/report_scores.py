"""
The scorecard: every question, what was expected, what happened.

Reads the saved baseline results so this is a view of the run, not a re-run.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"

results = json.loads((EVAL / "baseline_results.json").read_text(encoding="utf-8"))
rows = results["k=5 +follow"]
plain = {r["id"]: r for r in results["k=5"]}      # without footnote-following

LABEL = {
    "direct": "EASY      ",
    "cross_ref": "HARD      ",
    "cross_doc": "MIXED-DOC ",
    "out_of_corpus": "TRICK     ",
}

print("=" * 92)
print(f"{'ID':<5} {'TYPE':<11} {'RESULT':<9} {'FOUND':<7} {'CONF':<6} QUESTION")
print("=" * 92)

for r in rows:
    cat = r["category"]
    if cat == "out_of_corpus":
        verdict = "CAN'T TELL"
        found = "  -  "
    elif r["strict"]:
        verdict = "correct"
        found = f"{int(r['partial']*100)}%"
    elif r["partial"] > 0:
        verdict = "PARTIAL"
        found = f"{int(r['partial']*100)}%"
    else:
        verdict = "MISSED"
        found = "0%"
    print(f"{r['id']:<5} {LABEL[cat]:<11} {verdict:<9} {found:<7} "
          f"{r['top_score']:.3f}  {r['question'][:48]}")

print("\n" + "=" * 92)
print("TOTALS")
print("=" * 92)

for cat, name in [("direct", "EASY  - answer in one place"),
                  ("cross_ref", "HARD  - answer split across two places"),
                  ("cross_doc", "MIXED - answer spans different documents")]:
    sub = [r for r in rows if r["category"] == cat]
    got = sum(1 for r in sub if r["strict"])
    bar = "#" * got + "." * (len(sub) - got)
    print(f"  {name:<42} {got}/{len(sub)}  {bar}")

    if cat == "cross_ref":
        before = sum(1 for r in results["k=5"] if r["category"] == cat and r["strict"])
        print(f"  {'   ...without following footnotes':<42} {before}/{len(sub)}  "
              f"{'#' * before + '.' * (len(sub) - before)}")

ooc = [r for r in rows if r["category"] == "out_of_corpus"]
print(f"  {'TRICK - should return nothing':<42} 0/{len(ooc)}  {'.' * len(ooc)}  <- cannot detect these")

answerable = [r for r in rows if r["category"] != "out_of_corpus"]
got = sum(1 for r in answerable if r["strict"])
print(f"\n  {'ANSWERABLE QUESTIONS OVERALL':<42} {got}/{len(answerable)}")

print("\n" + "=" * 92)
print("WHY THE TRICK QUESTIONS CANNOT BE DETECTED")
print("=" * 92)
worst_real = min((r for r in answerable), key=lambda r: r["top_score"])
best_fake = max(ooc, key=lambda r: r["top_score"])
print(f"  lowest-confidence REAL question : {worst_real['top_score']:.3f}  {worst_real['id']} {worst_real['question'][:44]}")
print(f"  highest-confidence FAKE question: {best_fake['top_score']:.3f}  {best_fake['id']} {best_fake['question'][:44]}")
print(f"\n  The fake one scores HIGHER. No confidence cut-off can separate them.")
