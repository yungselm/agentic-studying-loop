"""Analyse a manual Anki export and report what makes cards hard for *you*.

    asl stats export.apkg [--deck "Study Loop"] [--home <card home>] [--mark-refreshed]

Export from Anki: File > Export > "Anki Deck Package (.apkg)" with
"Include scheduling information" ticked (or a whole-collection .colpkg).
Nothing here talks to Anki; you decide when (and whether) to look.

Writes, into <card home>/evidence/ (or the current folder):
  <date>-report.md   maturity status, fail rates by card size, leeches,
                     per-deck and per-standards-version comparisons, and
                     *suggested* limits. Suggestions only: the
                     refresh-standards skill turns them into a proposed edit
                     you approve.
  <date>-cards.csv   one row per card with its measures and review stats.

Definitions: "review answers" are review-phase answers (revlog type 1);
"fail" is an Again on one of them; "mature" is an interval of 21 days or more;
cards younger than `min_card_age_days` are left out of the size analysis.
"""
from __future__ import annotations

import base64
import csv
import datetime as dt
import html
import json
import re
import sqlite3
import statistics as st
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import cards as C
from .build import CODE_MODEL_ID, CONCEPT_MODEL_ID
from .config import Home, find_home

TIMER_MS = 60000
CODE_BINS = [0, 40, 80, 120, 160, 250, 10**9]
ANSWER_BINS = [0, 150, 250, 300, 450, 10**9]
BOLD_BINS = [0, 80, 120, 150, 250, 10**9]
MIN_BIN_ANSWERS = 60


# ---- reading the export ---------------------------------------------------------

def open_collection(path: Path) -> tuple[sqlite3.Connection, Path]:
    tmp = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for name in ("collection.anki21b", "collection.anki21", "collection.anki2"):
            if name in names:
                raw = z.read(name)
                break
        else:
            raise SystemExit(f"{path}: no collection inside; is this an Anki export?")
    if name.endswith("21b"):
        try:
            import zstandard
        except ImportError as e:
            raise SystemExit("This export is zstd-compressed: pip install zstandard") from e
        raw = zstandard.ZstdDecompressor().stream_reader(raw).read()
    db = tmp / "collection.sqlite"
    db.write_bytes(raw)
    return sqlite3.connect(db), tmp


def deck_names(con) -> dict[int, str]:
    try:
        return {did: name.replace("\x1f", "::")
                for did, name in con.execute("select id, name from decks")}
    except sqlite3.OperationalError:
        decks = json.loads(con.execute("select decks from col").fetchone()[0])
        return {int(k): v["name"] for k, v in decks.items()}


def _strip(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s or "")
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _b64(s: str) -> str:
    try:
        return base64.b64decode(s or "").decode("utf-8")
    except Exception:
        return _strip(s)


@dataclass
class Card:
    cid: int
    deck: str
    kind: str
    card_id: str
    std: str
    front: str
    created: dt.datetime
    ivl: int
    lapses: int
    queue: int
    ctype: int
    difficulty: float | None
    stability: float | None
    measures: dict = field(default_factory=dict)
    answers: list[tuple[int, int, int]] = field(default_factory=list)  # (ease, ms, type)

    @property
    def review(self):
        return [a for a in self.answers if a[2] == 1]

    @property
    def fails(self):
        return sum(1 for a in self.review if a[0] == 1)

    @property
    def fail_rate(self):
        r = self.review
        return self.fails / len(r) if r else None

    @property
    def timer_hits(self):
        return sum(1 for a in self.answers if a[1] >= TIMER_MS)

    @property
    def median_ms(self):
        return st.median(a[1] for a in self.answers) if self.answers else None


