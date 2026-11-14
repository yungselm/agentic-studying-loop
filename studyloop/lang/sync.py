"""`asl lang sync <export.apkg>`: the vault follows what the user studies in Anki.

Sentence cards (tag `asl::id::<id>`) move their word to `learning` (reviewed) or `known` (mature,
>= 21 days); grammar cards and Game Gengo lessons do the same for their grammar note (matched by
JLPT Sensei link, else by form). Statuses only go up: a lapse or an unstudied lesson never lowers
a status (hand-set ones stay). Then the plan runs again, so waiting lines are released."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import yaml

from ..cards import load_file
from ..config import load_deck
from .apkg import read_export
from .vocab import RANK

GRAMMAR_RANK = {"unknown": 0, "planned": 1, "learning": 2, "known": 3}


def _state(note) -> str | None:
    return "known" if note.mature else "learning" if note.reviewed else None


def _asl_id(note) -> str | None:
    return next((t.split("::", 2)[2] for t in note.tags if t.startswith("asl::id::")), None)


def sync(d, vocab, export: Path) -> dict:
    from .grammar import _norm_forms, split_frontmatter
    ex = read_export(export)
    deck = load_deck(d.path)
    cards = {str(c["id"]): c for f in deck.files() for c in load_file(f) if c.get("id")}
    by_id = {i: n for n in ex.notes if (i := _asl_id(n))}
    tok = vocab.tok
    out = Counter()

    # 1. sentence cards -> their word (the card's line decides the word, as in plan)
    for cid, note in by_id.items():
        c = cards.get(cid)
        st = _state(note)
        if not c or c.get("type") != "sentence" or not st:
            continue
        k = tok.key_for(str(c.get("word") or ""))
        e = vocab.entries.get(k) if k else None
        if e and RANK[st] > RANK[e.status]:
            e.status = st
            out[f"words {st}"] += 1

    # 2. grammar: asl grammar cards (their note link) and Game Gengo lessons (link, else form)
    gdir = d.notes_dir / "Grammar"
    notes = {}
    for p in sorted(gdir.glob("*.md")) if gdir.is_dir() else []:
        meta, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        if meta.get("type") == "grammar":
            notes[p.stem] = (p, meta)
    by_link = {str(m.get("link") or "").lower(): t for t, (_, m) in notes.items() if m.get("link")}
    by_form = {}
    for t, (_, m) in notes.items():
        for f in _norm_forms(str(m.get("grammar") or t)):
            by_form.setdefault(f, t)
    best: dict[str, str] = {}

    def offer(title: str | None, st: str | None) -> None:
        if title and st and GRAMMAR_RANK[st] > GRAMMAR_RANK.get(best.get(title, "unknown"), 0):
            best[title] = st

    for cid, note in by_id.items():
        c = cards.get(cid)
        if c and c.get("type") == "grammar":
            links = c.get("note") if isinstance(c.get("note"), list) else [c.get("note")]
            title = next((m.group(1) for x in links if x and (m := re.match(r"\[\[([^\]|#]+)", str(x)))), None)
            offer(title, _state(note))
    for note in ex.notes:
        if not note.model.startswith("GameGengoGrammar"):
            continue
        link = re.search(r'href="([^"]+)"', note.fields.get("GrammarLink", "") or "")
        grammar = re.sub(r"<[^>]+>|&nbsp;|​", "", note.fields.get("Grammar", ""))
        title = by_link.get(link.group(1).lower()) if link else None
        title = title or next((by_form[f] for f in _norm_forms(grammar) if f in by_form), None)
        offer(title, _state(note))
    for title, st in best.items():
        p, meta = notes[title]
        if GRAMMAR_RANK[st] > GRAMMAR_RANK.get(str(meta.get("status") or "unknown"), 0):
            _, fm, body = p.read_text(encoding="utf-8").split("---\n", 2)
            m = yaml.safe_load(fm) or {}
            m["status"] = st
            p.write_text("---\n" + yaml.safe_dump(m, allow_unicode=True, sort_keys=False, width=1000)
                         + "---\n" + body, encoding="utf-8")
            out[f"grammar {st}"] += 1

    # 3. how the language cards do, per source (an early look at the evidence)
    per = Counter()
    for cid, note in by_id.items():
        c = cards.get(cid)
        if not c or not note.reviews:
            continue
        src = str(c.get("line") or "").split("-")[0] or str(c.get("type"))
        per[(src, "reviews")] += note.reviews
        per[(src, "fails")] += note.fails
    out["_per_source"] = {s: (per[(s, "reviews")], per[(s, "fails")])
                          for s in sorted({s for s, _ in per})}
    out["_cards_found"] = len([i for i in by_id if i in cards])
    return out
