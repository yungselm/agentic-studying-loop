"""German (Standard German) for the language module. `German` (below) is the whole contract;
config: de.yaml. Everything else (lines, plan, drafts, cards, sync) is the shared pipeline.

    tokenizer.py   spaCy tokens; separable verbs joined; fillers   -> tokenizer()
    levels.py      CEFR estimated from word frequency               -> levels()

No bundled dictionary: the agent writes the gloss (`asl lang draft` shows the word and line).
Audio fallback: edge-tts's German voice (de.yaml `tts:`).
"""
from __future__ import annotations

from pathlib import Path

from studyloop.core.registry import Module, Registry
from studyloop.language.base import Language

HERE = Path(__file__).resolve().parent


class German(Language):
    code, name = "de", "German"
    config_file = HERE / "de.yaml"

    def __init__(self) -> None:
        self._tok = None

    def tokenizer(self):
        if self._tok is None:
            from studyloop.language_de.tokenizer import SpacyTokenizer
            self._tok = SpacyTokenizer()
        return self._tok

    def levels(self):
        from studyloop.language_de.levels import DeLevels
        return DeLevels(self.config)


DE = German()


def register(reg: Registry) -> None:
    reg.provide("language", DE.code, DE)


MODULE = Module("language_de", register, requires=("language",), extra="lang-de",
                needs=("spacy", "de_core_news_sm"))
