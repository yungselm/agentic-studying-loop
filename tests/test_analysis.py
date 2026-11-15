"""asl stats: the cards table joined to the card files, the analyses, report and summary."""
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

from studyloop.analysis import report as REP
from studyloop.analysis.analysis import Data, Section, Suggestion
from studyloop.core.build import build
from studyloop.core.cli import main
from studyloop.core.config import find_home, resolve_inputs

REPO = Path(__file__).resolve().parent.parent
DAY = 86400000


def _studied_home(tmp: Path) -> tuple[Path, Path]:
    """A copy of the example card home and an export of its tasklog deck with reviews."""
    home = tmp / "home"
    shutil.copytree(REPO / "example-vault/Studying/Anki cards", home)
    apkg = tmp / "built.apkg"
    build(resolve_inputs([str(home / "tasklog")]), apkg)
    out = tmp / "studied.apkg"
    with zipfile.ZipFile(apkg) as z:
        z.extractall(tmp / "x")
    con = sqlite3.connect(tmp / "x" / "collection.anki2")
    for nid, in con.execute("select id from notes").fetchall():          # 100 days old
        con.execute("update notes set id = ? where id = ?", (nid - 100 * DAY, nid))
        con.execute("update cards set nid = ? where nid = ?", (nid - 100 * DAY, nid))
    for i, (cid,) in enumerate(con.execute("select id from cards").fetchall()):
        con.execute("update cards set type = 2, queue = 2, ivl = 30, lapses = ?, data = ? "
                    "where id = ?", (6 if i == 0 else 0, json.dumps({"d": i % 9 + 1, "s": 20}), cid))
        for k in range(12):
            con.execute("insert into revlog values (?, ?, -1, ?, 30, 20, 2500, 8000, 1)",
                        (1_700_000_000_000 + i * 100 + k, cid, 1 if k < 2 else 3))
    con.commit()
    con.close()
    with zipfile.ZipFile(out, "w") as z:
        for p in (tmp / "x").iterdir():
            z.write(p, p.name)
    return home, out


def test_stats_joins_card_files_and_writes_report_and_summary(tmp_path, capsys):
    home, export = _studied_home(tmp_path)
    assert main(["stats", str(export), "--home", str(home)]) == 0
    out = capsys.readouterr().out
    assert "(12 of 12 cards matched to card files)" in out
    ev = home / "evidence"
    report = next(ev.glob("*-report.md")).read_text(encoding="utf-8")
    summary = next(ev.glob("*-summary.md")).read_text(encoding="utf-8")
    for title in ("## Refresh status", "## Overview", "## Suggested limits", "## Leeches"):
        assert title in report
    assert "- **Leeches**: 1 leech(es)" in summary and "## Suggestions" in summary
    assert len(summary) < len(report) / 2                       # the agent reads less
    csv = next(ev.glob("*-cards.csv")).read_text(encoding="utf-8")
    assert "tasklog/tasklog.yaml" in csv and "Atomic file writes" in csv     # the join

    for f in ev.glob("*"):
        f.unlink()
    assert main(["stats", str(export), "--home", str(home), "--only", "overview,leeches"]) == 0
    report = next(ev.glob("*-report.md")).read_text(encoding="utf-8")
    assert "## Leeches" in report and "## Refresh status" not in report


def test_report_renders_figures_and_only_changing_suggestions(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    keep = Suggestion("limits.code.typed_chars", "limit", "80/120", "80/120", "same", "low")
    change = Suggestion("limits.code.typed_chars", "limit", "80/120", "60/100", "worse above 60", "medium")
    secs = [(30, Section("Weak topics", summary="L03 is weakest", markdown="| x |",
                         figures=[("weak", fig)], suggestions=[keep, change]))]
    data = Data(pd.DataFrame(), pd.DataFrame(), find_home(tmp_path), None, tmp_path / "e.apkg")
    rep = REP.render_report(data, secs, tmp_path, "day")
    assert "![weak](day-weak.svg)" in rep and (tmp_path / "day-weak.svg").read_text().startswith("<?xml")
    summ = REP.render_summary(data, secs, "day-report.md")
    assert "- **Weak topics**: L03 is weakest" in summ
    assert "80/120 → 60/100" in summ and "→ 80/120" not in summ