def load_cards(con, deck_prefix: str | None) -> list[Card]:
    decks = deck_names(con)
    notes = {nid: (mid, tags, flds.split("\x1f"))
             for nid, mid, tags, flds in con.execute("select id, mid, tags, flds from notes")}
    out: dict[int, Card] = {}
    rows = con.execute("select id, nid, did, odid, ivl, lapses, queue, type, data from cards")
    for cid, nid, did, odid, ivl, lapses, queue, ctype, data in rows:
        deck = decks.get(odid or did, "?")
        if deck_prefix and not (deck == deck_prefix or deck.startswith(deck_prefix + "::")):
            continue
        mid, tags, f = notes[nid]
        tagl = tags.split()
        kind = next((t.split("::")[-1] for t in tagl if t.startswith("asl::type::")), None)
        if not kind:
            kind = ("code" if mid == CODE_MODEL_ID or len(f) == 7 else
                    "concept" if mid == CONCEPT_MODEL_ID or len(f) == 5 else "other")
        try:
            mem = json.loads(data) if data else {}
        except json.JSONDecodeError:
            mem = {}
        if kind == "code":
            m = {"typed_chars": C.typed_chars(_b64(f[1]), _b64(f[2])),
                 "typed_lines": len(C.typed(_b64(f[1]), _b64(f[2])))}
        elif kind in ("concept", "timeline"):
            ans = f[1] if len(f) > 1 else ""
            bold = re.findall(r"<(?:strong|b)>(.*?)</(?:strong|b)>", ans, re.S)
            m = {"answer_chars": len(_strip(ans)),
                 "bold_chars": len(_strip(bold[0])) if bold else 0}
        else:
            m = {}
        out[cid] = Card(
            cid=cid, deck=deck, kind=kind,
            card_id=next((t.split("::")[-1] for t in tagl if t.startswith("asl::id::")), ""),
            std=next((t.split("::")[-1] for t in tagl if t.startswith("asl::std::")), ""),
            front=_strip(f[0])[:90].replace("\n", " "),
            created=dt.datetime.fromtimestamp(nid / 1000), ivl=ivl, lapses=lapses,
            queue=queue, ctype=ctype, difficulty=mem.get("d"), stability=mem.get("s"),
            measures=m)
    for cid, ease, ms, rtype in con.execute("select cid, ease, time, type from revlog"):
        if cid in out and rtype in (0, 1, 2):
            out[cid].answers.append((ease, ms, rtype))
    return list(out.values())


# ---- analysis helpers ------------------------------------------------------------------

def _pct(x):
    return "–" if x is None else f"{100 * x:.0f}%"


def _med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def _fmt(x, nd=1):
    return "–" if x is None else f"{x:.{nd}f}"


def pooled(cards):
    rev = sum(len(c.review) for c in cards)
    return (sum(c.fails for c in cards) / rev) if rev else None, rev


def timer_share(cards):
    n = sum(len(c.answers) for c in cards)
    return (sum(c.timer_hits for c in cards) / n) if n else None


def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 10:
        return None

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r

    rx, ry = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def bin_table(cards, key, bins, title):
    rows = [f"| {title} | cards | review answers | fail rate | hit 60 s timer | median difficulty |",
            "|---|---|---|---|---|---|"]
    stats = []
    for lo, hi in zip(bins, bins[1:]):
        sel = [c for c in cards if lo < c.measures.get(key, -1) <= hi or
               (lo == 0 and c.measures.get(key) == 0)]
        fr, n = pooled(sel)
        ts = timer_share(sel)
        label = f"{lo}–{hi}" if hi < 10**9 else f">{lo}"
        rows.append(f"| {label} | {len(sel)} | {n} | {_pct(fr)}{' (few)' if n < MIN_BIN_ANSWERS else ''}"
                    f" | {_pct(ts)} | {_fmt(_med(c.difficulty for c in sel))} |")
        stats.append((lo, hi, fr, n, ts))
    return "\n".join(rows), stats


def suggest(stats, current_target, current_max, unit):
    """Heuristic, relative to the smallest cards (the best you do):
    target = top of the last bin (in a row) within `tol` of that fail rate,
    max = bottom of the first later bin clearly worse (>= 1.5x the reference,
    or >= 50% of answers hitting the 60 s timer). Bins with fewer than
    MIN_BIN_ANSWERS answers are ignored."""
    ok = [s for s in stats if s[3] >= MIN_BIN_ANSWERS and s[2] is not None]
    if len(ok) < 3:
        return f"- {unit}: not enough data yet (keep {current_target}/{current_max})."
    ref = ok[0][2]
    tol = max(0.05, 0.35 * ref)
    target = ok[0][1]
    for lo, hi, fr, _n, _ts in ok[1:]:
        if fr <= ref + tol and hi < 10**9:
            target = hi
        else:
            break
    worse = next((lo for lo, hi, fr, _n, ts in ok
                  if lo >= target and (fr >= 1.5 * ref or (ts or 0) >= 0.5)), None)
    t = min(target, 10**6)
    m = worse if worse is not None else current_max
    m = max(m, t)
    flag = "" if (t, m) == (current_target, current_max) else "  ← differs from current"
    return (f"- {unit}: target ≈ {t}, max ≈ {m} (current {current_target}/{current_max}; "
            f"reference fail rate {_pct(ref)} in the smallest bin){flag}")


