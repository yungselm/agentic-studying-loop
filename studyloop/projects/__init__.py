"""Code projects (deck kind `project`): cards from code you write in a repo. Start here.

    asl init -> connect.py   the deck folder, and the study-loop block in the project's CLAUDE.md
    asl mode -> connect.py   how the agent works in the project (the text: modes/<mode>.md)
    asl lint -> lint.py      this module's lint rule: headers, verbatim excerpts, `std:`, drift

    templates/   deck.yaml, Overview.md, profile.md and card files of a new project deck
"""
from __future__ import annotations

from pathlib import Path

from studyloop.core.registry import Command, DeckKind, Module, Registry

PROJECT = DeckKind(
    "project", what="code in a repo",
    skills="the mode in the project's CLAUDE.md, write-cards, study-note",
    card_types=("code", "concept", "timeline", "cloze"),
    detect=lambda d: bool(d.cfg.get("repo")) or (d.path / "profile.md").is_file(),
    frame_required=True)


def _init_args(p):
    p.add_argument("project", type=Path)
    p.add_argument("--home", type=Path, required=True)
    p.add_argument("--pack", required=True)
    p.add_argument("--prefix", required=True, help="card id prefix, e.g. omk")
    p.add_argument("--mode", default="mentor")
    p.add_argument("--notes", help="vault folder with this project's study notes")
    p.add_argument("--name", help="deck name (default: project folder name)")


def _init(a):
    from studyloop.projects.connect import init_project
    init_project(a.project, a.home, a.pack, a.prefix, a.mode, a.notes, a.name)
    return 0


def _mode_args(p):
    p.add_argument("mode")
    p.add_argument("project", type=Path, nargs="?", default=Path("."))


def _mode(a):
    from studyloop.projects.connect import set_mode
    set_mode(a.project, a.mode)
    return 0


def register(reg: Registry) -> None:
    from studyloop.projects.lint import RULE
    reg.add_deck_kind(PROJECT)
    reg.add_lint_rule(RULE)
    reg.add_command(Command("init", "connect a project: deck folder + CLAUDE.md block", _init_args, _init))
    reg.add_command(Command("mode", "switch the mode in a project's CLAUDE.md", _mode_args, _mode))


MODULE = Module("projects", register)
