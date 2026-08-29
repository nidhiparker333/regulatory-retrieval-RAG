"""
Run the full evaluation N times and report the spread.

Generation is stochastic. A single run gives a single sample, which means a
one-question difference between two configurations cannot be told apart from
noise - and every end-to-end figure in this repository came from one run.

This is the check that answers "how do you know that number is real". It says
which questions are stable, which flip between runs, and what the actual range
on each headline figure is.

Cost: the full set per repeat, about $0.65 a pass at time of writing.

Run:  .venv\\Scripts\\python.exe scripts\\run_variance.py [repeats]
"""

import collections
import json
import pathlib
import statistics as st
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"
PY = ROOT / ".venv" / "Scripts" / "python.exe"


def main() -> int:
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    live = EVAL / "full_eval_results.json"
    keep = live.read_bytes() if live.exists() else None
    runs = []

    print(f"Running the full evaluation {repeats} times.\n")
    try:
        for i in range(1, repeats + 1):
            print(f"--- run {i}/{repeats} " + "-" * 40)
            r = subprocess.run([str(PY), str(ROOT / "scripts" / "run_full_eval.py")],
                               cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                print(r.stdout[-2000:], r.stderr[-2000:])
                return 1
            data = json.loads(live.read_text(encoding="utf-8"))["results"]
            runs.append(data)
            (EVAL / f"variance_run_{i}.json").write_text(
                json.dumps({"results": data}, indent=2, ensure_ascii=False),
                encoding="utf-8")
            ans = [x for x in data if x["category"] != "out_of_corpus"]
            ooc = [x for x in data if x["category"] == "out_of_corpus"]
            gr = [x for x in ans if x["grounded"] is not None]
            print(f"    answered {sum(1 for x in ans if x['behaved'])}/{len(ans)}"
                  f"   grounded {sum(1 for x in gr if x['grounded'])}/{len(gr)}"
                  f"   refused {sum(1 for x in ooc if x['behaved'])}/{len(ooc)}"
                  f"   ${sum(x['cost_usd'] for x in data):.4f}\n")
    finally:
        # The single-run file is what metrics.py and check_docs.py read; a
        # variance sweep must not silently redefine the reported run.
        if keep is not None:
            live.write_bytes(keep)
            print("restored data/eval/full_eval_results.json (the reported run)\n")

    print("=" * 70)
    print("SPREAD ACROSS RUNS")
    print("=" * 70)

    def series(fn):
        return [fn(r) for r in runs]

    def answered(r):
        a = [x for x in r if x["category"] != "out_of_corpus"]
        return sum(1 for x in a if x["behaved"])

    def grounded(r):
        g = [x for x in r if x["category"] != "out_of_corpus" and x["grounded"] is not None]
        return sum(1 for x in g if x["grounded"])

    def refused(r):
        o = [x for x in r if x["category"] == "out_of_corpus"]
        return sum(1 for x in o if x["behaved"])

    def uncited(r):
        a = [x for x in r if x["category"] != "out_of_corpus"]
        return sum(1 for x in a if x["n_citations"] == 0 and not x["refused"])

    for name, fn, denom in [("answered", answered, 26), ("grounded", grounded, 26),
                            ("refused", refused, 4), ("uncited", uncited, None)]:
        v = series(fn)
        rng = f"{min(v)}–{max(v)}" if min(v) != max(v) else f"{v[0]}"
        stable = "stable" if min(v) == max(v) else "VARIES"
        d = f"/{denom}" if denom else ""
        print(f"  {name:<10} {rng}{d:<4}  runs {v}   {stable}")

    costs = [sum(x["cost_usd"] for x in r) for r in runs]
    print(f"  {'cost':<10} ${min(costs):.4f}–${max(costs):.4f}   mean ${st.mean(costs):.4f}")

    print("\n" + "=" * 70)
    print("PER-QUESTION STABILITY")
    print("=" * 70)
    flips = []
    for qid in [x["id"] for x in runs[0]]:
        verdicts = []
        for r in runs:
            row = next(x for x in r if x["id"] == qid)
            verdicts.append((row["behaved"], row["grounded"]))
        if len(set(verdicts)) > 1:
            flips.append((qid, verdicts))
    if flips:
        print(f"  {len(flips)} question(s) gave different verdicts between runs:")
        for qid, v in flips:
            print(f"    {qid}: {v}")
    else:
        print(f"  Every question gave the same verdict in all {repeats} runs.")
        print("  The headline figures are not a lucky sample.")

    cites = collections.defaultdict(list)
    for r in runs:
        for x in r:
            cites[x["id"]].append(x["n_citations"])
    spread = [(q, min(c), max(c)) for q, c in cites.items() if max(c) - min(c) >= 3]
    if spread:
        print(f"\n  Citation counts still move run to run (wording varies even when")
        print(f"  the verdict does not):")
        for q, lo, hi in sorted(spread, key=lambda x: x[1] - x[2])[:5]:
            print(f"    {q}: {lo}–{hi} citations")

    print(f"\nWrote {repeats} run files to data/eval/variance_run_*.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
