"""Study notes in the vault (skill `study-note`). Start here.

    asl notes -> check.py    checks notes against the style: TL;DR, a diagram, the word
                             budget, links, overviews. Notes are optional: cards build without them.
"""
from __future__ import annotations

from pathlib import Path

from studyloop.core.registry import Command, Module, Registry


def _notes_args(p):
    p.add_argument("inputs", nargs="*", help="folders or .md files (default: from ./CLAUDE.md)")
    p.add_argument("--vault", type=Path, help="vault root for links (default: the card home's "
                   "`vault:`, else the folder with .obsidian)")
    p.add_argument("-q", "--quiet", action="store_true", help="only print problems (!)")
    p.add_argument("--budget", type=int, default=250,
                   help="visible prose words per note before a hint (default 250)")


def _notes(a):
    from studyloop.notes.check import notes
    return notes(a.inputs, a.vault, a.quiet, a.budget)


def register(reg: Registry) -> None:
    reg.add_command(Command("notes", "check study notes: tl;dr, diagram, budget, links", _notes_args,
                            _notes))


MODULE = Module("notes", register, skills=("study-note",))
