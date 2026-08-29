# regulatory-retrieval

Question answering across the documents that govern AI — a binding EU regulation,
two US risk frameworks, and a security standard — where every answer cites the
article, annex or page it came from, and the system declines when the documents
cannot answer.

Retrieval-augmented generation: the model answers from passages fetched out of
these four documents at query time, not from what it learned in training. Which
means the quality of the system is the quality of the retrieval, and that is the
part this repository measures.

## Results

30 questions with answer keys written from the source documents and committed
before the first run. Every answer then read by hand against the sources.

| | |
|---|---|
| **Correct** | **25 / 26** answerable |
| Refused when the corpus could not answer | **4 / 4** |
| Answers quoting text not in the corpus | **0** of 18 quotes checked |
| Answers citing nothing | **0** |
| Cost per question | **$0.0216** |

By question type:

| | answered | grounded | correct |
|---|---|---|---|
| Answer in one section | 12/13 | 12/13 | 12/13 |
| Answer spans linked sections | 8/8 | 8/8 | 8/8 |
| Answer spans two documents | 2/2 | 2/2 | 2/2 |
| **All answerable** | **25/26** | **25/26** | **25/26** |

Retrieval scored separately, and free: **24 / 26**.

Three answers are correct but incomplete, and each says which part it cannot
cover rather than filling the gap. One is wrong — see *Known limits*.

## The problem this solves

Two properties of this material break ordinary retrieval.

**The answer is often not where you look for it.** 111 of 403 sections cite
another section. Article 6 defines "high-risk" by pointing at Annex III; Annex
III's title points back at Article 6. Neither means anything alone, and a single
similarity search returns one of them.

**A retrieval system cannot tell when it does not know.** Ask for the five
nearest passages and you always get five, however far away they are. Measured
here: the highest-scoring *unanswerable* question beat the lowest-scoring
answerable one. No similarity threshold separates them.

## What it does about it

**Cross-references are recorded when the documents are parsed and followed at
query time.** Retrieving any part of Annex III pulls in Article 6 automatically,
because Annex III's own heading cites it. Deterministic, free, and incapable of
inventing a link that is not in the text. Measured: cross-reference questions go
**3/8 → 7/8**, while doubling how much was retrieved changed nothing.

**Refusal is enforced where the answer is written**, not where passages are
found — because the measurement above shows confidence scores cannot separate
answerable from unanswerable.

**Every source group is guaranteed its best passage.** Nearest-neighbour search
returns whatever scores highest, which on a cross-document question is routinely
five passages from one document and none from the other. Reserving a slot per
source costs at most two extra passages and is query-independent.

## How it works

```
403 sections ──chunk──> 856 passages ──embed──> 856 × 384 float32  (1.2 MB)
                                                        │
question ──embed──> 384-d vector ──── dot product ──────┘
                                          │
                                     top-k = 5
                                          │
                    ┌─────────────────────┼─────────────────────┐
              source diversity      anchor expansion     cross-references
              (best passage per     (part 1 of a         (sections the hits
               missing source)       split section)       cite, by parse-time
                                                          metadata)
                    └─────────────────────┼─────────────────────┘
                                          │
                              context, bounded at 60,000 chars
                                          │
                          one generation call, citation required
                                          │
                            cited answer  │  "NOT IN THE SOURCES"
```

**Embeddings** are `BAAI/bge-small-en-v1.5`, 384 dimensions, run locally on CPU.
The whole corpus embeds in 170s, once, for nothing.

**Search is brute force** — one matrix multiply against all 856 vectors,
unit-normalised so cosine similarity is a dot product. Exact, 141 ms at the
median, and no approximate-nearest-neighbour index to be wrong. A vector
database exists to avoid comparing against every vector; at this size that
trade is not worth making, and the index stays a file that ships with the
application.

**Chunk boundaries come from the drafter's own numbering** (`1.`, `(a)`) before
falling back to sentence ends, so provisions stay whole. Enumerated lists get one
chunk per item with no packing — Annex III's eight high-risk categories are eight
separate chunks, which is what makes "is my CV screening tool high-risk"
answerable at all.

**Cross-references are extracted at parse time**, not inferred at query time.
Every chunk carries the article and annex numbers its section cites, including
chunks that never mention them — Article 6 and Annex III are different documents
and can never share a chunk, so the link survives only as metadata.

