---
type: guideline
scope: anki
standards_version: 1
evidence: "starter defaults: one learner's Rust deck, 542 cards, 6,537 reviews (2026-10-13)"
---
# Card standards (core)

Rules for writing study cards, for an AI agent or for you. They are **starter defaults**
measured on one learner's review data; `asl stats` + the `refresh-standards` skill re-measure
them on yours, and this file changes with that evidence.

**Read order before writing or editing cards:**
1. this file (`core.md`)
2. the pack addendum for the language (`rust.md`, `python.md`, …)
3. `preferences.md`: your own corrections, newest last; they win over 1 and 2
4. the project's `profile.md` (file roles, what the project files are) and `Overview.md` (the card index)

Numeric limits live in `studyloop.yaml` (`limits:`); `asl lint` enforces them. The numbers
below are the defaults.

---

## 1. What the data says

Graded binary (Again/Good) under FSRS, desired retention 0.90. "Fail" = share of review-phase
answers graded Again. "Typed" = solution lines not already in the starter, i.e. what you type.

| Finding | Number |
|---|---|
| Leeches (≥5 lapses) that are code cards | 46 / 46 |
| Median FSRS difficulty, code vs concept | 9.5 vs 2.1 |
| Fail rate, code vs concept | 20% vs 11% |
| Code fail rate by typed size: ≤40 / 40–80 / 80–250 / >250 chars | 17% / 21% / 22% / 39% |
| Reviews hitting Anki's 60 s timer, by typed size: ≤40 / 40–80 / 80–150 / >150 chars | 6% / 18% / 58% / 70%+ |
| Same typed size (40–80 chars), 1 / 2–3 / 4–6 lines | 20% / 20% / 23% |
| Concept fail rate by answer length: ≤300 / 300–450 chars | 7–8% / 15% |
| Concept cards with a bold lead >250 chars: median difficulty | 7.3 (vs 2.1) |
| Concurrency + async code cards vs all other code cards | 32% vs 19% fail |

What follows from it:

1. **Typing is the cost, in characters, not lines.** Instruction, starter and notes length had no
   measurable effect (|ρ| < 0.07); typed characters did (ρ = +0.27). Context you *read* is free, so
   pre-fill it generously. Context you *type* is expensive, so keep it minimal.
2. **Whole programs from a prose spec are the leech pattern.** Each failure is one of 3–5 sub-steps,
   and the whole card gets an Again.
3. **Internals you have never used don't stick.** Mechanism cards (how an executor polls) are hard;
   "when/why would you use it" cards are easy. Prefer flows you have seen run.
4. **Concept cards fail when they ask more than one thing**: long answers, cheat sheets, "name the
   three…", "X, and why Y?".

---

## 2. Code cards

| | target | hard max |
|---|---|---|
| Typed characters (whitespace-trimmed) | ≤ 80 | 120 |
| Typed lines | no limit (follows from characters) | — |
| New ideas per card | 1 | 1 |

**Card mix: about half code cards.** You learn patterns by typing them. Before writing a concept
card, check whether the idea can be typed instead (the *why* goes in `notes`). Keep concept cards
for what code can't show: why/what-if, timelines, debugging symptoms, measurements.

- **Pre-fill everything that isn't the lesson**: signatures, imports, stub types, the lines around
  the interesting one. The diff is line by line, so pre-filled lines that match cost nothing.
- **Leave one gap**: the line(s) that carry the idea. Several lines are fine while they stay under
  the limit and form one idea. Two ideas or over the max → a **ladder**.
- **Format the solution like the language's formatter** (and like the repo, for project cards).
  A correct line formatted differently shows up red.
- **The instruction states the observable behaviour and every literal the solution produces**
  (`asl lint` checks literals). Naming the function to use is optional and never rescues a card
  that needs 3+ steps.
- **Every checkable card has `tests:`**: two or three asserts, the normal case plus the edge the
  card is about (empty, missing, overflow).

**Ladder for big patterns.** 2–4 cards that all show the *same* full code; each blanks a different
step (one idea, ≤ max). You read the whole program every time and type one step.

### 2a. Context frame: code lives somewhere

A gap sits in its **home**, never in a floating fragment. Every code card's starter/solution shows:

| The gap is… | The card also shows |
|---|---|
| inside a function | the full signature and its end |
| inside a method | that, plus the enclosing class / impl line |
| inside a `match`/`switch` arm | the match line and the arm's pattern; other arms become `... other arms` comments |
| part of a builder / call chain | the whole chain |
| a type, decorator, derive or field | the whole type definition |

- **Elide inside, never cut the frame.** Skipped statements become one comment line saying what's
  skipped (`# ... validate the path`). Keep the lines that define what the gap uses and what uses
  its result.
- **Location header.** For project cards, the first line of every code section is the file path from
  the repo root plus the file's role from the project's `profile.md`:
  `# src/tasklog/store.py  (persistence: load/save the task list)`. Generic demo code gets none.
