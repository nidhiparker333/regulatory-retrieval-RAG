"use client";

import { useEffect, useState } from "react";
import Answer from "@/components/Answer";
import Trace from "@/components/Trace";
import type { AskResult } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API ?? "http://127.0.0.1:8000";

/**
 * Chosen to show range rather than to flatter.
 *
 * One multi-hop question whose answer spans two parts of the Act, one a US
 * reader asks first, one that needs a second document entirely, and one the
 * corpus cannot answer at all. The last is deliberate: a demo showing only
 * successes teaches a visitor nothing about when to trust it.
 */
const STARTERS = [
  { q: "Is my CV screening tool for hiring considered high-risk?", tag: "spans two sections" },
  { q: "Does the EU AI Act apply to a company based in the United States?", tag: "buried mid-article" },
  { q: "What does the Act require for cybersecurity, and what attacks should we defend against?", tag: "needs two documents" },
  { q: "What are the penalties under the Colorado AI Act?", tag: "not in the corpus" },
];

/** Matches the API's own `min_length`, so the server never has to reject one. */
const MIN_QUESTION = 3;

/**
 * Marks a message already written for a reader, so the catch below can tell it
 * apart from whatever the browser threw. Without this a dropped connection
 * surfaces as the raw "Failed to fetch", which tells a visitor nothing.
 */
class ApiError extends Error {}

/**
 * Turn an error response into something worth showing a reader.
 *
 * The API speaks two dialects neither of which belongs on screen: FastAPI
 * validation errors arrive as an array of objects, which stringifies to
 * "[object Object]", and the missing-key error is a message written for a
 * terminal that names a path on the operator's disk. Both are translated here
 * rather than rendered raw.
 */
function readError(status: number, data: unknown): string {
  if (status === 503) {
    return "The answering service has no API key configured, so it cannot generate answers.";
  }
  if (status === 429) {
    return "Rate limit reached — this endpoint spends real money per question. Try again shortly.";
  }

  const detail = (data as { detail?: unknown } | null)?.detail;

  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    return first?.msg
      ? `That question was rejected: ${first.msg}.`
      : "That question was rejected.";
  }

  if (typeof detail === "string" && detail.trim()) {
    // Terminal-formatted messages collapse to a run-on paragraph in HTML, and
    // may name local paths. Keep the first line, and only if it names none.
    const firstLine = detail.trim().split("\n").find((l) => l.trim())?.trim() ?? "";
    if (firstLine && !/[A-Za-z]:\\|\/home\/|\/Users\//.test(firstLine)) return firstLine;
  }

  return `The request failed (${status}).`;
}

