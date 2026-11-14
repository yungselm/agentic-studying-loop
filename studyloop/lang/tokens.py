"""Tokenizers: text -> tokens with a lexeme key (dictionary form + reading) and a kind.

Only kind == "word" counts as vocabulary; names, numbers, fillers (interjections) and function
tokens (particles, auxiliaries, punctuation, affixes) are never card targets."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache


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


def hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s or "")


def _kanji(c: str) -> bool:
    return "㐀" <= c <= "鿿" or c in "々〆ヶ"


def ruby(surface: str, kana: str) -> str:
    """Anki furigana for one token: 住んで + すんで -> ' 住[す]んで' (kana around the kanji stay
    outside the brackets; the space marks where the kanji base starts and is not shown)."""
    if not kana or not any(_kanji(c) for c in surface):
        return surface
    i = 0
    while i < min(len(surface), len(kana)) and not _kanji(surface[i]) and hira(surface[i]) == kana[i]:
        i += 1
    j = 0
    while (j < min(len(surface), len(kana)) - i and not _kanji(surface[-1 - j])
           and hira(surface[-1 - j]) == kana[-1 - j]):
        j += 1
    base, rt = surface[i:len(surface) - j], kana[i:len(kana) - j]
    if not rt or hira(base) == rt:
        return surface
    return f"{surface[:i]} {base}[{rt}]{surface[len(surface) - j:]}"


def furigana(tokens: list[Token], target_key: str | None = None) -> str:
    """The text with readings (`軽井沢[かるいざわ]`) and the target word's tokens in `**…**`."""
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
        out.append(ruby(t.surface, t.kana))
    if open_:
        out.append("**")
    return "".join(out).strip()


def plain_text(s: str) -> str:
    """Card text as read: no furigana brackets, no `**`, no base-marking spaces."""
    s = re.sub(r" ?([^ \[\]>*]+?)\[[^\]]*\]", r"\1", s or "")
    return s.replace("**", "")


_LATIN = re.compile(r"^[A-Za-z0-9Ａ-Ｚａ-ｚ０-９'’.\-]+$")
_FUNCTION_POS = {"助詞", "助動詞", "補助記号", "記号", "空白", "接頭辞", "接尾辞"}


class UnidicTokenizer:
    def __init__(self) -> None:
        try:
            import fugashi
        except ImportError as e:
            raise SystemExit("Japanese needs the language extra: "
                             'uv tool install "agentic-studying-loop[lang] @ ..." '
                             "(or pip install fugashi unidic-lite wordfreq)") from e
        self._tagger = fugashi.Tagger()

    def __call__(self, text: str) -> list[Token]:
        out = []
        for w in self._tagger(text):
            f = w.feature
            pos1, pos2 = f.pos1 or "", f.pos2 or ""
            lemma = (f.lemma or w.surface).split("-")[0]
            word = f.orthBase or w.surface
            # unconjugated: the reading heard here (私 → わたし, not the lemma's わたくし)
            reading = hira((f.kana if w.surface == word else None) or f.kanaBase or f.lForm or "")
            if pos1 in _FUNCTION_POS:
                kind = "function"
            elif pos1 == "感動詞":
                kind = "filler"
            elif pos2 == "固有名詞" or _LATIN.match(w.surface):
                kind = "name"
            elif pos2 == "数詞":
                kind = "number"
            else:
                kind = "word"
            out.append(Token(w.surface, f"{lemma}|{hira(f.lForm or '')}", word, reading, kind,
                             hira(f.kana or ""), w.white_space or "", pos1))
        return out

    @cache  # noqa: B019  (one tokenizer per run)
    def key_for(self, word: str) -> str | None:
        """Lexeme key of a dictionary word (from Vocabulary.md or a gloss)."""
        toks = [t for t in self(word) if t.kind == "word"]
        return toks[0].key if toks else None


_TOKENIZERS = {"unidic": UnidicTokenizer}


@cache
def tokenizer(name: str):
    if name not in _TOKENIZERS:
        raise SystemExit(f"Unknown tokenizer '{name}' (have: {', '.join(_TOKENIZERS)})")
    return _TOKENIZERS[name]()
