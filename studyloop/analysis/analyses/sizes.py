# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Card size against fail rate, per card type, and the limits that follow from it."""
from __future__ import annotations

from studyloop.analysis.analyses.helpers import (
    ANSWER_BINS,
    BOLD_BINS,
    CODE_BINS,
    GAP_BINS,
    _bins_summary,
    _fmt,
    _pct,
    bin_table,
    of_kind,
    pooled,
    spearman,
    studied,
    suggest,
)
from studyloop.analysis.types import Analysis, Section


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
