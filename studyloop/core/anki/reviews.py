# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Read an Anki export (.apkg / .colpkg; legacy or zstd) into plain tables.

The one reader for everything that looks at review data: `asl stats` works per card and
review, the language decks per note (seed, sync, mined decks, Game Gengo) and with the media."""
from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
MATURE_IVL = 21              # days; Anki's own line between young and mature


class NoteType(NamedTuple):
    id: int
    name: str
    fields: list[str]


class Card(NamedTuple):
    id: int
    nid: int
    deck: str                # full name, `Parent::Child`; the original deck while in a filtered one
    ord: int                 # template (or cloze gap) number, from 0
    type: int                # 0 new, 1 learning, 2 review, 3 relearning
    queue: int               # -1 suspended, -2/-3 buried
    ivl: int                 # days
    lapses: int
    data: str                # JSON; FSRS memory state as "d" (difficulty), "s" (stability)


class Review(NamedTuple):
    id: int                  # epoch ms of the answer
    cid: int
    ease: int                # 1 Again .. 4 Easy
    ms: int                  # answer time
    type: int                # 0 learning, 1 review, 2 relearning, 3 filtered, 4 manual


@dataclass
class Note:
    id: int                  # epoch ms of creation
    mid: int
    model: str               # note type name
    values: list[str]        # field values in note type order
    fields: dict[str, str]   # the same, by field name
    tags: list[str]
    guid: str = ""           # the build's GUID: joins a note back to its card file
    reviewed: bool = False   # a card is in learning/review now (not new, not reset)
    mature: bool = False     # a card in review with interval >= 21 days
    suspended: bool = False  # every card suspended
    reviews: int = 0         # review-phase answers (all cards of the note)
    fails: int = 0           # of those, Again


@dataclass
class ReviewData:
    """An Anki export as plain tables. Get it with `read_export`.

    Attributes
    ----------
    path : Path
    note_types : dict
        Id to `NoteType`.
    decks : dict
        Id to full deck name (``A::B``).
    notes : list of Note
        By id, which is creation order.
    cards : list of Card
    revlog : list of Review
        Every answer; empty for an export without scheduling data.
    media : dict
        File name to zip member; read with `read_media`.
    """
    path: Path
    note_types: dict[int, NoteType] = field(default_factory=dict)
    decks: dict[int, str] = field(default_factory=dict)
    notes: list[Note] = field(default_factory=list)            # by id (= creation order)
    cards: list[Card] = field(default_factory=list)
    revlog: list[Review] = field(default_factory=list)
    media: dict[str, str] = field(default_factory=dict)        # file name -> zip member

    def read_media(self, name: str) -> bytes | None:
        """One media file's bytes, or None if the export doesn't have it."""
        member = self.media.get(name)
        if member is None:
            return None
        with zipfile.ZipFile(self.path) as z:
            return unzstd(z.read(member))

    def extract_media(self, names: list[str], dest: Path) -> int:
        """Copy the named media files to `dest` (skips files already there). Returns the count written."""
        dest.mkdir(parents=True, exist_ok=True)
        n = 0
        with zipfile.ZipFile(self.path) as z:
            for name in names:
                out = dest / Path(name).name
                member = self.media.get(name)
                if member is None or out.exists():
                    continue
                out.write_bytes(unzstd(z.read(member)))
                n += 1
        return n


def read_export(path: Path) -> ReviewData:
    """Read an Anki export (.apkg or .colpkg, legacy or zstd-compressed).

    Examples
    --------
    The tasklog example deck, built with ``asl build`` (no reviews yet):

    >>> rd = read_export(Path("tasklog.apkg"))
    >>> len(rd.notes), len(rd.cards), len(rd.revlog)
    (8, 12, 0)
    >>> sorted(nt.name for nt in rd.note_types.values())
    ['Cloze Card', 'Code Editor Card', 'Concept Card']
    >>> rd.notes[0].tags
    ['tasklog', 'files', 'asl::id::tsk-001', 'asl::std::v1', 'asl::type::code']
    """
    path = Path(path).expanduser()
    rd = ReviewData(path)
    with _open(path) as con:
        rd.note_types = _note_types(con)
        rd.decks = _decks(con)
        rd.cards = [Card(cid, nid, rd.decks.get(odid or did, "?"), ord_, ctype, queue, ivl, lapses,
                         data or "")
                    for cid, nid, did, odid, ord_, ctype, queue, ivl, lapses, data in con.execute(
                        "select id, nid, did, odid, ord, type, queue, ivl, lapses, data from cards")]
        with contextlib.suppress(sqlite3.OperationalError):     # exports without a revlog
            rd.revlog = [Review(*r) for r in con.execute(
                "select id, cid, ease, time, type from revlog order by id")]
        rows = con.execute("select id, mid, flds, tags, guid from notes order by id").fetchall()
    rd.notes = _notes(rows, rd)
    with zipfile.ZipFile(path) as z:
        rd.media = _media_map(z)
    return rd


def _notes(rows, rd: ReviewData) -> list[Note]:
    by_note: dict[int, list[Card]] = {}
    for c in rd.cards:
        by_note.setdefault(c.nid, []).append(c)
    nid_of = {c.id: c.nid for c in rd.cards}
    rev: dict[int, list[int]] = {}
    for r in rd.revlog:
        if r.type == 1 and r.cid in nid_of:
            n = rev.setdefault(nid_of[r.cid], [0, 0])
            n[0] += 1
            n[1] += r.ease == 1
    out = []
    for nid, mid, flds, tags, guid in rows:
        nt = rd.note_types.get(mid, NoteType(mid, "?", []))
        vals = flds.split("\x1f")
        cards = by_note.get(nid, [])
        reviews, fails = rev.get(nid, (0, 0))
        out.append(Note(
            nid, mid, nt.name, vals, dict(zip(nt.fields, vals)), tags.split(), guid,
            reviewed=any(c.type in (1, 2, 3) for c in cards),
            mature=any(c.type == 2 and c.ivl >= MATURE_IVL for c in cards),
            suspended=bool(cards) and all(c.queue == -1 for c in cards),
            reviews=reviews, fails=fails))
    return out


@contextlib.contextmanager
def _open(path: Path) -> Iterator[sqlite3.Connection]:
    """The export's collection as a sqlite database in a temp folder (removed afterwards)."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for name in ("collection.anki21b", "collection.anki21", "collection.anki2"):
            if name in names:
                raw = z.read(name)
                break
        else:
            raise SystemExit(f"{path}: no collection inside; is this an Anki export?")
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "collection.sqlite"
        db.write_bytes(unzstd(raw))
        con = sqlite3.connect(db)
        try:
            yield con
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _note_types(con: sqlite3.Connection) -> dict[int, NoteType]:
    try:                                            # schema 18+: tables
        names = dict(con.execute("select id, name from notetypes"))
        flds: dict[int, list[str]] = {}
        for ntid, name in con.execute("select ntid, name from fields order by ntid, ord"):
            flds.setdefault(ntid, []).append(name)
        return {mid: NoteType(mid, n, flds.get(mid, [])) for mid, n in names.items()}
    except sqlite3.OperationalError:                # legacy: JSON in col
        models = json.loads(con.execute("select models from col").fetchone()[0])
        return {int(k): NoteType(int(k), m["name"], [f["name"] for f in m["flds"]])
                for k, m in models.items()}


