# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Grammar rules derived from Japanese grammar notation (`全然～ない（ぜんぜん～ない）`, `が (ga)`)
and UniDic parts of speech: particles and auxiliaries become token rules (`が/助詞`). Used when
seeding grammar notes from a Game Gengo deck; the shared grammar.py checks them."""
from __future__ import annotations

import re

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
