"""Cloze cards: gap parsing, lint, build (math, links, images), stats measures."""
import json
import sqlite3
import textwrap
import zipfile
from pathlib import Path

from studyloop import cards as C
from studyloop import config, lint, stats
from studyloop.build import build

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")


def vault(tmp: Path, cards_yaml: str) -> Path:
    """tmp/v: an Obsidian vault with one note, one image and a deck folder."""
    v = tmp / "v"
    (v / ".obsidian").mkdir(parents=True)
    (v / "Notes").mkdir()
    (v / "Notes" / "Softmax.md").write_text("---\naliases: [softmax loss]\n---\n# Softmax\n")
    (v / "Notes" / "scene.png").write_bytes(PNG)
    d = v / "cards"
    d.mkdir()
    (d / "deck.yaml").write_text("deck: T\nprefix: t\n")
    (d / "a.yaml").write_text(textwrap.dedent(cards_yaml), encoding="utf-8")
    return d


GOOD = """\
- id: t-001
  type: cloze
  text: |
    A fresh {{softmax}} classifier starts at loss {{$\\log C$}}, because each class gets {{1/C}}.
  extra: "So 2.3 for 10 classes."
  hook: "![[scene.png]] the dice room"
  source: "[[Softmax#Sanity check]]"
"""


def test_gaps_parse_nested_hints_and_code():
    g = C.gaps(r"{{\frac{1}{C}}} and {{c3::x::hint}} and {{`std::vec`}} and {{y}}")
    assert [(n, a, h) for n, a, h, *_ in g] == [
        (4, r"\frac{1}{C}", ""), (3, "x", "hint"), (5, "`std::vec`", ""), (6, "y", "")]
    # Anki ends a gap at the first `}}`: the build spaces nested braces out
    assert C.cloze_text(r"{{\frac{1}{C}}}") == r"{{c1::\frac{1}{C} }}"
    assert C.gap_answers("{{c1::ab}} {{c1::cd}} {{**efg**}}") == {1: 4, 2: 3}
    # length as rendered: a TeX command is one symbol, layout is free; "$5 and $10" is no math
    assert [C.shown_len(s) for s in (r"$v \leftarrow \rho v$", r"$\log C$", "$5 and $10")] == [4, 4, 10]


def _lint(d, capsys):
    rc = lint.lint(config.resolve_inputs([str(d)]))
    return rc, capsys.readouterr().out


def test_good_cloze_card_lints_clean(tmp_path, capsys):
    rc, out = _lint(vault(tmp_path, GOOD), capsys)
    assert rc == 0 and "OK" in out, out


def test_cloze_lint_flags(tmp_path, capsys):
    rc, out = _lint(vault(tmp_path, """\
        - id: t-001
          type: cloze
          text: "Only {{one gap}} here."
          source: "[[No such note]]"
        - id: t-002
          type: cloze
          text: "No gap at all."
        - id: t-003
          type: cloze
          text: "{{%s}} and {{b}}"
          hook: "![[missing.png]]"
          source: "[[softmax loss]]"
        """ % ("x" * 90)), capsys)
    assert rc == 1
    assert "[gaps] a.yaml: t-001" in out and "[[No such note]] not found" in out
    assert "! [size] a.yaml: t-002" in out
    assert "a gap asks 90 chars > max 80" in out and "image missing.png not found" in out
    assert "softmax loss" not in out          # an alias resolves


def test_build_cloze_note(tmp_path):
    d = vault(tmp_path, GOOD)
    out = tmp_path / "x.apkg"
    assert build(config.resolve_inputs([str(d)]), out) == 0
    with zipfile.ZipFile(out) as z:
        (tmp_path / "c.db").write_bytes(z.read("collection.anki2"))
        media = json.loads(z.read("media"))
    assert "scene.png" in media.values()
    con = sqlite3.connect(tmp_path / "c.db")
    flds, tags = con.execute("select flds, tags from notes").fetchone()
    text, extra, hook, source = flds.split("\x1f")
    assert text.startswith("A fresh {{c1::softmax}}") and r"{{c2::\(\log C\)}}" in text
    assert hook.startswith('<img src="scene.png">') and source == "Softmax › Sanity check"
    assert "asl::type::cloze" in tags and "asl::hook" in tags
    assert con.execute("select count(*) from cards").fetchone()[0] == 3   # one card per gap
    models = json.loads(con.execute("select models from col").fetchone()[0])
    assert any(m["name"] == "Cloze Card" and m["type"] == 1 for m in models.values())

    # stats reads the measures back per card (its own gap)
    scon, tmp = stats.open_collection(out)
    got = sorted((c.measures["gap_chars"], c.measures["gaps"], c.measures["hook"])
                 for c in stats.load_cards(scon, None))
    assert got == [(3, 3, 1), (4, 3, 1), (7, 3, 1)], got   # $\\log C$ shows 4 chars


def test_concept_card_takes_math_and_images(tmp_path, capsys):
    d = vault(tmp_path, """\
        - id: t-001
          type: concept
          question: "Why does a fresh classifier start at $\\\\log C$?"
          answer: "**Uniform scores**: each class gets $1/C$. ![[scene.png]]"
          source: "[[Softmax]]"
        - id: t-002
          type: concept
          question: "Q?"
          answer: "**A** ![[gone.png]]"
        """)
    rc, out = _lint(d, capsys)
    assert rc == 1 and "answer: image gone.png not found" in out and "t-001" not in out, out
    (d / "a.yaml").write_text("\n".join((d / "a.yaml").read_text().splitlines()[:5]) + "\n")
    out_pkg = tmp_path / "x.apkg"
    assert build(config.resolve_inputs([str(d)]), out_pkg) == 0
    with zipfile.ZipFile(out_pkg) as z:
        (tmp_path / "c.db").write_bytes(z.read("collection.anki2"))
        assert "scene.png" in json.loads(z.read("media")).values()
    q, a, *_ = sqlite3.connect(tmp_path / "c.db").execute("select flds from notes").fetchone()[0].split("\x1f")
    assert r"\(\log C\)" in q and '<img src="scene.png">' in a and r"\(1/C\)" in a
    assert C.measures({"type": "concept", "answer": "**A** ![[x.png]]"})["answer_chars"] == 1
