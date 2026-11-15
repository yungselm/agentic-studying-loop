"""A new language deck (`asl topic "<Language>" --lang <code> ...`)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..core.config import write_keep

TEMPLATES = Path(__file__).resolve().parent / "templates"


def init_language(name, home, lang, media, notes, prefix, goal, level, gloss) -> Path:
    """`asl topic <Language> --lang <code>`: deck.yaml, the brief, the notes folder."""
    from ..core.home import _yaml_str, init_home
    from ..core.vault import vault_for
    from ..project import _render, _resolve_in, write_topics_block  # step 6: topics move
    from .setup import lang_config
    lang_config(lang)                                   # known language?
    if not media:
        raise SystemExit("A language deck needs --media: a folder OUTSIDE the vault for clips "
                         "and screenshots (e.g. C:\\AnkiMedia\\japanese)")
    init_home(home, [])
    vault = vault_for(home) or home.parent
    slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or lang
    deck_dir = home / slug
    notes_dir = _resolve_in(vault, notes) if notes else vault / name
    notes_dir.mkdir(parents=True, exist_ok=True)
    rel = Path(os.path.relpath(notes_dir, deck_dir)).as_posix()
    kw = dict(name=name, lang=lang, prefix=prefix or lang, media=_yaml_str(media),
              goal=_yaml_str(goal) if goal else '""', level=level or '""', gloss=gloss or "en",
              notes=_yaml_str(rel))
    for tpl in ("deck.yaml", "Overview.md"):
        out = deck_dir / tpl
        if out.exists():
            print(f"  kept {out}")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        write_keep(out, _render((TEMPLATES / tpl).read_text(encoding="utf-8"), **kw))
        print(f"  created {out}")
    print(f"  notes (Vocabulary.md, Grammar/): {notes_dir}")
    print(f"  next: `asl lang setup {lang}` once, then `asl lang add {deck_dir} <video>`")
    write_topics_block(home)
    return deck_dir
