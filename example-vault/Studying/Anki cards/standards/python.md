# Python addendum

- Solutions match `ruff format`/Black. Checked files pass `ruff check` and run on Python ≥ 3.10, stdlib only; `tests:` are plain asserts run in the card's namespace; concept `code:` is imported, so it must run.
- The starter shows the full annotated signature; hints are read, not typed.
- Comments: elision `# ...`, header `# src/<path>  (<role>)`, hint `# uses: ...`, stubs `# stubs (real: src/<file>)`.
- Good gaps: comprehensions, `dict.get`/`setdefault`/`Counter`, `with`, `pathlib`, `dataclass` fields, `itertools`, `match`, `raise ... from e`.
- Good predict/what-if cards: mutable defaults, late-binding closures, `is` vs `==`, shallow copies, un-awaited coroutines.
- Third-party libraries go in the `_ext` file.
