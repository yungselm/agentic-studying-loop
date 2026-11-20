# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Rate benchmark cards blind, 1-5, in a local page that shows them as Anki would.

    uv run python benchmarks/rate.py pilot            # then open http://127.0.0.1:8765
    uv run python benchmarks/rate.py pilot v2         # two batches: arms compared across them

Picks `--per` random cards (default 5) per setup x arm x kind (code / topic / language) from the
batch's finished runs (with several batches, each batch's arm is its own group), in random order, without saying which model or arm made them. Workflow
cards render through the real card templates (CodeMirror for code cards); plain-prompt cards get
the same look as a concept card. A cloze note is rated as one of its Anki cards (one gap hidden).

`--recheck 20` shows 20 cards you already rated (evenly from each batch), blind again, and saves
the new scores to recheck.jsonl: `summary.py` then shows how far your scale moved between sessions.

Keys: space or enter flips, 1-5 rates (after flipping), u undoes the last rating.
Ratings go to results/<batch>/ratings.jsonl of the card's batch: card ids and scores only.
New runs join the pool the next time the page starts.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import random
import re
import sys
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

BENCH = Path(__file__).resolve().parent
DEFAULT_WORK = Path.home() / ".cache" / "asl-bench"

PLAIN_FRONT = '<div class="instr">{{Front}}</div>\n<div class="hint">Recall the answer, then flip &#9654;</div>'
PLAIN_BACK = '<div class="instr">{{Front}}</div>\n<div class="answer">{{Back}}</div>'
MATHJAX = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js"


# ---- a small Anki template renderer ----------------------------------------------------------

SECTION = re.compile(r"\{\{([#^])\s*([^}]+?)\s*\}\}(.*?)\{\{/\s*\2\s*\}\}", re.S)
TAG = re.compile(r"\{\{([^}]+)\}\}")
CLOZE = re.compile(r"\{\{c(\d+)::(.*?)(?:::((?:(?!\}\}).)*))?\}\}", re.S)


def cloze(value: str, ord_: int, side: str) -> str:
    def one(m):
        if int(m[1]) != ord_:
            return m[2]
        shown = m[2] if side == "a" else f"[{m[3] or '...'}]"
        return f'<span class="cloze">{shown}</span>'
    return CLOZE.sub(one, value)


def render(tpl: str, fields: dict[str, str], side: str, ord_: int = 1, front: str = "") -> str:
    """Anki's field substitution: {{Field}}, {{#Field}}..{{/Field}}, {{^Field}}, {{cloze:Field}},
    {{FrontSide}}; other filters (text:, ...) pass the field through."""
    prev = None
    while prev != tpl:                          # nested sections, innermost last
        prev = tpl
        tpl = SECTION.sub(lambda m: m[3] if bool(fields.get(m[2], "").strip()) == (m[1] == "#")
                          else "", tpl)

    def tag(m):
        name = m[1].strip()
        if name == "FrontSide":
            return front
        filt, _, field = name.rpartition(":")
        value = fields.get(field, "")
        if filt.endswith("cloze"):
            return cloze(value, ord_, side)
        if filt.startswith("text"):
            return re.sub(r"<[^>]+>", "", value)
        return value
    return TAG.sub(tag, tpl)


# ---- the pool: every card of the batch's finished runs ---------------------------------------

class Card:
    __slots__ = ("key", "rkey", "batch", "run", "front", "back", "media", "root")

    def __init__(self, batch, rkey, run, front, back, media, root):
        self.batch, self.rkey, self.key = batch, rkey, f"{batch}:{rkey}"   # run ids repeat across batches
        self.run, self.front, self.back = run, front, back
        self.media, self.root = media, root         # name -> file; folder for relative names


def _media_urls(s: str, idx: int) -> str:
    s = re.sub(r"\[sound:([^\]]+)\]",
               lambda m: f'<audio controls src="/m/{idx}/{html.escape(m[1])}"></audio>', s)
    # only media tags: the template's own <script src="_cards.js"> stay with the shared assets
    return re.sub(r'(<(?:img|audio|video|source)\b[^>]*?\bsrc=["\'])(?!https?:|data:|/)([^"\']+)',
                  lambda m: f"{m[1]}/m/{idx}/{m[2]}", s)


