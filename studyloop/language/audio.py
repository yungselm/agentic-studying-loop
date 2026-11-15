"""Audio with ffmpeg: split a clip where two speakers alternate.

ffmpeg comes from PATH, else from `imageio-ffmpeg` (part of the `lang` extra: a bundled binary
for Windows, macOS and Linux). TV audio has music under the speech, so pauses are found as the
quietest stretch near the expected cut (by the text's character share), not by a fixed level."""
from __future__ import annotations

import array
import shutil
import subprocess
from pathlib import Path

RATE = 8000                # Hz, mono: enough to find pauses
WIN = 0.02                 # s, loudness window
SMOOTH = 5                 # windows (100 ms) averaged
SEARCH = 0.25              # look for the pause within ±25% of the clip around the expected cut
QUIET = 0.5                # the pause must be below half the clip's median loudness
MIN_SHARE = 0.5            # each part keeps >= half the time its share of the text predicts


def ffmpeg_exe() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def loudness(exe: str, clip: Path) -> list[float]:
    raw = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-i", str(clip),
                          "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    pcm = array.array("h")
    pcm.frombytes(raw[: len(raw) // 2 * 2])
    n = int(RATE * WIN)
    rms = [(sum(x * x for x in pcm[i:i + n]) / n) ** 0.5 for i in range(0, len(pcm) - n + 1, n)]
    half = SMOOTH // 2
    return [sum(rms[max(0, i - half):i + half + 1]) / len(rms[max(0, i - half):i + half + 1])
            for i in range(len(rms))]


def cut_points(levels: list[float], shares: list[float]) -> list[tuple[float, float]] | None:
    """Per boundary between two speakers: (end of the part before, start of the part after), in
    seconds, both inside the pause so neither speaker is clipped. None when there is no clear
    pause or a part would be implausibly short for its text (overlapping speakers)."""
    if not levels:
        return None
    n, median = len(levels), sorted(levels)[len(levels) // 2]
    bounds = [0.0, *shares, 1.0]
    out, lo = [], 0
    for b, share in enumerate(shares, 1):
        mid = int(share * n)
        min_before = int(MIN_SHARE * (bounds[b] - bounds[b - 1]) * n)
        min_after = int(MIN_SHARE * (bounds[b + 1] - bounds[b]) * n)
        a = max(lo + min_before, mid - int(SEARCH * n), 1)
        z = min(n - 1 - min_after, mid + int(SEARCH * n))
        if a >= z:
            return None
        i = min(range(a, z), key=lambda k: (levels[k], abs(k - mid)))
        if levels[i] > QUIET * median:
            return None
        edge = levels[i] + 0.25 * (median - levels[i])   # the pause: windows near its floor
        left, right = i, i
        while left > lo and levels[left - 1] <= edge:
            left -= 1
        while right < n - 1 and levels[right + 1] <= edge:
            right += 1
        out.append(((right + 1) * WIN, left * WIN))
        lo = right
    return out


def cut(exe: str, src: Path, dst: Path, start: float, end: float | None) -> None:
    cmd = [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-ss", f"{start:.3f}"]
    if end is not None:
        cmd += ["-to", f"{end:.3f}"]
    subprocess.run(cmd + ["-c:a", "libmp3lame", "-q:a", "4", str(dst)], check=True)


def split_clip(exe: str, clip: Path, texts: list[str]) -> list[str] | None:
    """Cut `clip` into one file per text part (`<stem>_a.mp3`, ...); file names, or None."""
    lengths = [max(1, len(t)) for t in texts]
    total, acc, shares = sum(lengths), 0, []
    for n in lengths[:-1]:
        acc += n
        shares.append(acc / total)
    try:
        points = cut_points(loudness(exe, clip), shares)
    except (subprocess.CalledProcessError, OSError):
        return None                      # unreadable clip: keep it whole
    if points is None:
        return None
    starts = [0.0, *(b for _, b in points)]
    ends = [*(a for a, _ in points), None]
    names = []
    for j in range(len(texts)):
        name = f"{clip.stem}_{'abcdefghij'[j]}{clip.suffix}"
        cut(exe, clip, clip.parent / name, starts[j], ends[j])       # always: rules may change
        names.append(name)
    return names
