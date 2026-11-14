"""Grammar ground truth: one vault note per grammar point (`<notes>/Grammar/*.md`).

Frontmatter: `type: grammar`, `grammar`, `level`, `meaning`, `status`, `link`, and how to find it
in a line: `pattern` (a regex on the plain text: `ちゃいけない|じゃダメ`) and/or `token` (a word with
its part of speech, for particles: `が/助詞`). `asl lang grammar` seeds the notes and grammar
cards from a Game Gengo deck; the agent fixes the patterns `asl lang grammar --check` lists."""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..notes import split_frontmatter
from .apkg import read_export
from .tokens import plain_text

GATE_OK = {"planned": {"planned", "learning", "known"}, "learning": {"learning", "known"}}


@dataclass
class Point:
    title: str
    path: Path
    level: str = ""
    meaning: str = ""
    status: str = "unknown"
    pattern: str = ""
    token: str = ""
    link: str = ""
    image: str = ""
    examples: list[str] = field(default_factory=list)
    _rx: re.Pattern | None = None

    def matches(self, text: str, tokens: list) -> bool:
        if self.pattern:
            if self._rx is None:
                self._rx = re.compile(self.pattern)
            if self._rx.search(text):
                return True
        for rule in filter(None, (r.strip() for r in self.token.split("|"))):
            surface, pos, pos2 = (rule.split("/") + ["", ""])[:3]   # が/助詞, と/助詞/接続助詞
            if any((not surface or t.surface == surface) and (not pos or t.pos == pos)
                   and (not pos2 or t.pos2 == pos2) for t in tokens):      # `/形容詞`: any adjective
                return True
        return False


def load_points(notes_dir: Path) -> list[Point]:
    out = []
    for p in sorted((notes_dir / "Grammar").glob("*.md")):
        meta, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        if meta.get("type") != "grammar" or meta.get("detect") is False \
                or not (meta.get("pattern") or meta.get("token")):
            continue                     # `detect: false`: too generic to find in a line
        out.append(Point(p.stem, p, str(meta.get("level") or ""), str(meta.get("meaning") or ""),
                         str(meta.get("status") or "unknown"), str(meta.get("pattern") or ""),
                         str(meta.get("token") or ""), str(meta.get("link") or ""),
                         str(meta.get("image") or ""), [str(e) for e in meta.get("examples") or []]))
    return out


def detect(points: list[Point], text: str, tokens: list) -> list[Point]:
    return [p for p in points if p.matches(text, tokens)]


# ---- Game Gengo import --------------------------------------------------------------------

def _clean(s: str, mark: bool = True) -> str:
    """GG field -> card text: <font color>…</font> (the grammar) -> **…**, <br>/&nbsp; -> space."""
    s = re.sub(r"<br\s*/?>|&nbsp;|​", " ", s or "")
    if mark:
        s = re.sub(r"<font[^>]*>(.*?)</font>", r"**\1**", s, flags=re.S)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"\*\*\s*\*\*", "", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def _media(field_: str, rx: str) -> str:
    m = re.search(rx, field_ or "")
    return m.group(1) if m else ""


_ALT_SPLIT = re.compile(r"\s*(?:/|／|・|、|,|\+)\s*")
_GAP = re.compile(r"\s*(?:～|〜|~|…|\.\.\.)\s*")      # 全然～ない: 全然, then later ない


def _forms(grammar: str) -> list[str]:
    """'てしまう / ちゃう' -> ['てしまう', 'ちゃう']; '一番（いちばん）' -> ['一番']; 'が (ga)' -> ['が']."""
    g = re.sub(r"（[^）]*）|\([^)]*\)|\[[^\]]*\]", "", grammar)
    out = []
    for alt in _ALT_SPLIT.split(g):
        parts = [re.sub(r"[A-Za-z\s\[\]]+", "", x) for x in _GAP.split(alt)]
        alt = "～".join(x for x in parts if x)
        if alt and alt not in out:
            out.append(alt)
    return out


def _marked_tokens(marked: str, tok) -> list:
    """Tokens inside the **highlighted** grammar of an example (Game Gengo colours it)."""
    spans, plain, pos = [], "", 0
    for m in re.finditer(r"\*\*(.+?)\*\*", marked):
        plain += marked[pos:m.start()]
        spans.append((len(plain), len(plain) + len(m.group(1))))
        plain += m.group(1)
        pos = m.end()
    plain += marked[pos:]
    out, at = [], 0
    for t in tok(plain):
        start = plain.find(t.surface, at)
        if start < 0:
            continue
        at = start + len(t.surface)
        if any(a < at and start < b for a, b in spans):
            out.append(t)
    return out


