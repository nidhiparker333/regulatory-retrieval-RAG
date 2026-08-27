"""
Checks on the index that verify_index.py does not make.

verify_index answers "is the index internally consistent" - alignment, vector
sanity, self-retrieval. This answers a different question: "is the embedding
step doing what the code claims it does". Those come apart, because a claim in
a docstring is not tested by anything.

Run:  .venv\\Scripts\\python.exe scripts\\verify_embeddings.py
"""

import json
import pathlib

import numpy as np
from fastembed import TextEmbedding

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  [{'ok ' if ok else 'FAIL'}]  {label}{('   ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def unit(v: np.ndarray) -> np.ndarray:
    return v / np.clip(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9, None)


def main() -> int:
    chunks = json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8"))
    store = np.load(CLEAN / "index.npz", allow_pickle=True)
    vectors = store["vectors"]
    model_name = str(store["model"])
    model = TextEmbedding(model_name=model_name)

    # parallel=None keeps everything in this process. parallel=0 forks workers,
    # which is fine for the batch job in embed.py but pointless for a handful
    # of probes and awkward to run from anything but a real file.
    def embed(texts, how="passage"):
        fn = model.passage_embed if how == "passage" else model.query_embed
        return unit(np.array(list(fn(texts, parallel=None)), dtype=np.float32))

    print("=" * 70)
    print("1. QUERY vs PASSAGE ENCODING")
    print("=" * 70)
    # BGE models are trained with an instruction prefix on queries, and
    # embed.py's docstring states that using one call for both is "a real,
    # silent quality loss". That is a testable claim, so test it.
    probes = [
        "Deployers shall assign human oversight to natural persons",
        "who has to supervise the AI?",
        "high-risk classification of AI systems",
    ]
    p = embed(probes, "passage")
    q = embed(probes, "query")
    sims = [float(p[i] @ q[i]) for i in range(len(probes))]
    for text, s in zip(probes, sims):
        print(f"         cos(passage, query) = {s:.6f}   {text[:46]!r}")

    identical = all(s > 0.99999 for s in sims)
    # This is pinned rather than demanded. On fastembed 0.8.0 the two calls are
    # both pass-throughs to embed() and this model defines no query prefix, so
    # identical vectors are the correct expectation - not a defect. The check
    # exists so that a library upgrade which STARTS applying a prefix shows up
    # as a deliberate change rather than silently moving every score.
    check(identical,
          "query/passage encodings match the pinned expectation (identical)",
          "prefix is a no-op on this model + fastembed version")
    if not identical:
        print("         NOTE: encodings now differ - the library changed "
              "behaviour. Re-measure retrieval before trusting old scores.")

    print("\n" + "=" * 70)
    print("2. DETERMINISM  -  does re-embedding reproduce the index?")
    print("=" * 70)
    sample = [c["text"] for c in chunks[:24]]
    a = embed(sample, "passage")
    b = embed(sample, "passage")
    check(np.array_equal(a, b), "two runs in-process are bitwise identical")
    drift = float(np.abs(a - vectors[: len(sample)]).max())
    check(drift < 1e-5, "re-embedding matches the stored index", f"max |diff| = {drift:.2e}")

    print("\n" + "=" * 70)
    print("3. RETRIEVAL  -  the flagship multi-hop question")
    print("=" * 70)
    question = "Is my CV screening tool for hiring considered high-risk?"
    qv = embed([question], "query")[0]
    scores = vectors @ qv
    top = np.argsort(-scores)[:5]
    for rank, i in enumerate(top, 1):
        print(f"         {rank}. {scores[i]:.3f}  {chunks[i]['citation']}")
    hit = next((r for r, i in enumerate(top, 1)
                if chunks[i]["section_id"] == "anx_III"
                and "4. Employment" in chunks[i]["text"]), None)
    check(hit is not None, "Annex III employment category is in the top 5",
          f"rank {hit}" if hit else "NOT RETRIEVED")

    print("\n" + "=" * 70)
    print("4. SEMANTIC SANITY  -  does the model separate meaning from wording?")
    print("=" * 70)
    pairs = [
        ("a cat sat on the mat", "a kitten rested on the rug", "related, no shared words"),
        ("a cat sat on the mat", "quarterly revenue rose 12%", "unrelated"),
        ("human oversight of AI", "people supervising automated systems", "domain paraphrase"),
    ]
    got = {}
    for x, y, label in pairs:
        e = embed([x, y], "passage")
        s = float(e[0] @ e[1])
        got[label] = s
        print(f"         {s:.3f}   {label:<26} {x!r} / {y!r}")
    check(got["related, no shared words"] > got["unrelated"] + 0.15,
          "related text scores well above unrelated")
    check(got["domain paraphrase"] > 0.65,
          "domain paraphrase is recognised", f"{got['domain paraphrase']:.3f}")

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    if failures:
        print(f"  {len(failures)} check(s) failed:")
        for f in failures:
            print(f"    - {f}")
        return 1
    print("  All embedding checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
