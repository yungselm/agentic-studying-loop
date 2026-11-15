# Contributing

```bash
git clone https://github.com/yungselm/agentic-studying-loop && cd agentic-studying-loop
uv venv && uv pip install -e ".[dev]"
ruff check studyloop tests && pytest -q tests
asl lint -q examples/python-core examples/rust-core "example-vault/Studying/Anki cards/tasklog"
asl check examples/python-core examples/rust-core "example-vault/Studying/Anki cards/tasklog"
```

Layout ([architecture](docs/architecture.md)): the installable tool is `studyloop/`: `core/` is the
engine (card files, lint, build, check, packs, standards, Anki templates) and the other packages
are modules that plug into it (`core/registry.py`: deck kinds, card types, lint rules, commands).
A module is listed under `[project.entry-points."studyloop.modules"]` in `pyproject.toml`; after
adding or renaming one, run `uv sync` (or reinstall) so `asl` finds it. `skills/` and
`.claude-plugin/` are the Claude Code plugin and are also shipped with the tool for
`asl install-skills`. `examples/` and `example-vault/` are documentation and test fixtures.

Most wanted: new packs (docs/writing-a-pack.md), card types, analyses of review data
(`studyloop/analysis/`: a class with `run(data) -> Section`), and evidence
from your own reviews (open an issue with your `asl stats` report's tables; no card text needed).
Keep markdown for agents short: every line in a mode or skill costs context in every session that
loads it.
