"""C++ pack: cards compile in their own namespaces, failures name the card."""
import shutil
import textwrap

import pytest

from studyloop.cli import main

pytestmark = pytest.mark.skipif(not (shutil.which("g++") or shutil.which("clang++")),
                                reason="no C++ compiler")


def deck(tmp, cards):
    (tmp / "deck.yaml").write_text("deck: C\npack: cpp\nprefix: c\n")
    (tmp / "a.yaml").write_text(textwrap.dedent(cards))
    return tmp


TWO = """\
- id: c-001
  instruction: Double it.
  starter: "int twice(int x) { }"
  solution: |
    int twice(int x) { return x * 2; }
  tests: |
    assert(twice(2) == 4);
- id: c-002
  instruction: Same name in another card.
  starter: "x"
  solution: |
    #include <vector>
    int twice(const std::vector<int>& v) { return static_cast<int>(v.size()) * 2; }
  tests: |
    assert(twice({1, 2}) == 4);
"""


def test_cards_are_isolated_and_pass(tmp_path, capsys):
    assert main(["check", "--fast", str(deck(tmp_path, TWO))]) == 0
    src = capsys.readouterr().out
    assert "All checks passed" in src


def test_failures_name_the_card(tmp_path, capsys):
    bad = TWO.replace("x * 2", "x * 3") + """\
- id: c-003
  instruction: Dangling.
  starter: "x"
  solution: |
    #include <vector>
    int first_after_push() {
        std::vector<int> v{1};
        int& r = v[0];
        for (int i = 0; i < 100; ++i) v.push_back(i);
        return r;
    }
  tests: |
    assert(first_after_push() == 1);
"""
    assert main(["check", "--fast", str(deck(tmp_path, bad))]) == 1
    out = capsys.readouterr().out
    assert "[!] c-001" in out and "[!] c-003" in out and "[!] c-002" not in out
    assert "use-after-free" in out


def test_compile_error_names_the_card(tmp_path, capsys):
    deck(tmp_path, TWO.replace("return x * 2;", "return x * 2"))
    assert main(["check", "--fast", str(tmp_path)]) != 0