# ---- refresh state -------------------------------------------------------------

def state_path(home: Home, out_dir: Path) -> Path:
    return out_dir / "refresh-state.yaml"


def read_state(p: Path) -> dict:
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}


def refresh_status(cards, home: Home, state: dict) -> tuple[bool, str, dict]:
    r = home.refresh
    total = len(cards)
    mature = sum(1 for c in cards if c.ivl >= r["mature_ivl_days"])
    answers = sum(len(c.review) for c in cards)
    share = mature / total if total else 0
    last = state.get("last") or {}
    new_mature = mature - int(last.get("mature", 0))
    new_answers = answers - int(last.get("review_answers", 0))
    if not last:
        due = share >= r["mature_share"] and answers >= r["min_review_answers"]
        why = (f"{_pct(share)} mature (threshold {_pct(r['mature_share'])}), "
               f"{answers} review answers (min {r['min_review_answers']}); no refresh yet.")
    else:
        due = (new_mature >= r["step_share"] * total and new_answers >= r["min_review_answers"])
        why = (f"{new_mature} newly mature since {last.get('date')} "
               f"(needs {int(r['step_share'] * total)}), {new_answers} new review answers "
               f"(min {r['min_review_answers']}).")
    snap = {"date": dt.date.today().isoformat(), "cards": total, "mature": mature,
            "review_answers": answers}
    return due, why, snap


# ---- report ----------------------------------------------------------------------

def report(cards: list[Card], home: Home, src: Path, deck: str | None, state: dict) -> str:
    r = home.refresh
    lim = home.limits
    cutoff = dt.datetime.now() - dt.timedelta(days=r["min_card_age_days"])
    old = [c for c in cards if c.created <= cutoff and c.review]
    code = [c for c in old if c.kind == "code"]
    concept = [c for c in old if c.kind in ("concept", "timeline")]
    due, why, _snap = refresh_status(cards, home, state)
    out = [f"# Card evidence report — {dt.date.today().isoformat()}", "",
           f"Source: `{src.name}`{f', deck `{deck}`' if deck else ''}. "
           f"Standards version in use: v{home.standards_version}.", "",
           "## Refresh status", "",
           f"**{'Refresh due' if due else 'Not due yet'}**: {why}", "",
           "## Overview", "",
           f"{len(cards)} cards, {sum(len(c.answers) for c in cards)} answers. "
           f"Size analysis uses the {len(old)} cards older than {r['min_card_age_days']} days "
           "that have review answers.", "",
           "| | cards | fail rate | median difficulty | leeches (≥5 lapses) |",
           "|---|---|---|---|---|"]
    for name, sel in (("code", code), ("concept", concept)):
        fr, _ = pooled(sel)
        out.append(f"| {name} | {len(sel)} | {_pct(fr)} | {_fmt(_med(c.difficulty for c in sel))} "
                   f"| {sum(1 for c in sel if c.lapses >= 5)} |")
    sugg = []
    if code:
        t, s = bin_table(code, "typed_chars", CODE_BINS, "typed chars")
        rho = spearman([c.measures["typed_chars"] for c in code], [c.fail_rate for c in code])
        out += ["", "## Code cards: typed size", "", t, "",
                f"Spearman ρ (typed chars vs card fail rate): {_fmt(rho, 2)}"]
        sugg.append(suggest(s, lim["code"]["typed_chars_target"],
                            lim["code"]["typed_chars_max"], "typed chars"))
    if concept:
        t1, s1 = bin_table(concept, "answer_chars", ANSWER_BINS, "answer chars")
        t2, s2 = bin_table(concept, "bold_chars", BOLD_BINS, "bold lead chars")
        out += ["", "## Concept cards: answer size", "", t1, "", t2]
        sugg.append(suggest(s1, lim["concept"]["answer_chars_target"],
                            lim["concept"]["answer_chars_max"], "answer chars"))
        sugg.append(suggest(s2, lim["concept"]["bold_chars_target"],
                            lim["concept"]["bold_chars_max"], "bold lead chars"))
    # per deck
    by_deck: dict[str, list[Card]] = {}
    for c in code:
        by_deck.setdefault(c.deck, []).append(c)
    rows = sorted(((pooled(v)[0] or 0, k, v) for k, v in by_deck.items() if pooled(v)[1] >= 30),
                  reverse=True)
    if rows:
        out += ["", "## Code cards by deck (hardest first, ≥30 review answers)", "",
                "| deck | cards | fail rate | median difficulty |", "|---|---|---|---|"]
        out += [f"| {k} | {len(v)} | {_pct(fr)} | {_fmt(_med(c.difficulty for c in v))} |"
                for fr, k, v in rows[:15]]
    # standards cohorts
    cohorts: dict[str, list[Card]] = {}
    for c in old:
        cohorts.setdefault(c.std or "untagged", []).append(c)
    if len(cohorts) > 1:
        out += ["", "## By standards version (did the last rule change help?)", "",
                "| version | kind | cards | fail rate | median difficulty |", "|---|---|---|---|---|"]
        for v in sorted(cohorts):
            for kind in ("code", "concept"):
                sel = [c for c in cohorts[v] if (c.kind == "code") == (kind == "code")]
                if sel:
                    out.append(f"| {v} | {kind} | {len(sel)} | {_pct(pooled(sel)[0])} | "
                               f"{_fmt(_med(c.difficulty for c in sel))} |")
    out += ["", "## Suggested limits (heuristic — review before adopting)", "", *sugg]
    leeches = sorted((c for c in cards if c.lapses >= 5), key=lambda c: -c.lapses)
    if leeches:
        out += ["", "## Leeches", "", "| id | lapses | kind | size | front |", "|---|---|---|---|---|"]
        out += [f"| {c.card_id or '–'} | {c.lapses} | {c.kind} | {_size(c)} | {c.front} |"
                for c in leeches[:30]]
    rated = sorted((c for c in old if c.difficulty is not None), key=lambda c: -c.difficulty)
    if rated:
        out += ["", "## Hardest 15 (FSRS difficulty)", "",
                "| id | difficulty | fail rate | size | front |", "|---|---|---|---|---|"]
        out += [f"| {c.card_id or '–'} | {_fmt(c.difficulty)} | {_pct(c.fail_rate)} | {_size(c)} | "
                f"{c.front} |" for c in rated[:15]]
        out += ["", "## Easiest 15", "", "| id | difficulty | fail rate | size | front |",
                "|---|---|---|---|---|"]
        out += [f"| {c.card_id or '–'} | {_fmt(c.difficulty)} | {_pct(c.fail_rate)} | {_size(c)} | "
                f"{c.front} |" for c in rated[-15:]]
    return "\n".join(out) + "\n"


