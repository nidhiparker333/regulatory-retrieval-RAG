"""
Check every figure in README.md and FINDINGS.md against the pipeline.

Documentation drift is not a cosmetic problem. The predecessor to this project
reported 925 chunks and a 1.3 MB index long after both had changed, claimed in
one paragraph that no accuracy had been measured and printed accuracy figures in
the next, and described a 25-question set that had grown to 26. None of it was
dishonest; the numbers were simply typed once and never re-derived.

So the numbers are asserted here, in code, against the artefacts they describe.
A figure that changes without the prose changing fails the build.

Run:  .venv\\Scripts\\python.exe scripts\\check_docs.py
"""

import collections
import json
import pathlib
import re
import statistics as st
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
EVAL = ROOT / "data" / "eval"

failures: list[str] = []


def load():
    return (
        json.loads((CLEAN / "corpus.json").read_text(encoding="utf-8")),
        json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8")),
        json.loads((EVAL / "full_eval_results.json").read_text(encoding="utf-8"))["results"],
        json.loads((EVAL / "correctness.json").read_text(encoding="utf-8")),
        json.loads((EVAL / "arm_comparison.json").read_text(encoding="utf-8")),
        json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"],
    )


def check(doc: str, text: str, needle: str, label: str) -> None:
    """Assert a rendered figure appears in the document."""
    ok = needle in text
    print(f"  [{'ok ' if ok else 'FAIL'}]  {doc:<12} {label}")
    if not ok:
        print(f"           expected to find: {needle!r}")
        failures.append(f"{doc}: {label}")


