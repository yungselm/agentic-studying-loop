"""The card home: a folder (in your vault, if you keep one) with studyloop.yaml (limits,
refresh settings, standards version, the vault), your standards and the evidence from your
reviews. `Home`/`find_home` read it; `init_home` sets one up; `install_skills` copies skills.

    asl init-home <card home> [--pack rust --pack python] [--vault <folder> | --no-vault]
    asl install-skills [<.claude/skills folder>]

init-home copies the defaults there; from then on they evolve with your own review data."""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from studyloop.core.config.packs import find_pack
from studyloop.core.config.paths import PKG, _read_yaml, read_keep, write_keep

DEFAULT_REFRESH = {"mature_share": 0.5, "step_share": 0.25, "min_review_answers": 1000,
                   "min_card_age_days": 30, "mature_ivl_days": 21}


@dataclass
class Home:
    """The card home: a folder (usually in the vault) with studyloop.yaml and the decks.

    Get it with `find_home`; ``asl init-home`` makes one.

    Attributes
    ----------
    path : Path or None
        None when no card home was found (defaults apply).
    cfg : dict
        studyloop.yaml as read.

    Examples
    --------
    >>> h = find_home(Path("example-vault/Studying/Anki cards/tasklog"))
    >>> h.path.name, h.standards_version
    ('Anki cards', 1)
    >>> h.limits["concept"]
    {'answer_chars_target': 250, 'answer_chars_max': 300, 'bold_chars_target': 120, 'bold_chars_max': 150}
    """
    path: Path | None
    cfg: dict = field(default_factory=dict)

    @property
    def limits(self) -> dict:
        """Per card type: studyloop.yaml `limits:` over the card types' defaults."""
        from studyloop.core.registry import registry
        lim = {t.name: dict(t.default_limits) for t in registry().card_types.values()
               if t.default_limits}
        for kind, vals in (self.cfg.get("limits") or {}).items():
            lim.setdefault(kind, {}).update(vals or {})
        return lim

    @property
    def refresh(self) -> dict:
        """When ``asl stats`` may propose new limits: ``refresh:`` over `DEFAULT_REFRESH`."""
        return {**DEFAULT_REFRESH, **(self.cfg.get("refresh") or {})}

    @property
    def standards_version(self) -> int:
        """The ``std:`` new cards are written under."""
        return int(self.cfg.get("standards_version", 1))


def find_home(start: Path) -> Home:
    """The card home containing ``start``: the nearest folder upwards with studyloop.yaml.

    Examples
    --------
    >>> find_home(Path("example-vault/Studying/Anki cards/tasklog")).path.name
    'Anki cards'
    >>> find_home(Path("/tmp"))
    Home(path=None, cfg={})
    """
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / "studyloop.yaml").is_file():
            return Home(d, _read_yaml(d / "studyloop.yaml"))
    return Home(None, {})


TEMPLATES = PKG / "templates"


def _copy_new(src: Path, dst: Path) -> bool:
    if dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def init_home(home: Path, packs: list[str], vault: Path | str | None = None) -> None:
    """`vault`: the notes folder cards link into, `"none"` for cards only, None: leave as is."""
    home = home.expanduser().resolve()
    made = []
    if _copy_new(TEMPLATES / "card-home" / "studyloop.yaml", home / "studyloop.yaml"):
        made.append("studyloop.yaml")
    if vault is not None:
        made.append(f"vault: {set_vault(home, vault)}")
    for name in ("core.md",):
        if _copy_new(PKG / "standards" / name, home / "standards" / name):
            made.append(f"standards/{name}")
    if _copy_new(TEMPLATES / "card-home" / "preferences.md", home / "standards" / "preferences.md"):
        made.append("standards/preferences.md")
    for p in packs:
        if _copy_new(find_pack(p) / "standards.md", home / "standards" / f"{p}.md"):
            made.append(f"standards/{p}.md")
    (home / "evidence").mkdir(parents=True, exist_ok=True)
    print(f"Card home {home}: " + (", ".join(made) if made else "already set up, nothing changed."))


def set_vault(home: Path, vault: Path | str) -> str:
    """Write `vault:` into the card home's studyloop.yaml (relative when the vault holds the
    home, so the vault can move or sync between Windows and WSL). Returns the value written."""
    if str(vault) == "none":
        value = "none"
    else:
        v = Path(vault).expanduser().resolve()
        if not v.is_dir():
            raise SystemExit(f"Vault folder not found: {v}")
        value = Path(os.path.relpath(v, home)).as_posix() if home.is_relative_to(v) else str(v)
    p = home / "studyloop.yaml"
    text, fmt = read_keep(p)
    line = f"vault: {_yaml_str(value)}"
    if re.search(r"^vault:.*$", text, re.M):
        text = re.sub(r"^vault:.*$", lambda _m: line, text, count=1, flags=re.M)
    elif re.search(r"^# vault:.*$", text, re.M):          # the template's placeholder
        text = re.sub(r"^# vault:.*$", lambda _m: line, text, count=1, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n\n{line}\n"
    write_keep(p, text, fmt)
    return value


def _yaml_str(s: str | None) -> str:
    return '""' if s is None else '"' + str(s).replace("\\", "/").replace('"', "'") + '"'


def skills_dir() -> Path:
    """skills/ sits at the repo root (where the Claude Code plugin expects it) and
    is installed alongside the package as `studyloop_skills`."""
    import studyloop_skills
    return Path(studyloop_skills.__path__[0])


def install_skills(target: Path) -> None:
    """Copy the skills of the installed modules into a .claude/skills folder (for use without
    the plugin). A module without its optional install keeps its skills out: an agent never
    loads a skill it cannot follow, and every installed skill costs context in each session."""
    from studyloop.core.registry import registry
    reg = registry()
    owner = {s: m for m in reg.modules.values() for s in m.skills}
    target = target.expanduser().resolve()
    skipped = []
    for skill in sorted(skills_dir().iterdir()):
        if not (skill / "SKILL.md").is_file():
            continue
        m = owner.get(skill.name)
        if m is None or reg.missing(m):
            skipped.append(f"{skill.name}" + (f" ([{m.extra}])" if m and m.extra else ""))
            continue
        dst = target / skill.name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(skill, dst)
        print(f"  {dst}")
    if skipped:
        print(f"  not installed (their module's install is missing): {', '.join(skipped)}")


def render(tpl: str, **kw) -> str:
    """A template with `{{key}}` placeholders (deck.yaml, Overview.md of new decks)."""
    for k, v in kw.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    return tpl
