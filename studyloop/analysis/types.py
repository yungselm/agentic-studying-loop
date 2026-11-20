# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
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

#: Columns of `Data.cards`, name to meaning (one row per Anki card).
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
#: Columns of `Data.reviews`, name to meaning (one row per answer).
REVIEW_COLUMNS = {
    # one row per answer, for anything over time ("which lecture got weak in March")
    "cid": "Anki card id", "time": "when (datetime)", "ease": "1 Again .. 4 Easy", "ms": "answer time",
    "type": "0 learning, 1 review, 2 relearning, 3 filtered",
}


@dataclass
class Data:
    """What every analysis gets.

    Attributes
    ----------
    cards : pandas.DataFrame
        One row per Anki card; columns in `CARD_COLUMNS`.
    reviews : pandas.DataFrame
        One row per answer; columns in `REVIEW_COLUMNS`.
    home : Home
        Limits, refresh settings, standards version.
    deck : str or None
        ``--deck``: only this deck and its subdecks.
    export : Path
    state : dict
        The last refresh (``evidence/refresh-state.yaml``).

    Examples
    --------
    >>> c = data.cards
    >>> c[c["kind"] == "cloze"].groupby("gaps")["fail_rate"].mean()
    """
    cards: pd.DataFrame
    reviews: pd.DataFrame
    home: Home
    deck: str | None
    export: Path
    state: dict = field(default_factory=dict)


# ---- what an analysis returns ------------------------------------------------------------

@dataclass(frozen=True)
class Suggestion:
    """A proposed change; the refresh-standards skill turns these into one diff the user approves.

    Parameters
    ----------
    target : str
        What changes: ``"limits.concept.bold_chars"``, ``"standards/python.md"``, ``"tsk-007"``.
    kind : str
        ``limit``, ``rule`` or ``rewrite``.
    old : str or None
    new : str
    evidence : str
        One line: the numbers behind it.
    confidence : str
        ``low``, ``medium`` or ``high`` (bin sizes, effect size).

    Examples
    --------
    From the author's own review data (the concept-size analysis):

    >>> Suggestion("limits.concept.bold_chars", "limit", "120/150", "80/80",
    ...            "reference fail rate 4% in the smallest bin", "high")
    """
    target: str
    kind: str
    old: str | None
    new: str
    evidence: str
    confidence: str


@dataclass
class Section:
    """One section of the ``asl stats`` report: what an analysis returns.

    Attributes
    ----------
    title : str
    summary : str
        At most 3 lines, for the agent (it reads only these and the suggestions).
    markdown : str
        Tables and text, for you.
    figures : list of (str, Figure)
        ``(name, matplotlib Figure)``, saved next to the report.
    suggestions : list of Suggestion

    Examples
    --------
    >>> Section("Leeches", summary="3 leech(es) (≥5 lapses): tsk-007, tsk-012, cs-031",
    ...         markdown=table)                  # a markdown table of the leeches
    """
    title: str
    summary: str = ""
    markdown: str = ""
    figures: list[tuple[str, Any]] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)


class Analysis:
    """One analysis of review data. Subclass it, implement `run`, provide it.

    Attributes
    ----------
    name : str
        For ``asl stats --only code-size,leeches``.
    order : int
        Position in the report (refresh status 0, leeches 80).

    Examples
    --------
    The leeches section (``studyloop/analysis/analyses/cards.py``), shortened:

    >>> class Leeches(Analysis):
    ...     name, order = "leeches", 80
    ...
    ...     def run(self, data):
    ...         c = data.cards
    ...         leeches = c[c["lapses"] >= 5].sort_values("lapses", ascending=False)
    ...         if leeches.empty:
    ...             return None
    ...         return Section("Leeches", summary=f"{len(leeches)} leech(es)")
    >>> reg.provide("analysis", "leeches", Leeches())
    """
    name: str
    order: int = 50

    def run(self, data: Data) -> Section | None:
        """None: nothing to say (no cards of that kind, too few answers)."""
        raise NotImplementedError
