#!/usr/bin/env python3
"""Unit tests for the per-player season-stat aggregation (wc_live_ingest.py).

``recompute_season_stats`` rebuilds ``wc_players/{pid}.seasonStats`` from EVERY
``wc_fixtures/{fid}/playerScores/{pid}`` doc on each pass. It must be a full
recompute (never an increment) so re-running an ingest tick is a no-op.

Run:  .venv/bin/python -m pytest test_wc_season_stats.py -q
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import test_helpers as H  # noqa: E402
from fpl_predictor.data.wc_live_ingest import recompute_season_stats  # noqa: E402


def _score(db, fid, gw, pid, stats, dca=0, dcb=0, pts=0):
    db.collection("wc_fixtures").document(fid).set({"gw": gw})
    db.collection("wc_fixtures").document(fid).collection("playerScores").document(str(pid)).set({
        "playerId": pid, "gw": gw, "stats": stats,
        "defConActions": dca, "defConBonus": dcb, "fantasyPoints": pts,
    })


def _season(db, pid):
    return db.collection("wc_players").document(str(pid)).get().to_dict()["seasonStats"]


def test_sums_across_fixtures():
    db = H.FakeDB()
    _score(db, "f1", 1, 900001,
           {"goals": 1, "assists": 1, "shotsOnTarget": 3, "shots": 5, "minutes": 90, "cleanSheet": True},
           dca=11, dcb=2, pts=15)
    _score(db, "f2", 2, 900001,
           {"goals": 2, "assists": 0, "shotsOnTarget": 2, "shots": 4, "minutes": 75, "cleanSheet": False},
           dca=9, dcb=0, pts=12)
    n = recompute_season_stats(db)
    assert n == 1
    s = _season(db, 900001)
    assert s == {
        "goals": 3, "assists": 1, "shotsOnTarget": 5, "shots": 9,
        "cleanSheets": 1, "minutes": 165, "appearances": 2,
        "defconActions": 20, "defconBonus": 2, "points": 27,
    }


def test_zero_minute_player_has_no_appearance_or_cleansheet():
    db = H.FakeDB()
    _score(db, "f1", 1, 900002,
           {"goals": 0, "assists": 0, "shotsOnTarget": 0, "shots": 0, "minutes": 0, "cleanSheet": False})
    recompute_season_stats(db)
    s = _season(db, 900002)
    assert s["appearances"] == 0
    assert s["cleanSheets"] == 0
    assert s["minutes"] == 0


def test_recompute_is_idempotent():
    db = H.FakeDB()
    _score(db, "f1", 1, 900003,
           {"goals": 2, "assists": 1, "shotsOnTarget": 4, "shots": 7, "minutes": 90, "cleanSheet": True})
    recompute_season_stats(db)
    first = dict(_season(db, 900003))
    # Re-run twice more — a full recompute, so nothing changes.
    recompute_season_stats(db)
    recompute_season_stats(db)
    assert _season(db, 900003) == first


def test_missing_stats_keys_default_to_zero():
    db = H.FakeDB()
    # A sparse stat line (e.g. an early-live tick) must not KeyError.
    _score(db, "f1", 1, 900004, {"minutes": 45})
    recompute_season_stats(db)
    s = _season(db, 900004)
    assert s["minutes"] == 45
    assert s["appearances"] == 1
    assert s["goals"] == 0 and s["assists"] == 0 and s["shotsOnTarget"] == 0


def test_non_numeric_doc_id_skipped():
    db = H.FakeDB()
    _score(db, "f1", 1, 900005, {"goals": 1, "minutes": 90})
    # A stray non-pid doc under playerScores must be ignored, not crash.
    db.collection("wc_fixtures").document("f1").collection("playerScores").document("meta").set({"note": "x"})
    n = recompute_season_stats(db)
    assert n == 1
    assert _season(db, 900005)["goals"] == 1


def test_totalpoints_is_our_fantasy_sum_including_defcon():
    # Tarik-style: FIFA gives +2 (minutes) but the league adds +2 DefCon, so the
    # per-fixture fantasyPoints is 4 and the season TOTAL must be 4, not 2.
    db = H.FakeDB()
    _score(db, "f1", 1, 900006, {"minutes": 90, "cleanSheet": False},
           dca=13, dcb=2, pts=4)
    recompute_season_stats(db)
    doc = db.collection("wc_players").document("900006").get().to_dict()
    assert doc["seasonStats"]["points"] == 4
    assert doc["totalPoints"] == 4  # the column/modal Total reads this


def test_totalpoints_sums_across_gws():
    db = H.FakeDB()
    _score(db, "f1", 1, 900007, {"minutes": 90}, pts=4)
    _score(db, "f2", 2, 900007, {"minutes": 75}, pts=6)
    recompute_season_stats(db)
    doc = db.collection("wc_players").document("900007").get().to_dict()
    assert doc["totalPoints"] == 10
    assert doc["seasonStats"]["points"] == 10
