---
type: concept
topic: files
project: Tasklog
updated: 2026-10-29
tags: [python, files]
---
# Atomic file writes

## The idea in two sentences
Never write the real file in place: write a temporary file next to it, then swap it in with one
`os.replace`. Readers (and a crash) see either the old file or the new one, never half of each.

## How it works
1. Build the full content in memory (`json.dumps`).
2. `tempfile.mkstemp(dir=target.parent)` creates a unique temp file **on the same file system**.
3. Write and close it.
4. `os.replace(tmp, target)`: a rename, which the OS performs atomically within one file system.

## In this project
`Store.save()` in `src/tasklog/store.py` does exactly these four steps.

## Pitfalls
- A temp file in `/tmp` may sit on another file system; then `os.replace` fails or isn't atomic.
- `os.rename` refuses to overwrite on Windows; `os.replace` overwrites everywhere.
- After a crash a stray `*.tmp` can remain; harmless, but clean it up on start if it matters.

## Related
[[Context managers]]
