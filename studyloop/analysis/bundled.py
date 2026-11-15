"""The analyses that ship with the tool: what `asl stats` reported before it had modules,
one section each. Card sizes are binned against fail rates and turn into suggested limits;
the rest describe (by deck, by standards version, leeches, hardest and easiest cards)."""
from __future__ import annotations

import datetime as dt
import statistics as st

import pandas as pd

from .analysis import Analysis, Data, Section, Suggestion

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


# ---- the analyses --------------------------------------------------------------------------

def refresh_status(data: Data) -> tuple[bool, str, dict]:
    r = data.home.refresh
    cards = data.cards
    total = len(cards)
    mature = int((cards["ivl"] >= r["mature_ivl_days"]).sum())
    answers = int(cards["reviews"].sum())
    share = mature / total if total else 0
    last = data.state.get("last") or {}
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


class RefreshStatus(Analysis):
    name, order = "refresh-status", 0

    def run(self, data):
        due, why, _ = refresh_status(data)
        line = f"**{'Refresh due' if due else 'Not due yet'}**: {why}"
        return Section("Refresh status", summary=line.replace("**", ""), markdown=line)


class Overview(Analysis):
    name, order = "overview", 10

    def run(self, data):
        old, r = studied(data), data.home.refresh
        rows = ["| | cards | fail rate | median difficulty | leeches (≥5 lapses) |",
                "|---|---|---|---|---|"]
        parts = []
        for kind in ("code", "concept", "cloze"):
            sel = of_kind(old, kind)
            if kind == "cloze" and sel.empty:
                continue
            fr, _ = pooled(sel)
            rows.append(f"| {kind} | {len(sel)} | {_pct(fr)} | {_fmt(_med(sel['difficulty']))} "
                        f"| {int((sel['lapses'] >= LEECH_LAPSES).sum())} |")
            if len(sel):
                parts.append(f"{kind} {len(sel)} cards, fail {_pct(fr)}")
        head = (f"{len(data.cards)} cards, {int(data.cards['answers'].sum())} answers. "
                f"Size analysis uses the {len(old)} cards older than {r['min_card_age_days']} days "
                "that have review answers.")
        return Section("Overview", summary=head.split(" Size")[0] + " " + "; ".join(parts) + ".",
                       markdown=head + "\n\n" + "\n".join(rows))


class CodeSize(Analysis):
    name, order = "code-size", 20

    def run(self, data):
        code = of_kind(studied(data), "code")
        if code.empty:
            return None
        lim = data.home.limits["code"]
        t, s = bin_table(code, "typed_chars", CODE_BINS, "typed chars")
        rho = spearman(code["typed_chars"].tolist(), code["fail_rate"].tolist())
        return Section(
            "Code cards: typed size", summary=_bins_summary(s, "typed chars") + f"; ρ {_fmt(rho, 2)}",
            markdown=f"{t}\n\nSpearman ρ (typed chars vs card fail rate): {_fmt(rho, 2)}",
            suggestions=[suggest(s, lim["typed_chars_target"], lim["typed_chars_max"],
                                 "limits.code.typed_chars")])


class ConceptSize(Analysis):
    name, order = "concept-size", 21

    def run(self, data):
        concept = of_kind(studied(data), "concept")
        if concept.empty:
            return None
        lim = data.home.limits["concept"]
        t1, s1 = bin_table(concept, "answer_chars", ANSWER_BINS, "answer chars")
        t2, s2 = bin_table(concept, "bold_chars", BOLD_BINS, "bold lead chars")
        return Section(
            "Concept cards: answer size",
            summary=_bins_summary(s1, "answer chars") + "\n" + _bins_summary(s2, "bold lead chars"),
            markdown=f"{t1}\n\n{t2}",
            suggestions=[suggest(s1, lim["answer_chars_target"], lim["answer_chars_max"],
                                 "limits.concept.answer_chars"),
                         suggest(s2, lim["bold_chars_target"], lim["bold_chars_max"],
                                 "limits.concept.bold_chars")])


class ClozeSize(Analysis):
    name, order = "cloze-size", 22

    def run(self, data):
        cloze = of_kind(studied(data), "cloze")
        if cloze.empty:
            return None
        lim = data.home.limits["cloze"]
        t, s = bin_table(cloze, "gap_chars", GAP_BINS, "gap chars")
        t2, _ = bin_table(cloze, "gaps", [0, 1, 5, 10**9], "gaps per note")
        t3 = ["| hook | cards | review answers | fail rate |", "|---|---|---|---|"]
        hooks = []
        for label, h in (("none", 0), ("yes", 1)):
            sel = cloze[cloze["hook"].fillna(-1) == h]
            fr, n = pooled(sel)
            t3.append(f"| {label} | {len(sel)} | {n} | {_pct(fr)} |")
            hooks.append(f"{label} {_pct(fr)}")
        return Section(
            "Cloze cards", summary=_bins_summary(s, "gap chars") + "; hooks: " + ", ".join(hooks),
            markdown=f"{t}\n\n{t2}\n\nHooks (mnemonic, scene) have no measured effect yet; "
                     "this tests yours:\n\n" + "\n".join(t3),
            suggestions=[suggest(s, lim["gap_chars_target"], lim["gap_chars_max"],
                                 "limits.cloze.gap_chars")])


