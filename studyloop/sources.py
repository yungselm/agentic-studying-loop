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
      - "CS231n/_attachements"       # a folder: every PDF in it, one source per file
      - {url: "https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines", key: cg,
         parts: ["#S-resource", "#S-errors"]}

PDF parts come from the bookmarks; a chapter longer than `batch` tokens is listed with its
sections, and one without sections (or a PDF without bookmarks, like slides) in page chunks. Status counts cards and notes whose `source:` points into a part:
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
    first: int = 0                  # PDF pages or Markdown lines, 1-based, inclusive
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
    unit: str = "pages"             # Markdown sources count lines
    also: str = ""                  # a Markdown file's web address (cards may cite either)
    index: dict[str, int] = field(default_factory=dict)   # anchor / rule id -> line


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
    """Short id for a source: the first word, plus its number for numbered files
    ("Lecture 03 - Optimization" -> lecture03)."""
    m = re.match(r"\s*([A-Za-z]+)[\s_.-]*(\d+)", text)
    words = re.findall(r"[a-z0-9]+", text.lower())
    base = (m.group(1).lower() + m.group(2)) if m else next(
        (w for w in words if w not in {"https", "http", "www", "the", "a", "an"}), "src")
    key, n = base[:12], 2
    while key in taken:
        key, n = f"{base[:10]}{n}", n + 1
    return key


def _folder(deck: Deck, vault: Path | None, name: str) -> Path | None:
    p = Path(name).expanduser()
    if p.is_absolute():
        return p if p.is_dir() else None
    return next((b / p for b in (vault, deck.path) if b and (b / p).is_dir()), None)


def _expand(deck: Deck, vault: Path | None, raw) -> list:
    """A folder as a source -> its PDFs (and slides, flagged) in name order."""
    if isinstance(raw, dict) or re.match(r"https?://", str(raw)):
        return [raw]
    d = _folder(deck, vault, _strip_link(str(raw)))
    if d is None:
        return [raw]
    found = sorted(f for f in d.iterdir() if f.suffix.lower() in (".pdf", ".pptx", ".ppt", ".key"))
    pdfs = {f.stem.lower() for f in found if f.suffix.lower() == ".pdf"}
    found = [f for f in found if f.suffix.lower() == ".pdf" or f.stem.lower() not in pdfs]
    return [{"file": str(f)} for f in found] or [raw]


def resolve(deck: Deck, meta: dict) -> list[Source]:
    vault = N.card_vault(deck.path)
    files = N.vault_index(vault)[1] if vault else {}
    out, taken = [], set()
    for raw in [x for r in meta.get("sources") or [] for x in _expand(deck, vault, r)]:
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
            src = Source(key, Path(name).name, path=path, also=str(spec.get("also_url") or ""))
            if path is not None and path.suffix.lower() in (".md", ".markdown", ".txt"):
                src.unit = "lines"
            if path is None:
                src.problem = f"{name} not found in the vault"
            elif path.suffix.lower() in (".pptx", ".ppt", ".key"):
                src.problem = "slides: export to PDF next to it (Obsidian links PDF pages, asl maps them)"
            elif path.suffix.lower() != ".pdf" and src.unit != "lines":
                src.problem = "only PDF and Markdown files are split into parts; read it directly"
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


def outline(src: Source, flat: list[tuple[int, str, int]], pages: int,
            unit_ids: bool = False) -> None:
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
            short = re.match(r"([A-Za-z]{1,5}):\s", title) if unit_ids else None
            pid = short.group(1) if short else m.group(1) if m else _slug(title)
            parent = Part(f"{src.key}.{pid}", title, page, last)
            src.parts.append(parent)
        elif parent is not None:
            short = re.match(r"([A-Za-z]{1,5}\.[\w.-]+):", title) if unit_ids else None
            cid = (f"{src.key}.{short.group(1)}" if short else
                   f"{parent.id}.{'s' if unit_ids else ''}{len(parent.children) + 1}")
            taken = {c.id for c in parent.children}
            cid, n = (cid, 2) if cid not in taken else (f"{cid}{2}", 3)
            while cid in taken:
                cid, n = f"{cid[:-1]}{n}", n + 1
            parent.children.append(Part(cid, title, page, min(last, parent.last), depth=1))


MD_HEAD = re.compile(r"^(#{1,2})\s+(.*)$")
MD_ANCHOR = re.compile(r'<a\s+name="([^"]+)"\s*>\s*</a>|\{#([\w-]+)\}')
RULE_ID = re.compile(r"\b([A-Z][A-Za-z]{0,4}\.\d+)\b")


def scan_md(src: Source) -> list[int]:
    """A long Markdown document (e.g. the C++ Core Guidelines): `#` headings are parts, `##`
    their sections; anchors and rule ids (`R.1:` at a heading) index lines for the status."""
    lines = src.path.read_text(encoding="utf-8", errors="replace").splitlines()
    src.pages = len(lines)
    words, heads, fence = [], [], False
    for i, ln in enumerate(lines, 1):
        words.append(len(ln.split()))
        if ln.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence:
            continue
        for m in MD_ANCHOR.finditer(ln):
            src.index.setdefault((m.group(1) or m.group(2)).lower(), i)
        h = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if not h:
            continue
        title = MD_ANCHOR.sub("", h.group(2)).strip()
        r = re.match(r"([A-Z][A-Za-z]{0,4}\.\d+)\s*:", title)
        if r:
            src.index.setdefault(r.group(1).lower(), i)
        if len(h.group(1)) <= 2:
            heads.append((len(h.group(1)) - 1, title, i))
    outline(src, heads, len(lines), unit_ids=True)
    return words


