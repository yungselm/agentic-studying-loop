"""Start a topic (lectures, books, links; no code repo), and the topics block: a CLAUDE.md next to
the card home that lists every topic and language deck, so an agent started anywhere in the
studying folder finds them.

    asl topic <name> --home <card home> --sources <folder|file|url> [...] [--notes <folder>]
"""
from __future__ import annotations

import re
from pathlib import Path

from ..core.config import find_pack, load_deck, read_keep, write_keep
from ..core.home import _yaml_str, init_home, render
from ..core.registry import registry
from ..core.vault import resolve_in, split_frontmatter, vault_for, vault_rel

TEMPLATES = Path(__file__).resolve().parent / "templates"


def init_topic(name: str, home: Path, sources: list[str], notes: str | None, no_notes: bool,
               prefix: str | None, pack: str, goal: str | None, builds_on: list[str],
               lang: str | None = None, media: str | None = None, level: str | None = None,
               gloss: str | None = None) -> Path:
    """A deck for a topic without a code repo (lectures, books, links), or with `lang` a language
    deck, plus the topics block in the CLAUDE.md of the folder that holds the card home."""
    home = home.expanduser().resolve()
    if lang:
        makers = registry().provided("new-deck")         # the language module's
        if "language" not in makers:
            raise SystemExit("`asl topic --lang` needs the language module")
        return makers["language"][1](name, home, lang, media, notes, prefix, goal, level, gloss)
    find_pack(pack)
    init_home(home, [pack])
    vault = vault_for(home) or home.parent
    plain = name.lower().replace("+", "p").replace("#", "sharp")       # C++ -> cpp, C# -> csharp
    slug = re.sub(r"[^a-z0-9_]+", "_", plain).strip("_") or "topic"
    prefix = prefix or (re.sub(r"[^a-z0-9]", "", plain)[:3] or "top")
    deck_dir = home / slug
    src_lines = []
    for s in sources:
        if re.match(r"https?://", s):
            src_lines.append(f"  - {s}")
        else:
            src_lines.append(f"  - {_yaml_str(vault_rel(resolve_in(vault, s), vault))}")
    notes_val = ("false" if no_notes else
                 _yaml_str(vault_rel(resolve_in(vault, notes), vault)) if notes else
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
        write_keep(out, render((TEMPLATES / tpl).read_text(encoding="utf-8"), **kw))
        print(f"  created {out}")
    write_topics_block(home)
    if sources:
        from .sourcemap import build_map
        build_map(load_deck(deck_dir))
    return deck_dir


TOPICS_BEGIN, TOPICS_END = "<!-- studyloop:topics:begin -->", "<!-- studyloop:topics:end -->"


def write_topics_block(home: Path) -> None:
    """CLAUDE.md next to the card home: where topics live, so an agent started anywhere
    in the studying folder finds them without being told paths."""
    decks = [load_deck(d) for d in sorted(home.iterdir()) if (d / "deck.yaml").is_file()]
    topics = [d for d in decks if d.kind != "project"]     # projects have their own block

    def entry(d):
        b = registry().deck_kinds[d.kind]
        title = (d.path / "Overview.md").is_file() and _topic_name(d.path) or d.path.name
        kinds = ", ".join(b.card_types[:3]) + (" + code per the brief's `cards:`" if d.kind == "topic" else "")
        return f"  - {title} ({d.kind}: {b.skills}; cards: {kinds}): `{d.path}`"
    lines = [
        TOPICS_BEGIN,
        "## Study loop: topics ([agentic-studying-loop](https://github.com/yungselm/agentic-studying-loop))",
        "Each deck has a **kind** (`kind:` in its deck.yaml); the kind decides the skills, the "
        "`asl` commands and the card types. Follow only the named kind.",
        "- **topic** (lectures, books, links): `study-source` (one part per batch) → `study-note` → "
        "`write-cards`; `asl sources / fix / lint / check / build`; card mix from the brief's `cards:`.",
        "- **language**: `language-cards`; `asl lang add / plan / draft / grammar / tts / sync`, "
        "then `asl lint / build`; sentence and grammar cards only.",
        "- Choices for one topic go into its `Overview.md` brief; `preferences.md` only takes rules "
        "for all cards.",
        "",
        f"- **Card home** (standards, evidence): `{home}`",
        "- **Decks** (deck folder; its `Overview.md` holds the brief; read that, not the sources):",
        *[entry(d) for d in topics],
        f'- **New topic:** ask the goal, prior knowledge and notes-or-cards-only first, then '
        f'`asl topic "<name>" --home "{home}" --sources "<folder|file|url>" '
        '--notes "<notes folder>"` (or `--no-notes`)',
        f'- **New language:** `asl topic "<Language>" --lang <code> --home "{home}" '
        '--media "<folder outside the vault>"` (skill `language-cards` asks the rest)',
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
    meta, _ = split_frontmatter((d / "Overview.md").read_text(encoding="utf-8"))
    return str(meta.get("project") or "")
