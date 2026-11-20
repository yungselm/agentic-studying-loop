# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Cards: how they are written down and what each type does.

    io.py      card files (YAML lists) -> card dicts; `label`, `measures`
    text.py    what a card shows and asks: typed characters, plain answer + bold lead, cloze
               gaps, $math$, embedded images
    types.py   core's card types (code, concept, timeline, cloze): fields, measures, lint,
               Anki note type; a module's card types follow the same `CardType` (registry.py)
    ids.py     `asl ids` / `asl fix`: ids, std versions, `kind:`, the Overview.md index
"""
from studyloop.core.cards.io import (
    CardFileError,
    expand_timeline,
    id_comment_line,
    item_starts,
    label,
    load_file,
    measures,
)
from studyloop.core.cards.text import (
    EMBED,
    IMAGE_EXT,
    MATH_BLOCK,
    MATH_INLINE,
    _split_code,
    bold_lead,
    cloze_text,
    gap_answers,
    gaps,
    plain,
    shown_len,
    typed,
    typed_chars,
)

__all__ = ["EMBED", "IMAGE_EXT", "MATH_BLOCK", "MATH_INLINE", "CardFileError", "_split_code",
           "bold_lead", "cloze_text", "expand_timeline", "gap_answers", "gaps", "id_comment_line",
           "item_starts", "label", "load_file", "measures", "plain", "shown_len", "typed",
           "typed_chars"]
