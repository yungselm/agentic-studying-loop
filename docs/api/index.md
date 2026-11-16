# API

**Using `asl`:** [Commands](cli.md) lists every command and option; [Card format](../card-format.md)
is what goes in `deck.yaml` and the card files.

**Working on the code:** for collaborators. `studyloop` is a small core and modules that plug into it. Each module's
`__init__.py` is its entry point: what it is for, which command enters where (`asl x -> file.py`)
and one line per file. The pages below show those entry points; open the file in the repo and go
from there.

Rule: modules import core, core never imports a module (checked by `lint-imports`).

```{toctree}
:maxdepth: 1

cli
../card-format
core
registry
notes
sources
projects
language
analysis
```
