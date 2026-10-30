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


def _project_copy(tmp_path):
    import shutil
    src = REPO / "example-vault/Studying/Anki cards"
    home = tmp_path / "home"
    shutil.copytree(src, home)
    deck = home / "tasklog"
    cfg = (deck / "deck.yaml").read_text(encoding="utf-8")
    cfg = cfg.replace('repo: "../../../../examples/tasklog"',
                      f'repo: "{(REPO / "examples/tasklog").as_posix()}"')
    (deck / "deck.yaml").write_text(cfg, encoding="utf-8")
    return deck


def _lint_out(deck, capsys):
    rc = lint.lint(config.resolve_inputs([str(deck)]))
    return rc, capsys.readouterr().out


def test_project_deck_clean(tmp_path, capsys):
    rc, out = _lint_out(_project_copy(tmp_path), capsys)
    assert rc == 0, out


def test_excerpt_drift_is_caught(tmp_path, capsys):
    deck = _project_copy(tmp_path)
    ext = deck / "tasklog_ext.yaml"
    ext.write_text(ext.read_text(encoding="utf-8").replace(
        "app = typer.Typer()", "app = typer.Typer(help='x')"), encoding="utf-8")
    rc, out = _lint_out(deck, capsys)
    assert rc == 1 and "[excerpt]" in out and "typer.Typer(help" in out


def test_header_role_and_index(tmp_path, capsys):
    deck = _project_copy(tmp_path)
    f = deck / "tasklog.yaml"
    f.write_text(f.read_text(encoding="utf-8").replace(
        "(persistence: load/save the task list as JSON)", "(storage)", 2), encoding="utf-8")
    ov = deck / "Overview.md"
    ov.write_text(ov.read_text(encoding="utf-8").replace("| tsk-003 |", "| tsk-099 |"),
                  encoding="utf-8")
    rc, out = _lint_out(deck, capsys)
    assert "[header]" in out and "role for src/tasklog/store.py" in out
    assert "tsk-003 has no row" in out and "tsk-099 has no card" in out


def test_fix_adds_id_std_index_and_keeps_crlf(tmp_path):
    deck = _project_copy(tmp_path)
    f = deck / "tasklog.yaml"
    text = f.read_text(encoding="utf-8") + (
        "\n- type: concept\n  question: Q?\n  answer: |\n    **A.**\n  source: \"x → y\"\n")
    f.write_bytes(text.replace("\n", "\r\n").encode())
    ids.ids(config.resolve_inputs([str(deck)]), fix=True)
    raw = f.read_bytes().decode()
    assert "\r\n- id: tsk-006\r\n  std: 1\r\n  type: concept" in raw
    assert "| tsk-006 | draft | concept |" in (deck / "Overview.md").read_text(encoding="utf-8")


# ---- regressions from review ---------------------------------------------------

def _fix(d):
    ids.ids(config.resolve_inputs([str(d)]), fix=True)
    return [c.get("id") for c in C.load_file(d / "a.yaml")]


def _concept(q):
    return f"- type: concept\n  question: {q}\n  answer: |\n    **A.**\n"


def test_fix_legacy_migration_keeps_every_id_and_guid(tmp_path):
    body = "".join(f"# rlk-00{i}\n{_concept(f'Q{i}?')}\n" for i in range(1, 5))
    d = make_deck(tmp_path, body, "deck: K\npack: python\nprefix: rlk\nguid: legacy-kata\n")
    from studyloop.build import guid
    deck = config.load_deck(d)
    before = [guid(deck, d / "a.yaml", c) for c in C.load_file(d / "a.yaml")]
    assert _fix(d) == ["rlk-001", "rlk-002", "rlk-003", "rlk-004"]
    cards = C.load_file(d / "a.yaml")
    assert [c["guid"] for c in cards] == before
    assert "# rlk" not in (d / "a.yaml").read_text()


def test_fix_new_card_above_comment_id(tmp_path):
    d = make_deck(tmp_path, _concept("New?") + "\n# t-005\n" + _concept("Old?"))
    assert _fix(d) == ["t-006", "t-005"]


def test_fix_refuses_flow_style_and_keeps_file(tmp_path):
    body = '- {type: concept, question: "Q?", answer: "**A.**"}\n'
    d = make_deck(tmp_path, body)
    _fix(d)
    assert (d / "a.yaml").read_text() == body


def test_fix_four_space_items_and_empty_id(tmp_path):
    body = ("-   type: concept\n    question: Q1?\n    answer: '**A.**'\n"
            "- id:\n  type: concept\n  question: Q2?\n  answer: '**B.**'\n")
    d = make_deck(tmp_path, body)
    assert _fix(d) == ["t-001", "t-002"]


def test_fix_bom_file(tmp_path):
    d = make_deck(tmp_path, "")
    (d / "a.yaml").write_bytes(b"\xef\xbb\xbf" + _concept("Q?").encode())
    assert _fix(d) == ["t-001"]
    assert (d / "a.yaml").read_bytes().startswith(b"\xef\xbb\xbf- id: t-001")


def test_retired_card_comment_is_not_inherited(tmp_path):
    body = "# t-002\n# - question: old, retired card\n\n" + _concept("Brand new?")
    d = make_deck(tmp_path, body)
    assert C.load_file(d / "a.yaml")[0].get("id") is None


def test_text_bold_never_inside_code():
    from studyloop.build import text
    assert text("`x ** 2` and `-(x ** 2)`") == "<code>x ** 2</code> and <code>-(x ** 2)</code>"
    assert text("**`**kwargs` is a dict.**") == "<strong><code>**kwargs</code> is a dict.</strong>"


def test_two_projects_get_separate_presets(tmp_path):
    a = make_deck(tmp_path, _concept("A?").replace("- type", "- id: t-001\n  type"),
                  "deck: Study Loop::A\npack: python\nprefix: t\npresets:\n  default: {new_per_day: 3}\n")
    b = tmp_path / "b"
    b.mkdir()
    (b / "deck.yaml").write_text("deck: Study Loop::B\nprefix: u\npresets:\n  default: {new_per_day: 30}\n")
    (b / "b.yaml").write_text(_concept("B?").replace("- type", "- id: u-001\n  type"))
    out = tmp_path / "x.apkg"
    build(config.resolve_inputs([str(a), str(b)]), out)
    import json
    with zipfile.ZipFile(out) as z:
        (tmp_path / "c.db").write_bytes(z.read("collection.anki2"))
    con = sqlite3.connect(tmp_path / "c.db")
    decks = json.loads(con.execute("select decks from col").fetchone()[0])
    dconf = json.loads(con.execute("select dconf from col").fetchone()[0])
    per = {d["name"]: dconf[str(d["conf"])]["new"]["perDay"] for d in decks.values()
           if d["name"] != "Default"}
    assert per["Study Loop::A::A"] == 3 and per["Study Loop::B::B"] == 30
