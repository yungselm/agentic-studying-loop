# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""A source becomes lines: one row per subtitle cue or mined card, with its clip and screenshot.

    lines.py   `asl lang add`: mined .apkg or video + subtitles -> lines/<key>.tsv; cutting
               clips and screenshots from the video; speaker splits
    audio.py   ffmpeg (from PATH or imageio-ffmpeg): padding, splitting audio by speaker
    tts.py     `asl lang tts`: fallback audio for cards without a native clip
    clean.py   `asl lang clean`: media no line or card uses
"""
