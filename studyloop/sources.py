"""A topic's sources (books, links) as a map of parts, so an agent reads one part at a time.

    asl sources <deck>               # write the map into the deck's Overview.md
    asl sources <deck> --read tour.3 # print the text of one part (PDF), nothing else

The brief lives in the frontmatter of the deck's Overview.md:

    goal: "Modern C++ for regulated medical software"
    builds_on: [rust]                # contrast cards against what the user knows
    notes: "Studying/C++"            # vault folder for study notes; false = cards straight from the source
    batch: 12000                     # tokens an agent reads per batch (default 12000)
    sources:
      - "Tour of C++ 3rd.pdf"        # a file in the vault (or [[wikilink]], or a path)
      - {file: "Effective Modern C++.pdf", key: emc}
      - https://cliutils.gitlab.io/modern-cmake/
      - {url: "https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines", key: cg,
         parts: ["#S-resource", "#S-errors"]}

PDF parts come from the bookmarks; a chapter longer than `batch` tokens is listed with its
sections. Status counts cards and notes whose `source:` points into a part:
`[[Tour of C++ 3rd.pdf#page=42]]` (page in the PDF file, as Obsidian opens it), a URL, or
a `[[Note]]` whose own `source:` does. Bookmarks and word counts are cached in\n`.asl-sources.json` next to Overview.md.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import cards as C
from . import notes as N
from .config import Deck, read_keep, write_keep

BEGIN, END = "<!-- asl:sources -->", "<!-- asl:sources:end -->"
CACHE = ".asl-sources.json"
TOKENS_PER_WORD = 1.35
DEFAULT_BATCH = 12000
SKIP = re.compile(r"^(cover|half title|title page|copyright( page)?|(table of )?contents|index|"
                  r"dedication|acknowledg(e)?ments|from the publisher|about the authors?|colophon|"
                  r"other books.*|praise for.*)$", re.I)
PAGE_REF = re.compile(r"#(?:page=|p\.?)(\d+)", re.I)


@dataclass
class Part:
    id: str
    title: str
    first: int = 0                  # PDF pages, 1-based, inclusive
    last: int = 0
    url: str = ""
    depth: int = 0
    children: list[Part] = field(default_factory=list)
    words: int | None = None
    notes: int = 0
    cards: int = 0

    def covers(self, ref: tuple[str, int | None]) -> bool:
        kind, page = ref
        if self.url:
            return kind.startswith(self.url)
        return page is not None and self.first <= page <= self.last


@dataclass
class Source:
    key: str
    label: str
    path: Path | None = None
    url: str = ""
    pages: int = 0
    parts: list[Part] = field(default_factory=list)
    problem: str = ""


# ---- the brief ------------------------------------------------------------

def brief(deck: Deck) -> dict:
    ov = deck.path / "Overview.md"
    if not ov.is_file():
        return {}
    meta, _ = N.split_frontmatter(ov.read_text(encoding="utf-8"))
    return meta


def _strip_link(s: str) -> str:
    m = re.fullmatch(r"\s*!?\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]\s*", s)
    return (m.group(1) if m else s).strip()


def _key(text: str, taken: set[str]) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    base = next((w for w in words if w not in {"https", "http", "www", "the", "a", "an"}), "src")
    key, n = base[:12], 2
    while key in taken:
        key, n = f"{base[:10]}{n}", n + 1
    return key


def resolve(deck: Deck, meta: dict) -> list[Source]:
    vault = N.card_vault(deck.path)
    files = N.vault_index(vault)[1] if vault else {}
    out, taken = [], set()
    for raw in meta.get("sources") or []:
        spec = raw if isinstance(raw, dict) else (
            {"url": raw} if re.match(r"https?://", str(raw)) else {"file": raw})
        if spec.get("url"):
            url = str(spec["url"])
            host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
            key = str(spec.get("key") or _key(host, taken))
            src = Source(key, url, url=url)
            parts = spec.get("parts") or []
            src.parts = ([Part(f"{key}.{i}", str(p), url=_join(url, str(p)))
                          for i, p in enumerate(parts, 1)] or [Part(key, "(whole page)", url=url)])
        else:
            name = _strip_link(str(spec.get("file") or ""))
            key = str(spec.get("key") or _key(Path(name).stem, taken))
            p = Path(name).expanduser()
            path = (p if p.is_absolute() and p.is_file() else
                    (deck.path / p) if (deck.path / p).is_file() else files.get(Path(name).name.lower()))
            src = Source(key, Path(name).name, path=path)
            if path is None:
                src.problem = f"{name} not found in the vault"
            elif path.suffix.lower() != ".pdf":
                src.problem = "only PDFs are split into parts; read this file directly"
        taken.add(src.key)
        out.append(src)
    return out


def _join(url: str, part: str) -> str:
    if part.startswith("#"):
        return url.split("#")[0] + part
    if re.match(r"https?://", part):
        return part
    return url.rstrip("/") + "/" + part.lstrip("/")


# ---- PDFs -----------------------------------------------------------------

def _reader(path: Path):
    try:
        import pypdf
    except ImportError as e:            # pragma: no cover
        raise SystemExit("PDF sources need pypdf: reinstall asl (uv tool install --force ...)") from e
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    return pypdf.PdfReader(str(path))


def scan(src: Source, cache: dict) -> list[int]:
    """Bookmarks and words per page of a PDF, from the cache when the file is unchanged.
    Both can be slow (a 300-page book: ~30 s each), so this runs once per file."""
    st = src.path.stat()
    tag = f"{st.st_size}:{int(st.st_mtime)}"
    hit = cache.get(src.path.name)
    if not (hit and hit.get("tag") == tag and "outline" in hit):
        print(f"  reading {src.path.name} (once; cached in {CACHE}) ...", flush=True)
        reader = _reader(src.path)
        hit = {"tag": tag, "outline": _bookmarks(reader),
               "words": [len((pg.extract_text() or "").split()) for pg in reader.pages]}
        cache[src.path.name] = hit
    outline(src, [tuple(x) for x in hit["outline"]], len(hit["words"]))
    return hit["words"]


def _bookmarks(reader) -> list[tuple[int, str, int]]:
    flat: list[tuple[int, str, int]] = []

    def walk(items, depth):
        for it in items:
            if isinstance(it, list):
                walk(it, depth + 1)
                continue
            title = re.sub(r"\s+", " ", str(it.title or "")).strip()
            try:
                page = reader.get_destination_page_number(it) + 1
            except Exception:
                continue
            flat.append((depth, title, page))

    walk(reader.outline, 0)
    return flat


def outline(src: Source, flat: list[tuple[int, str, int]], pages: int) -> None:
    """Bookmarks -> parts with page ranges (chapters + their sections); front matter left out."""
    src.pages = pages
    if not flat:
        src.parts = [Part(src.key, "(no bookmarks: whole file)", 1, src.pages)]
        return
    parent: Part | None = None
    skipping = False
    for i, (depth, title, page) in enumerate(flat):
        if depth == 0:
            skipping = not title or bool(SKIP.match(title))
        if skipping or depth > 1 or not title:
            continue
        nxt = next((p for d, _, p in flat[i + 1:] if d <= depth), src.pages + 1)
        last = max(page, nxt - 1)
        if depth == 0:
            m = re.match(r"(?:chapter|part)?\s*(\d+)\b", title, re.I)
            parent = Part(f"{src.key}.{m.group(1) if m else _slug(title)}", title, page, last)
            src.parts.append(parent)
        elif parent is not None:
            parent.children.append(Part(f"{parent.id}.{len(parent.children) + 1}", title,
                                        page, min(last, parent.last), depth=1))


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:16] or "x"


def _load_cache(deck: Deck) -> dict:
    f = deck.path / CACHE
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except (OSError, ValueError):
        return {}


def text_of(path: Path, first: int, last: int) -> str:
    reader = _reader(path)
    out = []
    for i in range(first - 1, min(last, len(reader.pages))):
        out.append(f"--- page {i + 1} ---\n{reader.pages[i].extract_text() or ''}")
    return "\n".join(out)


# ---- status from cards and notes -----------------------------------------

def _refs(s: str) -> list[tuple[str, int | None]]:
    """(file name or URL, page) for every link in a source string."""
    out = []
    for m in re.finditer(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", s):
        target = m.group(1)
        name = target.split("#")[0].strip()
        pm = PAGE_REF.search(target)
        out.append((name, int(pm.group(1)) if pm else None))
    for m in re.finditer(r"https?://[^\s\"'\])>]+", s):
        out.append((m.group(0), None))
    rest = re.sub(r"\[\[[^\]]*\]\]|https?://\S+", " ", s)
    for m in re.finditer(r"([^\s\"'\[\]]+\.pdf)(#\S+)?", rest, re.I):
        pm = PAGE_REF.search(m.group(2) or "")
        out.append((m.group(1), int(pm.group(1)) if pm else None))
    return out


def _as_list(v) -> str:
    return " ".join(map(str, v)) if isinstance(v, list) else str(v or "")


def count(deck: Deck, meta: dict, sources: list[Source]) -> None:
    note_refs: dict[str, list] = {}          # note name -> its source refs
    folder = meta.get("notes")
    vault = N.card_vault(deck.path)
    if folder:
        nd = Path(str(folder)).expanduser()
        if not nd.is_absolute():
            nd = next((b / nd for b in (vault, deck.path) if b and (b / nd).is_dir()), nd)
        for p in nd.rglob("*.md") if nd.is_dir() else []:
            m, _ = N.split_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
            refs = _refs(_as_list(m.get("source")))
            if refs:
                note_refs[p.stem.lower()] = refs
    card_refs = []
    for f in deck.files():
        for c in C.load_file(f):
            refs = _refs(str(c.get("source") or ""))
            for name, _ in list(refs):
                refs += note_refs.get(name.lower(), [])
            card_refs.append(refs)

    for src in sources:
        def mine(ref, src=src):
            name, _ = ref
            return name.startswith(src.url) if src.url else (
                src.path is not None and name.lower() in (src.path.name.lower(), src.path.stem.lower()))

        for part in src.parts:
            for p in [part, *part.children]:
                p.notes = sum(any(mine(r) and p.covers(r) for r in refs) for refs in note_refs.values())
                p.cards = sum(any(mine(r) and p.covers(r) for r in refs) for refs in card_refs)


# ---- the map --------------------------------------------------------------

def _k(n: int | None) -> str:
    if n is None:
        return "?"
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _status(p: Part) -> str:
    bits = ([f"notes {p.notes}"] if p.notes else []) + ([f"cards {p.cards}"] if p.cards else [])
    return " · ".join(bits) or "todo"


def render(deck: Deck, meta: dict, sources: list[Source]) -> str:
    batch = int(meta.get("batch") or DEFAULT_BATCH)
    per_day = int((deck.presets().get("default") or {}).get("new_per_day") or 10)
    n_cards = sum(len(C.load_file(f)) for f in deck.files())
    done_words = sum(p.words or 0 for s in sources for p in s.parts if p.cards and p.words)
    done_cards = sum(p.cards for s in sources for p in s.parts if p.words)
    rate = done_cards / done_words * 1000 if done_words >= 1000 and done_cards >= 10 else None
    lines = [BEGIN, "## Sources", "",
             f"Written by `asl sources` (and `asl fix`); don't edit. Read one part: "
             f"`asl sources <deck> --read <part>`. Batch: ≤ {batch // 1000}k tokens "
             f"(~{int(batch / TOKENS_PER_WORD / 1000 + .5)}k words).",
             f"Deck: {n_cards} cards = {n_cards / per_day:.1f} days of new cards at "
             f"{per_day}/day." + (f" So far {rate:.1f} cards per 1k words; `~N cards` "
                                  "estimates todo parts from that." if rate else ""), ""]
    for src in sources:
        head = f"**{src.key}**: {src.label}" + (f" ({src.pages} pages)" if src.pages else "")
        lines += [head + (f": {src.problem}" if src.problem else ""), ""]
        if not src.parts:
            continue
        cols = "| part | title | pages | words | ~tokens | status |" if not src.url else \
               "| part | link | status |"
        lines += [cols, "|---|---|---|---|---|---|" if not src.url else "|---|---|---|"]
        for p in src.parts:
            if src.url:
                lines.append(f"| {p.id} | {p.url} | {_status(p)} |")
                continue
            rows = [p]
            if p.words is not None and p.words * TOKENS_PER_WORD > batch:
                rows += p.children
            for r in rows:
                tok = None if r.words is None else int(r.words * TOKENS_PER_WORD)
                title = r.title.replace("|", "/")
                title = ("↳ " if r.depth else "") + (title[:45] + "…" if len(title) > 46 else title)
                est = ""
                if rate and r.words and not r.cards and (r is not p or len(rows) == 1):
                    est = f" (~{rate * r.words / 1000:.0f} cards)"
                big = " ⚠ split" if tok and tok > batch and not (r is p and len(rows) > 1) else ""
                lines.append(f"| {r.id} | {title} | {r.first}–{r.last} | {_k(r.words)} | "
                             f"{_k(tok)}{big} | {_status(r)}{est} |")
        lines.append("")
    return "\n".join(lines + [END])


def write_map(ov: Path, block: str) -> None:
    text, fmt = read_keep(ov)
    if BEGIN in text and END in text:
        pre, rest = text.split(BEGIN, 1)
        text = pre + block + rest.split(END, 1)[1]
    else:
        lines = text.split("\n")
        at = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), len(lines))
        lines[at:at] = [block, ""]
        text = "\n".join(lines)
    write_keep(ov, text, fmt)


def build_map(deck: Deck, quiet: bool = False) -> list[Source] | None:
    meta = brief(deck)
    if not meta.get("sources"):
        return None
    sources = resolve(deck, meta)
    cache = _load_cache(deck)
    before = json.dumps(cache, sort_keys=True)
    for src in sources:
        if src.path is None or src.problem:
            continue
        words = scan(src, cache)
        for p in src.parts:
            for r in [p, *p.children]:
                r.words = sum(words[r.first - 1:r.last])
    if json.dumps(cache, sort_keys=True) != before:
        (deck.path / CACHE).write_text(json.dumps(cache), encoding="utf-8")
    count(deck, meta, sources)
    write_map(deck.path / "Overview.md", render(deck, meta, sources))
    if not quiet:
        todo = sum(1 for s in sources for p in s.parts if _status(p) == "todo")
        print(f"{deck.path.name}: sources map written to Overview.md "
              f"({len(sources)} source(s), {todo} part(s) todo).")
    return sources


def find_part(sources: list[Source], pid: str) -> tuple[Source, Part] | None:
    for s in sources:
        for p in s.parts:
            for r in [p, *p.children]:
                if r.id == pid:
                    return s, r
    return None


def sources(groups, read: str | None = None) -> int:
    for deck, _ in groups:
        if read:
            meta = brief(deck)
            srcs, cache = resolve(deck, meta), _load_cache(deck)
            for s in srcs:
                if s.path is not None and not s.problem:
                    scan(s, cache)
            hit = find_part(srcs, read)
            if hit is None:
                print(f"! no part `{read}` in {deck.path.name}; run `asl sources` and pick an id "
                      "from the map.")
                return 1
            s, p = hit
            if s.url:
                print(f"{p.id}: {p.url}\n(a link: fetch only this part)")
                return 0
            print(f"# {s.label} — {p.title} (pages {p.first}–{p.last})\n")
            print(text_of(s.path, p.first, p.last))
            return 0
        if build_map(deck) is None:
            print(f"{deck.path.name}: no `sources:` in Overview.md's frontmatter; nothing to map.")
    return 0
