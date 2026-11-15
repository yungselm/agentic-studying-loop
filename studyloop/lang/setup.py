"""A language's config (`<code>.yaml` next to this file), its download cache, and `asl lang setup`
(level lists, dictionary, grammar lists: everything a language needs once)."""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def lang_config(code: str) -> dict:
    p = HERE / f"{code}.yaml"
    if not p.is_file():
        have = ", ".join(sorted(q.stem for q in HERE.glob("*.yaml")))
        raise SystemExit(f"No language config for '{code}' (have: {have})")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cfg["code"] = code
    return cfg


def cache_dir(code: str) -> Path:
    base = os.environ.get("ASL_CACHE") or os.environ.get("XDG_CACHE_HOME") or (
        os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None)
    root = Path(base) if base else Path.home() / ".cache"
    d = (root if os.environ.get("ASL_CACHE") else root / "asl") / "lang" / code
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup(code: str, force: bool = False) -> int:
    """Download the level lists into the cache."""
    cfg = lang_config(code)
    lists = (cfg.get("levels") or {}).get("lists") or {}
    d = cache_dir(code)
    for level, url in lists.items():
        out = d / f"level_{level}.csv"
        if out.exists() and not force:
            print(f"  {level}: cached ({out})")
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "agentic-studying-loop"})
        with urllib.request.urlopen(req, timeout=60) as r:
            out.write_bytes(r.read())
        print(f"  {level}: downloaded → {out}")
    if credit := (cfg.get("levels") or {}).get("credit"):
        print(f"  ({credit})")
    from .dictionary import setup_dictionary
    from .overview import fetch_lists
    setup_dictionary(cfg, force)
    fetch_lists(cfg, force)
    try:
        import wordfreq  # noqa: F401
    except ImportError:
        print("  ! wordfreq missing: pip install wordfreq (frequency estimates are skipped)")
    return 0
