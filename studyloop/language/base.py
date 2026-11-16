"""What differs per language (docs/architecture.md, "Language modules").

The language module holds the pipeline every language shares: lines from video + subtitles or
mined decks, the i+1 planner, drafts, sync from reviews, grammar rules, the sentence and grammar
card types, `asl lang`. A language module (language_ja, later language_it) subclasses
`Language`, ships its `<code>.yaml` and registers it with `reg.provide("language", "ja", JA)`;
deck.yaml's `lang: ja` picks it. The defaults suit a language written with spaces and no
reading aid.
"""
from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import yaml

from studyloop.language.vocabulary.levels import Levels
from studyloop.language.vocabulary.tokens import Token, mark_target, plain_text


class Tokenizer(Protocol):
    def __call__(self, text: str) -> list[Token]: ...
    def key_for(self, word: str) -> str | None: ...     # lexeme key of a dictionary word


class Dictionary(Protocol):
    """Entries are the dictionary's own; only these methods look inside them."""
    def lookup(self, word: str, reading: str = "", pos: str = "") -> list: ...
    def readings(self, entry: Any) -> list[str]: ...
    def senses_text(self, entry: Any, langs: list[str], limit: int) -> str: ...
    def meaning(self, entries: list, langs: list[str]) -> str | None: ...   # short, for Vocabulary.md
    def interjection(self, entries: list) -> bool: ...                     # only ever an interjection


TTSEngine = Callable[[str, Path, dict], bool]          # (text, out.mp3, tts config) -> it worked


class Language:
    code: str                       # deck.yaml `lang:`
    name: str                       # "Japanese"
    config_file: Path               # <code>.yaml: level lists, dictionary, subtitle filters, TTS

    @functools.cached_property
    def config(self) -> dict:
        cfg = yaml.safe_load(self.config_file.read_text(encoding="utf-8")) or {}
        cfg["code"] = self.code
        return cfg

    # -- reading text --------------------------------------------------------------------
    def tokenizer(self) -> Tokenizer:
        raise NotImplementedError

    def text_length(self, text: str) -> int:
        """What the length cap (`length_cap:`) counts: words; Japanese counts characters."""
        return len(plain_text(text).split())

    # -- writing cards -------------------------------------------------------------------
    def annotate(self, tokens: list[Token], target_key: str | None) -> str:
        """Card text with the reading aid and the target in `**…**` (Japanese: furigana)."""
        return mark_target(tokens, target_key, lambda t: t.surface)

    def reading(self, word: str, token: Token | None, fallback: str) -> str:
        """The target word's reading for its card."""
        return token.reading if token else fallback

    # -- levels, meanings, audio -----------------------------------------------------------
    def levels(self) -> Levels:
        return Levels(self.config)

    def dictionary(self) -> Dictionary | None:
        return None

    def tts_engines(self) -> dict[str, TTSEngine]:
        """Engines beyond the shared `edge` (Japanese: a local VOICEVOX)."""
        return {}

    def setup(self, force: bool = False) -> None:
        """`asl lang setup <code>`: one-time downloads. Default: the level lists."""
        from studyloop.language.vocabulary.levels import download_lists
        download_lists(self.config, force)

    # -- grammar (optional) ----------------------------------------------------------------
    def grammar_lists(self) -> dict:
        """Official grammar points per level ({level: [{link, grammar, meaning}]}) for the
        overview's checklist (Japanese: JLPT, from JLPT Sensei). Empty: notes only."""
        return {}

    def import_grammar(self, d: Any, export: Path, statuses: str, cards: bool) -> int:
        """`asl lang grammar <deck> <export>`: grammar notes from a grammar deck."""
        raise SystemExit(f"`asl lang grammar` imports no deck for {self.name} yet")

    def grammar_images(self, d: Any) -> int:
        """`asl lang grammar --images`: an image on each grammar note that has none."""
        print(f"  images: none to fetch for {self.name}")
        return 0
