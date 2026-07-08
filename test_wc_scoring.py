"""
Regression + feature tests for the WC2026 scoring engine.

Covers:
  - EP1-W1: Defensive Contribution (DefCon) thresholds.
  - EP1-W2: rating-rank bonus (replaces the retired bps bonus).
  - EP1-W3: regression lock on the existing core scoring math.

Run from the worktree root:
  PYTHONPATH=. /Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python \
      -m pytest test_wc_scoring.py -q
"""

import pytest

from fpl_predictor.game.wc_scoring import (
    compute_player_points,
    compute_rating_bonus,
)

# Positions: 1=GK, 2=DEF, 3=MID, 4=FWD


def _tackles(total=0, interceptions=0, blocks=0):
    return {"total": total, "interceptions": interceptions, "blocks": blocks}


# ---------------------------------------------------------------------------
# EP1-W1 — DefCon thresholds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "position, defcon_actions, expected_delta",
    [
        (2, 9, 0),    # DEF below threshold (10)
        (2, 10, 2),   # DEF at threshold
        (3, 11, 0),   # MID below threshold (12)
        (3, 12, 2),   # MID at threshold
        (1, 20, 0),   # GK never awarded
        (4, 20, 0),   # FWD never awarded
    ],
)
def test_defcon_thresholds(position, defcon_actions, expected_delta):
    # A bare appearance >=60 is worth 2 base points; isolate the DefCon delta.
    base_stats = {"minutes": 90}
    base, _ = compute_player_points(base_stats, position)

    # Spread the defcon actions across the three contributing tackle fields.
    total = defcon_actions // 3
    interceptions = defcon_actions // 3
    blocks = defcon_actions - total - interceptions
    with_defcon = {
        "minutes": 90,
        "tackles": _tackles(total=total, interceptions=interceptions, blocks=blocks),
    }
    pts, _ = compute_player_points(with_defcon, position)

    assert pts - base == expected_delta


def test_defcon_missing_tackles_is_safe():
    # No tackles key at all → no crash, no award.
    pts, _ = compute_player_points({"minutes": 90}, 2)
    assert pts == 2  # appearance only


def test_defcon_not_awarded_when_minutes_zero():
    # minutes==0 early-return means no DefCon even with huge tackle counts.
    pts, bonus = compute_player_points(
        {"minutes": 0, "tackles": _tackles(total=50)}, 2
    )
    assert (pts, bonus) == (0, 0)


# ---------------------------------------------------------------------------
# EP1-W2 — rating-rank bonus
# ---------------------------------------------------------------------------

def test_rating_bonus_top3():
    rating_list = [
        (101, 7.1),
        (102, 8.9),
        (103, 6.2),
        (104, 8.0),
        (105, 5.5),
    ]
    bonuses = compute_rating_bonus(rating_list)
    assert bonuses == {102: 3, 104: 2, 101: 1}
    assert 103 not in bonuses
    assert 105 not in bonuses


def test_rating_bonus_zero_rating_excluded():
    rating_list = [(1, 0.0), (2, None), (3, 7.5)]
    # None coerced by caller; here we pass explicit values the function handles.
    bonuses = compute_rating_bonus([(1, 0.0), (3, 7.5)])
    assert bonuses == {3: 3}


def test_rating_bonus_tie_shares_rank():
    # Two players tied for 1st both get 3; next gets 1 (rank advances by 2).
    rating_list = [(1, 9.0), (2, 9.0), (3, 7.0), (4, 6.0)]
    bonuses = compute_rating_bonus(rating_list)
    assert bonuses[1] == 3
    assert bonuses[2] == 3
    assert bonuses[3] == 1   # rank 2 (0-based) → award_map[2] == 1
    assert 4 not in bonuses


def test_rating_bonus_tie_for_second():
    # Mirrors the old bps tie docstring: two tied for 2nd both get 2, 4th gets 0.
    rating_list = [(1, 9.0), (2, 8.0), (3, 8.0), (4, 7.0)]
    bonuses = compute_rating_bonus(rating_list)
    assert bonuses[1] == 3
    assert bonuses[2] == 2
    assert bonuses[3] == 2
    assert 4 not in bonuses  # rank advanced past 3


