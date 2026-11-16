"""Shared by the bundled analyses: pooled fail rates, size bins, the limit heuristic, the
cards old enough to judge, table rows."""
from __future__ import annotations

import datetime as dt
import statistics as st

import pandas as pd

from studyloop.analysis.types import Data, Suggestion

CODE_BINS = [0, 40, 80, 120, 160, 250, 10**9]
ANSWER_BINS = [0, 150, 250, 300, 450, 10**9]
BOLD_BINS = [0, 80, 120, 150, 250, 10**9]
GAP_BINS = [0, 10, 20, 40, 80, 10**9]
MIN_BIN_ANSWERS = 60
LEECH_LAPSES = 5


# ---- helpers -----------------------------------------------------------------------------

def _none(x):
    return None if x is None or pd.isna(x) else x


def _pct(x):
    x = _none(x)
    return "–" if x is None else f"{100 * x:.0f}%"


def _fmt(x, nd=1):
    x = _none(x)
    return "–" if x is None else f"{x:.{nd}f}"


def _med(xs):
    xs = [x for x in map(_none, xs) if x is not None]
    return st.median(xs) if xs else None


def pooled(df: pd.DataFrame) -> tuple[float | None, int]:
    """(fails / review answers, review answers) over a group of cards."""
    rev = int(df["reviews"].sum())
    return (int(df["fails"].sum()) / rev) if rev else None, rev


def timer_share(df: pd.DataFrame) -> float | None:
    n = int(df["answers"].sum())
    return (int(df["timer_hits"].sum()) / n) if n else None


def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(map(_none, xs), map(_none, ys)) if x is not None and y is not None]
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


def bin_table(df: pd.DataFrame, key: str, bins, title: str):
    rows = [f"| {title} | cards | review answers | fail rate | hit 60 s timer | median difficulty |",
            "|---|---|---|---|---|---|"]
    stats = []
    x = df[key].fillna(-1)
    for lo, hi in zip(bins, bins[1:]):
        sel = df[((lo < x) & (x <= hi)) | ((lo == 0) & (x == 0))]
        fr, n = pooled(sel)
        ts = timer_share(sel)
        label = f"{lo}–{hi}" if hi < 10**9 else f">{lo}"
        rows.append(f"| {label} | {len(sel)} | {n} | {_pct(fr)}{' (few)' if n < MIN_BIN_ANSWERS else ''}"
                    f" | {_pct(ts)} | {_fmt(_med(sel['difficulty']))} |")
        stats.append((lo, hi, fr, n, ts))
    return "\n".join(rows), stats


def _bins_summary(stats, unit: str) -> str:
    return f"fail rate by {unit}: " + ", ".join(
        f"{lo}–{hi if hi < 10**9 else '∞'} {_pct(fr)}{'*' if n < MIN_BIN_ANSWERS else ''}"
        for lo, hi, fr, n, _ in stats if n) + " (* = few answers)"


def suggest(stats, current_target, current_max, setting: str) -> Suggestion:
    """Heuristic, relative to the smallest cards (the best you do):
    target = top of the last bin (in a row) within `tol` of that fail rate,
    max = bottom of the first later bin clearly worse (>= 1.5x the reference,
    or >= 50% of answers hitting the 60 s timer). Bins with fewer than
    MIN_BIN_ANSWERS answers are ignored."""
    old = f"{current_target}/{current_max}"
    ok = [s for s in stats if s[3] >= MIN_BIN_ANSWERS and s[2] is not None]
    if len(ok) < 3:
        return Suggestion(setting, "limit", old, old, "not enough data yet", "low")
    ref = ok[0][2]
    tol = max(0.05, 0.35 * ref)
    target = ok[0][1]
    for lo, hi, fr, _n, _ts in ok[1:]:
        if fr <= ref + tol and hi < 10**9:
            target = hi
        else:
            break
    worse = next((lo for lo, hi, fr, _n, ts in ok
                  if lo >= target and (fr >= max(1.5 * ref, ref + tol) or (ts or 0) >= 0.5)),
                 None)
    t = min(target, 10**6)
    m = worse if worse is not None else current_max
    m = max(m, t)
    answers = sum(s[3] for s in ok)
    return Suggestion(setting, "limit", old, f"{t}/{m}",
                      f"reference fail rate {_pct(ref)} in the smallest bin",
                      "high" if len(ok) >= 4 and answers >= 10 * MIN_BIN_ANSWERS else "medium")


def limit_line(s: Suggestion) -> str:
    """A limit suggestion as the report shows it."""
    label = s.target.rsplit(".", 1)[-1].replace("_", " ")
    if s.evidence == "not enough data yet":
        return f"- {label}: not enough data yet (keep {s.old})."
    t, m = s.new.split("/")
    flag = "" if s.new == s.old else "  ← differs from current"
    return f"- {label}: target ≈ {t}, max ≈ {m} (current {s.old}; {s.evidence}){flag}"


def studied(data: Data) -> pd.DataFrame:
    """Cards old enough for the size analysis (`min_card_age_days`) with review answers."""
    cutoff = dt.datetime.now() - dt.timedelta(days=data.home.refresh["min_card_age_days"])
    c = data.cards
    return c[(c["created"] <= cutoff) & (c["reviews"] > 0)]


def of_kind(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Timeline cards count as concept cards (same note type, same limits)."""
    kinds = ("concept", "timeline") if kind == "concept" else (kind,)
    return df[df["kind"].isin(kinds)]


def _size(row) -> str:
    if _none(row["typed_chars"]) is not None:
        return f"{row['typed_chars']} typed"
    if _none(row["gap_chars"]) is not None:
        return f"{row['gap_chars']} gap/{row['gaps']} gaps"
    if _none(row["answer_chars"]) is not None:
        return f"{row['answer_chars']}/{row['bold_chars']} ans/bold"
    return "–"


def _by(df: pd.DataFrame, key: str, ascending: bool) -> pd.DataFrame:
    """Stable sort (ties keep the export's order), like Python's sorted()."""
    k = df[key] if ascending else -df[key]
    return df.assign(_k=k).sort_values("_k", kind="stable").drop(columns="_k")


def _card_rows(df: pd.DataFrame, cols) -> list[str]:
    return ["| " + " | ".join(f(r) for f in cols) + " |" for _, r in df.iterrows()]


def _rated(data: Data) -> pd.DataFrame:
    old = studied(data)
    return _by(old[old["difficulty"].notna()], "difficulty", ascending=False)


_RATED_COLS = [lambda r: r["card_id"] or "–", lambda r: _fmt(r["difficulty"]),
               lambda r: _pct(r["fail_rate"]), _size, lambda r: r["front"]]
