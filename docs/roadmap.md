# Roadmap

## Now (in order, one at a time)

### 1. Study notes worth reopening (done)
One idea per note; TL;DR + Mermaid diagram on the first screen; details folded; typed links
and an overview map (`study-note` skill). `asl notes` checks them (in CI for the example vault).
Length is a default (~250 words, lectures ~800), raised per note with `budget:`.
- [ ] Upgrade a few real vault notes, tune the rules from that (`preferences.md` → *Notes*).

### 2. Lecture cards (medicine), built on the author's AnKing history
The author's Staatsexamen deck (45k notes; 10.7k cards with 88k reviews, 2020–21) is the
evidence. First signals, review fail rate: cloze answers ≤ 10 chars 5–6% vs 20–80 chars ~9%
(the code cards' finding again: answer size predicts failure); cloze 5–8% vs basic 9–11%;
2–5 clozes per note beat 1; radiology/derm worst (11–12%), so image occlusion matters.
- [ ] `asl stats` reads foreign note types (cloze, basic, image occlusion) with their measures;
  the report becomes the baseline for `standards/medicine.md`.
- [ ] Card types `cloze` and `occlusion` (+ `basic` for image → diagnosis); a `med` pack whose
  checker lints instead of compiling.
- [ ] Lecture input: slides (PDF/PPTX) → study note → cards, `source: lecture.pdf#p12`.
- [ ] Reuse before writing: match a lecture against the 34k unstudied AnKing notes, propose
  "unsuspend these, write those".
- Open: first subject and language; unsuspend in the existing profile or copy into an `asl`
  deck; a newer export (~15k cards studied)? Media (4.2 GB) stays local, never committed.

### 3. Language cards
Collect the author's inputs and favourite sets first, then design. Starting ideas: a sentence
card (cloze/translation, audio, screenshot); a subtitle miner (`.srt` → i+1 sentences); stats
on sentence length, word frequency, unknown words. AnKing's term → definition cards (9.8% fail)
show where plain vocab cards struggle.

## Later
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
