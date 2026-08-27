"""
Step 5: turn every chunk into numbers, once, and save them.

Runs locally on CPU. No API, no key, no cost. Takes a couple of minutes the
first time and then never again - the vectors are saved to disk and every
search afterwards just reads the file.

A note on the two ways to embed text, and on a claim that turned out to be
false here:

  passage_embed()  for the documents being searched
  query_embed()    for the question doing the searching

BGE models are trained with an instruction prefix on queries, and the reasoning
usually given is sound: a question and a passage that mean the same thing are
written very differently - "who has to supervise the AI?" versus "Deployers
shall assign human oversight to natural persons".

But measured on this stack, the two calls return **bitwise identical** vectors.
In fastembed 0.8.0 both query_embed() and passage_embed() are pass-throughs to
embed(); the base class leaves them for models to specialise, and
BAAI/bge-small-en-v1.5 defines no query prefix (its `tasks` map is empty). So
the distinction costs nothing and buys nothing, and the code kept it only
because it reads as if it mattered.

Whether the prefix WOULD help is a separate question and an open one. BGE v1.5
was trained to retrieve well without the instruction, so the gain is likely
small - but "likely small" is not a measurement. Adding the prefix by hand and
scoring it against the question set is free, and it belongs with the other
retrieval hypotheses rather than being switched on because it sounds right.

scripts/verify_embeddings.py asserts this, so if a future fastembed starts
applying a prefix the change is caught rather than silently altering results.

Run:  .venv\\Scripts\\python.exe scripts\\embed.py
"""

import json
import pathlib
import time

import numpy as np
from fastembed import TextEmbedding

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
OUT = CLEAN / "index.npz"

MODEL_NAME = "BAAI/bge-small-en-v1.5"   # 384 dims, ~50 MB, runs on CPU


def main() -> None:
    chunks = json.loads((CLEAN / "chunks.json").read_text(encoding="utf-8"))
    print(f"Chunks to embed: {len(chunks)}")

    print(f"Loading {MODEL_NAME} ...")
    model = TextEmbedding(model_name=MODEL_NAME)

    texts = [c["text"] for c in chunks]
    started = time.time()

    # passage_embed, not embed - these are the documents being searched.
    #
    # batch_size and parallel matter here: the first run took 680s at about
    # 1 chunk/sec with the defaults, using ~4.3 GB. parallel=0 uses every
    # available core; batching keeps memory bounded rather than loading the
    # whole corpus into one tensor.
    vectors = np.array(
        list(model.passage_embed(texts, batch_size=32, parallel=0)),
        dtype=np.float32,
    )

    elapsed = time.time() - started
    print(f"Embedded in {elapsed:.1f}s  ({len(chunks)/elapsed:.0f} chunks/sec)")
    print(f"Shape: {vectors.shape}")

    # Normalise to unit length now, so similarity later is a plain dot
    # product instead of a division per comparison. Same answer, less work.
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.clip(norms, 1e-9, None)

    np.savez_compressed(
        OUT,
        vectors=vectors,
        ids=np.array([c["id"] for c in chunks]),
        model=MODEL_NAME,
    )

    size_mb = OUT.stat().st_size / 1_000_000
    print(f"\nSaved {OUT.name}  ({size_mb:.1f} MB)")
    print(f"  {vectors.shape[0]} vectors x {vectors.shape[1]} dimensions")
    print(f"  small enough to ship with the app - no vector database needed")
    print(f"\nCost: $0.00")


if __name__ == "__main__":
    main()
