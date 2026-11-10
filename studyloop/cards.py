"""Load card YAML files into plain dicts, with ids, and the size measures.

A card file is a YAML list. Every item is one card:

    - id: tsk-001            # stable id (recommended; drives the Anki note GUID)
      type: code             # code (default) | concept | timeline | cloze
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


class CardFileError(ValueError):
    """A card file that can't be read; the CLI prints it as one line."""


def load_file(path: str | Path) -> list[dict]:
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
    out = []
    for i, (card, cid) in enumerate(zip(cards, comment_ids)):
        card = dict(card)
        card.setdefault("type", "code")
        if not card.get("id") and cid:
            card["id"] = cid
        card["_file"] = path
        card["_index"] = i
        if card["type"] == "timeline":
            try:
                card = expand_timeline(card)
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


# ---- cloze gaps ---------------------------------------------------------------

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}   # embeddable on a card
EMBED = re.compile(r"!\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]|!\[[^\]]*\]\(([^)\s]+)\)")  # ![[a.png]], ![](a.png)
CLOZE_NUM = re.compile(r"^c(\d+)::", re.S)


def gaps(text: str | None) -> list[tuple[int, str, str, int, int]]:
    """`{{answer}}`, `{{answer::hint}}` or Anki's own `{{c2::answer}}` in a cloze text.

    Returns (number, answer, hint, start, end) per gap. Plain gaps are numbered in
    order after the explicit ones; braces inside a gap may nest (`{{\\frac{1}{C}}}`).
    """
    s, out, i = text or "", [], 0
    while (i := s.find("{{", i)) != -1:
        depth, j = 0, i + 2
        while j < len(s):
            if s.startswith("}}", j) and depth == 0:
                break
            depth += {"{": 1, "}": -1}.get(s[j], 0)
            j += 1
        if j >= len(s):
            break
        body = s[i + 2:j]
        m = CLOZE_NUM.match(body)
        num = int(m.group(1)) if m else 0
        body = body[m.end():] if m else body
        cut = next((k for k in range(len(body) - 1) if body.startswith("::", k)
                    and body[:k].count("`") % 2 == 0), None)   # `std::vec` is no hint
        ans, hint = (body, "") if cut is None else (body[:cut], body[cut + 2:])
        out.append([num, ans, hint, i, j + 2])
        i = j + 2
    nxt = max((g[0] for g in out), default=0)
    for g in out:
        if not g[0]:
            nxt += 1
            g[0] = nxt
    return [tuple(g) for g in out]


def cloze_text(text: str | None) -> str:
    """The text with every gap in Anki's `{{cN::answer[::hint]}}` form."""
    s, out, pos = text or "", [], 0
    for n, ans, hint, a, b in gaps(s):
        ans = ans.replace("}}", "} }") + (" " if ans.endswith("}") else "")  # Anki ends at `}}`
        out.append(s[pos:a] + f"{{{{c{n}::{ans}" + (f"::{hint}" if hint else "") + "}}")
        pos = b
    return "".join(out) + s[pos:]


MATH_BLOCK = re.compile(r"\$\$(.+?)\$\$", re.S)
MATH_INLINE = re.compile(r"(?<![\\$\w])\$(?=\S)([^$\n]+?)(?<=\S)\$(?![\w$])")   # not "$5 and $10"
TEX_CMD = re.compile(r"\\([A-Za-z]+|.)")
TEX_WORDS = {"log", "exp", "sin", "cos", "tan", "tanh", "max", "min", "arg", "det", "lim", "sup", "inf"}


def _tex_cmd(m: re.Match) -> str:
    name = m.group(1)
    if name in TEX_WORDS:
        return name                      # shown as a word
    return "" if name in ",;! " else "x"  # spacing, else one symbol


def shown_len(s: str) -> int:
    """Length as rendered: in `$math$` a command (`\\leftarrow`) is one symbol, and
    `$ { } ^ _` and spaces are layout, not characters."""
    def shown(m: re.Match) -> str:
        return re.sub(r"[{}^_\s]", "", TEX_CMD.sub(_tex_cmd, m.group(1)))
    return len(MATH_INLINE.sub(shown, MATH_BLOCK.sub(shown, plain(s))))


def gap_answers(text: str | None) -> dict[int, int]:
    """Cloze number -> characters you recall for that card (all its gaps, as rendered)."""
    out: dict[int, int] = {}
    for n, ans, *_ in gaps(text):
        out[n] = out.get(n, 0) + shown_len(ans)
    return out


def measures(card: dict) -> dict:
    """Numbers the standards limit, per card type."""
    if card.get("type") == "cloze":
        g = gap_answers(card.get("text"))
        return {"gaps": len(g), "gap_chars": max(g.values(), default=0),
                "hook": int(bool(str(card.get("hook") or "").strip()))}
    if card.get("type", "code") == "code":
        t = typed(card.get("starter"), card.get("solution"))
        return {"typed_chars": sum(map(len, t)), "typed_lines": len(t)}
    a = EMBED.sub("", card.get("answer") or "")       # an image is not answer text
    return {"answer_chars": len(plain(a)), "bold_chars": len(bold_lead(a))}


def label(card: dict) -> str:
    front = card.get("instruction") or card.get("question") or card.get("text") or "?"
    first = next((ln.strip() for ln in str(front).splitlines() if ln.strip()), "?")
    cid = card.get("id") or f"#{card['_index']}"
    return f"{cid} {first[:60]}"
