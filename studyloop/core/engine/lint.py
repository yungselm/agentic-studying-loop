"""Lint cards without running them: ids, sizes, self-containment.

    asl lint path/to/deck [files...]

Every card (here):
  [id]       missing / duplicate / retired ids, wrong prefix for this deck
  [dup]      two cards with the same front
  [kind]     an unknown card type, or one that doesn't belong to the deck's kind;
             deck.yaml without `kind:` or with an unknown one
  [pack]     `lang:` on a card (renamed to `pack:`)
  [index]    a card has no row in Overview.md (or a row has no card)
Per card type (core/cards/types.py, and each module's own types):
  [size]     over the limits in studyloop.yaml (`~` = over target only)
  [xref] [literal] [frame]   code cards: points at another card, emits a string the prompt
             never mentions, no enclosing function/type visible
  [gaps]     a cloze card with one gap (2-5 fail less)
  [source]   a `[[Note]]` source isn't in the vault; [media] an embedded image is missing
  [lang]     sentence/grammar cards: one **target**, word + gloss, length cap
Lint rules of modules: [header] [excerpt] [std] [repo] (project decks), [mix] (topic decks).

`!` = must fix (exit code 1), `~` = worth a look. `--quiet` prints only `!`;
`--skip size,frame` leaves out whole kinds (e.g. for an older deck).
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from studyloop.core import cards as C
from studyloop.core.config import Deck, find_home, load_pack
from studyloop.core.config.vault import vault_for
from studyloop.core.registry import DeckSummary, Flag, LintContext, registry


def kind_flags(deck: Deck) -> list[Flag]:
    """deck.yaml states its kind; decks from before `kind:` are detected (see Deck.detected_kinds)."""
    if not (deck.path / "deck.yaml").is_file():
        return []
    kinds = registry().deck_kinds
    k = deck.cfg.get("kind")
    if k is None:
        found = deck.detected_kinds()
        if len(found) > 1:
            return [Flag("!", "kind", f"looks like {' and '.join(found)}: set `kind:` in deck.yaml")]
        return [Flag("~", "kind", f"no `kind:` (`asl fix` writes `kind: {found[0]}`)")]
    if k not in kinds:
        return [Flag("!", "kind", f"unknown `kind: {k}` (one of: {', '.join(kinds)})")]
    return []


def card_flags(card: dict, prefix: str | None, seen: dict, fname: str, fronts: dict,
               retired: set[str]) -> list[Flag]:
    """What every card needs, whatever its type: an id of its own, a front of its own."""
    out = []
    if card.get("id") and str(card["id"]) in retired:
        out.append(Flag("!", "id", "uses a retired id (deck.yaml retired_ids); give it a new one"))
    t = registry().card_types.get(card["type"])
    front = " ".join((t.front(card) if t else "").split())
    if front:
        if front in fronts:
            out.append(Flag("!", "dup", f"same front as {fronts[front]}"))
        fronts.setdefault(front, f"{fname}: {C.label(card)}")
    cid = card.get("id")
    if not cid:
        out.append(Flag("!", "id", "no id (`asl fix` adds them)"))
    else:
        if cid in seen:
            out.append(Flag("!", "id", f"duplicate id, also in {seen[cid]}"))
        seen[cid] = fname
        if prefix and not str(cid).startswith(f"{prefix}-"):
            out.append(Flag("~", "id", f"id doesn't use this file's prefix '{prefix}-'"))
    return out


def index_flags(deck: Deck, card_ids: list[str]) -> list[Flag]:
    """Overview.md's card index: a row per card, a card per row (kinds with `card_index`)."""
    ov = deck.path / "Overview.md"
    if not deck.kind_spec.card_index or not ov.is_file():
        return []
    text = ov.read_text(encoding="utf-8")
    out = [Flag("!", "index", f"{cid} has no row in Overview.md")
           for cid in card_ids if not re.search(rf"(?<![\w-]){re.escape(cid)}(?![\w-])", text)]
    listed = set()
    for prefix in deck.prefixes():
        listed |= set(re.findall(rf"^\|\s*({re.escape(prefix)}-\d+)\s*\|", text, re.M))
    if listed:
        retired = {str(i) for i in deck.cfg.get("retired_ids") or []}
        out += [Flag("~", "index", f"Overview.md row {cid} has no card (add it to retired_ids?)")
                for cid in sorted(listed - set(card_ids) - retired)]
    return out


def lint(groups: list[tuple[Deck, list[Path]]], quiet: bool = False,
         skip: frozenset[str] = frozenset()) -> int:
    reg = registry()
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
        spec = deck.kind_spec
        rules = [r for r in reg.lint_rules if r.kinds is None or spec.name in r.kinds]
        retired = {str(i) for i in deck.cfg.get("retired_ids") or []}
        memo: dict = {}
        for sev, kind, msg in kind_flags(deck):
            report(sev, kind, f"{deck.path.name}/deck.yaml", msg)
        ids, types = [], Counter()
        for f in files:
            pack = deck.file_opts(f).get("pack") or deck.pack
            lint_cfg = load_pack(pack).get("lint", {}) if pack else {}
            for card in C.load_file(f):
                flags = card_flags(card, deck.prefix_for(f), seen, f.name, fronts, retired)
                t = reg.card_types.get(card["type"])
                if t is None:
                    flags.append(Flag("!", "kind", f"unknown card type `{card['type']}` "
                                      f"(installed: {', '.join(reg.card_types)})"))
                else:
                    ctx = LintContext(deck, spec, f, lim.get(t.limits_name or t.name, {}),
                                      lint_cfg, vault, memo)
                    flags += t.lint(card, ctx)
                    for r in rules:
                        if r.card:
                            flags += r.card(card, ctx)
                if "lang" in card:
                    flags.append(Flag("!", "pack", "`lang:` on a card is now `pack:` (lang: means "
                                      "a spoken language, in deck.yaml)"))
                types[card["type"]] += 1
                if t is not None and card["type"] not in spec.card_types:
                    flags.append(Flag("!", "kind", f"a {card['type']} card in a {spec.name} deck "
                                      f"(its cards: {', '.join(spec.card_types)})"))
                for sev, kind, msg in flags:
                    report(sev, kind, f"{f.name}: {C.label(card)}", msg)
                if card.get("id"):
                    ids.append(str(card["id"]))
        summary = DeckSummary(ids, types, set(files) >= set(deck.files()))
        for r in rules:
            if r.deck:
                for sev, kind, msg in r.deck(deck, summary):
                    report(sev, kind, deck.path.name, msg)
        if summary.whole:                       # whole deck given: check the index
            for sev, kind, msg in index_flags(deck, ids):
                report(sev, kind, deck.path.name, msg)
    if hard or soft:
        print(f"\n{hard} problem(s) (!), {soft} note(s) (~)" + (" hidden by --quiet" if quiet and soft else "") + ".")
    else:
        print("\nOK - all cards pass.")
    return 1 if hard else 0
