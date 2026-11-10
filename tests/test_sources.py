"""Sources map: PDF bookmarks -> parts, split by batch size, status from cards and notes."""
import json
import textwrap
from pathlib import Path

import pypdf

from studyloop import config, sources
from studyloop.cli import main


def book(path: Path) -> None:
    """20 blank pages; bookmarks: Cover, 1 Basics (2 sections), 2 Classes, Index."""
    w = pypdf.PdfWriter()
    for _ in range(20):
        w.add_blank_page(100, 100)
    w.add_outline_item("Cover", 0)
    ch1 = w.add_outline_item("1 The Basics", 2)
    w.add_outline_item("1.1 Programs", 2, parent=ch1)
    w.add_outline_item("1.2 Functions", 6, parent=ch1)
    w.add_outline_item("2 Classes", 10)
    w.add_outline_item("Index", 17)
    with open(path, "wb") as f:
        w.write(f)


def topic(tmp: Path, batch: int = 12000) -> Path:
    v = tmp / "v"
    (v / ".obsidian").mkdir(parents=True)
    (v / "Books").mkdir()
    book(v / "Books" / "Tour.pdf")
    (v / "Notes").mkdir()
    (v / "Notes" / "Classes.md").write_text('---\nsource: "[[Tour.pdf#page=12]]"\n---\n# Classes\n')
    d = v / "cards"
    d.mkdir()
    (d / "deck.yaml").write_text("deck: T\nprefix: t\n")
    (d / "a.yaml").write_text(textwrap.dedent("""\
        - id: t-001
          type: concept
          question: q1?
          answer: "**a.**"
          source: "[[Tour.pdf#page=4]]"
        - id: t-002
          type: concept
          question: q2?
          answer: "**a.**"
          source: "[[Classes]]"
        - id: t-003
          type: concept
          question: q3?
          answer: "**a.**"
          source: "https://example.org/guide#S-errors"
        """))
    (d / "Overview.md").write_text(textwrap.dedent(f"""\
        ---
        type: overview
        notes: Notes
        batch: {batch}
        sources:
          - "[[Tour.pdf]]"
          - {{url: "https://example.org/guide", key: g, parts: ["#S-resource", "#S-errors"]}}
          - Missing.pdf
        ---
        # T

        ## Topics

        | id | status | type | from |
        |---|---|---|---|
        | t-001 | draft | concept | x |
        | t-002 | draft | concept | x |
        | t-003 | draft | concept | x |
        """))
    return d


def test_outline_parts_and_status(tmp_path):
    d = topic(tmp_path)
    assert main(["sources", str(d)]) == 0
    text = (d / "Overview.md").read_text()
    assert text.index("## Sources") < text.index("## Topics")          # map first: cheap to read
    assert "Cover" not in text and "Index" not in text                  # front/back matter left out
    assert "| tour.1 | 1 The Basics | 3–10 |" in text
    assert "| tour.2 | 2 Classes | 11–17 | 0 | 0 | notes 1 · cards 1 |" in text
    assert "cards 1 |" in text.split("tour.1 |")[1].split("\n")[0]     # direct page link
    assert "g.1 | https://example.org/guide#S-resource | todo" in text
    assert "g.2 | https://example.org/guide#S-errors | cards 1" in text
    assert "Missing.pdf not found" in text
    assert "tour.1.1" not in text                                       # small chapter: no split


def test_rerun_replaces_block_and_splits_big_chapters(tmp_path):
    d = topic(tmp_path, batch=1000)
    main(["sources", str(d)])
    cache = json.loads((d / sources.CACHE).read_text())
    cache["Tour.pdf"]["words"] = [400] * 20                             # pretend the pages have text
    (d / sources.CACHE).write_text(json.dumps(cache))
    main(["sources", str(d)])
    text = (d / "Overview.md").read_text()
    assert text.count(sources.BEGIN) == 1
    assert "| tour.1.1 | ↳ 1.1 Programs | 3–6 | 1.6k |" in text           # 3.2k words > batch
    assert "| tour.1.2 | ↳ 1.2 Functions | 7–10 |" in text


def test_fix_refreshes_status(tmp_path):
    d = topic(tmp_path)
    main(["sources", str(d)])
    with open(d / "a.yaml", "a") as f:
        f.write('- type: concept\n  question: q4?\n  answer: "**a.**"\n'
                '  source: "https://example.org/guide#S-resource"\n')
    main(["fix", str(d)])
    assert "g.1 | https://example.org/guide#S-resource | cards 1" in (d / "Overview.md").read_text()


def test_read_one_part(tmp_path, capsys):
    d = topic(tmp_path)
    assert main(["sources", str(d), "--read", "tour.2"]) == 0
    out = capsys.readouterr().out
    assert "2 Classes (pages 11–17)" in out and "--- page 17 ---" in out and "page 18" not in out
    assert main(["sources", str(d), "--read", "nope"]) == 1


