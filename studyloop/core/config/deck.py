"""A deck: a folder of card files plus its deck.yaml (kind, Anki deck name, pack, id prefix,
presets). `resolve_inputs` turns command-line inputs into decks and their files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from studyloop.core.config.paths import _read_yaml

DEFAULT_PRESET = {"new_per_day": 14, "order": "random"}


@dataclass
class Deck:
    """A folder of card files plus its deck.yaml. Get one with `load_deck`.

    Attributes
    ----------
    path : Path
        The deck folder (absolute).
    cfg : dict
        deck.yaml as read (fields: docs, "Card format").

    Examples
    --------
    >>> d = load_deck(Path("example-vault/Studying/Anki cards/tasklog"))
    >>> d.name, d.kind, d.pack, d.prefixes()
    ('Study Loop::Tasklog', 'project', 'python', ['tsk'])
    >>> [f.name for f in d.files()]
    ['tasklog.yaml', 'tasklog_ext.yaml', 'tasklog_notes.yaml']
    >>> d.checked(d.files()[1])          # `files: {tasklog_ext.yaml: {check: false}}`
    False
    """
    path: Path
    cfg: dict

    @property
    def kind(self) -> str:
        """``kind:`` from deck.yaml (what a deck is for decides the skills, commands and card
        types), else the first detected kind."""
        from studyloop.core.registry import registry
        k = self.cfg.get("kind")
        return k if k in registry().deck_kinds else self.detected_kinds()[0]

    def detected_kinds(self) -> list[str]:
        """What a deck without `kind:` (made before it) looks like, by each kind's `detect`;
        none → the fallback kind (topic), else plain. Two at once: lint asks for `kind:`."""
        from studyloop.core.registry import registry
        kinds = registry().deck_kinds.values()
        out = [k.name for k in kinds if k.detect and k.detect(self)]
        return out or [k.name for k in kinds if k.fallback][:1] or ["plain"]

    @property
    def kind_spec(self):
        """The registered DeckKind of this deck."""
        from studyloop.core.registry import registry
        return registry().deck_kinds[self.kind]

    @property
    def name(self) -> str:
        """The Anki deck name: ``deck:``, else the folder name."""
        return self.cfg.get("deck") or self.path.name.replace("_", " ").title()

    @property
    def pack(self) -> str | None:
        """The default pack (``pack:``), or None."""
        return self.cfg.get("pack")

    def file_opts(self, f: Path) -> dict:
        """Per-file overrides from ``files:``."""
        return dict((self.cfg.get("files") or {}).get(f.name) or {})

    def prefix_for(self, f: Path | None = None) -> str | None:
        """Id prefix for a file: `files: {x.yaml: {prefix: ..}}`, else the deck's."""
        return (self.file_opts(f).get("prefix") if f else None) or self.cfg.get("prefix")

    def prefixes(self) -> list[str]:
        """Every id prefix in use (the deck's and per-file ones)."""
        ps = [self.cfg.get("prefix")] + [o.get("prefix") for o in (self.cfg.get("files") or {}).values()
                                         if isinstance(o, dict)]
        return [p for p in dict.fromkeys(ps) if p]

    def checked(self, f: Path) -> bool:
        """Whether ``asl check`` runs this file's code (``check:``, per file or deck)."""
        return bool(self.file_opts(f).get("check", self.cfg.get("check", True)))

    def presets(self) -> dict:
        """Anki deck options by preset name; ``default`` is always there."""
        p = dict(self.cfg.get("presets") or {})
        p.setdefault("default", dict(DEFAULT_PRESET))
        return p

    def files(self, include_examples=False) -> list[Path]:
        """The card files, in ``order:`` then by name; ``_example`` files only on request."""
        fs = sorted(p for p in self.path.glob("*.yaml") if p.name != "deck.yaml")
        if not include_examples:
            fs = [p for p in fs if not p.name.startswith("_")]
        order = self.cfg.get("order") or []
        rank = {stem: i for i, stem in enumerate(order)}
        return sorted(fs, key=lambda p: (rank.get(p.stem, len(rank)), p.stem))


def load_deck(folder: Path) -> Deck:
    """Read a deck folder's deck.yaml (an empty config if there is none).

    Examples
    --------
    >>> load_deck(Path("examples/python-core")).name
    'Study Loop Examples::Python'
    """
    folder = folder.resolve()
    return Deck(folder, _read_yaml(folder / "deck.yaml"))


def resolve_inputs(args: list[str]) -> list[tuple[Deck, list[Path]]]:
    """Command-line inputs (deck folders or single card files) to ``[(deck, files)]``.

    A folder gives all its files except ``_examples``; a file passed by name is always used
    (that's how you preview an example). Files of one deck are grouped.

    Parameters
    ----------
    args : list of str
        Paths; empty means the current folder.

    Raises
    ------
    SystemExit
        A path that doesn't exist.

    Examples
    --------
    >>> [(d.name, [f.name for f in fs]) for d, fs in resolve_inputs(["examples/python-core"])]
    [('Study Loop Examples::Python', ['collections.yaml', 'files.yaml'])]
    """
    groups: dict[Path, tuple[Deck, list[Path]]] = {}
    for a in args or ["."]:
        p = Path(a).expanduser()
        if p.is_dir():
            deck = load_deck(p)
            files = deck.files()
        elif p.is_file():
            deck = load_deck(p.parent)
            files = [p.resolve()]
        else:
            raise SystemExit(f"Not found: {a}")
        entry = groups.setdefault(deck.path, (deck, []))
        entry[1].extend(f for f in files if f not in entry[1])
    return list(groups.values())
