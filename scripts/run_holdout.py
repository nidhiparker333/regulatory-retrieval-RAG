"""
Run the held-out set. Once.

This is the check that answers "you tuned on your own test set".

Three things are measured, and the second is the one that matters:

  1. RETRIEVAL, out of sample. How often the shipped configuration finds the
     section a question was written from, on questions it never saw.

  2. WHETHER THE TUNING DECISIONS HOLD. k=5 and both retrieval arms were
     chosen by scoring against the 30-question set. Re-running those same
     sweeps here says whether those choices generalise or were fitted to the
     set that picked them. This is free - retrieval costs nothing - and it
     is the part a reviewer should care about, because a decision that only
     looks good on the set that produced it is the definition of overfitting.

  3. GENERATION. Whether the answers cite the section the question came from,
     and whether any answer arrives uncited.

A NOTE ON COMPARABILITY

The two sets are not scored identically and pretending otherwise would be
worse than saying so.

A held-out key is one section, required exactly. A tuning key can name
several sections and sources, all required. So the held-out bar is narrower
per question but unforgiving on that one section, and the aggregate numbers
are not directly comparable.

The script therefore also reports the tuning questions that have exactly one
section key and no source key, which IS the same shape of task, as the
honest side-by-side.

Run once. Tuning against this set would destroy the only property it has.

  .venv\\Scripts\\python.exe scripts\\run_holdout.py            retrieval only, free
  .venv\\Scripts\\python.exe scripts\\run_holdout.py --generate  adds answers, ~$1
"""

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"
OUT = EVAL / "holdout_results.json"


def main() -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    from retrieval import Retrieval

    R = Retrieval()
    hold = json.loads((EVAL / "holdout.json").read_text(encoding="utf-8"))["questions"]
    tune = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]

    def hit(q, k=5, expand=True, diverse=True) -> bool:
        got = {c["section_id"] for c in R.search(q["question"], k=k,
                                                 expand=expand, diverse=diverse)}
        return set(q["expect_sections"]).issubset(got)

    # ---------------------------------------------------------------- 1
    print("=" * 72)
    print("HELD-OUT RETRIEVAL, shipped configuration")
    print("=" * 72)
    results = [{"id": q["id"], "question": q["question"],
                "source": q["source_group"], "expect": q["expect_sections"][0],
                "found": hit(q)} for q in hold]
    n_hit = sum(r["found"] for r in results)
    print(f"\n  {n_hit}/{len(hold)} found the section the question was written from\n")
    per_src = collections.defaultdict(lambda: [0, 0])
    for r in results:
        per_src[r["source"]][1] += 1
        per_src[r["source"]][0] += r["found"]
    for src, (h, n) in sorted(per_src.items()):
        print(f"    {src:<14} {h}/{n}")

    missed = [r for r in results if not r["found"]]
    if missed:
        print(f"\n  missed:")
        for r in missed:
            print(f"    {r['id']}  {r['expect']:<20} {r['question'][:52]}")

    # ------------------------------------------------- the honest comparison
    same_shape = [q for q in tune
                  if len(q.get("expect_sections") or []) == 1
                  and not q.get("expect_sources")
                  and q["category"] != "out_of_corpus"]
    ss_hit = sum(hit(q) for q in same_shape)
    print(f"\n  Same-shape tuning questions (one section key, no source key):")
    print(f"    in sample      {ss_hit}/{len(same_shape)}")
    print(f"    out of sample  {n_hit}/{len(hold)}")

    # ---------------------------------------------------------------- 2
    print("\n" + "=" * 72)
    print("DO THE TUNING DECISIONS HOLD OUT OF SAMPLE?")
    print("=" * 72)

    print("\n  k, chosen as 5 on the tuning set:\n")
    print(f"    {'k':>4}{'held-out':>12}{'tuning set':>14}")
    k_rows = []
    for k in (3, 5, 8, 10, 15, 20):
        h = sum(hit(q, k=k) for q in hold)
        t = sum(hit(q, k=k) for q in same_shape)
        k_rows.append({"k": k, "holdout": h, "tuning": t})
        mark = "   <- shipped" if k == 5 else ""
        print(f"    {k:>4}{f'{h}/{len(hold)}':>12}{f'{t}/{len(same_shape)}':>14}{mark}")

    print("\n  Retrieval arms, both adopted on the tuning set:\n")
    arms = [("search alone", False, False),
            ("+ cross-references", True, False),
            ("+ source diversity", False, True),
            ("+ both (shipped)", True, True)]
    arm_rows = []
    print(f"    {'':<22}{'held-out':>12}{'tuning set':>14}")
    for label, ex, dv in arms:
        h = sum(hit(q, expand=ex, diverse=dv) for q in hold)
        t = sum(hit(q, expand=ex, diverse=dv) for q in same_shape)
        arm_rows.append({"arm": label, "holdout": h, "tuning": t})
        print(f"    {label:<22}{f'{h}/{len(hold)}':>12}{f'{t}/{len(same_shape)}':>14}")

    payload = {
        "_about": {
            "set": "data/eval/holdout.json - never used for any tuning decision",
            "note": ("Held-out keys are one section required exactly; tuning keys "
                     "can require several sections and sources. The same-shape "
                     "subset is the comparable figure."),
        },
        "retrieval": {"found": n_hit, "total": len(hold),
                      "per_source": {k: v for k, v in per_src.items()},
                      "same_shape_in_sample": [ss_hit, len(same_shape)]},
        "k_sweep": k_rows,
        "arms": arm_rows,
        "questions": results,
    }

    # ---------------------------------------------------------------- 3
    if "--generate" in sys.argv:
        from answer import answer
        print("\n" + "=" * 72)
        print("GENERATION on the held-out set")
        print("=" * 72 + "\n")
        # Correctness is NOT decided here. Whether an answer is right is a
        # judgement, and every judgement in this repository so far was made by
        # the person who built the pipeline. grade_blind.py makes this one with
        # a different model that never sees the system. This step only records
        # behaviour that can be counted without an opinion: did it refuse, did
        # it cite anything, what did it cost.
        cost, uncited, refused = 0.0, 0, 0
        for i, q in enumerate(hold, 1):
            a = answer(q["question"])
            cost += a["cost_usd"]
            cited = [c["citation"] for c in a["citations_used"]]
            uncited += a["uncited"]
            refused += a["refused"]
            for r in results:
                if r["id"] == q["id"]:
                    r.update(answered=not a["refused"], n_citations=len(cited),
                             cited=cited, uncited=a["uncited"],
                             cost_usd=a["cost_usd"], answer=a["answer"])
            flag = "REFUSED" if a["refused"] else ("UNCITED" if a["uncited"] else "")
            print(f"  {i:>2}/{len(hold)}  {q['id']}  {len(cited):>2} cites  {flag}")
        print(f"\n  answered {len(hold)-refused}/{len(hold)}"
              f"   uncited {uncited}   ${cost:.4f}")
        print("  correctness is decided by scripts/grade_blind.py, not here")
        payload["generation"] = {"answered": len(hold) - refused,
                                 "refused": refused, "uncited": uncited,
                                 "cost_usd": round(cost, 4)}
        payload["questions"] = results

    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
