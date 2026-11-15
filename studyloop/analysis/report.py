"""`asl stats`: analyse a manual Anki export and report what makes cards hard for *you*.

    asl stats export.apkg [--deck "Study Loop"] [--home <card home>] [--only a,b] [--mark-refreshed]

Export from Anki: File > Export > "Anki Deck Package (.apkg)" with "Include scheduling
information" ticked (or a whole-collection .colpkg). Nothing here talks to Anki.

Writes, into <card home>/evidence/ (or the current folder):
  <date>-<deck>-report.md    every analysis's section, tables and figures (.svg beside it): for you
  <date>-<deck>-summary.md   each section's summary and every suggestion: for the agent
                             (refresh-standards turns the suggestions into an edit you approve)
  <date>-<deck>-cards.csv    one row per card with its measures and review stats

Definitions: "review answers" are review-phase answers (revlog type 1); "fail" is an Again on
one of them; "mature" is an interval of 21 days or more; cards younger than
`min_card_age_days` are left out of the size analysis.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

import yaml

from ..core.config import find_home
from ..core.registry import registry
from ..core.reviews import read_export
from .analysis import Analysis, Data, Section
from .bundled import _fmt, limit_line, refresh_status
from .table import card_files, card_frame, load_cards, review_frame

SUGGESTIONS_ORDER = 70            # the suggested limits, between the descriptions and the cards
CSV_COLUMNS = ["card_id", "anki_cid", "deck", "kind", "std", "typed_chars", "typed_lines",
               "answer_chars", "bold_chars", "gap_chars", "gaps", "hook", "difficulty",
               "stability", "ivl", "lapses", "review_answers", "fail_rate", "median_ms",
               "timer_hits", "front", "file", "source_note"]


def analyses(only: list[str] | None = None) -> list[Analysis]:
    found = {name: a for name, (_m, a) in registry().provided("analysis").items()}
    if only:
        unknown = [n for n in only if n not in found]
        if unknown:
            raise SystemExit(f"Unknown analysis: {', '.join(unknown)} (have: {', '.join(sorted(found))})")
        found = {n: found[n] for n in only}
    return sorted(found.values(), key=lambda a: (a.order, a.name))


def run(data: Data, only: list[str] | None = None) -> list[tuple[int, Section]]:
    out = []
    for a in analyses(only):
        sec = a.run(data)
        if sec is not None:
            out.append((a.order, sec))
    return out


def render_report(data: Data, sections: list[tuple[int, Section]], out_dir: Path, stem: str) -> str:
    lines = [f"# Card evidence report — {dt.date.today().isoformat()}", "",
             f"Source: `{data.export.name}`{f', deck `{data.deck}`' if data.deck else ''}. "
             f"Standards version in use: v{data.home.standards_version}."]
    limits = [s for _, sec in sections for s in sec.suggestions if s.kind == "limit"]
    placed = False
    for order, sec in sections:
        if not placed and order > SUGGESTIONS_ORDER:
            lines += _limits_block(limits)
            placed = True
        lines += ["", f"## {sec.title}", "", sec.markdown]
        for name, fig in sec.figures:
            f = out_dir / f"{stem}-{name}.svg"
            fig.savefig(f, format="svg", bbox_inches="tight")
            lines += ["", f"![{name}]({f.name})"]
    if not placed:
        lines += _limits_block(limits)
    return "\n".join(lines) + "\n"


def _limits_block(limits) -> list[str]:
    return ["", "## Suggested limits (heuristic — review before adopting)", "",
            *[limit_line(s) for s in limits]]


def render_summary(data: Data, sections: list[tuple[int, Section]], report_name: str) -> str:
    """What the agent reads: a few lines per section and the suggestions, nothing else."""
    lines = [f"# Card evidence summary — {dt.date.today().isoformat()}", "",
             f"Source: `{data.export.name}`{f', deck `{data.deck}`' if data.deck else ''}; "
             f"standards v{data.home.standards_version}. Tables and fronts: `{report_name}`.", ""]
    for _, sec in sections:
        if sec.summary:
            lines.append(f"- **{sec.title}**: " + sec.summary.replace("\n", "; "))
    changes = [s for _, sec in sections for s in sec.suggestions if s.new != s.old]
    lines += ["", "## Suggestions" + ("" if changes else ": none"), ""]
    for s in changes:
        lines.append(f"- `{s.target}` ({s.kind}, confidence {s.confidence}): {s.old} → {s.new}. "
                     f"{s.evidence}")
    return "\n".join(lines) + "\n"


def write_csv(data: Data, p: Path) -> None:
    def cell(v, nd=None):
        if v is None or (not isinstance(v, (list, str)) and _isna(v)):
            return ""
        return _fmt(v, nd) if nd is not None else v
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for _, r in data.cards.iterrows():
            w.writerow([r["card_id"], r["cid"], r["deck"], r["kind"], r["std"],
                        *(cell(r[m]) for m in ("typed_chars", "typed_lines", "answer_chars",
                                               "bold_chars", "gap_chars", "gaps", "hook")),
                        _fmt(r["difficulty"], 2), _fmt(r["stability"], 1), r["ivl"], r["lapses"],
                        r["reviews"], "" if _isna(r["fail_rate"]) else f"{r['fail_rate']:.3f}",
                        r["median_ms"] or "", r["timer_hits"], r["front"], r["file"], r["source_note"]])


def _isna(v) -> bool:
    import pandas as pd
    return bool(pd.isna(v))


def stats(export: Path, deck: str | None, home_dir: Path | None, mark: bool,
          only: list[str] | None = None) -> int:
    home = find_home(home_dir or Path.cwd())
    rd = read_export(export)
    cards = load_cards(rd, deck)
    if not cards:
        raise SystemExit("No study-loop cards matched" + (f" deck '{deck}'" if deck else "") + ".")
    out_dir = (home.path / "evidence") if home.path else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    sp = out_dir / "refresh-state.yaml"
    state = (yaml.safe_load(sp.read_text(encoding="utf-8")) or {}) if sp.is_file() else {}
    key = deck or "(all decks)"
    sub = state.setdefault("decks", {}).setdefault(key, {})
    data = Data(card_frame(cards, card_files(home)), review_frame(rd, {c.cid for c in cards}),
                home, deck, export, sub)
    slug = re.sub(r"[^a-z0-9]+", "-", (deck or "all").lower()).strip("-")
    stem = f"{dt.date.today().isoformat()}-{slug}"
    sections = run(data, only)
    rep = out_dir / f"{stem}-report.md"
    rep.write_text(render_report(data, sections, out_dir, stem), encoding="utf-8")
    summ = out_dir / f"{stem}-summary.md"
    summ.write_text(render_summary(data, sections, rep.name), encoding="utf-8")
    write_csv(data, out_dir / f"{stem}-cards.csv")
    due, why, snap = refresh_status(data)
    matched = int(data.cards["matched"].sum())
    print(f"{'REFRESH DUE' if due else 'not due'}: {why}")
    print(f"Report: {rep}\nSummary: {summ}  ({matched} of {len(data.cards)} cards matched to card files)")
    if mark:
        sub["last"] = snap
        sub.setdefault("history", []).append(snap)
        sp.write_text(yaml.safe_dump(state, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(f"Marked refreshed for {key} in {sp}.")
    return 0
