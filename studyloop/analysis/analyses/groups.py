# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""How groups of cards do: per card type, per deck, per standards version."""
from __future__ import annotations

from studyloop.analysis.analyses.helpers import (
    LEECH_LAPSES,
    _fmt,
    _med,
    _pct,
    of_kind,
    pooled,
    studied,
)
from studyloop.analysis.types import Analysis, Section


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