class CodeByDeck(Analysis):
    name, order = "code-by-deck", 40

    def run(self, data):
        code = of_kind(studied(data), "code")
        groups = [(pooled(g)[0] or 0, deck, g) for deck, g in code.groupby("deck", sort=False)
                  if pooled(g)[1] >= 30]
        rows = sorted(groups, key=lambda x: (x[0], x[1]), reverse=True)
        if not rows:
            return None
        md = ["| deck | cards | fail rate | median difficulty |", "|---|---|---|---|"]
        md += [f"| {k} | {len(v)} | {_pct(fr)} | {_fmt(_med(v['difficulty']))} |"
               for fr, k, v in rows[:15]]
        return Section("Code cards by deck (hardest first, ≥30 review answers)",
                       summary="hardest: " + ", ".join(f"{k} {_pct(fr)}" for fr, k, _ in rows[:3]),
                       markdown="\n".join(md))


class ByStandards(Analysis):
    name, order = "by-standards", 50

    def run(self, data):
        old = studied(data)
        version = old["std"].where(old["std"] != "", "untagged")
        if version.nunique() <= 1:
            return None
        md = ["| version | kind | cards | fail rate | median difficulty |", "|---|---|---|---|---|"]
        summary = []
        for v in sorted(version.unique()):
            cohort = old[version == v]
            bits = []
            for kind in ("code", "concept", "cloze"):
                sel = of_kind(cohort, kind)
                if len(sel):
                    md.append(f"| {v} | {kind} | {len(sel)} | {_pct(pooled(sel)[0])} | "
                              f"{_fmt(_med(sel['difficulty']))} |")
                    bits.append(f"{kind} {_pct(pooled(sel)[0])}")
            summary.append(f"{v}: " + ", ".join(bits))
        return Section("By standards version (did the last rule change help?)",
                       summary="; ".join(summary), markdown="\n".join(md))


class Leeches(Analysis):
    name, order = "leeches", 80

    def run(self, data):
        c = data.cards
        leeches = _by(c[c["lapses"] >= LEECH_LAPSES], "lapses", ascending=False)
        if leeches.empty:
            return None
        md = ["| id | lapses | kind | size | front |", "|---|---|---|---|---|"]
        md += _card_rows(leeches.head(30), [lambda r: r["card_id"] or "–", lambda r: str(r["lapses"]),
                                            lambda r: r["kind"], _size, lambda r: r["front"]])
        ids = [i for i in leeches["card_id"].head(10) if i]
        return Section("Leeches", summary=f"{len(leeches)} leech(es) (≥{LEECH_LAPSES} lapses)"
                       + (f": {', '.join(ids)}" if ids else ""), markdown="\n".join(md))


def _rated(data: Data) -> pd.DataFrame:
    old = studied(data)
    return _by(old[old["difficulty"].notna()], "difficulty", ascending=False)


_RATED_COLS = [lambda r: r["card_id"] or "–", lambda r: _fmt(r["difficulty"]),
               lambda r: _pct(r["fail_rate"]), _size, lambda r: r["front"]]


class Hardest(Analysis):
    name, order = "hardest", 90

    def run(self, data):
        rated = _rated(data)
        if rated.empty:
            return None
        md = ["| id | difficulty | fail rate | size | front |", "|---|---|---|---|---|"]
        md += _card_rows(rated.head(15), _RATED_COLS)
        ids = [i for i in rated["card_id"].head(15) if i]
        return Section("Hardest 15 (FSRS difficulty)", summary=", ".join(ids), markdown="\n".join(md))


class Easiest(Analysis):
    name, order = "easiest", 91

    def run(self, data):
        rated = _rated(data)
        if rated.empty:
            return None
        md = ["| id | difficulty | fail rate | size | front |", "|---|---|---|---|---|"]
        md += _card_rows(rated.tail(15), _RATED_COLS)
        ids = [i for i in rated["card_id"].tail(15) if i]
        return Section("Easiest 15", summary=", ".join(ids), markdown="\n".join(md))


BUNDLED = (RefreshStatus(), Overview(), CodeSize(), ConceptSize(), ClozeSize(), CodeByDeck(),
           ByStandards(), Leeches(), Hardest(), Easiest())
