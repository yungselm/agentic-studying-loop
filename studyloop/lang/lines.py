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


def import_apkg(export_path: Path, key: str, label_re: str, strip_re: str = ""):
    """Lines (sorted by time, deduplicated by audio clip) and the media file names they use."""
    ex = read_export(export_path)
    seen, rows = set(), []
    for note in ex.notes:
        f = note.fields
        text = _clean(f.get("Expression") or f.get("Sentence") or "")
        if strip_re:
            text = re.sub(strip_re, "", text)
        audio = _media_name(f, r"\[sound:([^\]]+)\]") or (f.get("Audio") or "").strip()
        if not text or "placeholder" in text or not audio or audio in seen:
            continue
        if audio not in ex.media:
            continue
        seen.add(audio)
        image = _media_name(f, r'<img[^>]+src="([^"]+)"')
        rows.append((_timing(audio), text, audio, image if image in ex.media else ""))
    rows.sort(key=lambda r: (r[0][0], r[2]))
    lines, media, stats = [], [], {"notes": len(ex.notes), "lines": len(rows), "split": 0}
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


def add_source(deck_dir: Path, media_dir: Path, inp: Path, key: str, title: str,
               label_re: str, strip_re: str = "") -> int:
    inp = Path(inp).expanduser()
    if inp.suffix.lower() not in (".apkg", ".colpkg"):
        raise SystemExit(f"{inp}: only .apkg/.colpkg inputs so far (video + subtitles: later)")
    lines, media, stats, ex = import_apkg(inp, key, label_re, strip_re)
    out = deck_dir / "lines" / f"{key}.tsv"
    write_lines(out, lines)
    (deck_dir / "lines" / f"{key}.yaml").write_text(yaml.safe_dump(
        {"title": title, "key": key, "input": str(inp), "media": str(media_dir / key),
         "imported": dt.date.today().isoformat()}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    n = ex.extract_media(media, media_dir / key) if media else 0
    print(f"{title}: {stats['notes']} notes → {stats['lines']} lines "
          f"({stats['split']} with several speakers, split) → {len(lines)} rows")
    print(f"  {out}")
    print(f"  media: {n} new files in {media_dir / key}")
    return 0