def test_pdf_page_link_is_a_valid_source(tmp_path):
    from studyloop import lint
    d = topic(tmp_path)
    deck = config.load_deck(d)
    card = {"source": "[[Tour.pdf#page=4]]", "_file": d / "a.yaml"}
    from studyloop import notes as N
    assert lint.vault_flags(card, (), N.card_vault(deck.path)) == []


def lectures(tmp: Path) -> tuple[Path, Path]:
    """A vault with a lecture folder: two slide PDFs without bookmarks, one .pptx with its
    PDF export next to it, one without."""
    v = tmp / "v"
    (v / ".obsidian").mkdir(parents=True)
    att = v / "Studying" / "CS" / "_attachements"
    att.mkdir(parents=True)
    for name, n in (("Lecture 02 - Linear.pdf", 4), ("Lecture 10 - Long.pdf", 30)):
        w = pypdf.PdfWriter()
        for _ in range(n):
            w.add_blank_page(100, 100)
        with open(att / name, "wb") as f:
            w.write(f)
    (att / "Lecture 02 - Linear.pptx").write_bytes(b"")
    (att / "Lecture 11 - Draft.pptx").write_bytes(b"")
    return v, att


def test_topic_from_a_lecture_folder(tmp_path):
    v, att = lectures(tmp_path)
    home = v / "Studying" / "Anki cards"
    assert main(["topic", "CS", "--home", str(home), "--sources", str(att),
                 "--notes", str(v / "Studying" / "CS"), "--builds-on", "python"]) == 0
    d = home / "cs"
    deck = config.load_deck(d)
    assert deck.cfg["prefix"] == "cs" and not deck.cfg.get("repo")      # a topic, not a project
    assert not (d / "profile.md").exists()
    meta = sources.brief(deck)
    assert meta["sources"] == ["Studying/CS/_attachements"]             # vault-relative
    assert meta["notes"] == "Studying/CS" and meta["builds_on"] == ["python"]
    text = (d / "Overview.md").read_text()
    assert "**lecture02**: Lecture 02 - Linear.pdf" in text             # numbered keys
    assert "**lecture10**" in text
    assert "Lecture 02 - Linear.pptx" not in text                       # its PDF export is used
    assert "Lecture 11 - Draft.pptx: slides: export to PDF" in text
    claude = (v / "Studying" / "CLAUDE.md").read_text()
    assert "study-source" in claude and f"CS: `{d}`" in claude
    assert main(["topic", "CS", "--home", str(home)]) == 0              # rerun keeps the deck
    assert (v / "Studying" / "CLAUDE.md").read_text().count("studyloop:topics:begin") == 1
    assert main(["lint", "-q", str(d)]) == 0


def test_slides_without_bookmarks_split_into_page_chunks(tmp_path):
    v, att = lectures(tmp_path)
    home = v / "Studying" / "Anki cards"
    main(["topic", "CS", "--home", str(home), "--sources", str(att), "--no-notes"])
    d = home / "cs"
    cache = json.loads((d / sources.CACHE).read_text())
    cache["Lecture 10 - Long.pdf"]["words"] = [1000] * 30               # 30k words > batch
    (d / sources.CACHE).write_text(json.dumps(cache))
    main(["sources", str(d)])
    text = (d / "Overview.md").read_text()
    assert "| lecture10.p1-8 | ↳ pages 1–8 | 1–8 | 8.0k |" in text      # ≤ 12k tokens each
    assert "| lecture10.p25-30 |" in text
    assert "lecture02.p" not in text                                    # small: one part
    assert sources.brief(config.load_deck(d))["notes"] is False


GUIDE = """\
# <a name="main"></a>Guide

Intro words here.

# <a name="s-resource"></a>R: Resource management

## <a name="ss-raii"></a>R.raii: RAII

### <a name="rr-raii"></a>R.1: Manage resources automatically

```cpp
# not a heading
```

# <a name="s-errors"></a>E: Error handling

### <a name="re-throw"></a>E.2: Throw an exception
"""


def test_markdown_source_by_headings_and_rule_ids(tmp_path, capsys):
    d = topic(tmp_path)
    (tmp_path / "v" / "Books" / "Guide.md").write_text(GUIDE)
    ov = d / "Overview.md"
    ov.write_text(ov.read_text().replace(
        "  - Missing.pdf\n",
        '  - {file: Guide.md, key: cg, also_url: "https://example.org/guide-md"}\n'))
    with open(d / "a.yaml", "a") as f:
        f.write('- type: concept\n  question: q5?\n  answer: "**a.**"\n  source: "Guide R.1"\n'
                '- type: concept\n  question: q6?\n  answer: "**a.**"\n'
                '  source: "https://example.org/guide-md#re-throw"\n')
    main(["fix", str(d)])
    main(["sources", str(d)])
    text = ov.read_text()
    assert "| cg.R | R: Resource management |" in text
    assert "cg.R | R: Resource management | 5–14 |" in text and "| cards 1 |" in text
    assert "| cg.E | E: Error handling | 15–17 |" in text
    assert "not a heading" not in text                                   # fenced code skipped
    capsys.readouterr()
    assert main(["sources", str(d), "--read", "cg.R.raii"]) == 0
    assert "R.1: Manage resources" in capsys.readouterr().out
