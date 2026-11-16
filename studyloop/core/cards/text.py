"""What a card shows and asks, as text: typed characters of a code gap, the plain answer and
its bold lead, cloze gaps (with $math$ counted as rendered), embedded images. The card types'
measures and lint, and the build's rendering, use these."""
from __future__ import annotations

import re


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
