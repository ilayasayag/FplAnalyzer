"""get_all_players() filters malformed/empty wc_players docs.

Empty pool docs (no position/name/id) used to flow through to the client, where
they rendered as "UNDEFINED / Group ?" rows and — with draft_rank 0 — sorted to
the top of the draft pool, colliding on a duplicate String(undefined) key.
"""
from test_helpers import FakeDB
from fpl_predictor.data.wc_api import WC2026Client


def _seed_player(db, doc_id, **fields):
    db.collection("wc_players").document(str(doc_id)).set(fields)


def test_get_all_players_drops_positionless_junk_docs():
    db = FakeDB()
    # Two real, draftable players (have a position).
    _seed_player(db, 900001, id=900001, name="Raúl Rangel", position=1, teamId=12, draftRank=40)
    _seed_player(db, 900002, id=900002, name="Cristiano Ronaldo", position=4, teamId=27, draftRank=1)
    # Three malformed/empty docs — exactly the shape that broke the draft pool.
    _seed_player(db, "junk_a", web_name="?", form="0", totalPoints=0)   # no position/id
    _seed_player(db, "junk_b", position=None, name=None)
    _seed_player(db, "junk_c")                                          # totally empty

    players = WC2026Client(db=db).get_all_players(db)

    # Only the two real players survive.
    assert len(players) == 2
    names = {p["name"] for p in players}
    assert names == {"Raúl Rangel", "Cristiano Ronaldo"}
    # Every returned player has a usable id and position (no String(undefined)).
    for p in players:
        assert p.get("id") is not None
        assert p.get("element_type") in (1, 2, 3, 4)


def test_get_all_players_backfills_id_from_doc_id():
    db = FakeDB()
    # A real player whose doc omits the internal "id" field — id should come
    # from the (numeric) Firestore doc id rather than being left undefined.
    _seed_player(db, 900003, name="Lamine Yamal", position=3, teamId=9, draftRank=7)
    players = WC2026Client(db=db).get_all_players(db)
    assert len(players) == 1
    assert players[0]["id"] == 900003
