# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Grammar ground truth: one vault note per grammar point (`<notes>/Grammar/*.md`).

Frontmatter: `type: grammar`, `grammar`, `level`, `meaning`, `status`, `link`, `image`, and how to
find it in a line: `pattern` (a regex on the plain text: `ちゃいけない|じゃダメ`) and/or `token` (a
word with its part of speech: `が/助詞`, `と/助詞/接続助詞`, any adjective `/形容詞`). Derived rules
are `rule: auto`; the agent's are `rule: agent` (kept); `detect: false` = cannot be found in a
line. Seeding and derived rules: the language module (language_ja: gamegengo, rules);
the overview of the official lists: overview.py."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from studyloop.core.config.vault import split_frontmatter

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
