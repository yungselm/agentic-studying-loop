"""`asl lang draft`: sentence-card stubs for the next planned lines, in plan order.

Each stub has the text with furigana and the target in `**…**`, the word, its reading, audio,
image, line and source; `gloss: ""` is left for the agent (the sense used in this line, in the
brief's gloss language). The dictionary senses are printed for that, nothing else."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import yaml

from ..config import load_deck
from .plan import compute, write_state
from .tokens import furigana

SENSES_PER_LANG = 3
FIELDS = ("id", "type", "text", "word", "reading", "gloss", "audio", "image", "line", "source")


def _katakana(s: str) -> bool:
    return bool(s) and all("ァ" <= c <= "ヺ" or c == "ー" for c in s)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "source"


def _source_meta(deck_dir: Path, key: str) -> dict:
    p = deck_dir / "lines" / f"{key}.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}


def _item_yaml(card: dict) -> str:
    out = []
    for i, k in enumerate(FIELDS):
        v = card.get(k, "")
        val = v if k in ("id", "type", "line") else json.dumps(str(v), ensure_ascii=False)
        out.append(("- " if i == 0 else "  ") + f"{k}: {val}")
    return "\n".join(out) + "\n"


def _next_number(deck, prefix: str, st) -> int:
    """After every id in use, retired, or remembered by a rejected line (never reissued)."""
    from ..ids import _num, used_ids
    ids = set(used_ids(deck, []))
    ids |= {ln.status.split(":", 1)[1] for lines in st.by_src.values() for ln in lines
            if ln.status.startswith(("card:", "rejected:"))}
    return max((_num(i) for i in ids if str(i).startswith(prefix + "-")), default=0) + 1


def draft(d, vocab, levels, n: int, current: str | None, assume: list[str],
          source: str | None = None) -> int:
    deck = load_deck(d.path)
    st = compute(d.path, vocab, levels, d.cfg, current, assume,
                 str(d.brief.get("gloss_language") or "en"))
    picked = [(k, i) for k, i in st.plan.order
              if not source or st.items[i].source.startswith(source)][:n]   # in plan order
    if not picked:
        print("Nothing ready: every one-new-word line has a card, or is parked.")
        return 0
    dic = None
    if d.cfg.get("dictionary"):
        from .dictionary import Dictionary
        dic = Dictionary(d.cfg)
    from .dictionary import senses_text
    langs = list(dict.fromkeys([str(d.brief.get("gloss_language") or "en"), "en"]))
    fixes = d.cfg.get("reading_fixes") or {}
    prefix = deck.cfg.get("prefix") or d.lang
    num = _next_number(deck, prefix, st)
    by_file: dict[Path, list[str]] = defaultdict(list)
    print(f"Drafted {len(picked)} card(s): write each `gloss:` (the sense used in the line, "
          f"in {langs[0]}, a few words), check the reading, then `asl lint`.\n")
    for k, i in picked:
        it, e = st.items[i], vocab.entries[k]
        meta = _source_meta(d.path, it.source)
        title = str(meta.get("title") or it.source)
        toks = [replace(t, kana=fixes.get(t.surface, t.kana)) for t in vocab.tok(it.line.text)]
        tgt = next((t for t in toks if t.key == k), None)
        word = tgt.word if tgt else e.word        # as spelled in this line: 撮る, not 取る
        reading = fixes.get(word, tgt.reading if tgt else e.reading)
        if _katakana(word):                       # シーン: its reading is itself, not しーん
            reading = word
        entries = dic.lookup(word, reading, tgt.pos if tgt else "") if dic else []
        if entries and reading not in entries[0]["r"]:
            reading = entries[0]["r"][0]
        cid = f"{prefix}-{num:03d}"
        num += 1
        card = {"id": cid, "type": "sentence", "text": furigana(toks, k), "word": word,
                "reading": reading, "gloss": "", "audio": it.line.audio, "image": it.line.image,
                "line": it.line.id, "source": f"{title} · {it.line.start[:8]}"}
        by_file[d.path / f"vocabulary__{_slug(title)}.yaml"].append(_item_yaml(card))
        lvl = st.prio.effective_level(k)
        print(f"{cid}  {word}【{reading}】 {lvl}  {it.line.text}")
        if entries:
            print("\n".join("    " + ln for ln in senses_text(entries[0], langs, SENSES_PER_LANG).splitlines()))
        else:
            print("    (not in the dictionary: gloss from the context)")
    for f, items in by_file.items():
        head = "" if f.exists() and f.read_text(encoding="utf-8").strip() else \
            "# Sentence cards (asl lang draft). Fill `gloss:`; delete a card to reject its line.\n"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(head + "".join(items))
        print(f"\n→ {f}")
    st = compute(d.path, vocab, levels, d.cfg, current, assume,       # lines now `card:<id>`
                 str(d.brief.get("gloss_language") or "en"))
    write_state(st, vocab, levels)
    return 0
