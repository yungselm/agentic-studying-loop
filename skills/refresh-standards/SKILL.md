---
name: refresh-standards
description: Re-measure the card standards on the user's own Anki review data (a manual .apkg/.colpkg export) and propose edits to the standards and limits. Use when the user exports their deck and asks to refresh or tune their card standards.
---
# Refresh standards

Only when the user asks. Input: an Anki export with scheduling information.

1. `asl stats <export> --home <card home> [--deck "<name>"]` (needs the `analysis` extra) writes
   `evidence/<date>-<deck>-summary.md` (for you), `-report.md` (tables, fronts; for the user)
   and `-cards.csv`, and says if a refresh is due. Not due → report the status line and stop
   unless the user wants to continue.
2. Read the **summary** (not the report) and the current `standards/*.md` + `studyloop.yaml`. Look
   for: suggested limit changes (*Suggestions*; `*` bins have few answers), leeches and the
   hardest/easiest ids (open only those rows in the report to see their fronts), decks far above
   average, whether the last version helped (*By standards version*; revert if not). Name a
   mechanism for each change.
3. Propose one compact diff (standards files + `studyloop.yaml` limits), each edit with its
   evidence line, plus leech ids worth rewriting. **Apply nothing before approval.**
4. After approval: apply, bump `standards_version`, update `core.md`'s evidence section, add a
   dated line to `preferences.md`, then `asl stats <export> --home <card home> --mark-refreshed`.
