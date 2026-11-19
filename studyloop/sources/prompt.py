"""One self-contained prompt for a topic's parts: the brief, how many cards of which kind, the
card home's rules, the exact card format, the text and its figures, and `asl finish` at the end.

    asl prompt "Anki cards/rust_book"                 # every part still todo
    asl prompt "Anki cards/rust_book" --part ch04.s1,ch04.s2

Any agent (or a chat) can work from it without skills and without reading anything else: write
one card file, run `asl finish`, fix what it reports.
"""
from __future__ import annotations

import re
from pathlib import Path

from studyloop.core.config import Deck, find_home
from studyloop.core.config.vault import split_frontmatter
from studyloop.core.engine.budget import DEFAULT_BATCH
from studyloop.sources import sourcemap as sm

PER_1K_WORDS = 4            # default cards per 1,000 words of source; the brief's `per_1k_words`
# which `## N. Title` sections of core.md a prompt needs, found by title (card homes keep their
# own numbering); a kind missing from the card home's core.md comes from asl's own
KINDS = (("code", r"code cards"), ("concept", r"concept cards"), ("cloze", r"cloze"),
         ("hard", r"hard|never-used"))


def _sections(text: str) -> dict[str, tuple[str, str]]:
    """kind -> (its title, its text) for the sections of a standards file a prompt needs."""
    out, cur, title, buf = {}, None, "", []

    def close():
        if cur and cur not in out:
            out[cur] = (title, "\n".join(buf).strip())
    for ln in text.splitlines() + ["## end"]:
        if ln.startswith("## "):
            close()
            title = re.sub(r"^## (\d+\.)?\s*", "", ln).strip()
            cur = next((k for k, rx in KINDS if re.search(rx, title, re.I)
                        and not re.search(r"project", title, re.I)), None)
            buf = []
        elif cur:
            buf.append(ln)
    return out


def _drop_bullet(text: str, lead: str) -> str:
    """Remove the bullet starting with `- <lead>` and its indented continuation lines."""
    out, skip = [], False
    for ln in text.splitlines():
        if not ln.startswith("  "):
            skip = ln.startswith(f"- {lead}")
        if not skip:
            out.append(ln)
    return "\n".join(out)


def preferences(text: str) -> str:
    """The user's own rules: bullets under `## Cards`, comments left out."""
    body = re.sub(r"<!--.*?-->", "", "\n".join(split_frontmatter(text)[1]), flags=re.S)
    m = re.search(r"^## Cards\s*$(.*?)(?=^## |\Z)", body, re.S | re.M)
    return "\n".join(ln for ln in (m[1] if m else "").splitlines() if ln.startswith("- ")).strip()


def rules(deck: Deck, code: bool) -> str:
    std = find_home(deck.path).path / "standards"
    core = std / "core.md"
    from studyloop.core.config import PKG
    secs = _sections((PKG / "standards" / "core.md").read_text(encoding="utf-8"))
    if core.is_file():
        secs.update(_sections(core.read_text(encoding="utf-8")))     # the card home's own win
    parts = []
    for kind, _rx in KINDS:
        if kind not in secs or (kind == "code" and not code):
            continue
        title, body = secs[kind]
        if kind == "code":
            body = _drop_bullet(body, "**Project cards")
        parts.append(f"### {title}\n{body}")
    if code and deck.pack and (std / f"{deck.pack}.md").is_file():
        pack = (std / f"{deck.pack}.md").read_text(encoding="utf-8").split("\n", 1)[1].strip()
        parts.append(f"### {deck.pack} code\n{pack}")
    prefs = std / "preferences.md"
    mine = preferences(prefs.read_text(encoding="utf-8")) if prefs.is_file() else ""
    if mine:
        parts.append("### My own rules (these win)\n" + mine)
    text = "\n\n".join(parts)
    # cut what only makes sense inside the full standards (lint markers, section pointers,
    # project-deck rules, the default code share: the brief sets it here)
    text = re.sub(r" ?\*\(lint[^)]*\)\*", "", text)
    text = re.sub(r" \(failed least, §\d\)", "", text)
    text = re.sub(r" \(§\d\)", "", text)
    text = re.sub(r"About half of all cards\s+are code cards: if", "If", text)
    for lead in ("Ask the transferable concept", "`source:"):
        text = _drop_bullet(text, lead)
    return text



def card_format(code: bool, lang: str, link: str) -> str:
    fence = lang or "text"
    code_part = f"""
- instruction: |       # the behaviour, and every literal the solution produces
    ...
  starter: |           # the editor's content before typing: the context frame, one gap
    ...                # mark the gap with a comment line (`// your code here`)
  solution: |          # the starter's lines unchanged, the gap filled
    ...
  notes: |             # back side: the why
    ...
  tests: |             # 2–3 asserts, run against the solution
    ...
  source: "{link}"
""" if code else ""
    typed = ("\nWhat a code card makes you type: the solution's lines that are not in the starter "
             "(compared line by line, ignoring indentation). Keep every other line identical, "
             "or it counts as typed. Write code in ```" + fence + " style, formatted like the "
             "language's formatter.\n") if code else ""
    return f"""```yaml{code_part}
- type: concept
  question: |          # one question; code it asks about goes here, indented 4 spaces
    ...
  answer: |
    **Bold lead: what you grade yourself against.** At most two short sentences more.
  source: "{link}"

- type: cloze
  text: |              # 2–5 gaps about one idea; {{{{answer}}}} or {{{{answer::hint}}}}
    {{{{Name}}}}: fact with a {{{{gap}}}} and {{{{another}}}}.
  source: "{link}"

- type: timeline       # a real process: steps in the right order (the build shuffles)
  question: "Order the steps of ...:"
  steps: [first, second, third]
  detail: "one line"
  source: "{link}"
```
Leave out `id` and `std`: `asl finish` adds them. `**bold**`, `` `code` `` and `$math$` work in
every text field; `![[figures/<file>]]` shows a figure.{typed}"""


