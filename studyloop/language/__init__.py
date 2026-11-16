"""Language decks: sentence and grammar cards from native media, with the known words and
grammar points kept in the vault. Start here.

The pipeline every language shares; what differs per language is a `Language` (base.py) from a
language module (language_ja). Opt-in: the `lang` extra plus the language's own (`lang-ja`),
then `asl lang setup <code>`. Design: docs/language-cards.md.

    cli.py        `asl lang …`: every command starts here and calls into the folders below
    base.py       what a language provides: tokenizer, levels, dictionary, TTS, grammar lists
    setup.py      find a deck's language among the installed ones; the download cache
    deck.py       a language deck: open one (LangDeck), make a new one (`asl topic --lang`)
    media/        a source becomes lines: mined decks, video + subtitles, clips, TTS, cleanup
    vocabulary/   tokens and word levels, Vocabulary.md, the i+1 planner, sync from reviews
    grammar/      grammar points and their rules, the overview against the official lists
    cards/        the sentence and grammar card types, card stubs (draft), card-file edits
    templates/    deck.yaml and Overview.md of a new language deck

A source flows: media/lines -> vocabulary/plan -> cards/draft -> (you study) -> vocabulary/sync.
"""
from __future__ import annotations

from studyloop.core.registry import Command, DeckKind, Module, Registry

LANGUAGE = DeckKind(
    "language", what="a language from native media", skills="language-cards",
    card_types=("sentence", "grammar"), detect=lambda d: bool(d.cfg.get("lang")),
    card_index=False,          # thousands of cards: lines/*.tsv and Vocabulary.md are the index
    order_by_id=True)          # new cards in the planner's order across all subdecks


def register(reg: Registry) -> None:
    from studyloop.language.cards.types import LANG_TYPES
    from studyloop.language.cli import add_parser, main
    from studyloop.language.deck import init_language
    reg.add_deck_kind(LANGUAGE)
    reg.provide("new-deck", "language", init_language)        # `asl topic --lang`
    for t in LANG_TYPES:
        reg.add_card_type(t)
    reg.add_command(Command("lang", "language topics: import media, seed vocabulary, plan i+1 cards",
                            add_parser, main))


MODULE = Module("language", register, skills=("language-cards",), extra="lang", requires=("sources",),
                needs=("wordfreq", "imageio_ffmpeg", "edge_tts"))
