# Benchmark: cost and card quality

What does it cost to turn a book chapter into cards, per model and effort, and does the
workflow make better cards than just asking? Measured in November 2026 with Claude Code on a
subscription plan; costs are what the runs would have cost at API list price.

## Setup

- **Chapters:** *The Rust Programming Language* ch. 4 (ownership) and ch. 10 (generics, traits,
  lifetimes) as code topics; two chapters of a coronary imaging textbook (qualitative OCT,
  16 images; the concept of FFR) as topics with figures. Sources the author knows well enough
  to judge the cards.
- **Models:** Haiku 5.5 and Sonnet 5.5 at medium effort; Opus 5.5 at low, medium and high effort.
- **Three ways to make cards:**
  - **plain prompt:** the chapter and a one-paragraph request ("write Anki cards into
    `cards.tsv`"). No asl, no skills.
  - **skills workflow:** a card home, the `study-source` and `write-cards` skills and `asl`; the
    agent reads the skills, the standards and the sources map, then works on its own.
  - **asl prompt:** the same card home, no skills; the prompt is `asl prompt <deck>`: brief, card
    counts, rules, format, the chapter's text and figures, then `asl finish`.
- **Runs:** headless (`claude -p`), each in a fresh folder and a clean Claude Code config (no
  CLAUDE.md, memory or other skills). Tokens and cost come from Claude Code's own usage report.
- **Rating:** the author rated cards blind on a page that renders them as Anki does (code cards
  with the editor), 1 (useless or wrong) to 5 (exactly what I'd want): 5 random cards per model,
  way and kind of chapter, mixed. A later session re-rated 20 cards to measure drift.

## Results

<!-- benchmark:begin -->

### Cost, tokens, turns and cards

Per chapter: the mean over the four chapters of each chapter's median run.

```{image} _static/benchmarks/cost-light.svg
:class: only-light
:alt: Cost and cards per chapter by model and arm
```
```{image} _static/benchmarks/cost-dark.svg
:class: only-dark
:alt: Cost and cards per chapter by model and arm
```

| model, effort | arm | $ / chapter | tokens | turns | cards | cards passing lint |
|---|---|---|---|---|---|---|
| Haiku, medium | plain prompt | $0.02 | 265k | 6 | 46 | – |
| Haiku, medium | skills workflow | $0.03 | 742k | 18 | 35 | all |
| Haiku, medium | asl prompt | $0.03 | 359k | 12 | 32 | all |
| Sonnet, medium | plain prompt | $0.22 | 191k | 6 | 64 | – |
| Sonnet, medium | skills workflow | $0.36 | 535k | 16 | 44 | all |
| Sonnet, medium | asl prompt | $0.24 | 107k | 5 | 29 | all |
| Opus, low | plain prompt | $0.26 | 104k | 4 | 50 | – |
| Opus, low | skills workflow | $0.41 | 276k | 12 | 29 | all |
| Opus, low | asl prompt | $0.43 | 144k | 3 | 32 | all |
| Opus, medium | plain prompt | $0.51 | 181k | 6 | 66 | – |
| Opus, medium | skills workflow | $0.91 | 783k | 24 | 40 | all |
| Opus, medium | asl prompt | $0.56 | 186k | 6 | 32 | all |
| Opus, high | plain prompt | $0.77 | 344k | 8 | 80 | – |
| Opus, high | skills workflow | $1.12 | 1011k | 26 | 40 | all |
| Opus, high | asl prompt | $0.77 | 232k | 8 | 33 | all |

60 runs, $26.54 at API list price.

### Card quality

```{image} _static/benchmarks/quality-light.svg
:class: only-light
:alt: Mean rating by arm and by model
```
```{image} _static/benchmarks/quality-dark.svg
:class: only-dark
:alt: Mean rating by arm and by model
```

| | mean rating ± 95% interval | rated |
|---|---|---|
| plain prompt | 3.54 ± 0.27 | 50 |
| skills workflow | 3.49 ± 0.20 | 100 |
| asl prompt | 3.32 ± 0.24 | 50 |
| Haiku, medium | 3.27 ± 0.29 | 40 |
| Sonnet, medium | 3.33 ± 0.34 | 40 |
| Opus, low | 3.58 ± 0.30 | 40 |
| Opus, medium | 3.45 ± 0.33 | 40 |
| Opus, high | 3.67 ± 0.25 | 40 |

**Re-rating.** Cards rated again, blind, in a later session:

- pilot cards: 10 re-rated, mean 3.80 → 3.50 (-0.30), same score 6 of 10.
- v2 cards: 10 re-rated, mean 3.30 → 3.10 (-0.20), same score 8 of 10.

The rater's scale drifted by 0.2–0.3 between sessions and a single card's score can move by up to three points, so differences below about 0.3 between arms are noise.

<!-- benchmark:end -->

## What it means

- **A plain prompt works:** a strong model reading a chapter writes decent cards, and card for
  card they were rated the same as asl's. What a plain prompt doesn't give is control, and that
  is what asl adds:
  - **how many cards:** with `asl prompt` the count follows the chapter's length and the brief
    (46–53 cards for Rust ch. 10 on every model; a plain prompt gave 59 to 121), and fewer cards
    of the same quality mean fewer reviews for years;
  - **cards that follow the standards:** size limits, one idea per card, gaps that can't be
    guessed, the user's own rules; `asl finish` checked every card, and all 20 `asl prompt` runs
    passed (a plain prompt's cards are whatever it writes);
  - **the right kinds of card:** typed code cards that compile and pass their tests, cloze and
    concept cards, the book's figures, stable ids so a re-import updates cards in place.
- **Tokens:** `asl prompt` uses about as many as a plain prompt, and a quarter to a half of the
  skills workflow's. Costs follow: a third below the skills workflow on Sonnet
  and on Opus at medium and high effort, and about what a plain prompt costs there. Opus at low
  effort is the exception: its plain prompt is the cheapest run of all ($0.26; it writes once
  and stops), while with `asl prompt` it also runs the checks and fixes what they find ($0.43,
  the same as the skills workflow). Turns, not output, drive the cost: the workflow's agent explores (reads the
  standards, asl's own code) for 12–26 turns; with `asl prompt` it writes, runs `asl finish`,
  and is done in 3–12.
- **Model:** Opus rates a little above Sonnet and Haiku; effort makes no difference to quality,
  only to cost. Opus at low effort is the best value; Sonnet the budget option.

**Limits:** one rater who knows the material (and saw similar cards repeatedly); one run per
chapter and setup; coverage of the chapter was not measured. The study-loop skills' own fixes
during the benchmark (figures on cards, no guessable gaps) came in between the two batches.

## Reproduce

The runner, the rating page and this report are in
[`benchmarks/`](https://github.com/yungselm/agentic-studying-loop/tree/master/benchmarks).
Sources with private paths (the textbook) go in a gitignored `tasks.local.yaml`; card text,
transcripts and sources stay on your machine, only numbers are committed.

```bash
claude setup-token                          # runs on your plan; the token goes in ~/.claude_bench_token
uv run python benchmarks/run.py --check     # a clean config: no CLAUDE.md, memory or other skills
uv run python benchmarks/run.py --batch mine          # every task x setup x arm
uv run python benchmarks/rate.py mine                 # rate blind at http://127.0.0.1:8765
uv run --extra bench python benchmarks/report.py      # charts, tables, this page and the README
                                                      # (its ARMS names the batch per arm)
```
