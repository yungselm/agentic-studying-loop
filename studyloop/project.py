"""Set up a card home and a project, and switch modes.

    asl init-home <card home> [--pack rust --pack python]
    asl init <project dir> --home <card home> --pack rust --prefix omk
             [--mode mentor] [--notes "<vault folder with this project's notes>"]
    asl mode <teacher|mentor|coworker|on-demand> [<project dir>]

The card home is a folder in your notes vault (e.g. "Studying/Anki cards").
It owns *your* standards: init-home copies the repo's defaults there, and from
then on they evolve with your own review data.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import REPO, find_pack, read_keep, write_keep

BEGIN, MODE, END = "<!-- studyloop:begin -->", "<!-- studyloop:mode -->", "<!-- studyloop:end -->"
MODES = ["teacher", "mentor", "coworker", "on-demand"]
TEMPLATES = REPO / "templates"


def _copy_new(src: Path, dst: Path) -> bool:
    if dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def init_home(home: Path, packs: list[str]) -> None:
    home = home.expanduser().resolve()
    made = []
    if _copy_new(TEMPLATES / "card-home" / "studyloop.yaml", home / "studyloop.yaml"):
        made.append("studyloop.yaml")
    for name in ("core.md",):
        if _copy_new(REPO / "standards" / name, home / "standards" / name):
            made.append(f"standards/{name}")
    if _copy_new(TEMPLATES / "card-home" / "preferences.md", home / "standards" / "preferences.md"):
        made.append("standards/preferences.md")
    for p in packs:
        if _copy_new(find_pack(p) / "standards.md", home / "standards" / f"{p}.md"):
            made.append(f"standards/{p}.md")
    (home / "evidence").mkdir(parents=True, exist_ok=True)
    print(f"Card home {home}: " + (", ".join(made) if made else "already set up, nothing changed."))


def _render(tpl: str, **kw) -> str:
    for k, v in kw.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    return tpl


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
            tpl_text = (TEMPLATES / "project" / tpl).read_text(encoding="utf-8")
            write_keep(out, _render(tpl_text, **kw))
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
    body = (REPO / "modes" / f"{mode}.md").read_text(encoding="utf-8").strip()
    return "\n".join([
        BEGIN,
        "## Study loop ([agentic-studying-loop](https://github.com/yungselm/agentic-studying-loop))",
        "What the user learns here becomes study notes and Anki cards, via the skills "
        "`study-note`, `write-cards`, `check-cards`, `refresh-standards`.",
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


def install_skills(target: Path) -> None:
    """Copy the skills into a .claude/skills folder (for use without the plugin)."""
    target = target.expanduser().resolve()
    for skill in sorted((REPO / "skills").iterdir()):
        if (skill / "SKILL.md").is_file():
            dst = target / skill.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(skill, dst)
            print(f"  {dst}")
