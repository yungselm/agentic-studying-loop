"""Packs: one programming language each (checker, CodeMirror mode, standards addendum).
Bundled in core/packs/; your own in the folders of the ASL_PACKS environment variable."""
from __future__ import annotations

import os
from pathlib import Path

from studyloop.core.config.paths import PKG, _read_yaml


def pack_dirs() -> list[Path]:
    dirs = [Path(d) for d in os.environ.get("ASL_PACKS", "").split(os.pathsep) if d]
    return dirs + [PKG / "packs"]


def find_pack(name: str) -> Path:
    for d in pack_dirs():
        if (d / name / "pack.yaml").is_file():
            return d / name
    raise SystemExit(f"Unknown pack '{name}'. Packs live in: "
                     + ", ".join(str(d) for d in pack_dirs()))


def all_packs() -> list[Path]:
    seen, out = set(), []
    for d in pack_dirs():
        for p in sorted(d.glob("*/pack.yaml")):
            if p.parent.name not in seen and not p.parent.name.startswith("_"):
                seen.add(p.parent.name)
                out.append(p.parent)
    return out


def load_pack(name: str) -> dict:
    d = find_pack(name)
    cfg = _read_yaml(d / "pack.yaml")
    cfg["_dir"] = d
    return cfg
