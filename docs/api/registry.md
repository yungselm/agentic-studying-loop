# Registry

What a module plugs in, and how `asl` loads the modules. A module is a package with a
`MODULE = Module(...)` in its `__init__.py`, listed under
`[project.entry-points."studyloop.modules"]` in `pyproject.toml` (then `uv sync`).

```{eval-rst}
.. automodule:: studyloop.core.registry
   :members: Module, DeckKind, CardType, Flag, CodeBlock, Template, LintContext, NoteContext, LintRule, DeckSummary, Command, Registry, registry, load
   :member-order: bysource
```

## Command examples

```{eval-rst}
.. autofunction:: studyloop.core.cli.examples
```