def attach_words(src: Source, words: list[int], batch: int) -> None:
    """Word counts per part; a part over the batch without sections gets page chunks."""
    limit = batch / TOKENS_PER_WORD
    for p in src.parts:
        for r in [p, *p.children]:
            r.words = sum(words[r.first - 1:r.last])
        if p.children or p.words <= limit:
            continue
        a, acc = p.first, 0
        for pg in range(p.first, p.last + 1):
            w = words[pg - 1]
            if acc and acc + w > limit:
                p.children.append(_chunk(p, a, pg - 1, acc, src.unit))
                a, acc = pg, 0
            acc += w
        p.children.append(_chunk(p, a, p.last, acc, src.unit))


def _chunk(p: Part, a: int, b: int, words: int, unit: str) -> Part:
    tag = "p" if unit == "pages" else "l"
    return Part(f"{p.id}.{tag}{a}-{b}", f"{unit} {a}–{b}", a, b, depth=1, words=words)


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:16] or "x"


def _load_cache(deck: Deck) -> dict:
    f = deck.path / CACHE
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except (OSError, ValueError):
        return {}


def text_of(path: Path, first: int, last: int) -> str:
    if path.suffix.lower() != ".pdf":
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[first - 1:last])
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
    note_texts: dict[str, str] = {}          # note name -> its source text
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
                note_texts[p.stem.lower()] = _as_list(m.get("source"))
    card_refs, card_texts = [], []
    for f in deck.files():
        for c in C.load_file(f):
            s = str(c.get("source") or "")
            refs = _refs(s)
            for name, _ in list(refs):
                refs += note_refs.get(name.lower(), [])
                s += " " + note_texts.get(name.lower(), "")
            card_refs.append(refs)
            card_texts.append(s)

    for src in sources:
        if src.unit == "lines":
            _count_md(src, list(note_texts.values()), card_texts)
            continue

        def mine(ref, src=src):
            name, _ = ref
            return name.startswith(src.url) if src.url else (
                src.path is not None and name.lower() in (src.path.name.lower(), src.path.stem.lower()))

        for part in src.parts:
            for p in [part, *part.children]:
                p.notes = sum(any(mine(r) and p.covers(r) for r in refs) for refs in note_refs.values())
                p.cards = sum(any(mine(r) and p.covers(r) for r in refs) for refs in card_refs)


def _md_lines(src: Source, s: str) -> set[int]:
    """Lines of a Markdown source that a source string points at: `#anchor` or a rule id,
    when the string names the file, its key or its web address."""
    low = s.lower()
    names = [src.path.stem.lower(), f"{src.key} "] + ([src.also.lower()] if src.also else [])
    if not any(n and n in low for n in names):
        return set()
    hits = {src.index.get(a.lower()) for a in re.findall(r"#([\w.-]+)", s)}
    hits |= {src.index.get(r.lower()) for r in RULE_ID.findall(s)}
    return {h for h in hits if h}


def _count_md(src: Source, notes: list[str], cards: list[str]) -> None:
    note_lines = [_md_lines(src, s) for s in notes]
    card_lines = [_md_lines(src, s) for s in cards]
    for part in src.parts:
        for p in [part, *part.children]:
            p.notes = sum(any(p.first <= x <= p.last for x in ls) for ls in note_lines)
            p.cards = sum(any(p.first <= x <= p.last for x in ls) for ls in card_lines)


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
        head = f"**{src.key}**: {src.label}" + (f" ({src.pages} {src.unit})" if src.pages else "")
        lines += [head + (f": {src.problem}" if src.problem else ""), ""]
        if not src.parts:
            continue
        cols = f"| part | title | {src.unit} | words | ~tokens | status |" if not src.url else \
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
        words = scan_md(src) if src.unit == "lines" else scan(src, cache)
        attach_words(src, words, int(meta.get("batch") or DEFAULT_BATCH))
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
                    words = scan_md(s) if s.unit == "lines" else scan(s, cache)
                    attach_words(s, words, int(meta.get("batch") or DEFAULT_BATCH))
            hit = find_part(srcs, read)
            if hit is None:
                print(f"! no part `{read}` in {deck.path.name}; run `asl sources` and pick an id "
                      "from the map.")
                return 1
            s, p = hit
            if s.url:
                print(f"{p.id}: {p.url}\n(a link: fetch only this part)")
                return 0
            where = "" if p.title.startswith(s.unit) else f" ({s.unit} {p.first}–{p.last})"
            print(f"# {s.label} — {p.title}{where}\n")
            print(text_of(s.path, p.first, p.last))
            return 0
        if build_map(deck) is None:
            print(f"{deck.path.name}: no `sources:` in Overview.md's frontmatter; nothing to map.")
    return 0
