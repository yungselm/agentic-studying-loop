"""`asl notes`: the study-note style checks."""
import textwrap
from pathlib import Path

from studyloop import notes as N

REPO = Path(__file__).resolve().parent.parent

GOOD = """\
---
type: concept
aliases: [alias of a]
---
# A

> [!tldr]
> The idea.

```mermaid
flowchart LR
    X --> Y
```

## How it works
1. One step.

> [!question]- Test yourself
> Answer.

## Connections
- builds on: [[B]]: reason
- see also: [[C]]: reason
"""

OVERVIEW = """\
---
type: overview
---
# Overview

```mermaid
flowchart LR
    A --> B
```

1. [[A]]
2. [[B]]
"""


def vault(tmp: Path, files: dict[str, str]) -> Path:
    (tmp / ".obsidian").mkdir()
    for name, text in files.items():
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text), encoding="utf-8")
    return tmp


def kinds(tmp: Path, target: str) -> set[tuple[str, str]]:
    return {(s, k) for s, k, _, _ in N.check_notes([tmp / target], tmp)}


def test_example_vault_passes():
    root = REPO / "example-vault" / "Studying"
    targets = sorted(root.rglob("*.md"))
    found = N.check_notes(targets, root)
    assert found == [], found


def test_good_note_passes(tmp_path):
    v = vault(tmp_path, {"t/A.md": GOOD, "t/B.md": GOOD.replace("# A", "# B").replace("[[B]]", "[[A]]"),
                         "t/C.md": GOOD.replace("# A", "# C"), "t/Overview - T.md": OVERVIEW + "3. [[C]]\n"})
    assert kinds(v, "t/A.md") == set()


def test_bloated_note(tmp_path):
    wall = " ".join(["word"] * 300)
    v = vault(tmp_path, {"A.md": f"---\ntype: concept\n---\n# A\n\nIt's important to note that {wall}\n"})
    k = kinds(v, "A.md")
    assert {("!", "tldr"), ("!", "visual"), ("~", "budget"), ("~", "wall"), ("~", "links"),
            ("~", "recall"), ("~", "filler"), ("~", "orphan"), ("~", "index")} <= k


def test_folded_callouts_and_code_dont_count(tmp_path):
    hidden = "> " + " ".join(["word"] * 400)
    code = "```python\n" + "x = 1\n" * 400 + "```\n"
    v = vault(tmp_path, {"A.md": GOOD + f"\n> [!note]- Details\n{hidden}\n\n{code}"})
    assert ("~", "budget") not in kinds(v, "A.md")


def test_image_embed_counts_as_visual_and_must_exist(tmp_path):
    note = GOOD.replace("```mermaid\nflowchart LR\n    X --> Y\n```", "![[slide.png]]")
    v = vault(tmp_path, {"A.md": note})
    k = kinds(v, "A.md")
    assert ("!", "visual") not in k and ("!", "embed") in k
    (tmp_path / "attachments").mkdir()
    (tmp_path / "attachments" / "slide.png").write_bytes(b"")
    assert ("!", "embed") not in kinds(v, "A.md")


def test_links_resolve_by_alias_and_planned_links_are_quiet(tmp_path):
    v = vault(tmp_path, {"t/A.md": GOOD, "t/B.md": "---\ntype: concept\n---\n[[alias of a]]\n",
                         "t/Overview - T.md": OVERVIEW + "\n## Next\n- [[C]]\n"})
    msgs = [m for _, k, p, m in N.check_notes([v / "t/A.md", v / "t/B.md"], v) if k == "todo"]
    assert msgs == []                     # [[C]] is planned, [[alias of a]] resolves


def test_overview_map_lists_every_note(tmp_path):
    v = vault(tmp_path, {"t/A.md": GOOD, "t/Z.md": GOOD.replace("# A", "# Z"),
                         "t/Overview - T.md": OVERVIEW})
    msgs = [m for _, k, _, m in N.check_notes([v / "t/Overview - T.md"], v) if k == "map"]
    assert msgs == ["[[Z]] isn't on the map"]


def test_card_home_files_are_skipped(tmp_path):
    v = vault(tmp_path, {"Overview.md": "---\ntype: overview\nscope: anki\n---\n[[nothing]]\n"})
    assert kinds(v, "Overview.md") == set()


def test_default_folder_from_claude_md(tmp_path, monkeypatch, capsys):
    vault(tmp_path, {"notes/A.md": GOOD})
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "CLAUDE.md").write_text("- **Study notes for this project:** `../notes`\n", encoding="utf-8")
    monkeypatch.chdir(proj)
    assert N.notes([]) == 0
    assert "A.md" in capsys.readouterr().out


def test_code_inside_a_callout_is_code(tmp_path):
    code = "> [!example] Ex\n> ```python\n" + "> x = 1\n" * 400 + "> ```\n"
    v = vault(tmp_path, {"A.md": GOOD + "\n" + code})
    assert ("~", "budget") not in kinds(v, "A.md")


def test_budget_is_overridable_per_note(tmp_path):
    long = " ".join(["word"] * 40)
    text = GOOD + "\n" + "\n\n".join([long] * 10) + "\n"          # 400 words, no wall
    v = vault(tmp_path, {"A.md": text, "B.md": text.replace("type: concept", "type: concept\nbudget: 600")})
    assert ("~", "budget") in kinds(v, "A.md")
    assert ("~", "budget") not in kinds(v, "B.md")
    assert not [k for _, k, *_ in N.check_notes([v / "A.md"], v, budget=500) if k == "budget"]


def test_lecture_notes_moc_in_parent_lists_and_urls(tmp_path):
    items = "\n".join(f"- item {i} " + " ".join(["w"] * 30) for i in range(5))
    refs = "\n".join(f"- [ref {i}](https://example.com/{'a/' * 30})" for i in range(30))
    lec = GOOD.replace("type: concept", "type: lecture") + "\n" + items + "\n" + refs + "\n"
    v = vault(tmp_path, {"c/l/L1.md": lec, "c/Course MOC.md": "---\ntags: [x/moc]\n---\n[[L1]]\n"})
    k = kinds(v, "c/l/L1.md")
    assert ("~", "wall") not in k                 # list items are separate paragraphs
    assert ("~", "budget") not in k               # URLs don't count; lecture budget 800
    assert ("~", "index") not in k                # the MOC one folder up is the index
