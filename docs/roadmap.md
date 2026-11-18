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
- [ ] Italian as the second language: a `language_it` module like `language_ja` (tokenizer, CEFR
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

### 4. Token cost, measured
The tools are built so the agent reads only what it needs (budgets, `--read` one part, skills
loaded on demand). Check that this holds, then put numbers on it.
- [ ] Audit what the agent actually reads, per step: setup (today the paste prompt sends it to
  the GitHub page, so it fetches the whole README, ~3.2k words, to use the "For agents" section),
  a skill run (SKILL.md + standards + card files), the `CLAUDE.md` block. Fix the big ones.
- [ ] Setup steps as their own small file (`AGENTS.md` or `docs/agents/setup.md`), the paste
  prompt pointing at its raw URL; the README links to it instead of holding it.
- [ ] `llms.txt` on the docs site (generated by the docs build, see 5): the index an agent reads
  first when it fetches the docs from the web. Not needed inside a repo, where skills and
  `CLAUDE.md` do that job.
- [ ] Benchmark: the same tasks with the workflow (skills + `asl`) and without (a plain "write
  Anki cards for this" prompt). Shows how strong the model must be once the setup does its part.
  - Cells (arm × model × effort, 10 in all): Haiku 5.5, Sonnet 5.5, Opus 5.5 at medium effort,
    plus Opus at low and high, each with and without the workflow.
  - Tasks: one source per card kind, each one the author knows well enough to judge a card on
    sight (rater expertise matters more than topic breadth): code from *The Rust Programming
    Language* (public web book, so anyone can rerun it), topic cards from a coronary imaging and
    physiology textbook (PDF, stays local), language from a subtitled Japanese episode. Two parts
    of each source, so no single chapter sets the result. Each task is a frozen fixture (copied
    sources, pinned commits); the task list with local paths is gitignored, the results name only
    task id and kind.
  - Runs: every cell × task, 2+ runs each, in shuffled order (a warm prompt cache would favour
    whatever runs next). A pilot task first, to price a run before the full grid.
  - Token tracking: `claude -p --model … --effort … --output-format stream-json --verbose` in a
    fresh copy of the fixture, on the author's subscription (`claude setup-token`). A clean
    `CLAUDE_CONFIG_DIR` and `--setting-sources project` keep the author's memory, CLAUDE.md, hooks
    and plugins out; the workflow arm gets its skills and `CLAUDE.md` block in the fixture. Token
    counts are exact either way; the reported cost is the API-price equivalent. Runs go in batches
    so the plan's usage limits are not used up in one go.
    The final result line gives tokens per model (fresh input, cache read, cache write, output),
    cost, turns and time; the per-message usage in the stream doubles as the read audit above.
    `--max-budget-usd` caps a runaway run. Each run records the Claude Code version and the repo
    and skills commit.
  - Measure: tokens, cost, time, cards made, cards passing `asl lint`.
  - Rate (author): 15 random cards per cell (150 in all): 5 code, 5 topic, 5 language, drawn
    evenly across tasks and runs (cards from one run are alike). Rated 1 to 5 in a small local
    page (`python benchmarks/rate.py`): the card as Anki shows it, front then back, keys 1–5,
    shuffled, cell hidden until the end, saved after every card so it can be done in sittings.
  - The scale is ordinal: a 1-point step is the difference that matters, and 15 vs 15 finds it
    (80% power, α 0.05, rating SD ~1). Compare with Mann-Whitney (or ordinal regression for
    model × arm × effort), report medians and the share of 4–5 ratings, not just means.
  - Report per cell: total tokens and cost, median rating, good cards (4–5) per 100k tokens and
    per dollar. Later, the same cards' review fail rates from `asl stats` as the real measure.
  - Stored in the repo: `benchmarks/` holds the runner, rating page and report; only
    numbers go in git (`benchmarks/results/<date>/`: per-run tokens and cost, per-card scores by
    id and cell, the plots). Card text, transcripts and fixtures stay local (gitignored), so no
    vault content is published. The report writes the summary table and plots into the README
    between markers, so a rerun updates it when skills or models change.

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
