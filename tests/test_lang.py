"""Language topics: apkg import (legacy + zstd media), speaker split, seeding, levels, i+1 planner."""
import io
import zipfile
from collections import Counter
from pathlib import Path

import genanki
import pytest

from studyloop.lang import apkg as A
from studyloop.lang import levels as LV
from studyloop.lang.lines import import_apkg, read_lines, split_speakers, write_lines
from studyloop.lang.plan import Analysed, _mark_names, make_plan
from studyloop.lang.tokens import Token
from studyloop.lang.vocab import glossed_words

LABELS = "（[^）]*）"


def test_split_speakers():
    assert split_speakers("（A）こんばんは （B）どうも", LABELS) == [("A", "こんばんは"), ("B", "どうも")]
    assert split_speakers("台本は一切ございません （C）はい", LABELS) == [("", "台本は一切ございません"), ("C", "はい")]
    assert split_speakers("（笑い）（D）そうだね", LABELS) == [("D", "そうだね")]   # sound effect: dropped
    assert split_speakers("（YOU(ユウ)）テラスハウスは", LABELS) == [("YOU(ユウ)", "テラスハウスは")]


def test_glossed_words():
    assert glossed_words("最高(さいこう)=Das Beste, のんびりする＝entspannen") == ["最高", "のんびりする"]
    assert glossed_words("邪魔(じゃま)=Störung, どく=auf die Seite gehen") == ["邪魔", "どく"]
    assert glossed_words("") == []


def test_skeleton_matches_okurigana_variants():
    assert LV._skeleton("付き合う") == LV._skeleton("付合う") == "付合"
    assert LV._skeleton("めっちゃ") == ""


def _subs2srs_apkg(tmp: Path) -> Path:
    model = genanki.Model(1352568357693, "subs2srs", fields=[
        {"name": n} for n in ("SequenceMarker", "Audio", "Snapshot", "Expression", "Meaning")],
        templates=[{"name": "Card 1", "qfmt": "{{Audio}}{{Snapshot}}", "afmt": "{{Expression}}"}])
    deck = genanki.Deck(2059400110, "TH")
    rows = [
        ("1_002", "TH_0.00.14.264-0.00.16.808", "（YOU(ユウ)）テラスハウスは"),
        ("1_001", "TH_0.00.12.011-0.00.14.139", "（ﾄﾘﾝﾄﾞﾙ）こんばんは （一同）こんばんは"),
        ("1_001", "TH_0.00.12.011-0.00.14.139", "duplicate clip"),
    ]
    files = []
    for seq, clip, text in rows:
        for ext, data in (("mp3", b"ID3"), ("jpg", b"\xff\xd8\xff")):
            p = tmp / f"{clip}.{ext}"
            p.write_bytes(data)
            files.append(str(p))
        deck.add_note(genanki.Note(model, [seq, f"[sound:{clip}.mp3]", f'<img src="{clip}.jpg">', text, ""]))
    deck.add_note(genanki.Note(model, ["SequenceMarker placeholder", "Audio placeholder", "x",
                                       "Expression placeholder", ""]))
    out = tmp / "th.apkg"
    genanki.Package(deck, media_files=sorted(set(files))).write_to_file(out)
    return out


def test_import_apkg_sorts_dedupes_and_splits(tmp_path):
    lines, media, stats, ex = import_apkg(_subs2srs_apkg(tmp_path), "th1", LABELS)
    assert stats == {"notes": 4, "lines": 2, "split": 1}
    assert [(ln.id, ln.text, ln.speaker) for ln in lines] == [
        ("th1-0001a", "こんばんは", "ﾄﾘﾝﾄﾞﾙ"), ("th1-0001b", "こんばんは", "一同"),
        ("th1-0002", "テラスハウスは", "YOU(ユウ)")]
    assert lines[0].start == "00:00:12.011" and lines[0].end == "00:00:14.139"
    assert lines[0].status == "split:audio-pending"
    assert len(media) == 4 and ex.read_media("TH_0.00.12.011-0.00.14.139.mp3") == b"ID3"
    p = tmp_path / "lines" / "th1.tsv"
    write_lines(p, lines)
    assert read_lines(p) == lines


