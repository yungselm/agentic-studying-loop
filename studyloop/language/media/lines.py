# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
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

from studyloop.core.anki.reviews import read_export

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
    lines, media, stats = rows_to_lines(rows, key, label_re)
    stats["notes"] = len(ex.notes)
    return lines, media, stats, ex


def rows_to_lines(rows: list, key: str, label_re: str) -> tuple[list[Line], list[str], dict]:
    """(timing, text, audio, image) rows -> lines (sorted by time; speakers split)."""
    rows.sort(key=lambda r: (r[0][0], r[2]))
    lines, media, stats = [], [], {"lines": len(rows), "split": 0, "rows": rows}
    for i, ((start, end), text, audio, image) in enumerate(rows, 1):
        parts = split_speakers(text, label_re)
        if len(parts) > 1:
            stats["split"] += 1
        for j, (speaker, seg) in enumerate(parts):
            suffix = "abcdefghij"[j] if len(parts) > 1 else ""
            lines.append(Line(f"{key}-{i:04d}{suffix}", start, end, seg, speaker, audio, image,
                              "split:audio-pending" if len(parts) > 1 else ""))
        media += [m for m in (audio, image) if m]
    return lines, media, stats


# ---- subtitle files (.srt, .ass) --------------------------------------------------------------

VIDEO = {".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v", ".ts"}
_SRT_TIME = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{1,3})")


def _hms(h, m, s_, frac) -> str:
    return f"{int(h):02d}:{m}:{s_}.{(frac + '00')[:3]}"


def parse_subs(path: Path) -> list[tuple[str, str, str]]:
    """(start, end, text) per cue, times as HH:MM:SS.mmm; tags removed, lines joined."""
    raw = path.read_bytes().decode("utf-8-sig", errors="replace").replace("\r", "")
    out = []
    if path.suffix.lower() in (".ass", ".ssa"):
        for ln in raw.splitlines():
            if not ln.startswith("Dialogue:"):
                continue
            f = ln.split(":", 1)[1].split(",", 9)
            if len(f) < 10:
                continue
            a = re.match(r"(\d+):(\d\d):(\d\d)\.(\d+)", f[1].strip())
            b = re.match(r"(\d+):(\d\d):(\d\d)\.(\d+)", f[2].strip())
            text = re.sub(r"\{[^}]*\}", "", f[9]).replace("\\N", " ").replace("\\n", " ")
            if a and b:
                out.append((_hms(*a.groups()), _hms(*b.groups()), text.strip()))
        return out
    for block in re.split(r"\n\s*\n", raw):
        ls = [x for x in block.split("\n") if x.strip()]
        t = next((i for i, x in enumerate(ls) if "-->" in x), None)
        if t is None:
            continue
        times = _SRT_TIME.findall(ls[t])
        if len(times) < 2:
            continue
        text = " ".join(re.sub(r"<[^>]+>|\{[^}]*\}", "", x).strip() for x in ls[t + 1:])
        out.append((_hms(*times[0]), _hms(*times[1]), text.strip()))
    return out


def find_subs(video: Path, lang: str = "") -> Path | None:
    """`<video>.<lang>.srt/.ass` first, then `<video>.srt/.ass`."""
    tagged = (video.with_suffix(f".{lang}.srt"), video.with_suffix(f".{lang}.ass")) if lang else ()
    for cand in (*tagged, video.with_suffix(".srt"), video.with_suffix(".ass")):
        if cand.is_file():
            return cand
    return None


def _dots(t: str) -> str:
    """00:01:42.880 -> 0.01.42.880 (the clip-name style of subs2srs/movies2anki)."""
    h, m, rest = t.split(":")
    return f"{int(h)}.{m}.{rest}"


def import_subs(video: Path, subs: Path, key: str, label_re: str, strip_re: str = "",
                keep_re: str = "") -> tuple[list[Line], list[str], dict]:
    """A video + its subtitle file: one row per cue whose text matches `keep_re` (e.g. has kana)."""
    rows, dropped = [], 0
    for start, end, text in parse_subs(subs):
        text = re.sub(r"\s+", " ", re.sub(strip_re, "", text) if strip_re else text).strip()
        if not text or (keep_re and not re.search(keep_re, text)):
            dropped += 1
            continue
        stem = f"{video.stem}_{_dots(start)}-{_dots(end)}"
        rows.append(((start, end), text, f"{stem}.mp3", f"{stem}.jpg"))
    lines, media, stats = rows_to_lines(rows, key, label_re)
    stats.update(notes=len(rows) + dropped, dropped=dropped)
    return lines, media, stats


def _secs(t: str) -> float:
    h, m, sec = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def cut_from_video(video: Path, rows: list, out_dir: Path, pad: tuple[float, float],
                   width: int) -> tuple[int, int]:
    """Audio clip (padded, never far into the neighbouring lines) and a screenshot (mid-line, at
    most `width` px wide) per row, from the original video. Skips files that exist."""
    from concurrent.futures import ThreadPoolExecutor

    from studyloop.language.media.audio import ffmpeg_exe
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
    from studyloop.language.media.audio import ffmpeg_exe, split_clip
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


