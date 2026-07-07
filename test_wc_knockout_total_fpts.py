"""
Total-points knockout (GW7 SF + GW8 Final for a 6-manager league).

Pins the WC2026 knockout rules the way the game actually works:
  * Qualification + seeding are by TOTAL season fpts — NOT the H2H table.
  * The two non-qualifiers are eliminated at seeding: their entire squad is
    released to the free-agent pool and they're flagged ``eliminated``.
  * Knockout wishlist pick order = seed order (seed 1 → waiverPriority 1).
  * After the semis the two losers are released the same way and the final's
    pick order is set by seed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fpl_predictor.game.wc_knockout import (  # noqa: E402
    _compute_seeds, seed_knockout, advance_knockout_bracket,
)
from test_helpers import FakeDB  # noqa: E402


def test_compute_seeds_ranks_by_fpts_not_hpts():
    # H2H order (hpts) deliberately DISAGREES with fpts order. Seeds must follow
    # fpts: c(300) > a(250) > d(240) > b(230); e/f miss out.
    managers = [
        {"uid": "a", "hpts": 12, "fpts": 250},
        {"uid": "b", "hpts": 11, "fpts": 230},
        {"uid": "c", "hpts": 3,  "fpts": 300},
        {"uid": "d", "hpts": 9,  "fpts": 240},
        {"uid": "e", "hpts": 8,  "fpts": 200},
        {"uid": "f", "hpts": 1,  "fpts": 150},
    ]
    seeds = _compute_seeds(managers, qualifiers=4, draft_positions={})
    assert [s["uid"] for s in seeds] == ["c", "a", "d", "b"]
    assert [s["seed"] for s in seeds] == [1, 2, 3, 4]
    assert all(s["qualifiedVia"] == "fpts" for s in seeds)


def _seed_six_manager_league():
    db = FakeDB()
    lid = "L1"
    db.store[f"leagues/{lid}"] = {
        "knockoutStartGw": 7, "knockoutQualifiers": 4, "adminUid": "a",
    }
    # fpts order: a>b>c>d>e>f  → seeds a,b,c,d ; e,f eliminated.
    fpts = {"a": 300, "b": 280, "c": 260, "d": 240, "e": 220, "f": 200}
    managers = [{"uid": u, "hpts": 0, "fpts": p, "displayName": u, "teamName": u}
                for u, p in fpts.items()]
    db.store[f"leagues/{lid}/standings/current"] = {"managers": managers}
    for u in fpts:
        db.store[f"leagues/{lid}/members/{u}"] = {"draftPosition": 1, "waiverPriority": 9}
        db.store[f"leagues/{lid}/squads/{u}"] = {
            "players": [{"playerId": int(f"{ord(u)}0{i}")} for i in range(3)]
        }
    return db, lid


def test_seed_knockout_seeds_eliminates_and_sets_pick_order():
    db, lid = _seed_six_manager_league()
    res = seed_knockout(lid, db)

    # Seeds by fpts.
    assert [s["uid"] for s in res["seeds"]] == ["a", "b", "c", "d"]
    # SF matchups: seed 1v4 and 2v3.
    sf = db.store[f"leagues/{lid}/knockout/bracket"]["rounds"]["sf"]
    pairs = {(m["seedHome"], m["seedAway"]): (m["home"], m["away"]) for m in sf}
    assert pairs[(1, 4)] == ("a", "d")
    assert pairs[(2, 3)] == ("b", "c")
    assert all(m["gw"] == 7 for m in sf)

    # 5th/6th (e, f) eliminated + squads released to free agents.
    assert set(res["eliminated"]) == {"e", "f"}
    for u in ("e", "f"):
        assert db.store[f"leagues/{lid}/members/{u}"]["eliminated"] is True
        assert db.store[f"leagues/{lid}/members/{u}"]["eliminatedAtGw"] == 7
        assert db.store[f"leagues/{lid}/squads/{u}"]["players"] == []
    # Qualifiers keep their squads.
    for u in ("a", "b", "c", "d"):
        assert len(db.store[f"leagues/{lid}/squads/{u}"]["players"]) == 3
        assert not db.store[f"leagues/{lid}/members/{u}"].get("eliminated")

    # Pick order = seed order (seed 1 → waiverPriority 1).
    assert db.store[f"leagues/{lid}/members/a"]["waiverPriority"] == 1
    assert db.store[f"leagues/{lid}/members/b"]["waiverPriority"] == 2
    assert db.store[f"leagues/{lid}/members/c"]["waiverPriority"] == 3
    assert db.store[f"leagues/{lid}/members/d"]["waiverPriority"] == 4

    # A release transaction was logged for each eliminated manager.
    txns = [v for k, v in db.store.items()
            if k.startswith(f"leagues/{lid}/transactions/")
            and v.get("type") == "squad_released"]
    assert {t["uid"] for t in txns} == {"e", "f"}


def test_advance_semis_releases_losers_and_sets_final_order():
    db, lid = _seed_six_manager_league()
    seed_knockout(lid, db)

    # GW7 results: a beats d (SF 1v4), b beats c (SF 2v3). Winners a, b.
    db.store[f"leagues/{lid}/scores/7"] = {"results": {
        "a": {"points": 90}, "d": {"points": 40},
        "b": {"points": 70}, "c": {"points": 55},
    }}
    advance_knockout_bracket(lid, 7, db)

    bracket = db.store[f"leagues/{lid}/knockout/bracket"]
    final = bracket["rounds"]["final"]
    assert len(final) == 1
    # Higher seed (a, seed 1) is home; b (seed 2) away; played in GW8.
    assert final[0]["home"] == "a" and final[0]["away"] == "b"
    assert final[0]["gw"] == 8

    # SF losers (c, d) eliminated + released.
    for u in ("c", "d"):
        assert db.store[f"leagues/{lid}/members/{u}"]["eliminated"] is True
        assert db.store[f"leagues/{lid}/squads/{u}"]["players"] == []

    # Final pick order by seed: a → 1, b → 2.
    assert db.store[f"leagues/{lid}/members/a"]["waiverPriority"] == 1
    assert db.store[f"leagues/{lid}/members/b"]["waiverPriority"] == 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("ALL KNOCKOUT TESTS PASSED")