def test_zstd_export_media_map(tmp_path):
    import zstandard
    z = zstandard.ZstdCompressor()
    name = b"clip.mp3"
    entry = b"\x0a" + bytes([len(name)]) + name + b"\x10\x03"          # name, size
    entries = b"\x0a" + bytes([len(entry)]) + entry
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("media", z.compress(entries))
        zf.writestr("0", z.compress(b"ID3"))
    p = tmp_path / "x.apkg"
    p.write_bytes(buf.getvalue())
    with zipfile.ZipFile(p) as zf:
        assert A._media_map(zf) == {"clip.mp3": "0"}
    ex = A.Export(p, media={"clip.mp3": "0"})
    assert ex.read_media("clip.mp3") == b"ID3"


class _Prio:
    cap = 30

    def __init__(self, order):
        self.order = order

    def __call__(self, k):
        return (self.order.index(k), k)


def _item(i, words, chars=10):
    from studyloop.lang.lines import Line
    return Analysed(Line(f"s-{i:04d}", "", "", "x" * chars), "s", words, Counter(), chars)


def test_plan_chains_unlocks_and_priority():
    items = [                            # 'k' is known; every line has 2+ words
        _item(0, ["z", "k"]),            # low priority, available at once
        _item(1, ["a", "k"]),
        _item(2, ["a", "b"]),            # b (top priority) unlocks once a is planned
        _item(3, ["b", "c", "d"]),       # still 2 unknown after b: parked
        _item(4, ["k", "k2"]),           # all known
        _item(5, ["a", "k"], chars=20),  # a is planned on the shorter line 1: covered
    ]
    plan = make_plan(items, known=lambda k: k in ("k", "k2"), priority=_Prio(["b", "a", "z", "c", "d"]))
    assert [k for k, _ in plan.order] == ["a", "b", "z"]   # b jumps ahead of z once unlocked
    assert plan.first_round == 2
    assert plan.status == {0: "ready:3", 1: "ready:1", 2: "ready:2", 3: "parked:2 words",
                           4: "known", 5: "covered"}


def test_plan_prefers_lines_within_cap_and_unsplit():
    items = [_item(0, ["a", "k"], chars=40), _item(1, ["a", "k"], chars=12), _item(2, ["a", "k"], chars=5)]
    items[2].line.id += "b"              # a split line: only if nothing else
    plan = make_plan(items, known=lambda k: k == "k", priority=_Prio(["a"]))
    assert plan.order == [("a", 1)]


def test_mark_names_from_speaker_labels():
    toks = [Token("小室", "小室|", "小室", "", "name"), Token("安", "安|やす", "安", "やす", "word"),
            Token("未", "未|ひつじ", "未", "ひつじ", "word"), Token("です", "です|です", "です", "です", "function")]
    out = _mark_names(toks, "小室安未です", ["安未"])
    assert [t.kind for t in out] == ["name", "name", "name", "function"]


def test_unidic_kinds():
    pytest.importorskip("fugashi")
    from studyloop.lang.tokens import tokenizer
    tok = tokenizer("unidic")
    kinds = {t.surface: t.kind for t in tok("いやいや 困るよ。")}
    assert kinds["困る"] == "word" and kinds["よ"] == "function" and kinds["いやいや"] == "filler"
    assert tok.key_for("付き合う") == next(t.key for t in tok("付き合ってる") if t.kind == "word")


def test_single_word_line_only_when_no_longer_line_exists():
    items = [
        _item(0, ["a"], chars=3),        # single word; a longer line (2) has 'a': skipped
        _item(1, ["b"], chars=3),        # single word; no longer line has 'b': kept
        _item(2, ["a", "c"], chars=12),  # 'a' waits until 'c' is planned
        _item(3, ["c", "k"], chars=10),
    ]
    plan = make_plan(items, known=lambda k: k == "k", priority=_Prio(["a", "b", "c", "k"]))
    assert [k for k, _ in plan.order] == ["b", "c", "a"]
    assert plan.order[2] == ("a", 2)
    assert plan.status[0] == "covered" and plan.status[1].startswith("ready")


def test_single_word_line_skipped_while_its_word_waits():
    items = [_item(0, ["a"], chars=3), _item(1, ["a", "x", "y"], chars=12)]
    plan = make_plan(items, known=lambda k: False, priority=_Prio(["a", "x", "y"]))
    assert plan.order == []
    assert plan.status == {0: "skipped:single word", 1: "parked:3 words"}
