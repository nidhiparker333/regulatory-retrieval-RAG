# Brief: animated infographic for a RAG project

Paste this whole file in as source material. Everything below is verified against
the repository — no figure appears here that a script does not assert.

---

## 1. What I want made

A polished **animated infographic for LinkedIn** explaining a retrieval-augmented
generation system I built and evaluated.

- **Format:** 4:5 portrait, 1080 × 1350 px. Looping animation, no player chrome.
- **Read time:** the structure must be graspable in a few seconds of scrolling.
- **Static fallback:** the first frame must stand alone as a complete image.
- **Tone:** a technical architecture graphic or research communication piece.
  Not a social-media explainer, not course material.

**The narrative arc, in order:**

1. What retrieval-augmented generation is — one line, no tutorial.
2. The evidence corpus — four source collections.
3. How the system is built and how it answers.
4. **How it was evaluated.** This must carry near-equal visual weight to the
   architecture. It is the point, not a footnote.

The organising idea: *a RAG system should not be judged on whether it produces an
answer. It should be judged on whether it retrieves the right evidence, supports
its claims with that evidence, and abstains when the evidence is insufficient.*

---

## 2. What the system is

Question answering across four AI-governance documents, where every answer cites
the article, annex or page it came from, and the system declines when the
documents cannot answer.

**Corpus**

| Source | Type |
|---|---|
| EU AI Act, consolidated text of 27 July 2026 (Reg. 2024/1689 as amended by 2026/1744) | binding regulation |
| NIST AI Risk Management Framework | risk guidance |
| NIST Generative AI Profile | GenAI-specific risk guidance |
| OWASP LLM Top 10 | security |

- 403 sections, **856 passages**, ~204,000 tokens (815,171 characters)
- 111 of the 403 sections cite another section
- Source documents committed to the repo, checksummed, and re-verified against
  what the publishers serve: 18/18 match

**Stack**

- Embeddings: `BAAI/bge-small-en-v1.5`, 384 dimensions, run locally on CPU
- Search: brute-force exact nearest neighbour, one matrix multiply. **No vector
  database.** The whole index is a **1.2 MB file**. Median retrieval **141 ms**
- Generation: Claude Sonnet 5, constrained to the retrieved passages
- Interface: FastAPI over the same retrieval engine the evaluation scores, plus a
  Next.js front end that shows the retrieval trace beside every answer
- Cost: **$0.0216 per question**

**Pipeline**

Built once, offline: parse → chunk → embed → index.
Chunking is structure-aware (1800 char target, 2600 max, 200 overlap) and splits
on section boundaries rather than character counts.

Per query: semantic search over all 856 passages → three post-retrieval steps →
generation with citations, or refusal.

The three post-retrieval steps:

1. **Anchor expansion** — if a hit lands mid-article, pull in part 1, because in
   legislation the general rule sits in paragraph 1.
2. **Cross-reference following** — references are extracted at parse time and
   followed at query time. Annex III cites Article 6, so Article 6 is retrieved
   too. No agent, no second model call, and it cannot invent a link that is not
   in the text.
3. **Source diversity** — each source group is guaranteed its best passage, so a
   cross-document question does not come back as one document five times.

Refusal is enforced at generation, by instruction, not by a confidence threshold.

---

## 3. What was measured

### Each retrieval step, scored separately

| Configuration | Strict retrieval |
|---|---|
| Search alone | 17/26 |
| + cross-reference following | 22/26 |
| + source diversity | 19/26 |
| **+ both (shipped)** | **24/26** |

### Cross-reference following, on the 8 multi-hop questions

| top 5 | top 10 | + following references |
|---|---|---|
| 3/8 | 3/8 | **7/8** |

Doubling how much was retrieved changed nothing. The second half of the answer was
never further down the ranking — it was behind a citation the document made itself.

### Source diversity, on the 2 cross-document questions

0/2 → **2/2**

### Hybrid retrieval was built, measured, and rejected

| Arm | Strict |
|---|---|
| BM25 alone | 14/26 |
| Reciprocal rank fusion | 16/26 |
| Semantic alone | 17/26 |

Scope of that finding: hybrid lost on questions phrased the way this set is.
Users typing article numbers directly would change the picture.

### A confidence threshold cannot detect an unanswerable question

| | Top score |
|---|---|
| Lowest-scoring **answerable** question | 0.678 |
| Highest-scoring **unanswerable** question | **0.769** |

The populations overlap, so no cut-off separates them. This is why refusal is
enforced where the answer is written.

### End-to-end, on the 30-question set (26 answerable, 4 unanswerable)

| | |
|---|---|
| Retrieval, strict | 24/26 |
| Refused when the corpus could not answer | 4/4 |
| Answers citing nothing | 0 |
| Quoted spans not found in the corpus | 0 of 18 checked |

### Variance across three full runs

answered 25/25/25 · refused 4/4 each time · uncited 0 each time · grounded moves
between 24 and 25. One question flips between runs.

---

## 4. The evaluation methodology — the part that matters

### The flaw in the first evaluation

The chunk size, the number of passages retrieved, and both post-retrieval steps
were all chosen by scoring them against the same 30 questions that were then
reported. That set chose the settings and then graded them. Committing the answer
keys before the first run rules out fitting the keys to the output; it does not
rule out fitting the system to the questions.

