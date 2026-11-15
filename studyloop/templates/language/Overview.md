---
type: overview
scope: anki
project: "{{name}}"
goal: {{goal}}
level: {{level}}                 # current level (JLPT / CEFR); grammar above it counts as unknown
gloss_language: {{gloss}}        # target words are glossed in this language
known_from: []                   # Anki exports that seed Vocabulary.md (`asl lang seed`)
grammar_gate: learning           # vocabulary waits for grammar: learning | planned | off
notes: {{notes}}                 # Vocabulary.md and Grammar/ live here
sources: []
---
# {{name}}

Branch: **language** (skill `language-cards`; cards: sentence, grammar). Lines and their status:
`lines/*.tsv`; known words: `Vocabulary.md`; grammar: `Overview - {{name}} Grammar.md`.
