"""
Render docs/linkedin/scene.html to an MP4 and a GIF for LinkedIn.

scene.html draws its whole 14-second timeline from a single render(t) call and
accepts the time as a query parameter, so a frame is just a screenshot of
?t=<seconds>. That makes the render deterministic: the same HTML always gives
the same frames, which a screen recording never would.

Headless Chrome takes the frames, ffmpeg assembles them. Both were already on
this machine; nothing else is needed.

  .venv\\Scripts\\python.exe scripts\\build_scene.py            # mp4 + gif
  .venv\\Scripts\\python.exe scripts\\build_scene.py --mp4-only # skip the gif
  .venv\\Scripts\\python.exe scripts\\build_scene.py --fps 24

LinkedIn takes the MP4 directly and autoplays it muted in the feed. The GIF is
a fallback for places that will not take video; it is several times the size for
worse quality, so prefer the MP4.
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "docs" / "linkedin"

WIDTH, HEIGHT = 1080, 1350
DEFAULT_FPS = 24         # 24 keeps the frame count sane; the motion is slow

CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find(paths: list[str], names: tuple[str, ...], what: str) -> str:
    for p in paths:
        if pathlib.Path(p).exists():
            return p
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    raise SystemExit(f"Could not find {what}.")


def main() -> int:
    argv = sys.argv[1:]

    def opt(flag, default):
        return argv[argv.index(flag) + 1] if flag in argv else default

    scene = ROOT / opt("--scene", "docs/linkedin/reel.html")
    stem = opt("--stem", scene.stem)
    duration = float(opt("--duration", "29.3"))
    fps = int(opt("--fps", DEFAULT_FPS))
    gif = "--mp4-only" not in argv

    global SCENE, STEM, DURATION
    SCENE, STEM, DURATION = scene, stem, duration

    browser = find(CHROME, ("chrome", "msedge", "chromium"), "Chrome or Edge")
    ffmpeg = find([], ("ffmpeg",), "ffmpeg (install it, or use winget)")

    frames = int(DURATION * fps)
    print(f"  scene   : {SCENE.relative_to(ROOT)}")
    print(f"  frames  : {frames} at {fps} fps ({DURATION:g}s, {WIDTH}x{HEIGHT})")
    print(f"  browser : {pathlib.Path(browser).name}\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        shots = tmpdir / "frames"
        shots.mkdir()
        profile = tmpdir / "profile"

        for i in range(frames):
            t = i / fps
            out = shots / f"f{i:05d}.png"
            subprocess.run(
                [
                    browser,
                    "--headless",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    f"--user-data-dir={profile}",
                    f"--window-size={WIDTH},{HEIGHT}",
                    f"--screenshot={out}",
                    f"{SCENE.as_uri()}?t={t:.4f}",
                ],
                capture_output=True,
                timeout=120,
            )
            if not out.exists():
                raise SystemExit(f"Frame {i} failed to render.")
            if i % 30 == 0 or i == frames - 1:
                print(f"\r  captured {i + 1}/{frames}", end="", flush=True)
        print()

        pattern = str(shots / "f%05d.png")
        mp4 = OUTDIR / f"{STEM}.mp4"

        # yuv420p and even dimensions: without both, the file plays on a desktop
        # and silently fails on some mobile clients.
        subprocess.run(
            [
                ffmpeg, "-v", "error", "-y",
                "-framerate", str(fps), "-i", pattern,
                "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-movflags", "+faststart",
                str(mp4),
            ],
            check=True,
        )
        print(f"  wrote   : {mp4.relative_to(ROOT)}  ({mp4.stat().st_size / 1024:.0f} KB)")

        # A poster frame, for anywhere the video will not play.
        png = OUTDIR / f"{STEM}.png"
        shutil.copyfile(shots / "f00000.png", png)
        print(f"  wrote   : {png.relative_to(ROOT)}  ({png.stat().st_size / 1024:.0f} KB)")

        if gif:
            # Two passes: a palette built from the whole clip, then the encode.
            # A single pass quantises per frame and the flat background crawls.
            palette = tmpdir / "palette.png"
            subprocess.run(
                [ffmpeg, "-v", "error", "-y", "-framerate", str(fps), "-i", pattern,
                 "-vf", "fps=15,scale=720:-1:flags=lanczos,palettegen=stats_mode=diff",
                 str(palette)],
                check=True,
            )
            gif_path = OUTDIR / f"{STEM}.gif"
            subprocess.run(
                [ffmpeg, "-v", "error", "-y", "-framerate", str(fps), "-i", pattern,
                 "-i", str(palette),
                 "-lavfi", "fps=15,scale=720:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
                 "-loop", "0", str(gif_path)],
                check=True,
            )
            print(f"  wrote   : {gif_path.relative_to(ROOT)}  ({gif_path.stat().st_size / 1024:.0f} KB)")

    print("\n  Post the MP4 on LinkedIn. It autoplays muted in the feed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
