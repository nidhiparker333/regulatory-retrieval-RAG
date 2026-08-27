"""
Is the chunking and the index actually correct?

Counts and eyeballing are not verification. This checks the properties that,
if violated, produce output that still looks plausible - which is the only
kind of bug that survives to production.

The critical one is alignment. search.py assumes vectors[i] describes
chunks[i]. Nothing enforces that. Re-chunk without re-embedding and every
answer would cite the wrong source while remaining perfectly readable.

Run:  .venv\\Scripts\\python.exe scripts\\verify_index.py
"""

import collections
import json
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"

OK, WARN, FAIL = "[ok]  ", "[warn]", "[FAIL]"
problems = []


def check(condition: bool, msg: str, level: str = FAIL) -> None:
    tag = OK if condition else level
    print(f"  {tag} {msg}")
    if not condition:
        problems.append(msg)


def section(title: str) -> None:
    print(f"\n{'=' * 66}\n{title}\n{'=' * 66}")


corpus = json.loads((CLEAN / "corpus.json").read_text(encoding="utf-8"))
chunks = json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8"))
store = np.load(CLEAN / "index.npz", allow_pickle=True)
vectors = store["vectors"]
vec_ids = [str(i) for i in store["ids"]]


# --------------------------------------------------------------------------
section("1. CHUNKING  -  did any text go missing?")

# Sections that survived the junk filter, by id.
chunked_section_ids = {c["section_id"] for c in chunks}
kept_sections = [s for s in corpus if s["id"] in chunked_section_ids]
dropped = [s for s in corpus if s["id"] not in chunked_section_ids]

section_chars = sum(s["chars"] for s in kept_sections)
# body_chars excludes the header stamped onto each chunk, and overlap is
# duplicated text - so chunk bodies should exceed section text slightly.
body_chars = sum(c["body_chars"] for c in chunks)
ratio = body_chars / section_chars

print(f"  sections chunked   : {len(kept_sections)}")
print(f"  sections dropped   : {len(dropped)} ({sum(s['chars'] for s in dropped):,} chars)")
print(f"  section text       : {section_chars:,} chars")
print(f"  chunk bodies       : {body_chars:,} chars")
print(f"  ratio              : {ratio:.3f}  (>1 expected: overlap duplicates text)")
check(ratio >= 0.98, f"no text lost in chunking (ratio {ratio:.3f})")
check(ratio <= 1.35, f"overlap not excessive (ratio {ratio:.3f})", WARN)

for s in dropped:
    print(f"      dropped: {s['citation'][:44]:<46} {s['chars']:>7,}")


# --------------------------------------------------------------------------
section("2. CHUNKS  -  are any degenerate?")

empty = [c for c in chunks if not c["text"].strip()]
tiny = [c for c in chunks if c["body_chars"] < 60]
huge = [c for c in chunks if c["chars"] > 3200]
no_cite = [c for c in chunks if not c["citation"].strip()]

check(not empty, f"no empty chunks (found {len(empty)})")
check(not no_cite, f"every chunk is citable (found {len(no_cite)} without)")
check(len(tiny) < 20, f"very small chunks: {len(tiny)}", WARN)
check(not huge, f"no chunk exceeds 3,200 chars (found {len(huge)})", WARN)

# Duplicate text wastes retrieval slots and skews any similarity measure.
seen = collections.Counter(c["text"] for c in chunks)
dupes = [t for t, n in seen.items() if n > 1]
check(not dupes, f"no exact duplicate chunks (found {len(dupes)})", WARN)

sizes = sorted(c["body_chars"] for c in chunks)
print(f"\n  body size: min {sizes[0]}, median {sizes[len(sizes)//2]:,}, max {sizes[-1]:,}")
if tiny:
    print("  smallest few:")
    for c in sorted(chunks, key=lambda c: c["body_chars"])[:4]:
        print(f"      {c['citation'][:40]:<42} {c['body_chars']:>4}  {c['text'].splitlines()[-1][:44]!r}")


# --------------------------------------------------------------------------
section("3. ALIGNMENT  -  does vector[i] describe chunk[i]?")
# The failure that produces confident, readable, completely wrong citations.

check(len(vectors) == len(chunks),
      f"vector count matches chunk count ({len(vectors)} vs {len(chunks)})")

chunk_ids = [c["id"] for c in chunks]
aligned = vec_ids == chunk_ids
check(aligned, "stored ids match chunks.json order exactly")
if not aligned:
    for i, (a, b) in enumerate(zip(vec_ids, chunk_ids)):
        if a != b:
            print(f"      first divergence at position {i}: index={a!r} chunks={b!r}")
            break

check(len(set(chunk_ids)) == len(chunk_ids), "chunk ids are unique")


# --------------------------------------------------------------------------
section("4. VECTORS  -  are the numbers sane?")

check(vectors.dtype == np.float32, f"dtype is float32 (got {vectors.dtype})", WARN)
check(not np.isnan(vectors).any(), "no NaN values")
check(not np.isinf(vectors).any(), "no infinite values")

norms = np.linalg.norm(vectors, axis=1)
check(bool(np.allclose(norms, 1.0, atol=1e-3)),
      f"all vectors unit length (min {norms.min():.4f}, max {norms.max():.4f})")

zero_vecs = int((norms < 1e-6).sum())
check(zero_vecs == 0, f"no zero vectors (found {zero_vecs})")

# Identical vectors for different text would mean the model collapsed.
uniq = len({v.tobytes() for v in vectors})
check(uniq == len(vectors),
      f"every vector is distinct ({uniq} unique of {len(vectors)})", WARN)


# --------------------------------------------------------------------------
section("5. BEHAVIOUR  -  does the index retrieve itself?")
# A chunk used as its own query must return itself first. If it doesn't,
# the index is scrambled regardless of what the id check said.

rng = np.random.default_rng(0)
probe_idx = rng.choice(len(chunks), size=40, replace=False)
self_hits = 0
for i in probe_idx:
    scores = vectors @ vectors[i]
    if int(np.argmax(scores)) == i:
        self_hits += 1

check(self_hits == len(probe_idx),
      f"every probed chunk retrieves itself first ({self_hits}/{len(probe_idx)})")

# Chunks from the same section should sit closer than random pairs.
multi = [c for c in chunks if c["of_parts"] > 1]
if multi:
    by_section = collections.defaultdict(list)
    for i, c in enumerate(chunks):
        by_section[c["section_id"]].append(i)
    same, diff = [], []
    for ids in by_section.values():
        if len(ids) > 1:
            same.append(float(vectors[ids[0]] @ vectors[ids[1]]))
    for _ in range(200):
        a, b = rng.choice(len(chunks), size=2, replace=False)
        diff.append(float(vectors[a] @ vectors[b]))
    print(f"\n  mean similarity, same section : {np.mean(same):.3f}")
    print(f"  mean similarity, random pair  : {np.mean(diff):.3f}")
    check(np.mean(same) > np.mean(diff) + 0.1,
          "sibling chunks are closer than random pairs")


# --------------------------------------------------------------------------
section("VERDICT")
if not problems:
    print("  All checks passed.")
else:
    print(f"  {len(problems)} problem(s):\n")
    for i, p in enumerate(problems, 1):
        print(f"    {i}. {p}")
