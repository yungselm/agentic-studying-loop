# Architecture

The target structure of the code: a small **core** (the engine that reads, checks and builds
cards) and **modules** that plug into it, one per workflow, mirroring the skills. This is
the plan for the refactor; the [migration order](#migration-order) says how we get there.

Goals:
- **Install only what you use.** Someone who only writes code cards never installs a Japanese
  tokenizer; someone without Obsidian never needs a vault.
- **The agent sees as little as possible.** Every layer is designed for token cost: see
  [Token budget](#token-budget-the-agent-sees-as-little-as-possible).
- **Contributors can add a module without touching core**: a card type, a language, an
  analysis of review data.

## Layout

```
skills/                       at the repo root, so non-coders (and their agents) can edit them;
                              each skill is owned by one module and installed only with it
studyloop/
  core/         cli, registry, card files, config, vault (optional), budget, ids, lint,
                build, check, reviews (+ join), card types, packs/{python,rust,cpp}
  notes/        built in        study notes: `asl notes`               → study-note
  projects/     built in        code repos: init, modes, CLAUDE.md     → (modes)
  sources/      built in        topics from books/links: `asl topic`, `asl sources`
                                                                       → study-source
  language/     [lang]          the shared language pipeline: `asl lang`,
                                sentence + grammar cards              → language-cards
  language_ja/  [lang-ja]       Japanese for `language`
  analysis/     [analysis]      analyses of review data, reports      → refresh-standards
```

| Module | Install | Skills | Owns |
|---|---|---|---|
| core | always | check-cards, write-cards | card format, deck/home config, lint, build, check, ids, card types `code` `concept` `cloze` `timeline`, packs, Anki export reader, token budget |
| notes | built in | study-note | note checks (TL;DR, diagram, budget, links) |
| projects | built in | — | deck kind `project`, `asl init`, `asl mode`, `modes/*.md`, the CLAUDE.md block |
| sources | built in | study-source | deck kind `topic`, `asl topic`, `asl sources`, PDF / markdown / URL readers |
| language | `[lang]` | language-cards | deck kind `language`, card types `sentence` `grammar`, their templates and lint rules, lines, plan, draft, sync, tts, clean |
| language_ja | `[lang-ja]` | — | the `Language` for Japanese: fugashi + unidic, furigana, JLPT lists, JMdict, VOICEVOX |
| analysis | `[analysis]` | refresh-standards | the `Analysis` interface, the bundled analyses, the report writer; pandas, matplotlib |

**Built in** means the module ships with every install (no extra dependencies) but stays a
separate package with the same boundaries. **Optional installs** bring heavy dependencies:
`pip install agentic-studying-loop[lang-ja]` (which pulls in `[lang]`). The Python pack's
checker needs `ruff` and `pytest`: `[python]`. Rust and C++ checkers use system tools.

## Dependency rules

- A module imports core and the modules it declares in `requires`. **Core never imports a
  module.** CI enforces this with `import-linter`.
- Modules are found through the entry point group `studyloop.modules`. One distribution for
  now; because discovery already goes through entry points, a module can later become its own
  package (or a third-party one) without changes to core.
- A module whose optional install is missing still registers its name: `asl lang` then says
  `install agentic-studying-loop[lang]` instead of an ImportError. Heavy imports happen inside
  the commands, never at registration.

## Extension points

A module registers what it adds; the core engines (lint, build, stats, the CLI) only iterate
over what is registered. Core registers its own card types through the same API. Sketch (names
settle during the refactor):

```python
class Module:
    name: str                          # "language"
    requires: tuple[str, ...] = ()     # ("core",) is implicit
    extra: str | None = None           # "lang": the optional install that brings its deps
    skills: tuple[str, ...] = ()       # ("language-cards",): names of folders in skills/
    def register(self, reg: Registry) -> None: ...
```

| Extension | What it provides | Example |
|---|---|---|
| `DeckKind` | `detect(deck.yaml)`, scaffold templates, allowed card types | `language` (has `lang:`) |
| `CardType` | fields, `validate(card, ctx) → flags`, `measures(card)`, `note_model()`, `to_fields(card, ctx)` | `sentence` |
| `LintRule` | per-card or per-deck check → `!` / `~` flags | the card mix of a topic |
| `Checker` (pack) | compile / lint / test a batch of code cards ([writing a pack](writing-a-pack.md)) | `rust` |
| `SourceReader` | a source → parts with text | PDF bookmarks, markdown headings |
| `Analysis` | `run(table, ctx) → Section` | retention per source note |
| command | `register(subparsers)` | `asl lang …` |

A deck states its kind: `asl init`, `asl topic` and `asl topic --lang` write `kind:` into
`deck.yaml`, so nothing depends on the order modules load in. Decks without `kind:` (made
before this) are detected from their keys: `lang:` → `language`, `repo:` or a `profile.md` →
`project`, else `topic`. If two kinds claim the same deck, `asl lint` says so and asks for an
explicit `kind:` instead of guessing. If no module claims a deck, core still lints and builds
it as a plain deck: cards only.

Packs keep their own mechanism (`pack.yaml` + `checker.py`, found through `ASL_PACKS`). On a
card, `pack:` overrides the deck's pack (formerly `lang:`, which now only means a spoken
language in `deck.yaml`).

## The vault is optional

A vault is a folder of markdown, nothing more. The user is asked once, when the card home is
set up: do you keep notes in a folder of markdown (Obsidian or any other), and where? The
answer goes into `studyloop.yaml` as `vault: <path>` or `vault: none` (`asl init-home --vault
<path>` / `--no-vault`); `none` means the question never comes again. Card homes from before
this have no `vault:`; for them core falls back to the nearest folder with `.obsidian`. With a vault, build and lint
resolve `[[wikilinks]]` and `![[images]]`; without one, link resolution is off and cards build
anyway. The card home can be any folder. Obsidian is supported, never required.

## Token budget: the agent sees as little as possible

The agent is the main user of the CLI, and every token it reads costs the user. Every module
follows these rules; reviewing a new module starts with *what does it add to the agent's
context, and when?*

| Layer | Rule |
|---|---|
| Skill list | Only installed modules install their skills; an uninstalled module costs nothing in any session. |
| Skills | One workflow per skill, steps only. Details the agent needs only sometimes go in files next to `SKILL.md` and are read on demand (see below). Inline anything under ~30 lines that is almost always needed: each extra file is one more read. |
| CLI | The agent runs commands and never reads the code. Output is compact and actionable (`!` must fix, `~` may fix, `-q`). Commands do the summarizing: `asl sources --read <part>`, `asl lang draft` prints only the line and the dictionary senses. |
| Rules | A rule that lint can check does not also need prose in the standards. Moving rules into lint keeps `core.md` and the pack standards short, and those are read before every batch. |
| Big inputs | Never read whole. Books, episodes and review data go through `core.budget`: estimate tokens, split into parts that fit a batch, track each part's status. |
| Big files | `Overview.md`, `Vocabulary.md` and the like: read only the frontmatter or one section, ideally through a command (`--show brief`). |
| Reports | Every analysis gives the agent a short summary and `suggestions[]`; figures and tables are for the human, never read by the agent. |

`write-cards` shows the pattern for skills:

```
skills/write-cards/
  SKILL.md        steps for all decks; "project deck → project.md, topic deck → topic.md"
  project.md      recurring patterns, ladders, timelines
  topic.md        the brief, the card mix, notes → cloze/concept
  types/code.md   field reference, read only when writing that type
  types/cloze.md
```

## Language modules

`language` holds everything that is the same for every language: lines from video + subtitles
or mined decks, the i+1 planner, drafts, sync from reviews, TTS fallback, the `sentence` and
`grammar` card types. What differs per language sits behind one interface, implemented by a
module per language:

```python
class Language:
    code: str                                      # "ja"
    def tokenize(self, text) -> list[Token]: ...   # surface, lemma, reading, part of speech
    def reading_aid(self, tokens) -> str: ...      # furigana, pinyin, or the plain text
    def levels(self) -> Levels: ...                # JLPT, CEFR, HSK
    def dictionary(self) -> Dictionary: ...        # JMdict, Wiktionary, ...
    def tts_engines(self) -> list[TTSEngine]: ...
    def text_length(self, s) -> int: ...           # characters (ja) or words (it)
    subtitle_filters: dict                         # keep / speaker labels / strip (today in ja.yaml)
```

`language_ja` is today's `lang/ja.yaml` plus the Japanese parts of `tokens.py`, `levels.py`,
`dictionary.py` and `tts.py`. Italian becomes `language_it` with its own optional install,
not a fork of the pipeline.

## Review data and analysis

Core reads an Anki export (`.apkg` / `.colpkg`) into one `ReviewData` (cards, notes, revlog,
decks, note types) and joins it back to the card files through each card's GUID. Every review
then carries its card's deck, type, `std` version, tags, size measures, `source:` note and
source part. Grouping by any of those answers "which lecture / chapter / note was weak". Both
`analysis` and `asl lang sync` use this reader.

`analysis` turns the joined table into a pandas DataFrame and runs every registered analysis:

```python
class Analysis:
    name: str
    def run(self, table: pd.DataFrame, ctx) -> Section: ...

@dataclass
class Section:
    title: str
    summary: str                   # a few lines, for the agent
    markdown: str = ""             # tables etc., for the human
    figures: list = ()             # matplotlib figures → SVG next to the report
    suggestions: list[Suggestion] = ()

@dataclass
class Suggestion:                  # what refresh-standards acts on
    target: str                    # "limits.code.typed_chars_max", "standards/python.md", a card id
    kind: str                      # limit | rule | rewrite
    old: str | None
    new: str
    evidence: str                  # one line: the numbers behind it
    confidence: str                # low | medium | high (bin sizes, effect size)
```

The report goes to `evidence/<date>-report.md` with figures beside it, so it renders in
Obsidian and in any markdown viewer. The current `asl stats` (size bins, timer share, leeches,
standards versions) becomes the first set of analyses. New ones (graphs, weak topics) are
added without touching the skill: it only reads `summary` and `suggestions`.

## Tests and CI

Tests live with their module (`tests/core/`, `tests/language/`, ...). CI installs core alone
and runs the core tests, then one job per optional install. That matrix is what proves core
works without the modules. `import-linter` checks the dependency rules; a small check makes
sure every skill belongs to exactly one module and every skill a module names exists.

## Migration order

Each step keeps the tests green and is its own commit.

1. **One Anki export reader** in core (`core/reviews`), replacing `stats.open_collection` /
   `load_cards` and `lang/apkg.read_export`.
2. **Rename** the card-level `lang:` to `pack:`; `asl fix` migrates card files and writes
   `kind:` into each `deck.yaml` that lacks it.
3. **`core/` package**: move card files, config, ids, lint, build, check; the vault becomes
   optional (`vault:` setting).
4. **Registry and extension points**; core registers its card types through them.
5. **Language out of core**: the sentence/grammar note models and media handling (`build.py`),
   `lang_flags` (`lint.py`), the language branch (`config.py`), `_init_language`
   (`project.py`), the id special case (`ids.py`) → `language/`; then split off `language_ja/`.
6. **`sources`, `notes`, `projects`** as modules; `core.budget` from `sources.py`.
7. **`analysis`**: the join, the `Analysis` interface, the current stats ported as analyses.
8. **Packaging**: optional installs in `pyproject.toml` (`pytest`/`ruff` out of the base
   dependencies), skill ownership + filtered `install-skills`, `write-cards` split into
   reference files, `import-linter` and the CI matrix.

## Later

- **Subagents for long sources**: one batch (read a part → notes → cards) in a subagent, so the
  main session keeps only the summary. Saves tokens on long books but loses the conversation's
  context; only once the single-batch flow is stable, and backed by review stats.
- **Separate distributions** (`studyloop-lang`, third-party analyses) once someone outside
  needs them; the entry points already allow it.
