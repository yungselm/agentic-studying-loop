# Contributing

```bash
pip install -e ".[dev]"
ruff check studyloop packs tests && pytest -q tests
asl lint examples/python-core examples/rust-core "example-vault/Studying/Anki cards/tasklog"
asl check examples/python-core examples/rust-core "example-vault/Studying/Anki cards/tasklog"
```

Most wanted: new packs (docs/writing-a-pack.md), card types, better stats heuristics, and
evidence from your own reviews (open an issue with your `asl stats` report's tables; no card text
needed). Keep markdown for agents short: every line in a mode or skill costs context in every
session that loads it.
