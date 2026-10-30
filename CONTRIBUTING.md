# Contributing

```bash
git clone https://github.com/yungselm/agentic-studying-loop && cd agentic-studying-loop
uv venv && uv pip install -e ".[dev]"
ruff check studyloop tests && pytest -q tests
asl lint -q examples/python-core examples/rust-core "example-vault/Studying/Anki cards/tasklog"
asl check examples/python-core examples/rust-core "example-vault/Studying/Anki cards/tasklog"
```

Layout: the installable tool is `studyloop/` (engine, `packs/`, `standards/`, `modes/`,
`templates/`, `anki/`). `skills/` and `.claude-plugin/` are the Claude Code plugin and are also
shipped with the tool for `asl install-skills`. `examples/` and `example-vault/` are documentation
and test fixtures.

Most wanted: new packs (docs/writing-a-pack.md), card types, better stats heuristics, and evidence
from your own reviews (open an issue with your `asl stats` report's tables; no card text needed).
Keep markdown for agents short: every line in a mode or skill costs context in every session that
loads it.
