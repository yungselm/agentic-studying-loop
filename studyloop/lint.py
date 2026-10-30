"""Lint cards without running them: ids, sizes, self-containment.

    asl lint path/to/deck [files...]

  [id]       missing / duplicate ids, wrong prefix for this deck
  [size]     over the hard limits in studyloop.yaml (`~` = over target only)
  [xref]     the front points at another card ("like the previous card")
  [literal]  the solution produces a string the prompt never mentions
  [dup]      two cards with the same front
Project decks (profile.md or `repo:` in deck.yaml) also get [frame], [header],
[excerpt], [index] and [std]; see project_lint.py.

`!` = must fix (exit code 1), `~` = worth a look. `--quiet` prints only `!`;
`--skip size,frame` leaves out whole kinds (e.g. for an older deck).
"""
from __future__ import annotations

import re
from pathlib import Path

from . import cards as C
from . import project_lint as P
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


def _card_flags(card, lim, lint_cfg, prefix, seen, fname, fronts=None, retired=()):
    out = []
    if card.get("id") and str(card["id"]) in retired:
        out.append(("!", "id", "uses a retired id (deck.yaml retired_ids); give it a new one"))
    front = " ".join(str(card.get("instruction") or card.get("question") or "").split())
    if fronts is not None and front:
        if front in fronts:
            out.append(("!", "dup", f"same front as {fronts[front]}"))
        fronts.setdefault(front, f"{fname}: {C.label(card)}")
    cid = card.get("id")
    if not cid:
        out.append(("!", "id", "no id (`asl fix` adds them)"))
    else:
        if cid in seen:
            out.append(("!", "id", f"duplicate id, also in {seen[cid]}"))
        seen[cid] = fname
        if prefix and not str(cid).startswith(f"{prefix}-"):
            out.append(("~", "id", f"id doesn't use this deck's prefix '{prefix}-'"))
    m = C.measures(card)
    if card["type"] == "code":
        lc, n = lim["code"], m["typed_chars"]
        if n > lc["typed_chars_max"]:
            out.append(("!", "size", f"typed {n} chars > max {lc['typed_chars_max']} "
                        "(pre-fill more, or split into a ladder)"))
        elif n > lc["typed_chars_target"]:
            out.append(("~", "size", f"typed {n} chars > target {lc['typed_chars_target']}"))
        if XREF.search(card.get("instruction") or ""):
            out.append(("!", "xref", "front refers to another card"))
        out += [("!", "literal", msg) for msg in literal_flags(card, lint_cfg)]
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
    return out


def lint(groups: list[tuple[Deck, list[Path]]], quiet: bool = False,
         skip: frozenset[str] = frozenset()) -> int:
    hard = soft = 0
    seen: dict[str, str] = {}
    fronts: dict[str, str] = {}

    def report(sev, kind, where, msg):
        nonlocal hard, soft
        if kind in skip:
            return
        hard += sev == "!"
        soft += sev == "~"
        if sev == "!" or not quiet:
            print(f"{sev} [{kind}] {where} -> {msg}")

    for deck, files in groups:
        lim = find_home(deck.path).limits
        prefix = deck.cfg.get("prefix")
        roles, repo = P.file_roles(deck), P.repo_dir(deck)
        if repo is not None and not repo.is_dir():
            report("!", "repo", deck.path.name, f"repo path in deck.yaml not found: {repo}")
            repo = None
        ids = []
        for f in files:
            pack = deck.file_opts(f).get("pack") or deck.pack
            lint_cfg = load_pack(pack).get("lint", {}) if pack else {}
            for card in C.load_file(f):
                flags = _card_flags(card, lim, lint_cfg, prefix, seen, f.name, fronts,
                                     {str(i) for i in deck.cfg.get("retired_ids") or []})
                flags += P.check_card(deck, card, lint_cfg, deck.checked(f), roles, repo)
                for sev, kind, msg in flags:
                    report(sev, kind, f"{f.name}: {C.label(card)}", msg)
                if card.get("id"):
                    ids.append(str(card["id"]))
        if set(files) >= set(deck.files()):          # whole deck given: check the index
            for sev, kind, msg in P.check_index(deck, ids):
                report(sev, kind, deck.path.name, msg)
    if hard or soft:
        print(f"\n{hard} problem(s) (!), {soft} note(s) (~)" + (" hidden by --quiet" if quiet and soft else "") + ".")
    else:
        print("\nOK - all cards pass.")
    return 1 if hard else 0
