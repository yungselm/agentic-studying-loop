"""What an analysis of review data is (docs/architecture.md, "Review data and analysis").

`asl stats <export>` reads the export (core/anki/reviews.py), joins every Anki card back to its card
file, and runs every registered analysis on the result. Each returns a Section: a short summary
and suggestions for the agent (refresh-standards reads only those), tables and figures for you.
An analysis registers with `reg.provide("analysis", name, obj)`, like a language; the bundled
ones are today's report, split up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

    from studyloop.core.config import Home


# ---- the data every analysis gets ------------------------------------------------------

CARD_COLUMNS = {
    # one row per Anki card (a cloze note with 3 gaps is 3 rows)
    "cid": "Anki card id", "nid": "Anki note id", "guid": "note GUID", "ord": "template / gap number (from 0)",
    "deck": "Anki deck, full name (A::B)",
    "kind": "card type (code, concept, timeline, cloze, sentence, grammar)",
    "card_id": "the card's `id:` (tsk-007), from its tag", "std": "standards version, from its tag",
    "front": "the front as plain text (90 chars)",
    # from the card file, when the GUID matches one (`matched`); empty otherwise
    "matched": "found in a card file of the card home",
    "file": "deck folder / card file (cs231n/lecture_03.yaml)", "tags": "the card's `tags:`",
    "source": "`source:` as written", "source_note": "the [[Note]] it links to (Softmax)",
    # size measures, as studied (from the export; per Anki card: a cloze gap is its own card)
    "typed_chars": "code", "typed_lines": "code", "answer_chars": "concept, timeline",
    "bold_chars": "concept, timeline", "gap_chars": "cloze: this card's gaps", "gaps": "cloze",
    "hook": "cloze: 1 with a hook",
    # now (scheduling)
    "created": "note creation time", "ivl": "interval, days", "lapses": "lapses",
    "queue": "Anki queue (-1 suspended)", "ctype": "0 new, 1 learning, 2 review, 3 relearning",
    "difficulty": "FSRS difficulty (1-10)", "stability": "FSRS stability, days",
    # from the review log
    "answers": "all answers", "reviews": "review-phase answers", "fails": "Again on those",
    "fail_rate": "fails / reviews", "median_ms": "median answer time",
    "timer_hits": "answers at the 60 s timer",
}
REVIEW_COLUMNS = {
    # one row per answer, for anything over time ("which lecture got weak in March")
    "cid": "Anki card id", "time": "when (datetime)", "ease": "1 Again .. 4 Easy", "ms": "answer time",
    "type": "0 learning, 1 review, 2 relearning, 3 filtered",
}


@dataclass
class Data:
    cards: pd.DataFrame                 # CARD_COLUMNS
    reviews: pd.DataFrame               # REVIEW_COLUMNS
    home: Home                          # limits, refresh settings, standards version
    deck: str | None                    # `--deck`: only this deck and its subdecks
    export: Path
    state: dict = field(default_factory=dict)   # the last refresh (evidence/refresh-state.yaml)


# ---- what an analysis returns ------------------------------------------------------------

@dataclass(frozen=True)
class Suggestion:
    """A proposed change; refresh-standards turns these into one diff the user approves."""
    target: str                         # "limits.code.typed_chars_max", "standards/python.md", "tsk-007"
    kind: str                           # limit | rule | rewrite
    old: str | None
    new: str
    evidence: str                       # one line: the numbers behind it
    confidence: str                     # low | medium | high (bin sizes, effect size)


@dataclass
class Section:
    title: str
    summary: str = ""                   # ≤ 3 lines, for the agent
    markdown: str = ""                  # tables etc., for you
    figures: list[tuple[str, Any]] = field(default_factory=list)   # (name, matplotlib Figure)
    suggestions: list[Suggestion] = field(default_factory=list)


class Analysis:
    name: str                           # "size-bins"; `asl stats --only size-bins,leeches`
    order: int = 50                     # position in the report (refresh status 0, leeches 90)

    def run(self, data: Data) -> Section | None:
        """None: nothing to say (no cards of that kind, too few answers)."""
        raise NotImplementedError
