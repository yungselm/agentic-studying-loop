"""Read notes, card states and media from an Anki export (.apkg/.colpkg), legacy or zstd format."""
from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


def unzstd(b: bytes) -> bytes:
    if b[:4] != ZSTD_MAGIC:
        return b
    import zstandard
    return zstandard.ZstdDecompressor().stream_reader(b).read()


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


@dataclass
class Note:
    id: int
    model: str
    fields: dict[str, str]
    tags: list[str]
    reviewed: bool = False       # a card is in learning/review now (not new, not reset)
    mature: bool = False         # a card in review with interval >= 21 days
    suspended: bool = False      # every card suspended


@dataclass
class Export:
    path: Path
    notes: list[Note] = field(default_factory=list)
    media: dict[str, str] = field(default_factory=dict)   # file name -> zip member

    def read_media(self, name: str) -> bytes | None:
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


def _models(con: sqlite3.Connection) -> dict[int, tuple[str, list[str]]]:
    try:
        names = dict(con.execute("select id, name from notetypes"))
        flds: dict[int, list[str]] = {}
        for ntid, name in con.execute("select ntid, name from fields order by ntid, ord"):
            flds.setdefault(ntid, []).append(name)
        return {mid: (n, flds.get(mid, [])) for mid, n in names.items()}
    except sqlite3.OperationalError:
        models = json.loads(con.execute("select models from col").fetchone()[0])
        return {int(k): (m["name"], [f["name"] for f in m["flds"]]) for k, m in models.items()}


def read_export(path: Path) -> Export:
    from ..stats import open_collection
    path = Path(path).expanduser()
    con, tmp = open_collection(path)
    try:
        models = _models(con)
        state: dict[int, list[tuple[int, int, int]]] = {}
        for nid, ctype, queue, ivl in con.execute("select nid, type, queue, ivl from cards"):
            state.setdefault(nid, []).append((ctype, queue, ivl))
        ex = Export(path)
        for nid, mid, flds, tags in con.execute("select id, mid, flds, tags from notes order by id"):
            name, fnames = models.get(mid, ("?", []))
            vals = flds.split("\x1f")
            cards = state.get(nid, [])
            ex.notes.append(Note(
                nid, name, dict(zip(fnames, vals)), tags.split(),
                reviewed=any(t in (1, 2, 3) for t, _, _ in cards),
                mature=any(t == 2 and ivl >= 21 for t, _, ivl in cards),
                suspended=bool(cards) and all(q == -1 for _, q, _ in cards)))
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(path) as z:
        ex.media = _media_map(z)
    return ex