def derive_rule(forms: list[str], examples: list[str], tok, marked: list[str] = ()) -> tuple[str, str]:
    """(pattern, token): a particle or auxiliary used as one token -> token rule (`が/助詞`), else
    the literal forms as a regex. Checked against the examples by `check_points`."""
    patterns, tokens = [], []
    for f in forms:
        if "～" in f:                                       # 全然～ない -> 全然.*?ない
            patterns.append(".*?".join(re.escape(x) for x in f.split("～")))
            continue
        hit = None
        # the marked span first (と "whenever" vs と "and" in the same sentence), then anywhere
        candidates = [_marked_tokens(m, tok) for m in marked] + [tok(ex) for ex in examples]
        for toks in candidates:
            for t in toks:
                if t.surface == f and t.pos in ("助詞", "助動詞"):
                    hit = f"{f}/{t.pos}/{t.pos2}" if t.pos2 and t.pos2 != "*" else f"{f}/{t.pos}"
                    break
            if hit:
                break
        if hit and len(f) <= 2:
            tokens.append(hit)
        else:
            patterns.append(re.escape(f))
    return "|".join(patterns), "|".join(tokens)


def _safe(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "", title).strip() or "grammar"


def import_game_gengo(d, apkg: Path, statuses: str = "reviews", key: str = "gg",
                      cards: bool = False) -> int:
    from ..config import native_path
    from .tokens import tokenizer
    tok = tokenizer(d.cfg.get("tokenizer", ""))
    ex = read_export(native_path(apkg))
    gg = sorted((n for n in ex.notes if n.model.startswith("GameGengoGrammar")
                 and not str(n.fields.get("Card Order", "")).endswith("_000")),
                key=lambda n: (("N4" in n.fields["Card Order"]), n.fields["Card Order"]))
    if not gg:
        raise SystemExit(f"{apkg}: no GameGengoGrammar notes")
    groups: dict[str, list] = {}
    for n in gg:
        link = _media(n.fields.get("GrammarLink", ""), r'href="([^"]+)"')
        groups.setdefault(link or _clean(n.fields["Grammar"], False), []).append(n)

    gdir = d.notes_dir / "Grammar"
    (gdir / IMAGES).mkdir(parents=True, exist_ok=True)
    titles, written, kept = {}, 0, 0
    for link, ns in groups.items():
        f0 = ns[0].fields
        grammar = _clean(f0["Grammar"], False)
        meaning = _clean(f0["Grammar Meaning"], False)
        title = _safe(grammar)
        if title in titles.values():                       # と (and) vs と (whenever)
            title = _safe(f"{grammar} ({meaning.split(';')[0][:30]})")
        for n in ns:
            titles[id(n)] = title
        level = "N5" if any("N5" in t for n in ns for t in n.tags) else "N4"
        status = "unknown"
        if statuses == "reviews":
            status = ("known" if any(n.mature for n in ns) else
                      "learning" if any(n.reviewed for n in ns) else "unknown")
        examples = [plain_text(_clean(n.fields["Sentence Field Furigana"])) for n in ns]
        forms = []
        for n in ns:
            forms += [f for f in _forms(_clean(n.fields["Grammar"], False)) if f not in forms]
        marked = [re.sub(r" ?([^ \[\]>*]+?)\[[^\]]*\]", r"\1", _clean(n.fields["Sentence Field Furigana"]))
                  for n in ns]
        pattern, token = derive_rule(forms, examples, tok, marked)
        image = next((m for n in ns if (m := _media(n.fields.get("GrammarImage", ""), r'src="([^"]+)"'))
                      and m in ex.media), "")
        if image and not (gdir / IMAGES / image).exists():
            save_image(ex.read_media(image), gdir / IMAGES / image)     # the JLPT Sensei card
        p = gdir / f"{title}.md"
        if p.exists():
            kept += 1
            _update_note(p, pattern, token, "unknown" if statuses == "unknown" else None, image)
            continue
        meta = {"type": "grammar", "language": d.lang, "grammar": grammar, "level": level,
                "meaning": meaning, "status": status, "rule": "auto", "pattern": pattern,
                "token": token,
                "link": link if link.startswith("http") else "", "image": image,
                "source": "Game Gengo", "examples": examples}
        body = (f"# {grammar}\n\n{meaning}\n\n" + (f"![[{image}]]\n\n" if image else "")
                + "## Examples (Game Gengo)\n\n"
                + "\n".join(f"- {_clean(n.fields['Sentence Field'])}  \n  "
                            f"{_clean(n.fields['Sentence Translation'])} ({_clean(n.fields['Video Game'], False)})"
                            for n in ns) + "\n")
        p.write_text("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000)
                     + "---\n" + body, encoding="utf-8")
        written += 1

    if not cards:
        print(f"Game Gengo: {len(gg)} lessons → {len(groups)} grammar points ({written} notes "
              f"written, {kept} existing: `rule: auto` re-derived, others kept) in {gdir}")
        write_overview(d)
        return check_points(d, tok)
    # the lessons as grammar cards (`--cards`; generated: re-running rewrites the file)
    cards, media = [], []
    for i, n in enumerate(gg, 1):
        f = n.fields
        audio = _media(f["Audio Field"], r"\[sound:([^\]]+)\]")
        image = _media(f["Image Field"], r'src="([^"]+)"')
        media += [m for m in (audio, image) if m in ex.media]
        card = {"id": f"jag-{i:03d}", "type": "grammar",
                "text": _clean(f["Sentence Field Furigana"]), "grammar": _clean(f["Grammar"], False),
                "meaning": _clean(f["Grammar Meaning"], False),
                "translation": _clean(f["Sentence Translation"]), "note": f"[[{titles[id(n)]}]]",
                "link": _media(f.get("GrammarLink", ""), r'href="([^"]+)"'),
                "audio": audio, "image": image,
                "source": f"{_clean(f['Video Game'], False)} · Game Gengo {f['Card Order'].split('Grammar_')[-1]}"}
        cards.append(card)
    out = d.path / "grammar.yaml"
    out.write_text("# Grammar cards ported from Game Gengo (`asl lang grammar`); re-running rewrites this file.\n"
                   + "".join(_item(c) for c in cards), encoding="utf-8")
    n_media = ex.extract_media(media, d.media_dir / key)
    write_overview(d)
    print(f"Game Gengo: {len(gg)} lessons → {len(groups)} grammar points "
          f"({written} notes written, {kept} existing: `rule: auto` re-derived, others kept) in {gdir}")
    print(f"  {len(cards)} grammar cards → {out}; media: {n_media} new files in {d.media_dir / key}")
    return check_points(d, tok)


