"""Run every card's code through its pack's checker (compile / lint / tests).

    asl check path/to/deck [files...]

Each pack has a `checker.py` with

    def run(items: list[Item], workdir: Path, opts: dict) -> int   # 0 = all good

Items are code-card solutions (with their `tests:`) and concept-card `code:`
examples. Files marked `check: false` in deck.yaml (code that needs third-party
libraries, or fragments) and cards with `check: false` are skipped.
"""
from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import cards as C
from .config import Deck, load_pack


@dataclass
class Item:
    name: str        # unique identifier-safe name, e.g. sol_tasklog_tsk_001
    label: str       # human label: "tsk-001 Parse a ... (tasklog.yaml)"
    kind: str        # "solution" | "example"
    code: str
    tests: str = ""


def _ident(s: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", s.lower())).strip("_")


def collect(groups: list[tuple[Deck, list[Path]]]) -> tuple[dict[str, list[Item]], int]:
    by_pack: dict[str, list[Item]] = {}
    skipped = 0
    for deck, files in groups:
        for f in files:
            if not deck.checked(f):
                skipped += 1
                continue
            for card in C.load_file(f):
                pack = card.get("lang") or deck.file_opts(f).get("pack") or deck.pack
                if not pack or card.get("check") is False:
                    continue
                tag = _ident(str(card.get("id") or f"{f.stem}_{card['_index']}"))
                lbl = f"{C.label(card)} ({f.name})"
                if card["type"] == "code" and card.get("solution"):
                    by_pack.setdefault(pack, []).append(
                        Item(f"sol_{tag}", lbl, "solution", card["solution"],
                             card.get("tests") or ""))
                elif card["type"] != "code" and card.get("code"):
                    by_pack.setdefault(pack, []).append(
                        Item(f"ex_{tag}", lbl, "example", card["code"]))
    return by_pack, skipped


def load_checker(pack_dir: Path):
    spec = importlib.util.spec_from_file_location(f"asl_checker_{pack_dir.name}",
                                                  pack_dir / "checker.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cache_dir(pack: str) -> Path:
    base = os.environ.get("ASL_CACHE") or (
        os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    d = Path(base) / "agentic-studying-loop" / "check" / pack
    d.mkdir(parents=True, exist_ok=True)
    return d


def check(groups, opts: dict) -> int:
    by_pack, skipped = collect(groups)
    if skipped:
        print(f"Skipped {skipped} file(s) marked `check: false` in deck.yaml.")
    if not by_pack:
        print("Nothing to check.")
        return 0
    rc = 0
    for pack, items in by_pack.items():
        cfg = load_pack(pack)
        if not (cfg["_dir"] / "checker.py").is_file():
            print(f"[{pack}] no checker in this pack; {len(items)} block(s) not checked.")
            continue
        print(f"\n[{pack}] checking {len(items)} block(s)")
        rc |= load_checker(cfg["_dir"]).run(items, cache_dir(pack), {**cfg, **opts})
    print("\n✓ All checks passed." if rc == 0 else "\n✗ Problems above (labels name the cards).")
    return rc
