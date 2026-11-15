"""`asl lang draft`: sentence-card stubs for the next planned lines, in plan order.

Each stub has the text with furigana and the target in `**…**`, the word, its reading, audio,
image, line and source; `gloss: ""` is left for the agent (the sense used in this line, in the
brief's gloss language). The dictionary senses are printed for that, nothing else."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import yaml

from ..core.config import load_deck
from .cardfile import card_item
from .plan import compute, grammar_links, write_state

SENSES_PER_LANG = 3


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "source"


def _source_meta(deck_dir: Path, key: str) -> dict:
    p = deck_dir / "lines" / f"{key}.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}


def _next_number(deck, prefix: str, st) -> int:
    """After every id in use, retired, or remembered by a rejected line (never reissued)."""
    from ..core.ids import _num, used_ids
    ids = set(used_ids(deck, []))
    ids |= {ln.status.split(":", 1)[1] for lines in st.by_src.values() for ln in lines
            if ln.status.startswith(("card:", "rejected:"))}
    return max((_num(i) for i in ids if str(i).startswith(prefix + "-")), default=0) + 1


def draft(d, vocab, levels, n: int, current: str | None, assume: list[str],
          source: str | None = None) -> int:
    deck = load_deck(d.path)
    st = compute(d.path, vocab, levels, d.cfg, current, assume,
                 str(d.brief.get("gloss_language") or "en"), d.notes_dir,
                 str(d.brief.get("grammar_gate") or "learning"))
    picked = [(k, i) for k, i in st.plan.order
              if not source or st.items[i].source.startswith(source)][:n]   # in plan order
    if not picked:
        print("Nothing ready: every one-new-word line has a card, or is parked.")
        return 0
    dic = d.language.dictionary()
    langs = list(dict.fromkeys([str(d.brief.get("gloss_language") or "en"), "en"]))
    prefix = deck.cfg.get("prefix") or d.lang
    num = _next_number(deck, prefix, st)
    by_file: dict[Path, list[str]] = defaultdict(list)
    print(f"Drafted {len(picked)} card(s): write each `gloss:` (the sense used in the line, "
          f"in {langs[0]}, a few words), check the reading, then `asl lint`.\n")
    for k, i in picked:
        it, e = st.items[i], vocab.entries[k]
        meta = _source_meta(d.path, it.source)
        title = str(meta.get("title") or it.source)
        toks = vocab.tok(it.line.text)
        tgt = next((t for t in toks if t.key == k), None)
        word = tgt.word if tgt else e.word        # as spelled in this line: 撮る, not 取る
        reading = d.language.reading(word, tgt, e.reading)
        entries = dic.lookup(word, reading, tgt.pos if tgt else "") if dic else []
        if entries and reading not in dic.readings(entries[0]):
            reading = dic.readings(entries[0])[0]
        cid = f"{prefix}-{num:03d}"
        num += 1
        card = {"id": cid, "type": "sentence", "text": d.language.annotate(toks, k), "word": word,
                "reading": reading, "gloss": "", "audio": it.line.audio, "image": it.line.image,
                "grammar": grammar_links(it.grammar),
                "line": it.line.id, "source": f"{title} · {it.line.start[:8]}"}
        by_file[d.path / f"vocabulary__{_slug(title)}.yaml"].append(card_item(card, keep_empty=("gloss",)))
        lvl = st.prio.effective_level(k)
        print(f"{cid}  {word}【{reading}】 {lvl}  {it.line.text}")
        if entries:
            print("\n".join("    " + ln for ln in dic.senses_text(entries[0], langs, SENSES_PER_LANG).splitlines()))
        else:
            print("    (not in the dictionary: gloss from the context)")
    for f, items in by_file.items():
        head = "" if f.exists() and f.read_text(encoding="utf-8").strip() else \
            "# Sentence cards (asl lang draft). Fill `gloss:`; delete a card to reject its line.\n"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(head + "".join(items))
        print(f"\n→ {f}")
    st = compute(d.path, vocab, levels, d.cfg, current, assume,       # lines now `card:<id>`
                 str(d.brief.get("gloss_language") or "en"), d.notes_dir,
                 str(d.brief.get("grammar_gate") or "learning"))
    write_state(st, vocab, levels)
    return 0
