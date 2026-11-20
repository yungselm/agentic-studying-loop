# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""`asl` — the agentic-studying-loop command line."""
from __future__ import annotations

import argparse
import contextlib
import sys
import textwrap


def _utf8_stdout() -> None:
    """Windows consoles and pipes may default to cp1252; never crash on ✓ or →."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    _utf8_stdout()
    from studyloop.core.cards import CardFileError
    try:
        return _main(argv)
    except CardFileError as e:
        print(f"! {e}", file=sys.stderr)
        return 1


def examples(p: argparse.ArgumentParser, text: str) -> None:
    """Usage examples under a command's options: in `asl <cmd> -h` and on the docs site.

    Examples
    --------
    >>> examples(p, '''
    ...     asl lint -q decks/tasklog      # only problems
    ... ''')
    """
    p.epilog = "examples:\n" + textwrap.indent(textwrap.dedent(text).strip(), "  ")
    p.formatter_class = argparse.RawDescriptionHelpFormatter


def build_parser(reg) -> argparse.ArgumentParser:
    """Every command comes from a registered module (core's first). Also used by the docs."""
    ap = argparse.ArgumentParser(prog="asl", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for _module, cmd in reg.commands.values():
        cmd.arguments(sub.add_parser(cmd.name, help=cmd.help))
    return ap


def _main(argv=None) -> int:
    from studyloop.core.registry import registry
    reg = registry()
    a = build_parser(reg).parse_args(argv)
    module, cmd = reg.commands[a.cmd]
    missing = reg.missing(module)
    if missing:
        raise SystemExit(f"`asl {cmd.name}` needs the `{module.extra}` install "
                         f"(missing: {', '.join(missing)}): "
                         f"pip install \"agentic-studying-loop[{module.extra}]\"")
    return cmd.run(a)


if __name__ == "__main__":
    sys.exit(main())
