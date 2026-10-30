"""Fill in the bookkeeping so nobody has to do it by hand.

    asl ids path/to/deck          # next free id + cards without one (read-only)
    asl fix path/to/deck          # write it all (keeps comments and formatting):
      - `id:` for every card without one (<prefix>-NNN, never reusing retired_ids)
      - `std: <standards_version>` on those new cards (from studyloop.yaml)
      - a row in Overview.md for every card that has none (status `draft`)

So an agent can write a card without id/std/index row and let `asl fix` add them.

Migrating a deck imported with front-text GUIDs (deck.yaml `guid: legacy-kata`):
`fix` also freezes each card's current GUID as a `guid:` field, so switching to
ids creates no duplicates in Anki. Afterwards remove `guid: legacy-kata`.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import cards as C
from .build import guid as compute_guid
from .config import Deck, find_home, read_keep, write_keep

ITEM = re.compile(r"^- ")
INDEX_SECTION = "## New cards (added by `asl fix`, move rows where they belong)"


def _num(cid: str) -> int:
    m = re.search(r"-(\d+)$", str(cid))
    return int(m.group(1)) if m else 0


def used_ids(deck: Deck, files: list[Path]) -> set[str]:
    ids = {str(i) for i in deck.cfg.get("retired_ids") or []}
    for f in deck.files(include_examples=True) + files:
        ids |= {str(c["id"]) for c in C.load_file(f) if c.get("id")}
    return ids


def next_id(deck: Deck, files: list[Path]) -> str:
    prefix = deck.cfg.get("prefix") or "card"
    nums = [_num(i) for i in used_ids(deck, files) if str(i).startswith(prefix + "-")]
    return f"{prefix}-{(max(nums) if nums else 0) + 1:03d}"


class FixError(Exception):
    pass


def _plan(lines: list[str], parsed: list[dict], starts: list[int], new: set[int],
          std: int | None, legacy_guid) -> list[tuple[int, dict]]:
    """Per item: which keys to add, worked out on the ORIGINAL lines."""
    plan = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        m = re.match(r"-(\s+)\S", lines[start])
        if not m or lines[start][m.end() - 1] in "{[" or ":" not in lines[start]:
            raise FixError(f"item at line {start + 1} isn't a block mapping (`- key: value`); "
                           "add its id by hand")
        indent = " " * (1 + len(m.group(1)))
        keys = {}
        for i in range(start, end):
            km = re.match(rf"^(?:-\s+|{indent})(id|guid|std):(.*)$", lines[i])
            if km:
                keys[km.group(1)] = (i, km.group(2).strip())
        card = parsed[idx]
        add = {}
        if "id" not in keys or not keys["id"][1]:
            add["id"] = card["id"]
        if idx in new and std and "std" not in keys:
            add["std"] = std
        if legacy_guid and "guid" not in keys and not card.get("guid"):
            add["guid"] = legacy_guid(card)
        if add:
            plan.append((idx, {"add": add, "indent": indent, "keys": keys,
                               "comment": C.id_comment_line(lines, start)}))
    return plan


def fix_file(deck: Deck, f: Path, files: list[Path], std: int | None) -> int:
    text, fmt = read_keep(f)
    lines = text.split("\n")
    parsed = C.load_file(f)
    starts = C.item_starts(lines)
    if len(starts) != len(parsed):
        print(f"  [!] {f.name}: couldn't match YAML items to lines; fix by hand.")
        return 0
    prefix = deck.cfg.get("prefix") or "card"
    n = _num(next_id(deck, files))
    new = set()
    for i, card in enumerate(parsed):           # assign in file order
        if not card.get("id"):
            card["id"], n = f"{prefix}-{n:03d}", n + 1
            new.add(i)
    legacy = (lambda c: compute_guid(deck, f, c)) if deck.cfg.get("guid") == "legacy-kata" else None
    try:
        plan = _plan(lines, parsed, starts, new, std, legacy)
    except FixError as e:
        print(f"  [!] {f.name}: {e}")
        return 0
    for idx, p in reversed(plan):               # bottom-up: earlier line numbers stay valid
        start, add, ind = starts[idx], p["add"], p["indent"]
        fmt_val = {"id": str, "std": str, "guid": lambda g: f'"{g}"'}
        if "id" in add and "id" in p["keys"]:   # empty `id:` line: fill it in place
            i = p["keys"]["id"][0]
            lines[i] = re.sub(r"id:\s*$", f"id: {add.pop('id')}", lines[i])
        if add:
            new_lines = [f"{k}: {fmt_val[k](v)}" for k, v in add.items()]
            head = lines[start][len(ind):]
            lines[start:start + 1] = (["-" + ind[1:] + new_lines[0]]
                                      + [ind + x for x in new_lines[1:]] + [ind + head])
        if p["comment"] is not None:            # the id is a field now
            del lines[p["comment"]]
    new_text = "\n".join(lines)
    _verify(f, parsed, new_text, {idx: p["add"] for idx, p in plan})
    write_keep(f, new_text, fmt)
    return len(plan)


def _verify(f: Path, before: list[dict], new_text: str, added: dict[int, dict]) -> None:
    """Re-parse before writing: every card must equal the old one plus the added keys."""
    import yaml
    after = yaml.safe_load(new_text) or []
    if len(after) != len(before):
        raise SystemExit(f"{f}: refusing to write, item count would change. Nothing written.")
    for i, (old, new) in enumerate(zip(before, after)):
        want = {k: v for k, v in old.items() if not k.startswith("_")}
        if old.get("_timeline"):
            want = {k: want[k] for k in want if k not in ("question", "answer")}
            new = {k: v for k, v in new.items() if k not in ("question", "answer")}
        want.update({k: v for k, v in added.get(i, {}).items()})
        got = dict(new)
        got.setdefault("type", "code")
        if {k: str(v) for k, v in got.items()} != {k: str(v) for k, v in want.items()}:
            raise SystemExit(f"{f}: refusing to write, card {i + 1} would change "
                             f"unexpectedly. Nothing written; add ids by hand.")


def _source_short(card: dict) -> str:
    src = str(card.get("source") or "")
    return src.replace("|", "/")[:80]


def fix_index(deck: Deck) -> int:
    ov = deck.path / "Overview.md"
    if not ov.is_file():
        return 0
    text, nl = read_keep(ov)
    rows = []
    for f in deck.files():
        for c in C.load_file(f):
            cid = str(c.get("id") or "")
            if cid and not re.search(rf"(?<![\w-]){re.escape(cid)}(?![\w-])", text):
                kind = c["type"] + ("" if deck.checked(f) else " (unchecked)")
                rows.append(f"| {cid} | draft | {kind} | {_source_short(c)} |")
    if not rows:
        return 0
    if INDEX_SECTION not in text:
        text = text.rstrip() + f"\n\n{INDEX_SECTION}\n\n| id | status | type | from |\n|---|---|---|---|\n"
    lines = text.split("\n")
    sec = lines.index(INDEX_SECTION)
    last = sec
    for i in range(sec + 1, len(lines)):
        if lines[i].startswith("#"):
            break
        if lines[i].startswith("|"):
            last = i
    lines[last + 1:last + 1] = rows
    text = "\n".join(lines)
    write_keep(ov, text, nl)
    return len(rows)


def ids(groups, fix: bool) -> int:
    for deck, files in groups:
        missing = [(f, c) for f in files for c in C.load_file(f) if not c.get("id")]
        if not fix:
            print(f"{deck.path.name}: next free id {next_id(deck, files)}")
            for f, c in missing:
                print(f"  no id: {f.name} {C.label(c)}")
            continue
        home = find_home(deck.path)
        std = home.standards_version if home.path else None
        total = sum(fix_file(deck, f, files, std) for f in files)
        rows = fix_index(deck)
        print(f"{deck.path.name}: id/std/guid written on {total} card(s), "
              f"{rows} Overview.md row(s) added.")
    return 0
