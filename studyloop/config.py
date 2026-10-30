"""Where things live: repo assets, packs, decks (deck.yaml) and the card home
(studyloop.yaml)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
ASSETS = Path(__file__).resolve().parent / "assets"

DEFAULT_LIMITS = {
    "code": {"typed_chars_target": 80, "typed_chars_max": 120},
    "concept": {"answer_chars_target": 250, "answer_chars_max": 300,
                "bold_chars_target": 120, "bold_chars_max": 150},
}
DEFAULT_REFRESH = {"mature_share": 0.5, "step_share": 0.25, "min_review_answers": 1000,
                   "min_card_age_days": 30, "mature_ivl_days": 21}
DEFAULT_PRESET = {"new_per_day": 14, "order": "random"}


def _read_yaml(p: Path) -> dict:
    if not p.is_file():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def pack_dirs() -> list[Path]:
    dirs = [Path(d) for d in os.environ.get("ASL_PACKS", "").split(os.pathsep) if d]
    return dirs + [REPO / "packs"]


def find_pack(name: str) -> Path:
    for d in pack_dirs():
        if (d / name / "pack.yaml").is_file():
            return d / name
    raise SystemExit(f"Unknown pack '{name}'. Packs live in: "
                     + ", ".join(str(d) for d in pack_dirs()))


def all_packs() -> list[Path]:
    seen, out = set(), []
    for d in pack_dirs():
        for p in sorted(d.glob("*/pack.yaml")):
            if p.parent.name not in seen and not p.parent.name.startswith("_"):
                seen.add(p.parent.name)
                out.append(p.parent)
    return out


def load_pack(name: str) -> dict:
    d = find_pack(name)
    cfg = _read_yaml(d / "pack.yaml")
    cfg["_dir"] = d
    return cfg


@dataclass
class Home:
    """The card home: a folder (usually in the vault) with studyloop.yaml."""
    path: Path | None
    cfg: dict = field(default_factory=dict)

    @property
    def limits(self) -> dict:
        lim = {k: dict(v) for k, v in DEFAULT_LIMITS.items()}
        for kind, vals in (self.cfg.get("limits") or {}).items():
            lim.setdefault(kind, {}).update(vals or {})
        return lim

    @property
    def refresh(self) -> dict:
        return {**DEFAULT_REFRESH, **(self.cfg.get("refresh") or {})}

    @property
    def standards_version(self) -> int:
        return int(self.cfg.get("standards_version", 1))


def find_home(start: Path) -> Home:
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / "studyloop.yaml").is_file():
            return Home(d, _read_yaml(d / "studyloop.yaml"))
    return Home(None, {})


@dataclass
class Deck:
    """A folder of card files plus its deck.yaml."""
    path: Path
    cfg: dict

    @property
    def name(self) -> str:
        return self.cfg.get("deck") or self.path.name.replace("_", " ").title()

    @property
    def pack(self) -> str | None:
        return self.cfg.get("pack")

    def file_opts(self, f: Path) -> dict:
        return dict((self.cfg.get("files") or {}).get(f.name) or {})

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


def read_keep(p: Path) -> tuple[str, str]:
    """Text with \\n line ends + a format tag (line ending, BOM), so rewriting a
    file on Windows keeps CRLF/LF and a UTF-8 BOM exactly as they were."""
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), ("bom" if bom else "") + nl


def write_keep(p: Path, text: str, fmt: str = "\n") -> None:
    nl = fmt.replace("bom", "") or "\n"
    data = text.replace("\r\n", "\n").replace("\n", nl).encode("utf-8")
    p.write_bytes((b"\xef\xbb\xbf" if fmt.startswith("bom") else b"") + data)
