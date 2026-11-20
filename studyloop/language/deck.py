# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""A language deck: open one (`LangDeck`: the deck, its language, brief, media and notes
folders) or make a new one (`asl topic "<Language>" --lang <code> ...`)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from studyloop.core.config import load_deck, native_path, write_keep
from studyloop.language.base import Language

TEMPLATES = Path(__file__).resolve().parent / "templates"


@dataclass
class LangDeck:
    path: Path
    lang: str
    language: Language
    cfg: dict            # the language's config (<code>.yaml)
    brief: dict          # Overview.md frontmatter
    media_dir: Path
    notes_dir: Path

    @property
    def vocab_path(self) -> Path:
        return self.notes_dir / "Vocabulary.md"


def open_deck(folder: Path) -> LangDeck:
    from studyloop.core.config.vault import split_frontmatter
    from studyloop.language.setup import get_language
    deck = load_deck(Path(folder).expanduser())
    lang = deck.cfg.get("lang")
    if not lang:
        raise SystemExit(f"{deck.path}/deck.yaml: no `lang:` (e.g. `lang: ja`); not a language deck")
    ov = deck.path / "Overview.md"
    brief = split_frontmatter(ov.read_text(encoding="utf-8"))[0] if ov.is_file() else {}
    media = deck.cfg.get("media_dir")
    if not media:
        raise SystemExit(f"{deck.path}/deck.yaml: set `media_dir:` (a folder outside the vault "
                         "for clips and screenshots)")
    notes = brief.get("notes")
    notes_dir = deck.path
    if isinstance(notes, str) and notes.strip():
        p = native_path(notes)
        notes_dir = p if p.is_absolute() else (deck.path / p)
    language = get_language(lang)
    return LangDeck(deck.path, lang, language, language.config, brief,
                    native_path(media), notes_dir.resolve())


def init_language(name, home, lang, media, notes, prefix, goal, level, gloss) -> Path:
    """`asl topic <Language> --lang <code>`: deck.yaml, the brief, the notes folder."""
    from studyloop.core.config.home import _yaml_str, init_home, render
    from studyloop.core.config.vault import resolve_in, vault_for
    from studyloop.language.setup import lang_config
    from studyloop.sources.topic import write_topics_block
    lang_config(lang)                                   # known language?
    if not media:
        raise SystemExit("A language deck needs --media: a folder OUTSIDE the vault for clips "
                         "and screenshots (e.g. C:\\AnkiMedia\\japanese)")
    init_home(home, [])
    vault = vault_for(home) or home.parent
    slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or lang
    deck_dir = home / slug
    notes_dir = resolve_in(vault, notes) if notes else vault / name
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
        write_keep(out, render((TEMPLATES / tpl).read_text(encoding="utf-8"), **kw))
        print(f"  created {out}")
    print(f"  notes (Vocabulary.md, Grammar/): {notes_dir}")
    print(f"  next: `asl lang setup {lang}` once, then `asl lang add {deck_dir} <video>`")
    write_topics_block(home)
    return deck_dir
