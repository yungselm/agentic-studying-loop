"""What modules plug into core (docs/architecture.md, "Extension points").

A module exposes one `Module` (found through the entry point group `studyloop.modules`;
after adding one, run `uv sync` so the entry point is installed). Its `register` adds deck
kinds, card types, lint rules and commands. The engines (lint, build, check, the CLI) only
loop over what is registered; core registers its own card types the same way.
SourceReader (step 6) and Analysis (step 7) are added when their steps land.
"""
from __future__ import annotations

import argparse
import functools
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    import genanki

    from studyloop.core.config import Deck


# ---- modules ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Module:
    name: str                               # "language"
    register: Callable[[Registry], None]
    skills: tuple[str, ...] = ()            # folders in skills/ this module owns
    requires: tuple[str, ...] = ()          # other modules ("core" is implicit)
    extra: str | None = None                # optional install that brings its dependencies
    needs: tuple[str, ...] = ()             # import names from that install; checked before
                                            # a command runs, so a missing one says
                                            # `pip install agentic-studying-loop[<extra>]`


# ---- deck kinds ------------------------------------------------------------------------

@dataclass(frozen=True)
class DeckKind:
    name: str                               # `kind:` in deck.yaml
    what: str                               # "lectures, books, links" (topics block, README)
    skills: str                             # how the agent works such a deck, for the topics block
    card_types: tuple[str, ...]             # allowed here; other types get a [kind] flag
    detect: Callable[[Deck], bool] | None = None   # decks without `kind:` (from before it)
    fallback: bool = False                  # the kind of a deck nothing else detects (topic)
    card_index: bool = True                 # `asl fix` keeps card rows in Overview.md
    frame_required: bool = False            # code cards must show their enclosing function
                                            # (`!`, else `~`): code from a repo (project)
    order_by_id: bool = False               # new cards in id order across subdecks (language)
    after_fix: Callable[[Deck], None] | None = None   # e.g. topic: refresh the sources map


# ---- card types ------------------------------------------------------------------------

class Flag(NamedTuple):
    sev: str                                # "!" must fix (exit 1), "~" worth a look
    kind: str                               # shown as [kind]: size, id, media, ...
    msg: str


class CodeBlock(NamedTuple):
    """Code `asl check` hands to the pack's checker."""
    kind: str                               # "solution" (with tests) | "example"
    code: str
    tests: str = ""


@dataclass
class LintContext:
    deck: Deck
    kind: DeckKind                          # the deck's kind
    file: Path
    limits: dict                            # this card type's limits: studyloop.yaml over defaults
    pack: dict                              # the pack's `lint:` settings ({} without a pack)
    vault: Path | None
    memo: dict = field(default_factory=dict)        # shared by all cards of one deck

    def once(self, key: str, make: Callable[[], Any]) -> Any:
        """Deck-level data computed once per deck (the language's length cap, the repo path)."""
        if key not in self.memo:
            self.memo[key] = make()
        return self.memo[key]


class NoteContext:
    """What a card type needs to turn a card into Anki fields (implemented by build.py)."""
    deck: Deck
    file: Path
    pack_mode: str                          # CodeMirror mode of the card's pack

    def text(self, s: Any) -> str: ...      # plain text -> HTML
    def rich(self, s: Any) -> str: ...      # vault text: $math$, ![[images]], [[links]]
    def code(self, s: Any) -> str: ...      # code for the editor (base64)
    def source(self, card: dict) -> str: ...            # `source:` with its vault links
    def media(self, name: Any, kind: str) -> str: ...   # [sound:x] / <img>; ships the file
    def links(self, v: Any) -> str: ...     # one [[link]] or a list of them


class Template(NamedTuple):
    name: str                               # "Listening"
    front: str                              # file in the card type's templates_dir
    back: str


