"""
Render docs/carousel.html to a LinkedIn-ready PDF.

The deck used to be produced by opening the HTML and pressing Ctrl+P, which is
not reproducible and quietly depends on whatever the print dialog remembered
last. This drives headless Chrome or Edge instead, so the same input always
gives the same file.

LinkedIn accepts a PDF as a "document post" and renders it as a swipeable
carousel. Page size is set in the HTML (@page 1080x1350, 4:5 portrait) rather
than here, so the on-screen preview and the printed page cannot drift apart.

Run:  .venv\\Scripts\\python.exe scripts\\build_carousel.py
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "carousel.html"
OUT = ROOT / "docs" / "regulatory-retrieval-carousel.pdf"

# Chrome first: its print-to-pdf is the better behaved of the two.
CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str:
    for path in CANDIDATES:
        if pathlib.Path(path).exists():
            return path
    for name in ("chrome", "msedge", "chromium", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit(
        "No Chrome or Edge found. Install one, or open docs/carousel.html and "
        "print to PDF at 1080x1350 with margins set to none."
    )


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"Missing {SRC}")

    browser = find_browser()
    print(f"  browser : {pathlib.Path(browser).name}")
    print(f"  input   : {SRC.relative_to(ROOT)}")

    # A throwaway profile keeps this from touching the real browser profile,
    # and stops a running instance from hijacking the command.
    with tempfile.TemporaryDirectory() as profile:
        result = subprocess.run(
            [
                browser,
                "--headless",
                "--disable-gpu",
                f"--user-data-dir={profile}",
                "--no-pdf-header-footer",
                f"--print-to-pdf={OUT}",
                SRC.as_uri(),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

    if not OUT.exists():
        print(result.stdout, result.stderr, sep="\n")
        raise SystemExit("Browser produced no PDF.")

    size_kb = OUT.stat().st_size / 1024
    print(f"  output  : {OUT.relative_to(ROOT)}  ({size_kb:.0f} KB)")
    print("\n  Post it on LinkedIn as a document, not an image, to get the")
    print("  swipeable carousel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
