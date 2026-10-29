"""Card ids: show the next free id, or add missing ids in place.

    asl ids path/to/deck            # next free id + any cards without one
    asl ids path/to/deck --fix      # write `id:` fields (keeps comments/formatting)

Ids are `<prefix>-NNN` (prefix from deck.yaml) and are never reused: deleted
ids go into deck.yaml `retired_ids`.

Migrating a deck that was imported with front-text GUIDs (deck.yaml
`guid: legacy-kata`): `--fix` also freezes each card's current GUID as a
`guid:` field, so the switch to ids creates no duplicates in Anki. Afterwards
remove `guid: legacy-kata` from deck.yaml.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import cards as C
from .build import guid as compute_guid
from .config import Deck

ITEM = re.compile(r"^- ")


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


def fix_file(deck: Deck, f: Path, files: list[Path]) -> int:
    text = f.read_text(encoding="utf-8")
    parsed = C.load_file(f)
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if ITEM.match(ln)]
    if len(starts) != len(parsed):
        print(f"  [!] {f.name}: couldn't match YAML items to lines; fix by hand.")
        return 0
    legacy = deck.cfg.get("guid") == "legacy-kata"
    # assign new ids in file order before editing bottom-up
    prefix = deck.cfg.get("prefix") or "card"
    n = _num(next_id(deck, files))
    for card in parsed:
        if not card.get("id"):
            card["id"], n = f"{prefix}-{n:03d}", n + 1
    changed = 0
    for idx in reversed(range(len(starts))):
        card, start = parsed[idx], starts[idx]
        block_end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        yaml_has_id = any(re.match(r"^(- |  )id:", ln) for ln in lines[start:block_end])
        yaml_has_guid = any(re.match(r"^(- |  )guid:", ln) for ln in lines[start:block_end])
        add = []
        if not yaml_has_id:
            add.append(f"id: {card['id']}")
        if legacy and not yaml_has_guid and not card.get("guid"):
            add.append(f'guid: "{compute_guid(deck, f, card)}"')
        if not add:
            continue
        first = lines[start][2:]
        lines[start:start + 1] = ["- " + add[0]] + [f"  {a}" for a in add[1:]] + [f"  {first}"]
        # drop the old `# id` comment right above, now that the id is a field
        j = start - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j >= 0 and C.ID_COMMENT.match(lines[j].strip()):
            del lines[j]
        changed += 1
    if changed:
        f.write_text("\n".join(lines), encoding="utf-8")
    return changed


def ids(groups, fix: bool) -> int:
    for deck, files in groups:
        print(f"{deck.path.name}: next free id {next_id(deck, files)}")
        missing = [(f, c) for f in files for c in C.load_file(f) if not c.get("id")]
        for f, c in missing:
            print(f"  no id: {f.name} {C.label(c)}")
        if fix:
            total = sum(fix_file(deck, f, files) for f in files)
            print(f"  wrote id/guid fields on {total} card(s).")
    return 0
