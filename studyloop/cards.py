"""Load card YAML files into plain dicts, with ids, and the size measures.

A card file is a YAML list. Every item is one card:

    - id: tsk-001            # stable id (recommended; drives the Anki note GUID)
      type: code             # code (default) | concept | timeline
      ...

Older files keep the id as a comment above the item (`# omk-001`). Both forms
are read; a real `id:` field wins.
"""
from __future__ import annotations

import random
import re
from pathlib import Path

import yaml

ID_COMMENT = re.compile(r"^#\s*([A-Za-z][A-Za-z0-9]*-\d+)\s*$")
LETTERS = "ABCDEFGHIJ"


ITEM = re.compile(r"^-(\s|$)")


def item_starts(lines: list[str]) -> list[int]:
    """Line numbers of the top-level `- ` items of a card file."""
    return [i for i, ln in enumerate(lines) if ITEM.match(ln)]


def id_comment_line(lines: list[str], start: int) -> int | None:
    """The `# abc-001` comment directly above an item (blank lines allowed in
    between; any other comment line stops the search), or None."""
    j = start - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    if j >= 0 and ID_COMMENT.match(lines[j].strip()):
        return j
    return None


def _comment_ids(text: str) -> list[str | None]:
    lines = text.splitlines()
    out = []
    for start in item_starts(lines):
        j = id_comment_line(lines, start)
        out.append(ID_COMMENT.match(lines[j].strip()).group(1) if j is not None else None)
    return out


def load_file(path: str | Path) -> list[dict]:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    cards = yaml.safe_load(text) or []
    if not isinstance(cards, list):
        raise ValueError(f"{path}: a card file must be a YAML list")
    comment_ids = _comment_ids(text)
    if len(comment_ids) != len(cards):
        comment_ids = [None] * len(cards)
    out = []
    for i, (card, cid) in enumerate(zip(cards, comment_ids)):
        card = dict(card)
        card.setdefault("type", "code")
        if not card.get("id") and cid:
            card["id"] = cid
        card["_file"] = path
        card["_index"] = i
        if card["type"] == "timeline":
            card = expand_timeline(card)
        out.append(card)
    return out


def expand_timeline(card: dict) -> dict:
    """Turn an ordered `steps:` list into a shuffled A-E concept question.

    The shuffle is seeded with the card id (or the question), so it stays the
    same on every build and the note's front never changes by accident.
    """
    steps = [str(s).strip() for s in card.get("steps", [])]
    if not 3 <= len(steps) <= len(LETTERS):
        raise ValueError(f"timeline card needs 3-{len(LETTERS)} steps: {card.get('question')!r}")
    seed = str(card.get("id") or card.get("question"))
    order = list(range(len(steps)))
    rng = random.Random(seed)
    for _ in range(200):                   # prefer no step in its own slot
        rng.shuffle(order)
        if all(pos != idx for pos, idx in enumerate(order)):
            break
    shown = {LETTERS[pos]: steps[idx] for pos, idx in enumerate(order)}
    label_of = {idx: LETTERS[pos] for pos, idx in enumerate(order)}
    q = (card.get("question") or "Put these steps in order.").rstrip()
    q += "\n\n" + "\n".join(f"{k}  {v}" for k, v in shown.items())
    answer = "**" + " → ".join(label_of[i] for i in range(len(steps))) + "**"
    if card.get("detail"):
        answer += "\n" + str(card["detail"]).strip()
    card = dict(card, question=q, answer=answer)
    card["_timeline"] = True
    return card


# ---- size measures (shared by lint and stats) -------------------------------

def _lines(t: str | None) -> list[str]:
    return [ln.strip() for ln in (t or "").splitlines() if ln.strip()]


def typed(starter: str | None, solution: str | None) -> list[str]:
    """Solution lines that are not already in the starter: what you type."""
    given = set(_lines(starter))
    return [ln for ln in _lines(solution) if ln not in given]


def typed_chars(starter, solution) -> int:
    return sum(map(len, typed(starter, solution)))


CODE_SPAN = re.compile(r"`([^`]+)`")


def _split_code(s: str) -> list[tuple[bool, str]]:
    """[(is_code, text)] so markup rules never apply inside `code`."""
    out, pos = [], 0
    for m in CODE_SPAN.finditer(s):
        out += [(False, s[pos:m.start()]), (True, m.group(1))]
        pos = m.end()
    return out + [(False, s[pos:])]


def plain(s: str | None) -> str:
    """Text as rendered on the card: no backticks, no `**` outside code."""
    return "".join(t if code else t.replace("**", "") for code, t in _split_code(s or "")).strip()


def bold_lead(answer: str | None) -> str:
    """The first **bold** run (code spans inside it allowed), as rendered."""
    masked = "".join("\x00" * (len(t) + 2) if code else t for code, t in _split_code(answer or ""))
    m = re.search(r"\*\*(.+?)\*\*", masked, re.S)
    return plain((answer or "")[m.start(1):m.end(1)]) if m else ""


def measures(card: dict) -> dict:
    """Numbers the standards limit, per card type."""
    if card.get("type", "code") == "code":
        t = typed(card.get("starter"), card.get("solution"))
        return {"typed_chars": sum(map(len, t)), "typed_lines": len(t)}
    a = card.get("answer") or ""
    return {"answer_chars": len(plain(a)), "bold_chars": len(bold_lead(a))}


def label(card: dict) -> str:
    front = card.get("instruction") or card.get("question") or "?"
    first = next((ln.strip() for ln in str(front).splitlines() if ln.strip()), "?")
    cid = card.get("id") or f"#{card['_index']}"
    return f"{cid} {first[:60]}"
