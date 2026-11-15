"""Analyses of your own review data (`asl stats`, skill `refresh-standards`).

  analysis    what an analysis gets (Data: the cards and reviews tables) and returns (Section)
  table       the export -> one row per Anki card, joined to its card file by GUID
  bundled     the analyses that ship with the tool
  report      `asl stats`: runs them; report (for you), summary (for the agent), cards.csv

A new analysis: a class with `name`, `order` and `run(data) -> Section | None`, registered by
its module with `reg.provide("analysis", name, obj)` (see bundled.py).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from ..core.registry import Command, Module, Registry


def _stats_args(p):
    p.add_argument("export")
    p.add_argument("--deck", help="only this deck and its subdecks")
    p.add_argument("--home", type=Path, help="card home (default: search upwards from cwd)")
    p.add_argument("--only", help="comma-separated analyses to run, e.g. code-size,leeches")
    p.add_argument("--mark-refreshed", action="store_true",
                   help="record this export as the baseline for the next refresh")


def _stats(a):
    from .report import stats
    only = [x.strip() for x in a.only.split(",") if x.strip()] if a.only else None
    return stats(Path(a.export), a.deck, a.home, a.mark_refreshed, only)


def register(reg: Registry) -> None:
    reg.add_command(Command("stats", "analyse a manual Anki export (.apkg/.colpkg)", _stats_args,
                            _stats))
    if importlib.util.find_spec("pandas") is None:
        return                      # registering must never fail: `asl stats` names the install
    from .bundled import BUNDLED
    for a in BUNDLED:
        reg.provide("analysis", a.name, a)


MODULE = Module("analysis", register, skills=("refresh-standards",), extra="analysis",
                needs=("pandas",))
