---
name: language-cards
description: Make one-new-word sentence cards (audio + screenshot, target word glossed) and grammar cards from a show, a mined deck or a grammar book, with the known words tracked in the user's vault. Use when the user studies a language (Japanese, Italian, ...) and asks for language cards, or adds an episode or a deck.
---
# Language cards

Design and rules: `docs/language-cards.md` in the agentic-studying-loop repo. Needs `asl` with
the `lang` extra and, once per language, `asl lang setup <code>` (word lists, dictionary).

1. **New language?** Ask one question at a time: the goal, the gloss language, the current level
   (JLPT/CEFR), which Anki exports show what they know, grammar sources (book PDF, URL, deck),
   and a media folder **outside** the vault. Then write `deck.yaml` (`lang`, `prefix`,
   `media_dir`, presets: vocabulary `{order: sequential, gather: position}`) and the brief in
   `Overview.md` (`goal`, `gloss_language`, `level`, `known_from`, `notes`), and run
   `asl lang seed <deck>`.
2. **New media:** `asl lang add <deck> <video> --title "<Show Ep>" --key <short>` (subtitles
   `.srt`/`.ass` next to it, or `--subs`), or a mined `.apkg` (`--video` to re-cut from the video).
   Images and subtitles are the user's job; never open media files.
3. **Plan:** `asl lang plan <deck>`. Tell the user in two lines: ready cards, parked, skipped.
4. **Draft:** `asl lang draft <deck> -n 20` (more only when asked). It prints each card's line and
   dictionary senses. Fill only `gloss:` in the card file: **the sense used in that line**, in
   the gloss language, a few words; slang → say so `(Slang)`; a set phrase (はじめまして) → gloss
   the phrase. Fix the target's reading/furigana if it is wrong. Leave every other field.
5. **Grammar:** `asl lang grammar <deck> <game-gengo.apkg>` once (`--fresh`: all unknown), then
   `asl lang grammar <deck>` lists rules that miss their own examples. Fix each in its note
   (`Grammar/<point>.md`): `pattern` regex covering conjugations and casual forms, or `token`
   `surface/pos/pos2` for particles; set `rule: agent`. A rule that would match inside other
   words (`さ`, `間`) is too broad: tighten it. Cannot be found in a line → `detect: false`.
   Cards without native audio (book examples, decks without clips): `asl lang tts <deck>`.
6. **Finish:** `asl lint <deck>` (fix every `!`), then `asl build <deck> -o "<card home>/<deck>.apkg"`.
   Report the ids and the `.apkg` path (import: "Update notetypes" ticked).
7. **After studying:** the user exports from Anki (with scheduling); `asl lang sync <deck>
   <export.apkg>` moves words and grammar to learning/known and re-plans. Tell the user what
   was released and the fail rate per source.
8. **Rejected cards:** the user deletes a card from the file; the next plan marks its line
   `rejected` and plans the word elsewhere. Ids are never reused. Never set a word `ignored`
   yourself: the user edits `Vocabulary.md`.
