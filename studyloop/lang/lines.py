"""Media sources -> lines/<key>.tsv (one row per subtitle line) + media files in media_dir.

Inputs: an existing sentence-mining deck (.apkg from subs2srs, movies2anki, ...). Video +
subtitles and audio + transcript come later (ffmpeg)."""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .apkg import read_export

COLUMNS = ["id", "start", "end", "text", "speaker", "audio", "image", "status"]
_TIME = re.compile(r"(\d+)\.(\d\d)\.(\d\d)[.,](\d{3})-(\d+)\.(\d\d)\.(\d\d)[.,](\d{3})")


@dataclass
class Line:
    id: str
    start: str
    end: str
    text: str
    speaker: str = ""
    audio: str = ""
    image: str = ""
    status: str = ""
    extra: dict = field(default_factory=dict)


def read_lines(p: Path) -> list[Line]:
    with p.open(encoding="utf-8", newline="") as f:
        return [Line(**{k: r.get(k) or "" for k in COLUMNS}) for r in csv.DictReader(f, delimiter="\t")]


def write_lines(p: Path, lines: list[Line]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(COLUMNS)
        for ln in lines:
            w.writerow([getattr(ln, c).replace("\t", " ").replace("\n", " ") for c in COLUMNS])


def _clean(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s or "")
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\s+", " ", s).strip()


def _media_name(fields: dict[str, str], pattern: str) -> str:
    for v in fields.values():
        if m := re.search(pattern, v or ""):
            return m.group(1)
    return ""


def _timing(name: str) -> tuple[str, str]:
    m = _TIME.search(name or "")
    if not m:
        return "", ""
    g = m.groups()
    return f"{int(g[0]):02d}:{g[1]}:{g[2]}.{g[3]}", f"{int(g[4]):02d}:{g[5]}:{g[6]}.{g[7]}"


def split_speakers(text: str, label_re: str) -> list[tuple[str, str]]:
    """'（A）こんばんは （B）どうも' -> [('A', 'こんばんは'), ('B', 'どうも')]. Labels with no text
    after them (sound effects like （笑い）) are dropped."""
    if not label_re:
        return [("", text)]
    parts, speaker, pos = [], "", 0
    for m in re.finditer(label_re, text):
        seg = text[pos:m.start()].strip()
        if seg:
            parts.append((speaker, seg))
        speaker, pos = m.group(0)[1:-1].strip(), m.end()
    seg = text[pos:].strip()
    if seg:
        parts.append((speaker, seg))
    return parts


def import_apkg(export_path: Path, key: str, label_re: str, strip_re: str = "",
                only: str | None = None, from_video: bool = False):
    """Lines (sorted by time, deduplicated by audio clip) and the media file names they use.

    `only`: keep notes whose fields mention it (one episode of a multi-episode deck).
    `from_video`: the clips will be cut from the video, so notes need timings, not media."""
    ex = read_export(export_path)
    seen, rows = set(), []
    for note in ex.notes:
        f = note.fields
        if only and not any(only in (v or "") for v in f.values()):
            continue
        text = _clean(f.get("Expression") or f.get("Sentence") or "")
        if strip_re:
            text = re.sub(strip_re, "", text)
        audio = _media_name(f, r"\[sound:([^\]]+)\]") or (f.get("Audio") or "").strip()
        if not text or "placeholder" in text or not audio or audio in seen:
            continue
        timing = _timing(audio) if _timing(audio)[0] else _timing(" ".join(f.values()))
        if from_video:
            if not timing[0]:
                continue
            audio = Path(audio).stem + ".mp3"
            image = Path(audio).stem + ".jpg"
        elif audio not in ex.media:
            continue
        else:
            image = _media_name(f, r'<img[^>]+src="([^"]+)"')
            image = image if image in ex.media else ""
        seen.add(audio)
        rows.append((timing, text, audio, image))
    rows.sort(key=lambda r: (r[0][0], r[2]))
    lines, media, stats = [], [], {"notes": len(ex.notes), "lines": len(rows), "split": 0,
                                   "rows": rows}
    for i, ((start, end), text, audio, image) in enumerate(rows, 1):
        parts = split_speakers(text, label_re)
        if len(parts) > 1:
            stats["split"] += 1
        for j, (speaker, seg) in enumerate(parts):
            suffix = "abcdefghij"[j] if len(parts) > 1 else ""
            lines.append(Line(f"{key}-{i:04d}{suffix}", start, end, seg, speaker, audio, image,
                              "split:audio-pending" if len(parts) > 1 else ""))
        media += [m for m in (audio, image) if m]
    return lines, media, stats, ex


def _secs(t: str) -> float:
    h, m, sec = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def cut_from_video(video: Path, rows: list, out_dir: Path, pad: tuple[float, float],
                   width: int) -> tuple[int, int]:
    """Audio clip (padded, never far into the neighbouring lines) and a screenshot (mid-line, at
    most `width` px wide) per row, from the original video. Skips files that exist."""
    from concurrent.futures import ThreadPoolExecutor

    from .audio import ffmpeg_exe
    exe = ffmpeg_exe()
    if not exe:
        raise SystemExit("Cutting from video needs ffmpeg: install the `lang` extra (imageio-ffmpeg)")
    out_dir.mkdir(parents=True, exist_ok=True)
    times = [(_secs(s), _secs(e)) for (s, e), *_ in rows]
    jobs = []
    for i, ((start, end), _text, audio, image) in enumerate(rows):
        a, b = times[i]
        prev_end = times[i - 1][1] if i else 0.0
        next_start = times[i + 1][0] if i + 1 < len(times) else b + pad[1]
        a = max(0.0, a - pad[0], min(a, prev_end))                  # not into the previous line
        b = min(b + pad[1], max(b, next_start + 0.1))               # at most 0.1 s of the next
        if not (out_dir / audio).exists():
            jobs.append([exe, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{a:.3f}",
                         "-t", f"{b - a:.3f}", "-i", str(video), "-vn", "-ac", "2",
                         "-c:a", "libmp3lame", "-q:a", "4", str(out_dir / audio)])
        if image and not (out_dir / image).exists():
            mid = (times[i][0] + times[i][1]) / 2
            jobs.append([exe, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{mid:.3f}",
                         "-i", str(video), "-frames:v", "1", "-vf", f"scale='min({width},iw)':-2",
                         "-q:v", "3", str(out_dir / image)])
    import subprocess
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda c: subprocess.run(c, check=True), jobs))
    n_audio = sum(1 for c in jobs if c[-1].endswith(".mp3"))
    return n_audio, len(jobs) - n_audio


