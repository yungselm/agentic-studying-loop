"""Engine tests: card loading, ids, GUID stability, lint, build, stats helpers."""
import sqlite3
import textwrap
import zipfile
from pathlib import Path

import pytest

from studyloop import cards as C
from studyloop import config, ids, lint, stats
from studyloop.build import build

REPO = Path(__file__).resolve().parent.parent


def make_deck(tmp: Path, cards_yaml: str, deck_yaml: str = "deck: T\npack: python\nprefix: t\n"):
    d = tmp / "deck"
    d.mkdir()
    (d / "deck.yaml").write_text(deck_yaml, encoding="utf-8")
    (d / "a.yaml").write_text(textwrap.dedent(cards_yaml), encoding="utf-8")
    return d


CODE = """\
# t-001
- instruction: |
    Return the double of `x`.
  starter: |
    def double(x: int) -> int:

  solution: |
    def double(x: int) -> int:
        return 2 * x
  tests: |
    assert double(2) == 4

- type: concept
  question: Why?
  answer: |
    **Because.** Detail.
"""


def guids(apkg: Path) -> dict[str, str]:
    with zipfile.ZipFile(apkg) as z:
        tmp = apkg.parent / "x.anki2"
        tmp.write_bytes(z.read("collection.anki2"))
    con = sqlite3.connect(tmp)
    return {flds.split("\x1f")[0]: guid for guid, flds in con.execute("select guid, flds from notes")}


def test_comment_id_and_measures(tmp_path):
    d = make_deck(tmp_path, CODE)
    cs = C.load_file(d / "a.yaml")
    assert cs[0]["id"] == "t-001" and "id" not in cs[1]
    assert C.measures(cs[0]) == {"typed_chars": len("return 2 * x"), "typed_lines": 1}
    assert C.measures(cs[1])["bold_chars"] == len("Because.")


def test_ids_fix_assigns_and_keeps(tmp_path):
    d = make_deck(tmp_path, CODE)
    groups = config.resolve_inputs([str(d)])
    ids.ids(groups, fix=True)
    cs = C.load_file(d / "a.yaml")
    assert [c["id"] for c in cs] == ["t-001", "t-002"]
    assert "# t-001" not in (d / "a.yaml").read_text()


def test_guid_survives_front_edit(tmp_path):
    d = make_deck(tmp_path, CODE.replace("# t-001\n- instruction", "- id: t-001\n  instruction"))
    out = tmp_path / "a.apkg"
    build(config.resolve_inputs([str(d)]), out)
    before = guids(out)
    f = d / "a.yaml"
    f.write_text(f.read_text().replace("Return the double", "Return twice"), encoding="utf-8")
    build(config.resolve_inputs([str(d)]), out)
    after = guids(out)
    assert set(before.values()) == set(after.values())


def test_timeline_is_stable_and_shuffled():
    card = {"id": "x-1", "type": "timeline", "question": "Order:", "steps": ["a", "b", "c", "d"]}
    one, two = C.expand_timeline(dict(card)), C.expand_timeline(dict(card))
    assert one["question"] == two["question"]
    assert one["answer"].startswith("**") and "A → B → C → D" not in one["answer"]


def test_lint_flags_oversized_and_literal(tmp_path, capsys):
    big = "x = " + "1 + " * 40 + "1"
    yaml_text = f"""\
    - id: t-001
      instruction: |
        Return a greeting.
      starter: |
        def f() -> str:

      solution: |
        def f() -> str:
            {big}
            return "hello world"
    """
    d = make_deck(tmp_path, yaml_text)
    assert lint.lint(config.resolve_inputs([str(d)])) == 1
    out = capsys.readouterr().out
    assert "[size]" in out and "[literal]" in out


def test_suggest_and_spearman():
    assert stats.spearman(list(range(20)), list(range(20))) == pytest.approx(1.0)
    bins = [(0, 40, 0.10, 500, 0), (40, 80, 0.12, 500, 0), (80, 120, 0.20, 500, 0.1),
            (120, 10**9, 0.40, 500, 0.7)]
    s = stats.suggest(bins, 80, 120, "typed chars")
    assert "target ≈ 80, max ≈ 80" in s or "target ≈ 80, max ≈ 120" in s


@pytest.mark.parametrize("deck", ["examples/python-core", "example-vault/Studying/Anki cards/tasklog"])
def test_examples_lint_clean(deck):
    assert lint.lint(config.resolve_inputs([str(REPO / deck)])) == 0
