# Language cards (design)

Status: **design, not implemented.** Roadmap §3. Test case: port *Terrace House OND 1* (962
subs2srs notes, Japanese) into the new card types.

## Principles

1. **Grammar first, in real speech.** A grammar point is learned from a native sentence (audio +
   screenshot), as in the Game Gengo Grammar deck. Words come after.
2. **One new word per sentence (i+1).** A vocabulary card is a native sentence in which exactly one
   word is unknown; only that word is translated.
3. **Listen first.** The front shows no text.
4. **Ground truth in the vault.** Known words and grammar points live in the notes vault, are
   updated from Anki reviews, and decide which sentence becomes a card when.
5. **Native audio over TTS.** TTS is a fallback, tagged, and measured.
6. **Opt-in.** Language tooling is an install extra and a separate skill; code users never load it.

## Evidence (the author's Japanese decks, 2020–26)

Fail = *Again* on a review answer. Observational data, small samples; to be re-measured on the
new cards with `asl stats`.

| Deck / card kind | Reviews | Fail | Median time |
|---|---|---|---|
| Game Gengo Grammar (screenshot + audio, whole-sentence translation) | 1,322 | 13% | 11 s |
| Shirokuma (video clip), sentence with 0 glossed words | 1,084 | 9.5% | 12 s |
| Shirokuma, **1** glossed word | 1,728 | 20% | 13 s |
| Shirokuma, 2+ glossed words | 350 | 23% | 16–19 s |
| JLPT Tango N5, isolated words (suspended after) | 84 | 25% | 6 s |
| Terrace House (text visible on the front, Meaning = copy of the sentence in 920/962) | 123 | 40% | 15 s |

- **Each extra unknown word costs** fail rate and time → i+1 as a hard rule.
- **Length:** Game Gengo sentences > 30 characters fail 17% vs 9% at 11–20 → length cap (lint).
- **Second card per note:** Game Gengo has Listening + Reading cards for every note (fail 13.8%
  vs 12.6%). A card fails less when its sibling was reviewed since its own last review, in every
  interval bucket: ≤ 7 d 7.5% vs 9.5% (n = 734), 8–30 d 8.4% vs 13% (n = 173), > 30 d 21% vs 29%
  (n = 415). Same direction as the Staatsdeck cloze result (2–5 gaps per note beat 1,
  [evidence](evidence-cloze-cards.md)). Cost: a second card per note.

## Card types

### `grammar` (Game Gengo structure)

- **Front:** screenshot + audio. No text.
- **Back:** grammar point + meaning (title) · sentence with furigana/reading aid, the pattern
  highlighted · **whole-sentence translation**, the matching part highlighted · collapsible
  *Grammar*: vault note, book page or URL.
- **Cards per note:** listening + reading (text front) by default. Grammar notes are few (≈ 300
  for JLPT N5–N3) and the sibling effect above is consistent. `deck.yaml: cards: [listen]`
  turns the reading card off; `asl stats` re-checks the effect on the new deck.

```yaml
- type: grammar
  text: 死んじゃいけないよ
  pattern_text: 死んじゃいけない      # highlighted span in text
  grammar: "[[ちゃいけない]]"
  translation: "You **must not** die."
  audio: th1-0042.mp3
  image: th1-0042.jpg
  source: "Terrace House OND 1 · 00:12:34"
```

### `sentence` (vocabulary)

- **Front:** screenshot + audio. No text.
- **Back:** sentence with reading aid, **target word highlighted** · target word: dictionary
  form, reading, gloss of **the sense used here** (not the whole dictionary entry) · **no
  sentence translation** · collapsible *Grammar*: the grammar points detected in the sentence.
- **Cards per note:** listening only (thousands of notes: the second card's time cost
  dominates).

```yaml
- type: sentence
  text: いやいや 困るよ
  target: 困る                 # surface form in text
  lemma: 困る
  reading: こまる
  gloss: in Schwierigkeiten sein
  grammar: ["[[よ (Satzende)]]"]
  audio: th1-0042.mp3
  image: th1-0042.jpg
  source: "Terrace House OND 1 · 00:12:34"
```

### Decks

