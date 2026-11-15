"""The tables every analysis gets: the export's cards (one row per Anki card, measured as
studied) joined to the card files of the card home by GUID, and the review log."""
from __future__ import annotations

import base64
import datetime as dt
import html
import json
import re
import statistics as st
from dataclasses import dataclass, field

import pandas as pd

from ..core import cards as C
from ..core.config import Home
from ..core.registry import registry
from ..core.reviews import ReviewData

TIMER_MS = 60000
MEASURES = ("typed_chars", "typed_lines", "answer_chars", "bold_chars", "gap_chars", "gaps", "hook")
SOURCE_NOTE = re.compile(r"\[\[([^\]|#^]+)")


LEGACY_MODEL_NAMES = {"Rust Concept Card": "concept"}      # rust-lang-kata decks


def model_kinds(rd: ReviewData) -> dict[int, str]:
    """Notetype id -> card kind for the registered card types' note types (and
    rust-lang-kata's), matched by id or, if Anki renumbered them on import, by name.
    Types sharing a model (timeline -> concept) count as the first; tags tell them apart."""
    names, ids = dict(LEGACY_MODEL_NAMES), {}
    for t in registry().card_types.values():
        names.setdefault(t.model_name, t.name)
        ids.setdefault(t.model_id, t.name)
    kinds = {mid: names[nt.name] for mid, nt in rd.note_types.items() if nt.name in names}
    for mid, kind in ids.items():
        kinds.setdefault(mid, kind)
    return kinds


def _strip(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s or "")
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _b64(s: str) -> str:
    try:
        return base64.b64decode(s or "").decode("utf-8")
    except Exception:
        return _strip(s)


@dataclass
class Card:
    cid: int
    nid: int
    guid: str
    ord: int
    deck: str
    kind: str
    card_id: str
    std: str
    front: str
    created: dt.datetime
    ivl: int
    lapses: int
    queue: int
    ctype: int
    difficulty: float | None
    stability: float | None
    measures: dict = field(default_factory=dict)
    answers: list[tuple[int, int, int]] = field(default_factory=list)  # (ease, ms, type)

    @property
    def review(self):
        return [a for a in self.answers if a[2] == 1]

    @property
    def fails(self):
        return sum(1 for a in self.review if a[0] == 1)

    @property
    def fail_rate(self):
        r = self.review
        return self.fails / len(r) if r else None

    @property
    def timer_hits(self):
        return sum(1 for a in self.answers if a[1] >= TIMER_MS)

    @property
    def median_ms(self):
        return st.median(a[1] for a in self.answers) if self.answers else None


def load_cards(rd: ReviewData, deck_prefix: str | None) -> list[Card]:
    kinds = model_kinds(rd)
    notes = {n.id: n for n in rd.notes}
    out: dict[int, Card] = {}
    for c in rd.cards:
        cid, deck, ord_ = c.id, c.deck, c.ord
        if deck_prefix and not (deck == deck_prefix or deck.startswith(deck_prefix + "::")):
            continue
        note = notes[c.nid]
        f, tagl = note.values, note.tags
        kind = next((t.split("::")[-1] for t in tagl if t.startswith("asl::type::")), None)
        kind = kind or kinds.get(note.mid)
        if not kind:
            continue                    # not one of our cards (other decks in a .colpkg)
        try:
            mem = json.loads(c.data) if c.data else {}
        except json.JSONDecodeError:
            mem = {}
        if kind == "code":
            m = {"typed_chars": C.typed_chars(_b64(f[1]), _b64(f[2])),
                 "typed_lines": len(C.typed(_b64(f[1]), _b64(f[2])))}
        elif kind in ("concept", "timeline"):
            ans = f[1] if len(f) > 1 else ""
            bold = re.findall(r"<(?:strong|b)>(.*?)</(?:strong|b)>", ans, re.S)
            m = {"answer_chars": len(_strip(ans)),
                 "bold_chars": len(_strip(bold[0])) if bold else 0}
        elif kind == "cloze":
            g = C.gap_answers(re.sub(r"\\[()\[\]]", "$", _strip(f[0])))   # as written: $x$
            m = {"gap_chars": g.get(ord_ + 1, 0), "gaps": len(g),
                 "hook": int(bool(_strip(f[2]))) if len(f) > 2 else 0}
        else:
            m = {}
        out[cid] = Card(
            cid=cid, nid=c.nid, guid=note.guid, ord=ord_, deck=deck, kind=kind,
            card_id=next((t.split("::")[-1] for t in tagl if t.startswith("asl::id::")), ""),
            std=next((t.split("::")[-1] for t in tagl if t.startswith("asl::std::")), ""),
            front=_strip(f[0])[:90].replace("\n", " "),
            created=dt.datetime.fromtimestamp(c.nid / 1000), ivl=c.ivl, lapses=c.lapses,
            queue=c.queue, ctype=c.type, difficulty=mem.get("d"), stability=mem.get("s"),
            measures=m)
    for r in rd.revlog:
        if r.cid in out and r.type in (0, 1, 2):
            out[r.cid].answers.append((r.ease, r.ms, r.type))
    return list(out.values())


