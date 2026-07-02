#!/usr/bin/env python3
"""Tier-1 unit tests for ``WCWaiverManager.get_free_agents`` (the wishlist /
FA pickers' data source).

Regression for the "only Mexico + South Africa" search bug: the endpoint
sliced ``[:limit]`` (default 50) in RAW collection order — nation-clumped —
so most of the pool was silently invisible to every picker, and the rows
carried no stats (``totalPoints`` etc. were never returned, rendering
everyone as 0 pts).

Run:
    .venv/bin/python -m pytest test_wc_free_agents.py -v

Covers: best-first ordering (totalPoints DESC, minutes DESC, name ASC)
applied BEFORE the limit; stats fields present (totalPoints / minutes /
defconBonus / appearances / draftRank); owned + group-stage-eliminated
players excluded; position + name-search filters.
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_waivers import WCWaiverManager  # noqa: E402
from test_wc_wishlist import FakeDB  # noqa: E402

LID = "lg"


def _seed_player(db, pid, name, pos=3, pts=0, minutes=0, defcon=0, apps=0,
                 eliminated=False, team="AAA"):
    db.collection("wc_players").document(str(pid)).set({
        "id": pid, "name": name, "position": pos, "positionName": "MID",
        "teamId": 1, "teamName": team, "teamIso": team,
        "totalPoints": pts, "eliminated": eliminated, "draftRank": pid,
        "seasonStats": {"minutes": minutes, "defconBonus": defcon,
                        "appearances": apps},
    })


@pytest.fixture
def db():
    d = FakeDB()
    _seed_player(d, 1, "Zero Pts Early Doc", pts=0, minutes=0)
    _seed_player(d, 2, "Top Scorer", pts=30, minutes=250, defcon=4, apps=3)
    _seed_player(d, 3, "Mid Scorer", pts=12, minutes=180, defcon=2, apps=2)
    _seed_player(d, 4, "Owned Star", pts=50, minutes=300)
    _seed_player(d, 5, "Group Stage Out", pts=25, minutes=200, eliminated=True)
    _seed_player(d, 6, "Bench Zero A", pts=0, minutes=90)   # more minutes...
    _seed_player(d, 7, "Bench Zero B", pts=0, minutes=10)   # ...beats fewer
    _seed_player(d, 8, "Gustavo Keeper", pos=1, pts=8, minutes=270)
    # Owned Star sits on a squad → excluded.
    d.collection("leagues").document(LID).collection("squads").document("u1").set({
        "players": [{"playerId": 4, "position": 3}],
    })
    return d


@pytest.fixture
def mgr(db):
    return WCWaiverManager(db)


def test_sorted_best_first_before_limit(mgr):
    # The whole point of the fix: a small limit keeps the BEST players, not
    # whichever docs happened to iterate first.
    top2 = mgr.get_free_agents(LID, limit=2)
    assert [p["name"] for p in top2] == ["Top Scorer", "Mid Scorer"]

    ordered = [p["name"] for p in mgr.get_free_agents(LID)]
    assert ordered == ["Top Scorer", "Mid Scorer", "Gustavo Keeper",
                       "Bench Zero A", "Bench Zero B", "Zero Pts Early Doc"]


def test_stats_fields_present(mgr):
    top = mgr.get_free_agents(LID, limit=1)[0]
    assert top["totalPoints"] == 30
    assert top["minutes"] == 250
    assert top["defconBonus"] == 4
    assert top["appearances"] == 3
    assert top["draftRank"] == 2


def test_owned_and_eliminated_excluded(mgr):
    names = {p["name"] for p in mgr.get_free_agents(LID)}
    assert "Owned Star" not in names          # on a squad
    assert "Group Stage Out" not in names     # eliminated flag


def test_position_and_search_filters(mgr):
    gks = mgr.get_free_agents(LID, position=1)
    assert [p["name"] for p in gks] == ["Gustavo Keeper"]
    # The search that surfaced the bug: a name past the old raw-order cut.
    hits = mgr.get_free_agents(LID, search="gus")
    assert [p["name"] for p in hits] == ["Gustavo Keeper"]


def test_missing_season_stats_defaults_to_zero(db, mgr):
    db.collection("wc_players").document("9").set({
        "id": 9, "name": "No Stats Yet", "position": 3, "teamIso": "BBB",
    })
    row = [p for p in mgr.get_free_agents(LID) if p["id"] == 9][0]
    assert (row["totalPoints"], row["minutes"], row["defconBonus"],
            row["appearances"]) == (0, 0, 0, 0)
