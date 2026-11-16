"""Writes api/cli.md at build time: every `asl` command and option, read from the real parser
(`studyloop.core.cli.build_parser`), so the page never drifts from the code."""
from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

INTRO = """# Commands

Every `asl` command with its options, generated from the code at each docs build.
A command from an optional module says which install it needs. `asl <command> -h` prints the
same in the terminal.
"""


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _name(action: argparse.Action) -> str:
    if not action.option_strings:
        return f"`{action.metavar or action.dest}`"
    metavar = ""
    if action.nargs != 0:
        metavar = " " + (action.metavar or action.dest.upper())
    return ", ".join(f"`{o}{metavar}`" for o in action.option_strings)


def _rows(parser: argparse.ArgumentParser) -> list[str]:
    fmt = parser._get_formatter()
    rows = []
    for action in parser._actions:
        if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        help_ = fmt._expand_help(action) if action.help else ""
        extra = []
        if action.choices:
            extra.append("one of " + ", ".join(f"`{c}`" for c in action.choices))
        if action.default not in (None, False, argparse.SUPPRESS, [], "") and action.nargs != 0 \
                and "default" not in help_:
            extra.append(f"default `{action.default}`")
        if action.required and action.option_strings:
            extra.append("required")
        text = "; ".join(x for x in [help_, *extra] if x)
        rows.append(f"| {_name(action)} | {_cell(text)} |")
    return rows


def _command(parser: argparse.ArgumentParser, title: str, level: int, out: list[str],
             help_: str = "", note: str = "") -> None:
    out += [f"{'#' * level} `{title}`", ""]
    if help_:
        out += [help_[0].upper() + help_[1:] + ".", ""]
    if note:
        out += [note, ""]
    usage = parser.format_usage().removeprefix("usage: ").strip()
    out += ["```text", " ".join(usage.split()), "```", ""]
    rows = _rows(parser)
    if rows:
        out += ["| Argument | What it does |", "|---|---|", *rows, ""]
    if parser.epilog:                                # set by studyloop.core.cli.examples
        text = textwrap.dedent(parser.epilog.removeprefix("examples:\n"))
        out += ["Examples:", "", "```bash", text.rstrip(), "```", ""]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            helps = {a.dest: a.help for a in action._choices_actions}
            for name, child in action.choices.items():
                _command(child, f"{title} {name}", level + 1, out, helps.get(name) or "")


def write(path: Path, mock_modules: list[str]) -> None:
    from sphinx.ext.autodoc.mock import mock

    with mock(mock_modules):                         # optional installs: commands still listed
        from studyloop.core.cli import build_parser
        from studyloop.core.registry import registry
        reg = registry()
        ap = build_parser(reg)
    sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
    out = [INTRO]
    by_module: dict[str, list] = {}
    for module, cmd in reg.commands.values():
        by_module.setdefault(module.name, []).append((module, cmd))
    for name, cmds in by_module.items():
        module = cmds[0][0]
        out += [f"## {name.capitalize()}", ""]
        note = (f"Needs the `{module.extra}` install: "
                f"`pip install \"agentic-studying-loop[{module.extra}]\"`.") if module.extra else ""
        for _m, cmd in cmds:
            _command(sub.choices[cmd.name], f"asl {cmd.name}", 3, out, cmd.help, note)
    text = "\n".join(out).rstrip() + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