- **`uses:` hint.** When the gap calls a name defined outside the card, put its signature and home
  on the line above the gap, in starter and solution: `# uses: Store.save(self, path: Path) -> None  [src/tasklog/store.py]`.
  Leave it out when that name *is* the lesson.
- **Budget:** about 15–35 lines of context. A longer function gets more elisions, not a fragment.

---

## 3. Concept cards

| | target | hard max |
|---|---|---|
| Whole answer (bold lead + detail) | ≤ 250 chars | 300 |
| Bold lead sentence | ≤ 120 chars | 150 |
| Questions per card | 1 | 1 |

- **One question.** "And" joining two asks, "what's the fix?" after a "why", "name the N…", "one line
  each", comparison tables → split. A *symptom → cause + fix* card is fine if the bold lead says
  both in one sentence.
- **The bold lead is the checkable answer.** Grade yourself against it only. At most two short
  sentences of detail after it.
- **No cheat sheets.** One card per row, or none (look it up).
- **Ask the transferable concept, not the episode.** Answerable months later from general knowledge
  plus the front. Put the project case in the detail as `Project example: …`.
- **The front shows only `question`.** Code the question is about goes *in the question*, indented
  4 spaces (≤ ~10 lines). `code:` is back-only extra context (and is run by `asl check`).

---

## 4. Hard or never-used topics

For async, concurrency and anything you haven't written yourself, in this order of preference:

1. **Timeline card** (`type: timeline`): list the 3–6 steps of a *real* flow **in the right order**
   in `steps:`; the build shuffles them and labels A–E, and the answer is the order. Steps must have
   one unambiguous order; concurrent steps go in `detail:` instead. One timeline per flow (start →
   deliver → state change → redraw), another for cleanup.
2. **What-if card** on your own code: "If `update()` loaded the file directly, what would you see?"
   One mechanism per card.
3. **Fill-the-gap code card** in the real surrounding code (§2).
4. **Ladder** (§2) for patterns you'll have to write from memory.

Avoid for these topics: from-scratch programs, hand-rolled internals, mechanism cards before you
have used the API they explain.

---

## 5. Project cards

The cards **look like the repo**, not like a textbook exercise.

- **Real names and shapes**: the repo's functions, types, fields and statements. No invented
  stand-ins, no API the repo doesn't use (put the idiomatic alternative in `notes`).
- **Two files per project:**
  - `<project>.yaml` is checked (`asl check`): the lesson compiles/runs with the standard library
    alone, given minimal **stubs** of the real types under a `stubs (real: <file>)` comment, with
    only the fields the card touches.
  - `<project>_ext.yaml` has `check: false` (deck.yaml): code that needs third-party libraries.
    Copy it **verbatim** from the repo in its context frame and blank only the target line(s).
- **`source:`** names `<file> → <function>`. Tags include the project name.
- **Only patterns that come back get code cards.** One-off domain code gets the study note plus at
  most 2–3 concept cards on the idea.
- **Only confirmed code.** Cards are written after the code works, from the commit named in the
  overview.
- **Drift:** when code a card mirrors changes, mark it `needs update` in `Overview.md` and rewrite
  it. What-if/debugging cards about a past mistake stay valid.

---

## 6. Ids, index, changes

- Every card has an `id:` field, `<prefix>-NNN` (prefix in deck.yaml). Ids are never reused;
  deleted ids go into deck.yaml `retired_ids`. `asl ids <deck>` prints the next free one.
- The Anki note GUID comes from the id, so **editing any field, the front included, updates the card
  in place** on re-import. Only a new id (or changing a card between code and concept) creates a new
  note.
- **Splitting a card:** the part closest to the original keeps the id; new parts get new ids.
- Every card has a row in the project's `Overview.md` (status `draft` → `reviewed` → `needs update`).
- New cards get `std: <standards_version>` from `studyloop.yaml`, so later reports can compare
  cards written under different rules.
- Before adding a card, search the project's card files and any base deck for the same pattern.
  Plain patterns the base deck already drills get no project card; only the project-specific angle.

---

## 7. Pre-flight (before reporting cards as done)

1. `asl lint <deck folder>`: no `!` flags (ids, size, self-containment).
2. `asl check <deck folder>`: compiles/runs, linter clean, `tests:` pass.
3. `_ext` cards: every line except `...` elisions, the location header and `uses:` hints appears in
   the source file the header names, in order; every code card shows its context frame.
4. `Overview.md` rows updated; one line in chat names the cards added or changed.

---

## 8. Refreshing the evidence

You decide when. Export the deck from Anki with scheduling information, then run the
`refresh-standards` skill (it runs `asl stats`). The refresh is *due* once enough of the deck is
mature (`refresh:` in `studyloop.yaml`; defaults: 50% of cards at ≥21 days interval and ≥1,000
review answers, then every further 25%). The skill proposes edits to this file, the pack file and
`studyloop.yaml`; you approve them; `standards_version` goes up by one.
