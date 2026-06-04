#!/usr/bin/env python3
"""Unit tests for the WC 2026 transfer-window state machine (wc_windows.py).

These are PURE unit tests — no Firestore emulator needed. They exercise
``current_window`` / ``compute_window_boundaries`` directly with synthetic
fixture dicts, plus the rewired ``is_transfer_window_open`` wrapper.

Run:
    .venv/bin/python -m pytest test_wc_windows.py -q

Acceptance criteria covered (WC2026_WINDOWS_DESIGN.md §8 PR 2):
  * the three windows occur in order and exactly one (or NONE) is open;
  * GW1's window opens (off-by-one regression);
  * short-turnaround guard: when Tprev_end + trade_h + fa_h > T0, windows
    compress and none closes after T0;
  * boundary instants (exactly at open/close).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_windows import (  # noqa: E402
    DEFAULT_FREE_AGENT_WINDOW_HOURS,
    DEFAULT_MATCH_DURATION_MINUTES,
    DEFAULT_TRADE_WINDOW_HOURS,
    TransferWindow,
    compute_window_boundaries,
    current_window,
    resolve_durations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fx(kickoff: datetime, gw: int = 2):
    return {"kickoff": kickoff, "gw": gw}


def _utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


# A comfortable scenario: previous GW last kickoff far enough before T0 that
# the full 5h + 5h windows fit with NEXT_GW_BID time to spare.
#   prev last kickoff = day1 12:00 -> Tprev_end = 14:30 (+150min)
#   upcoming first kickoff (T0)    = day2 12:00
PREV_KO = _utc(2026, 6, 16, 12, 0)
T0 = _utc(2026, 6, 17, 12, 0)
PREV_FX = [_fx(PREV_KO, gw=1), _fx(_utc(2026, 6, 16, 9, 0), gw=1)]
UP_FX = [_fx(T0, gw=2), _fx(_utc(2026, 6, 17, 18, 0), gw=2)]
CONFIG = {"trade_window_hours": 5, "free_agent_window_hours": 5,
          "match_duration_minutes": 150}


def _tprev_end():
    return PREV_KO + timedelta(minutes=150)


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

def test_resolve_durations_defaults_when_empty():
    trade_h, fa_h, match_min = resolve_durations(None)
    assert trade_h == DEFAULT_TRADE_WINDOW_HOURS == 5
    assert fa_h == DEFAULT_FREE_AGENT_WINDOW_HOURS == 5
    assert match_min == DEFAULT_MATCH_DURATION_MINUTES == 150


def test_resolve_durations_reads_config():
    trade_h, fa_h, match_min = resolve_durations(
        {"trade_window_hours": 3, "free_agent_window_hours": 2,
         "match_duration_minutes": 120})
    assert (trade_h, fa_h, match_min) == (3.0, 2.0, 120.0)


# ---------------------------------------------------------------------------
# Ordering / exactly-one-open
# ---------------------------------------------------------------------------

def _win(now):
    w, gw = current_window(None, UP_FX, CONFIG, now=now,
                           prev_fixtures=PREV_FX, upcoming_gw=2)
    return w, gw


def test_windows_occur_in_order_and_exactly_one_open():
    tprev = _tprev_end()                       # 14:30 day1
    trade_close = tprev + timedelta(hours=5)   # 19:30 day1
    fa_close = trade_close + timedelta(hours=5)  # 00:30 day2

    # Before Tprev_end -> NONE
    assert _win(tprev - timedelta(minutes=1))[0] == TransferWindow.NONE
    # In TRADE
    assert _win(tprev + timedelta(hours=1))[0] == TransferWindow.TRADE
    # In FREE_AGENTS
    assert _win(trade_close + timedelta(hours=1))[0] == TransferWindow.FREE_AGENTS
    # In NEXT_GW_BID
    assert _win(fa_close + timedelta(hours=1))[0] == TransferWindow.NEXT_GW_BID
    # At/after T0 (lock) -> NONE
    assert _win(T0)[0] == TransferWindow.NONE
    assert _win(T0 + timedelta(hours=1))[0] == TransferWindow.NONE


def test_returns_upcoming_gw():
    w, gw = _win(_tprev_end() + timedelta(hours=1))
    assert gw == 2


def test_only_one_window_active_across_a_sweep():
    """Sweep every 10 minutes across the runway; never two phases at once
    (trivially true since current_window returns a single value, but this also
    asserts the *sequence* is monotonic: NONE -> TRADE -> FREE_AGENTS ->
    NEXT_GW_BID -> NONE with no regressions)."""
    order = [TransferWindow.NONE, TransferWindow.TRADE, TransferWindow.FREE_AGENTS,
             TransferWindow.NEXT_GW_BID, TransferWindow.NONE]
    seen_idx = 0
    t = _tprev_end() - timedelta(hours=2)
    end = T0 + timedelta(hours=1)
    while t <= end:
        w = _win(t)[0]
        # find w in order at or after current position
        idx = order.index(w, seen_idx) if w in order[seen_idx:] else order.index(w)
        assert idx >= seen_idx, f"phase regressed to {w} at {t}"
        seen_idx = idx
        t += timedelta(minutes=10)
    assert seen_idx == len(order) - 1  # ended back at NONE


# ---------------------------------------------------------------------------
# Boundary instants (half-open intervals: open inclusive, close exclusive)
# ---------------------------------------------------------------------------

def test_boundaries_exact_instants():
    bounds = compute_window_boundaries(PREV_FX, UP_FX, CONFIG)
    assert bounds["trade_open"] == _tprev_end()
    assert bounds["trade_close"] == _tprev_end() + timedelta(hours=5)
    assert bounds["fa_close"] == _tprev_end() + timedelta(hours=10)
    assert bounds["t0"] == T0

    # Exactly at trade_open -> TRADE (inclusive)
    assert _win(bounds["trade_open"])[0] == TransferWindow.TRADE
    # Exactly at trade_close -> FREE_AGENTS (close exclusive)
    assert _win(bounds["trade_close"])[0] == TransferWindow.FREE_AGENTS
    # Exactly at fa_close -> NEXT_GW_BID
    assert _win(bounds["fa_close"])[0] == TransferWindow.NEXT_GW_BID
    # Exactly at T0 -> NONE (lock, exclusive)
    assert _win(bounds["t0"])[0] == TransferWindow.NONE


# ---------------------------------------------------------------------------
# GW1 off-by-one regression
# ---------------------------------------------------------------------------

def test_gw1_window_opens_no_prev_fixtures():
    """GW1 has no previous GW. The window must still open before GW1's lock."""
    t0 = _utc(2026, 6, 11, 17, 0)  # GW1 lockAt from the calendar
    up = [_fx(t0, gw=1)]
    # With no prev fixtures, trade_open = T0 - (5+5)h = 07:00.
    just_after_open = t0 - timedelta(hours=10) + timedelta(minutes=1)
    w, gw = current_window(None, up, CONFIG, now=just_after_open,
                           prev_fixtures=None, upcoming_gw=1)
    assert w == TransferWindow.TRADE
    assert gw == 1


