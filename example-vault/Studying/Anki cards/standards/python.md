# Python addendum

Read after `core.md`; `preferences.md` wins over both.

- **Formatting:** solutions match `ruff format` / Black (4 spaces, double quotes, trailing commas
  in multi-line calls). Match the repo's formatter for project cards.
- **Checked files** pass `ruff check` (rules in `pack.yaml`) and run on Python ≥ 3.10 with the
  standard library only; `tests:` are plain `assert` statements executed in the card's namespace.
  Concept `code:` examples are imported, so they must run without errors or side effects beyond
  printing.
- **Type hints in signatures.** The starter shows the full annotated signature
  (`def parse(line: str) -> tuple[str, str] | None:`); hints are read, not typed.
- **Comments:** elisions `# ...`, location header `# src/<path>  (<role>)`, hints `# uses: ...`,
  stubs under `# stubs (real: src/<file>)`.
- **Classic gap targets:** comprehensions, `dict.get`/`setdefault`/`collections.Counter`,
  `with` blocks, `pathlib`, `dataclass` fields, `itertools`, f-string formatting, `match` statements,
  exception chaining (`raise ... from e`).
- **Gotchas make good predict/what-if cards:** mutable default arguments, late-binding closures in
  loops, `is` vs `==`, shallow copies, integer caching, `async` functions that are never awaited.
- **Third-party libraries** (`requests`, `pandas`, `numpy`, frameworks…) go in the `_ext` file
  (`check: false`).
