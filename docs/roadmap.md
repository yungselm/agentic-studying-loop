# Roadmap

## Now (in order, one at a time)

### 1. Study notes worth reopening (done)
One idea per note; TL;DR + Mermaid diagram on the first screen; details folded; typed links
and an overview map (`study-note` skill). `asl notes` checks them (in CI for the example vault).
Length is a default (~250 words, lectures ~800), raised per note with `budget:`.
- [ ] Upgrade a few real vault notes, tune the rules from that (`preferences.md` → *Notes*).

### 2. Notes → cards, for any subject (cloze type done)
A notes vault (lectures, study notes) becomes Anki cards. The new `cloze` type is built on the
author's medical exam deck (10.6k cards studied, 53k reviews; [evidence](evidence-cloze-cards.md)):
short gaps, 2–5 gaps per note, gap the name too (findings → name was harder and never carded).
Images, shared scenes and mnemonics showed no effect, so `hook:` stays optional and measured.
Language showed no effect either: no per-language rules. A Python course deck (767 cards;
[evidence](evidence-python-course.md)) replicates the code-card limits and favours contrast
questions. Image occlusion is left out: quick to make by hand, hard to generate.
- [x] `type: cloze`: gaps, hints, `$math$`, `[[Note#Section]]` source, `![[image]]` embeds; lint
  for gap size, single gaps, missing notes/images; `asl stats` measures gaps and hooks.
- [x] Concept cards take `$math$`, `![[image]]` and a `[[Note]]` source too.
- [ ] CS231n pilot: lectures 02–04 as 60 notes (cloze + concept) in the card home; review them,
  then card the other lectures and tune on the reviews.
- [ ] *Maybe, needs testing:* a study budget. The user sets minutes per day and new cards per
  day (`studyloop.yaml`); from that and the measured cost per card (median seconds per answer:
  cloze ~6–8 s, flip ~10 s, typed code ~27 s; answers per card from `asl stats`), suggest how
  many cards a topic or lecture should get, and which to drop first when it's over budget.
- [x] Lecture input: slide PDFs → study note → cards, `source: "[[lecture.pdf#page=12]]"` (2b).
  `.pptx` is flagged (export to PDF), not read.
- [ ] `asl stats` reads foreign note types (AnKing's cloze, basic), so any existing deck can
  seed the standards; then reuse before writing: match a note against unstudied cards
  (e.g. 34k AnKing notes) and propose "unsuspend these, write those".

### 3. Language cards
Collect the author's inputs and favourite sets first, then design. Starting ideas: a sentence
card (cloze/translation, audio, screenshot); a subtitle miner (`.srt` → i+1 sentences); stats
on sentence length, word frequency, unknown words. AnKing's term → definition cards (9.8% fail)
show where plain vocab cards struggle.

### 2b. Topics from books and links (done)
A brief in the deck's `Overview.md` (goal, `builds_on`, `notes:` flag, sources) and a sources map
written by `asl sources`: PDF bookmarks → parts with pages, words, tokens and status from the
`source:` links of notes and cards; chapters over the batch size listed by section. The agent reads
one part per batch (`--read`), never the whole book (`study-source` skill). `asl topic` starts a
topic without a code repo (a folder of lecture PDFs counts as one source per file; PDFs without
bookmarks split into page chunks) and lists the topics in a `CLAUDE.md` next to the card home.
- [x] `cpp` pack: one translation unit, a namespace per card, `-Werror` + ASan/UBSan, each card's
  asserts in their own process, clang-tidy Core Guidelines checks when installed.
- [x] Markdown sources split by headings (the Core Guidelines: sections, rule ids → status).
- [ ] C++ topic (author): Tour + Effective Modern C++ + Core Guidelines + Modern CMake, focused on
  regulated medical software; every chapter → cards, kata style. Then the regulatory topic.
- [ ] Parts for long web pages without hand-written `parts:` (fetch the headings once).

## Later
- **Documentation on Read the Docs**: move the docs (card format, packs, standards, the agent
  workflow) from `docs/` into a hosted site, with the README as the short entry point.
- **Merge the standards (~Dec 2026)**: after a month of reviews on the omakase cards (and later other
  projects), fold the author's personal standards back into the generic `core.md`, based on that data.
  Then the card home keeps only `preferences.md` and per-deck profiles, and `core.md` becomes a
  managed copy (`asl standards --update`).
- Publish on PyPI, so the install becomes `uv tool install agentic-studying-loop`.
- More packs: TypeScript (tsc + vitest), Go. Each needs a checker and a standards addendum.
- `asl stats --share`: an anonymised summary (bins and counts only) to pool evidence across learners.
- A drag-to-order front for timeline cards (today: labelled A–E, answer is the order).
