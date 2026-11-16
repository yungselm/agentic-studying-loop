"""The vault: a folder of markdown notes (Obsidian or any other) that cards link into.

Optional. With one, build and lint resolve `[[Note]]`, `![[image.png]]` and `source:` links
against it; without one, link resolution is off and cards build anyway."""
from __future__ import annotations

import functools
from pathlib import Path

import yaml

from studyloop.core.config.home import find_home
from studyloop.core.config.paths import native_path

NO_VAULT = {None, False, "", "none"}


def split_frontmatter(text: str) -> tuple[dict, list[str]]:
    """(YAML frontmatter as a dict, the remaining lines) of a markdown file."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                try:
                    meta = yaml.safe_load("\n".join(lines[1:i])) or {}
                except yaml.YAMLError:
                    meta = {}
                return (meta if isinstance(meta, dict) else {}), lines[i + 1:]
    return {}, lines


def vault_for(path: Path) -> Path | None:
    """The vault a deck (or a note) links into: `vault:` in the card home's studyloop.yaml
    (`none`: no vault; a relative path is relative to the card home), else the nearest folder
    with `.obsidian` (card homes from before the setting), else None."""
    path = Path(path).resolve()
    home = find_home(path)
    if home.path and "vault" in home.cfg:
        v = home.cfg["vault"]
        if v in NO_VAULT:
            return None
        p = native_path(v)
        return p if p.is_absolute() else (home.path / p).resolve()
    for p in [path, *path.parents]:
        if (p / ".obsidian").is_dir():
            return p
    return None


@functools.lru_cache(maxsize=8)
def vault_index(vault: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    """(note name or alias -> note, file name -> file), lower-cased, for card links."""
    notes, files = {}, {}
    for p in vault.rglob("*"):
        if ".obsidian" in p.parts or not p.is_file():
            continue
        files.setdefault(p.name.lower(), p)
        if p.suffix.lower() == ".md":
            notes.setdefault(p.stem.lower(), p)
            try:
                meta, _ = split_frontmatter(p.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            al = meta.get("aliases") or []
            for a in [al] if isinstance(al, str) else al:
                notes.setdefault(str(a).lower(), p)
    return notes, files


def vault_rel(p: Path, vault: Path | None) -> str:
    """A path as the vault sees it (relative), else absolute."""
    try:
        return p.relative_to(vault).as_posix() if vault else p.as_posix()
    except ValueError:
        return p.as_posix()


def resolve_in(base: Path, s: str) -> Path:
    """A path the user typed: absolute, relative to the current folder if it exists there,
    else relative to `base` (the vault)."""
    p = Path(s).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (Path.cwd() / p).resolve() if (Path.cwd() / p).exists() else (base / p).resolve()
