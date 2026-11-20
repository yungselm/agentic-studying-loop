# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Analyses of your own review data (`asl stats`, skill `refresh-standards`). Start here.

    asl stats -> report.py   reads the export, runs every analysis, writes the report (for you),
                             the summary (for the agent) and cards.csv

    types.py      what an analysis gets (Data: the cards and reviews tables) and returns
                  (Section, Suggestion), and the base class `Analysis`
    table.py      the export -> one row per Anki card, joined to its card file by GUID
    analyses/     the analyses that ship with the tool, one section of the report each

A new analysis: a class with `name`, `order` and `run(data) -> Section | None` (see
analyses/), registered with `reg.provide("analysis", name, obj)`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from studyloop.core.cli import examples
from studyloop.core.registry import Command, Module, Registry


def _stats_args(p):
    p.add_argument("export", help="a manual Anki export (.apkg or .colpkg) with scheduling data")
    p.add_argument("--deck", help="only this deck and its subdecks")
    p.add_argument("--home", type=Path, help="card home (default: search upwards from cwd)")
    p.add_argument("--only", help="comma-separated analyses to run, e.g. code-size,leeches")
    p.add_argument("--mark-refreshed", action="store_true",
                   help="record this export as the baseline for the next refresh")
    examples(p, """
        asl stats ~/Downloads/collection.colpkg                    # report + agent summary
        asl stats deck.apkg --deck "Study Loop::Tasklog"          # one deck and its subdecks
        asl stats deck.apkg --only code-size,leeches
        asl stats deck.apkg --mark-refreshed      # after the standards were updated from it
    """)


def _stats(a):
    from studyloop.analysis.report import stats
    only = [x.strip() for x in a.only.split(",") if x.strip()] if a.only else None
    return stats(Path(a.export), a.deck, a.home, a.mark_refreshed, only)


def register(reg: Registry) -> None:
    reg.add_command(Command("stats", "analyse a manual Anki export (.apkg/.colpkg)", _stats_args,
                            _stats))
    if importlib.util.find_spec("pandas") is None:
        return                      # registering must never fail: `asl stats` names the install
    from studyloop.analysis.analyses import BUNDLED
    for a in BUNDLED:
        reg.provide("analysis", a.name, a)


MODULE = Module("analysis", register, skills=("refresh-standards",), extra="analysis",
                needs=("pandas",))
