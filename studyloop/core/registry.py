"""What modules plug into core (docs/architecture.md, "Extension points").

A module exposes one `Module` (found through the entry point group `studyloop.modules`;
after adding one, run `uv sync` so the entry point is installed). Its `register` adds deck
kinds, card types, lint rules and commands. The engines (lint, build, check, the CLI) only
loop over what is registered; core registers its own card types the same way.
Modules can also define extension points of their own (`Registry.provide`): the language
module's "language", the analysis module's "analysis".
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
    """One module: what it registers and what it needs.

    Parameters
    ----------
    name : str
        Unique module name, e.g. ``"language"``.
    register : callable
        ``register(reg)`` adds the module's deck kinds, card types, lint rules and commands.
    skills : tuple of str
        Folders in ``skills/`` this module owns; ``asl install-skills`` installs them only
        when the module is installed.
    requires : tuple of str
        Other modules it builds on (``"core"`` is implicit).
    extra : str or None
        The optional install that brings its dependencies (``pip install
        agentic-studying-loop[<extra>]``).
    needs : tuple of str
        Import names from that install. Checked before one of the module's commands runs,
        so a missing one prints the install line instead of a traceback.

    Examples
    --------
    The Japanese module (``studyloop/language_ja/__init__.py``), registered in
    ``pyproject.toml`` under ``[project.entry-points."studyloop.modules"]``:

    >>> def register(reg):
    ...     reg.provide("language", "ja", JA)
    >>> MODULE = Module("language_ja", register, requires=("language",), extra="lang-ja",
    ...                 needs=("fugashi", "unidic_lite"))
    """
    name: str
    register: Callable[[Registry], None]
    skills: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    extra: str | None = None
    needs: tuple[str, ...] = ()


# ---- deck kinds ------------------------------------------------------------------------

@dataclass(frozen=True)
class DeckKind:
    """What a deck is for (``kind:`` in deck.yaml): its skills, card types and checks.

    Parameters
    ----------
    name : str
        The value of ``kind:``.
    what : str
        Short description for the topics block and the README, e.g. "lectures, books, links".
    skills : str
        How the agent works such a deck, written into the topics block of ``CLAUDE.md``.
    card_types : tuple of str
        Card types allowed here; others get a ``[kind]`` lint flag.
    detect : callable, optional
        ``detect(deck) -> bool`` for decks made before ``kind:`` existed.
    fallback : bool
        The kind of a deck nothing else detects (topic).
    card_index : bool
        ``asl fix`` keeps one row per card in ``Overview.md``.
    frame_required : bool
        Code cards must show their enclosing function (code from a repo: project).
    order_by_id : bool
        New cards in id order across subdecks (language).
    after_fix : callable, optional
        ``after_fix(deck)`` runs after ``asl fix`` (topic: refresh the sources map).

    Examples
    --------
    The topic kind (``studyloop/sources/__init__.py``):

    >>> TOPIC = DeckKind(
    ...     "topic", what="lectures, books, links",
    ...     skills="study-source -> study-note -> write-cards",
    ...     card_types=("cloze", "concept", "timeline", "code"), fallback=True,
    ...     after_fix=_refresh_map)
    >>> reg.add_deck_kind(TOPIC)
    """
    name: str
    what: str
    skills: str
    card_types: tuple[str, ...]
    detect: Callable[[Deck], bool] | None = None
    fallback: bool = False
    card_index: bool = True
    frame_required: bool = False
    order_by_id: bool = False
    after_fix: Callable[[Deck], None] | None = None


# ---- card types ------------------------------------------------------------------------

class Flag(NamedTuple):
    """One lint finding.

    Parameters
    ----------
    sev : str
        ``"!"`` must be fixed (``asl lint`` exits 1), ``"~"`` is worth a look.
    kind : str
        Shown as ``[kind]``: size, id, media, frame, ... (``asl lint --skip`` takes these).
    msg : str
        What is wrong, in one line.

    Examples
    --------
    >>> Flag("!", "size", "answer has no **bold lead** to grade against")
    """
    sev: str
    kind: str
    msg: str


class CodeBlock(NamedTuple):
    """Code ``asl check`` hands to the pack's checker.

    Parameters
    ----------
    kind : str
        ``"solution"`` (run with its tests) or ``"example"`` (compiled only).
    code : str
    tests : str
        Asserts, for solutions.

    Examples
    --------
    >>> CodeBlock("solution", "def double_all(nums): ...", "assert double_all([1]) == [2]")
    """
    kind: str
    code: str
    tests: str = ""


@dataclass
class LintContext:
    """What a card type's or rule's lint gets besides the card.

    Attributes
    ----------
    deck : Deck
    kind : DeckKind
        The deck's kind.
    file : Path
        The card file being linted.
    limits : dict
        This card type's limits: ``studyloop.yaml`` over the type's ``default_limits``.
    pack : dict
        The pack's ``lint:`` settings (``{}`` without a pack).
    vault : Path or None
        The notes vault, for ``[[links]]`` and ``![[images]]``.
    memo : dict
        Shared by all cards of one deck; use `once`.
    """
    deck: Deck
    kind: DeckKind
    file: Path
    limits: dict
    pack: dict
    vault: Path | None
    memo: dict = field(default_factory=dict)

    def once(self, key: str, make: Callable[[], Any]) -> Any:
        """Deck-level data, computed once per deck.

        Parameters
        ----------
        key : str
            Unique per module, e.g. ``"project.repo"``.
        make : callable
            Computes the value on first use.

        Examples
        --------
        The project checks read the repo path once, not once per card:

        >>> repo = ctx.once("project.repo", lambda: _existing_repo(ctx.deck))
        """
        if key not in self.memo:
            self.memo[key] = make()
        return self.memo[key]


class NoteContext:
    """What a card type needs to turn a card into Anki fields (implemented by build.py).

    Attributes
    ----------
    deck : Deck
    file : Path
    pack_mode : str
        CodeMirror mode of the card's pack (``"python"``, ``"rust"``).

    Examples
    --------
    The concept card's fields (``studyloop/core/cards/types.py``):

    >>> def to_fields(self, card, ctx):
    ...     return [ctx.rich(card["question"]), ctx.rich(card.get("answer")),
    ...             ctx.code(card.get("code", "")), ctx.pack_mode, ctx.source(card)]
    """
    deck: Deck
    file: Path
    pack_mode: str

    def text(self, s: Any) -> str:
        """Plain text to HTML (`backticks` and **bold** kept)."""
        ...

    def rich(self, s: Any) -> str:
        """Vault text to HTML: ``$math$``, ``![[images]]`` (shipped), ``[[links]]``."""
        ...

    def code(self, s: Any) -> str:
        """Code for the in-card editor (base64)."""
        ...

    def source(self, card: dict) -> str:
        """The card's ``source:``, with vault links shown as ``Note › Section``."""
        ...

    def media(self, name: Any, kind: str) -> str:
        """``[sound:x]`` or ``<img>`` for a media file; ships the file in the package."""
        ...

    def links(self, v: Any) -> str:
        """One ``[[link]]`` or a list of them."""
        ...


