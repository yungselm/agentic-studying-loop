# Writing a pack

A pack teaches the engine one language. It is a folder in `packs/` (or in a folder listed in the
`ASL_PACKS` environment variable):

```
packs/go/
├── pack.yaml      required
├── mode.js        CodeMirror 5 mode (syntax highlighting in the card editor)
├── checker.py     optional: compile / lint / test the cards
└── standards.md   addendum to standards/core.md (formatting, comment syntax, gotchas)
```

## pack.yaml

```yaml
name: go
codemirror_mode: go            # the name the mode registers (CodeMirror.defineMode("go", ...))
mode_file: mode.js
standards: standards.md
lint:                          # used by `asl lint`
  comment_prefix: '//'         # elisions, location headers, `uses:` hints
  frame: '^\s*(func|type)\b'    # a line that counts as the context frame
  comment: '//[^\n]*'
  string: '"((?:[^"\\]|\\.)*)"'
  ignore_messages: 'panic\(\s*"(?:[^"\\]|\\.)*"\s*\)'
# anything else is passed to the checker as `opts`
```

Most CodeMirror 5 modes are in the `codemirror@5` npm package under `mode/<lang>/<lang>.js`.
Modes built on `defineSimpleMode` work too (`_simple.js` is always loaded).

## checker.py

```python
def run(items, workdir, opts) -> int:   # 0 = everything passed
    ...
```

- `items`: objects with `name` (identifier-safe, unique), `label` (card id + front, for error
  messages), `kind` (`"solution"` or `"example"`), `code`, `tests`.
- `workdir`: a persistent cache folder for this pack (keeps incremental builds fast).
- `opts`: `pack.yaml` plus `{"fast": bool}` (skip slow linters).

Generate one project with every card isolated (a module per card), run the linter and the tests,
print what failed with the card's label. See `packs/rust/checker.py` and `packs/python/checker.py`.

## standards.md

Keep it short: formatter, edition/version, comment syntax for elisions / location headers /
`uses:` hints / stubs, where third-party code goes, and language-specific card shapes that work.
