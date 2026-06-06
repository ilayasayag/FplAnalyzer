"""
GAP-503/504 — standings ranking + qualification.

`_update_standings` previously wrote the managers array in arbitrary member
order, never set `rank`, and never set `knockedOut`/`qualified`. The client then
rendered every row as "#1" and "Qualified". These tests pin the fixed behaviour:
the array is sorted by H2H points (then fantasy points as a tiebreak), each
manager gets a 1-based `rank`, and only the top `knockoutQualifiers` are flagged
qualified.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fpl_predictor.game.wc_scoring import _update_standings  # noqa: E402
from test_helpers import FakeDB  # noqa: E402


def _seed_league(qualifiers=2, current_gw=3):
    db = FakeDB()
    lid = "L1"
    db.store[f"leagues/{lid}"] = {
        "knockoutQualifiers": qualifiers,
        "currentGw": current_gw,
    }
    # Three managers with distinct team names.
    for uid, team in [("u1", "Alpha FC"), ("u2", "Bravo FC"), ("u3", "Charlie FC")]:
        db.store[f"leagues/{lid}/members/{uid}"] = {
            "displayName": uid, "teamName": team,
        }
    # One scores doc: u1 & u2 both win (3 H2H pts each), u3 loses (0). Fantasy
    # points break the u1/u2 tie in u2's favour.
    db.store[f"leagues/{lid}/scores/{current_gw}"] = {
        "results": {
            "u1": {"points": 50},
            "u2": {"points": 60},
            "u3": {"points": 40},
        },
        "h2hResults": {
            "u1": {"result": "W"},
            "u2": {"result": "W"},
            "u3": {"result": "L"},
        },
    }
    return db, lid, current_gw


def _managers(db, lid):
    return db.store[f"leagues/{lid}/standings/current"]["managers"]


def test_standings_sorted_and_ranked():
    db, lid, gw = _seed_league(qualifiers=2)
    _update_standings(lid, db, gw)
    managers = _managers(db, lid)

    # Sorted by hpts desc then fpts desc: u2 (3/60) > u1 (3/50) > u3 (0/40).
    assert [m["uid"] for m in managers] == ["u2", "u1", "u3"]
    assert [m["rank"] for m in managers] == [1, 2, 3]


def test_standings_qualification_cutline():
    db, lid, gw = _seed_league(qualifiers=2)
    _update_standings(lid, db, gw)
    managers = _managers(db, lid)
    by_uid = {m["uid"]: m for m in managers}

    # Top-2 qualify; 3rd is knocked out.
    assert by_uid["u2"]["qualified"] is True and by_uid["u2"]["knockedOut"] is False
    assert by_uid["u1"]["qualified"] is True and by_uid["u1"]["knockedOut"] is False
    assert by_uid["u3"]["qualified"] is False and by_uid["u3"]["knockedOut"] is True


def test_standings_row_count_matches_members():
    db, lid, gw = _seed_league()
    _update_standings(lid, db, gw)
    managers = _managers(db, lid)

    # Exactly one row per member; no duplicate/stale rows.
    assert len(managers) == 3
    assert len({m["uid"] for m in managers}) == 3
    # Distinct team names carried through.
    assert {m["teamName"] for m in managers} == {"Alpha FC", "Bravo FC", "Charlie FC"}


def test_standings_writes_per_gw_snapshot():
    db, lid, gw = _seed_league()
    _update_standings(lid, db, gw)
    # Both the live "current" doc and the per-GW snapshot are written + ranked.
    assert f"leagues/{lid}/standings/current" in db.store
    snap = db.store[f"leagues/{lid}/standings/{gw}"]
    assert [m["rank"] for m in snap["managers"]] == [1, 2, 3]
    assert snap["qualifiers"] == 2
