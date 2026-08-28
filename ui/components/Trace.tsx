"use client";

import type { TraceStep } from "@/lib/types";

/**
 * The instrument panel.
 *
 * This is the half of the interface that matters. An answer alone asks to be
 * trusted; an answer next to the passages that produced it, with their scores,
 * can be checked. Weak scores and irrelevant hits are shown exactly as they
 * came back - hiding them would defeat the purpose.
 *
 * Steps rise in sequence rather than appearing at once, so the pipeline reads
 * as a sequence of decisions rather than a single opaque event.
 */

const STEP_TITLES: Record<string, string> = {
  search: "Searched the corpus",
  source_diversity: "Gave the other source a voice",
  anchor_expansion: "Pulled in the article's opening",
  follow_cross_references: "Followed cross-references",
  generate: "Wrote the answer",
};

/**
 * The why-line for each step, in the interface's own voice rather than the
 * API's. `search` is a function because the one number worth keeping from the
 * server's `detail` string is how many passages were compared - stating it
 * here means the count is never a literal in this file, and never goes stale
 * when the corpus is re-chunked.
 */
const STEP_WHY: Record<string, (corpusSize?: number) => string> = {
  search: (n) =>
    n
      ? `All ${n.toLocaleString()} passages compared by meaning, not keywords`
      : "Every passage compared by meaning, not keywords",
  source_diversity: () =>
    "One document was winning every slot. The others get their best passage",
  anchor_expansion: () =>
    "Landed mid-article. In legislation the general rule sits in paragraph 1",
  follow_cross_references: () =>
    "These passages cite others. The citation is followed, not guessed",
  generate: () =>
    "Constrained to the passages above, with a citation on every claim",
};

const SOURCE_LABEL: Record<string, string> = {
  "EU AI Act": "ACT",
  NIST: "NIST",
  OWASP: "OWASP",
};

function ScoreRow({
  citation,
  score,
  source,
  delay,
}: {
  citation: string;
  score?: number;
  source?: string;
  delay: number;
}) {
  // Scores cluster in a narrow band, so the bar is stretched across the range
  // that actually occurs rather than 0-1, where every bar would look identical.
  const pct =
    score !== undefined && score !== null
      ? Math.max(0.04, Math.min(1, (score - 0.55) / 0.4))
      : 0;
  const isAct = source === "EU AI Act";

  return (
    <div className="rise group" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex items-baseline gap-3 py-[5px]">
        <span
          className={`w-11 shrink-0 font-mono text-[11px] tabular-nums ${
            score !== undefined && score !== null ? "text-amber" : "text-faint"
          }`}
        >
          {score !== undefined && score !== null ? score.toFixed(3) : "—"}
        </span>
        <span className="flex-1 truncate text-[12.5px] text-dim transition-colors group-hover:text-ink">
          {citation}
        </span>
        {source && (
          <span
            className={`label shrink-0 !text-[9px] ${isAct ? "!text-amberdim" : ""}`}
          >
            {SOURCE_LABEL[source] ?? source}
          </span>
        )}
      </div>
      {score !== undefined && score !== null && (
        <div className="h-px w-full overflow-hidden bg-rule">
          <div
            className="bar h-px bg-amber/50"
            style={{ width: `${pct * 100}%`, animationDelay: `${delay + 120}ms` }}
          />
        </div>
      )}
    </div>
  );
}

export default function Trace({
  trace,
  cost,
  elapsed,
  corpusSize,
}: {
  trace: TraceStep[];
  cost: number;
  elapsed: number;
  corpusSize?: number;
}) {
  let delay = 0;
  const passages = trace.reduce((n, s) => n + (s.results?.length ?? 0), 0);

  return (
    <div className="flex flex-col gap-7">
      <div className="flex items-baseline justify-between border-b border-rule pb-3">
        <span className="label">How it answered</span>
        <span className="font-mono text-[10.5px] tabular-nums text-faint">
          {passages} passages · {(elapsed / 1000).toFixed(1)}s · $
          {cost.toFixed(4)}
        </span>
      </div>

      {trace.map((step, i) => {
        const stepDelay = delay;
        delay += 220;

        return (
          <section
            key={i}
            className="step-thread rise relative"
            style={{ animationDelay: `${stepDelay}ms` }}
          >
            <div className="flex items-baseline gap-2.5">
              <span className="font-mono text-[10px] tabular-nums text-amber/70">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="text-[13px] font-medium text-ink">
                {STEP_TITLES[step.step] ?? step.step}
              </h3>
              {step.ms !== undefined && (
                <span className="ml-auto font-mono text-[10px] tabular-nums text-faint">
                  {step.ms < 1000
                    ? `${Math.round(step.ms)}ms`
                    : `${(step.ms / 1000).toFixed(1)}s`}
                </span>
              )}
            </div>

            <p className="mt-1 pl-[26px] text-[11.5px] leading-relaxed text-faint">
              {STEP_WHY[step.step]?.(corpusSize) ?? step.detail}
            </p>

            {step.results && step.results.length > 0 && (
              <div className="mt-3 flex flex-col pl-[26px]">
                {step.results.map((r, j) => {
                  const d = delay;
                  delay += 70;
                  return (
                    <ScoreRow
                      key={j}
                      citation={r.citation}
                      score={r.score}
                      source={r.source}
                      delay={d}
                    />
                  );
                })}
              </div>
            )}

            {step.step === "generate" && step.tokens_in !== undefined && (
              <div className="mt-3 flex gap-5 pl-[26px] font-mono text-[10px] tabular-nums text-faint">
                <span>{step.tokens_in.toLocaleString()} tokens in</span>
                <span>{step.tokens_out?.toLocaleString()} out</span>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
