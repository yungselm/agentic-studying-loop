"""A dictionary in the language cache: JMdict for Japanese (EDRDG, CC BY-SA 4.0).

`asl lang setup ja` downloads JMdict.gz once and indexes it into dict.sqlite (forms -> entries
with senses in English and the other gloss languages JMdict has, e.g. German)."""
from __future__ import annotations

import gzip
import json
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .levels import cache_dir

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
POS_EN = {"名詞": "noun", "動詞": "verb", "形容詞": "adjective (keiyoushi)", "副詞": "adverb",
          "形状詞": "adjectival nouns", "代名詞": "pronoun", "連体詞": "pre-noun", "接続詞": "conjunction",
          "感動詞": "interjection"}
ISO2 = {"en": "eng", "de": "ger", "fr": "fre", "es": "spa", "ru": "rus", "nl": "dut",
        "hu": "hun", "sv": "swe", "sl": "slv"}


def _db_path(code: str) -> Path:
    return cache_dir(code) / "dict.sqlite"


def setup_dictionary(cfg: dict, force: bool = False) -> None:
    d = cfg.get("dictionary") or {}
    if not d.get("url"):
        return
    db = _db_path(cfg["code"])
    if db.exists() and not force:
        print(f"  dictionary: cached ({db})")
        return
    raw = cache_dir(cfg["code"]) / Path(d["url"]).name
    if not raw.exists() or force:
        req = urllib.request.Request(d["url"], headers={"User-Agent": "agentic-studying-loop"})
        with urllib.request.urlopen(req, timeout=300) as r:
            raw.write_bytes(r.read())
    n = build_index(raw, db)
    print(f"  dictionary: {n} entries → {db}" + (f"  ({d['credit']})" if d.get("credit") else ""))


def build_index(xml_gz: Path, db: Path) -> int:
    tmp = db.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript("create table entry (id integer primary key, data text);"
                      "create table form (form text, entry integer, common integer);")
    n = 0
    with gzip.open(xml_gz) as f:
        for _, el in ET.iterparse(f, events=("end",)):
            if el.tag != "entry":
                continue
            eid = int(el.findtext("ent_seq"))
            kanji = [(k.findtext("keb"), bool(k.findall("ke_pri"))) for k in el.findall("k_ele")]
            kana = [(r.findtext("reb"), bool(r.findall("re_pri"))) for r in el.findall("r_ele")]
            senses, pos, uk = [], [], False
            for s in el.findall("sense"):
                pos = [p.text for p in s.findall("pos")] or pos        # pos carries over
                uk = uk or any("kana alone" in (m.text or "") for m in s.findall("misc"))
                gl: dict[str, list[str]] = {}
                for g in s.findall("gloss"):
                    gl.setdefault(g.get(XML_LANG, "eng"), []).append(g.text or "")
                senses.append({"pos": pos, "gloss": gl})
            data = {"k": [k for k, _ in kanji], "r": [r for r, _ in kana], "s": senses,
                    "common": any(c for _, c in kanji + kana), "uk": uk}
            con.execute("insert into entry values (?, ?)", (eid, json.dumps(data, ensure_ascii=False)))
            con.executemany("insert into form values (?, ?, ?)",
                            [(form, eid, int(c)) for form, c in kanji + kana if form])
            n += 1
            el.clear()
    con.execute("create index form_idx on form(form)")
    con.commit()
    con.close()
    tmp.replace(db)
    return n


class Dictionary:
    def __init__(self, cfg: dict):
        db = _db_path(cfg["code"])
        if not db.exists():
            raise SystemExit(f"Dictionary not downloaded: run `asl lang setup {cfg['code']}`")
        self.con = sqlite3.connect(db)

    def lookup(self, word: str, reading: str = "", pos: str = "") -> list[dict]:
        """Entries with `word` as a written or kana form. Ranked: has `reading`, matches the
        part of speech (`pos`: UniDic pos1, e.g. 副詞 -> adverb), common."""
        rows = self.con.execute(
            "select e.data, max(f.common) from form f join entry e on e.id = f.entry "
            "where f.form = ? group by e.id", (word,)).fetchall()
        out = [dict(json.loads(d), _common=c) for d, c in rows]
        want = POS_EN.get(pos, "")
        def pos_hit(e):
            return bool(want) and any(want in p for sn in e["s"] for p in sn["pos"])
        kana_word = bool(word) and all("\u3040" <= c <= "\u30ff" for c in word)
        out.sort(key=lambda e: (reading not in e["r"] if reading else False, not pos_hit(e),
                                kana_word and not e.get("uk"),       # なん: 何 (kana), not 難
                                not e["_common"]))
        return out

    def readings(self, word: str) -> list[str]:
        return [r for e in self.lookup(word) for r in e["r"]]


def senses_text(entry: dict, langs: list[str], limit: int = 6) -> str:
    """Senses per language (JMdict keeps each language in its own senses):
    `en 1. [verb] to live; to reside` / `de 1. wohnen`."""
    lines = []
    for lg in langs:
        code = ISO2.get(lg, lg)
        senses = [s for s in entry["s"] if s["gloss"].get(code)][:limit]
        for i, s in enumerate(senses, 1):
            pos = s["pos"][0].split(" (")[0] if s["pos"] else ""
            lines.append(f"{lg} {i}. " + (f"[{pos}] " if pos and code == "eng" else "")
                         + "; ".join(s["gloss"][code][:4]))
    return "\n".join(lines)
