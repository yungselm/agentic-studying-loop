"""`asl lang clean <deck>`: files in media_dir that no line or card uses (left over after a
re-import or a removed source). Lists them; `--delete` removes them. Everything in media_dir can
be cut again by `asl lang add`, so nothing there is the only copy."""
from __future__ import annotations

import re
from pathlib import Path

from studyloop.core.cards import load_file
from studyloop.core.config import load_deck
from studyloop.language.media.lines import read_lines

EMBED = re.compile(r"!\[\[([^\]|#]+)")


def used_media(deck_dir: Path) -> set[str]:
    used = set()
    for f in sorted((deck_dir / "lines").glob("*.tsv")):
        for ln in read_lines(f):
            used |= {ln.audio, ln.image}
    deck = load_deck(deck_dir)
    for f in deck.files():
        for c in load_file(f):
            used |= {str(c.get("audio") or ""), str(c.get("image") or "")}
            for v in (c.get("note"), c.get("grammar"), c.get("text")):
                for x in (v if isinstance(v, list) else [v]):
                    used |= set(EMBED.findall(str(x or "")))
    return {Path(u).name.lower() for u in used if u}


def clean(d, delete: bool = False) -> int:
    used = used_media(d.path)
    files = [p for p in d.media_dir.rglob("*") if p.is_file()] if d.media_dir.is_dir() else []
    unused = [p for p in files if p.name.lower() not in used]
    size = sum(p.stat().st_size for p in unused)
    by_dir: dict[str, int] = {}
    for p in unused:
        by_dir[p.parent.name] = by_dir.get(p.parent.name, 0) + 1
    print(f"{d.media_dir}: {len(files)} files, {len(unused)} unused ({size / 1e6:.0f} MB)"
          + (": " + ", ".join(f"{k} {v}" for k, v in sorted(by_dir.items())) if unused else ""))
    if delete:
        for p in unused:
            p.unlink()
        for sub in sorted({p.parent for p in unused}, key=lambda q: -len(q.parts)):
            if sub != d.media_dir and sub.is_dir() and not any(sub.iterdir()):
                sub.rmdir()
        print(f"  deleted {len(unused)} files")
    elif unused:
        print("  `--delete` removes them (all can be cut again by `asl lang add`)")
    return 0
