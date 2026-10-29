---
type: concept
topic: python
updated: 2026-10-29
tags: [python, context-managers]
---
# Context managers

## The idea in two sentences
`with x as y:` calls `x.__enter__()` (its result becomes `y`), runs the body, and always calls
`x.__exit__(...)` afterwards, also when the body raised. That makes cleanup impossible to forget.

## How it works
1. evaluate `x` (e.g. `open(p)` creates the file object)
2. `y = x.__enter__()`
3. run the body
4. `x.__exit__(exc_type, exc, tb)`; a truthy return value would swallow the exception

## Pitfalls
- `__exit__` returning `True` hides errors; file objects return `False`.
- `contextlib.contextmanager` turns a generator into a context manager: code before `yield` is
  `__enter__`, code after it (in `finally`) is `__exit__`.

## Related
[[Atomic file writes]]
