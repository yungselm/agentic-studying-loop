"""Set up a card home and a project, and switch modes.

    asl init-home <card home> [--pack rust --pack python]
    asl init <project dir> --home <card home> --pack rust --prefix omk
             [--mode mentor] [--notes "<vault folder with this project's notes>"]
    asl mode <teacher|mentor|coworker|on-demand> [<project dir>]
    asl topic <name> --home <card home> --sources <folder|file|url> [...] [--notes <folder>]

The card home is a folder in your notes vault (e.g. "Studying/Anki cards").
It owns *your* standards: init-home copies the repo's defaults there, and from
then on they evolve with your own review data.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import PKG, find_pack, read_keep, write_keep

BEGIN, MODE, END = "<!-- studyloop:begin -->", "<!-- studyloop:mode -->", "<!-- studyloop:end -->"
MODES = ["teacher", "mentor", "coworker", "on-demand"]
TEMPLATES = PKG / "templates"


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
        if _copy_new(PKG / "standards" / name, home / "standards" / name):
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


def _yaml_str(s: str | None) -> str:
    return '""' if s is None else '"' + str(s).replace("\\", "/").replace('"', "'") + '"'


def _vault_rel(p: Path, vault: Path | None) -> str:
    """A path as the vault sees it (relative), else absolute."""
    try:
        return p.relative_to(vault).as_posix() if vault else p.as_posix()
    except ValueError:
        return p.as_posix()


def _resolve_in(base: Path, s: str) -> Path:
    p = Path(s).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (Path.cwd() / p).resolve() if (Path.cwd() / p).exists() else (base / p).resolve()


def init_topic(name: str, home: Path, sources: list[str], notes: str | None, no_notes: bool,
               prefix: str | None, pack: str, goal: str | None, builds_on: list[str]) -> Path:
    """A deck for a topic without a code repo (lectures, books, links), plus the study-loop
    block in the CLAUDE.md of the folder that holds the card home."""
    from . import notes as N
    home = home.expanduser().resolve()
    find_pack(pack)
    init_home(home, [pack])
    vault = N.card_vault(home) or home.parent
    plain = name.lower().replace("+", "p").replace("#", "sharp")       # C++ -> cpp, C# -> csharp
    slug = re.sub(r"[^a-z0-9_]+", "_", plain).strip("_") or "topic"
    prefix = prefix or (re.sub(r"[^a-z0-9]", "", plain)[:3] or "top")
    deck_dir = home / slug
    src_lines = []
    for s in sources:
        if re.match(r"https?://", s):
            src_lines.append(f"  - {s}")
        else:
            src_lines.append(f"  - {_yaml_str(_vault_rel(_resolve_in(vault, s), vault))}")
    notes_val = ("false" if no_notes else
                 _yaml_str(_vault_rel(_resolve_in(vault, notes), vault)) if notes else
                 '""                              # vault folder for study notes; false = cards only')
    kw = dict(name=name, prefix=prefix, pack=pack,
              goal=_yaml_str(goal) if goal else '""                               # what this topic is for',
              builds_on="[" + ", ".join(builds_on) + "]" if builds_on else
              "[]                          # what you know already: contrast cards",
              notes=notes_val, sources="\n".join(src_lines) or "  []")
    for tpl in ("deck.yaml", "Overview.md"):
        out = deck_dir / tpl
        if out.exists():
            print(f"  kept {out}")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        write_keep(out, _render((TEMPLATES / "topic" / tpl).read_text(encoding="utf-8"), **kw))
        print(f"  created {out}")
    write_topics_block(home)
    if sources:
        from .config import load_deck
        from .sources import build_map
        build_map(load_deck(deck_dir))
    return deck_dir


TOPICS_BEGIN, TOPICS_END = "<!-- studyloop:topics:begin -->", "<!-- studyloop:topics:end -->"


def write_topics_block(home: Path) -> None:
    """CLAUDE.md next to the card home: where topics live, so an agent started anywhere
    in the studying folder finds them without being told paths."""
    from .config import _read_yaml
    topics = [d for d in sorted(home.iterdir())
              if (d / "deck.yaml").is_file() and not _read_yaml(d / "deck.yaml").get("repo")]
    lines = [
        TOPICS_BEGIN,
        "## Study loop: topics ([agentic-studying-loop](https://github.com/yungselm/agentic-studying-loop))",
        "Lectures, books and links studied here become study notes and Anki cards: skill "
        "`study-source` (one part per batch), then `study-note`, `write-cards`, `check-cards`.",
        "",
        f"- **Card home** (standards, evidence): `{home}`",
        "- **Topics** (deck folder; its `Overview.md` holds the brief and the sources map; "
        "read that, not the sources):",
        *[f"  - {(d / 'Overview.md').is_file() and _topic_name(d) or d.name}: `{d}`" for d in topics],
        f'- **New topic:** `asl topic "<name>" --home "{home}" --sources "<folder|file|url>" '
        '--notes "<notes folder>"`',
        TOPICS_END,
    ]
    block = "\n".join(lines)
    md = home.parent / "CLAUDE.md"
    text, nl = read_keep(md) if md.exists() else ("", "\n")
    if TOPICS_BEGIN in text and TOPICS_END in text:
        pre, rest = text.split(TOPICS_BEGIN, 1)
        text = pre + block + rest.split(TOPICS_END, 1)[1]
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"
    write_keep(md, text, nl)
    print(f"  {md}: topics block written ({len(topics)} topic(s))")


def _topic_name(d: Path) -> str:
    from .notes import split_frontmatter
    meta, _ = split_frontmatter((d / "Overview.md").read_text(encoding="utf-8"))
    return str(meta.get("project") or "")


def _block(settings: str, mode: str) -> str:
    body = (PKG / "modes" / f"{mode}.md").read_text(encoding="utf-8").strip()
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


def skills_dir() -> Path:
    """skills/ sits at the repo root (where the Claude Code plugin expects it) and
    is installed alongside the package as `studyloop_skills`."""
    import studyloop_skills
    return Path(studyloop_skills.__path__[0])


def install_skills(target: Path) -> None:
    """Copy the skills into a .claude/skills folder (for use without the plugin)."""
    target = target.expanduser().resolve()
    for skill in sorted(skills_dir().iterdir()):
        if (skill / "SKILL.md").is_file():
            dst = target / skill.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(skill, dst)
            print(f"  {dst}")
