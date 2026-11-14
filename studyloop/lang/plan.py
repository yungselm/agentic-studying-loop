"""`asl lang plan`: which lines become one-new-word cards, in which order, and why the rest wait.

Writes the `status` column of every lines/*.tsv, fills `level` in Vocabulary.md, prints a report.
No cards are written here."""
from __future__ import annotations

import heapq
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

from .levels import NONE, Levels
from .lines import Line, read_lines, write_lines
from .vocab import COUNTS_AS_KNOWN, Vocabulary

MEDIA_PULL = 3          # a word in >= 3 lines of the user's media counts as current level
_PUNCT = re.compile(r"[\s、。！？!?…‥・「」『』“”\"'（）()~〜ー―-]+")


@dataclass
class Analysed:
    line: Line
    source: str
    words: list[str]                  # lexeme keys (kind == word), unique, in order
    kinds: Counter = field(default_factory=Counter)
    chars: int = 0
    quality: int = 1                  # the source's rank: better audio/images win a word's line


@dataclass
class Plan:
    order: list[tuple[str, int]] = field(default_factory=list)   # (lexeme key, line index)
    status: dict[int, str] = field(default_factory=dict)
    remaining: list[set] = field(default_factory=list)    # per line: unknown words left
    first_round: int = 0


def analyse(lines_by_source: dict[str, list[Line]], tok) -> tuple[list[Analysed], dict]:
    out, forms = [], defaultdict(Counter)       # key -> Counter[(word, reading)]
    for src, lines in lines_by_source.items():
        names = sorted({n for ln in lines for n in _names(ln.speaker)}, key=len, reverse=True)
        for ln in lines:
            toks = _mark_names(tok(ln.text), ln.text, names)
            keys = []
            for t in toks:
                if t.kind == "word":
                    forms[t.key][(t.word, t.reading)] += 1
                    if t.key not in keys:
                        keys.append(t.key)
            out.append(Analysed(ln, src, keys, Counter(t.kind for t in toks),
                                len(_PUNCT.sub("", ln.text))))
    return out, forms


def _names(speaker: str) -> list[str]:
    """Speaker labels name the cast: '徳井' or 'YOU' (2+ characters, to stay clear of words)."""
    return [n for n in re.split(r"[\s・/、,]+", speaker or "") if len(n) >= 2]


def _mark_names(toks: list, text: str, names: list[str]) -> list:
    """Tokens inside a cast name in the text become kind 'name' (UniDic splits 安未 into words)."""
    if not names:
        return toks
    spans = [(m.start(), m.end()) for n in names for m in re.finditer(re.escape(n), text)]
    if not spans:
        return toks
    out, pos = [], 0
    for t in toks:
        start = text.find(t.surface, pos)
        if start < 0:
            out.append(t)
            continue
        end = pos = start + len(t.surface)
        if t.kind == "word" and any(s < end and start < e for s, e in spans):
            t = replace(t, kind="name")
        out.append(t)
    return out


