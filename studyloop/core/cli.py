"""`asl` — the agentic-studying-loop command line."""
from __future__ import annotations

import argparse
import contextlib
import sys


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
