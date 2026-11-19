"""Sources map: PDF bookmarks -> parts, split by batch size, status from cards and notes."""
import json
import re
import textwrap
from pathlib import Path

import pypdf
import pytest

from studyloop.core import config
from studyloop.core.cli import main
from studyloop.sources import sourcemap as sources


def book(path: Path) -> None:
    """20 blank pages; bookmarks: Cover, 1 Basics (2 sections), 2 Classes, Index."""
    w = pypdf.PdfWriter()
    for _ in range(20):
        w.add_blank_page(100, 100)
    w.add_outline_item(title="Cover", page_number=0)
    ch1 = w.add_outline_item(title="1 The Basics", page_number=2)
    w.add_outline_item(title="1.1 Programs", page_number=2, parent=ch1)
    w.add_outline_item(title="1.2 Functions", page_number=6, parent=ch1)
    w.add_outline_item(title="2 Classes", page_number=10)
    w.add_outline_item(title="Index", page_number=17)
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
    from studyloop.core.cards.types import vault_flags
    from studyloop.core.config.vault import vault_for
    d = topic(tmp_path)
    deck = config.load_deck(d)
    card = {"source": "[[Tour.pdf#page=4]]", "_file": d / "a.yaml"}
    assert vault_flags(card, (), vault_for(deck.path)) == []


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
    assert "study-source" in claude and "- CS (topic: study-source" in claude and f"`{d}`" in claude
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


def test_markdown_source_by_heading_link(tmp_path):
    """A plain Markdown book (headings, no anchors): `[[Book#Heading]]` counts for its part."""
    d = topic(tmp_path)
    (tmp_path / "v" / "Books" / "Rust.md").write_text(
        "# Ownership\n\nwords\n\n## What Is Ownership?\n\n### The `String` Type\n\ntext\n\n"
        "## Slices\n\nmore\n")
    ov = d / "Overview.md"
    ov.write_text(ov.read_text().replace("  - Missing.pdf\n", "  - Rust.md\n"))
    with open(d / "a.yaml", "a") as f:
        f.write('- type: concept\n  question: q7?\n  answer: "**a.**"\n'
                '  source: "[[Rust.md#The `String` Type]]"\n'
                '- type: concept\n  question: q8?\n  answer: "**a.**"\n'
                '  source: "[[Rust#slices]]"\n')
    main(["fix", str(d)])
    main(["sources", str(d)])
    text = ov.read_text()
    row = next(ln for ln in text.splitlines() if "| Ownership |" in ln)
    assert row.endswith("| cards 2 |"), row


def test_read_several_parts_in_one_call(tmp_path, capsys):
    d = topic(tmp_path)
    assert main(["sources", str(d), "--read", "tour.1,tour.2"]) == 0
    out = capsys.readouterr().out
    assert "1 The Basics (pages 3–10)" in out and "2 Classes (pages 11–17)" in out


def scanned_topic(tmp: Path) -> Path:
    """A topic whose one source is a scanned page: a single photo, no text, no bookmarks."""
    import random

    from PIL import Image
    v = tmp / "v"
    (v / ".obsidian").mkdir(parents=True)
    (v / "Books").mkdir()
    rng = random.Random(0)
    img = Image.new("RGB", (400, 300))
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256))
                 for _ in range(400 * 300)])          # noise: a JPEG well over the icon size
    img.save(v / "Books" / "Scan.pdf")
    home = v / "Anki cards"
    assert main(["topic", "Scan", "--home", str(home), "--sources", str(v / "Books" / "Scan.pdf"),
                 "--no-notes"]) == 0
    return home / "scan"


def test_read_saves_the_parts_figures(tmp_path, capsys):
    d = scanned_topic(tmp_path)
    capsys.readouterr()
    part = re.search(r"^\| (\S+) \| \(no bookmarks", (d / "Overview.md").read_text(), re.M)[1]
    assert main(["sources", str(d), "--read", part]) == 0
    out = capsys.readouterr().out
    name = re.search(r"!\[\[figures/(\S+)\]\] 400×300", out)[1]
    assert (d / "figures" / name).stat().st_size > 4000
    assert main(["sources", str(d), "--read", part]) == 0             # second read: same file
    assert sorted(p.name for p in (d / "figures").iterdir()) == [name]


def test_finish_builds_only_a_clean_deck(tmp_path, capsys):
    d = scanned_topic(tmp_path)
    part = re.search(r"^\| (\S+) \| \(no bookmarks", (d / "Overview.md").read_text(), re.M)[1]
    main(["sources", str(d), "--read", part])
    fig = next((d / "figures").iterdir()).name
    apkg = d.parent / "scan.apkg"
    good = textwrap.dedent(f"""\
        - type: concept
          question: |
            What does this scan show?
            ![[figures/{fig}]]
          answer: "**Noise.**"
          source: "[[Scan.pdf#page=1]]"
        """)
    too_long = f'- type: concept\n  question: q?\n  answer: "**{"x" * 400}**"\n'
    (d / "a.yaml").write_text(good + too_long)
    assert main(["finish", str(d)]) == 1 and not apkg.exists()           # answer over the max
    (d / "a.yaml").write_text(good)
    assert main(["finish", str(d)]) == 0
    import zipfile
    media = json.loads(zipfile.ZipFile(apkg).read("media"))
    assert fig in media.values()                                        # the figure is packed