def split_audio(lines: list[Line], clips_dir: Path) -> tuple[int, int]:
    """Lines split by speaker get their own clip, cut at the pause between them. Returns
    (split, kept whole). Without ffmpeg nothing changes (status stays split:audio-pending)."""
    from .audio import ffmpeg_exe, split_clip
    exe = ffmpeg_exe()
    groups: dict[str, list[Line]] = {}
    for ln in lines:
        if ln.status.startswith("split:"):
            groups.setdefault(ln.audio, []).append(ln)
    if not exe or not groups:
        return 0, 0
    done = whole = 0
    for audio, parts in groups.items():
        names = split_clip(exe, clips_dir / audio, [ln.text for ln in parts]) \
            if (clips_dir / audio).is_file() else None
        for j, ln in enumerate(parts):
            if names:
                ln.audio, ln.status = names[j], ""
            else:
                ln.status = "split:whole-audio"      # no clear pause: both speakers in the clip
        done += bool(names)
        whole += not names
    return done, whole


def sync_card_audio(deck_dir: Path, audio_of_line: dict[str, str]) -> list[str]:
    """Cards keep the clip of their line (after a re-import cut or re-cut it). Edits only the
    `audio:` line of those cards, keeping the rest of the file as written."""
    import json
    changed = []
    for f in sorted(deck_dir.glob("*.yaml")):
        if f.name == "deck.yaml":
            continue
        text = f.read_text(encoding="utf-8")
        items = re.split(r"(?m)^(?=- )", text)
        for n, it in enumerate(items):
            lm = re.search(r"(?m)^  line: \"?([^\"\s]+)\"?\s*$", it)
            am = re.search(r"(?m)^  audio: .*$", it)
            new = audio_of_line.get(lm.group(1)) if lm else None
            if not (lm and am and new):
                continue
            line = f"  audio: {json.dumps(new, ensure_ascii=False)}"
            if am.group(0) != line:
                items[n] = it.replace(am.group(0), line)
                changed.append((re.search(r"id: (\S+)", it) or lm).group(1))
        if "".join(items) != text:
            f.write_text("".join(items), encoding="utf-8")
    return changed


KEEP = ("card:", "rejected:")      # statuses that must survive a re-import (ids are never reissued)


def add_source(deck_dir: Path, media_dir: Path, inp: Path, key: str, title: str,
               label_re: str, strip_re: str = "", video: Path | None = None,
               only: str | None = None, pad: tuple[float, float] = (0.25, 0.4),
               width: int = 960) -> int:
    from ..config import native_path
    raw_inp, inp = str(inp), native_path(inp)
    if inp.suffix.lower() not in (".apkg", ".colpkg"):
        raise SystemExit(f"{inp}: only .apkg/.colpkg inputs so far (video + subtitles: later)")
    video = native_path(video) if video else None
    if video and not video.is_file():
        raise SystemExit(f"Video not found: {video}")
    if video and only is None:
        only = video.stem                       # one episode of a multi-episode deck
    lines, media, stats, ex = import_apkg(inp, key, label_re, strip_re, only, bool(video))
    if not lines:
        raise SystemExit(f"{inp}: no lines" + (f" mentioning '{only}'" if only else ""))
    out = deck_dir / "lines" / f"{key}.tsv"
    kept = {ln.id: ln.status for ln in read_lines(out) if ln.status.startswith(KEEP)} \
        if out.is_file() else {}
    if video:
        na, ni = cut_from_video(video, stats["rows"], media_dir / key, pad, width)
        n = na + ni
    else:
        n = ex.extract_media(media, media_dir / key) if media else 0
    done, whole = split_audio(lines, media_dir / key)
    for ln in lines:
        if ln.id in kept:
            ln.status = kept[ln.id]
    write_lines(out, lines)
    synced = sync_card_audio(deck_dir, {ln.id: ln.audio for ln in lines})
    (deck_dir / "lines" / f"{key}.yaml").write_text(yaml.safe_dump(
        {"title": title, "key": key, "input": raw_inp, "media": key,
         **({"video": str(video), "only": only, "padding": list(pad)} if video else {}),
         "imported": dt.date.today().isoformat()}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    print(f"{title}: {stats['notes']} notes → {stats['lines']} lines "
          f"({stats['split']} with several speakers, split) → {len(lines)} rows")
    print(f"  {out}" + (f" ({len(kept)} card/rejected statuses kept)" if kept else ""))
    print(f"  media: {n} new files in {media_dir / key}")
    if synced:
        print(f"  cards: audio updated on {', '.join(synced)}")
    if stats["split"]:
        print(f"  audio: {done} clips cut at the pause between speakers, {whole} kept whole"
              if done or whole else "  audio: no ffmpeg found; split lines keep the whole clip "
              "(install the `lang` extra or ffmpeg, then run `asl lang add` again)")
    return 0
