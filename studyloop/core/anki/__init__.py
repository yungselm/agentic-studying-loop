# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Anki: reading exports, and the files that end up in Anki.

    reviews.py   an .apkg/.colpkg export -> ReviewData (notes with their review state, cards,
                 the review log, media); used by `asl stats` and `asl lang sync`
    templates/   the note types' HTML and CSS (core's card types)
    vendor/      CodeMirror 5, for typing code on the card
"""
from studyloop.core.anki.reviews import ReviewData, read_export

__all__ = ["ReviewData", "read_export"]
