# Findings

Engineering notes. **No number appears here unless something measured it**, and
`check_docs.py` verifies every figure against the pipeline.

---

## Measured results

30 questions, keys written from the sources and committed before the first run.
Every answer then read by hand against the source text.

| | Measured |
|---|---|
| Correct | **25 / 26** answerable |
| Refused when unanswerable | **4 / 4** |
| Quotes not found in the corpus | **0** of 18 |
| Answers citing nothing | **0** |
| Retrieval, strict | **24 / 26** |
| Cost per question | **$0.0216** — $22 per thousand |
| Retrieval latency | 141 ms p50 |
| Index | 856 × 384 float32, **1.2 MB**, no vector database |

---

## What works

### Cross-reference following: 3/8 → 7/8, and retrieving more does nothing

| top 5 | top 10 | + following references |
|---|---|---|
| 3/8 | 3/8 | **7/8** |

The middle column is the result worth reporting. The second half of the answer
is only reachable through a citation the document makes itself — not by
retrieving more of what already came back.

References are recorded at parse time and followed at query time. No agent, no
second model call, no per-question cost, and it cannot invent a link that is not
in the text. The usual answer to multi-hop retrieval is an agent that decides
what to look up next; on this corpus, reading the footnotes beats it.

### Refusal has to be enforced where the answer is written

Retrieval always returns *k* passages, however far away they are, so the hope was
that low similarity would flag an unanswerable question.

| | Top score |
|---|---|
| Lowest-scoring **answerable** question | 0.678 |
| Highest-scoring **unanswerable** question | **0.769** |

The unanswerable question scores *higher*. "What do the recitals say about
high-risk classification" — asked against a corpus that provably contains no
recitals — beats "is my CV screening tool for hiring considered high-risk",
which has a correct and retrievable answer. **No threshold separates these two
populations.**

Enforced at generation instead: **4/4**. Each refusal names what it actually held
and why that was not enough — the Colorado question identifies the passages as EU
provisions, the recitals question checks the document type of what it was given.

### Nearest-neighbour search cannot span two documents on its own

Top-k returns whatever scores highest, and on a cross-document question that is
routinely one document five times over. C01 retrieved five NIST passages and no
Article 9; C05 retrieved the Act and no OWASP. Both then behaved correctly on
what they held — C01 refused rather than write a one-sided comparison — but the
missing half was in the corpus the whole time, out-ranked rather than absent.

Reserving one slot per unrepresented source group fixes it for at most two extra
passages, and needs no knowledge of the question: **0/2 → 2/2**.

### Run it three times and one question moves

Generation is stochastic, so every end-to-end figure above is a sample. Three
full runs:

| | runs | |
|---|---|---|
| answered | 25, 25, 25 | **stable** |
| refused when unanswerable | 4, 4, 4 | **stable** |
| answers with no citation | 0, 0, 0 | **stable** |
| grounded | 25, 25, 24 | **varies** |

The behaviours that matter for safety do not move. Refusal is 4/4 in every run,
and no run produced an uncited answer.

What moves is **C05**, the cross-document cybersecurity question: in one run of
three it answered from the Act and never cited OWASP. So "cross-document 2/2" is
true of the reported run and is not a reliable 2/2 — source diversity puts the
OWASP passage in front of the model, and the model does not always use it.
Retrieval is deterministic here; generation is not, and this is the seam.

Citation counts move further than verdicts do. O03 ranged from 0 to 14 citations
across three runs while refusing correctly every time — the refusal is stable,
the wording around it is not.

### Answers decline the part they cannot cover

Three correct answers are incomplete and each says so: one was handed only Annex
IV's *header* and refuses to list contents it never received; one notes it has
Article 6(1) but not 6(2); one says the Measure function was not detailed in its
passages. None invents the missing half.

---

## What each step is worth

Every part of retrieval was scored separately against the question set, for
free, so nothing is in the pipeline on the strength of sounding sensible.

| | Strict |
|---|---|
| Search alone | 17/26 |
| + following cross-references | 22/26 |
| + source diversity | 19/26 |
| **+ both (shipped)** | **24/26** |

