"""Check study notes against the study-note style (skimmable, visual, linked).

    asl notes [folders or .md files]     default: the notes folder in ./CLAUDE.md

Concept and lecture notes (`type: concept` / `type: lecture`; lectures default to ~800 words):
  [tldr]     no `> [!tldr]` callout before the first `##` section           (!)
  [visual]   no Mermaid diagram or image embed                              (!)
  [embed]    an embedded file (`![[x.png]]`) doesn't exist in the vault     (!)
  [budget]   more visible prose than the budget (default ~250 words; code,
             diagrams and folded callouts don't count). A guide, not a cap:
             a complex note sets `budget: 600` in its frontmatter           (~)
  [wall]     a paragraph over 60 words                                      (~)
  [links]    fewer than 2 links to other notes                              (~)
  [recall]   no `> [!question]-` self-test                                  (~)
  [filler]   LLM filler ("it's important to note", "in summary", ...)       (~)
  [orphan]   no other note links here                                       (~)
  [index]    not listed in the folder's overview (`Overview - *.md` or a MOC,
             in this folder or the nearest parent that has one)             (~)
Overviews (`type: overview`):
  [map]      no Mermaid map, or a concept note of the folder isn't on it    (~)
  [todo]     a [[link]] to a note that doesn't exist and isn't planned in the
             overview (e.g. under *Next*)                                   (~)
Card-home files (`scope: anki`) are skipped.

`!` = must fix (exit code 1), `~` = worth a look.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

BUDGET = 250
WALL = 60
MIN_LINKS = 2
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".avif", ".pdf",
             ".canvas", ".excalidraw", ".mp4", ".webm", ".mp3", ".m4a"}

FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w-]*)")
CALLOUT = re.compile(r"^>\s*\[!(\w+)\]([-+]?)")
WIKI = re.compile(r"(!?)\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|([^\]]*))?\]\]")
MD_IMG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
FILLER = re.compile(
    r"\b(it(?:'|’)?s (?:important|worth) (?:to note|noting)|in summary|in conclusion|"
    r"let(?:'|’)?s dive|dive into|delve|essentially,|to summari[sz]e|in this note,? we|"
    r"as mentioned (?:above|earlier)|overall,)", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
TLDR = {"tldr", "summary", "abstract"}
CHECKED = {"concept", "lecture"}
LECTURE_BUDGET = 800           # a lecture note covers several ideas


@dataclass
class Note:
    path: Path
    meta: dict
    body: list[str]                       # lines after the frontmatter
    links: set[str] = field(default_factory=set)       # lower-cased targets of [[...]]
    embeds: list[str] = field(default_factory=list)
    has_visual: bool = False
    mermaid: list[str] = field(default_factory=list)   # source of each mermaid block

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def kind(self) -> str:
        t = str(self.meta.get("type", "")).lower()
        if t:
            return t
        tags = self.meta.get("tags") or []
        tags = tags if isinstance(tags, list) else [tags]
        if self.name.lower().endswith("moc") or any(str(x).lower().split("/")[-1] == "moc" for x in tags):
            return "overview"              # a map of content counts as the overview
        return ""


def split_frontmatter(text: str) -> tuple[dict, list[str]]:
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


def _unquote(ln: str) -> str:
    """The line without callout/quote markers (`> > x` -> `x`)."""
    return re.sub(r"^(\s*>\s?)+", "", ln)


def parse(path: Path) -> Note:
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    n = Note(path, meta, body)
    fence, lang, buf = None, "", []
    for ln in body:
        m = FENCE.match(_unquote(ln))
        if fence is None and m:
            fence, lang, buf = m.group(1), m.group(2).lower(), []
            continue
        if fence is not None:
            u = _unquote(ln).strip()
            if u.startswith(fence) and u.strip(fence[0]) == "":
                if lang == "mermaid":
                    n.has_visual = True
                    n.mermaid.append("\n".join(buf))
                fence = None
            else:
                buf.append(_unquote(ln))
            continue
        for bang, target, _alias in WIKI.findall(ln):
            t = target.strip()
            if bang:
                n.embeds.append(t)
                if Path(t).suffix.lower() in IMAGE_EXT:
                    n.has_visual = True
                else:
                    n.links.add(_key(t))           # an embedded note is also a link
            else:
                n.links.add(_key(t))
        if MD_IMG.search(ln):
            n.has_visual = True
    return n


def _key(target: str) -> str:
    t = target.strip().split("/")[-1]
    return (t[:-3] if t.lower().endswith(".md") else t).lower()


def prose(note: Note) -> tuple[list[str], list[str]]:
    """(visible prose lines, callout types in order). Skips fences, headings,
    folded callouts and tables; strips list and quote markers."""
    out, callouts = [], []
    fence, folded = None, False
    for ln in note.body:
        m = FENCE.match(_unquote(ln))
        if fence is None and m:
            fence = m.group(1)
            continue
        if fence is not None:
            u = _unquote(ln).strip()
            if u.startswith(fence) and u.strip(fence[0]) == "":
                fence = None
            continue
        c = CALLOUT.match(ln)
        if c:
            callouts.append(c.group(1).lower() + c.group(2))
            folded = c.group(2) == "-"
            title = ln[c.end():].strip()
            out.append("" if folded else title)
            continue
        if ln.startswith(">"):
            out.append("" if folded else ln.lstrip("> ").rstrip())
            continue
        folded = False
        s = ln.strip()
        if s.startswith("#") or s.startswith("|"):
            out.append("")
            continue
        item = re.match(r"^([-*+]|\d+[.)])\s+", s)
        if item:
            out.append("")                 # each list item is its own paragraph
        out.append(s[item.end():] if item else s)
    return out, callouts


def _words(s: str) -> list[str]:
    s = WIKI.sub(lambda m: m.group(3) or m.group(2), s)
    s = re.sub(r"\]\([^)]*\)", "]", s)            # [text](url): count the text only
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"`[^`]*`", " x ", s)
    return re.findall(r"[\w'’-]+", s)


def paragraphs(lines: list[str]) -> list[str]:
    paras, cur = [], []
    for ln in lines + [""]:
        if ln.strip():
            cur.append(ln)
        elif cur:
            paras.append(" ".join(cur))
            cur = []
    return paras


def find_vault(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".obsidian").is_dir():
            return p
    return start.parent if start.parent != start else start


def notes_dir_from_claude_md(cwd: Path) -> Path | None:
    f = cwd / "CLAUDE.md"
    if not f.is_file():
        return None
    m = re.search(r"\*\*Study notes for this project:\*\*\s*`([^`]+)`", f.read_text(encoding="utf-8"))
    if not m:
        return None
    p = Path(m.group(1)).expanduser()
    return (p if p.is_absolute() else cwd / p).resolve()


def check_notes(targets: list[Path], vault: Path,
                budget: int = BUDGET) -> list[tuple[str, str, Path, str]]:
    """Return (severity, kind, path, message) for every finding."""
    all_md = [p for p in vault.rglob("*.md") if ".obsidian" not in p.parts and ".trash" not in p.parts]
    files = {p.name.lower() for p in vault.rglob("*") if p.is_file() and ".obsidian" not in p.parts}
    parsed = {p: parse(p) for p in all_md}
    names = {p.stem.lower() for p in all_md}
    for n in parsed.values():
        al = n.meta.get("aliases") or []
        names |= {str(a).lower() for a in (al if isinstance(al, list) else [al])}
    incoming: dict[str, int] = {}
    for n in parsed.values():
        for t in n.links - {n.name.lower()}:
            incoming[t] = incoming.get(t, 0) + 1

    out = []
    for path in targets:
        n = parsed.get(path) or parse(path)
        if n.meta.get("scope") == "anki":
            continue                       # card home files (card index, standards)
        warn = lambda sev, kind, msg, n=n: out.append((sev, kind, n.path, msg))  # noqa: E731
        ov = _overviews(n, parsed, vault)
        planned = set().union(*(o.links for o in ov))
        if n.kind != "overview":
            for t in sorted(n.links - names - planned):
                warn("~", "todo", f"[[{t}]] doesn't exist yet: write it, or list it under "
                     "*Next* in the overview")
        if n.kind == "overview":
            _check_overview(n, parsed, warn)
            continue
        if n.kind not in CHECKED:
            continue
        lines, callouts = prose(n)
        first = next((i for i, ln in enumerate(n.body) if ln.startswith("## ")), len(n.body))
        head = [CALLOUT.match(ln) for ln in n.body[:first]]
        if not any(m and m.group(1).lower() in TLDR for m in head):
            warn("!", "tldr", "no `> [!tldr]` callout before the first `##` section")
        if not n.has_visual:
            warn("!", "visual", "no Mermaid diagram or image: add one to the first screen")
        for e in n.embeds:
            if Path(e).suffix and Path(e).suffix.lower() != ".md" and Path(e).name.lower() not in files:
                warn("!", "embed", f"![[{e}]] not found in the vault")
        words = sum(len(_words(ln)) for ln in lines)
        try:
            limit = int(n.meta.get("budget", LECTURE_BUDGET if n.kind == "lecture" else budget))
        except (TypeError, ValueError):
            limit = budget
        if words > limit:
            warn("~", "budget", f"{words} words of visible prose (budget ~{limit}): fold "
                 "details (`> [!note]-`), split off a sub-idea, or if the topic needs it, "
                 "set `budget:` in the frontmatter")
        for p in paragraphs(lines):
            if len(_words(p)) > WALL:
                warn("~", "wall", f"{len(_words(p))}-word paragraph: \"{p[:50]}...\"")
        others = n.links - {n.name.lower()}
        if len(others) < MIN_LINKS:
            warn("~", "links", f"{len(others)} link(s) to other notes (want ≥ {MIN_LINKS}, each with a reason)")
        if not any(c.startswith("question") for c in callouts):
            warn("~", "recall", "no `> [!question]-` self-test")
        text = "\n".join(lines)
        for f in sorted({m.group(0).lower() for m in FILLER.finditer(text)}):
            warn("~", "filler", f"\"{f}\": cut it")
        if EMOJI.search(text):
            warn("~", "filler", "emoji in the text: the callout icons are the markers")
        if not incoming.get(n.name.lower()):
            warn("~", "orphan", "no other note links here: add it to the overview or a related note")
        if ov and not any(n.name.lower() in o.links for o in ov):
            warn("~", "index", f"not in {ov[0].path.name}")
        elif not ov:
            warn("~", "index", "no overview (`Overview - *.md` or a MOC) in this or a parent folder")
    return out


def _overviews(n: Note, parsed: dict, vault: Path) -> list[Note]:
    """Overviews of the note's folder; else of the nearest parent folder that has one."""
    folder = n.path.parent
    while True:
        ov = [o for p, o in parsed.items() if p.parent == folder and o.kind == "overview" and o is not n]
        if ov or folder == vault or folder == folder.parent or vault not in folder.parents:
            return ov
        folder = folder.parent


