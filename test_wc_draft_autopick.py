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