def _update_note(p: Path, pattern: str, token: str, status: str | None, image: str = "") -> None:
    """An existing note: re-derive its rule only if it is still `rule: auto` (the agent's rules,
    `rule: agent`, and hand edits stay); `--fresh` resets the status."""
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return
    _, fm, body = text.split("---\n", 2)
    meta = yaml.safe_load(fm) or {}
    before = dict(meta)
    if meta.get("rule", "auto") == "auto" and meta.get("detect") is not False:
        meta.update(rule="auto", pattern=pattern, token=token)
    if status:
        meta["status"] = status
    if image and not meta.get("image"):
        meta["image"] = image
        body = re.sub(r"^(# .*\n\n.*\n)", rf"\1\n![[{image}]]\n", body, count=1)
    if meta != before:
        p.write_text("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000)
                     + "---\n" + body, encoding="utf-8")


IMAGES = "_attachements"          # next to the notes, as for other topics' PDFs


# ---- JLPT lists and the overview ------------------------------------------------------------

def fetch_lists(cfg: dict, force: bool = False) -> None:
    """The JLPT grammar lists (JLPT Sensei: link, form, meaning per point) into the cache."""
    import time
    import urllib.request

    from .levels import cache_dir
    lists = (cfg.get("grammar_lists") or {}).get("pages") or {}
    out = cache_dir(cfg["code"]) / "grammar_lists.json"
    if not lists or (out.exists() and not force):
        if lists:
            print(f"  grammar lists: cached ({out})")
        return
    data = {}
    row = re.compile(r'<td class="jl-td-gj[^"]*"><a[^>]*href=([^ >]+)[^>]*>([^<]+)</a><td class="jl-td-gm[^"]*">([^<]*)')
    for level, url in lists.items():
        items, page = [], 1
        while page < 20:
            u = url if page == 1 else f"{url.rstrip('/')}/page/{page}/"
            req = urllib.request.Request(u, headers={"User-Agent": "agentic-studying-loop"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    text = r.read().decode("utf-8", "replace")
            except Exception:
                break
            found = [{"link": h.strip('"').lower(), "grammar": html.unescape(g).strip(),
                      "meaning": html.unescape(m).strip()} for h, g, m in row.findall(text)]
            if not found:
                break
            items += found
            page += 1
            time.sleep(0.5)                                        # be polite
        data[level] = items
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  grammar lists: {', '.join(f'{k} {len(v)}' for k, v in data.items())} → {out}"
          + (f"  ({cfg['grammar_lists'].get('credit')})" if cfg["grammar_lists"].get("credit") else ""))


def write_overview(d) -> Path:
    """`Overview - <Language> Grammar.md`: the notes per level, and the JLPT lists as a checklist
    (ticked = a grammar note covers it)."""
    from .levels import cache_dir
    notes = []
    for p in sorted((d.notes_dir / "Grammar").glob("*.md")):
        meta, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        if meta.get("type") == "grammar":
            notes.append((p.stem, meta))
    lists_f = cache_dir(d.lang) / "grammar_lists.json"
    lists = json.loads(lists_f.read_text(encoding="utf-8")) if lists_f.exists() else {}
    by_link = {str(m.get("link") or "").lower(): t for t, m in notes if m.get("link")}
    by_form = {}
    for t, m in notes:
        for f in _norm_forms(str(m.get("grammar") or t)):
            by_form.setdefault(f, t)
    # notes without a link (Game Gengo N4) match a JLPT point by form; JLPT is the ground truth,
    # so the note takes its link and level
    for lvl, items in lists.items():
        for it in items:
            if it["link"] in by_link:
                continue
            t = next((by_form[f] for f in _norm_forms(it["grammar"]) if f in by_form), None)
            m = dict(notes).get(t)
            if t and not m.get("link"):
                m["link"], m["level"] = it["link"], lvl
                by_link[it["link"]] = t
                _set_fields(d.notes_dir / "Grammar" / f"{t}.md", link=it["link"], level=lvl)
    order = list(lists) or sorted({str(m.get("level") or "") for _, m in notes})
    name = d.cfg.get("name", d.lang)
    lines = ["---", "type: overview", f"language: {d.lang}", "---", f"# {name} grammar", "",
             "Ground truth: the JLPT lists (JLPT Sensei). A note per grammar point in [[Grammar]]; "
             "`status` drives the grammar gate, `pattern`/`token` find it in a line. "
             "Rewritten by `asl lang grammar`.", "",
             "| level | notes | known | learning | JLPT points covered |", "|---|---|---|---|---|"]
    for lvl in order:
        ns = [m for _, m in notes if m.get("level") == lvl]
        covered = sum(1 for it in lists.get(lvl, []) if it["link"] in by_link)
        lines.append(f"| {lvl} | {len(ns)} | {sum(m.get('status') == 'known' for m in ns)} | "
                     f"{sum(m.get('status') == 'learning' for m in ns)} | "
                     f"{covered} / {len(lists.get(lvl, [])) or '?'} |")
    for lvl in order:
        lines += ["", f"## {lvl}", ""]
        for it in lists.get(lvl, []):
            t = by_link.get(it["link"])
            if t:
                st = dict(notes)[t].get("status", "unknown")
                lines.append(f"- [x] [[{t}]] — {it['meaning']} · {st}")
            else:
                lines.append(f"- [ ] [{it['grammar']}]({it['link']}) — {it['meaning']}")
        listed = {it["link"] for it in lists.get(lvl, [])}
        extra = [(t, m) for t, m in notes if m.get("level") == lvl
                 and str(m.get("link") or "").lower() not in listed]
        if extra:
            lines += ["", f"Notes not on the {lvl} list:" if lists else "Notes:", ""]
            lines += [f"- [[{t}]] — {m.get('meaning', '')} · {m.get('status', 'unknown')}" for t, m in extra]
    out = d.notes_dir / f"Overview - {name} Grammar.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  overview: {out}")
    return out