def make_plan(items: list[Analysed], known, priority, excluded: frozenset = frozenset()) -> Plan:
    """Greedy i+1: repeatedly take the highest-priority word that has a line where it is the only
    unknown word; plan it on its best line (within the length cap, shortest); recompute.

    A single-word line (one content word: 'ヤバい', '私ですか？') is a card only when no longer
    line in the sources has that word; otherwise the word waits for a longer line."""
    plan = Plan()
    remaining = [set(k for k in it.words if not known(k)) for it in items]
    initially_zero = {i for i, r in enumerate(remaining) if not r}
    lines_of = defaultdict(list)
    for i, r in enumerate(remaining):
        for k in r:
            lines_of[k].append(i)
    has_longer = {k for it in items if len(it.words) > 1 for k in it.words}

    def eligible(i: int) -> bool:
        if i in excluded:                       # rejected: its card was deleted
            return False
        return len(items[i].words) > 1 or next(iter(remaining[i])) not in has_longer

    heap, pushed = [], set()

    def offer(i: int) -> None:
        if not eligible(i):
            return
        (k,) = remaining[i]
        if k not in pushed:
            pushed.add(k)
            heapq.heappush(heap, (priority(k), k))

    for i, r in enumerate(remaining):
        if len(r) == 1:
            offer(i)
    plan.first_round = len(pushed)
    planned = set()
    while heap:
        _, k = heapq.heappop(heap)
        if k in planned:
            continue
        cands = [i for i in lines_of[k] if remaining[i] == {k} and eligible(i)]
        if not cands:
            continue
        best = min(cands, key=lambda i: (items[i].chars > priority.cap, -items[i].quality,
                                         items[i].line.id[-1].isalpha(), items[i].chars))
        planned.add(k)
        plan.order.append((k, best))
        for i in lines_of[k]:
            remaining[i].discard(k)
            if len(remaining[i]) == 1:
                offer(i)
    chosen = {i: n for n, (_, i) in enumerate(plan.order, 1)}
    for i, it in enumerate(items):
        if i in excluded:
            plan.status[i] = "rejected"
        elif i in chosen:
            plan.status[i] = f"ready:{chosen[i]}"
        elif i in initially_zero:
            plan.status[i] = "known"
        elif not remaining[i]:
            plan.status[i] = "covered"
        elif len(remaining[i]) == 1 and not eligible(i):
            plan.status[i] = "skipped:single word"       # its word waits for a longer line
        else:
            plan.status[i] = f"parked:{len(remaining[i])} words"
    plan.remaining = remaining
    return plan


class Priority:
    def __init__(self, levels: Levels, level_of: dict[str, str], media_count: Counter,
                 current: str | None, cap: int):
        self.levels, self.level_of, self.media, self.current, self.cap = (
            levels, level_of, media_count, current, cap)

    def effective_level(self, k: str) -> str:
        lvl = self.level_of.get(k, NONE)
        if lvl == NONE and self.media[k] >= MEDIA_PULL and self.current:
            return self.current
        return lvl

    def __call__(self, k: str) -> tuple:
        return (self.levels.sort_index(self.effective_level(k), self.current), -self.media[k], k)


@dataclass
class State:
    files: list[Path]
    by_src: dict[str, list[Line]]
    items: list[Analysed]
    plan: Plan
    prio: Priority
    known: object
    assumed: set
    media: Counter
    cards: dict[str, str]               # line id -> card id (sentence cards in the deck)


def source_quality(meta: Path) -> int:
    """`quality:` in lines/<key>.yaml; default 2 when cut from the original video (padded clips,
    sharp screenshots), else 1 (clips as the mined deck cut them)."""
    import yaml
    m = (yaml.safe_load(meta.read_text(encoding="utf-8")) or {}) if meta.is_file() else {}
    return int(m.get("quality") or (2 if m.get("video") else 1))


def existing_cards(deck_dir: Path) -> list[dict]:
    from ..cards import load_file
    from ..config import load_deck
    deck = load_deck(deck_dir)
    return [c for f in deck.files() for c in load_file(f) if c.get("type") == "sentence"]


