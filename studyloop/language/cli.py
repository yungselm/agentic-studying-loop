# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""`asl lang …`: the language commands (setup, add, seed, plan, draft, grammar, tts, sync,
clean). `add_parser` defines them; `main` opens the deck and hands over to the pipeline."""
from __future__ import annotations

import re
from pathlib import Path

from studyloop.core.cli import examples
from studyloop.core.config import native_path
from studyloop.language.deck import open_deck


def _key_from_title(title: str) -> str:
    words = re.findall(r"[A-Za-z]+|\d+", title)
    key = "".join(w[0].lower() if w.isalpha() else w for w in words)
    return key or "src"


def main(a) -> int:
    from studyloop.language.setup import setup
    if a.lang_cmd == "setup":
        return setup(a.code, a.force)
    d = open_deck(a.deck)
    if a.lang_cmd == "add":
        from studyloop.language.media.lines import add_source
        title = a.title or Path(a.input).stem
        return add_source(d.path, d.media_dir, Path(a.input), a.key or _key_from_title(title),
                          title, d.cfg.get("speaker_labels") or "", d.cfg.get("strip") or "",
                          video=a.video, only=a.only,
                          pad=tuple(d.cfg.get("clip_padding") or (0.25, 0.4)),
                          width=int(d.cfg.get("screenshot_width") or 960),
                          subs=a.subs, keep_re=d.cfg.get("subtitle_keep") or "", lang=d.lang)
    if a.lang_cmd == "clean":
        from studyloop.language.media.clean import clean
        return clean(d, a.delete)
    if a.lang_cmd == "tts":
        from studyloop.language.media.tts import fill_audio
        return fill_audio(d)
    if a.lang_cmd == "grammar":
        from studyloop.language.grammar.points import check_points
        if a.input:
            return d.language.import_grammar(d, a.input, "unknown" if a.fresh else "reviews", a.cards)
        from studyloop.language.grammar.overview import write_overview
        write_overview(d)                     # also fills links/levels from the official lists
        if a.images:
            d.language.grammar_images(d)
        return check_points(d, d.language.tokenizer())
    tok = d.language.tokenizer()
    from studyloop.language.vocabulary.vocab import Vocabulary, seed
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
        from studyloop.language.vocabulary.plan import run
        from studyloop.language.vocabulary.sync import sync
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
        from studyloop.language.cards.draft import draft
        current = a.level or d.brief.get("level")
        return draft(d, vocab, levels, a.n, str(current) if current else None, a.assume or [],
                     a.source)
    if a.lang_cmd == "plan":
        from studyloop.language.vocabulary.plan import run
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
    s.add_argument("code", help="language code, e.g. ja")
    s.add_argument("--force", action="store_true", help="download again")
    examples(s, "asl lang setup ja        # JLPT lists, JMdict, grammar lists (once)")
    ad = ls.add_parser("add", help="import a media source (.apkg from subs2srs/movies2anki)")
    ad.add_argument("deck", type=Path, help="the language deck folder")
    ad.add_argument("input", help="a video (subtitles next to it: .srt/.ass) or a mined .apkg")
    ad.add_argument("--title", help='e.g. "Terrace House OND 1"')
    ad.add_argument("--key", help="short id prefix for its lines (default: from the title)")
    ad.add_argument("--video", help="the original video: cut padded clips + sharp screenshots from it")
    ad.add_argument("--only", help="keep notes mentioning this (default with --video: its file name)")
    ad.add_argument("--subs", help="the subtitle file, if not next to the video with the same name")
    examples(ad, """
        asl lang add "Anki cards/Japanese" ~/media/ja/terrace_house_01.mkv --title "Terrace House OND 1"
        asl lang add "Anki cards/Japanese" shirokuma.apkg --title "Shirokuma Cafe" --key sk
        asl lang add "Anki cards/Japanese" mined.apkg --video ep01.mkv   # re-cut clips from the video
    """)
    se = ls.add_parser("seed", help="mark words known from your own Anki exports")
    se.add_argument("deck", type=Path, help="the language deck folder")
    se.add_argument("exports", nargs="*", help="default: `known_from:` in Overview.md")
    examples(se, """
        asl lang seed "Anki cards/Japanese"                  # the exports in Overview.md
        asl lang seed "Anki cards/Japanese" old_decks.colpkg
    """)
    pl = ls.add_parser("plan", help="order one-new-word lines into cards; report the rest")
    pl.add_argument("deck", type=Path, help="the language deck folder")
    pl.add_argument("--level", help="current level (default: `level:` in Overview.md)")
    pl.add_argument("--assume", action="append", help="treat a level's listed words as known (repeat)")
    pl.add_argument("--dry", action="store_true", help="report only; write nothing")
    pl.add_argument("--gate", choices=["learning", "planned", "off"],
                    help="grammar gate (default: `grammar_gate:` in Overview.md, else learning)")
    examples(pl, """
        asl lang plan "Anki cards/Japanese" --dry            # the report, nothing written
        asl lang plan "Anki cards/Japanese" --level N4 --assume N5
    """)
    gr = ls.add_parser("grammar", help="grammar notes + cards from a Game Gengo deck; or check the rules")
    gr.add_argument("deck", type=Path, help="the language deck folder")
    gr.add_argument("input", nargs="?", help="a Game Gengo .apkg (without: check the notes' rules)")
    gr.add_argument("--fresh", action="store_true", help="every grammar point starts as unknown")
    gr.add_argument("--cards", action="store_true", help="also write the lessons as grammar cards")
    gr.add_argument("--images", action="store_true",
                    help="an image for each grammar note without one (Japanese: from JLPT Sensei)")
    examples(gr, """
        asl lang grammar "Anki cards/Japanese" game_gengo.apkg --cards   # notes + grammar cards
        asl lang grammar "Anki cards/Japanese"               # check the notes' rules
        asl lang grammar "Anki cards/Japanese" --images
    """)
    cl = ls.add_parser("clean", help="list (or --delete) media no line or card uses")
    cl.add_argument("deck", type=Path, help="the language deck folder")
    cl.add_argument("--delete", action="store_true", help="remove them")
    examples(cl, """
        asl lang clean "Anki cards/Japanese"                 # list first
        asl lang clean "Anki cards/Japanese" --delete
    """)
    tt = ls.add_parser("tts", help="give cards without native audio a text-to-speech clip")
    tt.add_argument("deck", type=Path, help="the language deck folder")
    examples(tt, 'asl lang tts "Anki cards/Japanese"     # VOICEVOX if running, else edge-tts')
    sy = ls.add_parser("sync", help="statuses from your Anki reviews (a manual .apkg/.colpkg export)")
    sy.add_argument("deck", type=Path, help="the language deck folder")
    sy.add_argument("export", help="Anki export with scheduling information")
    examples(sy, 'asl lang sync "Anki cards/Japanese" ~/Downloads/japanese.apkg')
    dr = ls.add_parser("draft", help="write sentence-card stubs for the next planned lines")
    dr.add_argument("deck", type=Path, help="the language deck folder")
    dr.add_argument("-n", type=int, default=20, help="how many cards (default 20)")
    dr.add_argument("--level", help="current level (default: `level:` in Overview.md)")
    dr.add_argument("--assume", action="append", help="treat a level's listed words as known")
    dr.add_argument("--source", help="only lines of sources whose key starts with this (e.g. sk)")
    examples(dr, """
        asl lang draft "Anki cards/Japanese" -n 50
        asl lang draft "Anki cards/Japanese" --source sk     # only Shirokuma Cafe lines
    """)
