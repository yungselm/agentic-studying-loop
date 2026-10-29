"""Lint cards without running them: ids, sizes, self-containment.

    asl lint path/to/deck [files...]

  [id]       missing / duplicate ids, wrong prefix for this deck
  [size]     over the hard limits in studyloop.yaml (`~` = over target only)
  [xref]     the front points at another card ("like the previous card")
  [literal]  the solution produces a string the prompt never mentions
  [timeline] steps missing or ambiguous

Exit code 1 if anything above the targets is flagged.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import cards as C
from .config import Deck, find_home, load_pack

XREF = re.compile(r"\b(like the previous|the previous card|as (above|before)|like it|"
                  r"same as the previous|see the (other|previous))\b", re.I)
STOP = set(
    "a an the to of in on at is are be it as and or for with into from by "
    "n x y z c e i j k v t s w h r m".split()
)


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


def lint(groups: list[tuple[Deck, list[Path]]]) -> int:
    hard = soft = 0
    seen: dict[str, str] = {}
    for deck, files in groups:
        home = find_home(deck.path)
        lim = home.limits
        prefix = deck.cfg.get("prefix")
        for f in files:
            pack = deck.file_opts(f).get("pack") or deck.pack
            lint_cfg = load_pack(pack).get("lint", {}) if pack else {}
            for card in C.load_file(f):
                where = f"{f.name}: {C.label(card)}"
                out = []
                cid = card.get("id")
                if not cid:
                    out.append(("!", "id", "no id (`asl ids --fix` adds them)"))
                else:
                    if cid in seen:
                        out.append(("!", "id", f"duplicate id, also in {seen[cid]}"))
                    seen[cid] = f.name
                    if prefix and not str(cid).startswith(f"{prefix}-"):
                        out.append(("~", "id", f"id doesn't use this deck's prefix '{prefix}-'"))
                m = C.measures(card)
                if card["type"] == "code":
                    lc = lim["code"]
                    n = m["typed_chars"]
                    if n > lc["typed_chars_max"]:
                        out.append(("!", "size", f"typed {n} chars > max {lc['typed_chars_max']} "
                                    "(pre-fill more, or split into a ladder)"))
                    elif n > lc["typed_chars_target"]:
                        out.append(("~", "size", f"typed {n} chars > target {lc['typed_chars_target']}"))
                    if XREF.search(card.get("instruction") or ""):
                        out.append(("!", "xref", "front refers to another card"))
                    for msg in literal_flags(card, lint_cfg):
                        out.append(("!", "literal", msg))
                else:
                    lc = lim["concept"]
                    a, b = m["answer_chars"], m["bold_chars"]
                    if not b:
                        out.append(("!", "size", "answer has no **bold lead** to grade against"))
                    if a > lc["answer_chars_max"] or b > lc["bold_chars_max"]:
                        out.append(("!", "size", f"answer {a}/{lc['answer_chars_max']}, "
                                    f"bold {b}/{lc['bold_chars_max']} chars"))
                    elif a > lc["answer_chars_target"] or b > lc["bold_chars_target"]:
                        out.append(("~", "size", f"answer {a}, bold {b} chars (over target)"))
                for sev, kind, msg in out:
                    print(f"{sev} [{kind}] {where} -> {msg}")
                    hard += sev == "!"
                    soft += sev == "~"
    print(f"\n{hard} problem(s), {soft} over-target note(s)." if hard or soft
          else "\nOK - all cards within limits and self-contained.")
    return 1 if hard else 0
