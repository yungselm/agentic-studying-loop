---
name: refresh-standards
description: Re-measure the card standards on the user's own Anki review data (a manual .apkg/.colpkg export) and propose edits to the standards and limits. Use when the user exports their deck and asks to refresh or tune their card standards.
---
# Refresh standards

The user decides when to do this; never nag. Input: an Anki export with scheduling information
(File → Export → Anki Deck Package, "Include scheduling information"; or a .colpkg).

1. **Run** `asl stats "<export>" --home "<card home>" [--deck "<deck name>"]`. It writes
   `<card home>/evidence/<date>-report.md` and `<date>-cards.csv` and says whether a refresh is due.
   If it's not due, show the status line and stop unless the user wants to go ahead anyway.
2. **Read** the report, the current `standards/*.md` and `studyloop.yaml`.
3. **Find changes the data supports**, e.g.:
   - a limit whose bins disagree with the current target/max (the report's *Suggested limits*);
     check that the bins have enough answers (`(few)` marks thin ones)
   - card shapes behind the leeches and the hardest 15 (from scratch? two questions? never-used
     internals?)
   - decks/topics far above the average fail rate → new shape rules for them
   - the *By standards version* table: did the last change help? Revert it if not.
   - what the easiest cards have in common (keep doing it)
   Ignore effects resting on fewer than ~60 review answers. Correlation isn't a rule by itself:
   name the mechanism you think explains it.
4. **Propose** one compact diff: the edits to `core.md` / `<pack>.md` / `studyloop.yaml` limits, each
   with its evidence line ("typed 80–120 chars: 16% fail, n=410"). Also list cards worth rewriting
   (leeches) by id. **Apply nothing before the user approves.**
5. **After approval**: apply the edits; bump `standards_version` in `studyloop.yaml`; update the
   `evidence:` line and section 1 of `core.md`; add a dated line to `preferences.md`
   ("v2: …"); then run `asl stats "<export>" --home "<card home>" --mark-refreshed` so the next
   refresh counts from here.
