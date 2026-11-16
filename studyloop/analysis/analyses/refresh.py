"""Is a refresh of the standards due? Enough of the deck matured since the last one."""
from __future__ import annotations

import datetime as dt

from studyloop.analysis.analyses.helpers import _pct
from studyloop.analysis.types import Analysis, Data, Section


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