### The held-out set

**45 questions the system was never tuned against.**

- Generated by a **different model** (Opus 5) from 203 sections the tuning set
  never used as an answer key
- Each answer key is **mechanical**: the section the question was written from,
  not a judgement about what a complete answer requires
- 15 questions per source, none discarded
- Sampling seeded and the seed recorded, so the sample cannot be quietly re-rolled
- Committed before being run

### Blind grading

A separate model saw **only** the question, the answer, and the ground-truth
source text. Never the pipeline, never which configuration produced the answer,
never a previous verdict. It cannot be lenient toward a near miss because it
cannot tell one from a direct hit.

### What the held-out set showed

| | of 45 |
|---|---|
| Correct | 27 |
| Partial | 6 |
| Declined to answer | 11 |
| **Wrong** | **1** |
| Answers citing nothing | 0 |

Retrieval found the exact required section **26/45**, against 11/12 on comparable
in-sample questions. That drop is real and is reported as the headline.

Split by whether retrieval found the required section:

| | correct | partial | wrong | declined |
|---|---|---|---|---|
| retrieval hit (26) | 23 | 1 | 0 | 2 |
| retrieval missed (19) | 4 | 5 | **1** | 9 |

**When retrieval fails, the system declines rather than inventing.** It declined
nine times for every answer it got wrong.

### Three things the independent grader found that self-review had not

1. It **disagreed with the author's grading on 8 of 23**, and was harsher on five
   — answers marked correct it marked partial for omitting substantive material,
   even where the answer flagged its own gap. A rubric difference, not an error,
   but only one party got to pick the rubric.
2. It **found a defect in the refusal detection**: it counted 11 refusals where
   the code counted 8. Three answers declined in plain English without using the
   exact phrase the check matched on. Refusal is the most safety-critical
   behaviour in the system and it was being detected by one string comparison.
3. It **overturned a published conclusion.** The k-sweep on the tuning set showed
   a flat stretch from k=5 — an elbow, and an argument that retrieving more buys
   nothing. Out of sample there is no elbow at all: 26/45 at k=5 climbing to
   36/45 at k=20. The elbow was a 26-question set that had run out of headroom.

### Verification infrastructure

Nine scripts re-check every stage and exit non-zero on failure: source integrity
and identity, upstream match, deterministic parsing, cross-reference integrity,
no text lost in chunking, citation validity, embedding behaviour, and the graders
themselves (18 hand-computed verdicts). A tenth asserts **every figure in the
documentation against the pipeline** and fails the build on a stale number.

---

## 5. What still fails, and what was never measured

Include these if there is room. They are what make the rest credible.

- **One question fails outright.** "Can an ordinary person complain about an AI
  system, and to whom?" never reaches Article 85, *Right to lodge a complaint
  with a market surveillance authority*. Asked in the source's own words it
  returns at rank 1. Article 85 does not appear in the top 50 of 856 passages at
  any depth tested. The cause is vocabulary, not structure.
- **One fabricated answer in the 45.** It named the wrong body for qualified
  alerts about general-purpose models. Article 66 was never retrieved.
- **Sample size.** 26 answerable plus 45 held out. Every figure is a fraction.
- **No second human** has read these answers. A blind second model is better than
  one grader and is not an independent reader.
- **Not tested:** a cross-encoder reranker, any other embedding model, a
  long-context baseline (the Act alone fits in a modern context window), any
  other corpus, anything at scale.

---

## 6. Accuracy constraints — do not state any of these

The system does **not** use, and the graphic must not show or imply:

- BM25, keyword search, or hybrid retrieval — **built, measured, and rejected**
- Reciprocal rank fusion — same
- A vector database of any kind — it is a 1.2 MB file
- An agent, a planner, or a second model call in the retrieval loop
- Any hosting or deployment — it is not deployed anywhere
- "100% accurate", or any accuracy claim as a percentage

Do not invent mechanisms, metrics, or numbers. If a figure is not in this
document, it was not measured.

---

## 7. Visual direction

**Use:** dark refined background · clean modern typography · cyan, blue and
violet accents used sparingly · thin connecting lines · restrained glow · simple
technical line icons · strong spacing and clear hierarchy · generous whitespace.

**Avoid:** dashboard UI · excessive cards · cartoon people · generic AI imagery
(brains, robots, glowing orbs) · glossy 3D icons · dense paragraphs · beginner
phrasing · content-marketing language · emoji.

**Animation** should clarify, not decorate. Most of the frame stays still.
Candidates: document fragments moving into the index · embedding points drifting ·
the query entering the retrieval layer · retrieval paths illuminating · selected
evidence highlighting · retrieved evidence moving into the model context · the
evidence gate activating · the citation or abstention state resolving · the
evaluation checks arriving one by one.

Nothing should animate in from invisible, so the resting frame is complete.

---

## 8. Register

Headline and architecture: precise but self-explaining. A senior engineer who does
not build RAG should follow it.

Evaluation section: unapologetically technical. That is where the credibility
lives, and softening it costs more than it gains.

Repository: github.com/nidhiparker333/regulatory-retrieval-RAG
