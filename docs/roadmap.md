# Roadmap

## Next
- More packs: TypeScript (tsc + vitest), Go, C++. Each needs a checker and a standards addendum.
- `asl stats --share`: an anonymised summary (bins and counts only) to pool evidence across learners.
- A drag-to-order front for timeline cards (today: labelled A–E, answer is the order).
- Migrate rust-lang-kata to the engine (see migrating-from-rust-lang-kata.md).

## Natural languages
The loop is the same; the card types and measures differ.
- **Sentence card** type: target sentence with a cloze or translation prompt, optional audio
  clip and screenshot.
- **Subtitle miner** (`packs/lang-<code>/`): `.srt` (+ video via ffmpeg) → candidate sentences
  ranked by unknown-word count (i+1), agent picks and annotates.
- Measures for `asl stats`: sentence length, word frequency rank, number of unknown words, audio
  length; the report bins them like typed characters today.
- Modes map naturally: "teacher" explains grammar first, "on-demand" only cards what you mark.
