"""`asl` — the agentic-studying-loop command line."""
from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from . import config


def _utf8_stdout() -> None:
    """Windows consoles and pipes may default to cp1252; never crash on ✓ or →."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    _utf8_stdout()
    ap = argparse.ArgumentParser(prog="asl", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build an .apkg from deck folders / card files")
    b.add_argument("inputs", nargs="*")
    b.add_argument("-o", "--out", default="asl-output/cards.apkg")

    c = sub.add_parser("check", help="compile / lint / test card code with each pack's checker")
    c.add_argument("inputs", nargs="*")
    c.add_argument("--fast", action="store_true", help="skip the linter (clippy / ruff)")

    li = sub.add_parser("lint", help="ids, size limits, self-containment (no code is run)")
    li.add_argument("inputs", nargs="*")
    li.add_argument("-q", "--quiet", action="store_true", help="only print problems (!)")

    i = sub.add_parser("ids", help="next free id and cards without one (read-only)")
    i.add_argument("inputs", nargs="*")
    i.add_argument("--fix", action="store_true", help="same as `asl fix`")

    fx = sub.add_parser("fix", help="write missing ids, std versions and Overview.md rows")
    fx.add_argument("inputs", nargs="*")

    s = sub.add_parser("stats", help="analyse a manual Anki export (.apkg/.colpkg)")
    s.add_argument("export")
    s.add_argument("--deck", help="only this deck and its subdecks")
    s.add_argument("--home", type=Path, help="card home (default: search upwards from cwd)")
    s.add_argument("--mark-refreshed", action="store_true",
                   help="record this export as the baseline for the next refresh")

    h = sub.add_parser("init-home", help="create a card home in your vault")
    h.add_argument("home", type=Path)
    h.add_argument("--pack", action="append", default=[])

    p = sub.add_parser("init", help="connect a project: deck folder + CLAUDE.md block")
    p.add_argument("project", type=Path)
    p.add_argument("--home", type=Path, required=True)
    p.add_argument("--pack", required=True)
    p.add_argument("--prefix", required=True, help="card id prefix, e.g. omk")
    p.add_argument("--mode", default="mentor")
    p.add_argument("--notes", help="vault folder with this project's study notes")
    p.add_argument("--name", help="deck name (default: project folder name)")

    m = sub.add_parser("mode", help="switch the mode in a project's CLAUDE.md")
    m.add_argument("mode")
    m.add_argument("project", type=Path, nargs="?", default=Path("."))

    k = sub.add_parser("install-skills", help="copy skills to a .claude/skills folder")
    k.add_argument("target", type=Path, nargs="?", default=Path.home() / ".claude" / "skills")

    sub.add_parser("packs", help="list available packs")

    a = ap.parse_args(argv)
    if a.cmd == "build":
        from .build import build
        return build(config.resolve_inputs(a.inputs), Path(a.out))
    if a.cmd == "check":
        from .check import check
        return check(config.resolve_inputs(a.inputs), {"fast": a.fast})
    if a.cmd == "lint":
        from .lint import lint
        return lint(config.resolve_inputs(a.inputs), a.quiet)
    if a.cmd in ("ids", "fix"):
        from .ids import ids
        return ids(config.resolve_inputs(a.inputs), a.cmd == "fix" or a.fix)
    if a.cmd == "stats":
        from .stats import stats
        return stats(Path(a.export), a.deck, a.home, a.mark_refreshed)
    if a.cmd == "init-home":
        from .project import init_home
        init_home(a.home, a.pack)
        return 0
    if a.cmd == "init":
        from .project import init_project
        init_project(a.project, a.home, a.pack, a.prefix, a.mode, a.notes, a.name)
        return 0
    if a.cmd == "mode":
        from .project import set_mode
        set_mode(a.project, a.mode)
        return 0
    if a.cmd == "install-skills":
        from .project import install_skills
        install_skills(a.target)
        return 0
    if a.cmd == "packs":
        for d in config.all_packs():
            print(f"{d.name:12} {d}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
