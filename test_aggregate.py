#!/usr/bin/env python3
"""EP2 tests — season totalPoints aggregation + per-player gw_history breakdown.

The invariant this epic enforces:
  * Σ wc_players.totalPoints == Σ playerScores(fantasyPoints) over processed
    fixtures (process_fixture writes both; the Increment onto wc_players must
    match the sum of the playerScores docs, with no double-count of the bonus
    that is already folded into fantasyPoints).
  * processing a fixture twice is idempotent (processedForFantasy early-return).
  * for a (uid, gw), Σ gw_history.players[].points == scores.results[uid].points.

PURE unit tests — an in-memory, path-keyed fake Firestore (extends the
_Snap/_Doc/_Coll/FakeDB shape from test_dedup_squads.py). It supports the
operations process_fixture + _snapshot_gw_history call:
``.collection().document().get()/.set(merge=)/.update()``, ``.get()`` (collection
read), ``collection_group(...)``, a ``.batch()`` writer, and interception of the
``firestore.Increment`` sentinel so repeated increments accumulate.

NOT faked here: the full ``finalize_gw`` flow (it reaches into wc_knockout,
elimination detection, transfer windows, standings, prediction bonus and is too
coupled to real client semantics). We exercise ``_snapshot_gw_history`` directly
for the gw_history-sums-to-results invariant — see report notes.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest test_aggregate.py -q
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_scoring import (  # noqa: E402
    process_fixture,
    _snapshot_gw_history,
)

# The fake-Firestore client + seed helpers used to live inline here; EP6-W1
# extracted them into a shared test_helpers module so the e2e reconciliation
# suite can reuse the exact same fake. Import them under the original names so
# the test bodies below are unchanged.
from test_helpers import (  # noqa: E402,F401
    FakeDB,
    player_block as _player_block,
    raw_stats as _raw_stats,
    seed_fixture as _seed_fixture,
    seed_players as _seed_players,
    sum_total_points as _sum_total_points,
    sum_player_scores as _sum_player_scores,
)


def _make_db():
    db = FakeDB()
    # Two players: one DEF, one FWD. No active leagues seeded so propagation is
    # a harmless no-op (keeps these tests focused on the aggregation invariant).
    _seed_players(db, {101: 2, 102: 4, 201: 3, 202: 1})
    # GW1 fixture: team 10 (home) vs team 20 (away), 1-0.
    _seed_fixture(db, 5001, 1, 10, 20, 1, 0)
    return db


def _process(db, fid=5001):
    home = [_player_block(101, "Def One", minutes=90, goals=0, rating="7.5"),
            _player_block(102, "Fwd One", minutes=90, goals=1, rating="8.2")]
    away = [_player_block(201, "Mid Two", minutes=90, goals=0, rating="6.8"),
            _player_block(202, "GK Two", minutes=90, goals=0, rating="6.0")]
    raw = _raw_stats(10, 20, home, away)
    return process_fixture(fid, raw, wc_client=None, db=db)


# ---------------------------------------------------------------------------
# EP2-W1 — totalPoints aggregation
# ---------------------------------------------------------------------------

def test_totalpoints_matches_playerscores():
    db = _make_db()
    _process(db)

    scores_sum = _sum_player_scores(db)
    totals_sum = _sum_total_points(db)
    assert scores_sum == totals_sum
    assert scores_sum > 0  # sanity: something was actually scored

    # Spot-check a single player: totalPoints == that player's fantasyPoints.
    ps = db.store["wc_fixtures/5001/playerScores/102"]
    assert db.store["wc_players/102"]["totalPoints"] == ps["fantasyPoints"]


def test_totalpoints_no_double_count_of_bonus():
    # fantasyPoints already folds in the rating bonus; the season Increment must
    # equal fantasyPoints, NOT fantasyPoints + bonusPoints.
    db = _make_db()
    _process(db)
    for pid in (101, 102, 201, 202):
        ps = db.store.get(f"wc_fixtures/5001/playerScores/{pid}")
        if ps is None:
            continue
        assert db.store[f"wc_players/{pid}"]["totalPoints"] == ps["fantasyPoints"]


# ---------------------------------------------------------------------------
# EP2-W3 — idempotency: processing the same GW/fixture twice is a no-op
# ---------------------------------------------------------------------------

def test_process_idempotent():
    db = _make_db()
    _process(db)

    totals_after_first = _sum_total_points(db)
    scores_after_first = _sum_player_scores(db)
    per_player_first = {k: v["totalPoints"]
                        for k, v in db.store.items() if k.startswith("wc_players/")}

    # Re-process the (now processedForFantasy) fixture — must early-return {}.
    result = _process(db)
    assert result == {}

    assert _sum_total_points(db) == totals_after_first
    assert _sum_player_scores(db) == scores_after_first
    per_player_second = {k: v["totalPoints"]
                         for k, v in db.store.items() if k.startswith("wc_players/")}
    assert per_player_first == per_player_second  # no double count


# ---------------------------------------------------------------------------
# EP2-W2 — gw_history players[].points sum equals results[uid].points
# ---------------------------------------------------------------------------

def test_gw_history_sums_to_results():
    db = FakeDB()
    lid = "lg_agg"
    gw = 1
    league_ref = db.collection("leagues").document(lid)

    starting = [11, 12, 13]
    bench = [14, 15]
    league_ref.collection("lineups").document(f"u_a_{gw}").set(
        {"starting": starting, "bench": bench, "locked": True}
    )

    all_player_points = {11: 6, 12: 2, 13: 3, 14: 1, 15: 0}
    # results.points is the authoritative total = sum over starters (post-autosub).
    starters_total = sum(all_player_points[p] for p in starting)
    results = {"u_a": {"points": starters_total}}
    all_player_stats = {11: {"minutes": 90, "goals": 1}, 12: {"minutes": 90}}

    _snapshot_gw_history(
        league_ref, gw, ["u_a"], all_player_points, results,
        league_phase_gws=[1, 2, 3], knockout_start_gw=4, db=db,
        all_player_stats=all_player_stats,
    )

    hist = db.store[f"leagues/{lid}/gw_history/u_a_{gw}"]
    # starters' points sum to the authoritative results total.
    starter_sum = sum(p["points"] for p in hist["players"] if p["id"] in starting)
    assert starter_sum == results["u_a"]["points"]
    # totalPoints mirrors results.
    assert hist["totalPoints"] == results["u_a"]["points"]
    # EP2-W2: per-player stats threaded through.
    by_id = {p["id"]: p for p in hist["players"]}
    assert by_id[11]["stats"] == {"minutes": 90, "goals": 1}
    assert by_id[13]["stats"] == {}  # absent from all_player_stats -> {}


def test_gw_history_idempotent_overwrite():
    db = FakeDB()
    lid = "lg_agg2"
    gw = 1
    league_ref = db.collection("leagues").document(lid)
    league_ref.collection("lineups").document(f"u_a_{gw}").set(
        {"starting": [11, 12], "bench": [], "locked": True}
    )
    results = {"u_a": {"points": 8}}
    for _ in range(2):
        _snapshot_gw_history(
            league_ref, gw, ["u_a"], {11: 5, 12: 3}, results,
            [1, 2, 3], 4, db, all_player_stats={},
        )
    hist = db.store[f"leagues/{lid}/gw_history/u_a_{gw}"]
    assert len(hist["players"]) == 2
    assert hist["totalPoints"] == 8


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
