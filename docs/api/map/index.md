# Code map

Each module's entry point (its `__init__.py`): what it is for, which command enters where
(`asl x -> file.py`) and one line per file. Open the module in the repo and go from there.

Rule: modules import core, core never imports a module (checked by `lint-imports`).

```{toctree}
:maxdepth: 1

core
notes
sources
projects
language
analysis
```
