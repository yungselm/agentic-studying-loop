"""The JLPT grammar lists and images, from JLPT Sensei (`grammar_lists:` in ja.yaml)."""
from __future__ import annotations

import html
import json
import re

from studyloop.core.config.vault import split_frontmatter
from studyloop.language.grammar.notes import embed_image, read_note, write_note
from studyloop.language.grammar.overview import IMAGES, save_image
from studyloop.language.setup import cache_dir


def lists(code: str) -> dict:
    """{level: [{link, grammar, meaning}]} as fetched by `asl lang setup ja` (empty before)."""
    f = cache_dir(code) / "grammar_lists.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


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
