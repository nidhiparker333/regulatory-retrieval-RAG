"""
Score every retrieval arm against the question set. No model, no cost.

The point is to find out which candidate fixes actually help before any of
them is adopted. The earlier project queued three retrieval improvements for
a defect that measurement later showed was costing nothing; the improvements
would have been credited with a gain that was never there.

Two metrics, because they answer different questions:

  strict   every required section (and source) retrieved - what a complete
           answer needs
  partial  the fraction retrieved - shows near-misses that strict hides, e.g.
           finding Annex III but not Article 6

Run:  .venv\\Scripts\\python.exe scripts\\compare_arms.py
"""

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from retrieval import Retrieval  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"

CATS = ["direct", "cross_ref", "cross_doc", "other_source"]

ARMS = [
    ("search only",        dict(expand=False, diverse=False)),
    ("+ expansion",        dict(expand=True,  diverse=False)),
    ("+ diversity",        dict(expand=False, diverse=True)),
    ("+ both (shipped)",   dict(expand=True,  diverse=True)),
]


def score(q: dict, hits: list) -> tuple[bool, float]:
    got_sections = {c["section_id"] for c in hits}
    got_sources = {c["source_group"] for c in hits}
    need_sections = q.get("expect_sections") or []
    need_sources = q.get("expect_sources") or []
    found = sum(1 for s in need_sections if s in got_sections)
    found += sum(1 for s in need_sources if s in got_sources)
    total = len(need_sections) + len(need_sources)
    if total == 0:
        return True, 1.0
    return found == total, found / total


def main() -> int:
    questions = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]
    answerable = [q for q in questions if q["category"] != "out_of_corpus"]
    ooc = [q for q in questions if q["category"] == "out_of_corpus"]
    R = Retrieval()

    results = {}
    for name, cfg in ARMS:
        rows = []
        for q in questions:
            hits = R.search(q["question"], k=5, **cfg)
            strict, partial = score(q, hits)
            rows.append({"id": q["id"], "category": q["category"],
                         "strict": strict, "partial": partial,
                         "n": len(hits)})
        results[name] = rows

    print("=" * 84)
    print("RETRIEVAL ARMS  -  strict score (every required section and source found)")
    print("=" * 84)
    header = f"{'arm':<18}" + "".join(f"{c:>14}" for c in CATS) + f"{'ALL':>10}{'passages':>10}"
    print(header)
    print("-" * 84)
    baseline = None
    for name, rows in results.items():
        line = f"{name:<18}"
        for c in CATS:
            sub = [r for r in rows if r["category"] == c]
            passed = sum(1 for r in sub if r["strict"])
            line += f"{f'{passed}/{len(sub)}':>14}"
        ans = [r for r in rows if r["category"] != "out_of_corpus"]
        total = sum(1 for r in ans if r["strict"])
        if baseline is None:
            baseline = total
        delta = total - baseline
        mark = f"  ({delta:+d})" if delta else ""
        mean_n = np.mean([r["n"] for r in rows])
        print(line + f"{f'{total}/{len(ans)}':>10}{mean_n:>10.1f}" + mark)

    print("\n" + "=" * 84)
    print("PARTIAL CREDIT  (mean fraction of requirements met)")
    print("=" * 84)
    print(f"{'arm':<18}" + "".join(f"{c:>14}" for c in CATS))
    print("-" * 84)
    for name, rows in results.items():
        line = f"{name:<18}"
        for c in CATS:
            sub = [r for r in rows if r["category"] == c]
            line += f"{np.mean([r['partial'] for r in sub]):>14.2f}"
        print(line)

    print("\n" + "=" * 84)
    print("THE FOUR KNOWN FAILURES  -  does any arm recover them?")
    print("=" * 84)
    watch = ["D04", "C01", "C05", "X08"]
    print(f"{'arm':<18}" + "".join(f"{w:>10}" for w in watch))
    print("-" * 84)
    for name, rows in results.items():
        by = {r["id"]: r for r in rows}
        line = f"{name:<18}"
        for w in watch:
            r = by.get(w)
            cell = f"{r['partial']:.2f}" if r else "-"
            line += f"{cell:>10}"
        print(line)

    (EVAL / "arm_comparison.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {EVAL / 'arm_comparison.json'}")
    print("Cost: $0.00")
    return 0


if __name__ == "__main__":
    sys.exit(main())