# ---- the tables -----------------------------------------------------------------------

def card_frame(cards: list[Card], join: dict[str, dict]) -> pd.DataFrame:
    """One row per card; `join` (GUID -> card-file columns) fills file, tags, source."""
    rows = []
    for c in cards:
        j = join.get(c.guid) or {}
        rev = c.review
        rows.append({
            "cid": c.cid, "nid": c.nid, "guid": c.guid, "ord": c.ord, "deck": c.deck,
            "kind": c.kind, "card_id": c.card_id, "std": c.std, "front": c.front,
            "matched": bool(j), "file": j.get("file", ""), "tags": j.get("tags", []),
            "source": j.get("source", ""), "source_note": j.get("source_note", ""),
            **{m: c.measures.get(m) for m in MEASURES},
            "created": c.created, "ivl": c.ivl, "lapses": c.lapses, "queue": c.queue,
            "ctype": c.ctype, "difficulty": c.difficulty, "stability": c.stability,
            "answers": len(c.answers), "reviews": len(rev), "fails": c.fails,
            "fail_rate": c.fail_rate, "median_ms": c.median_ms, "timer_hits": c.timer_hits,
        })
    df = pd.DataFrame(rows, columns=list(CARD_COLUMNS_ORDER))
    for m in MEASURES:
        df[m] = pd.array(df[m].tolist(), dtype="Int64")        # whole numbers; <NA> where none
    df["median_ms"] = pd.Series([c.median_ms for c in cards], dtype=object)   # as computed
    return df


CARD_COLUMNS_ORDER = ("cid", "nid", "guid", "ord", "deck", "kind", "card_id", "std", "front",
                      "matched", "file", "tags", "source", "source_note", *MEASURES, "created",
                      "ivl", "lapses", "queue", "ctype", "difficulty", "stability", "answers",
                      "reviews", "fails", "fail_rate", "median_ms", "timer_hits")


def review_frame(rd: ReviewData, cids: set[int]) -> pd.DataFrame:
    rows = [(r.cid, dt.datetime.fromtimestamp(r.id / 1000), r.ease, r.ms, r.type)
            for r in rd.revlog if r.cid in cids]
    return pd.DataFrame(rows, columns=["cid", "time", "ease", "ms", "type"])


def card_files(home: Home) -> dict[str, dict]:
    """GUID -> the card file's columns, for every card in the card home's decks."""
    from ..core.build import guid
    from ..core.config import load_deck
    out: dict[str, dict] = {}
    if not home.path:
        return out
    for d in sorted(p for p in home.path.iterdir() if (p / "deck.yaml").is_file()):
        deck = load_deck(d)
        for f in deck.files(include_examples=True):
            try:
                cards = C.load_file(f)
            except C.CardFileError:
                continue                    # a broken file: its cards stay unmatched
            for card in cards:
                src = str(card.get("source") or "")
                m = SOURCE_NOTE.search(src)
                out[guid(deck, f, card)] = {
                    "file": f"{d.name}/{f.name}", "tags": list(card.get("tags") or []),
                    "source": src, "source_note": m.group(1).strip() if m else ""}
    return out
