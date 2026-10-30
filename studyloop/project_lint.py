"""Checks for project decks (a deck folder with profile.md or `repo:` in deck.yaml).

  [frame]    a code card shows no enclosing function / type
  [header]   a code section doesn't start with `<comment> <path>  (<role>)` matching profile.md
  [excerpt]  an unchecked (`check: false`) card's code isn't verbatim from the repo
  [index]    a card has no row in Overview.md (or a row has no card)
  [std]      a card doesn't record the standards version it was written under
  [source]   `source:` points at a file/name the repo no longer has (drift hint)
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import Deck

ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|")


def is_project(deck: Deck) -> bool:
    return bool(deck.cfg.get("repo")) or (deck.path / "profile.md").is_file()


def repo_dir(deck: Deck) -> Path | None:
    r = deck.cfg.get("repo")
    if not r:
        return None
    p = Path(r).expanduser()
    return (p if p.is_absolute() else deck.path / p).resolve()


def file_roles(deck: Deck) -> dict[str, str]:
    prof = deck.path / "profile.md"
    if not prof.is_file():
        return {}
    roles = {}
    for ln in prof.read_text(encoding="utf-8").splitlines():
        m = ROW.match(ln.strip())
        if m and m.group(1) not in ("src/...",):
            roles[m.group(1)] = m.group(2).strip()
    return roles


def header_re(cp: str) -> re.Pattern:
    """`# src/pkg/file.py  (role)`: column 0, two spaces before the role."""
    return re.compile(rf"^{re.escape(cp)} (\S+\.\w+) {{2,}}\((.+)\)\s*$")


def sections(code: str, cp: str) -> list[tuple[str | None, list[str]]]:
    """Split code at location headers -> [(path or None, lines)]."""
    hr = header_re(cp)
    out: list[tuple[str | None, list[str]]] = [(None, [])]
    for ln in (code or "").splitlines():
        m = hr.match(ln)
        if m:
            out.append((m.group(1), []))
        else:
            out[-1][1].append(ln)
    return [s for s in out if s[0] or any(x.strip() for x in s[1])]


def _skip(line: str, cp: str) -> bool:
    s = line.strip()
    return (not s or (s.startswith(cp) and ("..." in s or s[len(cp):].strip().startswith("uses:")))
            or s.startswith(f"{cp} stubs"))


def excerpt_problem(lines: list[str], source: list[str], cp: str) -> str | None:
    """Every non-elision line must appear in the source, in order."""
    src = [s.strip() for s in source]
    pos = 0
    for ln in lines:
        if _skip(ln, cp):
            continue
        want = ln.strip()
        try:
            pos = src.index(want, pos) + 1
        except ValueError:
            return f"not in source (in this order): {want[:70]}"
    return None


def check_card(deck: Deck, card: dict, lint_cfg: dict, checked: bool,
               roles: dict[str, str], repo: Path | None) -> list[tuple[str, str, str]]:
    out = []
    project = is_project(deck)
    cp = lint_cfg.get("comment_prefix")
    if project and not card.get("std"):
        out.append(("~", "std", "no `std:` (standards version the card was written under)"))
    if repo is not None:
        out += source_flags(card, repo)
    if card["type"] != "code":
        return out
    sol = card.get("solution") or ""
    frame = lint_cfg.get("frame")
    if frame and not re.search(frame, sol, re.M):
        out.append(("!" if project else "~", "frame",
                    "no enclosing function/type visible (context frame, standards §2a)"))
    if not (project and cp):
        return out
    secs = sections(sol, cp)
    if not secs or secs[0][0] is None:
        out.append(("!", "header", f"code doesn't start with `{cp} <path>  (<role>)`"))
    hr = header_re(cp)
    for ln in sol.splitlines():
        m = hr.match(ln)
        if not m:
            continue
        path, role = m.group(1), m.group(2).strip()
        if roles and path not in roles:
            out.append(("!", "header", f"{path} has no row in profile.md's file roles"))
        elif roles and roles[path] != role:
            out.append(("!", "header", f"role for {path} should be ({roles[path]})"))
        if repo and not (repo / path).is_file():
            out.append(("!", "header", f"{path} doesn't exist in the repo ({repo})"))
    start_first = next((ln for ln in (card.get("starter") or "").splitlines() if ln.strip()), "")
    if secs and secs[0][0] and not hr.match(start_first):
        out.append(("!", "header", "starter must start with the same location header"))
    if not checked:
        if repo is None:
            out.append(("~", "excerpt", "set `repo:` in deck.yaml to verify excerpts"))
        else:
            for path, lines in secs:
                if path and (repo / path).is_file():
                    src = (repo / path).read_text(encoding="utf-8").splitlines()
                    msg = excerpt_problem(lines, src, cp)
                    if msg:
                        out.append(("!", "excerpt", f"{path}: {msg}"))
    return out


def source_flags(card: dict, repo: Path) -> list[tuple[str, str, str]]:
    """`source: "src/x.py → Store.save"`: the file and the name still exist (drift hint)."""
    src = str(card.get("source") or "")
    m = re.match(r"\s*(\S+\.\w+)\s*(?:→|->)\s*([\w.:]+)", src)
    if not m:
        return []
    path, name = m.group(1), re.split(r"[.:]+", m.group(2))[-1]
    f = repo / path
    if not f.is_file():
        return [("~", "source", f"{path} not found in the repo (moved? mark `needs update`)")]
    if not re.search(rf"\b{re.escape(name)}\b", f.read_text(encoding="utf-8")):
        return [("~", "source", f"`{name}` no longer in {path} (renamed? mark `needs update`)")]
    return []


def check_index(deck: Deck, card_ids: list[str]) -> list[tuple[str, str, str]]:
    ov = deck.path / "Overview.md"
    if not ov.is_file():
        return [("~", "index", "no Overview.md card index in this deck")] if is_project(deck) else []
    text = ov.read_text(encoding="utf-8")
    out = [("!", "index", f"{cid} has no row in Overview.md")
           for cid in card_ids if not re.search(rf"(?<![\w-]){re.escape(cid)}(?![\w-])", text)]
    prefix = deck.cfg.get("prefix")
    if prefix:
        listed = set(re.findall(rf"^\|\s*({re.escape(prefix)}-\d+)\s*\|", text, re.M))
        retired = {str(i) for i in deck.cfg.get("retired_ids") or []}
        out += [("~", "index", f"Overview.md row {cid} has no card (add it to retired_ids?)")
                for cid in sorted(listed - set(card_ids) - retired)]
    return out
