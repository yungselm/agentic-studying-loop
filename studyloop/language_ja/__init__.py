"""Japanese for the language module: UniDic tokens and furigana, JLPT levels, JMdict, VOICEVOX,
the JLPT grammar lists (JLPT Sensei) and Game Gengo grammar decks. Config: ja.yaml.

  tokenizer   UniDic (fugashi), kana, furigana     levels    JLPT lists: kana, okurigana
  jmdict      the dictionary                       voicevox  local TTS
  jlpt        grammar lists + images               gamegengo grammar notes from a Game Gengo deck
"""
from __future__ import annotations

import re
from pathlib import Path

from ..core.registry import Module, Registry
from ..language.language import Language
from ..language.tokens import plain_text

HERE = Path(__file__).resolve().parent
PUNCT = re.compile(r"[\s、。！？!?…‥・「」『』“”\"'（）()~〜―-]")


class Japanese(Language):
    code, name = "ja", "Japanese"
    config_file = HERE / "ja.yaml"

    def __init__(self) -> None:
        self._tok = None

    def tokenizer(self):
        if self._tok is None:
            from .tokenizer import UnidicTokenizer
            self._tok = UnidicTokenizer()
        return self._tok

    def text_length(self, text: str) -> int:
        """Characters, without punctuation: Japanese has no spaces between words."""
        return len(PUNCT.sub("", plain_text(text)))

    def annotate(self, tokens, target_key):
        """Furigana, with the config's `reading_fixes` (私 → わたし) on the tokens' readings."""
        from dataclasses import replace

        from .tokenizer import furigana
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
        from .levels import JaLevels
        return JaLevels(self.config)

    def dictionary(self):
        if not self.config.get("dictionary"):
            return None
        from .jmdict import JMdict
        return JMdict(self.config)

    def tts_engines(self):
        from .voicevox import speak
        return {"voicevox": speak}

    def setup(self, force: bool = False) -> None:
        from .jlpt import fetch_lists
        from .jmdict import setup_dictionary
        super().setup(force)
        setup_dictionary(self.config, force)
        fetch_lists(self.config, force)

    def grammar_lists(self) -> dict:
        from .jlpt import lists
        return lists(self.code)

    def import_grammar(self, d, export, statuses, cards):
        from .gamegengo import import_game_gengo
        return import_game_gengo(d, export, statuses, cards=cards)

    def grammar_images(self, d) -> int:
        from .jlpt import fetch_images
        return fetch_images(d)


JA = Japanese()


def register(reg: Registry) -> None:
    reg.provide("language", JA.code, JA)


MODULE = Module("language_ja", register, requires=("language",), extra="lang-ja",
                needs=("fugashi", "unidic_lite"))
