# Evidence: cloze cards

What the `cloze` card type and its standards (core.md §4) are based on, and what the data did
not support.

## Data

One learner's deck for the German medical licensing exam (Staatsexamen, 2020–21): 45k notes,
of which **10,636 cards** were studied, with **53,059 review answers** (88k answers including
learning steps). Two sources are mixed in:
- **AnKing** (English, USMLE): cloze notes, many with Sketchy/Pixorize scene mnemonics.
- **The learner's own cards** (German): front/back cards, clozes, image occlusion.

**Fail** means *Again* on a review-phase answer. Intervals are Wilson 95% CIs. Odds ratios (OR)
come from a logistic regression over review answers with standard errors clustered by note:
- *cloze model:* gap length (log₂), gaps per note, image sharing, source, language, question direction
- *front/back model:* answer length, image sharing, language, direction

These are observational data, not a trial: cards were not assigned to formats at random.

## Results

| Factor | Raw fail rate | Adjusted | Verdict |
|---|---|---|---|
| Card kind | cloze 7.6%, front/back 9.6%, occlusion 4.6% | cloze OR 0.82 [0.70–0.96] | **holds** |
| Gap length (this card's answer) | ≤10 chars 5.5%, 10–20 7.1%, 20–40 8.8%, 40–80 8.9%, >80 8.9% | OR 1.11 per doubling (p < 0.001) | **holds**; plateau after 40 chars, time keeps rising (7.6 s → 17.7 s) |
| Gaps per note | 1: 8.3%, 2: 5.5%, 3: 7.5%, 4–5: 6.2%, 6–8: 7.3%, >8: 8.2% | 2–5 vs 1: OR 0.66 [0.57–0.77]; 6+: 0.73 | **holds** |
| Front/back answer length | ≤20 chars 7.3%, 20–50 8.6%, >50 9.7–10.3% | OR 1.05 per doubling | **holds** (weaker than for cloze) |
| List answers (front/back) | 10.2% vs 8.6% | OR 1.10 [0.98–1.25] once length is held | length explains it |
| Direction (front/back, keyword-classified) | findings → name 10.0%, name → findings 8.4% | OR 1.51 [1.15–1.98] | **holds**; and **no reverse cards existed** |
| Image on the card | none 9.1%, image 7.9–8.3% | all ORs 0.89–1.08, CIs include 1 | **no effect** |
| Same image on 2–4 / 5–9 / ≥10 notes (shared scene) | own cards 8.8 / 10.3 / 8.9% vs no image 9.4% | n.s. | **no effect** |
| Ready-made scene (Sketchy/Pixorize tag) | 6.8% vs 7.7% | OR 0.97 [0.83–1.14] once gap length is held | **no effect** (its gaps are shorter) |
| Mnemonic named in the note | 10.1% vs 8.4% | not modelled | sits on harder facts, no verdict |
| Language (German vs English) | cloze: 8.4% vs 7.4% | cloze OR 1.17 [0.95–1.43] | tracks author and source, not language: **no rule** |

Leeches (≥ 4 lapses): 139 of 10,636, half cloze and half front/back. Their gaps were slightly
longer than average (median 22 vs 19 chars), and they had images no more often than other cards.

## Corrections

A first pass counted shared images per *card*. A cloze note with one image and three gaps
produces three cards with the same image, so "image shared by 2–4 cards" mostly measured
"2–4 gaps per note". Counted per *note*, the scene effect disappears. The learner's experience
with scene videos (Meditricks) may still be real, but it can't be read from review logs: the
learning happens while watching the video, and the review only sees a pasted screenshot.

## What it changed

| Evidence | In the tool |
|---|---|
| Short answers fail less; time rises with length | `asl lint`: gap ≤ 20 chars, max 80 (`limits.cloze`) |
| 2–5 gaps per note beat 1 | `asl lint` hint `[gaps]` on single-gap notes |
| Findings → name is harder and was never carded | Anki asks each gap with the others shown, so gapping the name gives that direction (core.md §4) |
| Cloze beats front/back for facts | facts from notes become `cloze`; *why* questions stay `concept` |
| Scenes and mnemonics unproven | `hook:` is optional and tagged `asl::hook`; `asl stats` reports fail rates with and without one |
| Language doesn't matter | no language field or rule |

## Limitations

- **One learner, one exam, two years.** Treat these as defaults; `refresh-standards` re-measures
  them on each user's own reviews.
- **Direction is classified by keywords**, which matched 1,587 cards; the rest are unclassified.
- **Source and topic are confounded:** AnKing covers USMLE topics, the own cards cover German
  exam topics.
