"""Vocabulary.md: the vault's ground truth of which words are known.

One markdown table, maintained by `asl lang` and editable by hand (status, level). Rows are
matched back to lexemes by tokenizing the `word` column, so hand-added rows work too."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..core.reviews import read_export
from .levels import NONE

STATUSES = ["known", "learning", "planned", "unknown", "ignored"]
RANK = {"ignored": 4, "known": 3, "learning": 2, "planned": 1, "unknown": 0}
COUNTS_AS_KNOWN = {"known", "learning", "planned", "ignored"}

HEADER = """---
type: vocabulary
language: {lang}
---
# Vocabulary

Maintained by `asl lang` (seed, plan, sync). Edit `status` by hand when you like:
`known`, `learning`, `planned` (a card exists), `unknown`, `ignored` (never a card target).
`level`: on a level list (`N4`), estimated from frequency (`~N3`), or neither (`—`);
recomputed on every plan unless set by hand with `!` (`N3!`).
`meaning`: the card's gloss when a card exists, else the dictionary's first sense (kept once set,
so a hand-written meaning stays).

| word | reading | level | meaning | status | card | source |
|---|---|---|---|---|---|---|
"""


@dataclass
class Entry:
    word: str
    reading: str
    level: str = ""
    status: str = "unknown"
    card: str = ""
    source: str = ""
    meaning: str = ""

    def raise_to(self, status: str, source: str = "") -> None:
        """Statuses only go up (a hand-set `ignored` or `known` is never lowered)."""
        if RANK[status] > RANK[self.status]:
            self.status = status
            if source:
                self.source = source
        elif not self.source and source:
            self.source = source


class Vocabulary:
    def __init__(self, path: Path, lang: str, tok):
        self.path, self.lang, self.tok = path, lang, tok
        self.entries: dict[str, Entry] = {}
        if path.is_file():
            self._read()

    def _read(self) -> None:
        cols = ["word", "reading", "level", "status", "card", "source"]     # files before `meaning`
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and cells[0] == "word":                 # the header names the columns
                cols = cells
                continue
            if len(cells) < 4 or not cells[0] or set(cells[0]) <= {"-"}:
                continue
            row = dict(zip(cols, cells))
            key = self.tok.key_for(row.get("word", ""))
            if not key:
                continue
            status = row.get("status") if row.get("status") in STATUSES else "unknown"
            e = self.entries.get(key)
            if e is None:
                self.entries[key] = Entry(row["word"], row.get("reading", ""), row.get("level", ""),
                                          status, row.get("card", ""), row.get("source", ""),
                                          row.get("meaning", ""))
            else:
                e.raise_to(status)

    def get(self, key: str, word: str, reading: str) -> Entry:
        if key not in self.entries:
            self.entries[key] = Entry(word, reading)
        return self.entries[key]

    def status(self, key: str) -> str:
        e = self.entries.get(key)
        return e.status if e else "unknown"

    def write(self, level_order: list[str], rank_of=None) -> None:
        def sort_key(item):
            key, e = item
            base = e.level.lstrip("~").rstrip("!")
            li = level_order.index(base) if base in level_order else len(level_order)
            return (li, e.level.startswith("~"), rank_of(key) if rank_of else 0, e.reading)
        rows = [f"| {_cell(e.word)} | {_cell(e.reading)} | {e.level} | {_cell(e.meaning)} | {e.status} "
                f"| {e.card} | {_cell(e.source)} |"
                for _, e in sorted(self.entries.items(), key=sort_key)]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(HEADER.format(lang=self.lang) + "\n".join(rows) + "\n", encoding="utf-8")


def _cell(s: str) -> str:
    return (s or "").replace("|", "/").replace("\n", " ")


# ---- seeding from the user's own Anki exports -------------------------------------------

_GLOSS = re.compile(r"([^\s=＝,、;；:：<>\]\[/()（）]+?)\s*(?:[(（][^)）]*[)）])?\s*[=＝]")


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>|&nbsp;|\[sound:[^\]]*\]", " ", s or "")


def glossed_words(meaning: str) -> list[str]:
    """Words the user glossed on a mined sentence card: `最高(さいこう)=Das Beste, どく=…`."""
    return [m.group(1) for m in _GLOSS.finditer(_strip_html(meaning))]


def seed(vocab: Vocabulary, exports: list[Path], text_fields=("Expression",),
         gloss_fields=("Meaning",)) -> dict[str, int]:
    """Sentence-mining notes the user has studied: every word in the sentence was known when the
    card was made, except the glossed ones (known once the card is mature, else learning).
    Single-word vocab notes count by their own card state. New, reset or suspended notes: skipped."""
    tok = vocab.tok
    counts = {"notes": 0, "known": 0, "learning": 0}
    for path in exports:
        ex = read_export(path)
        src = f"seed: {Path(path).name}"
        for note in ex.notes:
            text = next((note.fields[f] for f in text_fields if f in note.fields), None)
            if text is None or not note.reviewed or note.suspended:
                continue
            words = [t for t in tok(_strip_html(text)) if t.kind == "word"]
            if not words:
                continue
            counts["notes"] += 1
            if len(words) == 1:            # a vocab card (or a one-word line): its own state
                status = "known" if note.mature else "learning"
                vocab.get(words[0].key, words[0].word, words[0].reading).raise_to(status, src)
                counts[status] += 1
                continue
            gloss = next((note.fields[f] for f in gloss_fields if f in note.fields), "")
            new = {k for g in glossed_words(gloss) if (k := tok.key_for(g))}
            for t in words:
                status = ("known" if note.mature else "learning") if t.key in new else "known"
                e = vocab.get(t.key, t.word, t.reading)
                before = e.status
                e.raise_to(status, src)
                if e.status != before:
                    counts[e.status] += 1
    return counts


# ---- meanings (quick lookup) and words that are never targets ----------------------------

def fill_meanings(vocab: Vocabulary, glosses: dict[str, str], cfg: dict, gloss_lang: str) -> None:
    """`meaning` for quick lookup: a card's gloss wins; else keep what is there (hand-written);
    else the dictionary's first sense in the gloss language (English as fallback)."""
    for k, g in glosses.items():
        if k in vocab.entries:
            vocab.entries[k].meaning = g
    if all(e.meaning for k, e in vocab.entries.items() if k not in glosses) or not cfg.get("dictionary"):
        return
    from .dictionary import ISO2, Dictionary
    try:
        dic = Dictionary(cfg)
    except SystemExit:
        return
    codes = list(dict.fromkeys([ISO2.get(gloss_lang, gloss_lang), "eng"]))
    for k, e in vocab.entries.items():
        if e.meaning or k in glosses:
            continue
        lemma = k.split("|")[0]                      # dictionary form: なん -> 何
        hits = dic.lookup(lemma, e.reading) or dic.lookup(e.word, e.reading)
        for code in codes:
            sense = next((sn for h in hits[:1] for sn in h["s"] if sn["gloss"].get(code)), None)
            if sense:
                e.meaning = "; ".join(sense["gloss"][code][:3])
                break


def interjections(forms: dict, level_of: dict, levels, cfg: dict) -> set[str]:
    if not cfg.get("dictionary"):
        return set()
    from .dictionary import Dictionary
    try:
        dic = Dictionary(cfg)
    except SystemExit:
        return set()
    out = set()
    for k, fc in forms.items():
        if level_of.get(k, NONE).lstrip("~") in levels.order and not level_of[k].startswith("~"):
            continue                                   # on a list (なるほど N4): a word to learn
        entries = [e for (w, _) in fc for e in dic.lookup(w)[:1]]
        if entries and all(sn["pos"] and all("interjection" in p for p in sn["pos"])
                           for e in entries for sn in e["s"] if sn["gloss"].get("eng")):
            out.add(k)
    return out
