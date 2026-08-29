"""
Step 1 of the pipeline: get the four source documents onto disk.

There is no AI in this file. We are downloading four things and saving them.
That is genuinely most of what "building an AI system" involves.

Everything lands in data/raw/ exactly as the publisher wrote it. We never edit
these files afterwards — later steps read from here and write cleaned copies
elsewhere. That way, if we make a mistake cleaning, we can always start over
without downloading again.

Run:  .venv\\Scripts\\python.exe scripts\\fetch.py
"""

import json
import pathlib
import sys

import requests

# Where things go. `parents[1]` means "one folder up from scripts/".
ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

# Some servers reject requests that don't look like a browser.
HEADERS = {
    "User-Agent": "governance-rag/0.1 (research project; contact via github)"
}

# The four sources. `id` becomes the filename, so keep them short and stable.
SOURCES = [
    {
        "id": "eu_ai_act",
        "name": "EU AI Act (consolidated, 27 July 2026)",
        # CELEX 02024R1689-20260727 is the *consolidated* text: the original
        # 2024 regulation with the July 2026 amendment already folded in.
        # The un-consolidated version is a different, now-outdated document.
        "url": (
            "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/"
            "?uri=CELEX%3A02024R1689-20260727"
        ),
        "ext": "html",
    },
    {
        "id": "nist_ai_100_1",
        "name": "NIST AI RMF 1.0",
        "url": "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf",
        "ext": "pdf",
    },
    {
        "id": "nist_ai_600_1",
        "name": "NIST Generative AI Profile",
        "url": "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf",
        "ext": "pdf",
    },
]


def human(size_bytes: int) -> str:
    """1234567 -> '1.2 MB'. Only for printing."""
    mb = size_bytes / 1_000_000
    return f"{mb:.1f} MB" if mb >= 1 else f"{size_bytes / 1000:.0f} KB"


def download(url: str, dest: pathlib.Path) -> int:
    """Fetch one URL to one file. Returns bytes written."""
    # stream=True downloads in pieces instead of holding it all in memory.
    # The AI Act is large enough that this matters.
    with requests.get(url, headers=HEADERS, stream=True, timeout=120) as r:
        r.raise_for_status()  # turns a 404 into a crash instead of saving "Not Found"
        dest.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                f.write(chunk)
                written += len(chunk)
    return written


def fetch_owasp() -> list[dict]:
    """
    OWASP is a folder of markdown files on GitHub, not a single download.

    We ask GitHub's API what's in the folder rather than guessing filenames —
    guessed filenames break silently the moment the repo is reorganised, and
    this repo was reorganised three weeks ago.
    """
    api = (
        "https://api.github.com/repos/"
        "GenAI-Security-Project/GenAI-LLM-Top10/contents/2026/final"
    )
    r = requests.get(api, headers=HEADERS, timeout=60)
    if r.status_code != 200:
        print(f"  ! GitHub API returned {r.status_code} - skipping OWASP for now")
        print(f"    ({r.text[:120]})")
        return []

    listing = r.json()
    saved = []
    for entry in listing:
        if entry["type"] != "file" or not entry["name"].endswith(".md"):
            continue
        dest = RAW / "owasp" / entry["name"]
        size = download(entry["download_url"], dest)
        saved.append({"file": entry["name"], "bytes": size})
        print(f"    - {entry['name']:<44} {human(size)}")
    return saved


def main() -> int:
    print(f"Saving into {RAW}\n")
    manifest = []

    for src in SOURCES:
        dest = RAW / f"{src['id']}.{src['ext']}"
        print(f"  {src['name']}")
        try:
            size = download(src["url"], dest)
        except Exception as e:
            print(f"    ! FAILED: {e}\n")
            manifest.append({**src, "ok": False, "error": str(e)})
            continue
        print(f"    -> {dest.name}  {human(size)}\n")
        manifest.append({**src, "ok": True, "bytes": size, "path": str(dest)})

    print("  OWASP LLM Top 10 (2026)")
    owasp_files = fetch_owasp()
    manifest.append({
        "id": "owasp_llm_top10",
        "name": "OWASP LLM Top 10 (2026)",
        "ok": bool(owasp_files),
        "files": owasp_files,
    })

    # A manifest records what we actually got, when. Later steps read this
    # instead of assuming files exist, and it's the start of being able to say
    # "these results came from these exact documents".
    (RAW / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    failures = [m for m in manifest if not m.get("ok")]
    print(f"\nDone. {len(manifest) - len(failures)}/{len(manifest)} sources OK.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
