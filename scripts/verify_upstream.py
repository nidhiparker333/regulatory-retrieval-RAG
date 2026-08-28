"""
Re-download the sources and compare them against the committed bytes.

This closes the one gap the other checks cannot reach. verify_sources.py proves
the committed files are unchanged and self-identifying, but both of those hold
just as well for a download that was wrong from the start - a truncated
response, a redirect to a landing page, the wrong language edition. Only
fetching again and comparing answers "did we get the right bytes".

Nothing here writes to data/raw. Downloads go to a temporary directory and are
discarded, so a re-run cannot quietly replace the evidence with whatever the
publisher is serving today.

A difference is NOT automatically a failure. EUR-Lex re-consolidates, NIST
reissues PDFs, OWASP edits its markdown. What matters is knowing, and knowing
what changed - so differences are reported in detail and the exit code
distinguishes "unreachable" from "changed".

Run:  .venv\\Scripts\\python.exe scripts\\verify_upstream.py
"""

import difflib
import hashlib
import json
import pathlib
import re
import sys
import tempfile

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

HEADERS = {"User-Agent": "regulatory-retrieval/0.1 (research; verification re-fetch)"}

SOURCES = [
    ("eu_ai_act.html",
     "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX%3A02024R1689-20260727"),
    ("nist_ai_100_1.pdf", "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf"),
    ("nist_ai_600_1.pdf", "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf"),
]
OWASP_API = ("https://api.github.com/repos/"
             "GenAI-Security-Project/GenAI-LLM-Top10/contents/2026/final")

identical: list[str] = []
changed: list[tuple[str, str]] = []
unreachable: list[tuple[str, str]] = []


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def describe_text_diff(old: bytes, new: bytes, label: str) -> str:
    """For text sources, say what actually moved rather than just 'differs'."""
    try:
        o = old.decode("utf-8", "replace").splitlines()
        n = new.decode("utf-8", "replace").splitlines()
    except Exception:
        return "binary difference"
    sm = difflib.SequenceMatcher(None, o, n, autojunk=False)
    ratio = sm.quick_ratio()
    adds = dels = 0
    samples: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            dels += i2 - i1
        if tag in ("replace", "insert"):
            adds += j2 - j1
        if tag != "equal" and len(samples) < 3:
            src = (n[j1:j2] or o[i1:i2])[:1]
            if src:
                samples.append(f"{tag}: {re.sub(r'\\s+', ' ', src[0])[:90]}")
    out = [f"line similarity {ratio:.4f}; +{adds} / -{dels} lines"]
    out += [f"      {s}" for s in samples]
    return "\n".join(out)


def legal_text(raw: bytes) -> str | None:
    """
    The substance of the AI Act page, with presentation stripped out.

    EUR-Lex serves a Dynatrace analytics tag whose session id changes between
    deployments, so the HTML differs by a byte or two on essentially every
    fetch while the Regulation itself is untouched. Comparing raw bytes alone
    would therefore report a difference forever, and a check that always fires
    is one you stop reading.

    Comparing only the article and annex containers answers the question that
    actually matters: has the law changed?
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    parts = [re.sub(r"\s+", " ", el.get_text(" ", strip=True))
             for el in soup.select('div.eli-subdivision, div[id^="anx_"]')]
    return "\n".join(parts) if parts else None


def compare(name: str, local: pathlib.Path, url: str, tmp: pathlib.Path) -> None:
    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=180) as r:
            r.raise_for_status()
            fresh = tmp / name
            fresh.parent.mkdir(parents=True, exist_ok=True)
            with open(fresh, "wb") as f:
                for block in r.iter_content(64 * 1024):
                    f.write(block)
    except Exception as e:
        print(f"  [ -- ]  {name:<34} unreachable: {type(e).__name__}: {str(e)[:70]}")
        unreachable.append((name, str(e)))
        return

    old = local.read_bytes()
    new = fresh.read_bytes()
    if sha(old) == sha(new):
        print(f"  [ ok ]  {name:<34} identical ({len(new):,} bytes)")
        identical.append(name)
        return

    # Bytes differ. For the Act, ask whether the *law* differs before calling
    # it a change: the page carries a rotating analytics id that has nothing
    # to do with the Regulation.
    if name.endswith(".html"):
        old_substance, new_substance = legal_text(old), legal_text(new)
        if old_substance and old_substance == new_substance:
            print(f"  [ ok ]  {name:<34} legal text identical "
                  f"({len(new) - len(old):+d} B of presentation only)")
            identical.append(name)
            return

    print(f"  [DIFF]  {name:<34} committed {len(old):,} B / upstream {len(new):,} B")
    detail = (describe_text_diff(old, new, name)
              if name.endswith((".html", ".md"))
              else f"binary; {len(new) - len(old):+,} bytes")
    for line in detail.splitlines():
        print(f"          {line}")
    changed.append((name, detail.splitlines()[0]))


def main() -> int:
    print(f"Comparing {RAW} against upstream\n")
    with tempfile.TemporaryDirectory(prefix="upstream-check-") as td:
        tmp = pathlib.Path(td)

        for name, url in SOURCES:
            compare(name, RAW / name, url, tmp)

        print()
        try:
            listing = requests.get(OWASP_API, headers=HEADERS, timeout=60)
            listing.raise_for_status()
            entries = [e for e in listing.json()
                       if e["type"] == "file" and e["name"].endswith(".md")]
        except Exception as e:
            print(f"  [ -- ]  OWASP listing unreachable: {type(e).__name__}: {str(e)[:70]}")
            unreachable.append(("owasp listing", str(e)))
            entries = []

        local_owasp = {p.name for p in (RAW / "owasp").glob("*.md")}
        remote_owasp = {e["name"] for e in entries}
        if entries:
            only_local = sorted(local_owasp - remote_owasp)
            only_remote = sorted(remote_owasp - local_owasp)
            if only_local:
                print(f"  [DIFF]  files no longer upstream: {only_local}")
                changed.append(("owasp", f"removed upstream: {only_local}"))
            if only_remote:
                print(f"  [DIFF]  new files upstream: {only_remote}")
                changed.append(("owasp", f"added upstream: {only_remote}"))
            for e in sorted(entries, key=lambda x: x["name"]):
                if e["name"] in local_owasp:
                    compare(f"owasp/{e['name']}", RAW / "owasp" / e["name"],
                            e["download_url"], tmp)

    print("\n" + "=" * 72)
    print("VERDICT")
    print("=" * 72)
    print(f"  identical to upstream : {len(identical)}")
    print(f"  differing             : {len(changed)}")
    print(f"  unreachable           : {len(unreachable)}")

    if changed:
        print("\n  Differences are not automatically errors - publishers revise.")
        print("  Decide deliberately whether to re-fetch and re-measure:")
        for name, why in changed:
            print(f"    - {name}: {why}")
        return 2
    if unreachable:
        print("\n  Some sources could not be reached; this run proves nothing "
              "about them.")
        return 1
    print("\n  Every source matches what the publisher serves today: binaries and")
    print("  markdown byte-for-byte, the Act by its article and annex text (its")
    print("  page carries a rotating analytics id that is not part of the law).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
