"use client";

import { useEffect, useMemo, useState } from "react";
import type { AskResult } from "@/lib/types";

/**
 * The reading half.
 *
 * Citation markers in the text are turned into hoverable references that
 * reveal the passage they point at. That is the whole argument of the
 * project made tactile: a claim you can check in one gesture is a different
 * kind of claim from one you cannot.
 *
 * Three properties that argument depends on, each of which had to be fixed:
 *
 *   - The brackets are rendered, not stripped. Selecting an answer and
 *     pasting it has to produce "[1]", not a bare "1" indistinguishable from
 *     a figure in the prose.
 *   - Adjacent markers stay separable. "[1][2][3][7]" was rendering as four
 *     bare digits two pixels apart, which reads as the number 1237.
 *   - A marker that resolves to nothing is shown as inert and reported. The
 *     model can emit [9] when only eight passages were supplied; rendering
 *     that as a live control is worse than not rendering it, because it looks
 *     checkable and is not.
 */
export default function Answer({ result }: { result: AskResult }) {
  // Keyed by the marker's position in the text, NOT by its citation number.
  // The same source is often cited more than once - "[1] ... [1]" - and keying
  // by number meant hovering one opened every marker that shared it, so two
  // tooltips appeared at once over different parts of the sentence.
  const [open, setOpen] = useState<number | null>(null);
  const [shown, setShown] = useState(false);

  // A short beat before the prose arrives, so the trace has begun revealing
  // itself first. The answer should feel like the conclusion of something,
  // not the whole event.
  useEffect(() => {
    setShown(false);
    const t = setTimeout(() => setShown(true), 260);
    return () => clearTimeout(t);
  }, [result]);

  const refused = result.refused;
  const body = useMemo(
    () =>
      refused
        ? (result.answer ?? "").replace(/^NOT IN THE SOURCES\.?\s*/i, "")
        : (result.answer ?? ""),
    [result.answer, refused],
  );

  // Split on [n] so each marker becomes an element rather than literal text.
  const parts = useMemo(() => body.split(/(\[\d+\])/g), [body]);

  // Markers the model wrote that point at no supplied passage. Surfaced for
  // the same reason `uncited` is: a verification failure that nobody notices
  // is indistinguishable from no failure at all.
  const unresolved = useMemo(() => {
    const found = new Set<number>();
    for (const part of parts) {
      const m = part.match(/^\[(\d+)\]$/);
      if (m && !result.passages.some((p) => p.n === Number(m[1]))) {
        found.add(Number(m[1]));
      }
    }
    return [...found].sort((a, b) => a - b);
  }, [parts, result.passages]);

  if (!result.answer) return null;

  return (
    <div
      className={`transition-opacity duration-700 ${shown ? "opacity-100" : "opacity-0"}`}
    >
      {refused && (
        <div className="mb-6 flex items-center gap-3 rounded border border-amber/25 bg-amber/[0.06] px-4 py-3">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber" />
          <p className="text-[13px] text-amber">
            The documents do not answer this. Nothing below is inferred.
          </p>
        </div>
      )}

      <div className="font-display text-[19px] leading-[1.65] text-ink/90 sm:text-[21px]">
        {parts.map((part, i) => {
          const m = part.match(/^\[(\d+)\]$/);
          if (!m) {
            return (
              <span key={i} className="whitespace-pre-wrap">
                {part}
              </span>
            );
          }

          const n = Number(m[1]);
          const passage = result.passages.find((p) => p.n === n);

          // Nothing to show. Render the marker as plain inert text so the
          // reader can still see what the model wrote, but never offer a
          // gesture that leads nowhere.
          if (!passage) {
            return (
              <span
                key={i}
                title="This citation does not match any retrieved passage."
                aria-label={`Citation ${n}, which matches no retrieved passage`}
                className="mx-[2px] inline-block rounded-sm border border-dashed border-faint/50 px-[4px] align-[2px] font-mono text-[10px] text-faint line-through"
              >
                {`[${n}]`}
              </span>
            );
          }

          const isOpen = open === i;
          return (
            <button
              key={i}
              type="button"
              aria-label={`Citation ${n}: ${passage.citation}`}
              aria-expanded={isOpen}
              onMouseEnter={() => setOpen(i)}
              onMouseLeave={() => setOpen(null)}
              onFocus={() => setOpen(i)}
              onBlur={() => setOpen(null)}
              onClick={() => setOpen(isOpen ? null : i)}
              className="relative mx-[2px] inline-block rounded-sm bg-amber/15 px-[4px] align-[2px] font-mono text-[10px] text-amber transition-colors hover:bg-amber/30 focus:outline-none focus-visible:ring-1 focus-visible:ring-amber"
            >
              {/*
                One text node, and the button is inline-block rather than
                inline-flex. Both matter for copying: a flex container turns
                its children into block-level items, so splitting "[", n, "]"
                into separate spans made innerText emit a newline around every
                bracket - "[\n1\n]" - which is worse than the bare digits this
                replaced. Styling the brackets separately is not worth that.
              */}
              {`[${n}]`}
              {isOpen && (
                <span className="absolute bottom-full left-1/2 z-20 mb-2 w-[min(30rem,80vw)] -translate-x-1/2 cursor-default rounded-md border border-rule bg-raised p-4 text-left shadow-[0_24px_60px_-20px_rgba(0,0,0,0.9)]">
                  <span className="label block !text-amber">
                    {passage.citation}
                  </span>
                  <span className="mt-2 block font-sans text-[12.5px] leading-relaxed text-dim">
                    {passage.text.slice(0, 380)}
                    {passage.text.length > 380 && "…"}
                  </span>
                </span>
              )}
            </button>
          );
        })}
      </div>

      {result.uncited && (
        <p className="mt-6 border-l-2 border-amber/50 pl-3 text-[12px] text-amber/80">
          This answer carries no citations and cannot be verified against the
          sources.
        </p>
      )}

      {unresolved.length > 0 && (
        <p className="mt-6 border-l-2 border-amber/50 pl-3 text-[12px] text-amber/80">
          {unresolved.length === 1
            ? `Citation [${unresolved[0]}] points at no retrieved passage and cannot be checked.`
            : `Citations ${unresolved.map((n) => `[${n}]`).join(", ")} point at no retrieved passage and cannot be checked.`}
        </p>
      )}

      {result.citations_used.length > 0 && (
        <div className="mt-8 border-t border-rule pt-4">
          <span className="label">Sources cited</span>
          <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5">
            {result.citations_used.map((c) => (
              <span key={c.n} className="text-[12px] text-dim">
                <span className="font-mono text-[10px] text-amber">[{c.n}]</span>{" "}
                {c.citation}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
