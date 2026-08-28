"""
Run all 25 questions end to end and score the answers, not just the retrieval.

Retrieval scoring asked "did the right pages come back". This asks the harder
question: given those pages, did it produce a defensible answer, and did it
refuse when it should have?

Three things are checked per question:

  behaved   - answered when it could, refused when it could not
  grounded  - cited at least one of the sections the answer key requires
  cited     - cited anything at all (an uncited claim is unverifiable)

Cost: roughly $0.013 per question, so about $0.33 for the set.

The work is behind `main()` and a `__main__` guard because of that cost. This
module used to run the whole paid evaluation as a side effect of being
imported - `import run_full_eval` from a REPL, a test, or a tool inspecting the
package would start spending money with nothing on screen to say so.

Run:  .venv\\Scripts\\python.exe scripts\\run_full_eval.py
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from answer import answer  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"

def main() -> None:
    questions = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]

    results = []
    total_cost = 0.0

    print(f"Running {len(questions)} questions end to end...\n")

    for i, q in enumerate(questions, 1):
        t0 = time.time()
        try:
            r = answer(q["question"], k=5, follow=True)
        except Exception as e:
            print(f"  {q['id']}  ERROR: {e}")
            results.append({**q, "error": str(e)})
            continue

        total_cost += r["cost_usd"]
        unanswerable = q["category"] == "out_of_corpus"
        expected = set(q.get("expect_sections", []))

        # Which sections did it actually cite? Map citation numbers back to
        # passages, then to section ids.
        cited_citations = {c["citation"] for c in r["citations_used"]}
        cited_sections = set()
        for p in r["passages"]:
            if p["citation"] in cited_citations:
                base = p["citation"].split(" (part")[0]
                cited_sections.add(base)

        expected_labels = set()
        for sid in expected:
            if sid.startswith("art_"):
                expected_labels.add(f"Article {sid[4:]}")
            elif sid.startswith("anx_"):
                expected_labels.add(f"Annex {sid[4:]}")

        # Some answers do not live in a numbered article. NIST has no single
        # canonical section for "risk management", and OWASP's entries are the
        # unit there - so those questions state the source they must come from
        # instead, and score_retrieval.py has always honoured that field.
        #
        # This scorer did not. It looked at expect_sections alone, so C02, C03
        # and C04 - the three questions answered entirely from OWASP and NIST -
        # produced grounded=None and were dropped from the totals. That is why
        # the report read "17/19" beside 22 answerable questions: three
        # questions disappearing between two lines of the same summary, and
        # precisely the three testing whether the system can answer from
        # anything other than the Act.
        #
        # C01 was worse than dropped. Its note says it must show both the Act
        # and NIST, and it declares both sources - but checking art_9 alone
        # meant an answer citing Article 9 and no NIST at all scored grounded,
        # which is the exact failure the note was written to catch.
        expected_sources = set(q.get("expect_sources") or [])
        cited_sources = {p["source"] for p in r["passages"]
                         if p["citation"] in cited_citations}

        if expected_labels or expected_sources:
            # Every stated requirement must be met: the sections asked for, and
            # the sources asked for. Sections still count on any overlap, which
            # is what `grounded` has always meant.
            sections_ok = bool(expected_labels & cited_sections) if expected_labels else True
            sources_ok = expected_sources.issubset(cited_sources) if expected_sources else True
            grounded = sections_ok and sources_ok
        else:
            grounded = None

        behaved = r["refused"] if unanswerable else not r["refused"]

        # Split retrieval from generation. They have completely different
        # latency profiles - one is milliseconds and free, the other is seconds
        # and costs money - so a single end-to-end number hides which is which.
        gen_step = next((s for s in r["trace"] if s["step"] == "generate"), {})
        search_step = next((s for s in r["trace"] if s["step"] == "search"), {})

        results.append({
            "id": q["id"],
            "category": q["category"],
            "question": q["question"],
            "elapsed_ms": round((time.time() - t0) * 1000),
            "search_ms": search_step.get("ms"),
            "generate_ms": gen_step.get("ms"),
            "tokens_in": gen_step.get("tokens_in"),
            "tokens_out": gen_step.get("tokens_out"),
            "refused": r["refused"],
            "behaved": behaved,
            "grounded": grounded,
            "n_citations": len(r["citations_used"]),
            "cited_sections": sorted(cited_sections),
            "expected_sections": sorted(expected_labels),
            "answer": r["answer"],
            "cost_usd": r["cost_usd"],
        })

        mark = "ok " if behaved else "XX "
        g = "" if grounded is None else (" grounded" if grounded else " NOT-GROUNDED")
        print(f"  {i:>2}/{len(questions)}  {q['id']}  {mark}{g:<14} "
              f"{len(r['citations_used'])} citations  {time.time()-t0:.1f}s")

    (EVAL / "full_eval_results.json").write_text(
        json.dumps({"results": results, "total_cost_usd": round(total_cost, 4)},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # --- summary ---------------------------------------------------------------
    answerable = [r for r in results if r["category"] != "out_of_corpus"]
    ooc = [r for r in results if r["category"] == "out_of_corpus"]

    print("\n" + "=" * 70)
    print("END-TO-END RESULTS")
    print("=" * 70)
    print(f"  answered when it could      : {sum(1 for r in answerable if r['behaved'])}/{len(answerable)}")
    print(f"  refused when it should      : {sum(1 for r in ooc if r['behaved'])}/{len(ooc)}")
    print(f"  cited a required section    : {sum(1 for r in answerable if r['grounded'])}/{len(answerable)}")
    uncited = [r for r in answerable if r["n_citations"] == 0]
    print(f"  answers with no citation    : {len(uncited)}")
    print(f"\n  total cost                  : ${total_cost:.4f}")
    print(f"  per question                : ${total_cost/len(results):.4f}")
    print(f"\nWrote {EVAL / 'full_eval_results.json'}")



if __name__ == "__main__":
    main()