def fetch_images(d) -> int:
    """JLPT Sensei's image for notes that have a `link` but no `image` (one page request each)."""
    import hashlib
    import time
    import urllib.request
    gdir = d.notes_dir / "Grammar"
    (gdir / IMAGES).mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(gdir.glob("*.md")):
        meta, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        link = str(meta.get("link") or "")
        if meta.get("type") != "grammar" or meta.get("image") or "jlptsensei.com" not in link:
            continue
        try:
            from urllib.parse import quote
            req = urllib.request.Request(quote(link, safe=":/%?=&#"),
                                         headers={"User-Agent": "agentic-studying-loop"})
            page = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
            m = re.search(r'<meta property="?og:image"? content="?([^" >]+)', page)
            if not m:
                continue
            from urllib.parse import quote
            url = quote(html.unescape(m.group(1)), safe=":/%?=&#")   # raw Japanese in the file name
            req = urllib.request.Request(url, headers={"User-Agent": "agentic-studying-loop"})
            data = urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:                       # offline, moved page: try again later
            print(f"  ! {p.stem}: {e}")
            continue
        name = f"jlptsensei-{hashlib.sha1(link.encode()).hexdigest()[:10]}.jpg"
        save_image(data, gdir / IMAGES / name)
        text = p.read_text(encoding="utf-8")
        _, fm, body = text.split("---\n", 2)
        meta = yaml.safe_load(fm) or {}
        meta["image"] = name
        body = re.sub(r"^(# .*\n\n.*\n)", rf"\1\n![[{name}]]\n", body, count=1)
        p.write_text("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000)
                     + "---\n" + body, encoding="utf-8")
        n += 1
        time.sleep(0.5)
    print(f"  images: {n} fetched from JLPT Sensei")
    return n


