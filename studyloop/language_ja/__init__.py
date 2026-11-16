"""Japanese for the language module. Start here: `Japanese` (below) is the whole contract;
each method hands over to one file. Config: ja.yaml.

    tokenizer.py   UniDic tokens (fugashi), kana, furigana         -> tokenizer(), annotate()
    levels.py      JLPT word lists: kana readings, okurigana        -> levels()
    jmdict.py      the dictionary (JMdict)                          -> dictionary()
    voicevox.py    local text-to-speech                             -> tts_engines()
    jlpt.py        JLPT grammar lists and images (JLPT Sensei)      -> grammar_lists(), grammar_images()
    gamegengo.py   grammar notes from a Game Gengo deck             -> import_grammar()
    rules.py       grammar rules from Japanese notation (used by gamegengo)
"""
from __future__ import annotations

import re
from pathlib import Path

from studyloop.core.registry import Module, Registry
from studyloop.language.base import Language
from studyloop.language.vocabulary.tokens import plain_text

HERE = Path(__file__).resolve().parent
PUNCT = re.compile(r"[\s、。！？!?…‥・「」『』“”\"'（）()~〜―-]")


class Japanese(Language):
    code, name = "ja", "Japanese"
    config_file = HERE / "ja.yaml"

    def __init__(self) -> None:
        self._tok = None

    def tokenizer(self):
        if self._tok is None:
            from studyloop.language_ja.tokenizer import UnidicTokenizer
            self._tok = UnidicTokenizer()
        return self._tok

    def text_length(self, text: str) -> int:
        """Characters, without punctuation: Japanese has no spaces between words."""
        return len(PUNCT.sub("", plain_text(text)))

    def annotate(self, tokens, target_key):
        """Furigana, with the config's `reading_fixes` (私 → わたし) on the tokens' readings."""
        from dataclasses import replace

        from studyloop.language_ja.tokenizer import furigana
        fixes = self.config.get("reading_fixes") or {}
        return furigana([replace(t, kana=fixes.get(t.surface, t.kana)) for t in tokens], target_key)

    def reading(self, word, token, fallback):
        """`reading_fixes` first; katakana words read as themselves (シーン, not しーん)."""
        fixes = self.config.get("reading_fixes") or {}
        reading = fixes.get(word, token.reading if token else fallback)
        if word and all("ァ" <= c <= "ヺ" or c == "ー" for c in word):
            reading = word
        return reading

    def levels(self):
        from studyloop.language_ja.levels import JaLevels
        return JaLevels(self.config)

    def dictionary(self):
        if not self.config.get("dictionary"):
            return None
        from studyloop.language_ja.jmdict import JMdict
        return JMdict(self.config)

    def tts_engines(self):
        from studyloop.language_ja.voicevox import speak
        return {"voicevox": speak}

    def setup(self, force: bool = False) -> None:
        from studyloop.language_ja.jlpt import fetch_lists
        from studyloop.language_ja.jmdict import setup_dictionary
        super().setup(force)
        setup_dictionary(self.config, force)
        fetch_lists(self.config, force)

    def grammar_lists(self) -> dict:
        from studyloop.language_ja.jlpt import lists
        return lists(self.code)

    def import_grammar(self, d, export, statuses, cards):
        from studyloop.language_ja.gamegengo import import_game_gengo
        return import_game_gengo(d, export, statuses, cards=cards)

    def grammar_images(self, d) -> int:
        from studyloop.language_ja.jlpt import fetch_images
        return fetch_images(d)


JA = Japanese()


def register(reg: Registry) -> None:
    reg.provide("language", JA.code, JA)


MODULE = Module("language_ja", register, requires=("language",), extra="lang-ja",
                needs=("fugashi", "unidic_lite"))
