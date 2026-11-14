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
    assert {k: stats[k] for k in ("notes", "lines", "split")} == {"notes": 4, "lines": 2, "split": 1}
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


# ---- milestone 2: furigana, card types, lint, build, rejection --------------------------

def test_ruby_and_plain_text():
    from studyloop.lang.tokens import plain_text, ruby
    assert ruby("住んで", "すんで") == " 住[す]んで"
    assert ruby("お願い", "おねがい") == "お 願[ねが]い"
    assert ruby("軽井沢", "かるいざわ") == " 軽井沢[かるいざわ]"
    assert ruby("めっちゃ", "めっちゃ") == "めっちゃ"
    assert plain_text("ずっと 軽井沢[かるいざわ]に ** 住[す]ん**でます") == "ずっと軽井沢に 住んでます"   # the space before kanji only marks the base


def test_furigana_marks_target_tokens():
    from studyloop.lang.tokens import furigana
    toks = [Token("料理", "料理|りょうり", "料理", "りょうり", "word", "りょうり"),
            Token("の", "の|の", "の", "の", "function", "の"),
            Token("専門", "専門|せんもん", "専門", "せんもん", "word", "せんもん"),
            Token("辞め", "止める|やめる", "辞める", "やめる", "word", "やめ", " ")]
    assert furigana(toks, "専門|せんもん") == " 料理[りょうり]の** 専門[せんもん]**  辞[や]め".strip()


def test_plan_excludes_rejected_lines():
    items = [_item(0, ["a", "k"], chars=5), _item(1, ["a", "k"], chars=12)]
    plan = make_plan(items, known=lambda k: k == "k", priority=_Prio(["a"]), excluded=frozenset({0}))
    assert plan.order == [("a", 1)] and plan.status[0] == "rejected"


def _lang_deck(tmp: Path, cards_yaml: str) -> Path:
    media = tmp / "media" / "th1"
    media.mkdir(parents=True)
    (media / "c1.mp3").write_bytes(b"ID3")
    (media / "c1.jpg").write_bytes(b"\xff\xd8\xff")
    d = tmp / "japanese"
    d.mkdir()
    (d / "deck.yaml").write_text(
        f'deck: "日本語"\nlang: ja\nprefix: ja\nmedia_dir: "{tmp / "media"}"\n'
        "presets:\n  default: {new_per_day: 20, order: sequential, gather: position}\n"
        "files:\n  grammar.yaml: {prefix: jag, cards: [listen]}\n", encoding="utf-8")
    (d / "vocabulary__th.yaml").write_text(cards_yaml, encoding="utf-8")
    (d / "grammar.yaml").write_text(
        '- id: jag-001\n  type: grammar\n  text: "こんなところで ** 死[し]んじゃダメ**なんです"\n'
        '  grammar: じゃだめ\n  meaning: must not do\n  translation: "You **must not** die here."\n'
        '  audio: c1.mp3\n  image: c1.jpg\n', encoding="utf-8")
    return d


SENTENCE = '''\
- id: ja-002
  type: sentence
  text: "ずっと こっちの 軽井沢[かるいざわ]に ** 住[す]ん**でます"
  word: "住む"
  reading: "すむ"
  gloss: "wohnen"
  audio: "c1.mp3"
  image: "c1.jpg"
  line: th1-0249
- id: ja-001
  type: sentence
  text: "**めっちゃ** 気[き]になる"
  word: "めっちゃ"
  gloss: ""
  audio: "missing.mp3"
  image: "c1.jpg"
'''


def test_lang_lint(tmp_path, capsys):
    from studyloop import config, lint
    d = _lang_deck(tmp_path, SENTENCE)
    assert lint.lint(config.resolve_inputs([str(d)])) == 1
    out = capsys.readouterr().out
    assert "ja-001" in out and "no `gloss:`" in out and "missing.mp3 not found" in out
    assert "no `reading:`" in out and "[index]" not in out
    assert "ja-002" not in out and "jag-001" not in out


def test_lang_build(tmp_path):
    import json
    import sqlite3

    from studyloop import config
    from studyloop.build import build
    d = _lang_deck(tmp_path, SENTENCE.split("- id: ja-001")[0])
    out = tmp_path / "ja.apkg"
    assert build(config.resolve_inputs([str(d)]), out) == 0
    with zipfile.ZipFile(out) as z:
        z.extract("collection.anki2", tmp_path)
        media = set(json.loads(z.read("media")).values())
    assert {"c1.mp3", "c1.jpg"} <= media
    con = sqlite3.connect(tmp_path / "collection.anki2")
    models = json.loads(con.execute("select models from col").fetchone()[0])
    by_type = {models[str(mid)]["name"]: flds.split("\x1f")
               for mid, flds in con.execute("select mid, flds from notes")}
    assert by_type["Sentence Card"][0].endswith("<strong> 住[す]ん</strong>でます")
    assert by_type["Sentence Card"][4] == "[sound:c1.mp3]"
    assert by_type["Grammar Card"][8] == ""                  # cards: [listen] -> no Reading card
    assert con.execute("select count(*) from cards").fetchone()[0] == 2
    decks = json.loads(con.execute("select decks from col").fetchone()[0])
    dconf = json.loads(con.execute("select dconf from col").fetchone()[0])
    conf_of = {v["name"]: v["conf"] for v in decks.values()}
    assert dconf[str(conf_of["日本語::Vocabulary"])]["newGatherPriority"] == 1   # parent deck too