def workflow_cards(run: dict, run_dir: Path) -> list[tuple[str, str, str, dict]]:
    from studyloop.core import cards as C
    from studyloop.core.config import load_deck
    from studyloop.core.config.vault import vault_for, vault_index
    from studyloop.core.engine.build import build_models, make_note, media_index
    out = []
    homes = list((run_dir / "Anki cards").glob("*/deck.yaml"))
    if not homes:
        return out
    deck = load_deck(homes[0].parent)
    models = build_models({})
    vault, lang = vault_for(deck.path), media_index(deck)

    def find_file(n, f):
        if Path(n).name.lower() in lang:
            return lang[Path(n).name.lower()]
        if (f.parent / n).is_file():
            return f.parent / n
        return vault_index(vault)[1].get(Path(n).name.lower()) if vault else None
    for f in deck.files():
        try:
            cards = C.load_file(f)
        except Exception as e:                      # lint already counted it
            print(f"  skip {run['run_id']} {f.name}: {e}", file=sys.stderr)
            continue
        for i, card in enumerate(cards):
            media: dict[str, Path] = {}
            try:
                note = make_note(deck, f, card, models, lambda n, _f=f: find_file(n, _f), media)
            except (Exception, SystemExit) as e:
                print(f"  skip {run['run_id']} {f.name}#{i}: {e}", file=sys.stderr)
                continue
            fields = dict(zip((x["name"] for x in note.model.fields), note.fields))
            cloze_model = note.model.model_type == note.model.CLOZE
            for c in note.cards:
                tpl = note.model.templates[0 if cloze_model else c.ord]
                ord_ = c.ord + 1
                front = render(tpl["qfmt"], fields, "q", ord_)
                back = render(tpl["afmt"], fields, "a", ord_, front)
                cid = card.get("id") or f"{f.stem}#{i}"
                out.append((f"{run['run_id']}/{cid}/c{ord_}", front, back, media))
    return out


def plain_cards(run: dict, run_dir: Path) -> list[tuple[str, str, str, dict]]:
    f = run_dir / "cards.tsv"
    if not f.exists():
        return []
    out = []
    with open(f, encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.reader(fh, delimiter="\t") if any(c.strip() for c in r)
                and not r[0].startswith("#")]
    for n, r in enumerate(rows, 1):
        fields = {"Front": r[0], "Back": r[1] if len(r) > 1 else ""}
        out.append((f"{run['run_id']}/row{n}", render(PLAIN_FRONT, fields, "q"),
                    render(PLAIN_BACK, fields, "a"), {}))
    return out


def load_pool(batches: list[str], work: Path) -> tuple[dict[tuple, list[Card]], dict[str, Card]]:
    groups: dict[tuple, list[Card]] = {}
    by_key: dict[str, Card] = {}
    for batch in batches:
        runs = [json.loads(ln) for ln in (BENCH / "results" / batch / "runs.jsonl")
                .read_text(encoding="utf-8").splitlines() if ln.strip()]
        for run in runs:
            run_dir = work / batch / run["run_id"]
            if run["status"] != "ok" or not run_dir.is_dir():
                continue
            arm = run["arm"] if len(batches) == 1 else f"{run['arm']}@{batch}"
            made = (plain_cards if run["arm"] == "plain" else workflow_cards)(run, run_dir)
            for rkey, front, back, media in made:
                card = Card(batch, rkey, run, front, back, media, run_dir)
                groups.setdefault((run["setup"], arm, run["kind"]), []).append(card)
                by_key[card.key] = card
    return groups, by_key


# ---- ratings ---------------------------------------------------------------------------------

class Ratings:
    def __init__(self, path: Path):
        self.path, self.lock = path, threading.Lock()
        self.rows = ([json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()
                      if ln.strip()] if path.exists() else [])

    def rated(self) -> set[str]:
        return {r["key"] for r in self.rows}

    def add(self, card: Card, score: int) -> None:
        run = card.run
        row = {"key": card.rkey, "run_id": run["run_id"], "task": run["task"], "kind": run["kind"],
               "setup": run["setup"], "arm": run["arm"], "score": score,
               "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with self.lock:
            self.rows = [r for r in self.rows if r["key"] != card.rkey] + [row]
            self._save()

    def undo(self) -> str | None:
        with self.lock:
            if not self.rows:
                return None
            key = self.rows.pop()["key"]
            self._save()
            return key

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(json.dumps(r) + "\n" for r in self.rows), encoding="utf-8")


class AllRatings:
    """One ratings file per batch; keys are `<batch>:<key>` like Card.key."""

    def __init__(self, batches: list[str], name: str = "ratings.jsonl"):
        self.by = {b: Ratings(BENCH / "results" / b / name) for b in batches}

    def rated(self) -> set[str]:
        return {f"{b}:{k}" for b, r in self.by.items() for k in r.rated()}

    def add(self, card: Card, score: int) -> None:
        self.by[card.batch].add(card, score)

    def undo(self) -> str | None:
        last = [(r.rows[-1]["at"], b) for b, r in self.by.items() if r.rows]
        if not last:
            return None
        b = max(last)[1]
        return f"{b}:{self.by[b].undo()}"


