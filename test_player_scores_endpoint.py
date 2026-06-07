"""Route-level tests for GET /players/{id}/scores (VT-106 #47).

The endpoint joins each playerScores doc to its parent fixture to (a) name the
OPPONENT (the side that isn't the player's team), (b) drop orphaned scores whose
fixture was deleted, and (c) collapse to one row per GW. These guard the modal
History tab's OPPONENT column + the duplicate-GW1-rows regression.
"""
import flask

from test_helpers import FakeDB
import fpl_predictor.api_wc as api_wc


def _seed(db):
    # Player 100 plays for team 10 (ARG).
    db.store["wc_players/100"] = {"id": 100, "teamId": 10, "teamIso": "ARG"}
    # GW1: ARG (home) v ECU (away) -> opponent ECU.
    db.store["wc_fixtures/9001"] = {
        "id": 9001, "gw": 1,
        "homeTeam": {"id": 10, "isoCode": "ARG", "name": "Argentina"},
        "awayTeam": {"id": 20, "isoCode": "ECU", "name": "Ecuador"},
    }
    db.store["wc_fixtures/9001/playerScores/100"] = {"playerId": 100, "gw": 1, "fantasyPoints": 6}
    # GW2: GER (home) v ARG (away) -> opponent GER.
    db.store["wc_fixtures/9002"] = {
        "id": 9002, "gw": 2,
        "homeTeam": {"id": 30, "isoCode": "GER", "name": "Germany"},
        "awayTeam": {"id": 10, "isoCode": "ARG", "name": "Argentina"},
    }
    db.store["wc_fixtures/9002/playerScores/100"] = {"playerId": 100, "gw": 2, "fantasyPoints": 9}
    # Orphan GW1 score whose fixture (9999) no longer exists — must be dropped,
    # NOT surfaced as a duplicate GW1 row.
    db.store["wc_fixtures/9999/playerScores/100"] = {"playerId": 100, "gw": 1, "fantasyPoints": 3}


def _call(db, pid):
    api_wc.init_wc(db)
    app = flask.Flask(__name__)
    with app.app_context():
        resp, status = api_wc.get_player_scores(pid)
        return status, resp.get_json()["data"]


def test_player_scores_opponent_join_and_dedup():
    db = FakeDB()
    _seed(db)
    status, rows = _call(db, 100)
    assert status == 200
    # Orphan GW1 row dropped -> exactly one row per real fixture GW, sorted.
    assert [r["gw"] for r in rows] == [1, 2]
    by_gw = {r["gw"]: r for r in rows}
    assert by_gw[1]["opponent"] == "ECU"  # player home -> away side
    assert by_gw[2]["opponent"] == "GER"  # player away -> home side


def test_player_scores_empty_when_none():
    db = FakeDB()
    status, rows = _call(db, 100)
    assert status == 200
    assert rows == []
