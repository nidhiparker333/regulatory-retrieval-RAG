"""
Build a held-out question set the system was never tuned against.

WHY THIS EXISTS

The 30-question set in questions.json has an honest defence and a real
weakness, and they are different things.

The defence holds: the answer keys were written from the sources and
committed before the first run, so they cannot have been fitted to the
output. `git log` on questions.json proves the ordering.

The weakness is not addressed by that at all. k=5, the chunk size, and both
retrieval arms were each chosen by scoring against those same 30 questions.
So every headline retrieval figure in FINDINGS is an in-sample number - the
system was tuned on the set it is reported against. A commit timestamp says
nothing about that.

This script builds a set that is out-of-sample by construction.

HOW INDEPENDENCE IS ACTUALLY OBTAINED

Four properties, each one checkable rather than asserted:

  1. DISJOINT SOURCE MATERIAL. Every section used as a key by the tuning set
     is excluded. No held-out question is drawn from text the tuning
     questions touched.

  2. MECHANICAL KEYS. The key is the section the question was generated
     FROM. It is not a judgement about what a good answer needs - the
     question was written by reading that section, so that section answers
     it by construction. This is the property questions.json cannot claim.

  3. A DIFFERENT MODEL WRITES THE QUESTIONS. Generation is Opus 5; answering
     is Sonnet 5. The question author is not the answerer.

  4. THE GENERATOR IS BLIND. It sees one section of source text. It never
     sees the pipeline, the retrieval design, the tuning set, or any result.
     It cannot write questions that flatter a system it knows nothing about.

  Sampling is seeded and the seed is recorded, so the selection cannot be
  re-rolled until it looks good.

WHAT THIS STILL DOES NOT FIX

The generator is a language model, not a practitioner. These are questions
about text, written from text. A real user's questions would be worse posed,
more oblique, and would carry assumptions the source never addresses. D04 in
the tuning set - the everyday-phrasing failure - is exactly the kind of
question this process will under-produce.

So this measures generalisation to unseen material. It does not measure
generalisation to unseen USERS, and no set generated this way could.

Run:  .venv\\Scripts\\python.exe scripts\\make_holdout.py
"""

import collections
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
EVAL = ROOT / "data" / "eval"
OUT = EVAL / "holdout.json"

MODEL = "claude-opus-5"          # deliberately not the answering model
PER_SOURCE = 15
SEED = 20260829                  # recorded so the sample cannot be re-rolled
MIN_CHARS = 900                  # below this a section cannot support a question

GEN_SYSTEM = """You write evaluation questions for a document retrieval system.

You will be shown ONE passage from a real AI governance document. Write a single question that this passage genuinely answers.

REQUIREMENTS

1. The passage must actually contain the answer. If it does not contain enough to answer anything specific - it is a heading, a table of contents, a cross-reference stub, or pure boilerplate - return unsuitable instead of forcing a question.

2. Write the question the way a practitioner would ask it, in their own words. Do NOT reuse the passage's distinctive phrasing, and do not quote its title. A question built from the passage's own vocabulary tests string matching, not retrieval.

3. Ask about substance: an obligation, a threshold, a deadline, a definition, a procedure, a control, a responsibility. Not "what does this section say".

4. One question. Answerable from this passage alone. No multi-part questions joined by "and".

5. Do not mention passages, sections, articles by number, or the document's structure. The person asking does not know how the document is organised.

Return ONLY a JSON object, no other text:
{"suitable": true, "question": "...", "asks_about": "<the specific thing the passage answers, in a few words>"}
or
{"suitable": false, "reason": "..."}"""


def load_sections() -> dict:
    """Reassemble full section text from the chunks, in corpus order."""
    chunks = json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8"))
    secs = collections.OrderedDict()
    for c in chunks:
        s = secs.setdefault(c["section_id"], {
            "section_id": c["section_id"],
            "source_group": c["source_group"],
            "title": c.get("title", ""),
            "parts": [],
        })
        s["parts"].append(c["text"])
    for s in secs.values():
        s["text"] = "\n\n".join(s["parts"])
        del s["parts"]
    return secs


def main() -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    from answer import load_env
    load_env()
    import anthropic
    client = anthropic.Anthropic()

    secs = load_sections()

    # Property 1: everything the tuning set used as a key is off limits.
    tuning = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]
    used = {s for q in tuning for s in (q.get("expect_sections") or [])}
    tuning_text = {q["question"].lower() for q in tuning}

    pool = [s for s in secs.values()
            if s["section_id"] not in used and len(s["text"]) >= MIN_CHARS]
    print(f"{len(secs)} sections, {len(used)} excluded as tuning keys, "
          f"{len(pool)} eligible\n")

    by_source = collections.defaultdict(list)
    for s in pool:
        by_source[s["source_group"]].append(s)

    rng = random.Random(SEED)
    picked = []
    for src in sorted(by_source):
        group = sorted(by_source[src], key=lambda s: s["section_id"])
        picked += rng.sample(group, min(PER_SOURCE, len(group)))
    rng.shuffle(picked)

    questions, skipped, cost = [], [], 0.0
    for i, s in enumerate(picked, 1):
        body = s["text"][:12000]
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            system=GEN_SYSTEM,
            messages=[{"role": "user", "content": f"PASSAGE:\n\n{body}"}],
        )
        cost += (resp.usage.input_tokens * 5.0
                 + resp.usage.output_tokens * 25.0) / 1_000_000
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            got = json.loads(text)
        except json.JSONDecodeError:
            skipped.append((s["section_id"], "unparseable response"))
            continue

        if not got.get("suitable"):
            skipped.append((s["section_id"], got.get("reason", "unsuitable")[:60]))
            print(f"  {i:>2}. skip  {s['section_id']:<22} {got.get('reason','')[:44]}")
            continue

        q = got["question"].strip()
        if q.lower() in tuning_text:
            skipped.append((s["section_id"], "duplicate of a tuning question"))
            continue

        questions.append({
            "id": f"H{len(questions)+1:02d}",
            "question": q,
            "category": "holdout",
            "source_group": s["source_group"],
            "expect_sections": [s["section_id"]],
            "asks_about": got.get("asks_about", ""),
            "generated_from": s["section_id"],
        })
        print(f"  {i:>2}. {s['section_id']:<22} {q[:64]}")

    payload = {
        "_about": {
            "purpose": "Held-out set. The system was never tuned against these.",
            "generated_by": MODEL,
            "answered_by": "claude-sonnet-5 (deliberately a different model)",
            "seed": SEED,
            "per_source_sampled": PER_SOURCE,
            "excluded": "every section used as a key by data/eval/questions.json",
            "key_derivation": (
                "The key is the section the question was generated from. The "
                "question was written by reading that section, so that section "
                "answers it by construction - the key is mechanical, not a "
                "judgement about what a complete answer requires."
            ),
            "limitation": (
                "Generated from text by a model, so these are better posed than "
                "real user questions. This measures generalisation to unseen "
                "material, not to unseen users."
            ),
            "skipped": skipped,
        },
        "questions": questions,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{len(questions)} questions, {len(skipped)} skipped, ${cost:.4f}")
    print(f"by source: {dict(collections.Counter(q['source_group'] for q in questions))}")
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    print("Commit this BEFORE running it, exactly as questions.json was.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
