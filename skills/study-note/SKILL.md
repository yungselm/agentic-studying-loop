---
name: study-note
description: Write a study note in the user's notes vault (Obsidian-style markdown) for a topic they are learning in this project. Use before writing cards for a new topic, or when the user asks for a vault note.
---
# Study note

The project's CLAUDE.md study-loop block names the **study notes folder**.

1. **Check coverage first.** List the notes folder and read its overview/MOC note (e.g.
   `Overview - <topic>.md`). If the topic is covered, give a short refresher with a link to the
   note instead of a new note; extend the existing note if something is genuinely new.
2. **Write the note** as one markdown file in that folder:
   - frontmatter: `type: concept`, `topic`, `project`, `updated: <today>`, `tags`
   - title = the concept, not the episode ("Task::perform: async work off the UI thread")
   - sections: *The idea in two sentences* → *How it works* (a small diagram or numbered flow when
     there is one) → *In this project* (real file and function names) → *Pitfalls* → *Related*
     (`[[wikilinks]]` to neighbouring notes)
   - code examples are minimal and run as shown; mark anything the project doesn't do yet as such
3. **Register it**: add a line to the folder's overview note (create one if missing: a numbered
   reading order with one line per note on what it covers).
4. **Let the user read it and ask questions** before code or cards follow (teacher/mentor modes).
   Cards are written later, from the confirmed code (`write-cards`).
