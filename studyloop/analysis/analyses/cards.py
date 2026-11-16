"""Single cards worth a look: leeches, the hardest and the easiest (FSRS difficulty)."""
from __future__ import annotations

from studyloop.analysis.analyses.helpers import (
    _RATED_COLS,
    LEECH_LAPSES,
    _by,
    _card_rows,
    _rated,
    _size,
)
from studyloop.analysis.types import Analysis, Section


class Leeches(Analysis):
    name, order = "leeches", 80

    def run(self, data):
        c = data.cards
        leeches = _by(c[c["lapses"] >= LEECH_LAPSES], "lapses", ascending=False)
        if leeches.empty:
            return None
        md = ["| id | lapses | kind | size | front |", "|---|---|---|---|---|"]
        md += _card_rows(leeches.head(30), [lambda r: r["card_id"] or "–", lambda r: str(r["lapses"]),
                                            lambda r: r["kind"], _size, lambda r: r["front"]])
        ids = [i for i in leeches["card_id"].head(10) if i]
        return Section("Leeches", summary=f"{len(leeches)} leech(es) (≥{LEECH_LAPSES} lapses)"
                       + (f": {', '.join(ids)}" if ids else ""), markdown="\n".join(md))


class Hardest(Analysis):
    name, order = "hardest", 90

    def run(self, data):
        rated = _rated(data)
        if rated.empty:
            return None
        md = ["| id | difficulty | fail rate | size | front |", "|---|---|---|---|---|"]
        md += _card_rows(rated.head(15), _RATED_COLS)
        ids = [i for i in rated["card_id"].head(15) if i]
        return Section("Hardest 15 (FSRS difficulty)", summary=", ".join(ids), markdown="\n".join(md))


class Easiest(Analysis):
    name, order = "easiest", 91

    def run(self, data):
        rated = _rated(data)
        if rated.empty:
            return None
        md = ["| id | difficulty | fail rate | size | front |", "|---|---|---|---|---|"]
        md += _card_rows(rated.tail(15), _RATED_COLS)
        ids = [i for i in rated["card_id"].tail(15) if i]
        return Section("Easiest 15", summary=", ".join(ids), markdown="\n".join(md))