export default function Home() {
  const [q, setQ] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [asked, setAsked] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchOnly, setSearchOnly] = useState(false);
  // Read from the API rather than hardcoded, so re-chunking the corpus cannot
  // leave a stale number on screen.
  const [corpusSize, setCorpusSize] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/api/health`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!cancelled && typeof d?.chunks === "number") setCorpusSize(d.chunks);
      })
      .catch(() => {
        /* The count is decoration; its absence must not break the page. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function ask(question: string, retrievalOnly = searchOnly) {
    const trimmed = question.trim();
    if (loading) return;
    setQ(question);
    if (trimmed.length < MIN_QUESTION) {
      setError(`Please write at least ${MIN_QUESTION} characters.`);
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    setAsked(trimmed);
    try {
      const res = await fetch(`${API}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed, retrieval_only: retrievalOnly }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => null);
        throw new ApiError(readError(res.status, d));
      }
      setResult(await res.json());
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : `Could not reach the answering service at ${API}. Is it running?`,
      );
    } finally {
      setLoading(false);
    }
  }

  const tooShort = q.trim().length > 0 && q.trim().length < MIN_QUESTION;

  return (
    <main className="relative min-h-screen overflow-hidden">
      {/* Ambient light. Two slow blooms, well beneath the content. */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="ambient absolute -top-[30%] left-[8%] h-[70vh] w-[70vh] rounded-full bg-[radial-gradient(circle,rgba(240,166,60,0.10),transparent_68%)] blur-3xl" />
        <div
          className="ambient absolute -top-[10%] right-[4%] h-[55vh] w-[55vh] rounded-full bg-[radial-gradient(circle,rgba(79,209,197,0.07),transparent_68%)] blur-3xl"
          style={{ animationDelay: "-17s" }}
        />
      </div>

      <div className="relative mx-auto max-w-6xl px-6 py-16 md:px-10 md:py-24">
        <header className="max-w-2xl">
          <p className="label">AI governance · grounded retrieval</p>
          <h1 className="mt-4 font-display text-[2.6rem] leading-[1.05] tracking-tight text-ink sm:text-[3.4rem]">
            Ask the regulation.
            <br />
            <span className="text-amber">Check the answer.</span>
          </h1>
          <p className="mt-5 max-w-lg text-[14.5px] leading-relaxed text-dim">
            Every answer is built only from the EU AI Act, NIST&apos;s risk
            frameworks and the OWASP LLM Top 10 — and the passages that produced
            it are shown beside it, scores included.
          </p>
        </header>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(q);
          }}
          className="mt-12 max-w-3xl"
        >
          <div className="flex items-stretch gap-2 rounded-lg border border-rule bg-panel/70 p-2 backdrop-blur transition-colors focus-within:border-rulelit">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Ask about obligations, classification, penalties, security…"
              minLength={MIN_QUESTION}
              maxLength={500}
              aria-label="Your question"
              className="min-w-0 flex-1 bg-transparent px-4 py-3 text-[15px] text-ink outline-none placeholder:text-faint"
            />
            <button
              type="submit"
              disabled={loading || q.trim().length < MIN_QUESTION}
              className="shrink-0 rounded-md bg-amber px-6 py-3 text-[13px] font-semibold text-void transition-all hover:bg-amber/90 disabled:cursor-not-allowed disabled:bg-raised disabled:text-faint"
            >
              {loading ? "Thinking…" : searchOnly ? "Search" : "Ask"}
            </button>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            {/*
              Generation costs real money per question; retrieval costs nothing.
              Offering the free path is what makes exploring the corpus sane.
            */}
            <label className="flex cursor-pointer items-center gap-2 text-[12px] text-dim">
              <input
                type="checkbox"
                checked={searchOnly}
                onChange={(e) => setSearchOnly(e.target.checked)}
                className="h-3.5 w-3.5 accent-amber"
              />
              Search only — show the passages, skip the written answer (free)
            </label>
            {tooShort && (
              <span className="text-[11.5px] text-faint">
                At least {MIN_QUESTION} characters.
              </span>
            )}
          </div>

          {/*
            Kept visible after a result. These four are chosen to show range,
            including one the corpus cannot answer, and hiding them after the
            first question made the point exactly once.
          */}
          {/*
            A grid rather than pills. Each starter carries a label saying what
            it demonstrates, and a pill wide enough to hold both wraps into an
            unreadable shape at anything under a wide desktop.
          */}
          {!loading && (
            <div className="mt-5 grid gap-2 sm:grid-cols-2">
              {STARTERS.map((s) => (
                <button
                  key={s.q}
                  type="button"
                  onClick={() => ask(s.q)}
                  className="group rounded-lg border border-rule bg-panel/40 px-4 py-3 text-left transition-colors hover:border-rulelit hover:bg-panel/70"
                >
                  <span className="block text-[12.5px] leading-snug text-dim transition-colors group-hover:text-ink">
                    {s.q}
                  </span>
                  <span className="mt-1.5 block font-mono text-[9.5px] uppercase tracking-[0.14em] text-faint transition-colors group-hover:text-amberdim">
                    {s.tag}
                  </span>
                </button>
              ))}
            </div>
          )}
        </form>

        {error && (
          <p
            role="alert"
            className="mt-8 max-w-3xl rounded border border-rule bg-panel px-4 py-3 text-[13px] text-dim"
          >
            {error}
          </p>
        )}

        {loading && (
          <div className="mt-16 flex items-center gap-3">
            <span className="caret h-1.5 w-1.5 rounded-full bg-amber" />
            <span className="label">
              {corpusSize
                ? `Searching ${corpusSize.toLocaleString()} passages`
                : "Searching the corpus"}
              {searchOnly ? "" : ", then writing from what came back"}
            </span>
          </div>
        )}

        {result && (
          <>
            <p className="mt-16 border-l-2 border-amber/40 pl-4 font-display text-[17px] leading-snug text-dim">
              {asked}
            </p>

            {result.answer ? (
              <div className="mt-10 grid gap-x-14 gap-y-12 lg:grid-cols-[1.15fr_1fr]">
                <div className="min-w-0">
                  <p className="label border-b border-rule pb-3">The answer</p>
                  <div className="mt-7">
                    <Answer result={result} />
                  </div>
                </div>

                <div className="min-w-0">
                  <Trace
                    trace={result.trace}
                    cost={result.cost_usd}
                    elapsed={result.elapsed_ms}
                    corpusSize={corpusSize ?? undefined}
                  />
                </div>
              </div>
            ) : (
              // Search-only: there is no prose half, so the trace takes the
              // page and the passages it found are readable in full.
              <div className="mt-10 max-w-3xl">
                <Trace
                  trace={result.trace}
                  cost={result.cost_usd}
                  elapsed={result.elapsed_ms}
                  corpusSize={corpusSize ?? undefined}
                />
                {result.passages.length > 0 && (
                  <div className="mt-12">
                    <p className="label border-b border-rule pb-3">What it found</p>
                    <div className="mt-6 flex flex-col gap-5">
                      {result.passages.map((p) => (
                        <div key={p.n} className="border-l border-rule pl-4">
                          <div className="flex items-baseline gap-3">
                            <span className="font-mono text-[10px] tabular-nums text-amber">
                              {p.score !== null ? p.score.toFixed(3) : "—"}
                            </span>
                            <span className="label !text-amber">{p.citation}</span>
                          </div>
                          <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
                            {p.text}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        <footer className="mt-28 border-t border-rule pt-6">
          <p className="max-w-3xl text-[11.5px] leading-relaxed text-faint">
            Research project. Not legal advice. Answers are drawn only from the
            documents listed above and are not a substitute for reading them.
            Measured on a fixed 30-question set: 25 of 26 answerable questions
            correct, 4 of 4 unanswerable ones refused.
          </p>
        </footer>
      </div>
    </main>
  );
}