```
日本語
├── Grammar                 two cards per note, sequential (book / level order), ~5–10 new/day
└── Vocabulary              one card per note, high new/day
    ├── Terrace House OND 1     one subdeck per media source (= one card file)
    └── …
```

Separate decks: grammar can be studied first and at its own pace. The vocabulary preset sets
Anki's *new card gather order* to ascending position, so the planner's global order holds
across the source subdecks.

**Lint:** exactly one target; target occurs in `text`; length cap (from the pack, e.g. 30
characters for Japanese); audio and image exist; `grammar` links resolve; TTS audio tagged.

## A language is a topic

`asl topic "Italienisch" --lang it --sources <grammar book.pdf> --sources <media folder> …`. The
`study-source` skill asks for the brief, one question at a time, and writes it into the deck's
`Overview.md` frontmatter:

| Field | Question |
|---|---|
| `goal` | e.g. "follow Montalbano without subtitles", "JLPT N3" |
| `language`, `gloss_language` | target language; language of the glosses |
| `level` | current level (JLPT / CEFR / HSK / TOPIK); grammar above it is unknown |
| `known_from` | Anki exports that seed `Vocabulary.md` (once) |
| `sources` | grammar sources and media sources (below) |
| `media_dir` | folder **outside the vault** for videos, clips, screenshots |

### Grammar sources → `Grammar/` notes

- **Book PDF** (e.g. *Praxis-Grammatik Italienisch*, bought by the user): `asl sources` maps
  chapters to parts; the agent reads one part per batch (`--read`) and writes one note per
  grammar point with level, explanation, `source: "[[Book.pdf#page=N]]"`.
- **Website:** URL source, `parts: ["#anchor"]` for long pages.
- **Existing deck** (Game Gengo): its points, levels and links become notes.

Each grammar note gets a **`pattern:`** (match rule over lemma/part-of-speech sequences),
written once by the agent and tested on the source's examples. Detection over thousands of
subtitle lines is then plain code; the agent only confirms lines that become cards.