The two steps fix different failures and barely overlap. Following references
recovers the multi-hop questions and does nothing for cross-document ones;
diversity does the reverse. Together they are worth more than either alone.

### How many passages to retrieve, measured rather than inherited

`k` was carried over from the earlier project and had never been tested here.
Swept against the question set, free:

| k | strict | passages | context |
|---|---|---|---|
| 3 | 21/26 | 12.7 | 14,486 |
| **5** | **24/26** | **16.7** | **18,638** |
| 8 | 24/26 | 23.6 | 26,213 |
| 10 | 24/26 | 29.4 | 32,443 |
| 15 | 25/26 | 38.3 | 42,384 |
| 20 | 25/26 | 44.8 | 50,050 |

Three is too few. **Five to ten changes nothing at all** — the same flat stretch
the multi-hop result found, now bounded: more passages of the same kind do not
help. Fifteen adds one question and then twenty adds nothing, so the curve has
an elbow rather than a slope.

> **This elbow does not exist out of sample.** On 45 held-out questions the
> curve climbs the whole way — 26/45 at k=5 to 36/45 at k=20, with no flat
> stretch anywhere. The elbow above is an artefact of a 26-question set that
> had already saturated. See *Tuned on the test set* below; `k=5` still ships,
> but the reason has changed, and the reason above is not one that survives.

`k=5` still ships. The question k=15 recovers is X08, whose missing half —
Article 60a — sits at rank 11. But X08 was already graded **correct** at k=5:
it answered from Article 60, and grounding passes on any overlap with the key.
So k=15 buys a better retrieval number for 2.3× the context, with no measured
improvement in the answer. Paying that without evidence is the mistake this
project exists to avoid; the sweep is recorded so the trade can be re-argued.

### Chunk size was inherited. Swept, it turns out to be right — and overlap does nothing

Where you cut decides what can ever be retrieved, which makes this the largest
lever in the pipeline. It had never been tested. Each configuration re-chunked,
re-embedded and re-scored:

| target / max / overlap | chunks | strict | partial |
|---|---|---|---|
| **1800 / 2600 / 200** | 856 | **24/26** | **0.942** |
| 2400 / 3400 / 250 | 731 | 24/26 | 0.942 |
| 1800 / 2600 / **0** | 856 | 24/26 | 0.942 |
| 1200 / 1800 / 150 | 1063 | 23/26 | 0.929 |
| 900 / 1400 / 100 | 1227 | 23/26 | 0.929 |

Smaller is worse, and both smaller configurations lose the same question — C01,
which needs Article 9 alongside NIST. The reason is not the one that suggests
itself.

Article 9 is split into eight parts under every configuration, so fragmentation
is not the cause. Its best chunk ranks **62 of 856** in the shipped corpus and
**93 of 1227** in the smallest: search never surfaces it at either size. Article
9 reaches the answer entirely through cross-reference following — some retrieved
passage cites it.

So what smaller chunks break is not the target but the **seed**. Cutting finer
changes which passages win the top five, and those passages carry different
citations. The reference graph is only as good as what retrieval hands it, and
chunk size moves that quietly.

That makes chunk size and multi-hop retrieval coupled rather than independent
knobs, which is not how either is usually discussed.

**Overlap contributes nothing measurable.** Dropping it entirely — 1800/2600/0 —
scores identically to the shipped 200 characters, which cost 2.6% duplicated
text across the corpus.

That is not the same as overlap being useless. It guards against an answer
straddling a cut, and on 26 questions that failure mode may simply not occur.
Absence of evidence at this sample size is not evidence of absence, so it stays:
the cost is small and known, the risk it covers is real and unmeasured. Worth
revisiting on a larger question set.

The shipped configuration was inherited and is now tested rather than assumed,
which is the point of running this at all.

### The cross-reference cap was costing three questions

Following stopped after four references — and the fourth is not reliably the
useful one, because references are collected in corpus order, not by relevance.
Uncapped: **21/26 → 24/26**. It is now bounded by context size rather than count,
because characters are the cost and passage count is only a proxy.

---

## Tuned on the test set — and what happens when that stops