def main() -> int:
    corpus, chunks, results, corr, arms, questions = load()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    findings = (ROOT / "FINDINGS.md").read_text(encoding="utf-8")
    both = readme + findings

    answerable = [r for r in results if r["category"] != "out_of_corpus"]
    ooc = [r for r in results if r["category"] == "out_of_corpus"]
    graded = [r for r in answerable if r["grounded"] is not None]

    n_sections = len(corpus)
    n_chunks = len(chunks)
    n_chars = sum(s["chars"] for s in corpus)
    index_mb = round((CLEAN / "index.npz").stat().st_size / 1e6, 1)
    cost = st.mean([r["cost_usd"] for r in results])
    answered = sum(1 for r in answerable if r["behaved"])
    grounded = sum(1 for r in graded if r["grounded"])
    refused = sum(1 for r in ooc if r["behaved"])
    uncited = sum(1 for r in answerable if r["n_citations"] == 0 and not r["refused"])
    xref = [r for r in corpus if r.get("refs_annex") or r.get("refs_article")]

    def arm_strict(name: str) -> str:
        rows = [r for r in arms[name] if r["category"] != "out_of_corpus"]
        return f"{sum(1 for r in rows if r['strict'])}/{len(rows)}"

    print("=" * 70)
    print("CORPUS")
    print("=" * 70)
    check("both", both, f"{n_sections} sections", "section count")
    check("both", both, f"{n_chunks} chunks", "chunk count")
    check("README", readme, f"{n_chars:,} characters", "character count")
    check("both", both, f"{index_mb} MB", "index size")
    check("README", readme, f"{len(xref)} of {n_sections} sections cite", "cross-referencing sections")

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    s = corr["summary"]
    check("both", both, f"{s['correct']} / {s['answerable']}", "correct count")
    check("both", both, f"{refused} / {len(ooc)}", "refusal count")
    check("both", both, f"of {s['quotes_checked']}", "quotes checked")
    check("README", readme, f"{answered}/{len(answerable)}", "answered count")
    check("both", both, f"${cost:.4f}", "cost per question")
    check("both", both, f"{arm_strict('+ both (shipped)')}", "final retrieval score")
    check("FINDINGS", findings, f"{arm_strict('search only')}", "search-only arm")

    # ---------------------------------------------------------- held-out set
    #
    # These are the figures a reviewer will press hardest on, because they are
    # the only ones the system was not tuned against. If the prose and the
    # result files ever drift apart here, the drift is worse than anywhere
    # else in the repository: it would be overstating the one number that was
    # produced honestly.
    hold_res = EVAL / "holdout_results.json"
    hold_grade = EVAL / "holdout_graded.json"
    if hold_res.exists() and hold_grade.exists():
        hr = json.loads(hold_res.read_text(encoding="utf-8"))
        hg = json.loads(hold_grade.read_text(encoding="utf-8"))["graded"]
        n_hold = hr["retrieval"]["total"]
        found = hr["retrieval"]["found"]
        ss_hit, ss_n = hr["retrieval"]["same_shape_in_sample"]
        v = collections.Counter(g["verdict"] for g in hg)

        print(f"\n  held-out set ({n_hold} questions)")
        check("both", both, f"{found}/{n_hold}", "held-out retrieval")
        check("both", both, f"{ss_hit}/{ss_n}", "same-shape in-sample retrieval")
        check("both", both, f"| **{v['correct']}** |", "held-out correct")
        check("README", readme, f"| {v['partial']} |", "held-out partial")

        # The k curve is the claim that changed a shipped decision's reasoning.
        k5 = next(r["holdout"] for r in hr["k_sweep"] if r["k"] == 5)
        k20 = next(r["holdout"] for r in hr["k_sweep"] if r["k"] == 20)
        check("both", both, f"{k5}/{n_hold} to {k20}/{n_hold}", "held-out k curve")

        # Split table: the point of the whole exercise.
        miss = [g for g in hg if not g["retrieval_found"]]
        hit_g = [g for g in hg if g["retrieval_found"]]
        mw = sum(1 for g in miss if g["verdict"] == "wrong")
        hw = sum(1 for g in hit_g if g["verdict"] == "wrong")
        ok = (mw + hw) == v["wrong"]
        print(f"  [{'ok ' if ok else 'FAIL'}]  wrong answers reconcile across the split table")
        if not ok:
            failures.append("held-out split table")

        # A refusal count that disagrees with the grader is the defect this
        # set found once already. It must not silently come back.
        blind_ref = v["refused"]
        strict_ref = sum(1 for q in hr["questions"] if q.get("answered") is False)
        if blind_ref != strict_ref:
            phrase = f"{blind_ref} refusals where `answer.py` counted {strict_ref}"
            check("FINDINGS", findings, phrase, "refusal detection gap disclosed")
    else:
        print("\n  [FAIL]  held-out results missing; README cites them")
        failures.append("held-out results absent")

    print("\n" + "=" * 70)
    print("CLAIMS THAT MUST STAY TRUE")
    print("=" * 70)
    ok = uncited == 0 and "Answers citing nothing | **0**" in both
    print(f"  [{'ok ' if ok else 'FAIL'}]  zero uncited answers, and both docs say so")
    if not ok:
        failures.append("uncited claim")
    ok = s["quotes_fabricated"] == 0
    print(f"  [{'ok ' if ok else 'FAIL'}]  zero fabricated quotes recorded")
    if not ok:
        failures.append("fabricated quotes")
    ok = len(questions) == 30
    print(f"  [{'ok ' if ok else 'FAIL'}]  question set is 30")
    if not ok:
        failures.append("question count")
    # The one claim most likely to rot: a doc saying nothing was measured.
    for phrase in ("no accuracy figures", "does not exist yet", "quality has not been measured"):
        if phrase in both.lower():
            print(f"  [FAIL]  stale disclaimer present: {phrase!r}")
            failures.append(f"stale disclaimer: {phrase}")

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    if failures:
        print(f"  {len(failures)} figure(s) in the docs no longer match the pipeline:")
        for f in failures:
            print(f"    - {f}")
        print("\n  Re-run the pipeline, or update the prose. Do not do neither.")
        return 1
    print("  Every figure in README.md and FINDINGS.md matches the pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