class Template(NamedTuple):
    """One Anki card template of a card type.

    Examples
    --------
    >>> Template("Concept Card", "front_concept.html", "back_concept.html")
    """
    name: str
    front: str          # file in the card type's templates_dir
    back: str


class CardType:
    """One ``type:`` in card files. Subclass it and set the class attributes.

    Attributes
    ----------
    name : str
        The ``type:`` value, e.g. ``"cloze"``.
    model_id : int
        Anki keys note types by it: never change it once cards are imported.
    model_name : str
        The note type's name in Anki (``asl stats`` also matches by it).
    fields : tuple of str
    templates : tuple of Template
    templates_dir : Path
    cloze : bool
        An Anki cloze note type.
    default_limits : dict
        Defaults for ``limits: <name>:`` in ``studyloop.yaml``.
    limits_name : str or None
        Use another type's limits (timeline uses concept's).
    css : str
        Appended to the shared ``style.css``.

    Examples
    --------
    The concept card (``studyloop/core/cards/types.py``), shortened:

    >>> class Concept(CardType):
    ...     name, model_name = "concept", "Concept Card"
    ...     model_id = 1607392321
    ...     fields = ("Question", "Answer", "Code", "Lang", "Source")
    ...     templates = (Template("Concept Card", "front_concept.html", "back_concept.html"),)
    ...     templates_dir = TEMPLATES
    ...     default_limits = {"answer_chars_max": 300, "bold_chars_max": 150}
    ...
    ...     def measures(self, card):
    ...         a = card.get("answer") or ""
    ...         return {"answer_chars": len(plain(a)), "bold_chars": len(bold_lead(a))}
    ...
    ...     def lint(self, card, ctx):
    ...         if not self.measures(card)["bold_chars"]:
    ...             return [Flag("!", "size", "answer has no **bold lead** to grade against")]
    ...         return []
    >>> reg.add_card_type(Concept())
    """
    name: str
    model_id: int
    model_name: str
    fields: tuple[str, ...]
    templates: tuple[Template, ...]
    templates_dir: Path
    cloze: bool = False
    default_limits: dict = {}
    limits_name: str | None = None
    css: str = ""

    def prepare(self, card: dict) -> dict:
        """Change a card right after loading (timeline: shuffle the steps into a question)."""
        return card

    def front(self, card: dict) -> str:
        """The prompt: used for labels, the duplicate check, GUIDs of cards without an id."""
        return str(card.get("question") or "")

    def measures(self, card: dict) -> dict:
        """Numbers the standards limit; lint checks them, ``asl stats`` bins reviews by them.

        Examples
        --------
        >>> registry().card_type("concept").measures(card)     # tasklog's tsk-003
        {'answer_chars': 184, 'bold_chars': 105}
        """
        return {}

    def lint(self, card: dict, ctx: LintContext) -> list[Flag]:
        """This type's own checks, after the checks every card gets."""
        return []

    def to_fields(self, card: dict, ctx: NoteContext) -> list[str]:
        """The Anki fields, in the order of `fields`."""
        raise NotImplementedError

    def tags(self, card: dict) -> list[str]:
        """Extra Anki tags (cloze: ``asl::hook``)."""
        return []

    def code_blocks(self, card: dict) -> list[CodeBlock]:
        """What ``asl check`` runs. Any card may carry a ``code:`` example; code cards
        override this to hand over the solution and its tests."""
        return [CodeBlock("example", card["code"])] if card.get("code") else []

    def model(self, template: Callable[[str], str], css: str) -> genanki.Model:
        """The Anki note type. ``template(file)`` reads a template with the shared asset names
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
    """What a deck-level rule sees after all cards were linted.

    Attributes
    ----------
    ids : list of str
    types : Counter
        Card type to count, e.g. ``Counter({"cloze": 41, "concept": 12})``.
    whole : bool
        Every file of the deck was linted (not just one file passed by name).
    """
    ids: list[str]
    types: Counter
    whole: bool


@dataclass(frozen=True)
class LintRule:
    """A check beyond one card type, per card and/or per deck.

    Parameters
    ----------
    name : str
    kinds : tuple of str or None
        Deck kinds it applies to; None: all.
    card : callable, optional
        ``card(card, ctx) -> list[Flag]``, for every card.
    deck : callable, optional
        ``deck(deck, summary) -> list[Flag]``, once per deck.

    Examples
    --------
    The topic's card mix (``studyloop/sources/__init__.py``): a topic deck that is mostly
    code cards, against the brief's ``cards: {code: 0.3}``, gets a note:

    >>> reg.add_lint_rule(LintRule("mix", kinds=("topic",),
    ...                            deck=lambda deck, s: mix_flags(deck, s.types)))
    """
    name: str
    kinds: tuple[str, ...] | None = None
    card: Callable[[dict, LintContext], list[Flag]] | None = None
    deck: Callable[[Deck, DeckSummary], list[Flag]] | None = None


# ---- commands --------------------------------------------------------------------------

@dataclass(frozen=True)
class Command:
    """One ``asl <name>`` command.

    Parameters
    ----------
    name : str
    help : str
        One line, shown in ``asl -h`` and on the Commands page.
    arguments : callable
        ``arguments(parser)`` adds the options (and `studyloop.core.cli.examples`).
    run : callable
        ``run(args) -> int``, the exit code. Import heavy code inside it, not at the top of
        the module: every command is registered on every ``asl`` call.

    Examples
    --------
    ``asl stats`` (``studyloop/analysis/__init__.py``):

    >>> def _stats_args(p):
    ...     p.add_argument("export", help="a manual Anki export (.apkg or .colpkg)")
    ...     p.add_argument("--deck", help="only this deck and its subdecks")
    >>> def _stats(a):
    ...     from studyloop.analysis.report import stats
    ...     return stats(Path(a.export), a.deck, ...)
    >>> reg.add_command(Command("stats", "analyse a manual Anki export (.apkg/.colpkg)",
    ...                         _stats_args, _stats))
    """
    name: str
    help: str
    arguments: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], int]


# ---- the registry ----------------------------------------------------------------------

class Registry:
    """Everything the installed modules registered. Get it with `registry`.

    Attributes
    ----------
    modules : dict
        Name to `Module`, core first.
    deck_kinds : dict
        Name to `DeckKind`.
    card_types : dict
        Name to `CardType`.
    lint_rules : list of LintRule
    commands : dict
        Name to ``(Module, Command)``.
    provides : dict
        Extension point to ``{name: (Module, object)}``; see `provide`.

    Examples
    --------
    >>> reg = registry()
    >>> list(reg.deck_kinds)
    ['plain', 'language', 'project', 'topic']
    >>> list(reg.card_types)
    ['code', 'concept', 'timeline', 'cloze', 'sentence', 'grammar']
    """
    def __init__(self) -> None:
        self.modules: dict[str, Module] = {}
        self.deck_kinds: dict[str, DeckKind] = {}
        self.card_types: dict[str, CardType] = {}
        self.lint_rules: list[LintRule] = []
        self.commands: dict[str, tuple[Module, Command]] = {}
        self.provides: dict[str, dict[str, tuple[Module, Any]]] = {}
        self._current: Module | None = None

    def add_deck_kind(self, k: DeckKind) -> None:
        """Register a deck kind; the name must be unique."""
        self._unique(self.deck_kinds, k.name, "deck kind")
        self.deck_kinds[k.name] = k

    def add_card_type(self, t: CardType) -> None:
        """Register a card type (an instance); the name must be unique."""
        self._unique(self.card_types, t.name, "card type")
        self.card_types[t.name] = t

    def add_lint_rule(self, r: LintRule) -> None:
        """Register a lint rule; rules run in registration order."""
        self.lint_rules.append(r)

    def add_command(self, c: Command) -> None:
        """Register an ``asl`` command; the name must be unique."""
        self._unique(self.commands, c.name, "command")
        self.commands[c.name] = (self._current, c)

    def provide(self, point: str, name: str, obj: Any) -> None:
        """Add to an extension point a module defines for others. Core never looks inside.

        Parameters
        ----------
        point : str
            The extension point, e.g. ``"language"`` or ``"analysis"``.
        name : str
            Unique within the point, e.g. ``"ja"``.
        obj : object
            Whatever the point expects (a `studyloop.language.base.Language`, an
            `studyloop.analysis.types.Analysis`).

        Examples
        --------
        >>> reg.provide("language", "ja", Japanese())        # studyloop/language_ja
        >>> reg.provide("analysis", "leeches", Leeches())    # studyloop/analysis
        """
        table = self.provides.setdefault(point, {})
        self._unique(table, name, point)
        table[name] = (self._current, obj)

    def provided(self, point: str) -> dict[str, tuple[Module, Any]]:
        """Everything provided to an extension point, as ``{name: (module, object)}``.

        Examples
        --------
        >>> module, ja = registry().provided("language")["ja"]
        >>> module.name, ja.name
        ('language_ja', 'Japanese')
        """
        return self.provides.get(point, {})

    def card_type(self, name: str) -> CardType:
        """The card type for a ``type:`` value.

        Raises
        ------
        KeyError
            Unknown type; the message lists the installed ones.

        Examples
        --------
        >>> registry().card_type("cloze").model_name
        'Cloze Card'
        >>> registry().card_type("flashcard")
        KeyError: 'unknown card type `flashcard` (installed: code, concept, timeline, cloze, sentence, grammar)'
        """
        if name not in self.card_types:
            raise KeyError(f"unknown card type `{name}` (installed: {', '.join(self.card_types)})")
        return self.card_types[name]

    def missing(self, m: Module) -> list[str]:
        """Imports of the module's optional install (`Module.needs`) that aren't there.

        Examples
        --------
        >>> reg = registry()
        >>> reg.missing(reg.modules["analysis"])    # without the analysis install
        ['pandas']
        """
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
    """Core plus every installed module (entry points), loaded once per process.

    Examples
    --------
    >>> list(registry().modules)
    ['core', 'analysis', 'language', 'language_ja', 'notes', 'projects', 'sources']
    """
    from importlib.metadata import entry_points

    from studyloop.core import MODULE as CORE
    mods = [CORE]
    for ep in entry_points(group="studyloop.modules"):
        m = ep.load()
        if m.name != "core":
            mods.append(m)
    return load(mods)


def load(modules: list[Module]) -> Registry:
    """A registry from given modules: core first, then the rest by name.

    Tests use it to load a module without installing it.

    Raises
    ------
    SystemExit
        A module's `Module.requires` is missing, or two modules register the same name.

    Examples
    --------
    >>> from studyloop.core import MODULE as CORE
    >>> from studyloop.notes import MODULE as NOTES
    >>> list(load([NOTES, CORE]).modules)
    ['core', 'notes']
    """
    reg = Registry()
    names = {m.name for m in modules}
    for m in sorted(modules, key=lambda m: (m.name != "core", m.name)):
        absent = [r for r in m.requires if r not in names]
        if absent:
            raise SystemExit(f"module `{m.name}` needs {', '.join(absent)}")
        reg._load(m)
    return reg
