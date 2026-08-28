"""
Check the evaluation set before trusting anything it measures.

An answer key is an assertion about the corpus. If it points at a section that
does not exist, or at one that does not actually contain the answer, every
score computed from it is meaningless - and the failure is invisible, because
the numbers still come out.

This does not run retrieval. It only checks that the questions are
well-formed and that their expected answers are really there.

Run:  .venv\\Scripts\\python.exe scripts\\validate_questions.py
"""

import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"

corpus = {s["id"]: s for s in json.loads((CLEAN / "corpus.json").read_text(encoding="utf-8"))}
chunks = json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8"))
chunked_ids = {c["section_id"] for c in chunks}

data = json.loads((ROOT / "data" / "eval" / "questions.json").read_text(encoding="utf-8"))
questions = data["questions"]

OK, FAIL = "[ok]  ", "[FAIL]"
problems = []


def check(cond: bool, msg: str) -> None:
    print(f"  {OK if cond else FAIL} {msg}")
    if not cond:
        problems.append(msg)


print("=" * 72)
print("1. STRUCTURE")
print("=" * 72)

ids = [q["id"] for q in questions]
check(len(ids) == len(set(ids)), f"question ids unique ({len(ids)} questions)")

by_cat = collections.Counter(q["category"] for q in questions)
print()
for cat, n in by_cat.most_common():
    print(f"      {cat:<16} {n}")

by_wording = collections.Counter(q.get("wording", "?") for q in questions)
print()
for w, n in by_wording.most_common():
    print(f"      {w:<16} {n}")

check(by_cat["out_of_corpus"] >= 3,
      f"at least 3 unanswerable questions ({by_cat['out_of_corpus']})")
check(by_cat["cross_ref"] >= 5,
      f"at least 5 cross-reference questions ({by_cat['cross_ref']})")


print("\n" + "=" * 72)
print("2. ANSWER KEYS EXIST IN THE CORPUS")
print("=" * 72)

missing, unchunked = [], []
for q in questions:
    for sid in q.get("expect_sections", []):
        if sid not in corpus:
            missing.append((q["id"], sid))
        elif sid not in chunked_ids:
            unchunked.append((q["id"], sid))

check(not missing, f"every expected section exists ({len(missing)} missing)")
for qid, sid in missing:
    print(f"        {qid}: '{sid}' is not in the corpus")

check(not unchunked, f"every expected section survived chunking ({len(unchunked)} dropped)")
for qid, sid in unchunked:
    print(f"        {qid}: '{sid}' exists but was dropped at chunking")

for q in questions:
    if q["category"] == "out_of_corpus":
        check(not q.get("expect_sections"),
              f"{q['id']} is unanswerable and expects nothing")


print("\n" + "=" * 72)
print("3. DO THE EXPECTED SECTIONS LOOK RIGHT?")
print("=" * 72)
print("  Read these. A key that exists but points at the wrong text is the")
print("  failure this cannot catch automatically.\n")

for q in questions:
    keys = q.get("expect_sections", [])
    srcs = q.get("expect_sources", [])
    label = f"{q['id']} [{q['category']}]"
    print(f"  {label}")
    print(f"     Q: {q['question']}")
    if not keys and not srcs:
        print(f"     -> expects NO answer (unanswerable)")
    for sid in keys:
        s = corpus.get(sid)
        if s:
            n_chunks = sum(1 for c in chunks if c["section_id"] == sid)
            print(f"     -> {s['citation']:<16} {s['title'][:48]:<50} ({n_chunks} chunks)")
    for src in srcs:
        if src not in [c for c in keys]:
            print(f"     -> any section from: {src}")
    print()


print("=" * 72)
print("VERDICT")
print("=" * 72)
if problems:
    print(f"  {len(problems)} problem(s):")
    for i, p in enumerate(problems, 1):
        print(f"    {i}. {p}")
else:
    print(f"  All structural checks passed. {len(questions)} questions ready.")
    print("  Answer keys still need a human read - see section 3.")