def compute(deck_dir: Path, vocab: Vocabulary, levels: Levels, cfg: dict, current: str | None,
            assume: list[str], gloss_lang: str = "en") -> State:
    tok = vocab.tok
    files = sorted((deck_dir / "lines").glob("*.tsv"))
    if not files:
        raise SystemExit(f"{deck_dir}: no lines/*.tsv yet; run `asl lang add` first")
    by_src = {f.stem: read_lines(f) for f in files}
    items, forms = analyse(by_src, tok)
    quality = {f.stem: source_quality(f.with_suffix(".yaml")) for f in files}
    for it in items:
        it.quality = quality[it.source]

    level_of, media = {}, Counter()
    for it in items:
        media.update(it.words)
    for k, fc in forms.items():
        (word, reading), _ = fc.most_common(1)[0]
        e = vocab.get(k, word, reading)
        if not e.level.endswith("!"):          # `N3!`: set by hand, kept
            e.level = levels.level([w for (w, _) in fc] + [k.split("|")[0]], reading)
        level_of[k] = e.level.rstrip("!")
    for k, e in vocab.entries.items():          # seeded words not in these sources
        if k not in forms and not e.level.endswith("!"):
            e.level = levels.level([e.word, k.split("|")[0]], e.reading)

    # interjections the tokenizer tagged as words (うわっ before a word is an adverb to UniDic):
    # on no level list and only ever an interjection in the dictionary -> never a target
    fillers = _interjections(forms, level_of, levels, cfg)
    if fillers:
        for it in items:
            it.words = [k for k in it.words if k not in fillers]
        media = Counter(k for it in items for k in it.words)

    # cards decide `planned`: a word with a card is planned; a planned word whose card is gone
    # is unknown again, and its line is rejected (never proposed again)
    cards, carded_words, glosses = {}, {}, {}
    words_of_line = {it.line.id: it.words for it in items}
    for c in existing_cards(deck_dir):
        cid = str(c.get("id") or "")
        if str(c.get("gloss") or "").strip() and (gk := tok.key_for(str(c.get("word") or ""))):
            glosses[gk] = str(c["gloss"]).strip()
        for k in [k for k in words_of_line.get(str(c.get("line") or ""), [])
                  if vocab.status(k) in ("unknown", "planned")][:1]:
            if str(c.get("gloss") or "").strip():
                glosses.setdefault(k, str(c["gloss"]).strip())
        if c.get("line"):
            cards[str(c["line"])] = cid or "?"
        # the card's line: its one new word is the target, however `word:` was edited
        # (はじめまして, 様になる); known words stay known (statuses only go up)
        for k in words_of_line.get(str(c.get("line") or ""), []):
            if vocab.status(k) in ("unknown", "planned"):
                carded_words.setdefault(k, cid)
        if k := tok.key_for(str(c.get("word") or "")):
            carded_words.setdefault(k, cid)
    for k, e in vocab.entries.items():
        if k in carded_words:
            e.raise_to("planned")
            e.card = carded_words[k]
        elif e.status == "planned":
            e.status, e.card = "unknown", ""
    _fill_meanings(vocab, glosses, cfg, gloss_lang)
    old_ids = {i: it.line.status.split(":", 1)[1] for i, it in enumerate(items)
               if it.line.status.startswith(("card:", "rejected:"))}
    excluded = frozenset(i for i in old_ids if items[i].line.id not in cards)

    assumed = {k for k in forms if level_of[k] in assume}
    def known(k):
        return vocab.status(k) in COUNTS_AS_KNOWN or k in assumed

    prio = Priority(levels, level_of, media, current, int(cfg.get("length_cap") or 10**6))
    plan = make_plan(items, known, prio, excluded)
    for i, it in enumerate(items):
        if it.line.id in cards:
            plan.status[i] = f"card:{cards[it.line.id]}"
        elif i in excluded:
            plan.status[i] = f"rejected:{old_ids[i]}"       # the id stays used: never reissued
    return State(files, by_src, items, plan, prio, known, assumed, media, cards)


def _fill_meanings(vocab: Vocabulary, glosses: dict[str, str], cfg: dict, gloss_lang: str) -> None:
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


def _interjections(forms: dict, level_of: dict, levels: Levels, cfg: dict) -> set[str]:
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


def write_state(st: State, vocab: Vocabulary, levels: Levels) -> None:
    target = {i: k for k, i in st.plan.order}
    idx = 0
    for f in st.files:
        lines = st.by_src[f.stem]
        for ln in lines:
            s = st.plan.status[idx]
            if s.startswith("ready"):
                s = f"{s}:{vocab.entries[target[idx]].word}"
            elif s.startswith("parked"):
                s += ": " + " ".join(vocab.entries[k].word for k in st.items[idx].words
                                     if k in st.plan.remaining[idx])
            ln.status = s
            idx += 1
        write_lines(f, lines)
    vocab.write(levels.order, rank_of=lambda k: -st.media[k])


def run(deck_dir: Path, vocab: Vocabulary, levels: Levels, cfg: dict, current: str | None,
        assume: list[str], write: bool = True, gloss_lang: str = "en") -> int:
    st = compute(deck_dir, vocab, levels, cfg, current, assume, gloss_lang)
    if write:
        write_state(st, vocab, levels)
    _report(st.items, st.plan, vocab, levels, st.prio, st.known, st.assumed, st.by_src, current, cfg)
    return 0


def _pct(a: int, b: int) -> str:
    return f"{a} ({100 * a / b:.0f}%)" if b else str(a)


