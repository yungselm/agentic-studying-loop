"""Core as a module: its card types, the `plain` deck kind and its commands, registered
through the same API as every other module."""
from __future__ import annotations

from .registry import DeckKind, Module, Registry

PLAIN = DeckKind(
    "plain", what="cards only (no sources, no brief)", skills="write-cards",
    card_types=("code", "concept", "timeline", "cloze"))


def register(reg: Registry) -> None:
    from .cardtypes import CORE_TYPES
    from .commands import COMMANDS
    reg.add_deck_kind(PLAIN)
    for t in CORE_TYPES:
        reg.add_card_type(t)
    for c in COMMANDS:
        reg.add_command(c)


MODULE = Module("core", register, skills=("check-cards", "write-cards"))