Everything above this line was measured against the same 30 questions the
system was tuned on. The 30-question set has a defence that is true and
narrower than it sounds: the keys were written from the sources and committed
before the first run, so they cannot have been fitted to the output, and
`git log` proves the ordering.

That answers the wrong question. `k=5`, the chunk size and both retrieval arms
were each **chosen by scoring against those same 30 questions**. Every
retrieval figure above is in-sample. No commit timestamp touches that.

So: **45 held-out questions**, generated from 203 sections the tuning set never
used as a key, by Opus 5, which was shown one section of source text and nothing
about this system. The key is the section each question was written from —
mechanical, not a judgement about what a complete answer needs. Seeded and
recorded. Committed before being run. 15 per source, none discarded.

### Out of sample, retrieval is much worse

| | in sample | out of sample |
|---|---|---|
| found the required section | 11/12 | **26/45** |

Comparable questions only: the 12 tuning questions whose key is a single section
with no source requirement, which is the same shape of task as a held-out
question. By source, held-out: EU AI Act 9/15, NIST 8/15, OWASP 9/15 — the drop
is not one document being weak.

### The k=5 decision does not survive the move

| k | held-out | tuning set |
|---|---|---|
| 3 | 20/45 | 9/12 |
| **5** | **26/45** | **11/12** |
| 8 | 31/45 | 11/12 |
| 10 | 33/45 | 11/12 |
| 15 | 34/45 | 11/12 |
| 20 | 36/45 | 11/12 |

In sample the curve is flat from k=5 and the elbow argument is clean. Out of
sample **there is no elbow** — every increase buys questions, all the way to 20.
The flat stretch was a 26-question set running out of headroom, and it produced
a confident conclusion about diminishing returns that was really a statement
about the sample size.

`k=5` still ships, because context cost is real and the answers at k=5 are
graded below. But it now ships as a cost trade with a known price, not as the
free lunch the in-sample curve implied.

### What the held-out set structurally cannot test

| | held-out | tuning set |
|---|---|---|
| search alone | 25/45 | 11/12 |
| + cross-references | 26/45 | 11/12 |
| + source diversity | 25/45 | 11/12 |
| + both (shipped) | 26/45 | 11/12 |

Both arms together are worth **one question out of 45**, which looks like a
refutation and is not. Every held-out key is a *single* section, because each
question was generated from one. Cross-reference following and source diversity
exist for questions that need **two or more** sections or sources — the multi-hop
and cross-document cases. This set contains none, by construction.

So this table is not evidence the arms are worthless. It is evidence that a
generated set does not produce the question type they were built for, which is
a limitation of the held-out set and is why the in-sample 3/8 → 7/8 multi-hop
result is not withdrawn. Testing those arms out of sample needs a held-out set
built specifically for multi-hop, and that has not been done.

---

## Graded by a model that has never seen the system

Every correctness verdict here was mine, in one pass, and I built the pipeline.
That was disclosed as a weakness in three places. Disclosure is not repair.

**Opus 5 grades Sonnet 5's answers.** It sees the question, the answer, and the
ground-truth source text. It does not see the pipeline, the retrieval design,
which passages were retrieved, whether retrieval hit, or any earlier verdict —
so it cannot be lenient towards a near miss, because it cannot tell one from a
direct hit.

### On the held-out set

| | of 45 |
|---|---|
| correct | **27** |
| partial | 6 |
| refused | 11 |
| **wrong** | **1** |
| uncited | **0** |

Split by whether retrieval found the exact section:

| | correct | partial | wrong | refused |
|---|---|---|---|---|
| retrieval hit (26) | 23 | 1 | **0** | 2 |
| retrieval missed (19) | 4 | 5 | **1** | 9 |

**This is the result the whole project rests on.** When retrieval fails, the
system refuses 9 times out of 19 and is still substantively right 9 more. It
fabricated once. Retrieval at 26/45 looks poor until you see what the other 19
did with it: mostly declined, rarely wrong.

The one failure is H33, *"which body gives the Commission opinions on qualified
alerts about general-purpose models"*. The answer names the wrong body; Article
66(n) gives it to the Board. Retrieval never returned Article 66 — its best
chunk ranks 26 of 856 — and the model answered confidently from what it had
instead of declining. That is the failure mode the refusal instruction exists to
prevent, and here it did not fire.

