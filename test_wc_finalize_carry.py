#!/usr/bin/env python3
"""finalize_gw carry-forward: a manager who didn't set a lineup for the GW is
scored on their most recent prior GW's XI (not skipped to 0)."""
import os, sys
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import test_helpers as H  # noqa: E402
from fpl_predictor.game.wc_scoring import _carry_forward_lineup  # noqa: E402


def _lref():
    db = H.FakeDB()
    lref = db.collection("leagues").document("L")
    return lref


def test_carry_forward_uses_previous_gw():
    lref = _lref()
    lref.collection("lineups").document("u1_1").set(
        {"starting": [1, 2, 3], "bench": [4], "formation": [1, 4, 3, 3], "captain": 1})
    cf = _carry_forward_lineup(lref, "u1", 2)
    assert cf is not None
    assert cf["starting"] == [1, 2, 3] and cf["bench"] == [4]
    assert cf["formation"] == [1, 4, 3, 3] and cf["fromGw"] == 1


def test_carry_forward_walks_back_over_gaps():
    lref = _lref()
    lref.collection("lineups").document("u1_1").set(
        {"starting": [1, 2], "bench": [9], "formation": [1, 4, 3, 3]})
    # gw2 AND gw3 missing → gw3's carry-forward still resolves to gw1
    assert _carry_forward_lineup(lref, "u1", 3)["fromGw"] == 1


def test_carry_forward_none_when_never_set():
    lref = _lref()
    assert _carry_forward_lineup(lref, "u_never", 2) is None
