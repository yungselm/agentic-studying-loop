---
name: study-source
description: Start a topic from lectures, books or links (PDFs in the vault, URLs) and work through them one part at a time, into study notes and cards. Use when the user points to sources or a folder of slides, gives new ones, or asks for the next lecture or chapter. Not for languages (use language-cards) or code in a repo (the project's mode).
---
# Study a source

Deck kind **topic**. The deck's `Overview.md` holds the brief (frontmatter) and the sources map (`## Sources`).
Read only the frontmatter and that section: the card table below it isn't needed here.

**Effort:** writing cards needs no deep reasoning. In the first batch of a session, tell the
user once: low effort (`claude --effort low`) gives the same cards for up to a third less
([benchmark](https://agentic-studying-loop.readthedocs.io/en/latest/benchmarks.html)).

1. **New topic?** Ask first, one question at a time: the goal, what the user already knows,
   **study notes in the vault first (which folder?) or cards straight from the sources**, and
   for a source that teaches code, **how many code cards** (→ `cards: {code: 0.3}` in the
   brief; default `{code: 0}`). Then
   `asl topic "<name>" --home "<card home>" --sources "<folder|file|url>" --notes "<folder>"`
   (or `--no-notes`) `--goal "…" --builds-on <what they know>`; the card home is in the CLAUDE.md study-loop
   block. **Existing topic, no cards yet** (first batch): confirm the brief's `goal` and `notes`
   in one line before writing; `notes: ""` means undecided → ask. New sources later (also from
   chat): add to `sources:` (a folder, vault file, `[[link]]`, URL; `{url, key, parts:
   ["#anchor"]}` for a long page), then `asl sources <deck>` (a new PDF takes up to a minute,
   once). Slides in `.pptx`: ask the user to export to PDF next to them.
2. **Pick one part:** the user's choice, else the next useful `todo` for the goal. Say in one
   line: part, ~tokens, expected cards (`~N cards` once shown), and days of new cards already
   queued (map header). More than one part, or a `⚠ split` row → ask first.
3. **Cards straight from the source** (`notes: false`; a PDF or Markdown part):
   `asl prompt <deck> --part <part>` (parts asked for together: `a,b`) prints one prompt: the
   brief, how many cards of which kind, the rules, the card format, the part's text and its
   figures (saved to `<deck>/figures/`). Follow it exactly and read nothing else: not the
   standards, not the Overview's card table, not asl's code. It ends with `asl finish`.
4. **Notes first** (`notes:` folder), or a **link**: `asl sources <deck> --read <part>` (it
   saves and lists the part's figures: Read those the text discusses) or fetch only that part.
   Card what serves the goal (`focus` / `skip`, if set; `builds_on`: contrast cards, say where
   the analogy breaks); name what you skipped in one line. Then `study-note` per idea with
   `source: "[[Book.pdf#page=N]]"`, and `write-cards` from the notes (a link: its URL with the
   anchor as `source`). A card about what a figure shows embeds it: `![[figures/<file>]]`.
5. **Finish:** `asl finish <deck>`: fix (the part's status updates), lint, check (compiles and
   runs code cards), then builds `<card home>/<deck>.apkg` (same file each batch; re-importing
   updates cards in place). It stops at the first problem: fix it, run it again. No compiler
   found (e.g. Windows without `g++`): say so, and offer to run it in WSL. Report: the part, new
   ids, notes written, the `.apkg` path (import: File → Import, "Update notetypes" ticked), and
   the next part.
