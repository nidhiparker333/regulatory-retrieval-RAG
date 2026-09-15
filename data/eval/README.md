# The evaluation artefacts

Every file in this directory is the recorded output of a run, not a document.
They are committed so that the figures in [FINDINGS.md](../../FINDINGS.md) can
be checked against the thing that produced them rather than taken on trust —
`scripts/check_docs.py` reads several of them and fails if the prose and the
data disagree.

**These files are evidence. Editing one by hand falsifies a recorded result.**
To change what is in them, re-run the script that writes them.

## The two question sets

Everything else here is downstream of these two.

| File | What it is |
|---|---|
| `questions.json` | **The tuning set.** 30 questions, 26 answerable and 4 deliberately not. The keys were written from the source documents and committed before the first run, so `git log` shows they cannot have been fitted to the output. The system's settings were chosen by scoring against this set, which makes every figure derived from it in-sample. |
| `holdout.json` | **The held-out set.** 45 questions generated from 203 sections the tuning set never used as a key, 15 per source, seeded and recorded, committed before being run. This exists because keys committed early defend against fitting the *answers* and do nothing about fitting the *settings*. |

## Retrieval results — free to regenerate, no API key

| File | Written by | Read by | What it establishes |
|---|---|---|---|
| `baseline_results.json` | `score_retrieval.py` | `report_scores.py` | Retrieval-only scoring at `k=5`, `k=5 +follow`, `k=10`, `k=10 +follow`. Whether search found the section the key names, with no model involved. |
| `arm_comparison.json` | `compare_arms.py` | `check_docs.py` | The per-step ablation — see *What "arm" means* below. |

## End-to-end results — these cost money to regenerate

| File | Written by | Read by | What it establishes |
|---|---|---|---|
| `full_eval_results.json` | `run_full_eval.py` | `metrics.py`, `grade_blind.py`, `review_answers.py`, `check_docs.py` | All 30 tuning questions answered end to end: the answer, its citations, whether it refused, and the cost. The only artefact here whose regeneration is billed. |
| `correctness.json` | hand-written | `metrics.py`, `review_answers.py`, `check_docs.py` | Per-answer correctness for that run, graded by reading each answer against the source. Grounding is checkable in code; whether an answer is *right* is not, so this is a human judgement and is recorded as one. |
| `holdout_results.json` | `run_holdout.py` | `grade_blind.py`, `check_docs.py` | The held-out set: retrieval, the `k` sweep, the arms, and generation. The `k` sweep here is what showed the in-sample elbow does not exist out of sample. |
| `tuning_graded.json` | `grade_blind.py` | `check_docs.py` | Blind verdicts on the tuning run. |
| `holdout_graded.json` | `grade_blind.py` | `check_docs.py` | Blind verdicts on the held-out run, including the split by whether retrieval found the required section — the result the project rests on. |

Both graded files carry an `_about` block naming which model answered and which
graded, and what the grader was blind to. That block is also how the overlap
disclosed in FINDINGS can be verified: the grader and the held-out question
generator are the same model.

## Variance

| File | Written by | Read by |
|---|---|---|
| `variance_run_1.json` `variance_run_2.json` `variance_run_3.json` | `run_variance.py` | nothing |

Three independent end-to-end runs of the same 30 questions. Generation is
stochastic, so a single run cannot distinguish a real difference between two
configurations from noise; these bound how much moves when nothing changes.
Refusals and uncited answers do not move across the three. Grounding moves by
one question.

Nothing reads them back — `run_variance.py` computes the comparison in process
and prints it. They are here as retained evidence, so the claim about variance
in FINDINGS can be re-derived by someone who does not want to spend the money
re-running it.

## What "arm" means

An *arm* is one variant of the retrieval pipeline, scored on its own, in the
sense the word carries in experimental design. `arm_comparison.json` holds four:

| Arm | Pipeline |
|---|---|
| `search only` | Nearest-neighbour search and nothing else |
| `+ expansion` | Search plus following the cross-references a retrieved passage makes |
| `+ diversity` | Search plus reserving a slot for any source group not represented |
| `+ both (shipped)` | What actually ships |

Scoring each arm separately is what keeps a step in the pipeline honest: a
component stays because it is measurably worth something, not because it sounds
sensible. It is also how hybrid retrieval was found to be losing to the simpler
half of itself, and removed.

## Regenerating any of this

The retrieval-only artefacts need no API key:

```bash
.venv\Scripts\python.exe scripts\score_retrieval.py
```
```bash
.venv\Scripts\python.exe scripts\compare_arms.py
```

The end-to-end artefacts call a model and are billed. `run_holdout.py` is free
unless given `--generate`.

```bash
.venv\Scripts\python.exe scripts\run_full_eval.py
```
```bash
.venv\Scripts\python.exe scripts\run_holdout.py
```
```bash
.venv\Scripts\python.exe scripts\grade_blind.py holdout
```
