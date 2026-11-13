---
name: study-source
description: Start a topic from lectures, books or links (PDFs in the vault, URLs) and work through them one part at a time, into study notes and cards. Use when the user points to sources or a folder of slides, gives new ones, or asks for the next lecture or chapter.
---
# Study a source

The deck's `Overview.md` holds the brief (frontmatter) and the sources map (`## Sources`).
Read only the frontmatter and that section: the card table below it isn't needed here.

1. **New topic?** Ask first, one question at a time: the goal, what the user already knows, and
   **study notes in the vault first (which folder?) or cards straight from the sources**. Then
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
3. **Read only that part:** `asl sources <deck> --read <part>` for PDFs; never Read the whole
   PDF, and open page images only for a figure the text needs. Links: fetch only that part.
4. **Filter by the goal** (and `focus` / `skip` lists, if set): card what serves it, in depth for
   `focus`; name what you skipped in one line.
   `builds_on`: prefer contrast cards ("Rust `Box<T>` → C++?") and say where the analogy breaks.
5. **Write:** `notes:` folder → `study-note` per idea with `source: "[[Book.pdf#page=N]]"` in
   its frontmatter, then `write-cards` from the notes. `notes: false` → `write-cards` with
   `source: "[[Book.pdf#page=N]]"` (or the URL with its anchor) on every card.
6. **Finish:** `asl fix <deck>` (the part's status updates), `asl lint -q <deck>`, and
   `asl check <deck>`: it compiles and runs the code cards (C++, Rust, Python); fix every problem.
   No compiler found (e.g. Windows without `g++`): say so, and offer to run the check in WSL.
   Then `asl build <deck> -o "<card home>/<deck>.apkg"` (same file each batch; re-importing
   updates cards in place). Report: the part, new ids, notes written, the `.apkg` path (import:
   File → Import, "Update notetypes" ticked), and the next part.
