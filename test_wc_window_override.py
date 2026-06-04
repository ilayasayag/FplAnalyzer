#!/usr/bin/env python3
"""Unit tests for the admin transfer-window OVERRIDE in ``current_window``.

These are PURE unit tests — no Firestore emulator needed. They verify that a
``windowOverride`` on the league doc short-circuits the time-based logic, that
an invalid override falls through, and that a missing override is identical to
the existing fixture-clock behaviour.

Run:
    .venv/bin/python -m pytest test_wc_window_override.py -q
"""

import os
import sys
from datetime import datetime, timedelta, timezone

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_windows import (  # noqa: E402
    TransferWindow,
    current_window,
)


def _fx(kickoff: datetime, gw: int = 2):
    return {"kickoff": kickoff, "gw": gw}


def _utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


PREV_KO = _utc(2026, 6, 16, 12, 0)
T0 = _utc(2026, 6, 17, 12, 0)
PREV_FX = [_fx(PREV_KO, gw=1)]
UP_FX = [_fx(T0, gw=2)]
CONFIG = {"trade_window_hours": 5, "free_agent_window_hours": 5,
          "match_duration_minutes": 150}

# A `now` deep inside the mid-GW dead zone (well before the trade window opens)
# so the time-based logic would return NONE — proving the override wins.
NOW_DEAD = _utc(2026, 6, 16, 0, 0)


# ---------------------------------------------------------------------------
# (a) each of the 4 phases is forced regardless of fixtures / now
# ---------------------------------------------------------------------------

def test_override_forces_each_phase():
    for phase in ("none", "trade", "free_agents", "next_gw_bid"):
        league = {"currentGw": 2, "windowOverride": {"phase": phase}}
        win, gw = current_window(
            league_doc=league,
            fixtures_for_gw=UP_FX,
            config=CONFIG,
            now=NOW_DEAD,
            prev_fixtures=PREV_FX,
            upcoming_gw=2,
        )
        assert win == TransferWindow(phase), phase
        assert gw == 2


def test_override_force_open_when_clock_says_closed():
    # now is at/after T0 -> time-based would be NONE (locked). Override opens it.
    league = {"currentGw": 2, "windowOverride": {"phase": "trade"}}
    win, gw = current_window(
        league_doc=league,
        fixtures_for_gw=UP_FX,
        config=CONFIG,
        now=T0 + timedelta(hours=1),
        prev_fixtures=PREV_FX,
        upcoming_gw=2,
    )
    assert win == TransferWindow.TRADE


# ---------------------------------------------------------------------------
# (b) invalid phase string falls through to time-based
# ---------------------------------------------------------------------------

def test_invalid_phase_falls_through():
    league = {"currentGw": 2, "windowOverride": {"phase": "bogus"}}
    # NOW_DEAD is before trade_open -> time-based result is NONE.
    win, gw = current_window(
        league_doc=league,
        fixtures_for_gw=UP_FX,
        config=CONFIG,
        now=NOW_DEAD,
        prev_fixtures=PREV_FX,
        upcoming_gw=2,
    )
    assert win == TransferWindow.NONE
    assert gw == 2


def test_empty_phase_falls_through():
    league = {"currentGw": 2, "windowOverride": {"phase": ""}}
    win, _ = current_window(
        league_doc=league,
        fixtures_for_gw=UP_FX,
        config=CONFIG,
        now=NOW_DEAD,
        prev_fixtures=PREV_FX,
        upcoming_gw=2,
    )
    assert win == TransferWindow.NONE


# ---------------------------------------------------------------------------
# (c) no override -> identical to existing time-based behaviour
# ---------------------------------------------------------------------------

def test_no_override_identical_to_time_based():
    kwargs = dict(
        fixtures_for_gw=UP_FX,
        config=CONFIG,
        prev_fixtures=PREV_FX,
        upcoming_gw=2,
    )
    tprev_end = PREV_KO + timedelta(minutes=150)  # 14:30 day1
    # Sample several instants across the timeline and confirm with/without an
    # absent override key produces the same result as a plain league doc.
    samples = [
        NOW_DEAD,                       # NONE (before trade_open)
        tprev_end + timedelta(hours=1),  # TRADE
        tprev_end + timedelta(hours=6),  # FREE_AGENTS
        tprev_end + timedelta(hours=11),  # NEXT_GW_BID (still before T0)
        T0 + timedelta(hours=1),        # NONE (locked)
    ]
    for now in samples:
        baseline_win, baseline_gw = current_window(
            league_doc={"currentGw": 2}, now=now, **kwargs)
        # An override that is not a dict / missing must be ignored.
        for doc in ({"currentGw": 2},
                    {"currentGw": 2, "windowOverride": None},
                    {"currentGw": 2, "windowOverride": "nope"},
                    {"currentGw": 2, "windowOverride": {}}):
            win, gw = current_window(league_doc=doc, now=now, **kwargs)
            assert win == baseline_win, (now, doc)
            assert gw == baseline_gw, (now, doc)


# ---------------------------------------------------------------------------
# (d) override gw honored, defaults to upcoming_gw when absent
# ---------------------------------------------------------------------------

def test_override_gw_honored():
    league = {"currentGw": 2, "windowOverride": {"phase": "trade", "gw": 7}}
    win, gw = current_window(
        league_doc=league,
        fixtures_for_gw=UP_FX,
        config=CONFIG,
        now=NOW_DEAD,
        prev_fixtures=PREV_FX,
        upcoming_gw=2,
    )
    assert win == TransferWindow.TRADE
    assert gw == 7


def test_override_gw_defaults_to_upcoming():
    league = {"currentGw": 2, "windowOverride": {"phase": "free_agents"}}
    win, gw = current_window(
        league_doc=league,
        fixtures_for_gw=UP_FX,
        config=CONFIG,
        now=NOW_DEAD,
        prev_fixtures=PREV_FX,
        upcoming_gw=4,
    )
    assert win == TransferWindow.FREE_AGENTS
    assert gw == 4
