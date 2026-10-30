---
type: guideline
scope: anki
standards_version: 1
evidence: "starter defaults: one learner's Rust deck, 542 cards, 6,537 reviews (2026-10-13)"
---
# Card standards (core)

Defaults measured on one learner's reviews; `refresh-standards` re-measures them on yours.
Read with the pack file (`<pack>.md`) and `preferences.md` (wins on conflicts). Limits live in
`studyloop.yaml`; `asl lint` enforces them and everything marked *(lint)*.

## 1. Evidence

| Finding | Number |
|---|---|
| Leeches (≥5 lapses) that were code cards | 46 / 46 |
| Fail rate, code vs concept | 20% vs 11% |
| Code fail rate by typed chars ≤40 / 40–80 / 80–250 / >250 | 17 / 21 / 22 / 39% |
| Answers hitting the 60 s timer, typed ≤40 / 40–80 / 80–150 / >150 | 6 / 18 / 58 / 70%+ |
| Concept fail rate by answer ≤300 / 300–450 chars | 7–8 / 15% |

So: **typing is the cost, in characters, not lines** (instruction/starter/notes length had no
effect; reading is free). Whole programs from a prose spec are the leech pattern. Mechanism cards
for APIs you never used don't stick. Concept cards fail when they ask two things.

## 2. Code cards

- **≤ 80 typed chars, max 120** *(lint)*; no line limit. One idea per card. About half of all cards
  are code cards: if an idea can be typed, type it and put the *why* in `notes`.
- **Pre-fill everything but the lesson; leave one gap.** Two ideas or over the max → a **ladder**:
  2–4 cards showing the same full code, each blanking a different step.
- Solution formatted like the language's formatter (a differently formatted line shows red).
- The instruction states the behaviour and every literal the solution produces *(lint)*.
- Checkable cards have 2–3 `tests:` asserts, incl. the edge case the card is about.
- **Context frame** *(lint)*: the gap sits in its home: enclosing function signature (plus the
  class/impl line for methods), the whole match, chain or type definition. Skipped code becomes
  one `... what's skipped` comment, never a cut. About 15–35 lines.
- **Project cards** *(lint)*: each code section starts with `<comment> <path>  (<role>)`, the role
  from `profile.md`. A gap calling a name defined elsewhere gets `<comment> uses: <signature>  [<path>]`
  above it, unless that name is the lesson.

## 3. Concept cards

- **Answer ≤ 250 chars (max 300), bold lead ≤ 120 (max 150)** *(lint)*. Grade against the
  `**bold lead**` only; at most two short sentences after it.
- One question. No "and" joining two asks, no "name the N…", no cheat sheets or tables.
- Ask the transferable concept, not the episode; the project case goes in the detail as
  `Project example: …`.
- Code the question is about goes *in the question* (indented 4 spaces); `code:` is back-only.

## 4. Hard or never-used topics (async, concurrency, …)

Prefer, in order: **timeline** (`type: timeline`, real steps in the right order, one flow each),
**what-if** on your own code (one mechanism), **fill-the-gap** in real code, **ladder**.
Avoid from-scratch programs and hand-rolled internals.

## 5. Project rules

- Real names and shapes from the repo; no stand-ins, no API the repo doesn't use.
- `<project>.yaml` is checked: stdlib + minimal stubs of real types under `stubs (real: <file>)`.
  `<project>_ext.yaml` (`check: false`) is third-party code, **verbatim** from the repo *(lint)*.
- Only recurring patterns get code cards; one-off code gets the note + ≤3 concept cards.
- Only confirmed, working code. Drift → `needs update` in `Overview.md`, then rewrite
  (`asl lint` flags excerpts and `source:` names that no longer match).

## 6. Bookkeeping

Run `asl fix` after writing: it adds ids, `std:` and `Overview.md` rows. Ids drive the Anki GUID,
so edits (front included) update cards in place. Deleted ids go to deck.yaml `retired_ids`.
Before adding a card, search the deck (and any base deck) for the same pattern.

## 7. Done means

`asl fix`, `asl lint -q` and `asl check` all pass, and one line in chat names the card ids.