def _report(items, plan, vocab, levels, prio, known, assumed, by_src, current, cfg) -> None:
    n = len(items)
    counts = Counter(e.status for e in vocab.entries.values())
    print(f"Sources: {', '.join(f'{s} ({len(v)} rows)' for s, v in by_src.items())}")
    print(f"Vocabulary: {len(vocab.entries)} words · known {counts['known']}, learning "
          f"{counts['learning']}, ignored {counts['ignored']}"
          + (f" · assumed known (level {', '.join(sorted({vocab.entries[k].level for k in assumed}))}):"
             f" {len(assumed)}" if assumed else "")
          + f" · current level: {current or '?'}")

    before = Counter(min(len([k for k in it.words if not known(k)]), 4) for it in items)
    print("\nUnknown words per line (before planning):")
    print("  " + " · ".join(f"{'4+' if b == 4 else b}: {_pct(before[b], n)}" for b in range(5)))

    ready = [i for i, s in plan.status.items() if s.startswith("ready")]
    st = Counter(s.split(":")[0] for s in plan.status.values())
    parked = Counter(min(len(plan.remaining[i]), 4) for i, s in plan.status.items()
                     if s.startswith("parked"))
    print(f"\nPlan: {_pct(len(ready), n)} lines ready as one-new-word cards "
          f"({plan.first_round} words available at once, {len(ready) - plan.first_round} unlocked by "
          f"planning others)")
    print(f"  all words known already: {st['known']} · covered by planned words: {st['covered']}"
          + (f" · with a card: {st['card']}" if st['card'] else "")
          + (f" · rejected (card deleted): {st['rejected']}" if st['rejected'] else ""))
    print(f"  parked: {st['parked']} ("
          + ", ".join(f"{'4+' if b >= 4 else b} words: {c}" for b, c in sorted(parked.items())) + ")")
    skipped = [i for i, s in plan.status.items() if s.startswith("skipped")]
    waiting = {k for i in skipped for k in plan.remaining[i]}
    kept = sum(1 for i in ready if len(items[i].words) <= 1)
    print(f"  single-word lines: {len(skipped)} skipped (a longer line has the word; "
          f"{len(waiting)} words wait for it) · {kept} kept as cards (no longer line exists)")

    lv = Counter(prio.effective_level(k) for k, _ in plan.order)
    order = levels.order
    keys = [*order, *("~" + o for o in order), NONE]
    print("  levels of the planned words: "
          + " · ".join(f"{k} {lv[k]}" for k in keys if lv[k]))

    cap = prio.cap
    def quality(i):
        it = items[i]
        flags = []
        if len(it.words) <= 1:
            flags.append("single word")
        if it.chars < 4:
            flags.append("< 4 chars")
        if it.chars > cap:
            flags.append(f"> {cap} chars")
        if it.kinds["filler"] and len(it.words) <= 1:
            flags.append("filler")
        return flags
    q_all = Counter(f for i in range(n) for f in quality(i))
    q_ready = Counter(f for i in ready for f in quality(i))
    print("\nQuality (all lines → ready lines):")
    for f in ("single word", "filler", "< 4 chars", f"> {cap} chars"):
        print(f"  {f:12} {_pct(q_all[f], n):>12} → {_pct(q_ready[f], len(ready))}")
    good = [i for i in ready if not quality(i)]
    print(f"  ready and none of these: {_pct(len(good), len(ready))}")

    blockers = Counter()
    for i, s in plan.status.items():
        if s.startswith("parked"):
            blockers.update(plan.remaining[i])
    print("\nWords blocking the most parked lines (no line where they are the only new word):")
    print("  " + " · ".join(f"{vocab.entries[k].word} ({prio.effective_level(k)}, {c})"
                            for k, c in blockers.most_common(15)))

    print("\nFirst 25 cards in order:")
    for n_, (k, i) in enumerate(plan.order[:25], 1):
        e = vocab.entries[k]
        flags = quality(i)
        print(f"  {n_:3}. {e.word} 【{e.reading}】 {prio.effective_level(k):4} "
              f"×{prio.media[k]:<3} {items[i].line.id}  {items[i].line.text}"
              + (f"   [{', '.join(flags)}]" if flags else ""))