def test_prompt_is_self_contained(tmp_path, capsys):
    d = scanned_topic(tmp_path)
    prefs = d.parent / "standards" / "preferences.md"
    prefs.write_text(prefs.read_text() + "- 2026-11-18: Never card a dose (`sca-001`).\n")
    capsys.readouterr()
    assert main(["prompt", str(d)]) == 0
    out = capsys.readouterr().out
    assert "## Brief" in out and "About 5 cards" in out                # floor for a tiny part
    assert "### Cloze cards" in out and "### Hard or never-used topics" in out
    assert "### Code cards" not in out                                  # brief: no code cards
    assert "*(lint" not in out and "§" not in out                       # standards-only pointers cut
    assert "Never card a dose" in out                                   # the user's own rules
    assert "![[figures/" in out and "[[Scan.pdf#page=N]]" in out
    assert f'asl finish "{d}"' in out
    with pytest.raises(SystemExit):
        main(["prompt", str(d), "--part", "nope"])


def test_prompt_finds_rules_by_title_not_number(tmp_path, capsys):
    """A card home's own core.md, numbered differently and without cloze rules."""
    d = scanned_topic(tmp_path)
    (d.parent / "standards" / "core.md").write_text(
        "# Mine\n\n## 1. Data\n\nxdatax\n\n## 3. Concept cards\n\n- My concept rule.\n\n"
        "## 4. Hard topics\n\n- My hard rule.\n\n## 5. Project cards\n\n- Repo only.\n")
    capsys.readouterr()
    assert main(["prompt", str(d)]) == 0
    out = capsys.readouterr().out
    rules = out.split("## Rules")[1].split("## Format")[0]
    assert "### Concept cards\n- My concept rule." in rules
    assert "### Hard topics\n- My hard rule." in rules
    assert "### Cloze cards" in rules and "2–5 gaps" in rules           # asl's own cloze rules
    assert "Repo only" not in rules and "xdatax" not in rules


# ---- German sources ---------------------------------------------------------------------------

def _text_page(lines: list[str]):
    """A PDF page with real text (Helvetica, WinAnsi: umlauts as in German books)."""
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    w = pypdf.PdfWriter()
    page = w.add_blank_page(612, 792)
    n = NameObject
    font = DictionaryObject({n("/Type"): n("/Font"), n("/Subtype"): n("/Type1"),
                             n("/BaseFont"): n("/Helvetica"), n("/Encoding"): n("/WinAnsiEncoding")})
    page[n("/Resources")] = DictionaryObject(
        {n("/Font"): DictionaryObject({n("/F1"): w._add_object(font)})})

    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = "BT /F1 11 Tf 72 740 Td 14 TL " + " ".join(f"({esc(ln)}) '" for ln in lines) + " ET"
    stream = DecodedStreamObject()
    stream.set_data(ops.encode("cp1252"))
    page[n("/Contents")] = w._add_object(stream)
    return page


def _german_book(path: Path) -> None:
    """Inhaltsverzeichnis, Vorwort, a chapter with umlauts, a figure with an `Abb.` caption, Register."""
    import io
    import random

    from PIL import Image
    rng = random.Random(0)
    img = Image.new("RGB", (400, 300))
    img.putdata([tuple(rng.randrange(256) for _ in range(3)) for _ in range(400 * 300)])
    buf = io.BytesIO()
    img.save(buf, "PDF")
    w = pypdf.PdfWriter()
    w.add_page(_text_page(["Inhaltsverzeichnis", "1 Grundlagen . . . 3"]))
    w.add_page(_text_page(["Vorwort", "Dieses Buch richtet sich an Ärztinnen und Ärzte."]))
    w.add_page(_text_page(["1 Grundlagen der Koronarphysiologie",
                           "Der koronare Blutfluss hängt vom Druckgradienten ab.",
                           "Größere Stenosen führen zu höheren Druckverlusten."]))
    fig = w.add_page(pypdf.PdfReader(buf).pages[0])
    fig.merge_page(_text_page(["Abb. 1.1 Übersicht über die Druckmessung mit dem Führungsdraht",
                               "in der Koronararterie"]))
    w.add_page(_text_page(["Register", "FFR 3"]))
    for title, page in (("Inhaltsverzeichnis", 0), ("Vorwort", 1),
                        ("1 Grundlagen der Koronarphysiologie", 2), ("Register", 4)):
        w.add_outline_item(title, page)
    with open(path, "wb") as f:
        w.write(f)


def test_german_book(tmp_path, capsys):
    """German front matter is skipped, umlauts survive, `Abb.` captions are found; cards are in
    English unless the brief's `language:` says otherwise."""
    v = tmp_path / "v"
    (v / ".obsidian").mkdir(parents=True)
    (v / "Bücher").mkdir()
    _german_book(v / "Bücher" / "Koronar.pdf")
    home = v / "Anki-Karten"
    assert main(["topic", "Koronar", "--home", str(home), "--sources", str(v / "Bücher" / "Koronar.pdf"),
                 "--no-notes"]) == 0
    d = home / "koronar"
    text = (d / "Overview.md").read_text()
    assert "1 Grundlagen der Koronarphysiologie" in text
    for skipped in ("Inhaltsverzeichnis", "Vorwort", "Register"):
        assert f"| {skipped} |" not in text
    part = re.search(r"^\| (\S+) \| 1 Grundlagen", text, re.M)[1]
    capsys.readouterr()
    assert main(["sources", str(d), "--read", part]) == 0
    out = capsys.readouterr().out
    assert "Größere Stenosen" in out
    assert "Abb. 1.1 Übersicht über die Druckmessung" in out and "![[figures/" in out
    assert main(["prompt", str(d)]) == 0
    assert "Write the cards in English." in capsys.readouterr().out
    ov = d / "Overview.md"
    ov.write_text(ov.read_text().replace("---\n", "---\nlanguage: German\n", 1))
    assert main(["prompt", str(d)]) == 0
    assert "Write the cards in German." in capsys.readouterr().out
