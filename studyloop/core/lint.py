"""Lint cards without running them: ids, sizes, self-containment.

    asl lint path/to/deck [files...]

  [id]       missing / duplicate ids, wrong prefix for this deck
  [size]     over the hard limits in studyloop.yaml (`~` = over target only)
  [xref]     the front points at another card ("like the previous card")
  [literal]  the solution produces a string the prompt never mentions
  [dup]      two cards with the same front
  [gaps]     a cloze card with one gap (2-5 fail less)
  [source]   a `[[Note]]` source isn't in the vault; [media] an embedded image is missing
  [lang]     sentence/grammar cards: one **target**, word + gloss, length cap; [media] clip missing
  [kind]     a card type that doesn't belong to the deck's kind (project / topic / language);
             deck.yaml without `kind:` or with an unknown one
  [pack]     `lang:` on a card (renamed to `pack:`)
  [mix]      a topic deck's share of code cards is far from its brief's `cards:` (Overview.md)
Project decks (profile.md or `repo:` in deck.yaml) also get [frame], [header],
[excerpt], [index] and [std]; see project_lint.py.

`!` = must fix (exit code 1), `~` = worth a look. `--quiet` prints only `!`;
`--skip size,frame` leaves out whole kinds (e.g. for an older deck).
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .. import project_lint as P
from . import cards as C
from .config import DECK_KINDS, Deck, find_home, load_pack
from .vault import split_frontmatter, vault_for, vault_index

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


def cloze_flags(card: dict, lc: dict, vault: Path | None = None) -> list[tuple[str, str, str]]:
    out = []
    g = C.gap_answers(card.get("text"))
    if not g:
        out.append(("!", "size", "cloze card without a {{gap}} in `text:`"))
        return out
    n = max(g.values())
    if n > lc["gap_chars_max"]:
        out.append(("!", "size", f"a gap asks {n} chars > max {lc['gap_chars_max']} "
                    "(shorter answer, or split it into more gaps)"))
    elif n > lc["gap_chars_target"]:
        out.append(("~", "size", f"a gap asks {n} chars > target {lc['gap_chars_target']}"))
    if len(g) == 1:
        out.append(("~", "gaps", "one gap: 2-5 gaps per note fail less; gap the related "
                    "facts and the name they belong to"))
    if not str(card.get("source") or "").strip():
        out.append(("~", "source", "no `source:` (the vault note, `[[Note#Section]]`)"))
    return out + vault_flags(card, ("text", "extra", "hook"), vault)


def vault_flags(card: dict, fields, vault: Path | None) -> list[tuple[str, str, str]]:
    """`[[Note]]` in `source:` and `![[image]]` embeds in `fields` must exist in the vault."""
    if vault is None:
        return []
    out = []
    notes, files = vault_index(vault)
    for m in WIKI.finditer(str(card.get("source") or "")):
        target = m.group(2).split("#")[0].strip().lower()
        if target not in notes and target not in files:     # a note, or a file (book.pdf#page=4)
            out.append(("~", "source", f"[[{m.group(2)}]] not found in {vault.name}"))
    for field in fields:
        for m in C.EMBED.finditer(str(card.get(field) or "")):
            name = m.group(1) or m.group(2)
            if Path(name).suffix.lower() not in C.IMAGE_EXT:
                continue
            if Path(name).name.lower() not in files and not (card["_file"].parent / name).is_file():
                out.append(("!", "media", f"{field}: image {name} not found"))
    return out


WIKI = re.compile(r"(!?)\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")


def _card_flags(card, lim, lint_cfg, prefix, seen, fname, fronts=None, retired=(), vault=None):
    out = []
    if card.get("id") and str(card["id"]) in retired:
        out.append(("!", "id", "uses a retired id (deck.yaml retired_ids); give it a new one"))
    front = " ".join(str(card.get("instruction") or card.get("question")
                         or card.get("text") or "").split())
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
            out.append(("~", "id", f"id doesn't use this file's prefix '{prefix}-'"))
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
    elif card["type"] == "cloze":
        out += cloze_flags(card, lim["cloze"], vault)
    elif card["type"] in ("sentence", "grammar"):
        pass                                  # lang_flags(), with the deck's language context
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
        out += vault_flags(card, ("question", "answer"), vault)
    return out


def mix_flags(deck: Deck, kinds: Counter) -> list[tuple[str, str, str]]:
    """Topic decks: the brief's `cards: {code: 0.3}` sets the share of code cards; far off -> note.
    Without it, a topic deck that is mostly code cards gets the reminder to decide."""
    if deck.kind != "topic" or sum(kinds.values()) < 10:
        return []
    ov = deck.path / "Overview.md"
    brief = split_frontmatter(ov.read_text(encoding="utf-8"))[0] if ov.is_file() else {}
    total, code = sum(kinds.values()), kinds["code"] / sum(kinds.values())
    want = (brief.get("cards") or {}).get("code") if isinstance(brief.get("cards"), dict) else None
    if want is None:
        return [("~", "mix", f"{code:.0%} code cards and no `cards:` in the brief: set e.g. "
                 "`cards: {code: 0.3}` in Overview.md (books about code) or `{code: 0}`")] if code > 0.4 else []
    if abs(code - float(want)) > 0.15:
        return [("~", "mix", f"{code:.0%} code cards ({kinds['code']} of {total}); the brief says "
                 f"{float(want):.0%} (`cards:` in Overview.md)")]
    return []


def kind_flags(deck: Deck) -> list[tuple[str, str, str]]:
    """deck.yaml states its kind; decks from before `kind:` are detected (see Deck.detected_kinds)."""
    if not (deck.path / "deck.yaml").is_file():
        return []
    k = deck.cfg.get("kind")
    if k is None:
        found = deck.detected_kinds()
        if len(found) > 1:
            return [("!", "kind", f"looks like {' and '.join(found)}: set `kind:` in deck.yaml")]
        return [("~", "kind", f"no `kind:` (`asl fix` writes `kind: {found[0]}`)")]
    if k not in DECK_KINDS:
        return [("!", "kind", f"unknown `kind: {k}` (one of: {', '.join(DECK_KINDS)})")]
    return []


TARGET = re.compile(r"\*\*(.+?)\*\*", re.S)


def lang_context(deck: Deck) -> dict | None:
    if not deck.cfg.get("lang"):
        return None
    from ..lang.setup import lang_config
    from .build import media_index
    try:
        cfg = lang_config(deck.cfg["lang"])
    except SystemExit:
        cfg = {}
    return {"cap": int(cfg.get("length_cap") or 10**6), "media": media_index(deck),
            "has_media_dir": bool(deck.cfg.get("media_dir"))}


def lang_flags(card: dict, ctx: dict | None) -> list[tuple[str, str, str]]:
    """Sentence and grammar cards (docs/language-cards.md)."""
    from ..lang.tokens import plain_text
    t = card["type"]
    if ctx is None:
        return [("!", "lang", f"a {t} card needs a language deck (`lang:` and `media_dir:` in deck.yaml)")]
    out = []
    textv = str(card.get("text") or "")
    spans = TARGET.findall(textv)
    if t == "sentence" and len(spans) != 1:
        out.append(("!", "lang", f"`text:` needs exactly one **target word** (has {len(spans)})"))
    elif t == "grammar" and not spans:      # split patterns (しか…ない) mark several spans
        out.append(("!", "lang", "`text:` needs the **grammar pattern** marked"))
    need = ("word", "gloss") if t == "sentence" else ("grammar", "meaning", "translation")
    for k in need:
        if not str(card.get(k) or "").strip():
            out.append(("!", "lang", f"no `{k}:`"))
    if t == "sentence" and not str(card.get("reading") or "").strip():
        out.append(("~", "lang", "no `reading:` for the target word"))
    n = len(re.sub(r"[\s、。！？!?…‥・「」『』“”\"'（）()~〜―-]", "", plain_text(textv)))
    if n > ctx["cap"]:
        out.append(("~", "size", f"sentence {n} chars > cap {ctx['cap']} (longer lines fail more)"))
    for k in ("audio", "image"):
        name = str(card.get(k) or "").strip()
        if not name:
            if k == "audio" or t == "sentence":
                out.append(("!", "media", f"no `{k}:`"))
        elif ctx["has_media_dir"] and Path(name).name.lower() not in ctx["media"]:
            out.append(("!", "media", f"{k} {name} not found in media_dir"))
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
        vault = vault_for(deck.path)
        roles, repo = P.file_roles(deck), P.repo_dir(deck)
        if repo is not None and not repo.is_dir():
            report("!", "repo", deck.path.name, f"repo path in deck.yaml not found: {repo}")
            repo = None
        ids = []
        lctx = lang_context(deck)
        allowed = DECK_KINDS[deck.kind]["cards"]
        for sev, kind, msg in kind_flags(deck):
            report(sev, kind, f"{deck.path.name}/deck.yaml", msg)
        kinds = Counter()
        for f in files:
            pack = deck.file_opts(f).get("pack") or deck.pack
            lint_cfg = load_pack(pack).get("lint", {}) if pack else {}
            for card in C.load_file(f):
                flags = _card_flags(card, lim, lint_cfg, deck.prefix_for(f), seen, f.name, fronts,
                                     {str(i) for i in deck.cfg.get("retired_ids") or []}, vault)
                flags += P.check_card(deck, card, lint_cfg, deck.checked(f), roles, repo)
                if card["type"] in ("sentence", "grammar"):
                    flags += lang_flags(card, lctx)
                if "lang" in card:
                    flags.append(("!", "pack", "`lang:` on a card is now `pack:` (lang: means a "
                                  "spoken language, in deck.yaml)"))
                kinds[card["type"]] += 1
                if card["type"] not in allowed:
                    flags.append(("!" if card["type"] in ("sentence", "grammar") or deck.kind == "language"
                                  else "~", "kind", f"a {card['type']} card in a {deck.kind} deck "
                                  f"(its cards: {', '.join(allowed)})"))
                for sev, kind, msg in flags:
                    report(sev, kind, f"{f.name}: {C.label(card)}", msg)
                if card.get("id"):
                    ids.append(str(card["id"]))
        for sev, kind, msg in mix_flags(deck, kinds):
            report(sev, kind, deck.path.name, msg)
        if set(files) >= set(deck.files()):          # whole deck given: check the index
            for sev, kind, msg in P.check_index(deck, ids):
                report(sev, kind, deck.path.name, msg)
    if hard or soft:
        print(f"\n{hard} problem(s) (!), {soft} note(s) (~)" + (" hidden by --quiet" if quiet and soft else "") + ".")
    else:
        print("\nOK - all cards pass.")
    return 1 if hard else 0
