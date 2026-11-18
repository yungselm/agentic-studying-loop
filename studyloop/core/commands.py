"""Core's `asl` commands: build, check, lint, ids, fix, finish, init-home, install-skills, packs."""
from __future__ import annotations

from pathlib import Path

from studyloop.core import config
from studyloop.core.cli import examples
from studyloop.core.registry import Command


def _inputs(p):
    p.add_argument("inputs", nargs="*", help="deck folders or single card files (default: the current folder)")


def _build_args(p):
    _inputs(p)
    p.add_argument("-o", "--out", default="asl-output/cards.apkg", help="the .apkg to write")
    examples(p, """
        asl build "Anki cards/tasklog" -o tasklog.apkg     # one deck
        asl build "Anki cards/tasklog" "Anki cards/CS231n" -o study.apkg
        asl build "Anki cards/tasklog/_examples.yaml"      # preview an example file
    """)


def _build(a):
    from studyloop.core.engine.build import build
    return build(config.resolve_inputs(a.inputs), Path(a.out))


def _check_args(p):
    _inputs(p)
    p.add_argument("--fast", action="store_true", help="skip the linter (clippy / ruff)")
    examples(p, """
        asl check examples/python-core            # run every solution against its tests
        asl check --fast "Anki cards/omakase"     # compile and test, skip clippy
    """)


def _check(a):
    from studyloop.core.engine.check import check
    return check(config.resolve_inputs(a.inputs), {"fast": a.fast})


def _lint_args(p):
    _inputs(p)
    p.add_argument("-q", "--quiet", action="store_true", help="only print problems (!)")
    p.add_argument("--skip", default="", help="comma-separated kinds to leave out, e.g. size,frame")
    examples(p, """
        asl lint -q "Anki cards/tasklog"          # prints OK, or only the problems
        asl lint "Anki cards/CS231n/lecture_03.yaml"
        asl lint --skip size,frame "Anki cards/omakase"
    """)


def _lint(a):
    from studyloop.core.engine.lint import lint
    return lint(config.resolve_inputs(a.inputs), a.quiet,
                frozenset(k.strip() for k in a.skip.split(",") if k.strip()))


def _ids_args(p):
    _inputs(p)
    p.add_argument("--fix", action="store_true", help="same as `asl fix`")
    examples(p, """
        asl ids "Anki cards/tasklog"              # next free id: tsk-012; cards without one
    """)


def _fix_args(p):
    _inputs(p)
    examples(p, """
        asl fix "Anki cards/tasklog"              # after writing cards: ids, std, Overview.md rows
        asl fix "Anki cards/CS231n"               # a topic: also refreshes the sources map
    """)


def _ids(a):
    from studyloop.core.cards.ids import ids
    return ids(config.resolve_inputs(a.inputs), a.cmd == "fix" or getattr(a, "fix", False))


def _finish_args(p):
    _inputs(p)
    p.add_argument("-o", "--out", help="the .apkg to write (default: <card home>/<deck>.apkg)")
    p.add_argument("--fast", action="store_true", help="check without the linter (clippy / ruff)")
    examples(p, """
        asl finish "Anki cards/rust_book"         # fix, lint, check, then Anki cards/rust_book.apkg
    """)


def _finish(a):
    """The end of every batch in one call: fix, lint -q, check; build only when all pass."""
    from studyloop.core.cards.ids import ids
    from studyloop.core.engine.build import build
    from studyloop.core.engine.check import check
    from studyloop.core.engine.lint import lint
    groups = config.resolve_inputs(a.inputs)
    ids(groups, True)
    groups = config.resolve_inputs(a.inputs)          # ids and std are in the files now
    print("== lint")
    if lint(groups, True, frozenset()):
        print("finish: fix the problems (!) above, then run `asl finish` again; nothing built.")
        return 1
    print("== check")
    if check(groups, {"fast": a.fast}):
        print("finish: `asl check` failed (above); fix the cards, then run `asl finish` again; "
              "nothing built.")
        return 1
    out = Path(a.out) if a.out else groups[0][0].path.parent / f"{groups[0][0].path.name}.apkg"
    print("== build")
    return build(groups, out)


def _init_home_args(p):
    p.add_argument("home", type=Path, help="the new card home folder (holds studyloop.yaml and the decks)")
    p.add_argument("--pack", action="append", default=[], help="a pack whose standards addendum to copy in; repeat for more (`asl packs` lists them)")
    v = p.add_mutually_exclusive_group()
    v.add_argument("--vault", type=Path, help="your notes folder (Obsidian or any markdown); "
                   "cards link into it")
    v.add_argument("--no-vault", action="store_true", help="no notes folder: cards only")
    examples(p, """
        asl init-home "~/Notes/Anki cards" --vault ~/Notes --pack python --pack rust
        asl init-home ~/anki-cards --no-vault     # cards only
    """)


def _init_home(a):
    from studyloop.core.config.home import init_home
    init_home(a.home, a.pack, "none" if a.no_vault else a.vault)
    return 0


def _install_skills_args(p):
    p.add_argument("target", type=Path, nargs="?", default=Path.home() / ".claude" / "skills",
                   help="skills folder (default: ~/.claude/skills)")
    examples(p, """
        asl install-skills                        # for every project
        asl install-skills .claude/skills         # for this project only
    """)


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
            _fix_args, _ids),
    Command("finish", "end of a batch: fix, lint, check, then build the deck's .apkg",
            _finish_args, _finish),
    Command("init-home", "create a card home (in your vault, if you keep one)", _init_home_args,
            _init_home),
    Command("install-skills", "copy skills to a .claude/skills folder", _install_skills_args,
            _install_skills),
    Command("packs", "list available packs", lambda p: examples(p, "asl packs   # cpp, python, rust and your own"),
            _packs),
)
