---
type: project-profile
project: "Tasklog"
repo: "examples/tasklog"
---
# Tasklog: project profile

What an agent needs to write cards that look like this repo.

**Study notes:** `Studying/Tasklog/` (start at `Overview - Tasklog.md`)

## File roles

The location header of every code card uses the role from this table:
`# <path>  (<role>)`. Add a row the first time a card uses a file.

| File | Role (header text) |
|---|---|
| `src/tasklog/store.py` | persistence: load/save the task list as JSON |
| `src/tasklog/cli.py` | command line: typer app, one function per command |

## Project-specific rules

- Python ≥ 3.10, standard library only in `store.py`; `typer` only in `cli.py`, so cli cards go in
  `tasklog_ext.yaml`.
