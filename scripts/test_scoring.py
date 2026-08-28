"""
Test the graders against cases whose verdict is known by hand.

The scoring code is the only thing that decides what counts as a correct
answer, which makes it the one component whose bugs are undetectable from its
own output. Every headline figure passes through it. If it miscounts, the
report is confidently wrong and nothing else in the repo disagrees.

So it is graded the same way the system is: fixed inputs, expected verdicts
written down first, and a failure if they disagree.

Run:  .venv\\Scripts\\python.exe scripts\\test_scoring.py
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

failures: list[str] = []


def expect(got, want, label: str) -> None:
    ok = got == want
    print(f"  [{'ok ' if ok else 'FAIL'}]  {label}")
    if not ok:
        print(f"           expected {want!r}, got {got!r}")
        failures.append(label)


# ---------------------------------------------------------------------------
# The grounding rule, lifted from run_full_eval.py so the test exercises the
# same logic rather than a paraphrase of it.
# ---------------------------------------------------------------------------
def grounded(expected_labels: set, expected_sources: set,
             cited_sections: set, cited_sources: set):
    if expected_labels or expected_sources:
        sections_ok = bool(expected_labels & cited_sections) if expected_labels else True
        sources_ok = expected_sources.issubset(cited_sources) if expected_sources else True
        return sections_ok and sources_ok
    return None


def behaved(refused: bool, unanswerable: bool) -> bool:
    return refused if unanswerable else not refused


def main() -> int:
    print("=" * 72)
    print("1. GROUNDING  -  section-based questions")
    print("=" * 72)
    expect(grounded({"Article 99"}, set(), {"Article 99"}, {"EU AI Act"}),
           True, "cites the one required article")
    expect(grounded({"Article 99"}, set(), {"Article 98"}, {"EU AI Act"}),
           False, "cites a neighbouring article instead")
    expect(grounded({"Article 99"}, set(), set(), set()),
           False, "cites nothing")
    expect(grounded({"Article 11", "Annex IV"}, set(), {"Article 11"}, {"EU AI Act"}),
           True, "two required, one cited - grounded means ANY overlap")

    print("\n" + "=" * 72)
    print("2. GROUNDING  -  source-based questions (the ones that were dropped)")
    print("=" * 72)
    # C02/C03/C04: the answer lives in OWASP or NIST, which have no article
    # numbers, so the requirement is stated as a source.
    expect(grounded(set(), {"OWASP"}, {"OWASP LLM01 - Description"}, {"OWASP"}),
           True, "OWASP question citing OWASP")
    expect(grounded(set(), {"OWASP"}, {"Article 99"}, {"EU AI Act"}),
           False, "OWASP question citing only the Act - must NOT pass")
    expect(grounded(set(), {"NIST"}, set(), set()),
           False, "NIST question citing nothing")
    expect(grounded(set(), {"OWASP"}, set(), set()) is None,
           False, "source-only question is scored, not skipped")

    print("\n" + "=" * 72)
    print("3. GROUNDING  -  C01, which needs BOTH the Act and NIST")
    print("=" * 72)
    expect(grounded({"Article 9"}, {"EU AI Act", "NIST"},
                    {"Article 9", "NIST AI 100-1, 1.2"}, {"EU AI Act", "NIST"}),
           True, "cites Article 9 and a NIST section")
    expect(grounded({"Article 9"}, {"EU AI Act", "NIST"},
                    {"Article 9"}, {"EU AI Act"}),
           False, "cites Article 9 but no NIST - the one-sided comparison")
    expect(grounded({"Article 9"}, {"EU AI Act", "NIST"},
                    {"NIST AI 100-1, 1.2"}, {"NIST"}),
           False, "cites NIST but not Article 9")

    print("\n" + "=" * 72)
    print("4. GROUNDING  -  unanswerable questions are excluded, not failed")
    print("=" * 72)
    expect(grounded(set(), set(), set(), set()), None,
           "no requirement stated -> None (excluded from the denominator)")
    expect(grounded(set(), set(), {"Article 99"}, {"EU AI Act"}), None,
           "still None even if something was cited")

    print("\n" + "=" * 72)
    print("5. BEHAVIOUR  -  answered vs refused")
    print("=" * 72)
    expect(behaved(refused=False, unanswerable=False), True, "answered an answerable question")
    expect(behaved(refused=True, unanswerable=False), False, "refused an answerable question")
    expect(behaved(refused=True, unanswerable=True), True, "refused an unanswerable question")
    expect(behaved(refused=False, unanswerable=True), False, "answered an unanswerable question")

    print("\n" + "=" * 72)
    print("6. DENOMINATORS  -  every question is accounted for")
    print("=" * 72)
    import json
    qs = json.loads((ROOT / "data" / "eval" / "questions.json")
                    .read_text(encoding="utf-8"))["questions"]
    answerable = [q for q in qs if q["category"] != "out_of_corpus"]
    scoreable = [q for q in answerable
                 if (q.get("expect_sections") or q.get("expect_sources"))]
    print(f"         total {len(qs)}, answerable {len(answerable)}, "
          f"gradable for grounding {len(scoreable)}")
    expect(len(scoreable), len(answerable),
           "every answerable question is gradable for grounding")

    print("\n" + "=" * 72)
    print("VERDICT")
    print("=" * 72)
    if failures:
        print(f"  {len(failures)} test(s) failed:")
        for f in failures:
            print(f"    - {f}")
        return 1
    print("  The graders agree with every hand-computed verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
