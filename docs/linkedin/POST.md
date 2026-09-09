# LinkedIn post copy

Accompanies `docs/regulatory-retrieval-carousel.pdf`, uploaded as a **document
post** (not an image) so it renders as a swipeable carousel.

Mechanics worth knowing before editing:

- Roughly the first 200 characters show before "…see more". The opening two
  sentences have to carry the post on their own.
- LinkedIn strips markdown. Bold, italics and bullets will not render — the line
  breaks below are doing all the structural work, so keep them.
- The document's own title (set at upload) appears on the carousel. Suggested:
  **What it takes to make RAG work on regulation**

---

## Post

A retrieval system will answer any question you put to it. Fluently, and with a
citation. That is not evidence it worked.

I built a question-answering system over four AI-governance documents — the EU AI
Act, two NIST frameworks, and the OWASP LLM Top 10 — where every claim carries a
citation to the article, annex or page it came from, and the system declines when
the documents cannot answer.

Building it was the tractable half.

Two things turned out to matter more than the retrieval itself.

The first: some provisions are split across sections. Annex III lists CV
screening as high-risk. Article 6 states the conditions under which that listing
applies. Neither is sufficient alone — and retrieving more passages does not
surface the second, because it isn't semantically near the question. It's
referenced by the first. So cross-references are extracted when the documents are
parsed, and followed at query time. No agent, no second model call, and no
capacity to invent a link that isn't in the text.

The second: knowing when to stop. Similarity search always returns its nearest
passages, however far away they are. Measured on this corpus, retrieval
confidence could not separate answerable questions from unanswerable ones. So
abstention is enforced at generation, against the retrieved text, rather than by
thresholding a score.

Then the part I got wrong.

I had selected the retrieval parameters by scoring against the same question set
I was using to report results. Every figure was in-sample. So I wrote a second
set from sections the first had never touched, committed the answers before
running anything, and had a different model grade both — blind to how the answers
were produced.

Scores fell. The independent grader also surfaced a defect in my own refusal
detection that self-review had not.

That is the part I would keep if I built it again. Not the retrieval design — the
evaluation, and the assumption that my review of my own system was worth less
than I thought it was.

Method, figures, and the failures that remain — including one question it has
never been able to retrieve — are in the repository.

github.com/nidhiparker333/regulatory-retrieval-RAG

---

## Notes on what this deliberately does not do

- **No figures.** Every number lives in the repository. A post that leads with
  scores invites the reader to evaluate the scores; this one invites them to
  evaluate the method, which is the stronger ground.
- **No "excited to share".** The opening is a claim about retrieval systems in
  general, not an announcement.
- **The flaw is the pivot, not a disclaimer at the end.** Burying it would read
  as marketing; leading with it too early would read as self-deprecation. It sits
  where the turn belongs.
- **Hashtags omitted.** Add two or three if you want reach — `#RAG`,
  `#AIGovernance`, `#MachineLearning` — but they cost nothing to leave off and
  they date the post.
