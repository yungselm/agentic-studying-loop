"""Engine tests: card loading, ids, GUID stability, lint, build, stats helpers."""
import sqlite3
import textwrap
import zipfile
from pathlib import Path

import pytest

from studyloop.core import cards as C
from studyloop.core import config
from studyloop.core.cards import ids
from studyloop.core.engine import lint
from studyloop.core.engine.build import build

REPO = Path(__file__).resolve().parents[2]


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
    assert "\r\n- id: tsk-009\r\n  std: 1\r\n  type: concept" in raw
    assert "| tsk-009 | draft | concept |" in (deck / "Overview.md").read_text(encoding="utf-8")


# ---- regressions from review ---------------------------------------------------

def _fix(d):
    ids.ids(config.resolve_inputs([str(d)]), fix=True)
    return [c.get("id") for c in C.load_file(d / "a.yaml")]


def _concept(q):
    return f"- type: concept\n  question: {q}\n  answer: |\n    **A.**\n"


def test_fix_legacy_migration_keeps_every_id_and_guid(tmp_path):
    body = "".join(f"# rlk-00{i}\n{_concept(f'Q{i}?')}\n" for i in range(1, 5))
    d = make_deck(tmp_path, body, "deck: K\npack: python\nprefix: rlk\nguid: legacy-kata\n")
    from studyloop.core.engine.build import guid
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
    from studyloop.core.engine.build import text
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


def test_deck_kind_fix_and_lint(tmp_path, capsys):
    yml = "# header comment\ndeck: T  # keep me\npack: python\nprefix: t\n"
    d = make_deck(tmp_path, "- id: t-001\n  type: concept\n  question: Q?\n  answer: '**A.**'\n"
                            "  pack: rust\n", yml)
    assert config.load_deck(d).kind == "topic"
    lint.lint(config.resolve_inputs([str(d)]))
    assert "~ [kind] deck/deck.yaml -> no `kind:`" in capsys.readouterr().out
    ids.ids(config.resolve_inputs([str(d)]), fix=True)
    text = (d / "deck.yaml").read_text(encoding="utf-8")
    assert text == "# header comment\nkind: topic\ndeck: T  # keep me\npack: python\nprefix: t\n"
    assert "kind: topic written" in capsys.readouterr().out

    lint.lint(config.resolve_inputs([str(d)]))       # the card's `pack:` is fine; `kind` is set
    assert "[kind]" not in capsys.readouterr().out
    (d / "a.yaml").write_text("- id: t-001\n  type: concept\n  question: Q?\n  answer: '**A.**'\n"
                              "  lang: rust\n", encoding="utf-8")
    assert lint.lint(config.resolve_inputs([str(d)])) == 1
    assert "! [pack]" in capsys.readouterr().out

    # repo + lang: ambiguous, fix leaves it, lint asks; an unknown kind is an error
    (d / "deck.yaml").write_text("deck: T\nprefix: t\nlang: ja\nrepo: x\n", encoding="utf-8")
    ids.fix_kind(config.load_deck(d))
    assert "kind" not in (d / "deck.yaml").read_text(encoding="utf-8")
    assert lint.kind_flags(config.load_deck(d))[0][0] == "!"
    (d / "deck.yaml").write_text("kind: book\ndeck: T\n", encoding="utf-8")
    assert "unknown `kind: book`" in lint.kind_flags(config.load_deck(d))[0][2]


def test_vault_setting(tmp_path, capsys):
    from studyloop.core.cli import main
    from studyloop.core.config.vault import vault_for
    v = tmp_path / "Notes"
    home = v / "Anki cards"
    deck = home / "d"
    deck.mkdir(parents=True)
    assert vault_for(deck) is None                    # no setting, no .obsidian: no vault
    (v / ".obsidian").mkdir()
    assert vault_for(deck) == v                       # card homes from before the setting

    main(["init-home", str(home), "--no-vault"])
    assert "vault: \"none\"" in (home / "studyloop.yaml").read_text(encoding="utf-8")
    assert vault_for(deck) is None                    # `none` wins over .obsidian

    elsewhere = tmp_path / "Elsewhere"
    elsewhere.mkdir()
    main(["init-home", str(home), "--vault", str(elsewhere)])
    text = (home / "studyloop.yaml").read_text(encoding="utf-8")
    assert text.count("\nvault:") == 1 and "# vault: .." not in text   # replaced the placeholder
    assert vault_for(deck) == elsewhere.resolve()
    main(["init-home", str(home), "--vault", str(v)])
    assert 'vault: ".."' in (home / "studyloop.yaml").read_text(encoding="utf-8")   # relative
    assert vault_for(deck) == v.resolve()


def test_registry_modules_and_plain_decks(tmp_path, capsys):
    from studyloop.core import registry as R
    reg = R.registry()
    assert list(reg.modules)[0] == "core"
    assert set(reg.modules) >= {"core", "analysis", "language", "notes", "projects", "sources"}
    assert set(reg.deck_kinds) == {"plain", "language", "project", "topic"}
    assert set(reg.card_types) == {"code", "concept", "timeline", "cloze", "sentence", "grammar"}
    assert reg.missing(R.Module("x", lambda r: None, needs=("no_such_module_xyz",))) == ["no_such_module_xyz"]

    def twice(r):
        r.add_card_type(reg.card_types["cloze"])
    with pytest.raises(SystemExit, match="two modules register the card type `cloze`"):
        R.load([R.Module("core", lambda r: None), R.Module("a", twice), R.Module("b", twice)])

    d = make_deck(tmp_path, "- id: t-001\n  type: concept\n  question: Q?\n  answer: '**A.**'\n",
                  "kind: plain\ndeck: T\nprefix: t\n")
    assert lint.lint(config.resolve_inputs([str(d)])) == 0
    assert build(config.resolve_inputs([str(d)]), tmp_path / "x.apkg") == 0
