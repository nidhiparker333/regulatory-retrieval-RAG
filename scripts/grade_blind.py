"""
Grade answers with a model that has never seen the system.

WHY

Every correctness verdict in this repository was made by one reader, in one
pass, and that reader built the pipeline. It is stated as a weakness in the
README and in FINDINGS, and stating a weakness is not the same as fixing it.

This fixes it as far as it can be fixed without a second human.

WHAT THE GRADER IS AND IS NOT SHOWN

  Shown:     the question, the answer, and the source text the question was
             written from - the ground truth.

  Not shown: the pipeline, the retrieval design, which passages were actually
             retrieved, whether retrieval scored a hit, the tuning set, any
             previous verdict, or the fact that I built any of it.

  Model:     Opus 5. The answers were written by Sonnet 5. A model does not
             grade its own work here.

The grader cannot know whether retrieval succeeded, so it cannot be lenient
towards a near miss or harsh towards one. It reads the answer against the
source and says whether the answer is right.

WHY THIS MATTERS FOR THE HELD-OUT SET

Held-out keys are mechanical: the key is the section the question was
generated from. That is exactly right for measuring retrieval and too strict
for measuring answers, because a question written from one section is often
answered just as well by a neighbouring one. Retrieval scored 26/45 against
that strict key. How many of the other 19 produced a good answer anyway is a
question about answers, not about sections, and this is what settles it.

  .venv\\Scripts\\python.exe scripts\\grade_blind.py holdout
  .venv\\Scripts\\python.exe scripts\\grade_blind.py tuning
"""

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
EVAL = ROOT / "data" / "eval"

MODEL = "claude-opus-5"
PRICE_IN, PRICE_OUT = 5.00, 25.00

SYSTEM = """You are grading answers about AI governance documents. You did not write the answer and you know nothing about the system that produced it.

You are given a QUESTION, an ANSWER, and the SOURCE TEXT that the question was written from.

Judge the ANSWER against the SOURCE TEXT. Choose exactly one verdict:

- "correct"  - the answer addresses the question and nothing in it contradicts the source. Bracketed numbers like [2] are citation markers; ignore their formatting and judge the substance.
- "partial"  - the answer is accurate as far as it goes but leaves a substantive part of the question unaddressed. If the answer itself says which part it cannot cover, that counts in its favour, not against it: an answer that declines what it cannot support is behaving correctly.
- "wrong"    - the answer asserts something the source contradicts, or confidently answers about different subject matter than the question asked.
- "refused"  - the answer declines to answer, typically opening with "NOT IN THE SOURCES".

Two rules that matter:

1. The answer does NOT have to come from the source text shown. If it answers the question correctly from other material, that is "correct". The source text is the ground truth for what a right answer looks like, not a requirement about where it came from.

2. Do not reward or punish an answer for being cited, well written, hedged or confident. Judge only whether what it says is true of the subject matter and responsive to the question.

Return ONLY a JSON object:
{"verdict": "correct|partial|wrong|refused", "why": "<one sentence, max 25 words>"}"""


def section_text(section_ids: list) -> str:
    chunks = json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8"))
    want = set(section_ids)
    parts = [c["text"] for c in chunks if c["section_id"] in want]
    return "\n\n".join(parts)[:14000]


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "holdout"
    sys.path.insert(0, str(ROOT / "scripts"))
    from answer import load_env
    load_env()
    import anthropic
    client = anthropic.Anthropic()

    if which == "holdout":
        rows = json.loads((EVAL / "holdout_results.json").read_text(encoding="utf-8"))["questions"]
        items = [{"id": r["id"], "question": r["question"], "answer": r.get("answer", ""),
                  "sections": [r["expect"]], "retrieval_found": r["found"]}
                 for r in rows if r.get("answer") is not None]
        out = EVAL / "holdout_graded.json"
    else:
        res = json.loads((EVAL / "full_eval_results.json").read_text(encoding="utf-8"))["results"]
        qs = {q["id"]: q for q in
              json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]}
        items = []
        for r in res:
            q = qs[r["id"]]
            if q["category"] == "out_of_corpus":
                continue          # nothing to grade against; refusal is the key
            items.append({"id": r["id"], "question": r["question"],
                          "answer": r.get("answer", ""),
                          "sections": q.get("expect_sections") or [],
                          "retrieval_found": None})
        out = EVAL / "tuning_graded.json"

    graded, cost = [], 0.0
    for i, it in enumerate(items, 1):
        src = section_text(it["sections"])
        if not src:
            continue
        resp = client.messages.create(
            model=MODEL, max_tokens=1500, thinking={"type": "adaptive"},
            system=SYSTEM,
            messages=[{"role": "user", "content":
                       f"QUESTION:\n{it['question']}\n\n"
                       f"ANSWER:\n{it['answer']}\n\n"
                       f"SOURCE TEXT:\n{src}"}])
        cost += (resp.usage.input_tokens * PRICE_IN
                 + resp.usage.output_tokens * PRICE_OUT) / 1_000_000
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            got = json.loads(text)
        except json.JSONDecodeError:
            got = {"verdict": "unparseable", "why": text[:80]}
        graded.append({**it, **got})
        print(f"  {i:>2}/{len(items)}  {it['id']}  {got['verdict']:<9} {got.get('why','')[:56]}")

    counts = collections.Counter(g["verdict"] for g in graded)
    print("\n" + "=" * 68)
    print(f"BLIND GRADE - {which}, graded by {MODEL}")
    print("=" * 68)
    n = len(graded)
    for v in ("correct", "partial", "wrong", "refused", "unparseable"):
        if counts.get(v):
            print(f"  {v:<12} {counts[v]:>3} / {n}")

    if which == "holdout":
        # The question the strict key could not answer.
        hit = [g for g in graded if g["retrieval_found"]]
        miss = [g for g in graded if not g["retrieval_found"]]
        print(f"\n  Where retrieval hit the exact section ({len(hit)}):")
        print(f"    {sum(1 for g in hit if g['verdict']=='correct')} correct, "
              f"{sum(1 for g in hit if g['verdict']=='partial')} partial, "
              f"{sum(1 for g in hit if g['verdict']=='wrong')} wrong, "
              f"{sum(1 for g in hit if g['verdict']=='refused')} refused")
        print(f"\n  Where it did NOT ({len(miss)}):")
        print(f"    {sum(1 for g in miss if g['verdict']=='correct')} correct, "
              f"{sum(1 for g in miss if g['verdict']=='partial')} partial, "
              f"{sum(1 for g in miss if g['verdict']=='wrong')} wrong, "
              f"{sum(1 for g in miss if g['verdict']=='refused')} refused")
        print("\n  A 'wrong' in the second group is the failure that matters:")
        print("  retrieval missed and the system answered anyway.")
        for g in miss:
            if g["verdict"] == "wrong":
                print(f"    {g['id']}: {g['why'][:70]}")

    (out).write_text(json.dumps(
        {"_about": {"grader": MODEL, "answerer": "claude-sonnet-5",
                    "blind_to": ["the pipeline", "what was retrieved",
                                 "whether retrieval hit", "any previous verdict"],
                    "cost_usd": round(cost, 4)},
         "graded": graded}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ${cost:.4f}   wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
