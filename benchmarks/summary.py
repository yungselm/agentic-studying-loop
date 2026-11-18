"""Tokens, cost and cards per setup and arm, from a batch's runs.jsonl (medians over runs), and
the 1-5 ratings from rate.py once there are some.

    python benchmarks/summary.py pilot
    python benchmarks/summary.py pilot v2      # several batches: each arm labelled arm@batch
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

BENCH = Path(__file__).resolve().parent
ORDER = ["haiku-medium", "sonnet-medium", "opus-low", "opus-medium", "opus-high"]


def _k(n: float) -> str:
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


def table(runs: list[dict]) -> str:
    cells = defaultdict(list)
    for r in runs:
        if r["status"] == "ok":
            cells[(r["setup"], r["arm"])].append(r)
    rows = ["| setup | arm | runs | cache read | cache write | input | output | total | cost | "
            "cards | cards w/o lint problem | $ per card | min |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    keys = sorted(cells, key=lambda k: (ORDER.index(k[0]) if k[0] in ORDER else 99, k[1]))
    for setup, arm in keys:
        rs = cells[(setup, arm)]
        def med(f, rs=rs):
            return median(f(r) for r in rs)
        cards = med(lambda r: r["cards"])
        ok = (f"{med(lambda r: r['cards'] - r['cards_flagged']):.0f}" if not arm.startswith("plain")
              else "–")
        cost = med(lambda r: r["cost_usd"])
        rows.append(
            f"| {setup} | {arm} | {len(rs)} | {_k(med(lambda r: r['tokens'].get('cache_read', 0)))} | "
            f"{_k(med(lambda r: r['tokens'].get('cache_write', 0)))} | "
            f"{_k(med(lambda r: r['tokens'].get('input', 0)))} | "
            f"{_k(med(lambda r: r['tokens'].get('output', 0)))} | {_k(med(lambda r: r['tokens_total']))} | "
            f"${cost:.2f} | {cards:.0f} | {ok} | {'–' if not cards else f'${cost / cards:.3f}'} | "
            f"{med(lambda r: r['wall_s']) / 60:.0f} |")
    return "\n".join(rows)


def by_task(runs: list[dict]) -> str:
    """Cost and cards per task x setup, one column per arm: like-for-like comparisons."""
    ok = [r for r in runs if r["status"] == "ok"]
    arms = sorted({r["arm"] for r in ok})
    cell = defaultdict(list)
    for r in ok:
        cell[(r["task"], r["setup"], r["arm"])].append(r)
    rows = ["| task | setup | " + " | ".join(arms) + " |", "|---|---|" + "---|" * len(arms)]
    for task in sorted({r["task"] for r in ok}):
        for setup in [s for s in ORDER if any(r["setup"] == s and r["task"] == task for r in ok)]:
            vals = []
            for a in arms:
                rs = cell.get((task, setup, a))
                vals.append(f"${median(r['cost_usd'] for r in rs):.2f} · {median(r['cards'] for r in rs):.0f} c · "
                            f"{median(r.get('turns') or 0 for r in rs):.0f} t" if rs else "–")
            rows.append(f"| {task} | {setup} | " + " | ".join(vals) + " |")
    return "\n".join(rows)


def rating_table(rows: list[dict]) -> str:
    """Your 1-5 scores per setup and arm: count, median, mean, share rated 4 or 5, per kind."""
    cells = defaultdict(list)
    for r in rows:
        cells[(r["setup"], r["arm"])].append(r)
    kinds = sorted({r["kind"] for r in rows})
    out = ["| setup | arm | rated | median | mean | 4-5 | " + " | ".join(f"{k} mean" for k in kinds) + " |",
           "|---|---|---|---|---|---|" + "---|" * len(kinds)]
    for setup, arm in sorted(cells, key=lambda k: (ORDER.index(k[0]) if k[0] in ORDER else 99, k[1])):
        sc = [r["score"] for r in cells[(setup, arm)]]
        per_kind = []
        for k in kinds:
            ks = [r["score"] for r in cells[(setup, arm)] if r["kind"] == k]
            per_kind.append(f"{sum(ks) / len(ks):.1f} ({len(ks)})" if ks else "–")
        out.append(f"| {setup} | {arm} | {len(sc)} | {median(sc):g} | {sum(sc) / len(sc):.2f} | "
                   f"{sum(s >= 4 for s in sc) / len(sc):.0%} | " + " | ".join(per_kind) + " |")
    return "\n".join(out)


def load(batches: list[str], name: str) -> list[dict]:
    """Rows of results/<batch>/<name> for every batch; with several, arm becomes arm@batch."""
    out = []
    for b in batches:
        f = BENCH / "results" / b / name
        if not f.exists():
            continue
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                if len(batches) > 1:
                    r["arm"] = f"{r['arm']}@{b}"
                out.append(r)
    return out


def main() -> int:
    batches = sys.argv[1:] or ["pilot"]
    runs = load(batches, "runs.jsonl")
    if not runs:
        raise SystemExit(f"no runs.jsonl in results/ for {' '.join(batches)}")
    done = {(r["run_id"], r["arm"]) for r in runs if r["status"] == "ok"}
    bad = [r for r in runs if r["status"] != "ok" and (r["run_id"], r["arm"]) not in done]  # retried: gone
    print(table(runs))
    ok = [r for r in runs if r["status"] == "ok"]
    print(f"\n{len(ok)} ok run(s), total ${sum(r['cost_usd'] for r in ok):.2f} "
          f"(API list price; on a plan this is what the runs would have cost), "
          f"{sum(r['tokens_total'] for r in ok):,} tokens.")
    for r in bad:
        print(f"  {r['status']}: {r['run_id']} {r['error'][:200]}")
    print("\nPer task (median cost · cards · turns):\n")
    print(by_task(runs))
    rated = load(batches, "ratings.jsonl")
    if rated:
        print("\nYour ratings (1-5):\n")
        print(rating_table(rated))
    again = load(batches, "recheck.jsonl")
    if again:
        first = {(r["run_id"], r["key"]): r["score"] for r in rated}
        print("\nRe-rated cards (your scale between sessions):\n")
        for b in sorted({r["arm"].split("@")[-1] for r in again}):
            pairs = [(first[(r["run_id"], r["key"])], r["score"]) for r in again
                     if r["arm"].endswith(b) and (r["run_id"], r["key"]) in first]
            if pairs:
                a0, a1 = (sum(x) / len(pairs) for x in zip(*pairs))
                same = sum(x == y for x, y in pairs)
                print(f"- {b}: {len(pairs)} cards, first {a0:.2f} → now {a1:.2f} "
                      f"({a1 - a0:+.2f}); same score {same}/{len(pairs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