# ---- paths, audio split, re-import ----------------------------------------------------------

def test_native_path_windows_and_wsl():
    import os

    from studyloop.config import native_path
    if os.name == "nt":
        assert str(native_path("/mnt/c/x/y")) == "C:\\x\\y"
    elif Path("/mnt/c").is_dir():
        assert native_path(r"C:\WorkingData\AnkiMedia") == Path("/mnt/c/WorkingData/AnkiMedia")
    assert native_path("/tmp/x") == Path("/tmp/x")


def test_cut_points_finds_the_quiet_stretch():
    from studyloop.lang.audio import WIN, cut_points
    levels = [10.0] * 40 + [1.0] * 5 + [10.0] * 55          # a pause at windows 40-44
    ((end_a, start_b),) = cut_points(levels, [0.5])
    assert (start_b, end_a) == (40 * WIN, 45 * WIN)           # both parts keep the whole pause
    assert cut_points([10.0] * 100, [0.5]) is None           # no clear pause: keep whole
    late = [10.0] * 92 + [1.0] * 3 + [10.0] * 5               # quiet only near the end
    assert cut_points(late, [0.6]) is None                    # 2nd part too short for its text


def test_readd_keeps_card_and_rejected_statuses(tmp_path):
    from studyloop.lang.lines import add_source
    apkg = _subs2srs_apkg(tmp_path)
    deck = tmp_path / "deck"
    add_source(deck, tmp_path / "media", apkg, "th1", "TH", LABELS)
    tsv = deck / "lines" / "th1.tsv"
    lines = read_lines(tsv)
    lines[2].status, lines[0].status = "card:ja-001", "rejected:ja-002"
    write_lines(tsv, lines)
    add_source(deck, tmp_path / "media", apkg, "th1", "TH", LABELS)
    st = {ln.id: ln.status for ln in read_lines(tsv)}
    assert st["th1-0002"] == "card:ja-001" and st["th1-0001a"] == "rejected:ja-002"
    assert st["th1-0001b"].startswith("split:")          # fake clips: no split, kept whole


def test_cut_from_video(tmp_path):
    import subprocess

    from studyloop.lang.audio import ffmpeg_exe
    from studyloop.lang.lines import cut_from_video
    exe = ffmpeg_exe()
    if not exe:
        pytest.skip("no ffmpeg")
    video = tmp_path / "ep1.mp4"
    subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=4:size=1280x720:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-shortest", str(video)], check=True)
    rows = [(("00:00:00.500", "00:00:01.500"), "a", "ep1_a.mp3", "ep1_a.jpg"),
            (("00:00:01.500", "00:00:03.000"), "b", "ep1_b.mp3", "ep1_b.jpg")]
    na, ni = cut_from_video(video, rows, tmp_path / "out", (0.25, 0.4), 960)
    assert (na, ni) == (2, 2)
    assert all((tmp_path / "out" / n).stat().st_size > 0 for n in ("ep1_a.mp3", "ep1_b.jpg"))
    probe = subprocess.run([exe, "-hide_banner", "-i", str(tmp_path / "out" / "ep1_b.jpg")],
                           capture_output=True, text=True).stderr
    assert "960x540" in probe                                   # scaled to the width cap


def test_plan_prefers_the_better_source():
    items = [_item(0, ["a", "k"], chars=8), _item(1, ["a", "k"], chars=20)]
    items[1].quality = 2                      # cut from video: wins over the shorter line
    plan = make_plan(items, known=lambda k: k == "k", priority=_Prio(["a"]))
    assert plan.order == [("a", 1)]


def test_vocabulary_reads_old_and_new_columns(tmp_path):
    from studyloop.lang.vocab import Vocabulary

    class Tok:
        def key_for(self, w):
            return f"{w}|"
    old = tmp_path / "Vocabulary.md"
    old.write_text("| word | reading | level | status | card | source |\n|---|---|---|---|---|---|\n"
                   "| 住む | すむ | N5 | planned | ja-003 | seed |\n", encoding="utf-8")
    v = Vocabulary(old, "ja", Tok())
    e = v.entries["住む|"]
    assert (e.status, e.card, e.meaning) == ("planned", "ja-003", "")
    e.meaning = "to live"
    v.write(["N5"])
    text = old.read_text(encoding="utf-8")
    assert "| word | reading | level | meaning | status | card | source |" in text
    assert Vocabulary(old, "ja", Tok()).entries["住む|"].meaning == "to live"
