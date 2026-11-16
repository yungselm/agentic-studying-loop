"""A deck: a folder of card files plus its deck.yaml (kind, Anki deck name, pack, id prefix,
presets). `resolve_inputs` turns command-line inputs into decks and their files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from studyloop.core.config.paths import _read_yaml

DEFAULT_PRESET = {"new_per_day": 14, "order": "random"}


@dataclass
class Deck:
    """A folder of card files plus its deck.yaml."""
    path: Path
    cfg: dict

    @property
    def kind(self) -> str:
        """`kind:` from deck.yaml (what a deck is for decides the skills, commands and card
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
        return self.cfg.get("deck") or self.path.name.replace("_", " ").title()

    @property
    def pack(self) -> str | None:
        return self.cfg.get("pack")

    def file_opts(self, f: Path) -> dict:
        return dict((self.cfg.get("files") or {}).get(f.name) or {})

    def prefix_for(self, f: Path | None = None) -> str | None:
        """Id prefix for a file: `files: {x.yaml: {prefix: ..}}`, else the deck's."""
        return (self.file_opts(f).get("prefix") if f else None) or self.cfg.get("prefix")

    def prefixes(self) -> list[str]:
        ps = [self.cfg.get("prefix")] + [o.get("prefix") for o in (self.cfg.get("files") or {}).values()
                                         if isinstance(o, dict)]
        return [p for p in dict.fromkeys(ps) if p]

    def checked(self, f: Path) -> bool:
        return bool(self.file_opts(f).get("check", self.cfg.get("check", True)))

    def presets(self) -> dict:
        p = dict(self.cfg.get("presets") or {})
        p.setdefault("default", dict(DEFAULT_PRESET))
        return p

    def files(self, include_examples=False) -> list[Path]:
        fs = sorted(p for p in self.path.glob("*.yaml") if p.name != "deck.yaml")
        if not include_examples:
            fs = [p for p in fs if not p.name.startswith("_")]
        order = self.cfg.get("order") or []
        rank = {stem: i for i, stem in enumerate(order)}
        return sorted(fs, key=lambda p: (rank.get(p.stem, len(rank)), p.stem))


def load_deck(folder: Path) -> Deck:
    folder = folder.resolve()
    return Deck(folder, _read_yaml(folder / "deck.yaml"))


def resolve_inputs(args: list[str]) -> list[tuple[Deck, list[Path]]]:
    """CLI inputs (deck folders or single card files) -> [(deck, files)].

    A folder builds all its files except `_examples`; a file passed by name is
    always used (that's how you preview an example)."""
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
