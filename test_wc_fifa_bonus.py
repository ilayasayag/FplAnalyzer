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
    fifa_breakdown, _excluded_pts, fetch_espn_match_stats, parse_whoscored_match,
    _defcon_actions, _has_defensive_components,
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


# ----- Per-player clean sheet (Phase 3): credited when no goal was conceded
#       WHILE the player was on the pitch, even if his side conceded later -----

def test_clean_sheet_credited_def_subbed_off_before_goal():
    # Ricardo Rodriguez: DEF subbed off at 88', Switzerland conceded at 90'. FIFA
    # awarded the +5 clean sheet. Our parser now sets cleanSheet=True, so the +5
    # is ITEMIZED (not leaked into a reconciliation line). 88' (+2) + clean (+5)
    # = 7; FIFA total 9; 1.5% owned -> scouting 2 (9>6 & <5%). League == 7.
    bd = fifa_breakdown(
        {"minutes": 88, "cleanSheet": True, "goalsConceded": 1},
        position=2, fifa_total=9, percent_selected=1.5)
    cs = _line(bd, "Clean sheet")
    assert cs is not None and cs["pts"] == 5
    # A clean-sheet-credited player is NOT also docked goals conceded.
    assert _line(bd, "Goals conceded") is None
    assert _excluded_pts(bd) == 2
    counted = sum(ln["pts"] for ln in bd if not ln.get("excluded"))
    assert counted == 7  # FIFA 9 − scouting 2; the +5 is itemized, not reconciled
    # Nothing leaked into the catch-all (the clean sheet is now itemized).
    assert _line(bd, "FIFA match points") is None
    assert _line(bd, "FIFA adjustment") is None


def test_no_clean_sheet_def_full_match_concedes_shows_goals_conceded():
    # DEF on the full 90', side conceded 3 -> no clean sheet, "Goals conceded"
    # line of -(3-1) = -2, and NO "Clean sheet" line (regression guard).
    bd = fifa_breakdown(
        {"minutes": 90, "cleanSheet": False, "goalsConceded": 3},
        position=2, fifa_total=99)
    assert _line(bd, "Clean sheet") is None
    gc = _line(bd, "Goals conceded")
    assert gc is not None and gc["pts"] == -2


# ----- parse_whoscored_match: per-player on-pitch clean-sheet window -----

def _ws_player(pid, name, starter=True):
    return {"playerId": pid, "name": name, "isFirstEleven": starter, "stats": {}}


def _make_matchcentre(events):
    """Minimal synthetic WhoScored matchCentre: two home defenders + a token away
    striker, final score 0-1 (away scored once)."""
    return {
        "playerIdNameDictionary": {
            "1": "Off Early", "2": "Full Match", "9": "Away Striker"},
        "maxMinute": 90,
        "ftScore": "0 : 1",
        "home": {"name": "Home", "players": [
            _ws_player(1, "Off Early"), _ws_player(2, "Full Match")]},
        "away": {"name": "Away", "players": [_ws_player(9, "Away Striker")]},
        "events": events,
    }


def _goal_event(pid, minute):
    return {"playerId": pid, "minute": minute,
            "type": {"displayName": "Goal"},
            "outcomeType": {"displayName": "Successful"}, "qualifiers": []}


def _suboff_event(pid, minute):
    return {"playerId": pid, "minute": minute,
            "type": {"displayName": "SubstitutionOff"},
            "outcomeType": {"displayName": "Successful"}, "qualifiers": []}


def test_ws_clean_sheet_window(monkeypatch):
    import fpl_predictor.data.wc_live_ingest as M
    # Home defender #1 subbed off at 88'; away striker #9 scores at 90'. Defender
    # #2 plays the full match. So #1 was OFF when the goal went in (clean sheet),
    # #2 was ON (no clean sheet). Away striker concession lands on the HOME side.
    events = [_suboff_event(1, 88), _goal_event(9, 90)]
    monkeypatch.setattr(M, "_ws_match_centre", lambda mid: _make_matchcentre(events))
    _, rows = M.parse_whoscored_match(123)
    by_name = {r["name"]: r["stats"] for r in rows}
    # Off at 88', goal at 90' -> clean sheet TRUE, charged 0 while on.
    assert by_name["Off Early"]["cleanSheet"] is True
    assert by_name["Off Early"]["concededWhileOn"] == 0
    # Full match, goal at 90' while on -> clean sheet FALSE.
    assert by_name["Full Match"]["cleanSheet"] is False
    assert by_name["Full Match"]["concededWhileOn"] == 1


def test_ws_clean_sheet_window_early_goal(monkeypatch):
    import fpl_predictor.data.wc_live_ingest as M
    # Goal at 70' (mid-match). Defender #1 off at 88' was ON at 70' (no clean
    # sheet); defender #2 full match also ON at 70' (no clean sheet).
    events = [_suboff_event(1, 88), _goal_event(9, 70)]
    monkeypatch.setattr(M, "_ws_match_centre", lambda mid: _make_matchcentre(events))
    _, rows = M.parse_whoscored_match(123)
    by_name = {r["name"]: r["stats"] for r in rows}
    assert by_name["Off Early"]["cleanSheet"] is False
    assert by_name["Full Match"]["cleanSheet"] is False