def _norm_forms(g: str) -> list[str]:
    """Comparable forms: '間（あいだ）' -> ['間'], 'ちゃいけない・じゃいけない' -> both, no spaces."""
    g = re.sub(r"（[^）]*）|\([^)]*\)|\s", "", g)
    return [x for x in re.split(r"[・/／,、]", g) if x]


def _set_fields(p: Path, **fields) -> None:
    _, fm, body = p.read_text(encoding="utf-8").split("---\n", 2)
    meta = yaml.safe_load(fm) or {}
    meta.update(fields)
    p.write_text("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000)
                 + "---\n" + body, encoding="utf-8")


def save_image(data: bytes, out: Path, width: int = 600) -> None:
    """A JLPT Sensei card into the vault, at most `width` px wide (they are 600x338 cards)."""
    import subprocess
    import tempfile

    from .audio import ffmpeg_exe
    exe = ffmpeg_exe()
    if not exe:
        out.write_bytes(data)
        return
    with tempfile.NamedTemporaryFile(suffix=out.suffix, delete=False) as tmp:
        tmp.write(data)
    try:
        subprocess.run([exe, "-y", "-loglevel", "error", "-i", tmp.name, "-vf",
                        f"scale='min({width},iw)':-2", "-q:v", "4", str(out)], check=True)
    except subprocess.CalledProcessError:
        out.write_bytes(data)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def _item(card: dict) -> str:
    out = []
    for i, (k, v) in enumerate(card.items()):
        if v in ("", None):
            continue
        val = v if k in ("id", "type") else json.dumps(str(v), ensure_ascii=False)
        out.append(("- " if i == 0 else "  ") + f"{k}: {val}")
    return "\n".join(out) + "\n"


def check_points(d, tok) -> int:
    """Each grammar note's rule must find its own examples; list the ones that don't."""
    points = load_points(d.notes_dir)
    bad = []
    for p in points:
        miss = [e for e in p.examples if not p.matches(e, tok(e))]
        if miss:
            bad.append((p, miss))
    unruled = [q.stem for q in sorted((d.notes_dir / "Grammar").glob("*.md"))
               if q.stem not in {p.title for p in points}
               and split_frontmatter(q.read_text(encoding="utf-8"))[0].get("detect") is not False]
    print(f"Grammar rules: {len(points) - len(bad)} of {len(points)} find all their examples"
          + (f"; {len(unruled)} notes without a rule" if unruled else ""))
    for p, miss in bad:
        print(f"  ! {p.title}: pattern={p.pattern!r} token={p.token!r} misses: {miss[0][:50]}")
    for t in unruled:
        print(f"  ! {t}: no `pattern:` or `token:`")
    return 0
