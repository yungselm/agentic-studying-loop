"""Sphinx config for the docs site (Read the Docs). Build: `sphinx-build -W docs docs/_build`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

project = "agentic-studying-loop"
author = "yungselm"
extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx.ext.viewcode"]
source_suffix = {".md": "markdown"}
html_theme = "furo"
html_title = project
default_role = "literal"            # `x` in docstrings is code, as on GitHub
myst_heading_anchors = 3
html_extra_path = ["_redirects"]             # old URLs (api/core.html -> api/map/core.html)

# Development notes stay in the repo, not on the site; the site is install + reference.
exclude_patterns = ["_build", "_redirects", "architecture.md", "evidence-*.md", "language-cards.md",
                    "migrating-from-rust-lang-kata.md", "roadmap.md", "writing-a-pack.md"]

# Optional installs: the API pages document their modules without installing them.
autodoc_mock_imports = ["pandas", "matplotlib", "fugashi", "unidic_lite", "wordfreq",
                        "imageio_ffmpeg", "edge_tts"]
autodoc_member_order = "bysource"
autodoc_typehints = "description"           # types next to the parameters, not in the signature
napoleon_google_docstring = False           # NumPy style only
napoleon_use_rtype = False


def _literal_maps(app, what, name, obj, options, lines):
    """Module docstrings are plain text: every indented block (the `asl x -> file.py` maps)
    becomes a literal block, so its lines stay lines and `*`, `->` are shown as written."""
    if what != "module" or not obj.__doc__:
        return
    out, prev = [], ""
    for line in obj.__doc__.splitlines():               # raw: autodoc's dedent eats the maps
        starts_block = line.startswith("    ") and not prev.startswith(" ")
        if starts_block and prev.strip():
            out += ["", "::", ""]                       # block glued to its paragraph
        elif starts_block and not (out and out[-2:-1] and out[-2].rstrip().endswith("::")):
            out += ["::", ""]                           # block after a blank line
        if line.strip() and not line.startswith(" ") and out and out[-1].startswith("    "):
            out.append("")                              # text glued to the block's end
        out.append(line)
        if line.strip():
            prev = line
    lines[:] = out + [""]


def _write_cli(app):
    """api/cli.md from the real parser (docs/_cli.py)."""
    from _cli import write
    write(Path(app.srcdir) / "api" / "cli.md", autodoc_mock_imports)


def setup(app):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    app.connect("builder-inited", _write_cli)
    app.connect("autodoc-process-docstring", _literal_maps)
