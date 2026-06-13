#!/usr/bin/env python3
"""The league does NOT count FIFA's scouting/extras bonus.

fifa_breakdown reconciles our itemized lines to FIFA's authoritative total with a
"FIFA bonus (scouting / extras)" remainder line. That line is flagged
``excluded`` and subtracted from fantasyPoints (shown in red on the breakdown for
transparency). e.g. Folarin Balogun: FIFA 15, bonus 4 -> our league 11.

Run:  .venv/bin/python -m pytest test_wc_fifa_bonus.py -q
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.data.wc_live_ingest import fifa_breakdown, _excluded_pts  # noqa: E402


# Balogun: FWD, 90', 2 goals, 3 shots on target. FIFA's published total is 15.
BALOGUN_STATS = {"minutes": 90, "goals": 2, "shotsOnTarget": 3, "cleanSheet": False}
BALOGUN_FIFA_TOTAL = 15


def test_bonus_line_is_flagged_excluded():
    bd = fifa_breakdown(BALOGUN_STATS, position=4, fifa_total=BALOGUN_FIFA_TOTAL)
    bonus = [ln for ln in bd if ln.get("excluded")]
    assert len(bonus) == 1
    assert bonus[0]["label"].startswith("FIFA bonus")
    # known = 2 (mins) + 8 (2 goals x4) + 1 (3 SoT // 2) = 11; remainder 4.
    assert bonus[0]["pts"] == 4


def test_excluded_pts_extracts_the_bonus():
    bd = fifa_breakdown(BALOGUN_STATS, position=4, fifa_total=BALOGUN_FIFA_TOTAL)
    assert _excluded_pts(bd) == 4


def test_our_total_excludes_bonus():
    bd = fifa_breakdown(BALOGUN_STATS, position=4, fifa_total=BALOGUN_FIFA_TOTAL)
    defcon_bonus = 0
    our_total = BALOGUN_FIFA_TOTAL + defcon_bonus - _excluded_pts(bd)
    assert our_total == 11  # the league figure the user asked for


def test_no_bonus_line_when_total_matches_known():
    # A player whose FIFA total equals our itemized sum has no remainder.
    stats = {"minutes": 90}  # known = 2, FIFA total 2
    bd = fifa_breakdown(stats, position=3, fifa_total=2)
    assert _excluded_pts(bd) == 0
    assert not any(ln.get("excluded") for ln in bd)


def test_defcon_line_is_not_excluded():
    # The DefCon line is appended by the scorer (not fifa_breakdown) and must be
    # counted — only the FIFA bonus line carries the excluded flag.
    bd = fifa_breakdown(BALOGUN_STATS, position=4, fifa_total=BALOGUN_FIFA_TOTAL)
    bd.append({"label": "Defensive contribution (11/10)", "value": 11, "pts": 2})
    assert _excluded_pts(bd) == 4  # only the FIFA bonus, DefCon stays counted
