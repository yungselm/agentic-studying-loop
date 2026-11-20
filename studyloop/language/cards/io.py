# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Card files (YAML lists in the deck folder): write new card items, and change single fields of
existing cards in place (the rest of the file, comments included, stays as written)."""
from __future__ import annotations

import json
import re
from pathlib import Path

RAW = ("id", "type", "line")        # written without quotes


def card_item(card: dict, keep_empty: tuple[str, ...] = ()) -> str:
    """One `- id: …` item; values JSON-quoted (valid YAML, safe for any text), empty ones left
    out unless named in `keep_empty` (a `gloss: ""` the agent fills)."""
    out = []
    for k, v in card.items():
        if v in ("", None, []) and k not in keep_empty:
            continue
        val = v if k in RAW else json.dumps(v if isinstance(v, list) else str(v), ensure_ascii=False)
        out.append(("- " if not out else "  ") + f"{k}: {val}")
    return "\n".join(out) + "\n"


_KEY = {"id": re.compile(r"^- id: \"?([^\"\s]+)"),
        "line": re.compile(r"(?m)^  line: \"?([^\"\s]+)\"?\s*$")}


def edit_cards(deck_dir: Path, by: str, changes: dict[str, dict]) -> list[str]:
    """Set fields on cards found by `by` ("id" or "line"): {key: {field: value}}. A missing field is
    inserted before `line:` (else at the end). Returns the ids of the cards that changed."""
    changed = []
    for f in sorted(Path(deck_dir).glob("*.yaml")):
        if f.name == "deck.yaml":
            continue
        text = f.read_text(encoding="utf-8")
        items = re.split(r"(?m)^(?=- )", text)
        for n, it in enumerate(items):
            m = _KEY[by].search(it)
            if not m or m.group(1) not in changes:
                continue
            new = it
            for name, value in changes[m.group(1)].items():
                line = f"  {name}: {json.dumps(value, ensure_ascii=False)}"
                old = re.search(rf"(?m)^  {name}: .*$", new)
                if old:
                    new = new.replace(old.group(0), line, 1)
                elif (lm := _KEY["line"].search(new)):
                    new = new.replace(lm.group(0), line + "\n" + lm.group(0), 1)
                else:
                    new = new.rstrip("\n") + "\n" + line + "\n"
            if new != it:
                items[n] = new
                cid = _KEY["id"].search(it)
                changed.append(cid.group(1) if cid else m.group(1))
        if "".join(items) != text:
            f.write_text("".join(items), encoding="utf-8")
    return changed
