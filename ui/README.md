# UI

The reading half of [regulatory-retrieval](../README.md): an answer set beside
the retrieval that produced it.

The layout is the argument. An answer alone asks to be trusted; an answer with
its passages, their scores, and the steps that found them can be checked. So the
prose is set in a serif and the trace in mono, and neither is hidden behind a
toggle.

Amber means one thing throughout: **this is evidence**. It marks scores,
citations, and the passages a claim rests on, and nothing else — so anything
amber is worth looking at.

## It needs the API running

This is a client. It has no corpus, no index and no model — every question goes
to the FastAPI server in [`../api`](../api), and the passage count in the loading
line is read from `/api/health` rather than hardcoded.

From the repository root:

```bash
.venv\Scripts\python.exe -m uvicorn api.server:app --port 8000
```

Then, in a second terminal:

```bash
npm install && npm run dev
```

If the API is down, asking a question says so rather than failing silently.

## Costs

Generating an answer calls a model and costs roughly **$0.02** a question.

**Search only** on the form skips generation entirely and costs nothing. It
returns the passages, their scores and the full trace — enough to explore the
corpus, and the right default when you are looking around rather than reading an
answer.

Without a key the API still serves retrieval, and the UI says so instead of
showing a server error.

## Pointing at a different API

`NEXT_PUBLIC_API` overrides the default `http://127.0.0.1:8000`:

```bash
NEXT_PUBLIC_API=http://192.168.1.10:8000 npm run dev
```

If that API is on a reachable interface, set `API_TOKEN` and `ASK_RATE_LIMIT` on
it. CORS does not protect it — a script ignores CORS entirely.

## What the components do

| File | Job |
|---|---|
| `app/page.tsx` | Form, question state, error translation, search-only mode |
| `components/Answer.tsx` | The prose, with citation markers that reveal their passage |
| `components/Trace.tsx` | The instrument panel — steps, scores, timings, cost |
| `lib/types.ts` | The API response contract |

### Citations are the point, so they are handled carefully

- Brackets are **rendered, not stripped**, so copying an answer keeps `[1]`
  rather than a bare `1` indistinguishable from a figure in the sentence.
- Adjacent markers stay separable. `[1][2][3]` as bare digits two pixels apart
  reads as the number 123.
- Tooltips are keyed by a marker's **position**, not its citation number. The
  same source is usually cited more than once, and keying by number opened every
  marker sharing it — two tooltips at once, over different parts of a sentence.
- A marker pointing at no supplied passage is drawn **inert and struck through**,
  and reported under the answer. A model can write `[9]` when eight passages were
  supplied; rendering that as a live control is worse than not rendering it,
  because it looks checkable and is not.
