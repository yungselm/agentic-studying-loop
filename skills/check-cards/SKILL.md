---
name: check-cards
description: Validate a deck folder of study cards and build the Anki package. Use when the user asks to check, validate, or build their cards.
---
# Check cards

1. `asl fix <deck>`: missing ids, `std:`, Overview.md rows.
2. `asl lint -q <deck>`: ids, size, self-containment, context frame, headers, verbatim excerpts,
   index, drift. Fix every `!`; drop `-q` to also see `~` notes.
3. `asl check <deck>`: compile, lint and run tests with the pack's checker.
4. If asked: `asl build <deck> -o <name>.apkg`; import with "Update notetypes" ticked ("Import any deck presets" only on the very first import).

Report: card count, what you fixed, what needs the user's decision.
