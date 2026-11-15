"""Vault notes with YAML frontmatter (grammar notes): read, write, change fields. The body is
kept exactly as written."""
from __future__ import annotations

import re
from pathlib import Path

import yaml


def read_note(p: Path) -> tuple[dict, str]:
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    _, fm, body = text.split("---\n", 2)
    return yaml.safe_load(fm) or {}, body


def write_note(p: Path, meta: dict, body: str) -> None:
    p.write_text("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000)
                 + "---\n" + body, encoding="utf-8")


def update_note(p: Path, **fields) -> bool:
    """Set frontmatter fields; writes only if something changed."""
    meta, body = read_note(p)
    new = {**meta, **fields}
    if new != meta:
        write_note(p, new, body)
    return new != meta


def embed_image(body: str, image: str) -> str:
    """`![[image]]` after the note's title and first line (where the meaning stands)."""
    return re.sub(r"^(# .*\n\n.*\n)", rf"\1\n![[{image}]]\n", body, count=1)
