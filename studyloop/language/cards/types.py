"""The language card types: sentence (one new word, listening front) and grammar
(a grammar point; Listening + optional Reading card). Design: docs/language-cards.md."""
from __future__ import annotations

import html
import re
from pathlib import Path

from studyloop.core.config import Deck
from studyloop.core.registry import CardType, Flag, Template

TEMPLATES = Path(__file__).resolve().parent / "anki"
TARGET = re.compile(r"\*\*(.+?)\*\*", re.S)


class _LangCard(CardType):
    templates_dir = TEMPLATES
    css = (TEMPLATES / "style.css").read_text(encoding="utf-8")

    def front(self, card):
        return str(card.get("text") or "")

    def lint(self, card, ctx):
        return lang_flags(card, ctx.once("lang", lambda: lang_context(ctx.deck)))


class Sentence(_LangCard):
    name, model_name = "sentence", "Sentence Card"
    model_id = 1607392325
    fields = ("Text", "Word", "Reading", "Gloss", "Audio", "Image", "Grammar", "Source")
    templates = (Template("Listening", "front_sentence.html", "back_sentence.html"),)

    def to_fields(self, card, ctx):
        return [ctx.text(card.get("text")), ctx.text(card.get("word")), ctx.text(card.get("reading")),
                ctx.text(card.get("gloss")), ctx.media(card.get("audio"), "audio"),
                ctx.media(card.get("image"), "image"), ctx.links(card.get("grammar")), ctx.source(card)]


class Grammar(_LangCard):
    name, model_name = "grammar", "Grammar Card"
    model_id = 1607392327
    fields = ("Text", "Grammar", "Meaning", "Translation", "Audio", "Image", "Notes", "Source",
              "ReadCard")
    templates = (Template("Listening", "front_sentence.html", "back_grammar.html"),
                 Template("Reading", "front_grammar_read.html", "back_grammar.html"))

    def to_fields(self, card, ctx):
        opts = ctx.deck.file_opts(ctx.file).get("cards") or ctx.deck.cfg.get("cards")
        read = "read" in (opts or ["listen", "read"])
        notes = ctx.links(card.get("note")) + (
            f'<br><a href="{html.escape(str(card["link"]))}">{html.escape(str(card["link"]))}</a>'
            if card.get("link") else "")
        return [ctx.text(card.get("text")), ctx.text(card.get("grammar")),
                ctx.text(card.get("meaning")), ctx.text(card.get("translation")),
                ctx.media(card.get("audio"), "audio"), ctx.media(card.get("image"), "image"),
                notes, ctx.source(card), "y" if read else ""]


LANG_TYPES = (Sentence(), Grammar())


def lang_context(deck: Deck) -> dict | None:
    """Per deck: the language's length cap and the clips in media_dir."""
    if not deck.cfg.get("lang"):
        return None
    from studyloop.core.engine.build import media_index
    from studyloop.language.base import Language
    from studyloop.language.setup import get_language
    try:
        lang = get_language(deck.cfg["lang"])
        cap, length = lang.config.get("length_cap"), lang.text_length
        reading = bool(lang.config.get("reading_aid"))
    except SystemExit:                    # not installed: lint the rest, skip the length cap
        cap, length, reading = None, Language().text_length, True
    return {"cap": int(cap or 10**6), "length": length, "media": media_index(deck),
            "reading": reading,                    # the language shows readings (furigana)
            "has_media_dir": bool(deck.cfg.get("media_dir"))}


def lang_flags(card: dict, ctx: dict | None) -> list[Flag]:
    t = card["type"]
    if ctx is None:
        return [Flag("!", "lang", f"a {t} card needs a language deck (`lang:` and `media_dir:` in deck.yaml)")]
    out = []
    textv = str(card.get("text") or "")
    spans = TARGET.findall(textv)
    if t == "sentence" and len(spans) != 1:
        out.append(Flag("!", "lang", f"`text:` needs exactly one **target word** (has {len(spans)})"))
    elif t == "grammar" and not spans:      # split patterns (しか…ない) mark several spans
        out.append(Flag("!", "lang", "`text:` needs the **grammar pattern** marked"))
    need = ("word", "gloss") if t == "sentence" else ("grammar", "meaning", "translation")
    for k in need:
        if not str(card.get(k) or "").strip():
            out.append(Flag("!", "lang", f"no `{k}:`"))
    if t == "sentence" and ctx.get("reading", True) and not str(card.get("reading") or "").strip():
        out.append(Flag("~", "lang", "no `reading:` for the target word"))
    n = ctx["length"](textv)
    if n > ctx["cap"]:
        out.append(Flag("~", "size", f"sentence {n} chars > cap {ctx['cap']} (longer lines fail more)"))
    for k in ("audio", "image"):
        name = str(card.get(k) or "").strip()
        if not name:
            if k == "audio" or t == "sentence":
                out.append(Flag("!", "media", f"no `{k}:`"))
        elif ctx["has_media_dir"] and Path(name).name.lower() not in ctx["media"]:
            out.append(Flag("!", "media", f"{k} {name} not found in media_dir"))
    return out