def test_ws_own_goal_counts_against_own_side(monkeypatch):
    import fpl_predictor.data.wc_live_ingest as M
    # Home defender #2 scores an OWN goal at 50' -> a HOME concession. Both home
    # defenders are on the pitch at 50' (no clean sheet for either). The away
    # striker, on the whole match, conceded nothing -> clean sheet.
    og = {"playerId": 2, "minute": 50, "type": {"displayName": "Goal"},
          "outcomeType": {"displayName": "Successful"},
          "qualifiers": [{"type": {"displayName": "OwnGoal"}}]}
    monkeypatch.setattr(M, "_ws_match_centre",
                        lambda mid: _make_matchcentre([og]))
    _, rows = M.parse_whoscored_match(123)
    by_name = {r["name"]: r["stats"] for r in rows}
    assert by_name["Off Early"]["cleanSheet"] is False      # home side conceded
    assert by_name["Full Match"]["cleanSheet"] is False
    assert by_name["Away Striker"]["cleanSheet"] is True     # away conceded nothing


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


# ----- DefCon by position (Phase 5): ball recoveries count for MID only -----

# A stat line with CBIT=8 (tk3 + int2 + clr2 + blk1) and 4 ball recoveries.
# CBITR = 12. DEF must see 8 (no recoveries); MID must see 12.
_DEFCON_STATS = {
    "minutes": 90,
    "tackles": {"total": 3, "interceptions": 2, "blocks": 1},
    "clearances": 2,
    "ballRecoveries": 4,
    "defCon": 12,  # stale precomputed CBITR — must NOT be used by the helper
}


def test_defcon_actions_def_excludes_ball_recoveries():
    # DEF: CBIT only = 3+2+2+1 = 8 (ball recoveries NOT counted).
    assert _defcon_actions(_DEFCON_STATS, 2) == 8


def test_defcon_actions_mid_includes_ball_recoveries():
    # MID: CBITR = 8 + 4 = 12 (ball recoveries counted).
    assert _defcon_actions(_DEFCON_STATS, 3) == 12


def test_defcon_actions_none_for_gk_fwd():
    assert _defcon_actions(_DEFCON_STATS, 1) is None
    assert _defcon_actions(_DEFCON_STATS, 4) is None


def test_def_at_threshold_10_no_bonus_mid_at_12_earns():
    # DEF threshold 10: CBIT=8 < 10 -> NO bonus.
    actions_def = _defcon_actions(_DEFCON_STATS, 2)
    assert actions_def == 8 and (2 if actions_def >= 10 else 0) == 0
    # MID threshold 12: CBITR=12 >= 12 -> +2.
    actions_mid = _defcon_actions(_DEFCON_STATS, 3)
    assert actions_mid == 12 and (2 if actions_mid >= 12 else 0) == 2


def test_has_defensive_components():
    # WhoScored line carries a tackles dict -> True.
    assert _has_defensive_components(_DEFCON_STATS) is True
    assert _has_defensive_components({"ballRecoveries": 0}) is True
    assert _has_defensive_components({"defCon": 0}) is True
    # ESPN-style line (goals/assists/minutes only) -> False, so DefCon is preserved.
    assert _has_defensive_components({"minutes": 90, "goals": 1, "assists": 0}) is False
    assert _has_defensive_components({}) is False


def _rebuild_defcon(stats, pos, fifa_total, own, fifa_pos,
                    thr_def=10, thr_mid=12, defcon_pts=2):
    """Mirror recompute_all_scores's per-doc re-derive: FIFA breakdown + a
    position-correct DefCon line rebuilt from STORED components. Returns
    (breakdown, defcon_bonus, defcon_actions, fantasy_points)."""
    nbd = fifa_breakdown(stats, pos, fifa_total, own, fifa_position=fifa_pos)
    actions = _defcon_actions(stats, pos)
    thr = thr_def if pos == 2 else (thr_mid if pos == 3 else None)
    if thr is not None and actions is not None:
        dcb = defcon_pts if actions >= thr else 0
        nbd.append({"label": f"Defensive contribution ({actions}/{thr})",
                    "value": actions, "pts": dcb})
    else:
        dcb, actions = 0, None
    nb = _excluded_pts(nbd)
    nfp = fifa_total + dcb - nb
    return nbd, dcb, actions, nfp


def test_recompute_rederives_def_from_cbitr_to_cbit():
    # A stored DEF doc whose OLD bonus was based on CBITR (12 >= 10 -> +2). On
    # re-sync, DefCon is re-derived from stored components as CBIT (8 < 10 -> 0):
    # the bonus is REMOVED. FIFA total 5 (90' +2, the rest reconciled), 20% owned
    # (no scouting). New total must equal FIFA + DefCon − scouting = 5 + 0 − 0 = 5.
    bd, dcb, actions, nfp = _rebuild_defcon(
        _DEFCON_STATS, pos=2, fifa_total=5, own=20.0, fifa_pos=2)
    assert actions == 8           # CBIT, not the stale CBITR 12
    assert dcb == 0               # bonus removed (8 < 10)
    dl = _line(bd, "Defensive contribution (8/10)")
    assert dl is not None and dl["pts"] == 0
    # HARD INVARIANT: total == FIFA + DefCon − scouting.
    assert nfp == 5 + dcb - _excluded_pts(bd)
    assert nfp == 5


def test_recompute_mid_keeps_cbitr_bonus():
    # Same stats as a MID: CBITR=12 >= 12 -> +2 retained. FIFA 5, 20% owned.
    # total = 5 + 2 − 0 = 7.
    bd, dcb, actions, nfp = _rebuild_defcon(
        _DEFCON_STATS, pos=3, fifa_total=5, own=20.0, fifa_pos=3)
    assert actions == 12 and dcb == 2
    assert nfp == 5 + 2 - _excluded_pts(bd)
    assert nfp == 7