def _size(c: Card) -> str:
    m = c.measures
    if "typed_chars" in m:
        return f"{m['typed_chars']} typed"
    if "answer_chars" in m:
        return f"{m['answer_chars']}/{m['bold_chars']} ans/bold"
    return "–"


def write_csv(cards: list[Card], p: Path):
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["card_id", "anki_cid", "deck", "kind", "std", "typed_chars", "typed_lines",
                    "answer_chars", "bold_chars", "difficulty", "stability", "ivl", "lapses",
                    "review_answers", "fail_rate", "median_ms", "timer_hits", "front"])
        for c in cards:
            m = c.measures
            w.writerow([c.card_id, c.cid, c.deck, c.kind, c.std, m.get("typed_chars", ""),
                        m.get("typed_lines", ""), m.get("answer_chars", ""),
                        m.get("bold_chars", ""), _fmt(c.difficulty, 2), _fmt(c.stability, 1),
                        c.ivl, c.lapses, len(c.review),
                        "" if c.fail_rate is None else f"{c.fail_rate:.3f}",
                        c.median_ms or "", c.timer_hits, c.front])


def stats(export: Path, deck: str | None, home_dir: Path | None, mark: bool) -> int:
    home = find_home(home_dir or Path.cwd())
    con, _tmp = open_collection(export)
    cards = load_cards(con, deck)
    if not cards:
        raise SystemExit("No cards matched" + (f" deck '{deck}'" if deck else "") + ".")
    out_dir = (home.path / "evidence") if home.path else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    sp = state_path(home, out_dir)
    state = read_state(sp)
    today = dt.date.today().isoformat()
    rep = out_dir / f"{today}-report.md"
    rep.write_text(report(cards, home, export, deck, state), encoding="utf-8")
    write_csv(cards, out_dir / f"{today}-cards.csv")
    due, why, snap = refresh_status(cards, home, state)
    print(f"{'REFRESH DUE' if due else 'not due'}: {why}")
    print(f"Report: {rep}")
    if mark:
        state["last"] = snap
        state.setdefault("history", []).append(snap)
        sp.write_text(yaml.safe_dump(state, sort_keys=False), encoding="utf-8")
        print(f"Marked refreshed in {sp}.")
    return 0