**The book gives which points, in which order, and why; media gives the sentence.** For each
point (in the book's order) the planner looks for a media line using it with nothing else
unknown → `grammar` card with native audio. None found → the book's example + TTS, no image
(`audio: tts`), or wait for more media.

### Media sources → `lines/<source>.tsv`

The user provides one of:

| Input | User is responsible for |
|---|---|
| Existing mined deck (`.apkg` from subs2srs, movies2anki, asbplayer, Language Reactor) | — |
| Video + subtitles with the same basename (`e01.mkv`, `e01.ja.srt`) | subtitles in the target language, in sync; **images without subtitles** |
| Audio + timed transcript (podcast) | timing (later: Whisper) |

`asl lang add <source>` writes the clips and screenshots into `media_dir` and one row per line
into the deck's `lines/<source>.tsv` (text only, in the vault). The agent reads the text, never
the media.

```
id        start        end          text                  audio         image         status
th1-0042  00:12:34.10  00:12:36.02  いやいや 困るよ        th1-0042.mp3  th1-0042.jpg  ready:困る
th1-0043  00:12:36.50  00:12:40.11  料理の専門学校 辞めて  th1-0043.mp3  th1-0043.jpg  parked:2 words
```

**Lines with two speakers are split** (19% of Terrace House lines): speaker labels mark the
text split; the audio is cut at the silence nearest the character-proportional point (ffmpeg
`silencedetect`). No clear silence → keep the line whole.

## Ground truth

```
<notes folder>/
├── Vocabulary.md     lemma | reading | level | status | card id | first source   (asl-maintained, editable)
└── Grammar/          one note per grammar point (level, pattern, explanation, examples, cards)
<card home>/<deck>/
├── deck.yaml         lang: ja, cards: [...], media_dir
├── Overview.md       brief + sources map + card index
├── lines/            one .tsv per media source
└── *.yaml            cards: one file per grammar part / media source
```

Status per word and grammar point: `unknown → planned → learning → known` (mature ≥ 21 d),
plus `ignored` (names, speaker labels, interjections). `asl lang sync <export.apkg>` updates it
from reviews.

### Word levels

Every word gets a `level`, written by `asl lang plan` (editable by hand):

1. **On a level list** (JLPT, CEFR, HSK, TOPIK; from `lang.yaml`): that level, e.g. `N4`.
2. **Not listed, in the frequency data:** estimated from its frequency rank, with bands
   calibrated on the listed words (an unlisted word as common as the median N3 word → `~N3`).
   `~` marks an estimate.
3. **In neither** (slang, show-specific, rare): `—`, ordered last, unless it occurs in ≥ 3 lines
   of the user's media: then it counts as the current level (the show will keep repeating it).

Level is a **priority, not a gate**: it orders the ready cards (planner step 3), it never parks
a line. Learning words in level order gets you speaking sooner; a lower-level word missing from
the media doesn't hold back the rest.

## The planner (`asl lang plan`)

1. Tokenize and lemmatize each line; drop `ignored` tokens.
2. Per line: unknown words (planned counts as known: Anki introduces new cards in order) and
   unknown grammar points (only `learning` / `known` count: grammar sits in its own deck and
   may not be studied yet).
3. Loop: lines with exactly one unknown word and no unknown grammar → order the words by
   level (current level and below first, then upwards; `—` last), then frequency in the user's
   media, then general frequency → best line per word (shortest) → mark planned → recompute.
   A line with three unknown words becomes ready once two of them are planned elsewhere.
4. The rest is `parked:<reason>`, re-planned after every sync.

The grammar phase runs the same loop over grammar points (vocabulary relaxed: the back has a
full translation). Only `ready` lines become cards and only built cards enter Anki: the deck
grows at the front instead of being reordered (Anki keeps a new card's position once imported).

## Tools (per language in `studyloop/langs/<code>/lang.yaml`)

| Step | Japanese | Others |
|---|---|---|
| Tokenize / lemmatize | fugashi + UniDic | spaCy / stanza; jieba (zh), kiwi (ko) |
| Dictionary | JMdict (English, German glosses) | Wiktionary (kaikki.org dumps) |
| Frequency | wordfreq + frequency in the user's media | wordfreq |
| Word levels | JLPT lists (N5–N1) | CEFR lists (e.g. Kelly lists: Italian and 8 others), HSK, TOPIK |
| Clips / screenshots | ffmpeg | ffmpeg |
| No subtitles | faster-whisper | faster-whisper |
| TTS fallback | VOICEVOX | Piper / edge-tts |

**Packaging:** `uv tool install "agentic-studying-loop[lang]"` (Python deps); ffmpeg external;
`asl lang setup <code>` downloads dictionary, tokenizer data and frequency lists into a cache.
The `language-cards` skill ships in its own plugin in the same marketplace. The repo ships
tools, never content (book pages, Game Gengo images, JLPT Sensei text stay with the user).

## Milestones

1. **Import + plan report, no cards:** `asl lang add` for an `.apkg`, speaker-label cleanup and
   split, tokenizer, `Vocabulary.md` seeded from the author's exports (Shirokuma glosses,
   Game Gengo), `asl lang plan` report: ready / parked by reason on Terrace House. Count the
   low-quality lines (single words, fillers, fragments) and the `~` / `—` levels; a quality
   filter is designed from those numbers in a second step.
2. **Card types** `sentence` and `grammar`: templates, lint, build; first ~50 Terrace House
   cards by the agent; review on the phone.
3. **Grammar ground truth:** `Grammar/` from Game Gengo, `pattern:` detection, grammar links,
   grammar gate for vocabulary.
4. **Sync loop:** `asl lang sync`, re-plan, stats (fail by unknown words, length, audio kind,
   sibling card).
5. **New media:** video + subtitles → clips, subtitle retiming, Whisper and TTS fallbacks.
6. **Second language:** Italian from *Praxis-Grammatik Italienisch* + media, proving the
   book → grammar notes → media sentence path.

## Decisions

- Images are the user's responsibility (no subtitle check: tokens).
- Clips and videos live outside the vault (`media_dir`).
- The brief is gathered by the agent's questions, as for other topics.
- Grammar cards: whole-sentence translation; vocabulary cards: target word only.
- Multi-speaker lines are split.
- Word level orders the cards but never blocks one; unlisted words get a frequency estimate.
- Two cards per note for grammar (few, intense); one for vocabulary (mass immersion).
- The Terrace House port starts fresh (its 123 reviews were a test run).
