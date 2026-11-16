"""Tokens: text -> tokens with a lexeme key (dictionary form + reading) and a kind. Each
language brings its own tokenizer (language_ja: UniDic).

Only kind == "word" counts as vocabulary; names, numbers, fillers (interjections) and function
tokens (particles, auxiliaries, punctuation, affixes) are never card targets."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    surface: str
    key: str          # lexeme id: "lemma|reading"; merges conjugations and spelling variants
    word: str         # dictionary form as written here (e.g. する, 辞める)
    reading: str      # reading of `word` (hiragana for Japanese)
    kind: str         # word | name | number | filler | function
    kana: str = ""    # reading of the surface as it appears (hiragana)
    space: str = ""   # whitespace before the token in the text
    pos: str = ""     # part of speech (UniDic pos1: 名詞, 動詞, 副詞, ...)
    pos2: str = ""    # finer (UniDic pos2: 格助詞 vs 接続助詞 tells と "and" from と "whenever")


def mark_target(tokens: list[Token], target_key: str | None, render) -> str:
    """The text with each token as `render(token)` and the target word's tokens in `**…**`."""
    out, open_ = [], False
    for t in tokens:
        hit = target_key is not None and t.key == target_key
        if open_ and not hit:
            out.append("**")
            open_ = False
        out.append(t.space)
        if hit and not open_:
            out.append("**")
            open_ = True
        out.append(render(t))
    if open_:
        out.append("**")
    return "".join(out).strip()


def plain_text(s: str) -> str:
    """Card text as read: no furigana brackets, no `**`, no base-marking spaces."""
    s = re.sub(r" ?([^ \[\]>*]+?)\[[^\]]*\]", r"\1", s or "")
    return s.replace("**", "")
