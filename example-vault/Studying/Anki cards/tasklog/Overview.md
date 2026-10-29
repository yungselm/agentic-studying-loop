---
type: overview
scope: anki
project: "Tasklog"
---
# Tasklog: card index

Every card has a row. Status: `draft` → `reviewed` → `needs update` (code it mirrors changed).

**Code reference:** cards mirror the tasklog example as shipped with agentic-studying-loop v0.1.0.

## Persistence (`store.py`) · note: [[Atomic file writes]]

| id | status | type | from (file → function) |
|---|---|---|---|
| tsk-001 | reviewed | code | store.py → Store.save |
| tsk-002 | reviewed | code | store.py → Store.load |
| tsk-003 | reviewed | concept | store.py → Task |
| tsk-004 | draft | timeline | store.py → Store.save |

## Command line (`cli.py`)

| id | status | type | from (file → function) |
|---|---|---|---|
| tsk-005 | draft | code (ext) | cli.py → list_tasks |