# ---------------------------------------------------------------------------
# EP1-W3 — regression matrix (existing core math, computed by hand)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name, stats, position, expected",
    [
        # appearance <60 → 1; >=60 → 2
        ("appearance_under_60", {"minutes": 45}, 3, (1, 0)),
        ("appearance_60_plus", {"minutes": 90}, 3, (2, 0)),
        # minutes==0 → (0,0)
        ("no_minutes", {"minutes": 0, "goals": 3}, 4, (0, 0)),
        # goals by position (appearance >=60 = 2 base)
        ("goal_gk", {"minutes": 90, "goals": 1}, 1, (2 + 10, 0)),
        ("goal_def", {"minutes": 90, "goals": 1}, 2, (2 + 6, 0)),
        ("goal_mid", {"minutes": 90, "goals": 1}, 3, (2 + 5, 0)),
        ("goal_fwd", {"minutes": 90, "goals": 1}, 4, (2 + 4, 0)),
        # assists (+3 each)
        ("assist", {"minutes": 90, "assists": 2}, 3, (2 + 6, 0)),
        # clean sheet by position (only with >=60 min)
        ("cs_gk", {"minutes": 90, "cleanSheet": True}, 1, (2 + 4, 0)),
        ("cs_def", {"minutes": 90, "cleanSheet": True}, 2, (2 + 4, 0)),
        ("cs_mid", {"minutes": 90, "cleanSheet": True}, 3, (2 + 1, 0)),
        ("cs_fwd", {"minutes": 90, "cleanSheet": True}, 4, (2 + 0, 0)),
        # goals conceded GK/DEF: -1 per 2 conceded (floor)
        ("gc_gk", {"minutes": 90, "goalsConceded": 3}, 1, (2 - 1, 0)),
        ("gc_def", {"minutes": 90, "goalsConceded": 4}, 2, (2 - 2, 0)),
        ("gc_mid_none", {"minutes": 90, "goalsConceded": 4}, 3, (2, 0)),
        # cards
        ("yellow", {"minutes": 90, "yellowCards": 1}, 3, (2 - 1, 0)),
        ("red", {"minutes": 90, "redCards": 1}, 3, (2 - 3, 0)),
        # own goal (-2)
        ("own_goal", {"minutes": 90, "ownGoal": 1}, 2, (2 - 2, 0)),
        # penalty miss (-2), pen save GK-only (+5)
        ("pen_miss", {"minutes": 90, "penaltyMissed": 1}, 4, (2 - 2, 0)),
        ("pen_save_gk", {"minutes": 90, "penaltySaved": 1}, 1, (2 + 5, 0)),
        # saves 1-per-3 for GK
        ("saves_gk", {"minutes": 90, "saves": 7}, 1, (2 + 2, 0)),
        ("saves_under_60", {"minutes": 30, "saves": 3}, 1, (1 + 1, 0)),
    ],
)
def test_engine_regression_matrix(name, stats, position, expected):
    assert compute_player_points(stats, position) == expected, name


def test_compute_bps_bonus_removed():
    import fpl_predictor.game.wc_scoring as ws
    assert not hasattr(ws, "compute_bps_bonus")


# ---------------------------------------------------------------------------
# Auto-subs must preserve the squad (swap, not drop)
# ---------------------------------------------------------------------------
def test_auto_sub_swaps_and_preserves_squad_size():
    """A non-playing starter is swapped to the bench with the incoming sub —
    never dropped. Regression for the '14 players' bug where bench.pop() deleted
    the subbed-out starter, shrinking the 15-man lineup to 14."""
    from fpl_predictor.game.wc_scoring import apply_auto_subs
    starting = [1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14]   # 1GK 4DEF 4MID 2FWD
    bench = [10, 15, 16, 12]                          # bench[0]=GK
    pos = {1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 3, 7: 3, 8: 3, 9: 3,
           13: 4, 14: 4, 10: 1, 15: 4, 16: 3, 12: 3}
    minutes = {p: 90 for p in starting + bench}
    minutes[13] = 0                                   # FWD starter didn't play

    new_starting, new_bench, subs = apply_auto_subs(starting, bench, minutes, pos)

    assert len(new_starting) == 11
    assert len(new_bench) == 4                        # was 3 before the fix
    assert set(new_starting + new_bench) == set(starting + bench)  # nobody lost
    assert 13 not in new_starting and 13 in new_bench  # subbed-out -> bench
    assert subs and subs[0]["out"] == 13


def test_appeared_starter_with_zero_minutes_is_not_autosubbed():
    """Regression (GW5 Medina): a late sub recorded with minutes=0 but
    appeared=1/subIns=1 must NOT be benched. finalize_gw floors an appeared
    player's minutes at 1 before apply_auto_subs; this mirrors that floor and
    asserts the player is kept."""
    from fpl_predictor.game.wc_scoring import apply_auto_subs
    starting = [1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14]
    bench = [10, 15, 16, 12]
    pos = {1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 3, 7: 3, 8: 3, 9: 3,
           13: 4, 14: 4, 10: 1, 15: 4, 16: 3, 12: 3}
    stats = {p: {"minutes": 90} for p in starting + bench}
    stats[13] = {"minutes": 0, "appeared": 1, "subIns": 1}  # late sub, 0 recorded

    # Mirror finalize_gw's all_player_minutes construction (the floor).
    minutes = {}
    for pid, s in stats.items():
        m = s.get("minutes") or 0
        if m == 0 and (s.get("appeared") or s.get("subIns")):
            m = 1
        minutes[pid] = m

    new_starting, new_bench, subs = apply_auto_subs(starting, bench, minutes, pos)
    assert 13 in new_starting          # appeared → stays in the XI
    assert subs == []                  # no auto-sub triggered
