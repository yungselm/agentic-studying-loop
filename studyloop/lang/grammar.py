"""Grammar ground truth: one vault note per grammar point (`<notes>/Grammar/*.md`).

Frontmatter: `type: grammar`, `grammar`, `level`, `meaning`, `status`, `link`, `image`, and how to
find it in a line: `pattern` (a regex on the plain text: `ちゃいけない|じゃダメ`) and/or `token` (a
word with its part of speech: `が/助詞`, `と/助詞/接続助詞`, any adjective `/形容詞`). Derived rules
are `rule: auto`; the agent's are `rule: agent` (kept); `detect: false` = cannot be found in a
line. Seeding: gamegengo.py; the JLPT overview: overview.py."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..core.vault import split_frontmatter

GATE_OK = {"planned": {"planned", "learning", "known"}, "learning": {"learning", "known"}}


@dataclass
class Point:
    title: str
    path: Path
    level: str = ""
    meaning: str = ""
    status: str = "unknown"
    pattern: str = ""
    token: str = ""
    link: str = ""
    image: str = ""
    examples: list[str] = field(default_factory=list)
    _rx: re.Pattern | None = None

    def matches(self, text: str, tokens: list) -> bool:
        if self.pattern:
            if self._rx is None:
                self._rx = re.compile(self.pattern)
            if self._rx.search(text):
                return True
        for rule in filter(None, (r.strip() for r in self.token.split("|"))):
            surface, pos, pos2 = (rule.split("/") + ["", ""])[:3]   # が/助詞, と/助詞/接続助詞
            if any((not surface or t.surface == surface) and (not pos or t.pos == pos)
                   and (not pos2 or t.pos2 == pos2) for t in tokens):      # `/形容詞`: any adjective
                return True
        return False


def load_points(notes_dir: Path) -> list[Point]:
    out = []
    for p in sorted((notes_dir / "Grammar").glob("*.md")):
        meta, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        if meta.get("type") != "grammar" or meta.get("detect") is False \
                or not (meta.get("pattern") or meta.get("token")):
            continue                     # `detect: false`: too generic to find in a line
        out.append(Point(p.stem, p, str(meta.get("level") or ""), str(meta.get("meaning") or ""),
                         str(meta.get("status") or "unknown"), str(meta.get("pattern") or ""),
                         str(meta.get("token") or ""), str(meta.get("link") or ""),
                         str(meta.get("image") or ""), [str(e) for e in meta.get("examples") or []]))
    return out


def detect(points: list[Point], text: str, tokens: list) -> list[Point]:
    return [p for p in points if p.matches(text, tokens)]


_ALT_SPLIT = re.compile(r"\s*(?:/|／|・|、|,|\+)\s*")
_GAP = re.compile(r"\s*(?:～|〜|~|…|\.\.\.)\s*")      # 全然～ない: 全然, then later ない


def _forms(grammar: str) -> list[str]:
    """'てしまう / ちゃう' -> ['てしまう', 'ちゃう']; '一番（いちばん）' -> ['一番']; 'が (ga)' -> ['が']."""
    g = re.sub(r"（[^）]*）|\([^)]*\)|\[[^\]]*\]", "", grammar)
    out = []
    for alt in _ALT_SPLIT.split(g):
        parts = [re.sub(r"[A-Za-z\s\[\]]+", "", x) for x in _GAP.split(alt)]
        alt = "～".join(x for x in parts if x)
        if alt and alt not in out:
            out.append(alt)
    return out


def _marked_tokens(marked: str, tok) -> list:
    """Tokens inside the **highlighted** grammar of an example (Game Gengo colours it)."""
    spans, plain, pos = [], "", 0
    for m in re.finditer(r"\*\*(.+?)\*\*", marked):
        plain += marked[pos:m.start()]
        spans.append((len(plain), len(plain) + len(m.group(1))))
        plain += m.group(1)
        pos = m.end()
    plain += marked[pos:]
    out, at = [], 0
    for t in tok(plain):
        start = plain.find(t.surface, at)
        if start < 0:
            continue
        at = start + len(t.surface)
        if any(a < at and start < b for a, b in spans):
            out.append(t)
    return out


def derive_rule(forms: list[str], examples: list[str], tok, marked: list[str] = ()) -> tuple[str, str]:
    """(pattern, token): a particle or auxiliary used as one token -> token rule (`が/助詞`), else
    the literal forms as a regex. Checked against the examples by `check_points`."""
    patterns, tokens = [], []
    for f in forms:
        if "～" in f:                                       # 全然～ない -> 全然.*?ない
            patterns.append(".*?".join(re.escape(x) for x in f.split("～")))
            continue
        hit = None
        # the marked span first (と "whenever" vs と "and" in the same sentence), then anywhere
        candidates = [_marked_tokens(m, tok) for m in marked] + [tok(ex) for ex in examples]
        for toks in candidates:
            for t in toks:
                if t.surface == f and t.pos in ("助詞", "助動詞"):
                    hit = f"{f}/{t.pos}/{t.pos2}" if t.pos2 and t.pos2 != "*" else f"{f}/{t.pos}"
                    break
            if hit:
                break
        if hit and len(f) <= 2:
            tokens.append(hit)
        else:
            patterns.append(re.escape(f))
    return "|".join(patterns), "|".join(tokens)


def check_points(d, tok) -> int:
    """Each grammar note's rule must find its own examples; list the ones that don't."""
    points = load_points(d.notes_dir)
    bad = []
    for p in points:
        miss = [e for e in p.examples if not p.matches(e, tok(e))]
        if miss:
            bad.append((p, miss))
    unruled = [q.stem for q in sorted((d.notes_dir / "Grammar").glob("*.md"))
               if q.stem not in {p.title for p in points}
               and split_frontmatter(q.read_text(encoding="utf-8"))[0].get("detect") is not False]
    print(f"Grammar rules: {len(points) - len(bad)} of {len(points)} find all their examples"
          + (f"; {len(unruled)} notes without a rule" if unruled else ""))
    for p, miss in bad:
        print(f"  ! {p.title}: pattern={p.pattern!r} token={p.token!r} misses: {miss[0][:50]}")
    for t in unruled:
        print(f"  ! {t}: no `pattern:` or `token:`")
    return 0
