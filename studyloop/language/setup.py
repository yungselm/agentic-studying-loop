"""Find a language (deck.yaml `lang:`) among the installed language modules; its download cache;
`asl lang setup <code>` (everything a language needs once: level lists, dictionary, ...)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from studyloop.language.base import Language


def get_language(code: str) -> Language:
    from studyloop.core.registry import registry
    reg = registry()
    langs = reg.provided("language")
    if code not in langs:
        raise SystemExit(f"No language '{code}' installed (have: {', '.join(sorted(langs)) or 'none'})")
    module, lang = langs[code]
    missing = reg.missing(module)
    if missing:
        raise SystemExit(f"{lang.name} needs the `{module.extra}` install (missing: {', '.join(missing)}): "
                         f'pip install "agentic-studying-loop[{module.extra}]"')
    return lang


def lang_config(code: str) -> dict:
    """The language's `<code>.yaml`, with `code` set."""
    return get_language(code).config


def cache_dir(code: str) -> Path:
    base = os.environ.get("ASL_CACHE") or os.environ.get("XDG_CACHE_HOME") or (
        os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None)
    root = Path(base) if base else Path.home() / ".cache"
    d = (root if os.environ.get("ASL_CACHE") else root / "asl") / "lang" / code
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup(code: str, force: bool = False) -> int:
    get_language(code).setup(force)
    return 0
