"""Language topics: sentence mining, a vocabulary ground truth in the vault, i+1 planning.

Opt-in: needs the `lang` extra (tokenizer, frequency data) and `asl lang setup <code>`.
Design: docs/language-cards.md."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import load_deck, native_path


@dataclass
class LangDeck:
    path: Path
    lang: str
    cfg: dict            # language config (lang/<code>.yaml)
    brief: dict          # Overview.md frontmatter
    media_dir: Path
    notes_dir: Path

    @property
    def vocab_path(self) -> Path:
        return self.notes_dir / "Vocabulary.md"


def open_deck(folder: Path) -> LangDeck:
    from ..notes import split_frontmatter
    from .levels import lang_config
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
    return LangDeck(deck.path, lang, lang_config(lang), brief,
                    native_path(media), notes_dir.resolve())


def _key_from_title(title: str) -> str:
    words = re.findall(r"[A-Za-z]+|\d+", title)
    key = "".join(w[0].lower() if w.isalpha() else w for w in words)
    return key or "src"


def main(a) -> int:
    from .levels import Levels, setup
    from .tokens import tokenizer
    if a.lang_cmd == "setup":
        return setup(a.code, a.force)
    d = open_deck(a.deck)
    if a.lang_cmd == "add":
        from .lines import add_source
        title = a.title or Path(a.input).stem
        return add_source(d.path, d.media_dir, Path(a.input), a.key or _key_from_title(title),
                          title, d.cfg.get("speaker_labels") or "", d.cfg.get("strip") or "",
                          video=a.video, only=a.only,
                          pad=tuple(d.cfg.get("clip_padding") or (0.25, 0.4)),
                          width=int(d.cfg.get("screenshot_width") or 960))
    tok = tokenizer(d.cfg.get("tokenizer", ""))
    from .vocab import Vocabulary, seed
    vocab = Vocabulary(d.vocab_path, d.lang, tok)
    levels = Levels(d.cfg)
    if a.lang_cmd == "seed":
        exports = [native_path(p) for p in (a.exports or d.brief.get("known_from") or [])]
        if not exports:
            raise SystemExit("No exports: pass them, or set `known_from:` in Overview.md")
        c = seed(vocab, exports)
        vocab.write(levels.order)
        print(f"Seeded from {c['notes']} studied notes: {c['known']} words known, "
              f"{c['learning']} learning → {d.vocab_path}")
        return 0
    if a.lang_cmd == "draft":
        from .draft import draft
        current = a.level or d.brief.get("level")
        return draft(d, vocab, levels, a.n, str(current) if current else None, a.assume or [],
                     a.source)
    if a.lang_cmd == "plan":
        from .plan import run
        current = a.level or d.brief.get("level")
        return run(d.path, vocab, levels, d.cfg, str(current) if current else None,
                   a.assume or [], write=not a.dry,
                   gloss_lang=str(d.brief.get("gloss_language") or "en"))
    return 1


def add_parser(sub) -> None:
    lg = sub.add_parser("lang", help="language topics: import media, seed vocabulary, plan i+1 cards")
    ls = lg.add_subparsers(dest="lang_cmd", required=True)
    s = ls.add_parser("setup", help="download level lists for a language (e.g. ja)")
    s.add_argument("code")
    s.add_argument("--force", action="store_true", help="download again")
    ad = ls.add_parser("add", help="import a media source (.apkg from subs2srs/movies2anki)")
    ad.add_argument("deck", type=Path)
    ad.add_argument("input", help="the source: an .apkg (video + subtitles: later)")
    ad.add_argument("--title", help='e.g. "Terrace House OND 1"')
    ad.add_argument("--key", help="short id prefix for its lines (default: from the title)")
    ad.add_argument("--video", help="the original video: cut padded clips + sharp screenshots from it")
    ad.add_argument("--only", help="keep notes mentioning this (default with --video: its file name)")
    se = ls.add_parser("seed", help="mark words known from your own Anki exports")
    se.add_argument("deck", type=Path)
    se.add_argument("exports", nargs="*", help="default: `known_from:` in Overview.md")
    pl = ls.add_parser("plan", help="order one-new-word lines into cards; report the rest")
    pl.add_argument("deck", type=Path)
    pl.add_argument("--level", help="current level (default: `level:` in Overview.md)")
    pl.add_argument("--assume", action="append", help="treat a level's listed words as known (repeat)")
    pl.add_argument("--dry", action="store_true", help="report only; write nothing")
    dr = ls.add_parser("draft", help="write sentence-card stubs for the next planned lines")
    dr.add_argument("deck", type=Path)
    dr.add_argument("-n", type=int, default=20, help="how many cards (default 20)")
    dr.add_argument("--level", help="current level (default: `level:` in Overview.md)")
    dr.add_argument("--assume", action="append", help="treat a level's listed words as known")
    dr.add_argument("--source", help="only lines of sources whose key starts with this (e.g. sk)")
