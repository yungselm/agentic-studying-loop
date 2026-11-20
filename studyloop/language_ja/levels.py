# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Japanese word levels: readings in hiragana, okurigana variants (付き合う = 付合う), and
kana-only words matched by their reading."""
from __future__ import annotations

from studyloop.language.vocabulary.levels import Levels
from studyloop.language_ja.tokenizer import hira


class JaLevels(Levels):
    def normalize_reading(self, s: str) -> str:
        return hira(s)

    def variant(self, form: str) -> str:
        return _skeleton(form)

    def reading_only(self, form: str) -> bool:
        return _is_kana(form)


def _skeleton(s: str) -> str:
    """The kanji of a word without its kana (okurigana): 付き合う, 付合う -> 付合."""
    return "".join(c for c in s if not _is_kana(c))


def _is_kana(s: str) -> bool:
    return all("ぁ" <= c <= "ゖ" or "ァ" <= c <= "ヺ" or c == "ー" for c in s)
