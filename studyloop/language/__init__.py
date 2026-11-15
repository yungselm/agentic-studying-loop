"""Language topics: sentence mining, a vocabulary ground truth in the vault, i+1 planning.

The pipeline every language shares; what differs per language is a `Language` (language.py)
from a language module (language_ja). Opt-in: the `lang` extra plus the language's own
(`lang-ja`), then `asl lang setup <code>`. Design: docs/language-cards.md. Modules, in the
order a source flows through them:

  language    what a language provides (tokenizer, levels, dictionary, TTS, grammar lists)
  setup       find the deck's language, the download cache, `asl lang setup`
  lines       sources -> lines/<key>.tsv: mined .apkg, video + subtitles; clips, screenshots
  audio       ffmpeg (padding, speaker splits); Anki exports are read by core.reviews
  tokens      tokens, plain text, the **target**   levels   word levels (lists, frequency)
  vocab       Vocabulary.md, seeding from exports, meanings
  grammar     grammar rules (pattern / token) and their check
  overview    the official grammar lists as a checklist against the grammar notes
  new         a new language deck (`asl topic --lang`)
  plan        the i+1 planner and its report    draft    card stubs in plan order
  cardtypes   sentence + grammar cards: fields, lint
  cardfile    card items, in-place field edits   notefile  note frontmatter
  sync        statuses from Anki reviews    tts    fallback audio    clean    unused media"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..core.config import load_deck, native_path
from ..core.registry import Command, DeckKind, Module, Registry
from .language import Language


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
    from ..core.vault import split_frontmatter
    from .setup import get_language
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


def _key_from_title(title: str) -> str:
    words = re.findall(r"[A-Za-z]+|\d+", title)
    key = "".join(w[0].lower() if w.isalpha() else w for w in words)
    return key or "src"


def main(a) -> int:
    from .setup import setup
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
                          width=int(d.cfg.get("screenshot_width") or 960),
                          subs=a.subs, keep_re=d.cfg.get("subtitle_keep") or "", lang=d.lang)
    if a.lang_cmd == "clean":
        from .clean import clean
        return clean(d, a.delete)
    if a.lang_cmd == "tts":
        from .tts import fill_audio
        return fill_audio(d)
    if a.lang_cmd == "grammar":
        from .grammar import check_points
        if a.input:
            return d.language.import_grammar(d, a.input, "unknown" if a.fresh else "reviews", a.cards)
        from .overview import write_overview
        write_overview(d)                     # also fills links/levels from the official lists
        if a.images:
            d.language.grammar_images(d)
        return check_points(d, d.language.tokenizer())
    tok = d.language.tokenizer()
    from .vocab import Vocabulary, seed
    vocab = Vocabulary(d.vocab_path, d.lang, tok)
    levels = d.language.levels()
    if a.lang_cmd == "seed":
        exports = [native_path(p) for p in (a.exports or d.brief.get("known_from") or [])]
        if not exports:
            raise SystemExit("No exports: pass them, or set `known_from:` in Overview.md")
        c = seed(vocab, exports)
        vocab.write(levels.order)
        print(f"Seeded from {c['notes']} studied notes: {c['known']} words known, "
              f"{c['learning']} learning → {d.vocab_path}")
        return 0
    if a.lang_cmd == "sync":
        from .plan import run
        from .sync import sync
        r = sync(d, vocab, native_path(a.export))
        changes = {k: v for k, v in r.items() if not k.startswith("_")}
        print(f"Synced {r['_cards_found']} language cards from {a.export}: "
              + (", ".join(f"{v} {k}" for k, v in sorted(changes.items())) or "no status changed"))
        for src, (n, f) in r["_per_source"].items():
            print(f"  {src}: {n} reviews, fail {f / n:.0%}" if n else f"  {src}: no reviews")
        print()
        current = d.brief.get("level")
        return run(d.path, vocab, levels, d.cfg, str(current) if current else None, [],
                   gloss_lang=str(d.brief.get("gloss_language") or "en"), notes_dir=d.notes_dir,
                   gate=str(d.brief.get("grammar_gate") or "learning"))
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
                   gloss_lang=str(d.brief.get("gloss_language") or "en"), notes_dir=d.notes_dir,
                   gate=str(a.gate or d.brief.get("grammar_gate") or "learning"))
    return 1


def add_parser(lg) -> None:
    """The `asl lang …` subcommands, on the `lang` parser."""
    ls = lg.add_subparsers(dest="lang_cmd", required=True)
    s = ls.add_parser("setup", help="download level lists for a language (e.g. ja)")
    s.add_argument("code")
    s.add_argument("--force", action="store_true", help="download again")
    ad = ls.add_parser("add", help="import a media source (.apkg from subs2srs/movies2anki)")
    ad.add_argument("deck", type=Path)
    ad.add_argument("input", help="a video (subtitles next to it: .srt/.ass) or a mined .apkg")
    ad.add_argument("--title", help='e.g. "Terrace House OND 1"')
    ad.add_argument("--key", help="short id prefix for its lines (default: from the title)")
    ad.add_argument("--video", help="the original video: cut padded clips + sharp screenshots from it")
    ad.add_argument("--only", help="keep notes mentioning this (default with --video: its file name)")
    ad.add_argument("--subs", help="the subtitle file, if not next to the video with the same name")
    se = ls.add_parser("seed", help="mark words known from your own Anki exports")
    se.add_argument("deck", type=Path)
    se.add_argument("exports", nargs="*", help="default: `known_from:` in Overview.md")
    pl = ls.add_parser("plan", help="order one-new-word lines into cards; report the rest")
    pl.add_argument("deck", type=Path)
    pl.add_argument("--level", help="current level (default: `level:` in Overview.md)")
    pl.add_argument("--assume", action="append", help="treat a level's listed words as known (repeat)")
    pl.add_argument("--dry", action="store_true", help="report only; write nothing")
    pl.add_argument("--gate", choices=["learning", "planned", "off"],
                    help="grammar gate (default: `grammar_gate:` in Overview.md, else learning)")
    gr = ls.add_parser("grammar", help="grammar notes + cards from a Game Gengo deck; or check the rules")
    gr.add_argument("deck", type=Path)
    gr.add_argument("input", nargs="?", help="a Game Gengo .apkg (without: check the notes' rules)")
    gr.add_argument("--fresh", action="store_true", help="every grammar point starts as unknown")
    gr.add_argument("--cards", action="store_true", help="also write the lessons as grammar cards")
    gr.add_argument("--images", action="store_true",
                    help="an image for each grammar note without one (Japanese: from JLPT Sensei)")
    cl = ls.add_parser("clean", help="list (or --delete) media no line or card uses")
    cl.add_argument("deck", type=Path)
    cl.add_argument("--delete", action="store_true", help="remove them")
    tt = ls.add_parser("tts", help="give cards without native audio a text-to-speech clip")
    tt.add_argument("deck", type=Path)
    sy = ls.add_parser("sync", help="statuses from your Anki reviews (a manual .apkg/.colpkg export)")
    sy.add_argument("deck", type=Path)
    sy.add_argument("export", help="Anki export with scheduling information")
    dr = ls.add_parser("draft", help="write sentence-card stubs for the next planned lines")
    dr.add_argument("deck", type=Path)
    dr.add_argument("-n", type=int, default=20, help="how many cards (default 20)")
    dr.add_argument("--level", help="current level (default: `level:` in Overview.md)")
    dr.add_argument("--assume", action="append", help="treat a level's listed words as known")
    dr.add_argument("--source", help="only lines of sources whose key starts with this (e.g. sk)")


# ---- the module ----------------------------------------------------------------------

LANGUAGE = DeckKind(
    "language", what="a language from native media", skills="language-cards",
    card_types=("sentence", "grammar"), detect=lambda d: bool(d.cfg.get("lang")),
    card_index=False,          # thousands of cards: lines/*.tsv and Vocabulary.md are the index
    order_by_id=True)          # new cards in the planner's order across all subdecks


def register(reg: Registry) -> None:
    from .cardtypes import LANG_TYPES
    reg.add_deck_kind(LANGUAGE)
    for t in LANG_TYPES:
        reg.add_card_type(t)
    reg.add_command(Command("lang", "language topics: import media, seed vocabulary, plan i+1 cards",
                            add_parser, main))


MODULE = Module("language", register, skills=("language-cards",), extra="lang", requires=("sources",),
                needs=("wordfreq", "imageio_ffmpeg", "edge_tts"))
