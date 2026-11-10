---
name: study-note
description: Write a study note in the user's notes vault (Obsidian-style markdown) for a topic they are learning in this project. Use before writing cards for a new topic, or when the user asks for a vault note.
---
# Study note

The notes folder is in the CLAUDE.md study-loop block. Notes get skimmed: one idea per note,
the first screen carries it, links build the web. `preferences.md` (*Notes*) wins.

1. **Covered already?** Read the folder's overview (`Overview - *.md` or a MOC) and search the
   vault. If yes: refresher + link, or add only what's new.
2. **Upgrading a note?** Restructure, never cut: every fact, formula, example and link stays,
   visible or folded. Check against the old note (and its source link); tell the user what moved.
3. **Write** one file per idea (lectures: one per lecture, `type: lecture`). One line per
   paragraph (Obsidian renders every line break). No filler, no emoji; bold only card keywords.
   ````markdown
   ---
   type: concept
   tags: [python, files]
   aliases: [other names]
   budget: 600          # only if the topic needs it (default ~250 visible words, lecture ~800)
   source: "[[Book.pdf#page=42]]"   # from a book or link: the sources map counts it
   ---
   # Atomic file writes

   > [!tldr]
   > The whole idea, ≤ 2 lines.

   ```mermaid
   flowchart LR         %% ≤ 8 nodes; or sequenceDiagram, stateDiagram-v2, mindmap
   ```

   ## Why care          — the concrete failure it prevents
   ## How it works      — ≤ 5 one-line steps; formulas with a **where:** line
   ## In this project   — real files/functions

   > [!note]- Details   — folded depth: fold, don't cut
   > [!warning] Pitfalls
   > [!question]- Test yourself: ...?   — answer inside

   ## Connections
   - builds on: [[Other note]]: reason ≤ 8 words   — or used by, contrast, part of, see also
   ````
4. **Register** in the overview: a reading-order line and a node on its Mermaid map
   (`class A,B internal-link` makes nodes clickable); notes worth writing go under *Next*. Add
   the reverse link in the linked note.
5. `asl notes <folder>`: fix every `!`; act on `~` only where it improves the note.
6. Let the user read and ask before code or cards follow.
