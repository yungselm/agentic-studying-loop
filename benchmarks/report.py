# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""The benchmark report: charts for the docs, a short README section and the results part of
docs/benchmarks.md, from results/ (numbers only).

    uv run --extra bench python benchmarks/report.py

Arms as reported: plain (batch pilot), workflow (the skills, batch v2) and prompt (`asl prompt`,
batch v2). Ratings: plain from pilot, workflow from both batches, prompt from v2.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent
OUT = REPO / "docs" / "_static" / "benchmarks"
README = REPO / "README.md"
DOC = REPO / "docs" / "benchmarks.md"
BEGIN, END = "<!-- benchmark:begin -->", "<!-- benchmark:end -->"

SETUPS = ["haiku-medium", "sonnet-medium", "opus-low", "opus-medium", "opus-high"]
LABEL = {"haiku-medium": "Haiku\nmedium", "sonnet-medium": "Sonnet\nmedium", "opus-low": "Opus\nlow",
         "opus-medium": "Opus\nmedium", "opus-high": "Opus\nhigh"}
ARMS = {"plain": "pilot", "workflow": "v2", "prompt": "v2"}          # arm -> batch whose runs count
CHAPTER = {"rust-ch04": "Rust ch. 4", "rust-ch10": "Rust ch. 10",
           "coronary-ch13": "the OCT chapter", "coronary-ch20": "the FFR chapter"}
ARM_NAME = {"plain": "plain prompt", "workflow": "skills workflow", "prompt": "asl prompt"}
# dataviz reference palette, slots 1-3, validated light and dark (aqua < 3:1 light: tables carry it)
THEME = {
    "light": {"surface": "#fcfcfb", "text": "#0b0b0b", "muted": "#52514e", "grid": "#e4e3df",
              "plain": "#2a78d6", "workflow": "#eb6834", "prompt": "#1baf7a"},
    "dark": {"surface": "#1a1a19", "text": "#f0efec", "muted": "#c3c2b7", "grid": "#3a3a37",
             "plain": "#3987e5", "workflow": "#d95926", "prompt": "#199e70"},
}


# ---- data --------------------------------------------------------------------------------------

def _rows(batch: str, name: str) -> list[dict]:
    f = BENCH / "results" / batch / name
    if not f.exists():
        return []
    rows = [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for r in rows:
        r["batch"] = batch
    return rows


def runs() -> list[dict]:
    return [r for arm, b in ARMS.items() for r in _rows(b, "runs.jsonl")
            if r["arm"] == arm and r["status"] == "ok"]


def per_chapter(rs: list[dict], arm: str, setup: str, value) -> float | None:
    """Mean over chapters of the median over that chapter's runs."""
    by_task = defaultdict(list)
    for r in rs:
        if r["arm"] == arm and r["setup"] == setup:
            by_task[r["task"]].append(value(r))
    return mean(median(v) for v in by_task.values()) if by_task else None


def ratings() -> list[dict]:
    out = []
    for b in ("pilot", "v2"):
        out += [r for r in _rows(b, "ratings.jsonl") if ARMS.get(r["arm"]) == b or r["arm"] == "workflow"]
    return out


def ci(xs: list[int]) -> tuple[float, float, int]:
    """Mean and the half-width of its 95% interval."""
    return mean(xs), (1.96 * stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0), len(xs)


def recheck() -> list[tuple[str, float, float, int, int]]:
    out = []
    for b in ("pilot", "v2"):
        first = {r["key"]: r["score"] for r in _rows(b, "ratings.jsonl")}
        pairs = [(first[r["key"]], r["score"]) for r in _rows(b, "recheck.jsonl") if r["key"] in first]
        if pairs:
            a0, a1 = (mean(x) for x in zip(*pairs))
            out.append((b, a0, a1, sum(x == y for x, y in pairs), len(pairs)))
    return out


# ---- charts ------------------------------------------------------------------------------------

def _style(ax, t):
    ax.set_facecolor(t["surface"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(t["grid"])
    ax.tick_params(colors=t["muted"], length=0, labelsize=9)
    ax.grid(axis="y", color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def chart_cost(rs: list[dict], theme: str) -> Path:
    t = THEME[theme]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), facecolor=t["surface"])
    panels = [("Cost per chapter (USD, API list price)", lambda r: r["cost_usd"], "${:.2f}"),
              ("Cards per chapter", lambda r: r["cards"], "{:.0f}")]
    w = 0.26
    for ax, (title, value, _fmt) in zip(axes, panels):
        _style(ax, t)
        for i, arm in enumerate(ARMS):
            ys = [per_chapter(rs, arm, s, value) or 0 for s in SETUPS]
            ax.bar([x + (i - 1) * w for x in range(len(SETUPS))], ys, w, color=t[arm],
                   edgecolor=t["surface"], linewidth=1.5, label=ARM_NAME[arm])
        ax.set_xticks(range(len(SETUPS)), [LABEL[s] for s in SETUPS])
        if title.startswith("Cost"):
            ax.yaxis.set_major_formatter(lambda v, _pos: f"${v:.2f}")
        ax.set_title(title, loc="left", color=t["text"], fontsize=10.5, pad=10)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, fontsize=9,
               labelcolor=t["text"], bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _save(fig, f"cost-{theme}.svg")


def chart_quality(rated: list[dict], theme: str) -> Path:
    t = THEME[theme]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.0), facecolor=t["surface"],
                             gridspec_kw={"width_ratios": [1, 1.4]})
    groups = [("By arm (all models)", [(ARM_NAME[a], [r["score"] for r in rated if r["arm"] == a], t[a])
                                       for a in ARMS]),
              ("By model (all arms)", [(LABEL[s].replace("\n", " "),
                                        [r["score"] for r in rated if r["setup"] == s], t["muted"])
                                       for s in SETUPS])]
    for ax, (title, rows) in zip(axes, groups):
        _style(ax, t)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=t["grid"], linewidth=0.8)
        for y, (name, xs, color) in enumerate(reversed(rows)):
            m, h, n = ci(xs)
            ax.plot([m - h, m + h], [y, y], color=color, linewidth=2, solid_capstyle="round")
            ax.plot(m, y, "o", color=color, markersize=8, markeredgecolor=t["surface"], markeredgewidth=2)
            ax.text(m + h + 0.05, y, f"{m:.2f}  (n={n})", va="center", fontsize=8.5, color=t["muted"])
        ax.set_yticks(range(len(rows)), [r[0] for r in reversed(rows)])
        ax.set_xlim(2.5, 4.5)
        ax.set_ylim(-0.6, len(rows) - 0.4)
        ax.set_title(title, loc="left", color=t["text"], fontsize=10.5, pad=10)
    fig.text(0.01, 0.01, "Mean rating (1-5) with 95% interval; one rater, blind", fontsize=8.5,
             color=t["muted"])
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return _save(fig, f"quality-{theme}.svg")