### On the original 30, the grader is harsher than I was

| | mine | blind |
|---|---|---|
| correct | 25/26 | **16/23** |
| partial | — | 6 |
| wrong | 1 | **0** |

Agreement on 15 of 23; disagreement on 8, and **five run the same way**: D01,
X04, X07, X08 and C01 I marked correct and the grader marks partial, each for
omitting substantive material the source contains.

The gap is a rubric, not an error. I counted an answer that flags its own
incompleteness as correct, and wrote that up approvingly — *"Answers decline the
part they cannot cover"*. An independent grader counts the same answer as
partial: saying so is better than not saying so, and it is still incomplete.
Both readings are defensible. Only one of them was mine to choose, which is the
entire problem with grading your own system.

What holds under both rubrics: **zero wrong answers on the tuning set, one on
the held-out set.** The system's accuracy claim was generous. Its
does-not-fabricate claim was not.

### The grader found a defect in the code

It counted **11 refusals where `answer.py` counted 8**. Rule 3 of the system
prompt asks a refusal to open with the exact string `NOT IN THE SOURCES`. Three
answers declined in plain English instead — *"this specific scenario is not
addressed"*, *"I cannot fully answer this question"* — and the strict check read
all three as ordinary answers.

Refusal is the most safety-critical behaviour in this system and it was detected
by matching one string. Anything consuming this output programmatically would
have treated those three as answers. `answer.py` now reports `refused` (strict,
so every published figure still means what it meant) alongside `declined`, which
agrees with the independent grader on all 45 with no false positives.

Instructed refusal works in substance and not reliably in form. Nothing in the
repository could have found that, because every check in it was written by the
person who wrote the prompt.

---

## What still fails

### One question, and the cause is vocabulary rather than structure

*"Can an ordinary person complain about an AI system, and to whom?"* never
reaches Article 85, titled *"Right to lodge a complaint with a market
surveillance authority"*. Asked in those words it returns at **rank 1, 0.901**.
The article is perfectly findable; the everyday phrasing does not reach it.

No retrieval arm recovers it, and neither does retrieving more: **Article 85
does not appear in the top 50 of 856 passages.** Following references and source
diversity both operate on what search returned, and search never returns it at
any depth tested. It needs the
question rewritten into the register of the source before searching, which is a
different mechanism and is not built.

Structural problems — cross-references, multi-hop, buried list items — are
solved. What remains is the distance between how a person asks and how a
legislature writes.

### Two words decide the flagship question

The same failure, on the question this project leads with, found by trying to
run the README's own example from a fresh clone.

| asked as | Annex III | Article 6 |
|---|---|---|
| *Is my CV screening tool **for hiring** considered high-risk?* | parts 1, 4, 5 | **yes** |
| *Is my CV screening tool high-risk?* | part 1 only | **no** |

Dropping *for hiring* costs Article 6 entirely. With it, search reaches Annex III
parts 4 and 5 — the employment category — and those parts cite Article 6, so
following references brings it in. Without it, only part 1 comes back, the
heading, which does not carry that citation. The multi-hop machinery is intact
and never gets the seed it needs.

This is worth more than the D04 result above, because D04 is a question nobody
tuned anything on and this is *the* demonstration question. Two words of
practitioner vocabulary — the ones naming the Annex III category — are load
bearing, and nothing in the pipeline would tell you which two.

It also explains why the held-out numbers are what they are. Those questions were
written by a model asked not to reuse the source's phrasing, so they are full of
exactly this: the right question in the wrong words.

---

## The detour worth recording

### The sophisticated-looking failure had the least sophisticated cause

The flagship question — *Is my CV screening tool for hiring considered
high-risk?* — first returned
neither Article 6 nor Annex III. The obvious diagnosis was that the embeddings
were too weak for this kind of question, which is the point at which most people
reach for a bigger model or a reranker.

The actual cause was ten lines of string handling. Annex III is eight numbered
high-risk categories, and the chunker was packing small pieces together to fill a
target size — splicing the tail of *Education* onto the head of *Employment*. No
chunk was coherently about hiring, so nothing could match a question about
hiring.

