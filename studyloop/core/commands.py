"""Core's `asl` commands: build, check, lint, ids, fix, init-home, install-skills, packs."""
from __future__ import annotations

from pathlib import Path

from studyloop.core import config
from studyloop.core.registry import Command


def _inputs(p):
    p.add_argument("inputs", nargs="*", help="deck folders or single card files (default: the current folder)")


def _build_args(p):
    _inputs(p)
    p.add_argument("-o", "--out", default="asl-output/cards.apkg", help="the .apkg to write")


def _build(a):
    from studyloop.core.engine.build import build
    return build(config.resolve_inputs(a.inputs), Path(a.out))


def _check_args(p):
    _inputs(p)
    p.add_argument("--fast", action="store_true", help="skip the linter (clippy / ruff)")


def _check(a):
    from studyloop.core.engine.check import check
    return check(config.resolve_inputs(a.inputs), {"fast": a.fast})


def _lint_args(p):
    _inputs(p)
    p.add_argument("-q", "--quiet", action="store_true", help="only print problems (!)")
    p.add_argument("--skip", default="", help="comma-separated kinds to leave out, e.g. size,frame")


def _lint(a):
    from studyloop.core.engine.lint import lint
    return lint(config.resolve_inputs(a.inputs), a.quiet,
                frozenset(k.strip() for k in a.skip.split(",") if k.strip()))


def _ids_args(p):
    _inputs(p)
    p.add_argument("--fix", action="store_true", help="same as `asl fix`")


def _ids(a):
    from studyloop.core.cards.ids import ids
    return ids(config.resolve_inputs(a.inputs), a.cmd == "fix" or getattr(a, "fix", False))


def _init_home_args(p):
    p.add_argument("home", type=Path, help="the new card home folder (holds studyloop.yaml and the decks)")
    p.add_argument("--pack", action="append", default=[], help="a pack whose standards addendum to copy in; repeat for more (`asl packs` lists them)")
    v = p.add_mutually_exclusive_group()
    v.add_argument("--vault", type=Path, help="your notes folder (Obsidian or any markdown); "
                   "cards link into it")
    v.add_argument("--no-vault", action="store_true", help="no notes folder: cards only")


def _init_home(a):
    from studyloop.core.config.home import init_home
    init_home(a.home, a.pack, "none" if a.no_vault else a.vault)
    return 0


def _install_skills_args(p):
    p.add_argument("target", type=Path, nargs="?", default=Path.home() / ".claude" / "skills",
                   help="skills folder (default: ~/.claude/skills)")


def _install_skills(a):
    from studyloop.core.config.home import install_skills
    install_skills(a.target)
    return 0


def _packs(a):
    for d in config.all_packs():
        print(f"{d.name:12} {d}")
    return 0


COMMANDS = (
    Command("build", "build an .apkg from deck folders / card files", _build_args, _build),
    Command("check", "compile / lint / test card code with each pack's checker", _check_args, _check),
    Command("lint", "ids, size limits, self-containment (no code is run)", _lint_args, _lint),
    Command("ids", "next free id and cards without one (read-only)", _ids_args, _ids),
    Command("fix", "write missing kind, ids, std versions, Overview.md rows and sources map",
            _inputs, _ids),
    Command("init-home", "create a card home (in your vault, if you keep one)", _init_home_args,
            _init_home),
    Command("install-skills", "copy skills to a .claude/skills folder", _install_skills_args,
            _install_skills),
    Command("packs", "list available packs", lambda p: None, _packs),
)