def _save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / name
    fig.savefig(f, format="svg", facecolor=fig.get_facecolor(), metadata={"Date": None})
    plt.close(fig)
    return f


# ---- text --------------------------------------------------------------------------------------

def _rating_by(rated, key, val) -> str:
    xs = [r["score"] for r in rated if r[key] == val]
    m, h, n = ci(xs)
    return f"{m:.2f} ± {h:.2f}"


def spread(rs: list[dict], arm: str) -> list[tuple[str, int, int]]:
    """Per chapter: fewest and most cards across the models (runs that wrote cards)."""
    out = []
    for t in sorted({r["task"] for r in rs}):
        c = [r["cards"] for r in rs if r["arm"] == arm and r["task"] == t and r["cards"]]
        if c:
            out.append((t, min(c), max(c)))
    return out


def clean(rs: list[dict], arm: str) -> tuple[int, int]:
    """Runs whose every card passed lint and whose code compiled and passed its tests."""
    mine = [r for r in rs if r["arm"] == arm]
    return sum(r.get("cards_flagged") == 0 and r.get("check_ok") is not False for r in mine), len(mine)


def _cell(rs, arm, s) -> str:
    tok, usd, cards = (per_chapter(rs, arm, s, f) for f in
                       (lambda r: r["tokens_total"], lambda r: r["cost_usd"], lambda r: r["cards"]))
    return f"{tok / 1000:.0f}k · ${usd:.2f} · {cards:.0f}"


def readme_block(rs: list[dict], rated: list[dict]) -> str:
    rows = ["| model, effort | asl prompt: tokens · $ · cards | plain prompt: tokens · $ · cards "
            "| rating (1-5) |", "|---|---|---|---|"]
    for s in SETUPS:
        rows.append(f"| {LABEL[s].replace(chr(10), ', ')} | {_cell(rs, 'prompt', s)} | "
                    f"{_cell(rs, 'plain', s)} | {_rating_by(rated, 'setup', s)} |")
    widest = max(spread(rs, "plain"), key=lambda x: x[2] - x[1])
    asl = dict((t, (a, b)) for t, a, b in spread(rs, "prompt"))[widest[0]]
    ok, n = clean(rs, "prompt")
    n_runs, n_rated = len(rs), len(rated)
    return "\n".join([
        BEGIN,
        f"Four book chapters (Rust, coronary imaging), five model setups, three ways to make cards; "
        f"{n_runs} runs, {n_rated} cards rated blind (1-5) by the author. Per chapter, as a mean "
        "over the four; tokens include cache reads. [Full report](docs/benchmarks.md).",
        "",
        '<picture><source media="(prefers-color-scheme: dark)" '
        'srcset="docs/_static/benchmarks/cost-dark.svg">'
        '<img alt="Cost and cards per chapter by model and arm" '
        'src="docs/_static/benchmarks/cost-light.svg"></picture>',
        "",
        *rows,
        "",
        "**A plain prompt works too**: asked for Anki cards, a strong model writes decent ones, and "
        "card for card they were rated the same. What it doesn't give you is control. `asl` does:",
        "",
        f"- **How many cards.** The count follows the chapter's length and your brief: "
        f"{asl[0]}–{asl[1]} cards for {CHAPTER.get(widest[0], widest[0])} on every model, where a "
        f"plain prompt gave anywhere from {widest[1]} to {widest[2]}. Fewer cards of the same quality are fewer "
        "reviews for years.",
        f"- **Cards that follow your standards.** Size limits, one idea per card, cloze gaps you "
        f"can't guess, your own rules from `preferences.md`: `asl finish` checks every card "
        f"({ok} of {n} runs passed all checks); a plain prompt gives you whatever it writes.",
        "- **The right kind of card.** Typed code cards that compile and pass their tests, cloze "
        "and concept cards, the book's figures on the cards, and stable ids, so a re-import "
        "updates cards instead of duplicating them.",
        "- **About the same tokens as a plain prompt** on most models, and a quarter to a half of "
        "what the agent spends finding its own way with the skills. Low effort is enough "
        "(`claude --effort low`): more effort only adds turns, not better cards.",
        END])


