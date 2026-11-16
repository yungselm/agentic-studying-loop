"""Card files: a YAML list per file, one card per item, loaded into plain dicts.

    - id: tsk-001            # stable id (recommended; drives the Anki note GUID)
      type: code             # code (default) | concept | timeline | cloze | ...
      ...

Older files keep the id as a comment above the item (`# omk-001`). Both forms are read; a real
`id:` field wins. Loading runs each card type's `prepare` (timeline: shuffle the steps).
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


class CardFileError(ValueError):
    """A card file that can't be read; the CLI prints it as one line."""


def load_file(path: str | Path) -> list[dict]:
    """Read a card file: a YAML list of cards, each prepared by its card type.

    Every card gets ``type`` (default ``code``), ``_file`` and ``_index``; an id written as a
    ``# tsk-001`` comment above the card counts as its ``id``.

    Raises
    ------
    CardFileError
        Invalid YAML (with the line) or not a list.

    Examples
    --------
    >>> cards = load_file("example-vault/Studying/Anki cards/tasklog/tasklog.yaml")
    >>> len(cards), {k: cards[0][k] for k in ("id", "type", "_index")}
    (4, {'id': 'tsk-001', 'type': 'code', '_index': 0})
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    try:
        cards = yaml.safe_load(text) or []
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f":{mark.line + 1}" if mark else ""
        raise CardFileError(f"{path.name}{where}: {getattr(e, 'problem', None) or e} "
                            "(backslashes: use '...' or a | block, not \"...\")") from None
    if not isinstance(cards, list):
        raise CardFileError(f"{path}: a card file must be a YAML list")
    comment_ids = _comment_ids(text)
    if len(comment_ids) != len(cards):
        comment_ids = [None] * len(cards)
    from studyloop.core.registry import registry
    types = registry().card_types
    out = []
    for i, (card, cid) in enumerate(zip(cards, comment_ids)):
        card = dict(card)
        card.setdefault("type", "code")
        if not card.get("id") and cid:
            card["id"] = cid
        card["_file"] = path
        card["_index"] = i
        if card["type"] in types:           # unknown types: `asl lint` says so
            try:
                card = types[card["type"]].prepare(card)
            except ValueError as e:
                raise CardFileError(f"{path.name}: {e}") from None
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


def measures(card: dict) -> dict:
    """Numbers the standards limit: the card type's `measures`."""
    from studyloop.core.registry import registry
    t = registry().card_types.get(card.get("type", "code"))
    return t.measures(card) if t else {}


def label(card: dict) -> str:
    from studyloop.core.registry import registry
    t = registry().card_types.get(card.get("type", "code"))
    front = (t.front(card) if t else "") or "?"
    first = next((ln.strip() for ln in str(front).splitlines() if ln.strip()), "?")
    cid = card.get("id") or f"#{card['_index']}"
    return f"{cid} {first[:60]}"
