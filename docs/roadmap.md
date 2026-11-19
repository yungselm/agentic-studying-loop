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

### 3. Language cards (designed: [language-cards.md](language-cards.md))
Grammar first from native sentences (Game Gengo structure), then i+1 vocabulary cards (audio +
screenshot front, one target word glossed). Known words and grammar points live in the vault
and order the cards; a language is a topic (grammar book PDF/URL + media sources). Built on the
author's Japanese decks: 1 unknown word fails 20% vs 23% for 2+ (Shirokuma, 3.4k reviews).
Opt-in: `[lang-ja]` extra (shared `[lang]` + Japanese) + separate skill.
- [x] Import + plan report on Terrace House OND 1 (no cards yet): `asl lang setup/add/seed/plan`.
- [x] `sentence` and `grammar` card types; first ~50 Terrace House cards.
- [x] Grammar ground truth from Game Gengo (+ JLPT checklist, images, N3 port); grammar gate.
- [x] `asl lang sync` from reviews (fail rate per source; more stats once reviewed).
- [x] Video + subtitles input (and re-cutting mined decks from their video); TTS fallback
  (VOICEVOX / edge-tts); `asl lang clean` for unused media.
- [ ] Whisper: check clips against their subtitle (cut short, extra talkers), word-exact
  speaker splits, subtitles for media without them.
- [x] German (`language_de`, `[lang-de]`, requested by the author's coworkers): spaCy tokens
  with separable verbs as one word, CEFR levels estimated from word frequency, edge-tts voice; no
  bundled dictionary yet (Wiktionary via kaikki.org would add glosses and noun gender).
- [ ] Italian as the third language: a `language_it` module like `language_ja` (tokenizer, CEFR
  word levels, dictionary, `it.yaml`) and an episode with Italian subtitles; the grammar book (*Praxis-Grammatik
  Italienisch*) later, once found. Postponed by the author.
- [ ] Card preferences and quality checks the user decides (which source or card kind wins a
  word, minimum audio/image quality, Whisper check), designed together after the pipeline.
- [ ] The author's real start: a fresh topic from all their sources (Terrace House, Shirokuma,
  Game Gengo, ...) with everything new (no seed), so the vault's ground truth starts clean.

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
- [x] `asl prompt`: one self-contained prompt per batch (brief, card counts from length and
  figures, the card home's rules, format, text, figures), then `asl finish` (fix, lint, check,
  build). `study-source` runs on it for cards straight from a PDF or Markdown source.
- [x] PDF figures: `--read` and `asl prompt` save a part's raster images to `<deck>/figures/` with
  their captions; cards embed them.
- [ ] Vector drawings (most diagrams in some books) have no image file: render the page region
  (needs a PDF renderer, e.g. pypdfium2).
- [ ] `asl prompt` for links (fetch the part) and for the notes-first path; project decks
  (`write-cards`) the same way.

### 4. Token cost, measured
The tools are built so the agent reads only what it needs (budgets, `--read` one part, skills
loaded on demand). Check that this holds, then put numbers on it.
- [x] Audit what the agent reads, for topics (from the benchmark transcripts): the skills
  workflow spent 10–30 turns reading the standards, the sources map, `--help` and asl's own
  code; most of the cost was turns, not output. Fixed by `asl prompt` (3–9 turns).
- [ ] The same audit for setup (the paste prompt sends the agent to the GitHub page, so it
  fetches the whole README to use the "For agents" section), projects and languages.
- [ ] Setup steps as their own small file (`AGENTS.md` or `docs/agents/setup.md`), the paste
  prompt pointing at its raw URL; the README links to it instead of holding it.
- [ ] `llms.txt` on the docs site (generated by the docs build, see 5): the index an agent reads
  first when it fetches the docs from the web. Not needed inside a repo, where skills and
  `CLAUDE.md` do that job.
- [x] Benchmark (2026-11-18, [results](benchmarks.md)): 4 book chapters (Rust ch. 4 and 10,
  coronary imaging OCT and FFR) × 5 setups (Haiku and Sonnet medium, Opus low/medium/high) ×
  3 arms (plain prompt, skills workflow, `asl prompt`), one run each, headless on the author's
  plan with a clean config. 200 cards rated blind by the author (`benchmarks/rate.py`), 20
  re-rated to measure drift (0.2–0.3). Card quality: the same in all three arms; Opus a little
  above Sonnet and Haiku; effort no difference. The skills workflow cost a third more through
  exploring turns, so topics now run on `asl prompt`. Only numbers are committed
  (`benchmarks/results/<batch>/`); `benchmarks/report.py` writes the charts, the README section
  and the docs page.
- [ ] Re-test the figure rules from the ratings (findings get their image, no figure that
  doesn't show the asked thing, one card per figure): prompt arm on the OCT chapter.
- [ ] Language task (Shirokuma ep. 3): runner setup for `asl lang`, then its 5 cards per cell.
- [ ] More than one run per cell, and the cards' real review fail rates from `asl stats` once
  they've been studied: the measure that counts.

### 5. Documentation on Read the Docs
A hosted site where the author explains the thinking in detail (why the standards are what they
are, the evidence, the loop); the README stays the short entry point.
- [x] First test site, hosted: Sphinx + MyST, Furo theme, `.readthedocs.yaml`, built in CI so
  broken links fail (`make html` in `docs/` locally). Two sections to start:
  - **Install**: uv, the extras, the card home, first deck (from the README's Install part).
  - **API**: one page per module from its entry-point `__init__` docstring (autodoc), then the
    registry (how to write a module), for collaborators.
- [ ] Then the rest of `docs/*.md` (card format, packs, evidence, architecture) and the author's
  write-ups on the thinking behind the standards and the loop.
- [ ] `llms.txt` generated from the site (e.g. `sphinx-llms-txt`).

## Later
- **Merge the standards (~Dec 2026)**: after a month of reviews on the omakase cards (and later other
  projects), fold the author's personal standards back into the generic `core.md`, based on that data.
  Then the card home keeps only `preferences.md` and per-deck profiles, and `core.md` becomes a
  managed copy (`asl standards --update`).
- Publish on PyPI, so the install becomes `uv tool install agentic-studying-loop`.
- More packs: TypeScript (tsc + vitest), Go. Each needs a checker and a standards addendum.
- `asl stats --share`: an anonymised summary (bins and counts only) to pool evidence across learners.
- A drag-to-order front for timeline cards (today: labelled A–E, answer is the order).