def pick(groups: dict[tuple, list[Card]], done: set[str], per: int, rng: random.Random):
    """A random unrated card from a group with the fewest ratings still under `per`."""
    rated = Counter()
    for g, cards in groups.items():
        rated[g] = sum(c.key in done for c in cards)
    open_ = [g for g, cards in groups.items()
             if rated[g] < per and any(c.key not in done for c in cards)]
    target = sum(min(per, len(cards)) for cards in groups.values())
    progress = (sum(min(per, rated[g]) for g in groups), target)
    if not open_:
        return None, progress
    low = min(rated[g] for g in open_)
    g = rng.choice([g for g in open_ if rated[g] == low])
    return rng.choice([c for c in groups[g] if c.key not in done]), progress


# ---- the page --------------------------------------------------------------------------------

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rate cards</title>
<style>
:root { --bg:#f4f4f2; --fg:#222; --muted:#777; --panel:#fff; --line:#ddd; --accent:#3b6fd8; }
@media (prefers-color-scheme: dark) { :root { --bg:#1d1d1f; --fg:#e8e8e8; --muted:#999;
  --panel:#2a2a2d; --line:#444; --accent:#7aa2f7; } }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.4 system-ui, sans-serif; }
header { display:flex; justify-content:space-between; padding:10px 16px; color:var(--muted); }
#frame { display:block; width:min(900px, calc(100% - 32px)); height:68vh; margin:0 auto;
  border:1px solid var(--line); border-radius:8px; background:#fff; }
#bar { display:flex; gap:8px; justify-content:center; padding:14px 16px; flex-wrap:wrap; }
button { font:inherit; padding:8px 14px; border-radius:6px; border:1px solid var(--line);
  background:var(--panel); color:var(--fg); cursor:pointer; min-width:44px; }
button:disabled { opacity:.35; cursor:default; }
#flip { border-color:var(--accent); }
#help { text-align:center; color:var(--muted); font-size:13px; padding:0 16px 16px; }
#done { display:none; text-align:center; padding:60px 16px; font-size:18px; }
</style></head><body>
<header><span id="progress"></span><span id="msg"></span></header>
<iframe id="frame"></iframe>
<div id="done">All cards rated. The scores are in each batch's <code>ratings.jsonl</code>;
<code>python benchmarks/summary.py __BATCHES__</code> shows them per setup.</div>
<div id="bar">
  <button id="flip">Show answer (space)</button>
  <button class="r" data-s="1" disabled>1</button><button class="r" data-s="2" disabled>2</button>
  <button class="r" data-s="3" disabled>3</button><button class="r" data-s="4" disabled>4</button>
  <button class="r" data-s="5" disabled>5</button>
  <button id="undo">Undo (u)</button>
</div>
<div id="help">1 useless or wrong · 2 poor · 3 usable · 4 good · 5 exactly what I'd want</div>
<script>
let card = null, flipped = false;
const frame = document.getElementById('frame');
function show() {
  frame.src = '/card/' + card.idx + '/' + (flipped ? 'a' : 'q');
  document.getElementById('flip').disabled = flipped;
  document.querySelectorAll('.r').forEach(b => b.disabled = !flipped);
}
async function next(url, body) {
  const r = await fetch(url || '/api/next', body ? {method:'POST', body:JSON.stringify(body)} : {});
  const j = await r.json();
  document.getElementById('progress').textContent = j.progress[0] + ' / ' + j.progress[1] + ' rated';
  document.getElementById('msg').textContent = j.msg || '';
  if (!j.card) { card = null; frame.style.display = 'none';
    document.getElementById('bar').style.display = 'none';
    document.getElementById('done').style.display = 'block'; return; }
  frame.style.display = ''; document.getElementById('bar').style.display = '';
  document.getElementById('done').style.display = 'none';
  card = j.card; flipped = false; show();
}
function rate(s) { if (card && flipped) next('/api/rate', {key: card.key, score: s}); }
document.getElementById('flip').onclick = () => { if (card) { flipped = true; show(); } };
document.querySelectorAll('.r').forEach(b => b.onclick = () => rate(+b.dataset.s));
document.getElementById('undo').onclick = () => next('/api/undo', {});
function key(e) {
  if (e.key === ' ' || e.key === 'Enter') { if (card && !flipped) { e.preventDefault(); flipped = true; show(); } }
  else if ('12345'.includes(e.key) && e.key.length === 1) rate(+e.key);
  else if (e.key === 'u') next('/api/undo', {});
}
document.addEventListener('keydown', key);
frame.addEventListener('load', () => {     // keys work while the card has focus, except in an editor
  frame.contentDocument.addEventListener('keydown', e => {
    if (!e.target.closest || !e.target.closest('.CodeMirror')) key(e); });
});
next();
</script></body></html>
"""


def serve(args) -> int:
    from studyloop.core.engine.build import STATIC_MEDIA, TPL, bundle_modes
    groups, by_key = load_pool(args.batch, args.work)
    if args.recheck:                   # re-rate cards you rated before: did your scale move?
        rated = AllRatings(args.batch).rated()
        rng0 = random.Random(1)
        chosen = []
        for b in args.batch:
            mine = sorted(k for k in rated if k.startswith(f"{b}:") and k in by_key)
            chosen += rng0.sample(mine, min(len(mine), args.recheck // len(args.batch)))
        groups = {("recheck", "", ""): [by_key[k] for k in chosen]}
    label = " + ".join(args.batch)
    if not groups:
        raise SystemExit(f"no finished runs with cards in {args.work} for {label}")
    for (setup, arm, kind), cards in sorted(groups.items()):
        print(f"  {kind:8} {setup:14} {arm:8} {len(cards):4} cards")
    ratings = AllRatings(args.batch, "recheck.jsonl" if args.recheck else "ratings.jsonl")
    if args.recheck:
        args.per = len(groups[("recheck", "", "")])
    rng = random.Random()
    assets = {k: v.read_bytes() for k, v in STATIC_MEDIA.items()}
    assets["_modes.js"] = bundle_modes().encode()
    css = (TPL / "style.css").read_text(encoding="utf-8")
    from studyloop.core.registry import registry
    css += "".join(t.css for t in registry().card_types.values() if t.css)
    assets["style.css"] = css.encode()
    index = {i: c for i, c in enumerate(by_key.values())}
    idx_of = {c.key: i for i, c in index.items()}
    page = PAGE.replace("__BATCHES__", html.escape(" ".join(args.batch))).encode()

    def payload(card: Card | None, progress, msg="") -> dict:
        if card is None:
            return {"card": None, "progress": progress, "msg": msg}
        return {"card": {"key": card.key, "idx": idx_of[card.key]}, "progress": progress, "msg": msg}

    def card_page(i: int, side: str) -> bytes:
        """One side as its own page, so the template's scripts (CodeMirror) load as in Anki."""
        card = index[i]
        body = _media_urls(card.front if side == "q" else card.back, i)
        return ('<!doctype html><html><head><meta charset="utf-8"><base href="/a/">'
                '<link rel="stylesheet" href="style.css">'
                f'<script async src="{MATHJAX}"></script></head>'
                f'<body class="card">{body}</body></html>').encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, body: bytes, ctype: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def json(self, obj):
            self.send(json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            p = unquote(self.path.split("?")[0])
            if p == "/":
                return self.send(page, "text/html; charset=utf-8")
            if p == "/api/next":
                return self.json(payload(*pick(groups, ratings.rated(), args.per, rng)))
            m = re.fullmatch(r"/card/(\d+)/([qa])", p)
            if m and int(m[1]) in index:
                return self.send(card_page(int(m[1]), m[2]), "text/html; charset=utf-8")
            if p.startswith("/a/") and p[3:] in assets:
                ctype = {"css": "text/css", "js": "text/javascript"}[p.rsplit(".", 1)[1]]
                return self.send(assets[p[3:]], ctype + "; charset=utf-8")
            m = re.fullmatch(r"/m/(\d+)/(.+)", p)
            if m and int(m[1]) in index:
                card = index[int(m[1])]
                f = card.media.get(m[2]) or next((v for k, v in card.media.items()
                                                  if k.lower() == m[2].lower()), None)
                if f is None:
                    cand = (card.root / m[2]).resolve()
                    f = cand if cand.is_relative_to(card.root.resolve()) and cand.is_file() else None
                if f is not None:
                    import mimetypes
                    return self.send(f.read_bytes(), mimetypes.guess_type(f.name)[0]
                                     or "application/octet-stream")
            self.send(b"not found", "text/plain", 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path == "/api/rate":
                card = by_key.get(body.get("key"))
                if card and body.get("score") in (1, 2, 3, 4, 5):
                    ratings.add(card, body["score"])
                return self.json(payload(*pick(groups, ratings.rated(), args.per, rng)))
            if self.path == "/api/undo":
                key = ratings.undo()
                card = by_key.get(key) if key else None
                _, progress = pick(groups, ratings.rated(), args.per, rng)
                if card is None:
                    return self.json(payload(*pick(groups, ratings.rated(), args.per, rng),
                                             msg="nothing to undo"))
                return self.json(payload(card, progress, "undone: rate it again"))
            self.send(b"not found", "text/plain", 404)

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"rating {label}: http://127.0.0.1:{args.port}  (Ctrl+C to stop; ratings are saved "
          "after each card)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped; start it again to continue")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("batch", nargs="*", default=["pilot"], help="one or more batches (default: pilot)")
    ap.add_argument("--per", type=int, default=5, help="cards per setup x arm x kind (default 5)")
    ap.add_argument("--recheck", type=int, metavar="N",
                    help="re-rate N cards you already rated, split over the batches (to recheck.jsonl)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--work", type=Path, default=DEFAULT_WORK, help="where run.py left the runs")
    return serve(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
