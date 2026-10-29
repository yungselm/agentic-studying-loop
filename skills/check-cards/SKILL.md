---
name: check-cards
description: Validate a deck folder of study cards (ids, size limits, self-containment, compile/lint/tests) and build the Anki package. Use when the user asks to check, validate, or build their cards.
---
# Check cards

1. `asl lint "<deck folder>"`: ids, size limits from `studyloop.yaml`, self-containment.
   Fix every `!`. For `~` (over target, under the hard max) say why it's acceptable or shorten it.
2. `asl check "<deck folder>"`: runs the pack's checker (Rust: clippy + cargo test; Python: ruff +
   pytest). Files with `check: false` are skipped; verify those by comparing with the repo source.
3. Cards without ids: `asl ids "<deck folder>" --fix` (it also freezes old GUIDs when the deck
   uses `guid: legacy-kata`, so no duplicates appear in Anki).
4. Build when asked: `asl build "<deck folder>" -o "<file>.apkg"`. Import in Anki with
   "Update notetypes" enabled; changed cards update in place.

Report: number of cards, flags fixed, anything left for the user to decide.