KEEP = ("card:", "rejected:")      # statuses that must survive a re-import (ids are never reissued)


def _match_old_ids(old: list[Line], new: list[Line], tol: float = 0.6) -> dict[str, str]:
    """old line id -> new line id for the same line: start within `tol` seconds (a mined deck may
    have padded its clips) and the same text, else the most similar text (>= 0.6), else the only
    line starting there. Each new line is used once."""
    import difflib

    def norm(t):
        return re.sub(r"[\s、。！？!?…‥・「」『』“”()（）]", "", t)
    starts = [(_secs(ln.start), ln) for ln in new]
    used, out = set(), {}
    for ln in old:
        t = _secs(ln.start)
        near = [n for s_, n in starts if abs(s_ - t) <= tol and n.id not in used]
        if not near:
            continue
        a = norm(ln.text)
        best = max(near, key=lambda n: (norm(n.text) == a, difflib.SequenceMatcher(None, a, norm(n.text)).ratio(),
                                        -abs(_secs(n.start) - t)))
        ratio = difflib.SequenceMatcher(None, a, norm(best.text)).ratio()
        if ratio >= 0.6 or len(near) == 1 and abs(_secs(best.start) - t) <= 0.3:
            out[ln.id] = best.id
            used.add(best.id)
    return out


def add_source(deck_dir: Path, media_dir: Path, inp: Path, key: str, title: str,
               label_re: str, strip_re: str = "", video: Path | None = None,
               only: str | None = None, pad: tuple[float, float] = (0.25, 0.4),
               width: int = 960, subs: Path | None = None, keep_re: str = "", lang: str = "") -> int:
    from studyloop.core.config import native_path
    raw_inp, inp = str(inp), native_path(inp)
    ex = None
    if inp.suffix.lower() in VIDEO:              # a video + its subtitle file
        video = inp
        subs = native_path(subs) if subs else find_subs(video, lang)
        if not subs or not subs.is_file():
            raise SystemExit(f"{video}: no subtitles next to it (.srt/.ass); pass --subs")
        lines, media, stats = import_subs(video, subs, key, label_re, strip_re, keep_re)
    elif inp.suffix.lower() in (".apkg", ".colpkg"):
        video = native_path(video) if video else None
        if video and not video.is_file():
            raise SystemExit(f"Video not found: {video}")
        if video and only is None:
            only = video.stem                       # one episode of a multi-episode deck
        lines, media, stats, ex = import_apkg(inp, key, label_re, strip_re, only, bool(video))
    else:
        raise SystemExit(f"{inp}: give a video (with .srt/.ass next to it) or an .apkg")
    if not lines:
        raise SystemExit(f"{inp}: no lines" + (f" mentioning '{only}'" if only else ""))
    out = deck_dir / "lines" / f"{key}.tsv"
    old = read_lines(out) if out.is_file() else []
    renamed = _match_old_ids(old, lines)        # same line, new id (another input, renumbered)
    lost = [ln for ln in old if ln.status.startswith(KEEP) and ln.id not in renamed]
    if lost:                                    # never hand a card's status to another line
        raise SystemExit(f"{out.name}: {len(lost)} line(s) with a card or a rejection are not in the new "
                         "input; nothing changed:\n" + "\n".join(f"  {ln.id} {ln.status} {ln.start} {ln.text}"
                                                                  for ln in lost[:10]))
    kept = {renamed[ln.id]: ln.status for ln in old if ln.status.startswith(KEEP)}
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
    from studyloop.language.cards.io import edit_cards
    moved = edit_cards(deck_dir, "line", {o: {"line": n} for o, n in renamed.items() if o != n})
    synced = edit_cards(deck_dir, "line", {ln.id: {"audio": ln.audio} for ln in lines if ln.audio})
    (deck_dir / "lines" / f"{key}.yaml").write_text(yaml.safe_dump(
        {"title": title, "key": key, "input": raw_inp, "media": key,
         **({"video": str(video), "only": only, "padding": list(pad)} if video else {}),
         "imported": dt.date.today().isoformat()}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    what = "cues" if ex is None else "notes"
    print(f"{title}: {stats['notes']} {what} → {stats['lines']} lines "
          f"({stats['split']} with several speakers, split) → {len(lines)} rows")
    print(f"  {out}" + (f" ({len(kept)} card/rejected statuses kept)" if kept else ""))
    print(f"  media: {n} new files in {media_dir / key}")
    if stats.get("dropped"):
        print(f"  {stats['dropped']} cues dropped (empty, or not in the language: credits, other subtitles)")
    if moved:
        print(f"  cards: line ids updated on {len(moved)} card(s) (same lines, new numbering)")
    if synced:
        print(f"  cards: audio updated on {', '.join(synced)}")
    if stats["split"]:
        print(f"  audio: {done} clips cut at the pause between speakers, {whole} kept whole"
              if done or whole else "  audio: no ffmpeg found; split lines keep the whole clip "
              "(install the `lang` extra or ffmpeg, then run `asl lang add` again)")
    return 0