def _rel(p: Path) -> str:
    """The deck folder as the agent should write it: relative to the current folder if inside."""
    try:
        return str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(p)


def build_prompt(deck: Deck, part_ids: list[str] | None = None) -> str:
    meta = sm.brief(deck)
    srcs, cache = sm.resolve(deck, meta), sm._load_cache(deck)
    for s in srcs:
        if s.path is not None and not s.problem:
            words = sm.scan_md(s) if s.unit == "lines" else sm.scan(s, cache)
            sm.attach_words(s, words, int(meta.get("batch") or DEFAULT_BATCH))
    sm.count(deck, meta, srcs)
    if part_ids:
        hits = [sm.find_part(srcs, p) for p in part_ids]
        missing = [p for p, h in zip(part_ids, hits) if h is None]
        if missing:
            raise SystemExit(f"no part {', '.join(missing)} in {deck.path.name}; "
                             "`asl sources` lists them")
        chosen = hits
    else:
        chosen = [(s, p) for s in srcs if not s.url for p in s.parts if sm._status(p) == "todo"]
        if not chosen:
            raise SystemExit(f"{deck.path.name}: no part left to do (`asl sources` shows the map)")

    words = sum(p.words or 0 for _, p in chosen)
    figs = [ln for s, p in chosen if s.unit == "pages" for ln in sm.figures(deck, s, p.first, p.last)]
    n_figs = sum(ln.count("![[") for ln in figs)
    per_1k = float(meta.get("per_1k_words") or PER_1K_WORDS)
    n = max(5, round(words / 1000 * per_1k + n_figs))          # every example figure: a card
    share = float((meta.get("cards") or {}).get("code", 0) or 0)
    n_code = round(n * share)
    code = n_code > 0
    goal, known = meta.get("goal") or "", meta.get("builds_on") or []
    known = ", ".join(known) if isinstance(known, list) else str(known)
    lists = [f"{k}: {', '.join(map(str, v))}" for k in ("focus", "skip")
             if (v := meta.get(k))]

    s0, p0 = chosen[0]
    pdf = s0.unit == "pages"
    link = (f"[[{s0.path.name}#page=N]]" if pdf else f"[[{s0.path.stem}#Heading]]")
    where = _rel(deck.path)
    file = f"{where}/{re.sub(r'[^a-z0-9]+', '_', p0.id.lower()).strip('_')}.yaml"
    titles = "; ".join(p.title for _, p in chosen)

    mix = (f"about {n_code} code cards (`asl check` compiles and tests them), the rest "
           "cloze and concept" if code else "cloze and concept cards")
    out = [f"# Anki cards: {s0.label}, {titles}", "",
           "Make Anki cards for the text below, all in this session. Everything you need is in "
           "this prompt: don't read other files or asl's code.", "",
           "## Brief", "",
           *([f"- Goal: {goal}"] if goal else []),
           *([f"- I already know: {known}. Don't card what that covers; where it helps, "
              "contrast with it and say where the analogy breaks."] if known else []),
           *[f"- {x}" for x in lists],
           f"- Write the cards in {meta.get('language') or 'English'}.",
           f"- About {n} cards (±25%) for these {words:,} words"
           + (f" and {n_figs} figure{'s' * (n_figs != 1)}" if n_figs else "") + f": {mix}. Facts, names and "
           "numbers → cloze; why, when, X vs Y → concept; a process → timeline. Fewer good "
           "cards beat many: card what serves the goal, skip the rest.",
           "", "## Rules", "", rules(deck, code), "",
           "## Format", "",
           f"Write all cards into `{file}` (a YAML list). Every card's `source:` points to "
           + ("the page it comes from: `" + link + "` (N = the page number in the text below)."
              if pdf else "its section: `" + link + "`."), "",
           card_format(code, deck.pack or "", link), ""]

    for s, p in chosen:
        out += [f"## Text: {p.title}", "", "<text>", sm.text_of(s.path, p.first, p.last).strip(),
                "</text>", ""]
    if figs:
        out += ["## Figures", "",
                f"Saved in `{where}/{sm.FIGURES}/`. Open each one the text discusses (it is an "
                "image file) before you card it; a card about what a figure shows embeds it, as "
                "written here:", "", *figs, ""]
    out += ["## Finish", "",
            f"Run `asl finish \"{where}\"`: it adds ids, checks every card against the rules "
            "above, compiles and tests code cards, and builds the deck. If it reports problems, "
            "fix those cards and run it again until it passes. Then tell me in two lines what you "
            "made."]
    return "\n".join(out) + "\n"


def prompt(groups, part: str | None, out: Path | None = None) -> int:
    for deck, _ in groups:
        text = build_prompt(deck, [x.strip() for x in part.split(",") if x.strip()] if part else None)
        if out:
            out.write_text(text, encoding="utf-8")
            print(f"{deck.path.name}: prompt written to {out} (~{len(text) // 4:,} tokens)")
        else:
            print(text, end="")
    return 0
