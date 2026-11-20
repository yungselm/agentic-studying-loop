# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Seed the grammar ground truth from a Game Gengo deck: one note per grammar point (grouped by
its JLPT Sensei link, status from the deck's reviews), the JLPT Sensei image, a detection rule
derived from the lesson's forms and highlighted span; with `--cards` the lessons as `grammar`
cards (the author keeps Game Gengo's own deck, so off by default)."""
from __future__ import annotations

import html
import re
from pathlib import Path

from studyloop.core.anki.reviews import read_export
from studyloop.language.cards.io import card_item
from studyloop.language.grammar.notes import embed_image, read_note, write_note
from studyloop.language.grammar.overview import IMAGES, save_image, write_overview
from studyloop.language.grammar.points import check_points
from studyloop.language.vocabulary.tokens import plain_text
from studyloop.language_ja.rules import _forms, derive_rule


def _clean(s: str, mark: bool = True) -> str:
    """GG field -> card text: <font color>…</font> (the grammar) -> **…**, <br>/&nbsp; -> space."""
    s = re.sub(r"<br\s*/?>|&nbsp;|​", " ", s or "")
    if mark:
        s = re.sub(r"<font[^>]*>(.*?)</font>", r"**\1**", s, flags=re.S)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"\*\*\s*\*\*", "", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def _media(field_: str, rx: str) -> str:
    m = re.search(rx, field_ or "")
    return m.group(1) if m else ""


def _safe(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "", title).strip() or "grammar"


def import_game_gengo(d, apkg: Path, statuses: str = "reviews", key: str = "gg",
                      cards: bool = False) -> int:
    from studyloop.core.config import native_path
    tok = d.language.tokenizer()
    ex = read_export(native_path(apkg))
    gg = sorted((n for n in ex.notes if n.model.startswith("GameGengoGrammar")
                 and not str(n.fields.get("Card Order", "")).endswith("_000")),
                key=lambda n: (("N4" in n.fields["Card Order"]), n.fields["Card Order"]))
    if not gg:
        raise SystemExit(f"{apkg}: no GameGengoGrammar notes")
    groups: dict[str, list] = {}
    for n in gg:
        link = _media(n.fields.get("GrammarLink", ""), r'href="([^"]+)"')
        groups.setdefault(link or _clean(n.fields["Grammar"], False), []).append(n)

    gdir = d.notes_dir / "Grammar"
    (gdir / IMAGES).mkdir(parents=True, exist_ok=True)
    titles, written, kept = {}, 0, 0
    for link, ns in groups.items():
        f0 = ns[0].fields
        grammar = _clean(f0["Grammar"], False)
        meaning = _clean(f0["Grammar Meaning"], False)
        title = _safe(grammar)
        if title in titles.values():                       # と (and) vs と (whenever)
            title = _safe(f"{grammar} ({meaning.split(';')[0][:30]})")
        for n in ns:
            titles[id(n)] = title
        level = "N5" if any("N5" in t for n in ns for t in n.tags) else "N4"
        status = "unknown"
        if statuses == "reviews":
            status = ("known" if any(n.mature for n in ns) else
                      "learning" if any(n.reviewed for n in ns) else "unknown")
        examples = [plain_text(_clean(n.fields["Sentence Field Furigana"])) for n in ns]
        forms = []
        for n in ns:
            forms += [f for f in _forms(_clean(n.fields["Grammar"], False)) if f not in forms]
        marked = [re.sub(r" ?([^ \[\]>*]+?)\[[^\]]*\]", r"\1", _clean(n.fields["Sentence Field Furigana"]))
                  for n in ns]
        pattern, token = derive_rule(forms, examples, tok, marked)
        image = next((m for n in ns if (m := _media(n.fields.get("GrammarImage", ""), r'src="([^"]+)"'))
                      and m in ex.media), "")
        if image and not (gdir / IMAGES / image).exists():
            save_image(ex.read_media(image), gdir / IMAGES / image)     # the JLPT Sensei card
        p = gdir / f"{title}.md"
        if p.exists():
            kept += 1
            _update_note(p, pattern, token, "unknown" if statuses == "unknown" else None, image)
            continue
        meta = {"type": "grammar", "language": d.lang, "grammar": grammar, "level": level,
                "meaning": meaning, "status": status, "rule": "auto", "pattern": pattern,
                "token": token,
                "link": link if link.startswith("http") else "", "image": image,
                "source": "Game Gengo", "examples": examples}
        body = (f"# {grammar}\n\n{meaning}\n\n" + (f"![[{image}]]\n\n" if image else "")
                + "## Examples (Game Gengo)\n\n"
                + "\n".join(f"- {_clean(n.fields['Sentence Field'])}  \n  "
                            f"{_clean(n.fields['Sentence Translation'])} ({_clean(n.fields['Video Game'], False)})"
                            for n in ns) + "\n")
        write_note(p, meta, body)
        written += 1

    if not cards:
        print(f"Game Gengo: {len(gg)} lessons → {len(groups)} grammar points ({written} notes "
              f"written, {kept} existing: `rule: auto` re-derived, others kept) in {gdir}")
        write_overview(d)
        return check_points(d, tok)
    # the lessons as grammar cards (`--cards`; generated: re-running rewrites the file)
    cards, media = [], []
    for i, n in enumerate(gg, 1):
        f = n.fields
        audio = _media(f["Audio Field"], r"\[sound:([^\]]+)\]")
        image = _media(f["Image Field"], r'src="([^"]+)"')
        media += [m for m in (audio, image) if m in ex.media]
        card = {"id": f"jag-{i:03d}", "type": "grammar",
                "text": _clean(f["Sentence Field Furigana"]), "grammar": _clean(f["Grammar"], False),
                "meaning": _clean(f["Grammar Meaning"], False),
                "translation": _clean(f["Sentence Translation"]), "note": f"[[{titles[id(n)]}]]",
                "link": _media(f.get("GrammarLink", ""), r'href="([^"]+)"'),
                "audio": audio, "image": image,
                "source": f"{_clean(f['Video Game'], False)} · Game Gengo {f['Card Order'].split('Grammar_')[-1]}"}
        cards.append(card)
    out = d.path / "grammar.yaml"
    out.write_text("# Grammar cards ported from Game Gengo (`asl lang grammar`); re-running rewrites this file.\n"
                   + "".join(card_item(c) for c in cards), encoding="utf-8")
    n_media = ex.extract_media(media, d.media_dir / key)
    write_overview(d)
    print(f"Game Gengo: {len(gg)} lessons → {len(groups)} grammar points "
          f"({written} notes written, {kept} existing: `rule: auto` re-derived, others kept) in {gdir}")
    print(f"  {len(cards)} grammar cards → {out}; media: {n_media} new files in {d.media_dir / key}")
    return check_points(d, tok)


def _update_note(p: Path, pattern: str, token: str, status: str | None, image: str = "") -> None:
    """An existing note: re-derive its rule only if it is still `rule: auto` (the agent's rules,
    `rule: agent`, and hand edits stay); `--fresh` resets the status."""
    meta, body = read_note(p)
    if not meta:
        return
    before = dict(meta)
    if meta.get("rule", "auto") == "auto" and meta.get("detect") is not False:
        meta.update(rule="auto", pattern=pattern, token=token)
    if status:
        meta["status"] = status
    if image and not meta.get("image"):
        meta["image"] = image
        body = embed_image(body, image)
    if meta != before:
        write_note(p, meta, body)


