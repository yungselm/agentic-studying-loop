---
name: write-cards
description: Write or update Anki cards (YAML) for a pattern the user learned in this project, following the card home's standards. Use when the study-loop block in CLAUDE.md says cards are due, or the user asks to card something.
---
# Write cards

Paths (card home, deck folder) are in the CLAUDE.md study-loop block.

1. **Read** `<card home>/standards/core.md`, `<pack>.md`, `preferences.md` (wins), and the deck's
   `profile.md`. Skim `Overview.md` and grep the deck for the pattern: no duplicates.
2. **Decide:** only recurring patterns, only confirmed working code. Big pattern → ladder;
   async/concurrency → timeline first. Aim for ~half code cards. From a vault note (lectures,
   study notes): facts → `cloze`, *why* → `concept`; its `[!question]` callouts are ready-made.
   From a book or link (`study-source`): `source: "[[Book.pdf#page=N]]"` or the URL, so the
   sources map counts it; the brief's `goal` and `builds_on` (Overview.md) decide what and how.
3. **Write** into `<slug>.yaml` (stdlib + stubs, checked) or `<slug>_ext.yaml` (third-party,
   verbatim). Leave out `id`/`std`, `asl fix` adds them:
   ```yaml
   - instruction: |   # behaviour + every literal produced
     starter: |       # location header, context frame, one gap
     solution: |      # same lines, gap filled
     notes: |         # the why
     source: "src/pkg/store.py → Store.load"
     tags: [project, topic]
     tests: |         # checked file only: 2–3 asserts
   - type: concept
     question: |
     answer: |
       **Bold lead.** ≤ two sentences.
   - type: timeline
     question: "Order ...:"
     steps: [first, second, third]   # correct order; the build shuffles
     detail: "who runs what"
   - type: cloze
     text: |                         # 2–5 short gaps; gap the name too (asks both ways)
       {{Atomic write}}: a {{temp file}} in the same folder, then {{`os.replace`}}.
     hook: "optional mnemonic / scene, ![[scene.png]]"
     source: "[[Atomic file writes#How it works]]"
   ```
4. **Finish:** `asl fix <deck>`, then `asl lint -q <deck>` and `asl check <deck>`; fix every
   problem. Report the new ids in one line.
5. **Corrections** from the user: fix the card, add a dated one-line rule with the id to
   `preferences.md`.
