"""Build an Anki .apkg from one or more deck folders / card files.

    asl build path/to/deck [more decks or files] [-o out.apkg]

Deck naming (deck.yaml `deck:` is the folder's Anki deck, e.g. "Study Loop::Tasklog"):
  <stem>.yaml       -> <deck>::<Stem>          (subdecks: true, the default)
  <a>__<b>.yaml     -> <deck>::<A>::<B>
  subdecks: false   -> every file goes straight into <deck>
  files: {x.yaml: {deck: "Other::Name"}}  -> explicit deck for one file

Note GUIDs come from the card `id` (stable: editing a card's front updates it in
place instead of creating a duplicate). See docs/card-format.md.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
import zlib
from pathlib import Path

import genanki

from studyloop.core import cards as C
from studyloop.core.config import ANKI, Deck, all_packs, load_pack
from studyloop.core.config.vault import vault_for as vault_of
from studyloop.core.config.vault import vault_index
from studyloop.core.registry import NoteContext, registry

TPL = ANKI / "templates"
VENDOR = ANKI / "vendor"

# media name in templates -> source file (modes are bundled from all packs)
STATIC_MEDIA = {
    "_codemirror.js": VENDOR / "_codemirror.js",
    "_codemirror.css": VENDOR / "_codemirror.css",
    "_simple.js": VENDOR / "_simple.js",
    "_closebrackets.js": VENDOR / "_closebrackets.js",
    "_matchbrackets.js": VENDOR / "_matchbrackets.js",
    "_cards.js": TPL / "_cards.js",
}


# ---- text helpers ------------------------------------------------------------

def b64(s) -> str:
    return base64.b64encode((s or "").encode("utf-8")).decode("ascii")


MATH_BLOCK, MATH_INLINE = C.MATH_BLOCK, C.MATH_INLINE
WIKILINK = re.compile(r"(!?)\[\[([^\]|]+?)(?:\|([^\]]*))?\]\]")
MD_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")


def text(s, math: bool = False) -> str:
    """HTML-escape; `code` -> <code>, **bold** -> <strong> (never inside code).
    `math`: Obsidian's `$x$` / `$$x$$` become Anki's MathJax `\\(x\\)` / `\\[x\\]`.
    Line breaks and indentation are kept by the CSS."""
    spans, parts = [], []
    for is_code, t in C._split_code(str(s or "")):
        t = html.escape(t, quote=False)
        if is_code:
            parts.append(f"\x01{len(spans)}\x02")
            spans.append(t)
        else:
            if math:
                t = MATH_INLINE.sub(r"\\(\1\\)", MATH_BLOCK.sub(r"\\[\1\\]", t))
            parts.append(t)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", "".join(parts), flags=re.S)
    return re.sub("\x01(\\d+)\x02", lambda m: f"<code>{spans[int(m.group(1))]}</code>", out)


def link_text(target: str, alias: str | None) -> str:
    """`[[Note#Section|alias]]` as shown on a card: the alias, else `Note › Section`."""
    if alias:
        return alias
    return " › ".join(p for p in re.split(r"[#^]", target, maxsplit=1) if p)


def vault_links(s: str, find_file, media: dict[str, Path]) -> str:
    """Rendered field: `![[img.png]]` / `![](img.png)` -> <img> (file added to `media`),
    `[[Note]]` -> its name. `find_file(name)` returns the file or None."""
    def embed(name: str, fallback: str) -> str:
        f = find_file(name)
        if not f or f.suffix.lower() not in C.IMAGE_EXT:
            return fallback
        media.setdefault(f.name, f)
        return f'<img src="{html.escape(f.name)}">'

    s = MD_IMAGE.sub(lambda m: embed(m.group(1), m.group(0)), s)
    return WIKILINK.sub(lambda m: embed(m.group(2), m.group(0)) if m.group(1)
                        else link_text(m.group(2), m.group(3)), s)


def titled(seg: str) -> str:
    return seg.replace("_", " ").replace("-", " ").strip().title()


# ---- assets & models -----------------------------------------------------------

def bundle_modes() -> str:
    parts = []
    for p in all_packs():
        cfg = load_pack(p.name)
        mf = p / cfg.get("mode_file", "mode.js")
        if mf.is_file():
            parts.append(f"/* pack: {p.name} */\n" + mf.read_text(encoding="utf-8"))
    return "\n;\n".join(parts)


def stage_media(tmp: Path) -> tuple[list[str], dict[str, str]]:
    """Copy media under content-hashed names (Anki caches media by name, so a
    changed file must get a new name). Returns (paths, template renames)."""
    sources = {k: v.read_text(encoding="utf-8") for k, v in STATIC_MEDIA.items()}
    sources["_modes.js"] = bundle_modes()
    digest = hashlib.sha1("".join(sources[k] for k in sorted(sources)).encode()).hexdigest()[:8]
    renames, paths = {}, []
    for name, content in sources.items():
        new = f"_asl{digest}{name}"
        (tmp / new).write_text(content, encoding="utf-8")
        renames[name] = new
        paths.append(str(tmp / new))
    return paths, renames


def build_models(renames) -> dict[str, genanki.Model]:
    """card type -> its Anki note type; types sharing a model_id share one model."""
    css = (TPL / "style.css").read_text(encoding="utf-8")
    by_id: dict[int, genanki.Model] = {}
    out = {}
    for t in registry().card_types.values():
        def template(name, _dir=t.templates_dir):
            text = (_dir / name).read_text(encoding="utf-8")
            for old, new in renames.items():
                text = text.replace(f'"{old}"', f'"{new}"')
            return text
        if t.model_id not in by_id:
            by_id[t.model_id] = t.model(template, css + t.css)
        out[t.name] = by_id[t.model_id]
    return out


# ---- decks, guids, notes -------------------------------------------------------------

def deck_name(deck: Deck, f: Path) -> str:
    explicit = deck.file_opts(f).get("deck")
    if explicit is not None:
        if explicit == "":
            return deck.name
        return explicit if "::" in explicit else f"{deck.name}::{explicit}"
    if not deck.cfg.get("subdecks", True):
        return deck.name
    return deck.name + "::" + "::".join(titled(s) for s in f.stem.lstrip("_").split("__"))


def deck_id(name: str) -> int:
    return 1700000000 + zlib.crc32(name.encode()) % 100000000


def guid(deck: Deck, f: Path, card: dict) -> str:
    if card.get("guid"):
        return str(card["guid"])
    kind = "concept" if card["type"] != "code" else "code"
    front = card.get("instruction") or card.get("question") or card.get("text")
    if deck.cfg.get("guid") == "legacy-kata":
        key = f.stem if not deck.cfg.get("legacy_additional") else f"additional__{f.stem}"
        return genanki.guid_for(key, kind, front)
    if card.get("id"):
        # only the id (plus an optional namespace): renaming decks or folders never
        # changes a GUID, so Anki keeps the review history
        return genanki.guid_for(deck.cfg.get("guid_namespace") or "asl-id", str(card["id"]))
    return genanki.guid_for(deck.name, f.stem, kind, front)


def pack_mode(deck: Deck, f: Path, card: dict) -> str:
    pack = card.get("pack") or deck.file_opts(f).get("pack") or deck.pack
    if not pack:
        return "text/plain"
    try:
        return load_pack(pack).get("codemirror_mode", pack)
    except SystemExit:
        return pack


class Note(NoteContext):
    """How card types render fields: vault links, math, media, code for the editor."""

    def __init__(self, deck: Deck, file: Path, card: dict, find_file, media: dict[str, Path]):
        self.deck, self.file = deck, file
        self.pack_mode = pack_mode(deck, file, card)
        self.find_file, self.files = find_file, media

    def text(self, s) -> str:
        return text(s)

    def rich(self, s) -> str:
        return vault_links(text(str(s or "").strip("\n"), math=True), self.find_file, self.files)

    def code(self, s) -> str:
        return b64(s)

    def source(self, card: dict) -> str:
        return vault_links(text(card.get("source", "")), self.find_file, self.files)

    def media(self, name, kind: str) -> str:
        name = str(name or "").strip()
        if not name:
            return ""
        f = self.find_file(name)
        if f:
            self.files.setdefault(f.name, f)
        return f"[sound:{html.escape(name)}]" if kind == "audio" else f'<img src="{html.escape(name)}">'

    def links(self, v) -> str:
        items = v if isinstance(v, list) else ([v] if v else [])
        return " · ".join(vault_links(text(str(i)), self.find_file, self.files) for i in items)


def make_note(deck, f, card, models, find_file=lambda _n: None,
              media: dict[str, Path] | None = None) -> genanki.Note:
    t = registry().card_types.get(card["type"])
    if t is None:
        raise SystemExit(f"{f.name}: {C.label(card)}: unknown card type `{card['type']}` "
                         "(`asl lint` lists the installed ones)")
    tags = [str(x).replace(" ", "_") for x in card.get("tags", [])]
    if card.get("id"):
        tags.append(f"asl::id::{card['id']}")
    if card.get("std"):
        tags.append(f"asl::std::v{card['std']}")
    tags.append(f"asl::type::{card['type']}")
    if card.get("tts"):
        tags.append("asl::tts")                 # audio from text-to-speech, not native
    ctx = Note(deck, f, card, find_file, {} if media is None else media)
    fields = t.to_fields(card, ctx)
    return genanki.Note(model=models[t.name], fields=fields, guid=guid(deck, f, card),
                        tags=tags + t.tags(card))


# ---- deck options presets (patched into the package after genanki) -----------

def make_conf(cid: int, name: str, p: dict) -> dict:
    return {
        "id": cid, "mod": int(time.time()), "name": name, "usn": -1, "maxTaken": 60,
        "autoplay": True, "timer": 0, "replayq": True, "dyn": False,
        "new": {"bury": False, "delays": p.get("learning_steps", [1.0, 10.0]),
                "initialFactor": 2500, "ints": [1, 4, 7],
                "order": 1 if p.get("order") == "sequential" else 0,  # 1 = order added
                "perDay": p.get("new_per_day", 14), "separate": True},
        # v3 scheduler: 1 = gather new cards by position (across subdecks), 0 = deck by deck
        "newGatherPriority": 1 if p.get("gather") == "position" else 0,
        "rev": {"bury": False, "ease4": 1.3, "fuzz": 0.05, "ivlFct": 1.0,
                "maxIvl": 36500, "perDay": p.get("max_reviews", 9999),
                "hardFactor": 1.2, "minSpace": 1},
        "lapse": {"delays": p.get("relearn_steps", [10.0]),
                  "leechAction": p.get("leech_action", 1),
                  "leechFails": p.get("leech_fails", 5), "minInt": 1, "mult": 0.1},
    }


def conf_id(deck_name: str, preset: str, p: dict) -> int:
    """One options group per deck folder and preset, so two projects' `default`
    presets never overwrite each other."""
    return int(p.get("conf_id") or 1000 + zlib.crc32(f"{deck_name}:{preset}".encode()) % 9000000)


def _deck_obj(did, name, cid):
    return {"id": did, "mod": int(time.time()), "name": name, "usn": -1, "lrnToday": [0, 0],
            "revToday": [0, 0], "newToday": [0, 0], "timeToday": [0, 0],
            "collapsed": False, "browserCollapsed": False, "desc": "", "dyn": 0,
            "conf": cid, "extendNew": 0, "extendRev": 0}


def postprocess(apkg: Path, deck_presets: dict[str, tuple[int, dict, str]],
                sequential_order: list[str],
                group_defaults: list[tuple[str, tuple[int, dict, str]]] = (),
                positions: dict[str, int] | None = None):
    """deck_presets: anki deck name -> (conf id, preset dict, preset label).
    Adds the presets, creates missing parent decks, stamps sequential order."""
    tmp = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(apkg) as z:
        names = z.namelist()
        z.extractall(tmp)
    db = next(n for n in names if n.startswith("collection.anki2"))
    con = sqlite3.connect(tmp / db)
    cur = con.cursor()
    decks = json.loads(cur.execute("select decks from col").fetchone()[0])
    dconf = json.loads(cur.execute("select dconf from col").fetchone()[0])
    for cid, preset, plabel in [*deck_presets.values(), *(c for _n, c in group_defaults)]:
        dconf[str(cid)] = make_conf(cid, plabel, preset)

    existing = {d["name"] for d in decks.values()}
    parents = sorted({"::".join(parts[:i]) for parts in (n.split("::") for n in existing)
                      for i in range(1, len(parts))} - existing)
    for pname in parents:
        # a parent takes the `default` preset of the deck folder it belongs to
        conf = next((c[0] for name, c in group_defaults
                     if name == pname or name.startswith(pname + "::")
                     or pname.startswith(name + "::")), 1)   # parents inside the folder's deck too
        pid = 1600000000 + zlib.crc32(pname.encode()) % 90000000
        decks[str(pid)] = _deck_obj(pid, pname, conf)
    for d in decks.values():
        if d.get("name") in deck_presets:
            d["conf"] = deck_presets[d["name"]][0]
    cur.execute("update col set decks = ?, dconf = ?", (json.dumps(decks), json.dumps(dconf)))

    # Anki shows new cards of a sequential preset by `due`; stamp build order.
    name_by_id = {int(k): d.get("name", "") for k, d in decks.items()}
    seq = set(sequential_order)
    rows = cur.execute("select id, nid, did from cards order by nid").fetchall()
    rank = {n: i for i, n in enumerate(sequential_order)}
    picked = sorted((rank[name_by_id[did]], nid, cid) for cid, nid, did in rows
                    if name_by_id.get(did) in seq)
    for pos, (_r, _n, cid) in enumerate(picked, start=1):
        cur.execute("update cards set due = ?, type = 0, queue = 0 where id = ?", (pos, cid))
    # language decks: the planner's order (card id number) across all their subdecks
    if positions:
        start = len(picked) + 1
        for cid, g in cur.execute("select c.id, n.guid from cards c join notes n on n.id = c.nid").fetchall():
            if g in positions:
                cur.execute("update cards set due = ?, type = 0, queue = 0 where id = ?",
                            (start + positions[g], cid))
    con.commit()
    con.close()
    with zipfile.ZipFile(apkg, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.write(tmp / n, n)
    shutil.rmtree(tmp)


# ---- main --------------------------------------------------------------------------

def media_index(deck: Deck) -> dict[str, Path]:
    """Language decks: clips and screenshots live in `media_dir` (outside the vault)."""
    from studyloop.core.config import native_path
    d = native_path(deck.cfg["media_dir"]) if deck.cfg.get("media_dir") else None
    if not d or not d.is_dir():
        return {}
    return {p.name.lower(): p for p in d.rglob("*") if p.is_file()}


def id_number(cid) -> int:
    m = re.search(r"(\d+)$", str(cid))
    return int(m.group(1)) if m else 0


def build(groups: list[tuple[Deck, list[Path]]], out: Path) -> int:
    tmp = Path(tempfile.mkdtemp())
    media, renames = stage_media(tmp)
    models = build_models(renames)
    note_media: dict[str, Path] = {}
    anki_decks: dict[str, genanki.Deck] = {}
    deck_presets: dict[str, tuple[int, dict, str]] = {}
    sequential: list[str] = []
    group_defaults = []
    total, anki_cards, no_id, guids = 0, 0, 0, {}
    positions: dict[str, int] = {}
    for deck, files in groups:
        presets = deck.presets()
        group_defaults.append((deck.name, (conf_id(deck.name, "default", presets["default"]),
                                           presets["default"], presets["default"].get("name") or f"{deck.name} default")))
        vault = vault_of(deck.path)
        lang_media = media_index(deck)
        def find_file(n, _f=None, _v=vault, _m=lang_media):
            if Path(n).name.lower() in _m:
                return _m[Path(n).name.lower()]
            hit = (_f.parent / n) if _f else None
            if hit and hit.is_file():
                return hit
            return vault_index(_v)[1].get(Path(n).name.lower()) if _v else None
        for f in files:
            name = deck_name(deck, f)
            if name not in anki_decks:
                anki_decks[name] = genanki.Deck(deck_id(name), name)
                pname = deck.file_opts(f).get("preset", "default")
                p = presets.get(pname) or presets["default"]
                deck_presets[name] = (conf_id(deck.name, pname, p), p, p.get("name") or f"{deck.name} {pname}")
                if p.get("order") == "sequential":
                    sequential.append(name)
            for card in C.load_file(f):
                note = make_note(deck, f, card, models,
                                 lambda n, _f=f: find_file(n, _f), note_media)
                if note.guid in guids:
                    raise SystemExit(f"Duplicate GUID: {C.label(card)} ({f.name}) and "
                                     f"{guids[note.guid]} — ids must be unique.")
                guids[note.guid] = f"{C.label(card)} ({f.name})"
                anki_decks[name].add_note(note)
                if deck.kind_spec.order_by_id and card.get("id"):
                    positions[note.guid] = id_number(card["id"])
                total += 1
                anki_cards += len(note.cards)
                no_id += not card.get("id") and not card.get("guid")
    if not total:
        print("No cards found.")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    pkg = genanki.Package(list(anki_decks.values()))
    pkg.media_files = media + [str(p) for p in note_media.values()]
    pkg.write_to_file(str(out))
    postprocess(out, deck_presets, sequential, group_defaults, positions)
    shutil.rmtree(tmp)
    extra = f" ({anki_cards} Anki cards)" if anki_cards != total else ""
    print(f"Wrote {out}: {total} cards{extra} in {len(anki_decks)} deck(s).")
    if no_id:
        print(f"  [!] {no_id} card(s) without an id: their GUID follows the front text, "
              "so editing the front will import a duplicate. Run `asl fix`.")
    return 0