**Generation is a single call** to `claude-sonnet-5` with adaptive thinking,
constrained to the retrieved passages, with refusal and per-claim citation
required by the system prompt and verified afterwards in code.

## The corpus

| Source | Format | Sections |
|---|---|---|
| EU AI Act — Regulation (EU) 2024/1689, consolidated 27 July 2026 | HTML | 133 |
| NIST AI 100-1 and AI 600-1 — Risk Management Framework and Generative AI Profile | PDF | 95 |
| OWASP LLM Top 10 (2026) | Markdown | 175 |

403 sections, 815,171 characters, split into 856 chunks. The index is
**1.2 MB** — no vector database; it ships with the application.

**The Act is taken as HTML, not PDF.** EUR-Lex publishes it in 24 languages and
two formats; the HTML carries the document's own structural markup (`id="art_6"`,
`id="anx_III"`), so articles and annexes are extracted exactly rather than
inferred from layout.

**Use the consolidated text, not the 2024 original.** The Regulation was amended
by Regulation (EU) 2026/1744. Articles 4a, 60a and 75a–d exist only in the
amended version, and their presence is how `verify_sources.py` proves which text
this is. Much of the tooling in this space still answers from the superseded
version.

ISO/IEC 42001 belongs in this corpus on merit and is **not included** — it sits
behind a paywall and cannot be redistributed.

## Not legal advice

A research project. Nothing it produces is legal advice, and its answers should
not be relied on for compliance decisions.

## Run it

```bash
python -m venv .venv
```
```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Everything up to generation is free and needs no API key.

```bash
.venv\Scripts\python.exe scripts\fetch.py
```
```bash
.venv\Scripts\python.exe scripts\parse_act.py
```
```bash
.venv\Scripts\python.exe scripts\parse_nist.py
```
```bash
.venv\Scripts\python.exe scripts\parse_owasp.py
```
```bash
.venv\Scripts\python.exe scripts\build_corpus.py
```
```bash
.venv\Scripts\python.exe scripts\chunk.py
```
```bash
.venv\Scripts\python.exe scripts\embed.py
```

Ask a question (needs a key in `api-key.txt`, which is gitignored):

```bash
.venv\Scripts\python.exe scripts\answer.py "is my CV screening tool high-risk?"
```

Score retrieval, compare every retrieval strategy, run the full evaluation:

```bash
.venv\Scripts\python.exe scripts\compare_arms.py
```
```bash
.venv\Scripts\python.exe scripts\run_full_eval.py
```
```bash
.venv\Scripts\python.exe scripts\metrics.py
```

## Verification

Every stage has a script that re-checks it. All exit non-zero on failure, so any
of them can gate a build.

| Script | Checks |
|---|---|
| `verify_upstream.py` | The committed bytes still match what the publishers serve |
| `verify_sources.py` | Integrity (sha256) and identity (is this the document it claims to be) |
| `validate.py` | Parsing coverage, article numbering, cross-reference integrity |
| `verify_index.py` | 15 checks: alignment, vector sanity, self-retrieval |
| `verify_embeddings.py` | The embedding step does what the code says it does |
| `test_scoring.py` | The graders agree with 18 hand-computed verdicts |
| `check_docs.py` | Every figure in this file matches the pipeline |

## Known limits

**One question fails, for a diagnosed reason.** "Can an ordinary person complain
about an AI system?" never reaches Article 85, *"Right to lodge a complaint with
a market surveillance authority"*. Asked in those words it returns at rank 1.
The question and the text share no vocabulary, and no retrieval arm recovers it —
the later steps operate on what search returned, and search never returns Article
85. It needs the question rewritten into the register of the source before
searching, which is not built.

**Correctness was graded by one reader, in one pass, and that reader built the
pipeline.** An independent grader would be better. Per-answer reasoning is in
`data/eval/correctness.json` so the judgement can be disputed rather than taken
on trust.

**30 questions is a small sample.** Read every figure as a fraction, not a
percentage. A single question is 3.8 points.

**Answer quality beyond citation grounding is unassessed** — whether an answer is
a *good* summary, not merely a supported one.

Engineering notes, including what was measured and rejected, are in
[FINDINGS.md](FINDINGS.md).