def doc_block(rs: list[dict], rated: list[dict]) -> str:
    out = [BEGIN, "", "### Cost, tokens, turns and cards", "",
           "Per chapter: the mean over the four chapters of each chapter's median run.", "",
           "```{image} _static/benchmarks/cost-light.svg", ":class: only-light",
           ":alt: Cost and cards per chapter by model and arm", "```",
           "```{image} _static/benchmarks/cost-dark.svg", ":class: only-dark",
           ":alt: Cost and cards per chapter by model and arm", "```", "",
           "| model, effort | arm | $ / chapter | tokens | turns | cards | cards passing lint |",
           "|---|---|---|---|---|---|---|"]
    for s in SETUPS:
        for a in ARMS:
            v = [per_chapter(rs, a, s, f) for f in (lambda r: r["cost_usd"], lambda r: r["tokens_total"],
                                                   lambda r: r.get("turns") or 0, lambda r: r["cards"])]
            lint = ("all" if a != "plain" and all(r["cards_flagged"] == 0 for r in rs
                                                  if r["arm"] == a and r["setup"] == s) else "–")
            out.append(f"| {LABEL[s].replace(chr(10), ', ')} | {ARM_NAME[a]} | ${v[0]:.2f} | "
                       f"{v[1] / 1000:.0f}k | {v[2]:.0f} | {v[3]:.0f} | {lint} |")
    total = sum(r["cost_usd"] for r in rs)
    out += ["", f"{len(rs)} runs, ${total:.2f} at API list price.", "",
            "### Card quality", "",
            "```{image} _static/benchmarks/quality-light.svg", ":class: only-light",
            ":alt: Mean rating by arm and by model", "```",
            "```{image} _static/benchmarks/quality-dark.svg", ":class: only-dark",
            ":alt: Mean rating by arm and by model", "```", "",
            "| | mean rating ± 95% interval | rated |", "|---|---|---|"]
    for a in ARMS:
        out.append(f"| {ARM_NAME[a]} | {_rating_by(rated, 'arm', a)} | "
                   f"{sum(r['arm'] == a for r in rated)} |")
    for s in SETUPS:
        out.append(f"| {LABEL[s].replace(chr(10), ', ')} | {_rating_by(rated, 'setup', s)} | "
                   f"{sum(r['setup'] == s for r in rated)} |")
    rc = recheck()
    if rc:
        out += ["", "**Re-rating.** Cards rated again, blind, in a later session:", ""]
        out += [f"- {b} cards: {n} re-rated, mean {a0:.2f} → {a1:.2f} ({a1 - a0:+.2f}), "
                f"same score {same} of {n}." for b, a0, a1, same, n in rc]
        out += ["", "The rater's scale drifted by 0.2–0.3 between sessions and a single card's "
                "score can move by up to three points, so differences below about 0.3 between "
                "arms are noise."]
    return "\n".join(out + ["", END])


def put(f: Path, block: str) -> None:
    text = f.read_text(encoding="utf-8")
    if BEGIN not in text:
        raise SystemExit(f"{f.name}: add {BEGIN} / {END} where the report goes")
    f.write_text(re.sub(re.escape(BEGIN) + ".*?" + re.escape(END), lambda _m: block, text,
                        flags=re.S), encoding="utf-8")


def main() -> int:
    rs, rated = runs(), ratings()
    for theme in THEME:
        chart_cost(rs, theme)
        chart_quality(rated, theme)
    put(README, readme_block(rs, rated))
    put(DOC, doc_block(rs, rated))
    print(f"charts in {OUT.relative_to(REPO)}; README.md and {DOC.relative_to(REPO)} updated "
          f"({len(rs)} runs, {len(rated)} ratings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
