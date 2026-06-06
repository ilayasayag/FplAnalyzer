#!/usr/bin/env python3
"""EP6-W2 — end-to-end scoring reconciliation.

One suite that fails if ANY layer of the merged EP1/EP2/EP3 pipeline drifts:
the per-player scoring engine, the season aggregation onto
``wc_players.totalPoints``, or the per-manager ``gw_history`` snapshot join.

It runs the REAL ``process_fixture`` (engine + aggregation + persistence) and
the REAL ``_snapshot_gw_history`` against the shared seeded fake Firestore from
``test_helpers`` (EP6-W1) — a realistic dataset with all four positions, two
fixtures, and two managers with squads + lineups.

The three invariants (see WC2026 scoring fix plan EP6):

  1. Per-player reconciliation (engine <-> persisted):
       playerScores(p,gw).fantasyPoints
         == compute_player_points(stats, pos, rules)[0]   # base
            + playerScores(p,gw).bonusPoints               # rating bonus
     i.e. the persisted total is exactly base + bonus, recomputed from the
     persisted stats themselves. Catches engine drift AND any mismatch between
     what was scored and what was written.

  2. Season aggregation:
       Σ wc_players.totalPoints == Σ over all playerScores of fantasyPoints
     The atomic Increment onto each player's season total must equal the sum of
     the per-fixture fantasyPoints, with NO double-count of the bonus (which is
     already folded into fantasyPoints).

  3. Manager total reconciliation (finalize layer that DOES run on the fake):
       Σ gw_history{uid}_{gw}.players[].points (starters only, post-autosub)
         == scores/{gw}.results.{uid}.points   (minus captain bonus)
     Captain bonus is disabled in this game (resolve_captain_bonus -> 0), so
     the relation is a plain equality. We derive results.points from the
     authoritative engine output (the per-player fantasyPoints of each
     manager's locked starters) and feed it to the real _snapshot_gw_history,
     then assert the snapshot's starter points sum back to it.

SCOPE NOTE (mirrors EP2's test_aggregate.py): the FULL ``finalize_gw`` is not
exercised here — it reaches into knockout seeding, elimination detection,
transfer-window/standings side effects and the real ``WC2026Client``, which are
too coupled to drive against the in-memory fake. We exercise the layers that DO
run on the fake: process_fixture -> playerScores -> totalPoints, and
_snapshot_gw_history with directly-seeded lineups/scores. The auto-sub +
results-derivation arithmetic that finalize_gw performs in between is reproduced
faithfully in this test (apply_auto_subs + sum of starter fantasyPoints) so
invariant 3 is still a real end-to-end check of the snapshot join. The
finalize-only gaps (knockout/elimination/window) need the emulator.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest test_e2e_reconcile.py -q
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_scoring import (  # noqa: E402
    apply_auto_subs,
    compute_player_points,
    process_fixture,
    _snapshot_gw_history,
)
from test_helpers import (  # noqa: E402
    SEED_FIXTURE_RAW,
    SEED_LID,
    SEED_MANAGERS,
    SEED_POSITIONS,
    build_seeded_db,
    sum_player_scores,
    sum_total_points,
)


# Default engine rules (no wc_config override) — None lets the engine use its
# built-in scoring table. A custom-rules variant is exercised below.
@pytest.fixture
def db():
    return build_seeded_db()


def _process_all(db):
    """Run the real process_fixture on every seeded fixture (GW1)."""
    results = {}
    for fid, raw in SEED_FIXTURE_RAW.items():
        results[fid] = process_fixture(fid, raw, wc_client=None, db=db)
    return results


def _rules_in(db):
    cfg = db.store.get("wc_config/tournament")
    return (cfg or {}).get("rules", {}) if cfg else {}


# ---------------------------------------------------------------------------
# Invariant 1 — per-player engine <-> persisted reconciliation
# ---------------------------------------------------------------------------

def _assert_per_player(db):
    rules = _rules_in(db)
    seen = 0
    for key, ps in db.store.items():
        if "/playerScores/" not in key:
            continue
        seen += 1
        pid = ps["playerId"]
        pos = SEED_POSITIONS[pid]
        base, _ = compute_player_points(ps["stats"], pos, rules)
        bonus = ps["bonusPoints"]
        assert ps["fantasyPoints"] == base + bonus, (
            f"player {pid}: persisted fantasyPoints={ps['fantasyPoints']} != "
            f"recomputed base({base}) + bonus({bonus})"
        )
    return seen


def test_per_player_reconciles(db):
    _process_all(db)
    seen = _assert_per_player(db)
    # Every player on the pitch (minutes>0) gets a playerScores doc. The
    # 0-minute no-show (206) scores 0 base+bonus but is still written.
    assert seen >= 18


# ---------------------------------------------------------------------------
# Invariant 2 — season totalPoints aggregation
# ---------------------------------------------------------------------------

def test_season_totals_reconcile(db):
    _process_all(db)
    scores_sum = sum_player_scores(db)
    totals_sum = sum_total_points(db)
    assert scores_sum == totals_sum
    assert scores_sum > 0  # sanity: something was actually scored

    # And per-player: each wc_players.totalPoints equals that player's single
    # GW1 fantasyPoints (no double count of the rating bonus).
    for pid in SEED_POSITIONS:
        ps = db.store.get(f"wc_fixtures/9001/playerScores/{pid}") or \
            db.store.get(f"wc_fixtures/9002/playerScores/{pid}")
        if ps is None:
            continue
        assert db.store[f"wc_players/{pid}"]["totalPoints"] == ps["fantasyPoints"]


# ---------------------------------------------------------------------------
# Invariant 3 — manager total reconciliation via gw_history snapshot
# ---------------------------------------------------------------------------

def _derive_results_and_history(db, gw=1):
    """Reproduce the finalize_gw arithmetic that feeds _snapshot_gw_history.

    Builds all_player_points/minutes/stats from the persisted playerScores
    (exactly as finalize_gw does), applies auto-subs per manager, derives
    results.{uid}.points as the sum of post-autosub starters' fantasyPoints
    (captain bonus disabled => no extra term), persists those results, then
    runs the REAL _snapshot_gw_history. Returns (results, uid_list).
    """
    all_player_points, all_player_minutes, all_player_stats = {}, {}, {}
    for key, ps in db.store.items():
        if "/playerScores/" not in key:
            continue
        pid = ps["playerId"]
        all_player_points[pid] = all_player_points.get(pid, 0) + ps["fantasyPoints"]
        all_player_minutes[pid] = all_player_minutes.get(pid, 0) + (ps["stats"].get("minutes") or 0)
        all_player_stats[pid] = ps["stats"]

    league_ref = db.collection("leagues").document(SEED_LID)
    uid_list = list(SEED_MANAGERS.keys())
    results = {}
    for uid in uid_list:
        lineup_ref = league_ref.collection("lineups").document(f"{uid}_{gw}")
        lineup = lineup_ref.get().to_dict()
        new_starting, new_bench, subs = apply_auto_subs(
            lineup["starting"], lineup["bench"], all_player_minutes, SEED_POSITIONS
        )
        base_pts = sum(all_player_points.get(p, 0) for p in new_starting)
        # captain bonus disabled in this game
        results[uid] = {"points": base_pts, "rawPoints": base_pts, "captainBonus": 0}
        lineup_ref.update({"starting": new_starting, "bench": new_bench,
                           "autoSubsMade": subs, "locked": True})

    league_ref.collection("scores").document(str(gw)).set({"results": results})

    _snapshot_gw_history(
        league_ref, gw, uid_list, all_player_points, results,
        league_phase_gws=[1, 2, 3], knockout_start_gw=4, db=db,
        all_player_stats=all_player_stats,
    )
    return results, uid_list


def test_manager_totals_reconcile(db):
    _process_all(db)
    results, uid_list = _derive_results_and_history(db)

    league_ref = db.collection("leagues").document(SEED_LID)
    for uid in uid_list:
        hist = league_ref.collection("gw_history").document(f"{uid}_1").get().to_dict()
        assert hist is not None, f"no gw_history for {uid}"
        lineup = league_ref.collection("lineups").document(f"{uid}_1").get().to_dict()
        starters = set(lineup["starting"])  # post-autosub
        starter_sum = sum(p["points"] for p in hist["players"] if p["id"] in starters)
        # Invariant 3: starters' snapshot points sum == results.points
        # (minus captain bonus, which is 0 here).
        captain_bonus = results[uid].get("captainBonus", 0)
        assert starter_sum == results[uid]["points"] - captain_bonus
        assert hist["totalPoints"] == results[uid]["points"]


# ---------------------------------------------------------------------------
# The whole-pipeline test: all three invariants in one pass
# ---------------------------------------------------------------------------

def test_full_invariant(db):
    # Layer 1+2: engine + aggregation + persistence.
    _process_all(db)
    n_players = _assert_per_player(db)
    assert n_players >= 18
    assert sum_player_scores(db) == sum_total_points(db) > 0

    # Layer 3: snapshot join reconciles to manager totals.
    results, uid_list = _derive_results_and_history(db)
    league_ref = db.collection("leagues").document(SEED_LID)
    for uid in uid_list:
        hist = league_ref.collection("gw_history").document(f"{uid}_1").get().to_dict()
        lineup = league_ref.collection("lineups").document(f"{uid}_1").get().to_dict()
        starters = set(lineup["starting"])
        starter_sum = sum(p["points"] for p in hist["players"] if p["id"] in starters)
        assert starter_sum == results[uid]["points"] - results[uid].get("captainBonus", 0)


def test_full_invariant_with_custom_rules():
    """Same end-to-end check but with a wc_config/tournament rules override.

    Proves the engine honours custom scoring AND that the persisted
    fantasyPoints still reconcile to a recompute under those same rules
    (invariant 1) and aggregate cleanly (invariant 2). Guards against a rules
    path that scores one way but persists/aggregates another.
    """
    custom_rules = {
        "scoring": {
            "appearUnder60": 1,
            "appear60Plus": 2,
            "goalPoints": {"1": 10, "2": 6, "3": 5, "4": 4},
            "csPoints": {"1": 4, "2": 4, "3": 1, "4": 0},
            "gcPointsPer2": {"1": -1, "2": -1, "3": 0, "4": 0},
            "defConPoints": 2,
            "defConThresholdDef": 10,
            "defConThresholdMid": 12,
        }
    }
    db = build_seeded_db(rules=custom_rules)
    _process_all(db)
    _assert_per_player(db)  # recompute uses the seeded custom rules
    assert sum_player_scores(db) == sum_total_points(db) > 0


# ---------------------------------------------------------------------------
# Idempotency at the e2e layer: re-processing changes nothing
# ---------------------------------------------------------------------------

def test_reprocess_is_noop(db):
    _process_all(db)
    totals_before = sum_total_points(db)
    scores_before = sum_player_scores(db)

    again = _process_all(db)
    # Every fixture is already processedForFantasy -> early-return {}.
    assert all(r == {} for r in again.values())
    assert sum_total_points(db) == totals_before
    assert sum_player_scores(db) == scores_before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
