# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Core's card types: code, concept, timeline, cloze (docs/card-format.md).

Each says how it is measured, linted and turned into an Anki note; the engines in lint.py,
build.py and check.py only call these hooks."""
from __future__ import annotations

import re
from pathlib import Path

from studyloop.core import cards as C
from studyloop.core.config import ANKI
from studyloop.core.config.vault import vault_index
from studyloop.core.registry import CardType, CodeBlock, Flag, Template

TEMPLATES = ANKI / "templates"
XREF = re.compile(r"\b(like the previous|the previous card|as (above|before)|like it|"
                  r"same as the previous|see the (other|previous))\b", re.I)
STOP = set(
    "a an the to of in on at is are be it as and or for with into from by "
    "n x y z c e i j k v t s w h r m".split()
)
WIKI = re.compile(r"(!?)\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")


class Code(CardType):
    """Type the gap into an editor; on flip, lines that differ from the solution turn red."""
    name, model_name = "code", "Code Editor Card"
    model_id = 1607392319                   # same ids as rust-lang-kata, so its decks can migrate
    fields = ("Instruction", "StarterCode", "Solution", "Lang", "Notes", "Source", "Walkthrough")
    templates = (Template("Code Card", "front.html", "back.html"),)
    templates_dir = TEMPLATES
    default_limits = {"typed_chars_target": 80, "typed_chars_max": 120}

    def front(self, card):
        return str(card.get("instruction") or "")

    def measures(self, card):
        t = C.typed(card.get("starter"), card.get("solution"))
        return {"typed_chars": sum(map(len, t)), "typed_lines": len(t)}

    def lint(self, card, ctx):
        out = []
        n, lc = self.measures(card)["typed_chars"], ctx.limits
        if n > lc["typed_chars_max"]:
            out.append(Flag("!", "size", f"typed {n} chars > max {lc['typed_chars_max']} "
                            "(pre-fill more, or split into a ladder)"))
        elif n > lc["typed_chars_target"]:
            out.append(Flag("~", "size", f"typed {n} chars > target {lc['typed_chars_target']}"))
        if XREF.search(card.get("instruction") or ""):
            out.append(Flag("!", "xref", "front refers to another card"))
        out += [Flag("!", "literal", msg) for msg in literal_flags(card, ctx.pack)]
        frame = ctx.pack.get("frame")
        if frame and not re.search(frame, card.get("solution") or "", re.M):
            out.append(Flag("!" if ctx.kind.frame_required else "~", "frame",
                            "no enclosing function/type visible (context frame, standards §2a)"))
        return out

    def to_fields(self, card, ctx):
        return [ctx.text(str(card["instruction"]).rstrip("\n")), ctx.code(card.get("starter", "")),
                ctx.code(card.get("solution", "")), ctx.pack_mode, ctx.text(card.get("notes", "")),
                ctx.text(card.get("source", "")), ctx.code(card.get("walkthrough", ""))]

    def code_blocks(self, card):
        sol = card.get("solution")
        return [CodeBlock("solution", sol, card.get("tests") or "")] if sol else []


class Concept(CardType):
    """Question -> short answer with a **bold lead** to grade against."""
    name, model_name = "concept", "Concept Card"
    model_id = 1607392321
    fields = ("Question", "Answer", "Code", "Lang", "Source")
    templates = (Template("Concept Card", "front_concept.html", "back_concept.html"),)
    templates_dir = TEMPLATES
    default_limits = {"answer_chars_target": 250, "answer_chars_max": 300,
                      "bold_chars_target": 120, "bold_chars_max": 150}

    def front(self, card):
        return str(card.get("question") or "")

    def measures(self, card):
        a = C.EMBED.sub("", card.get("answer") or "")       # an image is not answer text
        return {"answer_chars": len(C.plain(a)), "bold_chars": len(C.bold_lead(a))}

    def lint(self, card, ctx):
        out, lc = [], ctx.limits
        m = self.measures(card)
        a, b = m["answer_chars"], m["bold_chars"]
        if not b:
            out.append(Flag("!", "size", "answer has no **bold lead** to grade against"))
        if a > lc["answer_chars_max"] or b > lc["bold_chars_max"]:
            out.append(Flag("!", "size", f"answer {a}/{lc['answer_chars_max']}, "
                            f"bold {b}/{lc['bold_chars_max']} chars"))
        elif a > lc["answer_chars_target"] or b > lc["bold_chars_target"]:
            out.append(Flag("~", "size", f"answer {a}, bold {b} chars (over target)"))
        return out + vault_flags(card, ("question", "answer"), ctx.vault)

    def to_fields(self, card, ctx):
        return [ctx.rich(card["question"]), ctx.rich(card.get("answer")),
                ctx.code(card.get("code", "")), ctx.pack_mode, ctx.source(card)]


class Timeline(Concept):
    """Ordered `steps:`, shown shuffled as A-E; a concept card once loaded."""
    name = "timeline"
    limits_name = "concept"
    default_limits = {}

    def prepare(self, card):
        return C.expand_timeline(card)


class Cloze(CardType):
    """Short gaps, 2-5 per note; Anki makes one card per gap number."""
    name, model_name = "cloze", "Cloze Card"
    model_id = 1607392323
    fields = ("Text", "Extra", "Hook", "Source")
    templates = (Template("Cloze Card", "front_cloze.html", "back_cloze.html"),)
    templates_dir = TEMPLATES
    cloze = True
    default_limits = {"gap_chars_target": 20, "gap_chars_max": 80}

    def front(self, card):
        return str(card.get("text") or "")

    def measures(self, card):
        g = C.gap_answers(card.get("text"))
        return {"gaps": len(g), "gap_chars": max(g.values(), default=0),
                "hook": int(bool(str(card.get("hook") or "").strip()))}

    def lint(self, card, ctx):
        out, lc = [], ctx.limits
        g = C.gap_answers(card.get("text"))
        if not g:
            return [Flag("!", "size", "cloze card without a {{gap}} in `text:`")]
        n = max(g.values())
        if n > lc["gap_chars_max"]:
            out.append(Flag("!", "size", f"a gap asks {n} chars > max {lc['gap_chars_max']} "
                            "(shorter answer, or split it into more gaps)"))
        elif n > lc["gap_chars_target"]:
            out.append(Flag("~", "size", f"a gap asks {n} chars > target {lc['gap_chars_target']}"))
        if len(g) == 1:
            out.append(Flag("~", "gaps", "one gap: 2-5 gaps per note fail less; gap the related "
                            "facts and the name they belong to"))
        if not str(card.get("source") or "").strip():
            out.append(Flag("~", "source", "no `source:` (the vault note, `[[Note#Section]]`)"))
        return out + vault_flags(card, ("text", "extra", "hook"), ctx.vault)

    def to_fields(self, card, ctx):
        return [ctx.rich(C.cloze_text(card.get("text"))), ctx.rich(card.get("extra")),
                ctx.rich(card.get("hook")), ctx.source(card)]

    def tags(self, card):
        return ["asl::hook"] if str(card.get("hook") or "").strip() else []


CORE_TYPES = (Code(), Concept(), Timeline(), Cloze())


# ---- lint helpers -------------------------------------------------------------------

def _words(s):
    s = re.sub(r"\{[^}]*\}", " ", s)
    return [w.lower() for w in re.findall(r"[A-Za-z]{2,}", s)]


def _norm(s):
    return " " + re.sub(r"\s+", " ", s.lower()) + " "


def _literals(rx: re.Pattern, s: str) -> set[str]:
    out = set()
    for m in rx.finditer(s):
        groups = [g for g in m.groups() if g is not None] or [m.group(0)]
        out.add(groups[0])
    return out


def literal_flags(card: dict, lint_cfg: dict) -> list[str]:
    """Strings the solution produces that the prompt never mentions."""
    if not lint_cfg:
        return []
    comment = re.compile(lint_cfg.get("comment", r"(?!x)x"))
    string = re.compile(lint_cfg.get("string", r"(?!x)x"))
    ignore = re.compile(lint_cfg.get("ignore_messages", r"(?!x)x"))
    instr = card.get("instruction") or ""
    ctx = _norm(instr + " " + (card.get("notes") or ""))
    clean = ignore.sub("", comment.sub("", card.get("solution") or ""))
    given = _literals(string, comment.sub("", card.get("starter") or ""))
    allow = set(card.get("lint_allow") or [])
    flags = []
    for lit in sorted(_literals(string, clean) - given - allow):
        missing = [w for w in _words(lit) if w not in STOP and w not in ctx]
        if missing:
            flags.append(f'solution emits "{lit}" (missing from prompt: {missing})')
    return flags


def vault_flags(card: dict, fields, vault: Path | None) -> list[Flag]:
    """`[[Note]]` in `source:` and `![[image]]` embeds in `fields` must exist in the vault."""
    if vault is None:
        return []
    out = []
    notes, files = vault_index(vault)
    for m in WIKI.finditer(str(card.get("source") or "")):
        target = m.group(2).split("#")[0].strip().lower()
        if target not in notes and target not in files:     # a note, or a file (book.pdf#page=4)
            out.append(Flag("~", "source", f"[[{m.group(2)}]] not found in {vault.name}"))
    for field in fields:
        for m in C.EMBED.finditer(str(card.get(field) or "")):
            name = m.group(1) or m.group(2)
            if Path(name).suffix.lower() not in C.IMAGE_EXT:
                continue
            if Path(name).name.lower() not in files and not (card["_file"].parent / name).is_file():
                out.append(Flag("!", "media", f"{field}: image {name} not found"))
    return out