class CardType:
    """One `type:` in card files. Subclass and set the class attributes."""
    name: str                               # "cloze"
    model_id: int                           # never change: Anki keys note types by it
    model_name: str                         # "Cloze Card" (stats also matches by name)
    fields: tuple[str, ...]
    templates: tuple[Template, ...]
    templates_dir: Path
    cloze: bool = False                     # an Anki cloze note type
    default_limits: dict = {}               # studyloop.yaml `limits: <name>:` defaults
    limits_name: str | None = None          # use another type's limits (timeline: concept)
    css: str = ""                           # appended to the shared style.css for this type

    def prepare(self, card: dict) -> dict:
        """Right after loading (timeline: shuffle the steps into a question)."""
        return card

    def front(self, card: dict) -> str:
        """The prompt: labels, the duplicate check, GUIDs of cards without an id."""
        return str(card.get("question") or "")

    def measures(self, card: dict) -> dict:
        """Numbers the standards limit; lint checks them, stats bins reviews by them."""
        return {}

    def lint(self, card: dict, ctx: LintContext) -> list[Flag]:
        return []

    def to_fields(self, card: dict, ctx: NoteContext) -> list[str]:
        raise NotImplementedError

    def tags(self, card: dict) -> list[str]:
        """Extra Anki tags (cloze: asl::hook)."""
        return []

    def code_blocks(self, card: dict) -> list[CodeBlock]:
        """Any card may carry a `code:` example; the code card overrides this."""
        return [CodeBlock("example", card["code"])] if card.get("code") else []

    def model(self, template: Callable[[str], str], css: str) -> genanki.Model:
        """The Anki note type. `template(file)` reads a template with the shared asset names
        (CodeMirror, _cards.js) resolved; card types sharing a model_id share one model."""
        import genanki
        return genanki.Model(
            self.model_id, self.model_name, fields=[{"name": f} for f in self.fields],
            templates=[{"name": t.name, "qfmt": template(t.front), "afmt": template(t.back)}
                       for t in self.templates],
            css=css, sort_field_index=0,
            model_type=genanki.Model.CLOZE if self.cloze else genanki.Model.FRONT_BACK)


# ---- lint rules ------------------------------------------------------------------------

@dataclass(frozen=True)
class DeckSummary:
    ids: list[str]
    types: Counter                          # card type -> count
    whole: bool                             # every file of the deck was linted


@dataclass(frozen=True)
class LintRule:
    """A check beyond one card type: project headers and excerpts, the topic's card mix."""
    name: str
    kinds: tuple[str, ...] | None = None    # deck kinds it applies to; None: all
    card: Callable[[dict, LintContext], list[Flag]] | None = None
    deck: Callable[[Deck, DeckSummary], list[Flag]] | None = None


# ---- commands --------------------------------------------------------------------------

@dataclass(frozen=True)
class Command:
    name: str                               # `asl <name>`
    help: str
    arguments: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], int]


# ---- the registry ----------------------------------------------------------------------

class Registry:
    def __init__(self) -> None:
        self.modules: dict[str, Module] = {}
        self.deck_kinds: dict[str, DeckKind] = {}
        self.card_types: dict[str, CardType] = {}
        self.lint_rules: list[LintRule] = []
        self.commands: dict[str, tuple[Module, Command]] = {}
        self.provides: dict[str, dict[str, tuple[Module, Any]]] = {}
        self._current: Module | None = None

    def add_deck_kind(self, k: DeckKind) -> None:
        self._unique(self.deck_kinds, k.name, "deck kind")
        self.deck_kinds[k.name] = k

    def add_card_type(self, t: CardType) -> None:
        self._unique(self.card_types, t.name, "card type")
        self.card_types[t.name] = t

    def add_lint_rule(self, r: LintRule) -> None:
        self.lint_rules.append(r)

    def add_command(self, c: Command) -> None:
        self._unique(self.commands, c.name, "command")
        self.commands[c.name] = (self._current, c)

    def provide(self, point: str, name: str, obj: Any) -> None:
        """An extension point a module defines for others (the language module's "language":
        language_ja provides "ja"). Core never looks inside."""
        table = self.provides.setdefault(point, {})
        self._unique(table, name, point)
        table[name] = (self._current, obj)

    def provided(self, point: str) -> dict[str, tuple[Module, Any]]:
        return self.provides.get(point, {})

    def card_type(self, name: str) -> CardType:
        if name not in self.card_types:
            raise KeyError(f"unknown card type `{name}` (installed: {', '.join(self.card_types)})")
        return self.card_types[name]

    def missing(self, m: Module) -> list[str]:
        """Imports of the module's optional install that aren't there."""
        import importlib.util
        return [n for n in m.needs if importlib.util.find_spec(n) is None]

    def _unique(self, table: dict, name: str, what: str) -> None:
        if name in table:
            raise SystemExit(f"two modules register the {what} `{name}`")

    def _load(self, m: Module) -> None:
        self.modules[m.name] = m
        self._current = m
        m.register(self)
        self._current = None


@functools.cache
def registry() -> Registry:
    """Core plus every installed module (entry points), loaded once per process."""
    from importlib.metadata import entry_points

    from studyloop.core import MODULE as CORE
    mods = [CORE]
    for ep in entry_points(group="studyloop.modules"):
        m = ep.load()
        if m.name != "core":
            mods.append(m)
    return load(mods)


def load(modules: list[Module]) -> Registry:
    """Core first, then the rest by name; a module's `requires` must be there."""
    reg = Registry()
    names = {m.name for m in modules}
    for m in sorted(modules, key=lambda m: (m.name != "core", m.name)):
        absent = [r for r in m.requires if r not in names]
        if absent:
            raise SystemExit(f"module `{m.name}` needs {', '.join(absent)}")
        reg._load(m)
    return reg
