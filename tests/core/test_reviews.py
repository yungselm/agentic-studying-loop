"""core.reviews: an export's notes with their review state (deferred from the migration's step 1)."""
import sqlite3
import zipfile

import genanki

from studyloop.core.anki.reviews import MATURE_IVL, read_export


def _export(tmp, cards):
    """An .apkg with one note per entry of `cards`: (type, queue, ivl, review eases)."""
    model = genanki.Model(1, "Basic", fields=[{"name": "Front"}],
                          templates=[{"name": "C", "qfmt": "{{Front}}", "afmt": "{{Front}}"}])
    deck = genanki.Deck(2, "D")
    for i in range(len(cards)):
        deck.add_note(genanki.Note(model, [f"q{i}"], guid=f"g{i}"))
    apkg = tmp / "built.apkg"
    genanki.Package(deck).write_to_file(apkg)
    with zipfile.ZipFile(apkg) as z:
        z.extractall(tmp / "x")
    con = sqlite3.connect(tmp / "x" / "collection.anki2")
    rows = con.execute("select c.id, n.guid from cards c join notes n on n.id = c.nid").fetchall()
    for cid, guid in rows:
        ctype, queue, ivl, eases = cards[int(guid[1:])]
        con.execute("update cards set type = ?, queue = ?, ivl = ? where id = ?", (ctype, queue, ivl, cid))
        for k, ease in enumerate(eases):
            con.execute("insert into revlog values (?, ?, -1, ?, 1, 1, 2500, 5000, 1)",
                        (cid * 100 + k, cid, ease))
    con.commit()
    con.close()
    out = tmp / "export.apkg"
    with zipfile.ZipFile(out, "w") as z:
        for p in (tmp / "x").iterdir():
            z.write(p, p.name)
    return out


def test_note_state_from_cards_and_revlog(tmp_path):
    rd = read_export(_export(tmp_path, [
        (0, 0, 0, []),                              # new
        (2, 2, MATURE_IVL - 1, [3, 1, 3]),          # young review card, one fail
        (2, 2, MATURE_IVL, [3, 3]),                 # mature
        (2, -1, 40, [1]),                           # mature but suspended
    ]))
    by_guid = {n.guid: n for n in rd.notes}
    assert set(by_guid) == {"g0", "g1", "g2", "g3"}
    g0, g1, g2, g3 = (by_guid[f"g{i}"] for i in range(4))
    assert not g0.reviewed and not g0.mature and g0.reviews == 0
    assert g1.reviewed and not g1.mature and (g1.reviews, g1.fails) == (3, 1)
    assert g2.reviewed and g2.mature and (g2.reviews, g2.fails) == (2, 0)
    assert g3.suspended and g3.mature and (g3.reviews, g3.fails) == (1, 1)
    assert g1.fields == {"Front": "q1"} and g1.model == "Basic"
    assert len(rd.revlog) == 6 and {c.deck for c in rd.cards} == {"D"}
