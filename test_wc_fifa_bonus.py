#!/usr/bin/env python3
"""fifa_breakdown — FIFA WC 2026 official rules + the scouting-bonus rule.

League total = FIFA round total − scouting + DefCon, where scouting is a FLAT +2
awarded only when the player scored >4 match points AND is <5% owned. The
breakdown itemizes FIFA's published per-stat rules (goal values by position,
clean sheets, SoT for forwards, etc.) and reconciles to FIFA's authoritative
total.

Run:  .venv/bin/python -m pytest test_wc_fifa_bonus.py -q
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.data.wc_live_ingest import fifa_breakdown, _excluded_pts  # noqa: E402


def _line(bd, label):
    return next((ln for ln in bd if ln["label"] == label), None)


# ----- Goal values by position: GK 9, DEF 7, MID 6, FWD 5 -----

def test_goal_value_by_position():
    for pos, val in [(1, 9), (2, 7), (3, 6), (4, 5)]:
        bd = fifa_breakdown({"minutes": 90, "goals": 1}, position=pos, fifa_total=99)
        assert _line(bd, "Goal scored")["pts"] == val, pos


# ----- Clean sheet: GK/DEF +5, MID +1, FWD none -----

def test_clean_sheet_points_by_position():
    cs = {"minutes": 90, "cleanSheet": True, "goalsConceded": 0}
    assert _line(fifa_breakdown(cs, 1, 99), "Clean sheet")["pts"] == 5   # GK
    assert _line(fifa_breakdown(cs, 2, 99), "Clean sheet")["pts"] == 5   # DEF
    assert _line(fifa_breakdown(cs, 3, 99), "Clean sheet")["pts"] == 1   # MID
    assert _line(fifa_breakdown(cs, 4, 99), "Clean sheet") is None       # FWD


# ----- Shots on target: forwards only -----

def test_shots_on_target_forwards_only():
    sot = {"minutes": 90, "shotsOnTarget": 4}
    assert _line(fifa_breakdown(sot, 4, 99), "Shots on target")["pts"] == 2  # FWD: 4//2
    assert _line(fifa_breakdown(sot, 3, 99), "Shots on target") is None      # MID: none


# ----- Scouting bonus: flat +2, only if >4 pts AND <5% owned -----

def test_scouting_when_high_score_and_low_owned():
    # Balogun: FWD, 2 goals (10) + 90' (2) + 3 SoT (1) = 13; FIFA total 15; 1% owned.
    bd = fifa_breakdown({"minutes": 90, "goals": 2, "shotsOnTarget": 3},
                        position=4, fifa_total=15, percent_selected=1.0)
    assert _excluded_pts(bd) == 2
    counted = sum(ln["pts"] for ln in bd if not ln.get("excluded"))
    assert counted == 13  # league total = 15 − 2


def test_no_scouting_when_low_score_even_if_low_owned():
    # Brahim: MID, assist (+3) + 90' (+2); FIFA total 4; 2.1% owned (<5%) but only
    # 4 match points -> NO scouting (the >4 condition spares him). League = 4.
    bd = fifa_breakdown({"minutes": 90, "assists": 1},
                        position=3, fifa_total=4, percent_selected=2.1)
    assert _excluded_pts(bd) == 0
    counted = sum(ln["pts"] for ln in bd if not ln.get("excluded"))
    assert counted == 4


def test_no_scouting_when_widely_owned():
    # High scorer but 12% owned -> no scouting (ownership condition fails).
    bd = fifa_breakdown({"minutes": 90, "goals": 2, "shotsOnTarget": 3},
                        position=4, fifa_total=15, percent_selected=12.0)
    assert _excluded_pts(bd) == 0
    assert sum(ln["pts"] for ln in bd if not ln.get("excluded")) == 15


def test_unknown_ownership_means_no_scouting():
    bd = fifa_breakdown({"minutes": 90, "goals": 2}, position=4, fifa_total=15)
    assert _excluded_pts(bd) == 0


# ----- Reconciliation: a real FIFA stat our feed missed is KEPT, not dropped ---

def test_missed_clean_sheet_is_kept_not_excluded_as_bonus():
    # Ricardo: FIFA gave a clean sheet (subbed off before a late goal); our data
    # shows none, so we only itemize minutes (+2). FIFA total 9, 1.5% owned.
    # scouting = 2 (9>6 & <5%); the other 5 (the clean sheet) is KEPT. League = 7.
    bd = fifa_breakdown({"minutes": 90, "goals": 0, "cleanSheet": False},
                        position=2, fifa_total=9, percent_selected=1.5)
    assert _excluded_pts(bd) == 2
    assert sum(ln["pts"] for ln in bd if not ln.get("excluded")) == 7
    assert _line(bd, "FIFA match points")["pts"] == 5


def test_defcon_line_is_not_excluded():
    bd = fifa_breakdown({"minutes": 90, "goals": 2, "shotsOnTarget": 3},
                        position=4, fifa_total=15, percent_selected=1.0)
    bd.append({"label": "Defensive contribution (11/10)", "value": 11, "pts": 2})
    assert _excluded_pts(bd) == 2  # only the scouting bonus; DefCon counts
