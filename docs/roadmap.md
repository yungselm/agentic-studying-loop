# Roadmap

## Next
- **Documentation on Read the Docs**: move the docs (card format, packs, standards, the agent
  workflow) from `docs/` into a hosted site, with the README as the short entry point.
- **Merge the standards (~Dec 2026)**: after a month of reviews on the omakase cards (and later other
  projects), fold the author's personal standards back into the generic `core.md`, based on that data.
  Then the card home keeps only `preferences.md` and per-deck profiles, and `core.md` becomes a
  managed copy (`asl standards --update`).
- Publish on PyPI, so the install becomes `uv tool install agentic-studying-loop`.
- More packs: TypeScript (tsc + vitest), Go, C++. Each needs a checker and a standards addendum.
- `asl stats --share`: an anonymised summary (bins and counts only) to pool evidence across learners.
- A drag-to-order front for timeline cards (today: labelled A–E, answer is the order).

## Natural languages
The loop is the same; the card types and measures differ.
- **Sentence card** type: target sentence with a cloze or translation prompt, optional audio
  clip and screenshot.
- **Subtitle miner** (a `lang-<code>` pack): `.srt` (+ video via ffmpeg) → candidate sentences
  ranked by unknown-word count (i+1), agent picks and annotates.
- Measures for `asl stats`: sentence length, word frequency rank, number of unknown words, audio
  length; the report bins them like typed characters today.
- Modes map naturally: "teacher" explains grammar first, "on-demand" only cards what you mark.
