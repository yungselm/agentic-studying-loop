"""Every skill belongs to exactly one module; `asl install-skills` leaves out the skills of
modules whose optional install is missing."""
from pathlib import Path

from studyloop.core import home
from studyloop.core.registry import registry

SKILLS = Path(__file__).resolve().parents[2] / "skills"


def test_every_skill_has_one_module():
    owners: dict[str, list[str]] = {}
    for m in registry().modules.values():
        for s in m.skills:
            owners.setdefault(s, []).append(m.name)
    on_disk = {p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()}
    assert set(owners) == on_disk, (set(owners) ^ on_disk)
    assert all(len(v) == 1 for v in owners.values()), owners


def test_install_skills_skips_modules_without_their_install(tmp_path, monkeypatch, capsys):
    reg = registry()
    monkeypatch.setattr(type(reg), "missing", lambda self, m: ["x"] if m.name == "language" else [])
    home.install_skills(tmp_path)
    got = {p.name for p in tmp_path.iterdir()}
    assert "language-cards" not in got and {"write-cards", "check-cards"} <= got
    assert "language-cards ([lang])" in capsys.readouterr().out
