# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Connect a code project (deck folder + the study-loop block in its CLAUDE.md), switch modes.

    asl init <project dir> --home <card home> --pack rust --prefix omk
             [--mode mentor] [--notes "<vault folder with this project's notes>"]
    asl mode <teacher|mentor|coworker|on-demand> [<project dir>]

The block's mode text comes from modes/<mode>.md; the deck from templates/.
"""
from __future__ import annotations

import re
from pathlib import Path

from studyloop.core.config import find_pack, read_keep, write_keep
from studyloop.core.config.home import init_home, render

BEGIN, MODE, END = "<!-- studyloop:begin -->", "<!-- studyloop:mode -->", "<!-- studyloop:end -->"
MODES = ["teacher", "mentor", "coworker", "on-demand"]
HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"


def init_project(project: Path, home: Path, pack: str, prefix: str, mode: str,
                 notes: str | None, name: str | None) -> None:
    project = project.expanduser().resolve()
    home = home.expanduser().resolve()
    find_pack(pack)
    init_home(home, [pack])
    name = name or project.name
    slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    deck_dir = home / slug
    notes_path = str(Path(notes).expanduser().resolve()) if notes else None
    kw = dict(name=name, slug=slug, pack=pack, prefix=prefix, project=project,
              repo=project.as_posix(),
              notes=notes_path or f"(not set: add the vault folder for {name}'s notes)")
    for tpl, dst in (("deck.yaml", "deck.yaml"), ("Overview.md", "Overview.md"),
                     ("profile.md", "profile.md"), ("cards.yaml", f"{slug}.yaml"),
                     ("cards_ext.yaml", f"{slug}_ext.yaml")):
        out = deck_dir / dst
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            tpl_text = (TEMPLATES / tpl).read_text(encoding="utf-8")
            write_keep(out, render(tpl_text, **kw))
            print(f"  created {out}")
    settings = "\n".join([
        f"- **Card home** (standards, evidence): `{home}`",
        f"- **This project's deck:** `{deck_dir}` (pack `{pack}`, ids `{prefix}-NNN`, "
        "index in `Overview.md`, file roles in `profile.md`)",
        f"- **Study notes for this project:** `{kw['notes']}`",
    ])
    write_block(project / "CLAUDE.md", settings, mode)
    print("Next: give the agent the skills (plugin, or `asl install-skills`), then work as usual.")


def _block(settings: str, mode: str) -> str:
    body = (HERE / "modes" / f"{mode}.md").read_text(encoding="utf-8").strip()
    return "\n".join([
        BEGIN,
        "## Study loop ([agentic-studying-loop](https://github.com/yungselm/agentic-studying-loop))",
        "What the user learns here becomes study notes and Anki cards, via the skills "
        "`study-note`, `study-source`, `write-cards`, `check-cards`, `refresh-standards`.",
        "",
        settings.strip(),
        "",
        MODE,
        body,
        END,
    ])


def write_block(claude_md: Path, settings: str, mode: str) -> None:
    if mode not in MODES:
        raise SystemExit(f"Unknown mode '{mode}'. Choose one of: {', '.join(MODES)}")
    text, nl = read_keep(claude_md) if claude_md.exists() else ("", "\n")
    block = _block(settings, mode)
    if BEGIN in text and END in text:
        pre, rest = text.split(BEGIN, 1)
        _, post = rest.split(END, 1)
        text = pre + block + post
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"
    write_keep(claude_md, text, nl)
    print(f"  {claude_md}: study loop block written (mode: {mode})")


def set_mode(project: Path, mode: str) -> None:
    claude_md = project.expanduser().resolve() / "CLAUDE.md"
    text = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
    if BEGIN not in text or MODE not in text:
        raise SystemExit(f"No study loop block in {claude_md}; run `asl init` first.")
    inner = text.split(BEGIN, 1)[1].split(MODE, 1)[0]
    settings = "\n".join(ln for ln in inner.splitlines() if ln.startswith("- "))
    write_block(claude_md, settings, mode)
