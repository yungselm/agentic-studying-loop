---
name: study-source
description: Work through a topic's books and links (PDFs in the vault, URLs) one batch at a time, into study notes and cards. Use when the user points to sources for a topic, gives new ones, or asks to continue a book or course.
---
# Study a source

The deck's `Overview.md` holds the brief (frontmatter) and the sources map (`## Sources`).
Read only the frontmatter and that section: the card table below it isn't needed here.

1. **No brief yet?** Ask for the goal and what the user already knows, then write the
   frontmatter: `goal`, `builds_on: [rust]`, `notes: "<vault folder>"` or `notes: false`
   (cards straight from the source), `sources:` (vault file names, `[[links]]`, URLs;
   `{url, key, parts: ["#anchor", "chapters/x.html"]}` for a long page). Sources given in
   chat go there too. Then `asl sources <deck>` (a new PDF takes about a minute, once).
2. **Pick one part:** the user's choice, else the next useful `todo` for the goal. Say in one
   line: part, ~tokens, expected cards (`~N cards` once shown), and days of new cards already
   queued (map header). More than one part, or a `⚠ split` row → ask first.
3. **Read only that part:** `asl sources <deck> --read <part>` for PDFs; never Read the whole
   PDF, and open page images only for a figure the text needs. Links: fetch only that part.
4. **Filter by the goal:** card what serves it; name what you skipped in one line.
   `builds_on`: prefer contrast cards ("Rust `Box<T>` → C++?") and say where the analogy breaks.
5. **Write:** `notes:` folder → `study-note` per idea with `source: "[[Book.pdf#page=N]]"` in
   its frontmatter, then `write-cards` from the notes. `notes: false` → `write-cards` with
   `source: "[[Book.pdf#page=N]]"` (or the URL with its anchor) on every card.
6. `asl fix <deck>`: the part's status updates. Report the part, new ids, and what's next.
