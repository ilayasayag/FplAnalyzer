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

from fpl_predictor.data.wc_live_ingest import (  # noqa: E402
    fifa_breakdown, _excluded_pts, fetch_espn_match_stats,
)


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


# ----- FIFA position drives the itemization, not our draft position -----

def test_fifa_position_used_for_goal_value():
    # "Brown": FIFA classifies as DEF (goal +7) but we drafted him MID (goal +6).
    # The itemized "Goal scored" line must follow FIFA (+7), and the total must
    # still equal FIFA − scouting (no leak into the reconciliation line).
    # 90' (+2) + DEF goal (+7) = 9; FIFA total 9; 20% owned -> no scouting.
    bd = fifa_breakdown({"minutes": 90, "goals": 1}, position=3, fifa_total=9,
                        percent_selected=20.0, fifa_position=2)
    assert _line(bd, "Goal scored")["pts"] == 7          # DEF value, not MID's 6
    # nothing leaked into a reconciliation line, and no scouting taken
    assert _line(bd, "FIFA match points") is None
    assert _line(bd, "FIFA adjustment") is None
    assert _excluded_pts(bd) == 0
    counted = sum(ln["pts"] for ln in bd if not ln.get("excluded"))
    assert counted == 9  # == FIFA total (HARD INVARIANT: total = FIFA − scouting)


def test_fifa_position_falls_back_to_pool_position():
    # No FIFA position supplied -> itemize with our pool position (MID goal +6).
    bd = fifa_breakdown({"minutes": 90, "goals": 1}, position=3, fifa_total=8,
                        percent_selected=20.0)
    assert _line(bd, "Goal scored")["pts"] == 6


# ----- FIFA extras: penalty won (+2), penalty conceded (-1), FK goal (+1) -----

def test_penalty_won_itemized_nmecha():
    # Felix Nmecha (Germany): MID, 72' (+2), goal (+6), penalty won (+2),
    # 3 tackles (+1) = 11 itemized; FIFA total 13; 0.1% owned -> scouting 2
    # (13>6 & <5%). The "Penalty won" line is present and the reconciliation
    # absorbs nothing extra: counted total == FIFA − scouting == 11.
    bd = fifa_breakdown(
        {"minutes": 72, "goals": 1, "penaltiesWon": 1, "tackles": 3},
        position=3, fifa_total=13, percent_selected=0.1)
    won = _line(bd, "Penalty won")
    assert won is not None and won["pts"] == 2
    assert _excluded_pts(bd) == 2
    counted = sum(ln["pts"] for ln in bd if not ln.get("excluded"))
    assert counted == 11  # FIFA 13 − scouting 2
    # nothing leaked into the reconciliation line (everything itemized)
    assert _line(bd, "FIFA match points") is None
    assert _line(bd, "FIFA adjustment") is None


def test_penalty_conceded_itemized_bazoer():
    # Riechedly Bazoer (Curaçao): DEF, 87' (+2), 6 goals conceded (-5),
    # penalty conceded (-1) = -4 itemized; FIFA total -4; 0% owned -> no scouting.
    # This is the exact bug: the -1 must be ITEMIZED and counted, so the league
    # total is -4, NOT -3 (which is what dropping the -1 into the catch-all gave).
    bd = fifa_breakdown(
        {"minutes": 87, "goalsConceded": 6, "penaltiesConceded": 1, "cleanSheet": False},
        position=2, fifa_total=-4, percent_selected=0.0)
    conc = _line(bd, "Penalty conceded")
    assert conc is not None and conc["pts"] == -1
    assert _excluded_pts(bd) == 0
    counted = sum(ln["pts"] for ln in bd if not ln.get("excluded"))
    assert counted == -4  # the bug would have made this -3
    # fully itemized: no reconciliation line needed
    assert _line(bd, "FIFA match points") is None
    assert _line(bd, "FIFA adjustment") is None


def test_freekick_goal_itemized_on_top_of_goal():
    # A direct free-kick goal is +1 ON TOP of the goal. MID 90' (+2) + goal (+6)
    # + FK bonus (+1) = 9; FIFA total 9; 20% owned -> no scouting; fully itemized.
    bd = fifa_breakdown({"minutes": 90, "goals": 1, "freekickGoals": 1},
                        position=3, fifa_total=9, percent_selected=20.0)
    assert _line(bd, "Goal scored")["pts"] == 6
    assert _line(bd, "Free-kick goal")["pts"] == 1
    assert _excluded_pts(bd) == 0
    counted = sum(ln["pts"] for ln in bd if not ln.get("excluded"))
    assert counted == 9
    assert _line(bd, "FIFA match points") is None
    assert _line(bd, "FIFA adjustment") is None


# ----- ESPN fallback minutes: never stamp 90 on a mid-match starter -----

class _FakeFeed:
    """Monkeypatch target for _get_json: serves a synthetic scoreboard + summary
    for one LIVE match at minute 50, with one starter subbed off at 30'."""
    def __init__(self):
        self.scoreboard = {
            "events": [{
                "id": "999001",
                "status": {
                    "type": {"name": "STATUS_FIRST_HALF", "state": "in",
                             "completed": False},
                    # 50 minutes elapsed = 3000 seconds
                    "clock": 3000.0, "displayClock": "50'", "period": 2,
                },
                "competitions": [{
                    "competitors": [
                        {"homeAway": "home", "score": "0",
                         "team": {"abbreviation": "AAA", "displayName": "Team A"}},
                        {"homeAway": "away", "score": "0",
                         "team": {"abbreviation": "BBB", "displayName": "Team B"}},
                    ],
                }],
            }],
        }
        self.summary = {
            "keyEvents": [{
                "type": {"type": "substitution"},
                "clock": {"value": 1800.0, "displayValue": "30'"},  # 30 minutes
                "participants": [
                    {"athlete": {"id": "200", "displayName": "Sub On"}},
                    {"athlete": {"id": "101", "displayName": "Early Off"}},
                ],
            }],
            "rosters": [{
                "homeAway": "home",
                "team": {"abbreviation": "AAA"},
                "roster": [
                    {"athlete": {"id": "100", "displayName": "Full Starter"},
                     "starter": True, "subbedIn": False, "subbedOut": False,
                     "stats": [{"name": "appearances", "value": 1.0}]},
                    {"athlete": {"id": "101", "displayName": "Early Off"},
                     "starter": True, "subbedIn": False, "subbedOut": True,
                     "stats": [{"name": "appearances", "value": 1.0}]},
                    {"athlete": {"id": "200", "displayName": "Sub On"},
                     "starter": False, "subbedIn": True, "subbedOut": False,
                     "stats": [{"name": "appearances", "value": 1.0},
                               {"name": "subIns", "value": 1.0}]},
                ],
            }],
        }

    def __call__(self, url, timeout=25):
        return self.scoreboard if "scoreboard" in url else self.summary


def test_espn_live_minutes_not_stamped_90(monkeypatch):
    import fpl_predictor.data.wc_live_ingest as M
    monkeypatch.setattr(M, "_get_json", _FakeFeed())
    _, stats = M.fetch_espn_match_stats("20260614")
    by_name = {s["name"]: s["stats"]["minutes"] for s in stats}
    # The on-pitch starter is capped at the LIVE clock (50), NOT stamped 90.
    assert by_name["Full Starter"] == 50
    # Starter subbed off at 30' gets 30 (the sub-off clock).
    assert by_name["Early Off"] == 30
    # Sub on at 30' has played 50 − 30 = 20 minutes so far.
    assert by_name["Sub On"] == 20
