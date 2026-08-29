"""
Sweep the chunk-size parameters and score each one.

TARGET, MAX and OVERLAP were inherited and never tested, which makes them the
largest untested lever in the pipeline: where you cut decides what can ever be
retrieved. Annex III is the standing proof - packing its eight categories
together made "is my CV screening tool high-risk" unanswerable, and giving each
item its own chunk moved the answer to rank 1.

Each configuration is re-chunked, re-embedded and scored. Embedding is the slow
part, roughly three minutes a configuration on CPU, and free.

The shipped chunks.json and index.npz are backed up and restored afterwards.
A sweep that leaves the corpus in whatever state the last configuration
produced would silently invalidate every figure in the documentation.

Run:  .venv\\Scripts\\python.exe scripts\\sweep_chunking.py
"""

import importlib
import json
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
EVAL = ROOT / "data" / "eval"
PY = ROOT / ".venv" / "Scripts" / "python.exe"

# (TARGET, MAX, OVERLAP). The first row is what ships.
CONFIGS = [
    (1800, 2600, 200),   # shipped
    (1200, 1800, 150),   # smaller, tighter passages
    (2400, 3400, 250),   # larger, more context per passage
    (1800, 2600,   0),   # shipped size, no overlap
    (900,  1400, 100),   # much smaller
]


def score_all() -> tuple[int, int, float]:
    """Strict and partial retrieval score over the answerable questions."""
    for m in ("retrieval",):
        if m in sys.modules:
            del sys.modules[m]
    sys.path.insert(0, str(ROOT / "scripts"))
    from retrieval import Retrieval

    R = Retrieval()
    qs = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]
    ans = [q for q in qs if q["category"] != "out_of_corpus"]
    strict = 0
    partials = []
    for q in ans:
        hits = R.search(q["question"], k=5, expand=True, diverse=True)
        got_s = {c["section_id"] for c in hits}
        got_src = {c["source_group"] for c in hits}
        need_s = q.get("expect_sections") or []
        need_src = q.get("expect_sources") or []
        found = sum(1 for s in need_s if s in got_s) + sum(1 for s in need_src if s in got_src)
        total = len(need_s) + len(need_src)
        if total == 0:
            strict += 1
            partials.append(1.0)
        else:
            strict += found == total
            partials.append(found / total)
    return strict, len(ans), sum(partials) / len(partials)


def main() -> int:
    chunks_f, index_f = CLEAN / "chunks.json", CLEAN / "index.npz"
    backup = ROOT / ".sweep-backup"
    backup.mkdir(exist_ok=True)
    shutil.copy2(chunks_f, backup / "chunks.json")
    shutil.copy2(index_f, backup / "index.npz")

    chunk_src = (ROOT / "scripts" / "chunk.py").read_text(encoding="utf-8")
    rows = []

    try:
        for target, mx, overlap in CONFIGS:
            label = f"{target}/{mx}/{overlap}"
            print(f"--- TARGET={target} MAX={mx} OVERLAP={overlap} " + "-" * 24)

            patched = (chunk_src
                       .replace("TARGET = 1800", f"TARGET = {target}")
                       .replace("MAX = 2600", f"MAX = {mx}")
                       .replace("OVERLAP = 200", f"OVERLAP = {overlap}"))
            tmp = ROOT / "scripts" / "_sweep_chunk.py"
            tmp.write_text(patched, encoding="utf-8")

            t0 = time.time()
            for step in (tmp, ROOT / "scripts" / "embed.py"):
                r = subprocess.run([str(PY), str(step)], cwd=ROOT,
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    print(r.stdout[-1500:], r.stderr[-1500:])
                    return 1
            tmp.unlink(missing_ok=True)

            n_chunks = len(json.loads(chunks_f.read_text(encoding="utf-8")))
            strict, total, partial = score_all()
            rows.append((label, n_chunks, strict, total, partial, time.time() - t0))
            print(f"    {n_chunks} chunks   strict {strict}/{total}   "
                  f"partial {partial:.3f}   ({time.time()-t0:.0f}s)\n")
    finally:
        shutil.copy2(backup / "chunks.json", chunks_f)
        shutil.copy2(backup / "index.npz", index_f)
        shutil.rmtree(backup, ignore_errors=True)
        (ROOT / "scripts" / "_sweep_chunk.py").unlink(missing_ok=True)
        print("restored the shipped chunks.json and index.npz\n")

    print("=" * 68)
    print("CHUNK SIZE SWEEP")
    print("=" * 68)
    print(f"  {'target/max/overlap':<22}{'chunks':>8}{'strict':>10}{'partial':>10}")
    print("-" * 68)
    for label, n, strict, total, partial, _ in rows:
        ship = "  <- shipped" if label == "1800/2600/200" else ""
        print(f"  {label:<22}{n:>8}{f'{strict}/{total}':>10}{partial:>10.3f}{ship}")

    best = max(rows, key=lambda r: (r[2], r[4]))
    print(f"\n  best: {best[0]} at {best[2]}/{best[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
