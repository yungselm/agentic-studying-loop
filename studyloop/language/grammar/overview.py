# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""The grammar overview: the language's official lists (`Language.grammar_lists`; JLPT for
Japanese) as a checklist against the vault's grammar notes."""
from __future__ import annotations

import re
from pathlib import Path

from studyloop.core.config.vault import split_frontmatter
from studyloop.language.grammar.notes import update_note

IMAGES = "_attachements"          # next to the notes, as for other topics' PDFs


def write_overview(d) -> Path:
    """`Overview - <Language> Grammar.md`: the notes per level, and the official lists as a
    checklist (ticked = a grammar note covers it)."""
    notes = []
    for p in sorted((d.notes_dir / "Grammar").glob("*.md")):
        meta, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        if meta.get("type") == "grammar":
            notes.append((p.stem, meta))
    lists = d.language.grammar_lists()
    gl = d.cfg.get("grammar_lists") or {}
    list_name, list_source = gl.get("name") or "listed", gl.get("source") or "the official lists"
    by_link = {str(m.get("link") or "").lower(): t for t, m in notes if m.get("link")}
    by_form = {}
    for t, m in notes:
        for f in _norm_forms(str(m.get("grammar") or t)):
            by_form.setdefault(f, t)
    # notes without a link (Game Gengo N4) match a listed point by form; the lists are the ground
    # truth, so the note takes its link and level
    for lvl, items in lists.items():
        for it in items:
            if it["link"] in by_link:
                continue
            t = next((by_form[f] for f in _norm_forms(it["grammar"]) if f in by_form), None)
            m = dict(notes).get(t)
            if t and not m.get("link"):
                m["link"], m["level"] = it["link"], lvl
                by_link[it["link"]] = t
                update_note(d.notes_dir / "Grammar" / f"{t}.md", link=it["link"], level=lvl)
    order = list(lists) or sorted({str(m.get("level") or "") for _, m in notes})
    name = d.cfg.get("name", d.lang)
    lines = ["---", "type: overview", f"language: {d.lang}", "---", f"# {name} grammar", "",
             f"Ground truth: {list_source}. A note per grammar point in [[Grammar]]; "
             "`status` drives the grammar gate, `pattern`/`token` find it in a line. "
             "Rewritten by `asl lang grammar`.", "",
             f"| level | notes | known | learning | {list_name} points covered |", "|---|---|---|---|---|"]
    for lvl in order:
        ns = [m for _, m in notes if m.get("level") == lvl]
        covered = sum(1 for it in lists.get(lvl, []) if it["link"] in by_link)
        lines.append(f"| {lvl} | {len(ns)} | {sum(m.get('status') == 'known' for m in ns)} | "
                     f"{sum(m.get('status') == 'learning' for m in ns)} | "
                     f"{covered} / {len(lists.get(lvl, [])) or '?'} |")
    for lvl in order:
        lines += ["", f"## {lvl}", ""]
        for it in lists.get(lvl, []):
            t = by_link.get(it["link"])
            if t:
                st = dict(notes)[t].get("status", "unknown")
                lines.append(f"- [x] [[{t}]] — {it['meaning']} · {st}")
            else:
                lines.append(f"- [ ] [{it['grammar']}]({it['link']}) — {it['meaning']}")
        listed = {it["link"] for it in lists.get(lvl, [])}
        extra = [(t, m) for t, m in notes if m.get("level") == lvl
                 and str(m.get("link") or "").lower() not in listed]
        if extra:
            lines += ["", f"Notes not on the {lvl} list:" if lists else "Notes:", ""]
            lines += [f"- [[{t}]] — {m.get('meaning', '')} · {m.get('status', 'unknown')}" for t, m in extra]
    out = d.notes_dir / f"Overview - {name} Grammar.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  overview: {out}")
    return out


def _norm_forms(g: str) -> list[str]:
    """Comparable forms: '間（あいだ）' -> ['間'], 'ちゃいけない・じゃいけない' -> both, no spaces."""
    g = re.sub(r"（[^）]*）|\([^)]*\)|\s", "", g)
    return [x for x in re.split(r"[・/／,、]", g) if x]


def save_image(data: bytes, out: Path, width: int = 600) -> None:
    """An image into the vault, at most `width` px wide (JLPT Sensei's are 600x338 cards)."""
    import subprocess
    import tempfile

    from studyloop.language.media.audio import ffmpeg_exe
    exe = ffmpeg_exe()
    if not exe:
        out.write_bytes(data)
        return
    with tempfile.NamedTemporaryFile(suffix=out.suffix, delete=False) as tmp:
        tmp.write(data)
    try:
        subprocess.run([exe, "-y", "-loglevel", "error", "-i", tmp.name, "-vf",
                        f"scale='min({width},iw)':-2", "-q:v", "4", str(out)], check=True)
    except subprocess.CalledProcessError:
        out.write_bytes(data)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


