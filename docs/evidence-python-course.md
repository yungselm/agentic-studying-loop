# Evidence: a programming course deck

A second check of the code and concept card standards (core.md §2–3), on a different subject,
learner setting and grading style than the Rust deck they were first measured on.

## Data

One learner's deck for a university course (Advanced Python, 2025, final grade 6/6):
**767 cards** studied, **2,760 review answers**, May to October 2025.
- 565 front/back cards (concepts, tooling, "what does this return"), often with screenshots
- 71 type-in cards: write the code or command
- 41 cloze and 90 image occlusion cards (too few to model)

**Fail** means *Again* on a review-phase answer. Odds ratios (OR) come from a logistic regression
with standard errors clustered by note, controlling for the review's position (the 1st, 2nd…
review of the card), since hard cards collect more reviews.

**Read with care:** every interval stayed under a week (a one-semester deck), so this measures
short-term retention. The interval itself can't be a factor: failed cards get short intervals.

## Results

| Factor | Raw fail rate | Adjusted | Verdict |
|---|---|---|---|
| Typed code vs flip card | 35% vs 18% | OR 2.2 [1.7–2.9] at equal answer length | **replicates** the Rust deck (20% vs 11%) |
| Typed answer length | ≤20 chars 27%, 20–50 34%, 50–100 36% | OR 1.43 per doubling [1.18–1.74] | **replicates**: typing is the cost |
| Flip-card answer length (text answers) | 13–19%, no trend | OR 1.06 [0.91–1.24] | **no effect** (the medical deck: 1.05, weak) |
| Question form, flip cards | contrast (*when X? X vs Y?*) 6%, *what is* 20% | contrast OR 0.30 [0.12–0.77]; *why* 0.83, *how* 0.78 (n.s.) | **contrast holds** (66 cards) |
| Context shown on a typed card (screenshot) | 29% vs 42% | OR 0.65 [0.34–1.26] once CLI cards are held | same direction as the context-frame rule, not significant |
| CLI commands (git, poetry) vs code | | OR 1.5 [0.8–3.0] | n.s.; tooling trivia already avoided |
| Card kind, raw | cloze 15%, occlusion 13%, flip 18% | not modelled | too few cloze cards |

Leeches (≥ 4 lapses): 25, two patterns.
- **15 ask for exact code or commands**, 13 of them with no code shown
  (`np.unique(…, return_counts=True)`, `pd.timedelta_range(freq="150min")`, 6 git commands):
  the Rust deck's leech pattern again.
- **10 ask for an enumeration**: ISO 25010's 8 characteristics, the Agile Manifesto's values,
  `ax.scatter()`'s parameters, "what is L in SOLID".

## What it changed

| Evidence | In the tool |
|---|---|
| Typing cost replicates on a second language and learner | typed-chars limits stay; core.md §1 lists both decks |
| Contrast questions fail least | core.md §3: prefer *when X instead of Y?* for concept cards |
| Exact API recall without context is a leech pattern | supports the existing context-frame and `// uses:` rules |
| Enumerations are the other leech pattern | supports §3's "no *name the N…*"; the ISO 25010 cloze (8 sentence-long gaps) failed too, so §4's short gaps apply |
| Image occlusion | left out: quick to make by hand, hard to generate from notes |

## Limitations

- **Short intervals only**: nothing here says how these cards hold over months.
- **Question forms are classified by keywords**; 188 cards matched no form.
- **Grading may differ by form:** a contrast answer may be graded more leniently than an exact
  definition.
