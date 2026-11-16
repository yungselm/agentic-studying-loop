"""Core: the engine every other module builds on. Start here.

What a deck is, how cards are written down, and the three things done with them:

    asl lint   -> engine/lint.py     card checks, then each card type's own, then module rules
    asl build  -> engine/build.py    an Anki package from deck folders
    asl check  -> engine/check.py    run card code through the pack's checker (packs/<lang>/)
    asl fix    -> cards/ids.py       ids, std versions, `kind:`, the Overview.md index

The parts:

    registry.py   what modules plug in (deck kinds, card types, lint rules, commands) and
                  `registry()`, which loads them; read this to write a module
    cli.py        `asl`: one subcommand per registered command; commands.py has core's own
    config/       where things are: card home (studyloop.yaml), decks (deck.yaml), packs, vault
    cards/        card files (io), what a card shows (text), core's card types, ids
    engine/       lint, build, check; budget (how much an agent reads at once)
    anki/         reading Anki exports (reviews.py); the note templates and CodeMirror
    packs/ standards/ templates/   shipped files: checkers, default standards, a new card home

Rule: modules (notes, sources, projects, language, analysis) import core; core never imports
a module (`lint-imports`, docs/architecture.md). Core registers itself like any module, below.
"""
from __future__ import annotations

from studyloop.core.registry import DeckKind, Module, Registry

PLAIN = DeckKind(
    "plain", what="cards only (no sources, no brief)", skills="write-cards",
    card_types=("code", "concept", "timeline", "cloze"))


def register(reg: Registry) -> None:
    from studyloop.core.cards.types import CORE_TYPES
    from studyloop.core.commands import COMMANDS
    reg.add_deck_kind(PLAIN)
    for t in CORE_TYPES:
        reg.add_card_type(t)
    for c in COMMANDS:
        reg.add_command(c)


MODULE = Module("core", register, skills=("check-cards", "write-cards"))