def test_is_transfer_window_open_gw1_regression():
    """The rewired wrapper: GW1's window (passed as gw=0 by callers) must open.

    Old behavior returned False for gw=0 forever. Now it delegates to
    current_window for upcoming GW1.
    """
    from fpl_predictor.game.wc_gameweeks import is_transfer_window_open, get_lock_time

    t0 = get_lock_time(1)  # GW1 lockAt
    # 1 hour before lock -> some window must be open (NEXT_GW_BID by then).
    assert is_transfer_window_open(0, now=t0 - timedelta(hours=1)) is True
    # After lock -> closed.
    assert is_transfer_window_open(0, now=t0 + timedelta(hours=1)) is False
    # Long before any window -> closed.
    assert is_transfer_window_open(0, now=t0 - timedelta(days=2)) is False


def test_is_transfer_window_open_matches_current_window_for_gw2():
    from fpl_predictor.game.wc_gameweeks import is_transfer_window_open, get_lock_time

    t0_gw2 = get_lock_time(2)
    # 30 min before GW2 lock -> a window is open.
    assert is_transfer_window_open(1, now=t0_gw2 - timedelta(minutes=30)) is True
    # After GW2 lock -> closed.
    assert is_transfer_window_open(1, now=t0_gw2 + timedelta(minutes=1)) is False


# ---------------------------------------------------------------------------
# Short-turnaround guard
# ---------------------------------------------------------------------------