def _decks(con: sqlite3.Connection) -> dict[int, str]:
    try:
        return {did: name.replace("\x1f", "::")
                for did, name in con.execute("select id, name from decks")}
    except sqlite3.OperationalError:
        decks = json.loads(con.execute("select decks from col").fetchone()[0])
        return {int(k): v["name"] for k, v in decks.items()}


# ---- zstd + the media map (legacy JSON or protobuf) ------------------------------------

def unzstd(b: bytes) -> bytes:
    if b[:4] != ZSTD_MAGIC:
        return b
    import zstandard
    return zstandard.ZstdDecompressor().stream_reader(b).read()


def _media_map(z: zipfile.ZipFile) -> dict[str, str]:
    raw = unzstd(z.read("media")) if "media" in z.namelist() else b""
    try:
        return {v: k for k, v in json.loads(raw or b"{}").items()}
    except (ValueError, UnicodeDecodeError):
        pass
    out: dict[str, str] = {}
    entries = (v for fn, v in _proto(raw) if fn == 1)
    for idx, entry in enumerate(entries):
        name, member = None, str(idx)
        for fn, v in _proto(entry):
            if fn == 1:
                name = v.decode("utf-8")
            elif fn == 255:
                member = str(v)
        if name:
            out[name] = member
    return out


def _varint(b: bytes, i: int) -> tuple[int, int]:
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        s += 7
        if x < 0x80:
            return r, i


def _proto(b: bytes) -> Iterator[tuple[int, object]]:
    """Minimal protobuf reader: (field number, value) pairs."""
    i = 0
    while i < len(b):
        key, i = _varint(b, i)
        fn, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 2:
            n, i = _varint(b, i)
            v, i = b[i:i + n], i + n
        elif wt == 1:
            v, i = b[i:i + 8], i + 8
        elif wt == 5:
            v, i = b[i:i + 4], i + 4
        else:
            raise ValueError(f"protobuf wire type {wt}")
        yield fn, v
