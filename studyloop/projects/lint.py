"""Lint rule for project decks (`kind: project`: code from a repo, see profile.md).

  [header]   a code section doesn't start with `<comment> <path>  (<role>)` matching profile.md
  [excerpt]  an unchecked (`check: false`) card's code isn't verbatim from the repo
  [std]      a card doesn't record the standards version it was written under
  [source]   `source:` points at a file/name the repo no longer has (drift hint)
  [repo]     deck.yaml's `repo:` isn't there; [index] no Overview.md card index
(The context frame, [frame], is the code card's own check: `!` in project decks.)
"""
from __future__ import annotations

import re
from pathlib import Path

from studyloop.core.config import Deck
from studyloop.core.registry import DeckSummary, Flag, LintContext, LintRule

ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|")


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


def card_flags(card: dict, ctx: LintContext) -> list[Flag]:
    roles = ctx.once("project.roles", lambda: file_roles(ctx.deck))
    repo = ctx.once("project.repo", lambda: _existing_repo(ctx.deck))
    checked = ctx.deck.checked(ctx.file)
    out = []
    cp = ctx.pack.get("comment_prefix")
    if not card.get("std"):
        out.append(Flag("~", "std", "no `std:` (standards version the card was written under)"))
    if repo is not None:
        out += source_flags(card, repo)
    if card["type"] != "code" or not cp:
        return out
    sol = card.get("solution") or ""
    secs = sections(sol, cp)
    hr = header_re(cp)

    def lead_ok(code: str) -> bool:
        """Starts with a location header, or with a `stubs (real: ...)` block
        followed by one (checked files put the header above the mirrored code)."""
        first = next((ln.strip() for ln in (code or "").splitlines() if ln.strip()), "")
        has_header = any(hr.match(ln) for ln in (code or "").splitlines())
        return bool(hr.match(first)) or (first.startswith(f"{cp} stubs") and has_header)

    if not lead_ok(sol):
        out.append(("!", "header", f"code doesn't start with `{cp} <path>  (<role>)` "
                    f"(or a `{cp} stubs (real: ...)` block followed by one)"))
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
    if lead_ok(sol) and not lead_ok(card.get("starter") or ""):
        out.append(("!", "header", "starter must start like the solution (header or stubs block)"))
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


def _existing_repo(deck: Deck) -> Path | None:
    r = repo_dir(deck)
    return r if r is not None and r.is_dir() else None


def deck_flags(deck: Deck, summary: DeckSummary) -> list[Flag]:
    out = []
    repo = repo_dir(deck)
    if repo is not None and not repo.is_dir():
        out.append(Flag("!", "repo", f"repo path in deck.yaml not found: {repo}"))
    if summary.whole and not (deck.path / "Overview.md").is_file():
        out.append(Flag("~", "index", "no Overview.md card index in this deck"))
    return out


RULE = LintRule("project", kinds=("project",), card=card_flags, deck=deck_flags)