def test_short_turnaround_compresses_and_never_overruns_t0():
    """gap < trade_h + fa_h: both windows scale proportionally, fa_close <= T0,
    and NEXT_GW_BID gets the remainder (here zero)."""
    prev_ko = _utc(2026, 6, 16, 12, 0)        # Tprev_end = 14:30
    t0 = prev_ko + timedelta(minutes=150) + timedelta(hours=4)  # gap = 4h < 10h
    prev = [_fx(prev_ko, gw=1)]
    up = [_fx(t0, gw=2)]

    bounds = compute_window_boundaries(prev, up, CONFIG)
    tprev_end = prev_ko + timedelta(minutes=150)
    gap = (t0 - tprev_end).total_seconds()
    assert abs(gap - 4 * 3600) < 1

    # trade:fa ratio stays 5:5 = 1:1, each gets 2h, summing to the 4h gap.
    assert abs((bounds["trade_close"] - bounds["trade_open"]).total_seconds()
               - 2 * 3600) < 1
    assert abs((bounds["fa_close"] - bounds["trade_close"]).total_seconds()
               - 2 * 3600) < 1
    # No window closes after T0; NEXT_GW_BID window is zero-length here.
    assert bounds["fa_close"] <= bounds["t0"]
    assert bounds["fa_close"] == bounds["t0"]

    # Phases still ordered & none open after T0.
    def win(now):
        return current_window(None, up, CONFIG, now=now, prev_fixtures=prev,
                              upcoming_gw=2)[0]

    assert win(tprev_end + timedelta(minutes=30)) == TransferWindow.TRADE
    assert win(bounds["trade_close"] + timedelta(minutes=30)) == TransferWindow.FREE_AGENTS
    assert win(t0) == TransferWindow.NONE
    assert win(t0 + timedelta(minutes=1)) == TransferWindow.NONE


def test_zero_gap_turnaround_no_window_opens():
    """If Tprev_end >= T0 (lock already passed / overlap), nothing opens."""
    prev_ko = _utc(2026, 6, 16, 12, 0)         # Tprev_end = 14:30
    t0 = prev_ko + timedelta(minutes=150)       # gap = 0
    prev = [_fx(prev_ko, gw=1)]
    up = [_fx(t0, gw=2)]
    bounds = compute_window_boundaries(prev, up, CONFIG)
    assert bounds["trade_open"] == bounds["t0"]
    # At exactly T0, lock is hit -> NONE.
    w = current_window(None, up, CONFIG, now=t0, prev_fixtures=prev,
                       upcoming_gw=2)[0]
    assert w == TransferWindow.NONE


def test_proportional_scaling_uneven_durations():
    """Uneven trade/fa hours scale by the same factor, preserving the ratio."""
    cfg = {"trade_window_hours": 6, "free_agent_window_hours": 2,
           "match_duration_minutes": 150}
    prev_ko = _utc(2026, 6, 16, 12, 0)
    tprev_end = prev_ko + timedelta(minutes=150)
    t0 = tprev_end + timedelta(hours=4)   # gap 4h vs requested 8h -> scale 0.5
    prev = [_fx(prev_ko, gw=1)]
    up = [_fx(t0, gw=2)]
    bounds = compute_window_boundaries(prev, up, cfg)
    assert abs((bounds["trade_close"] - bounds["trade_open"]).total_seconds()
               - 3 * 3600) < 1   # 6h * 0.5
    assert abs((bounds["fa_close"] - bounds["trade_close"]).total_seconds()
               - 1 * 3600) < 1   # 2h * 0.5
    assert bounds["fa_close"] <= bounds["t0"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_no_upcoming_fixtures_returns_none():
    w, gw = current_window(None, [], CONFIG, now=_utc(2026, 6, 16, 12, 0),
                           prev_fixtures=PREV_FX, upcoming_gw=2)
    assert w == TransferWindow.NONE


def test_naive_now_is_treated_as_utc():
    naive_now = datetime(2026, 6, 16, 15, 30)  # within TRADE (14:30-19:30)
    w = current_window(None, UP_FX, CONFIG, now=naive_now,
                       prev_fixtures=PREV_FX, upcoming_gw=2)[0]
    assert w == TransferWindow.TRADE


def test_iso_string_kickoffs_supported():
    up = [{"kickoff": "2026-06-17T12:00:00Z", "gw": 2}]
    prev = [{"kickoff": "2026-06-16T12:00:00+00:00", "gw": 1}]
    bounds = compute_window_boundaries(prev, up, CONFIG)
    assert bounds["t0"] == T0
    assert bounds["trade_open"] == _tprev_end()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