Giving each list item its own chunk moved the correct answer to rank 1. The most
sophisticated-looking failure had the least sophisticated cause, and it was found
by printing the data and reading it.

---

## How the numbers are verified

Nine scripts re-check every stage, each exiting non-zero on failure. They exist
because the failures that matter here produce output that still reads perfectly.

| Property | Why it would be invisible if broken |
|---|---|
| **Source identity** | A truncated download, the wrong language edition, or the superseded 2024 Act all hash consistently and pass an integrity check forever. Articles 4a and 75a–d exist only in the consolidated text, so their presence settles which text this is |
| **Upstream match** | 18/18 sources still match what the publishers serve. The Act's page differs by a rotating analytics id, so it is compared by its article and annex text — a check that always fires is one you stop reading |
| **Deterministic parsing** | Output was byte-different between runs from set iteration order. Nothing downstream changed, but a corpus that cannot be checksummed cannot be evidence |
| **Cross-reference integrity** | The Act cites other laws in the same form it cites itself. 12% of recorded references pointed at the GDPR or a Directive, not the Act — following those pulls the wrong article into an answer |
| **No text lost in chunking** | All 399 sections verified reconstructable from their chunks. Short pieces were being dropped, two of them operative provisions |
| **Citations describe real chunks** | Part numbering was gapped, so a citation could read "part 3 of 8" for a document with seven parts — and one section lost its part 1 entirely, silently disabling anchor expansion for it |
| **The embedding step does what it says** | `query_embed` and `passage_embed` return bitwise identical vectors on this model; the code described the distinction as load-bearing |
| **The graders are graded** | 18 hand-computed verdicts. The previous scorer dropped three questions from its totals and labelled a refusal count as "accuracy" |

---

## What is not measured

- **Answer quality beyond citation grounding.** Whether an answer is a good
  summary, not merely a supported one, is unassessed.
- **Human correctness was graded by one reader in one pass**, and that reader
  built the pipeline. That is now cross-checked rather than merely disclosed:
  Opus 5 grades both sets blind, disagrees on 8 of 23, and is harsher in five.
  Both graders are still models or me — **no second human has read these
  answers**, and a second model is not an independent human.
- **Sample size.** 30 questions, 26 answerable, plus 45 held out. Every figure is
  a fraction, not a percentage.
- **Generalisation to unseen users.** The held-out set is questions about text,
  written from text by a model, so they are better posed than a real user's.
  It measures generalisation to unseen *material*. D04 — the everyday-phrasing
  failure — is exactly the kind of question this process under-produces, so the
  held-out numbers are, if anything, optimistic about phrasing.
- **The retrieval arms, out of sample.** Held-out keys are single sections, so
  the set cannot contain the multi-hop and cross-document questions the two arms
  exist for. Their 3/8 → 7/8 result remains in-sample only.
- **Chunk size, out of sample.** The sweep was scored against the tuning set
  alone and has not been re-run against the held-out questions.
- **Any corpus but this one**, and anything at scale.
- **The embedding model.** `bge-small-en-v1.5` was never compared against a
  larger model or a different family. Whether a bigger encoder closes the
  vocabulary gap that D04 exposes is unknown.
- **Run-to-run variance.** Generation is stochastic and the evaluation was run
  once. Every end-to-end figure here is a single sample, so a one-question
  difference between two configurations cannot be distinguished from noise.
- **Refusal rests on four questions**, which is the smallest sample in the set
  and the most safety-critical behaviour in the system.
- **Whether the answer keys are the only defensible ones.** They are one reading
  of what a complete answer requires.

---

## Open questions

- Does rewriting a question into the register of the source recover the
  vocabulary failure? It is the one remaining failure mode with a named cause.
- Does a cross-encoder reranker - a second pass that reads candidates rather
  than comparing them by distance - help here? Untested.
- **Is retrieval necessary at all?** The Act alone is ~94k tokens and fits in a
  modern context window. Retrieval costs $0.0216 a question; stuffing the full
  text would cost more, but accuracy, not cost, is the question worth answering.
