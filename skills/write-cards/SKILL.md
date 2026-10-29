---
name: write-cards
description: Write or update Anki cards (YAML) for a pattern the user learned in this project, following the card home's standards. Use when the study-loop block in CLAUDE.md says cards are due, or the user asks to card something.
---
# Write cards

The project's CLAUDE.md study-loop block names the **card home** and this **project's deck folder**.

## 1. Read first, every time
1. `<card home>/standards/core.md`, then `<card home>/standards/<pack>.md`, then
   `<card home>/standards/preferences.md` (wins on conflicts).
2. `<deck folder>/profile.md` (file roles) and `<deck folder>/Overview.md` (existing cards).
3. `<card home>/studyloop.yaml` for `standards_version`.

## 2. Decide what gets cards
- Only patterns that will come back. One-off code: study note + at most 2–3 concept cards.
- Only **confirmed** code: it compiles/runs and the user agreed it works. Otherwise wait.
- No duplicates: search both card files of the deck (and any base deck the profile names) for the
  pattern first. Only the project-specific angle gets a card.
- Aim for about half code cards. Big pattern → a ladder of 2–4 cards; async/concurrency → a
  timeline card first.

## 3. Write
- Std-only (checkable) code → `<slug>.yaml`; third-party libraries → `<slug>_ext.yaml` (verbatim from
  the repo, context frame, location header).
- Get ids with `asl ids "<deck folder>"`; every new card gets `id:` and `std: <standards_version>`.
- Schema:
  ```yaml
  - id: tsk-012
    std: 1
    instruction: |   # behaviour + every literal the solution produces
    starter: |       # full context frame, one gap
    solution: |      # starter lines identical, gap filled, formatter style
    notes: |         # the why; idiomatic alternatives
    source: "src/tasklog/store.py → Store.load"
    tags: [tasklog, files]
    tests: |         # checkable file only: 2–3 asserts incl. the edge case
  - id: tsk-013
    std: 1
    type: concept
    question: |      # one question; code it asks about goes here, indented 4 spaces
    answer: |
      **Bold lead: the checkable answer.** At most two short sentences more.
    code: |          # optional, back side only
  - id: tsk-014
    std: 1
    type: timeline
    question: "Order the steps when ... :"
    steps: [first, second, third, fourth]   # in the CORRECT order; the build shuffles
    detail: "Which thread runs what, in one line."
  ```
- Add a row per card to `Overview.md` (status `draft`, source, related note).

## 4. Verify (don't report done before this)
1. `asl lint "<deck folder>"`: fix every `!`; `~` (over target) needs a reason.
2. `asl check "<deck folder>"`: compile/lint/tests pass.
3. `_ext` cards: compare every line with the source file at the overview's commit.
4. Tell the user in one line which ids were added or changed. Edits update cards in place on the
   next import (GUIDs come from ids), so there's nothing to delete by hand.

## 5. Corrections
When the user corrects a card's style ("too big", "use the real names"), fix the card and add a
dated one-line rule with the card id to `standards/preferences.md`.