def _check_overview(n: Note, parsed: dict, warn) -> None:
    if not n.mermaid:
        warn("~", "map", "no Mermaid map of the notes (see the study-note skill)")
        return
    src = "\n".join(n.mermaid).lower()
    for p, o in parsed.items():
        if p.parent == n.path.parent and o.kind in CHECKED and o.name.lower() not in src:
            warn("~", "map", f"[[{o.name}]] isn't on the map")


def notes(inputs: list[str], vault: Path | None = None, quiet: bool = False,
          budget: int = BUDGET) -> int:
    roots = [Path(i).expanduser().resolve() for i in inputs]
    if not roots:
        d = notes_dir_from_claude_md(Path.cwd())
        if not d:
            print("no notes folder given, and no `**Study notes for this project:**` line in ./CLAUDE.md")
            return 2
        roots = [d]
    missing = [r for r in roots if not r.exists()]
    if missing:
        print(f"not found: {', '.join(map(str, missing))}")
        return 2
    vault = (vault.expanduser().resolve() if vault else
             find_vault(roots[0] if roots[0].is_dir() else roots[0].parent))
    targets = sorted({p for r in roots for p in ([r] if r.is_file() else r.rglob("*.md"))
                      if ".obsidian" not in p.parts})
    found = check_notes(targets, vault, budget)
    hard = sum(1 for s, *_ in found if s == "!")
    soft = len(found) - hard
    for sev, kind, path, msg in found:
        if quiet and sev == "~":
            continue
        try:
            where = path.relative_to(vault)
        except ValueError:
            where = path
        print(f"{sev} [{kind}] {where} -> {msg}")
    if found:
        print(f"\n{hard} problem(s) (!), {soft} note(s) (~) in {len(targets)} file(s)"
              + (" (~ hidden by --quiet)" if quiet and soft else "") + ".")
    else:
        print(f"OK - {len(targets)} note(s) pass.")
    return 1 if hard else 0
