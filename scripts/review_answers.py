"""
Print each answer beside the passages it cites, for a human correctness read.

Grounding is checkable by code: did the answer cite a section the key
requires? Correctness is not. Whether a claim is true, whether the passage
cited actually supports it, and whether the answer misreads what it quotes are
judgements that need someone to read both and decide.

This script only lays the evidence out. The verdicts live in
data/eval/correctness.json and are written by hand.

Run:  .venv\\Scripts\\python.exe scripts\\review_answers.py [ID ...]
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"


def main() -> int:
    results = json.loads((EVAL / "full_eval_results.json").read_text(encoding="utf-8"))["results"]
    questions = {q["id"]: q for q in
                 json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]}

    wanted = [a.upper() for a in sys.argv[1:]]
    rows = [r for r in results if not wanted or r["id"] in wanted]

    for r in rows:
        q = questions[r["id"]]
        print("=" * 78)
        print(f"{r['id']}  [{r['category']}]   refused={r['refused']}  grounded={r['grounded']}")
        print(f"Q: {r['question']}")
        print(f"KEY: sections={q.get('expect_sections')} sources={q.get('expect_sources')}")
        if q.get("notes"):
            print(f"NOTE: {q['notes']}")
        print("-" * 78)
        print(r["answer"] or "(empty)")
        print("-" * 78)
        print(f"CITED SECTIONS: {r['cited_sections']}")
        print()

    print(f"\n{len(rows)} question(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
