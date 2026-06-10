"""Auto-pick honors the manager's draft watchlist before falling back to the
best-available-by-draft-rank heuristic (DraftEngine._find_best_available).

Uses the shared FakeDB so it runs in the normal unit suite (no emulator)."""
import pytest

from test_helpers import FakeDB
from fpl_predictor.game.draft import DraftEngine


# --- minimal player pool: 11 is the best by rank, 10 is a low-rank FWD --------
PLAYERS = [
    {"id": 10, "element_type": 4, "draft_rank": 50, "total_points": 5},   # FWD, weak
    {"id": 11, "element_type": 4, "draft_rank": 1,  "total_points": 99},  # FWD, best
    {"id": 12, "element_type": 3, "draft_rank": 2,  "total_points": 90},  # MID
    {"id": 13, "element_type": 1, "draft_rank": 3,  "total_points": 80},  # GK
]


class _FakeFpl:
    def get_players(self):
        return [dict(p) for p in PLAYERS]


def _engine(db):
    return DraftEngine(db, _FakeFpl())


def _seed_watchlist(db, lid, uid, ids):
    (db.collection("leagues").document(lid).collection("draft")
     .document("watchlists").collection(uid).document("list")
     .set({"playerIds": ids}))


def _seed_pick(db, lid, uid, position, i):
    (db.collection("leagues").document(lid).collection("draft")
     .document("state").collection("picks").document(f"pk{i}")
     .set({"uid": uid, "position": position}))


def test_autopick_takes_top_watchlist_player_over_better_rank():
    db = FakeDB()
    _seed_watchlist(db, "L", "u1", [10])          # weak FWD, but #1 on my list
    pid = _engine(db)._find_best_available("L", "u1", {"pickedPlayerIds": []})
    assert pid == 10                               # NOT 11 (the higher-ranked FWD)


def test_autopick_skips_watchlist_player_whose_position_is_full():
    db = FakeDB()
    # Already hold 3 FWDs → FWD quota (3) is full, so the FWD on my list is skipped.
    for i in range(3):
        _seed_pick(db, "L", "u1", 4, i)
    _seed_watchlist(db, "L", "u1", [10, 12])       # 10=FWD (full), 12=MID (room)
    pid = _engine(db)._find_best_available("L", "u1", {"pickedPlayerIds": []})
    assert pid == 12


def test_autopick_skips_already_taken_watchlist_player():
    db = FakeDB()
    _seed_watchlist(db, "L", "u1", [10, 12])
    pid = _engine(db)._find_best_available("L", "u1", {"pickedPlayerIds": [10]})
    assert pid == 12                               # 10 gone → next on the list


def test_autopick_falls_back_to_rank_when_watchlist_empty_or_unusable():
    db = FakeDB()                                   # no watchlist doc at all
    pid = _engine(db)._find_best_available("L", "u1", {"pickedPlayerIds": []})
    assert pid in {p["id"] for p in PLAYERS}        # picked by need+rank, not crash
    # With an empty squad the resolver targets a needed position by draft rank.
    assert pid == 12


# --- nation cap (max 3 per nation) -------------------------------------------
NATION_PLAYERS = [
    {"id": 20, "element_type": 2, "draft_rank": 1, "total_points": 9, "teamShort": "FRA"},
    {"id": 21, "element_type": 2, "draft_rank": 2, "total_points": 8, "teamShort": "FRA"},
    {"id": 22, "element_type": 2, "draft_rank": 3, "total_points": 7, "teamShort": "FRA"},
    {"id": 23, "element_type": 2, "draft_rank": 4, "total_points": 6, "teamShort": "FRA"},  # 4th FRA
    {"id": 24, "element_type": 2, "draft_rank": 5, "total_points": 5, "teamShort": "GER"},
    {"id": 25, "element_type": 3, "draft_rank": 6, "total_points": 4, "teamShort": "GER"},
]


class _FakeFplNations:
    def get_players(self):
        return [dict(p) for p in NATION_PLAYERS]

    def get_player_map(self):
        return {p["id"]: dict(p) for p in NATION_PLAYERS}


def _seed_nation_pick(db, lid, uid, player, i):
    (db.collection("leagues").document(lid).collection("draft")
     .document("state").collection("picks").document(f"npk{i}")
     .set({"uid": uid, "position": player["element_type"],
           "playerId": player["id"]}))


def test_autopick_skips_watchlist_player_when_nation_capped():
    db = FakeDB()
    for i, p in enumerate(NATION_PLAYERS[:3]):     # hold 3 FRA already
        _seed_nation_pick(db, "L", "u1", p, i)
    _seed_watchlist(db, "L", "u1", [23, 24])       # 23=4th FRA, 24=GER
    eng = DraftEngine(db, _FakeFplNations())
    pid = eng._find_best_available("L", "u1", {"pickedPlayerIds": [20, 21, 22]})
    assert pid == 24                               # FRA capped → GER next


def test_autopick_fallback_avoids_capped_nation():
    db = FakeDB()
    for i, p in enumerate(NATION_PLAYERS[:3]):     # hold 3 FRA, no watchlist
        _seed_nation_pick(db, "L", "u1", p, i)
    eng = DraftEngine(db, _FakeFplNations())
    pid = eng._find_best_available("L", "u1", {"pickedPlayerIds": [20, 21, 22]})
    assert pid in (24, 25)                         # never 23 (4th FRA)


