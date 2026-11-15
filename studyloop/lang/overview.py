"""The grammar overview: the language's official lists (JLPT for Japanese, from `grammar_lists`
in its config) as a checklist against the vault's grammar notes, and the images on the notes."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from ..notes import split_frontmatter
from .notefile import embed_image, read_note, update_note, write_note
from .setup import cache_dir

IMAGES = "_attachements"          # next to the notes, as for other topics' PDFs


def fetch_lists(cfg: dict, force: bool = False) -> None:
    """The JLPT grammar lists (JLPT Sensei: link, form, meaning per point) into the cache."""
    import time
    import urllib.request

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
                update_note(d.notes_dir / "Grammar" / f"{t}.md", link=it["link"], level=lvl)
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
    from urllib.parse import quote
    gdir = d.notes_dir / "Grammar"
    (gdir / IMAGES).mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(gdir.glob("*.md")):
        meta, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        link = str(meta.get("link") or "")
        if meta.get("type") != "grammar" or meta.get("image") or "jlptsensei.com" not in link:
            continue
        try:
            req = urllib.request.Request(quote(link, safe=":/%?=&#"),
                                         headers={"User-Agent": "agentic-studying-loop"})
            page = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
            m = re.search(r'<meta property="?og:image"? content="?([^" >]+)', page)
            if not m:
                continue
            url = quote(html.unescape(m.group(1)), safe=":/%?=&#")   # raw Japanese in the file name
            req = urllib.request.Request(url, headers={"User-Agent": "agentic-studying-loop"})
            data = urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:                       # offline, moved page: try again later
            print(f"  ! {p.stem}: {e}")
            continue
        name = f"jlptsensei-{hashlib.sha1(link.encode()).hexdigest()[:10]}.jpg"
        save_image(data, gdir / IMAGES / name)
        meta, body = read_note(p)
        write_note(p, {**meta, "image": name}, embed_image(body, name))
        n += 1
        time.sleep(0.5)
    print(f"  images: {n} fetched from JLPT Sensei")
    return n


def _norm_forms(g: str) -> list[str]:
    """Comparable forms: '間（あいだ）' -> ['間'], 'ちゃいけない・じゃいけない' -> both, no spaces."""
    g = re.sub(r"（[^）]*）|\([^)]*\)|\s", "", g)
    return [x for x in re.split(r"[・/／,、]", g) if x]


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


