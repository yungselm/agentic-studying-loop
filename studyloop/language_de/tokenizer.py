# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""German text: spaCy tokens (de_core_news_sm). A separable verb is one word (fängt … an ->
anfangen) on the verb; its particle counts as a function word, so a card marks one target.
Fillers (äh, hm) stay out of the vocabulary."""
from __future__ import annotations

from functools import cache

from studyloop.language.vocabulary.tokens import Token

MODEL = "de_core_news_sm"
_FUNCTION_POS = {"PUNCT", "SPACE", "DET", "ADP", "CCONJ", "SCONJ", "PART", "PRON", "AUX", "SYM", "X"}
_FILLERS = {"äh", "ähm", "hm", "hmm", "mhm", "ah", "oh", "ach", "na", "naja", "tja", "oje", "au",
            "aua", "pst", "huch", "hey", "okay", "ok"}


class SpacyTokenizer:
    def __init__(self) -> None:
        try:
            import spacy
            self._nlp = spacy.load(MODEL)
        except (ImportError, OSError) as e:
            raise SystemExit("German needs the `lang-de` install: "
                             'pip install "agentic-studying-loop[lang-de]"') from e

    def __call__(self, text: str) -> list[Token]:
        doc = self._nlp(text)
        lemma = {t.i: t.lemma_ or t.text for t in doc}
        for t in doc:                                # separable verb: the verb carries the whole word
            if t.dep_ == "svp" and t.head.pos_ in ("VERB", "AUX"):
                lemma[t.head.i] = t.text.lower() + t.head.lemma_
        out, space = [], ""
        for t in doc:
            low = t.text.lower()
            if low in _FILLERS or t.pos_ == "INTJ":
                kind = "filler"
            elif t.pos_ in _FUNCTION_POS or t.dep_ == "svp":
                kind = "function"
            elif t.pos_ == "PROPN" or t.ent_type_ in ("PER", "LOC", "ORG"):
                kind = "name"
            elif t.pos_ == "NUM" or t.like_num:
                kind = "number"
            else:
                kind = "word"
            word = lemma[t.i]
            out.append(Token(t.text, f"{word}|", word, "", kind, "", space, t.pos_, t.dep_))
            space = t.whitespace_
        return out

    @cache  # noqa: B019  (one tokenizer per run)
    def key_for(self, word: str) -> str | None:
        """Lexeme key of a dictionary word (from Vocabulary.md or a gloss)."""
        toks = [t for t in self(word) if t.kind == "word"]
        return toks[0].key if toks else None
