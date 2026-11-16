"""The analyses that ship with the tool: the `asl stats` report before it had modules, one
section each, in report order.

    refresh.py   is a refresh due                     (refresh-status)
    groups.py    per card type, deck, standards version (overview, code-by-deck, by-standards)
    sizes.py     size against fail rate -> suggested limits (code-size, concept-size, cloze-size)
    cards.py     leeches, hardest, easiest            (leeches, hardest, easiest)
    helpers.py   pooled fail rates, bins, the limit heuristic

A new analysis: a class like these (`name`, `order`, `run(data) -> Section | None`), registered
with `reg.provide("analysis", name, obj)`.
"""
from studyloop.analysis.analyses.cards import Easiest, Hardest, Leeches
from studyloop.analysis.analyses.groups import ByStandards, CodeByDeck, Overview
from studyloop.analysis.analyses.helpers import _fmt, limit_line, spearman, suggest
from studyloop.analysis.analyses.refresh import RefreshStatus, refresh_status
from studyloop.analysis.analyses.sizes import ClozeSize, CodeSize, ConceptSize

BUNDLED = (RefreshStatus(), Overview(), CodeSize(), ConceptSize(), ClozeSize(), CodeByDeck(),
           ByStandards(), Leeches(), Hardest(), Easiest())

__all__ = ["BUNDLED", "_fmt", "limit_line", "refresh_status", "spearman", "suggest"]