def test_make_pick_rejects_while_paused():
    db = FakeDB()
    (db.collection("leagues").document("L").collection("draft").document("state")
     .set({"status": "active", "paused": True, "order": ["u1"], "currentPick": 0,
           "totalPicks": 15, "pickTimer": 30, "pickedPlayerIds": []}))
    eng = DraftEngine(db, _FakeFplNations())
    with pytest.raises(ValueError, match="paused"):
        eng.make_pick("L", "u1", 20)


def _seed_state(db, lid="L", **over):
    base = {"status": "active", "order": ["u1", "u2"], "currentPick": 0,
            "totalPicks": 30, "pickTimer": 30, "pickedPlayerIds": [],
            "paused": False}
    base.update(over)
    (db.collection("leagues").document(lid).collection("draft")
     .document("state").set(base))
    return base


def test_make_pick_rejects_stale_expected_pick():
    db = FakeDB()
    _seed_state(db, currentPick=5)
    eng = DraftEngine(db, _FakeFplNations())
    with pytest.raises(ValueError, match="STALE_PICK"):
        eng.make_pick("L", "u2", 24, is_auto=True, expected_pick=4)


def test_auto_pick_for_previous_drafter_not_reassigned():
    # An auto pick computed for u1 must NOT be credited to u2 after the turn
    # advanced (the old code silently reassigned it — "random player" bug).
    db = FakeDB()
    _seed_state(db, currentPick=1)              # drafter at pick 1 = u2
    eng = DraftEngine(db, _FakeFplNations())
    with pytest.raises(ValueError, match="TURN_CHANGED"):
        eng.make_pick("L", "u1", 24, is_auto=True)


def test_auto_pick_retries_next_candidate_when_taken():
    # Best candidate already in pickedPlayerIds -> engine must pick the NEXT
    # best instead of stalling. 20 is "taken", so the auto pick lands 21.
    import time as _t
    db = FakeDB()
    _seed_state(db, order=["u1"], currentPick=0,
                pickedPlayerIds=[20], pickDeadline=_t.time() - 5)
    _seed_watchlist(db, "L", "u1", [20, 21])
    eng = DraftEngine(db, _FakeFplNations())
    res = eng.auto_pick("L")
    assert res["playerId"] == 21


def test_rollback_rewinds_and_dedupes():
    db = FakeDB()
    _seed_state(db, currentPick=3, paused=True,
                pickedPlayerIds=[20, 21, 21])    # corrupted: 21 duplicated
    picks = (db.collection("leagues").document("L").collection("draft")
             .document("state").collection("picks"))
    picks.document("0").set({"pickNumber": 0, "uid": "u1", "playerId": 20, "webName": "A"})
    picks.document("1").set({"pickNumber": 1, "uid": "u2", "playerId": 21, "webName": "B"})
    picks.document("2").set({"pickNumber": 2, "uid": "u2", "playerId": 21, "webName": "B"})  # dup!
    eng = DraftEngine(db, _FakeFplNations())
    res = eng.rollback_draft("L", 1)             # pick 1 back on the clock
    assert res["currentPick"] == 1
    assert [r["pickNumber"] for r in res["removed"]] == [1, 2]
    state = (db.collection("leagues").document("L").collection("draft")
             .document("state").get().to_dict())
    assert state["currentPick"] == 1
    assert state["pickedPlayerIds"] == [20]      # rebuilt + deduped
    assert state["paused"] is True               # stays paused until resume
    assert state["currentDrafter"] == "u2"       # pick 1 in [u1,u2] snake


def test_validate_detects_duplicates():
    db = FakeDB()
    _seed_state(db, currentPick=2, pickedPlayerIds=[20])
    picks = (db.collection("leagues").document("L").collection("draft")
             .document("state").collection("picks"))
    picks.document("0").set({"pickNumber": 0, "uid": "u1", "playerId": 20, "position": 2, "webName": "A"})
    picks.document("1").set({"pickNumber": 1, "uid": "u2", "playerId": 20, "position": 2, "webName": "A"})
    eng = DraftEngine(db, _FakeFplNations())
    rep = eng.validate_draft("L")
    assert rep["ok"] is False
    assert rep["duplicates"][0]["playerId"] == 20
    assert len(rep["duplicates"][0]["picks"]) == 2


def test_make_pick_rejects_fourth_same_nation_player():
    db = FakeDB()
    lid, uid = "L", "u1"
    state_ref = (db.collection("leagues").document(lid)
                 .collection("draft").document("state"))
    state_ref.set({
        "status": "active", "order": [uid], "currentPick": 0,
        "totalPicks": 15, "pickTimer": 30, "pickedPlayerIds": [20, 21, 22],
    })
    for i, p in enumerate(NATION_PLAYERS[:3]):     # u1 already drafted 3 FRA
        _seed_nation_pick(db, lid, uid, p, i)
    eng = DraftEngine(db, _FakeFplNations())
    with pytest.raises(ValueError, match="max 3 players from FRA"):
        eng.make_pick(lid, uid, 23)                # 4th FRA → rejected
    res = eng.make_pick(lid, uid, 24)              # GER → allowed
    assert res["playerId"] == 24
