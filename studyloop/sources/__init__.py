"""Topics from lectures, books and links (deck kind `topic`, skill `study-source`).

  sourcemap   a topic's sources as a map of parts sized to the token budget; `asl sources`
  topic       `asl topic`: a new topic deck, and the topics block in the vault's CLAUDE.md
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..core.config import Deck
from ..core.registry import Command, DeckKind, LintRule, Module, Registry
from ..core.vault import split_frontmatter


def mix_flags(deck: Deck, kinds: Counter) -> list[tuple[str, str, str]]:
    """Topic decks: the brief's `cards: {code: 0.3}` sets the share of code cards; far off -> note.
    Without it, a topic deck that is mostly code cards gets the reminder to decide."""
    if deck.kind != "topic" or sum(kinds.values()) < 10:
        return []
    ov = deck.path / "Overview.md"
    brief = split_frontmatter(ov.read_text(encoding="utf-8"))[0] if ov.is_file() else {}
    total, code = sum(kinds.values()), kinds["code"] / sum(kinds.values())
    want = (brief.get("cards") or {}).get("code") if isinstance(brief.get("cards"), dict) else None
    if want is None:
        return [("~", "mix", f"{code:.0%} code cards and no `cards:` in the brief: set e.g. "
                 "`cards: {code: 0.3}` in Overview.md (books about code) or `{code: 0}`")] if code > 0.4 else []
    if abs(code - float(want)) > 0.15:
        return [("~", "mix", f"{code:.0%} code cards ({kinds['code']} of {total}); the brief says "
                 f"{float(want):.0%} (`cards:` in Overview.md)")]
    return []


def _refresh_map(deck: Deck) -> None:
    """After `asl fix`: the sources map's status follows the new cards' `source:` links."""
    from .sourcemap import BEGIN, build_map
    ov = deck.path / "Overview.md"
    if ov.is_file() and BEGIN in ov.read_text(encoding="utf-8"):
        build_map(deck, quiet=True)


TOPIC = DeckKind(
    "topic", what="lectures, books, links", skills="study-source -> study-note -> write-cards",
    card_types=("cloze", "concept", "timeline", "code"), fallback=True, after_fix=_refresh_map)


def _sources_args(p):
    p.add_argument("inputs", nargs="*")
    p.add_argument("--read", metavar="PART", help="print the text of one part, e.g. tour.3")


def _sources(a):
    from ..core.config import resolve_inputs
    from .sourcemap import sources
    return sources(resolve_inputs(a.inputs), a.read)


def _topic_args(p):
    p.add_argument("name", help='e.g. "CS231n" or "C++"')
    p.add_argument("--home", type=Path, required=True, help="card home in your vault")
    p.add_argument("--sources", action="append", default=[],
                   help="a folder of PDFs, a file or a URL (repeat for more)")
    p.add_argument("--notes", help="vault folder for this topic's study notes")
    p.add_argument("--no-notes", action="store_true", help="cards straight from the sources")
    p.add_argument("--prefix", help="card id prefix (default: from the name)")
    p.add_argument("--pack", default="python", help="code highlighting/checker (default python)")
    p.add_argument("--goal", help="what the topic is for; steers what gets carded")
    p.add_argument("--builds-on", action="append", default=[], help="what you know already")
    p.add_argument("--lang", help="a language deck instead (e.g. ja): sentence and grammar cards")
    p.add_argument("--media", help="language decks: folder outside the vault for clips/screenshots")
    p.add_argument("--level", help="language decks: current level (JLPT / CEFR)")
    p.add_argument("--gloss", help="language decks: gloss language (default en)")


def _topic(a):
    from .topic import init_topic
    init_topic(a.name, a.home, a.sources, a.notes, a.no_notes, a.prefix, a.pack, a.goal,
               a.builds_on, a.lang, a.media, a.level, a.gloss)
    return 0


def register(reg: Registry) -> None:
    reg.add_deck_kind(TOPIC)
    reg.add_lint_rule(LintRule("mix", kinds=("topic",),
                               deck=lambda deck, s: mix_flags(deck, s.types)))
    reg.add_command(Command("sources", "map a topic's books/links into parts (Overview.md)",
                            _sources_args, _sources))
    reg.add_command(Command("topic", "start a topic from lectures, books or links (no code repo)",
                            _topic_args, _topic))


MODULE = Module("sources", register, skills=("study-source",))
