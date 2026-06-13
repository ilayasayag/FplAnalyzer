#!/usr/bin/env python3
"""Unit tests for the WC 2026 transfer-window state machine (wc_windows.py).

T0-anchored timeline (T0 = the upcoming GW's first kickoff), per the league spec:

  * OFFER-TRADES (NEXT_GW_BID): T0 .. (this GW's last match end + reopen_h).
    The GW is live — managers may offer trades + edit their bid-wishlist, but
    squads are frozen.
  * TRADE: (prev GW last match end + reopen_h) .. (T0 - fa_open_before_h).
    Execute manager↔manager trades; squads change.
  * FREE_AGENTS: (T0 - fa_open_before_h) .. (T0 - squad_lock_before_h).
    Free-agent pickups (+ the wishlist/waiver draft runs when this opens).
  * NONE (locked): (T0 - squad_lock_before_h) .. T0. Squads + XI locked.

Defaults: fa_open_before = 5h, squad_lock_before = 1h, reopen_after = 1h,
match_duration = 150 min.

Run:  .venv/bin/python -m pytest test_wc_windows.py -q
"""

import os
import sys
from datetime import datetime, timedelta, timezone

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_windows import (  # noqa: E402
    DEFAULT_FA_OPEN_BEFORE_HOURS,
    DEFAULT_MATCH_DURATION_MINUTES,
    DEFAULT_SQUAD_LOCK_BEFORE_HOURS,
    DEFAULT_TRADE_REOPEN_AFTER_HOURS,
    TransferWindow,
    compute_window_boundaries,
    current_window,
    resolve_durations,
)


def _fx(kickoff, gw=2):
    return {"kickoff": kickoff, "gw": gw}


def _utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


# Scenario:
#   prev GW last kickoff = 16 Jun 12:00 -> end 14:30 -> trade reopens 15:30 (16 Jun)
#   upcoming GW: first kickoff (T0) = 17 Jun 12:00, last kickoff = 17 Jun 18:00
#                -> offer_close = 18:00 + 2:30 + 1:00 = 21:30 (17 Jun)
#   fa_open    = T0 - 5h = 07:00 (17 Jun);  squad_lock = T0 - 1h = 11:00 (17 Jun)
PREV_KO = _utc(2026, 6, 16, 12, 0)
T0 = _utc(2026, 6, 17, 12, 0)
UP_LAST = _utc(2026, 6, 17, 18, 0)
PREV_FX = [_fx(PREV_KO, gw=1), _fx(_utc(2026, 6, 16, 9, 0), gw=1)]
UP_FX = [_fx(T0, gw=2), _fx(UP_LAST, gw=2)]
CONFIG = {"fa_open_before_hours": 5, "squad_lock_before_hours": 1,
          "trade_reopen_after_hours": 1, "match_duration_minutes": 150}


def _win(now):
    return current_window(None, UP_FX, CONFIG, now=now,
                          prev_fixtures=PREV_FX, upcoming_gw=2)[0]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_resolve_durations_defaults_when_empty():
    fa, sq, re_, mm = resolve_durations(None)
    assert (fa, sq, re_, mm) == (5.0, 1.0, 1.0, 150.0)
    assert DEFAULT_FA_OPEN_BEFORE_HOURS == 5
    assert DEFAULT_SQUAD_LOCK_BEFORE_HOURS == 1
    assert DEFAULT_TRADE_REOPEN_AFTER_HOURS == 1
    assert DEFAULT_MATCH_DURATION_MINUTES == 150


def test_resolve_durations_reads_config():
    assert resolve_durations({
        "fa_open_before_hours": 6, "squad_lock_before_hours": 2,
        "trade_reopen_after_hours": 3, "match_duration_minutes": 120,
    }) == (6.0, 2.0, 3.0, 120.0)


# ---------------------------------------------------------------------------
# Boundary instants
# ---------------------------------------------------------------------------

def test_boundaries_exact_instants():
    b = compute_window_boundaries(PREV_FX, UP_FX, CONFIG)
    assert b["t0"] == T0
    assert b["fa_open"] == T0 - timedelta(hours=5)        # 17 Jun 07:00
    assert b["squad_lock"] == T0 - timedelta(hours=1)     # 17 Jun 11:00
    assert b["trade_open"] == PREV_KO + timedelta(minutes=150) + timedelta(hours=1)  # 16 Jun 15:30
    assert b["offer_close"] == UP_LAST + timedelta(minutes=150) + timedelta(hours=1)  # 17 Jun 21:30


# ---------------------------------------------------------------------------
# Pre-GW phase sequence (NEXT_GW_BID tail -> TRADE -> FREE_AGENTS -> NONE)
# ---------------------------------------------------------------------------

def test_pre_gw_phase_sequence():
    b = compute_window_boundaries(PREV_FX, UP_FX, CONFIG)
    # before trade reopens = still the previous GW's offer-trades tail
    assert _win(b["trade_open"] - timedelta(minutes=1)) == TransferWindow.NEXT_GW_BID
    # trade window
    assert _win(b["trade_open"]) == TransferWindow.TRADE
    assert _win(b["fa_open"] - timedelta(minutes=1)) == TransferWindow.TRADE
    # free-agent window
    assert _win(b["fa_open"]) == TransferWindow.FREE_AGENTS
    assert _win(b["squad_lock"] - timedelta(minutes=1)) == TransferWindow.FREE_AGENTS
    # locked
    assert _win(b["squad_lock"]) == TransferWindow.NONE
    assert _win(T0 - timedelta(minutes=1)) == TransferWindow.NONE


# ---------------------------------------------------------------------------
# Live GW: OFFER-TRADES, then trades reopen after the GW ends
# ---------------------------------------------------------------------------

def test_live_gw_offer_then_trade_reopen():
    b = compute_window_boundaries(PREV_FX, UP_FX, CONFIG)
    assert _win(T0) == TransferWindow.NEXT_GW_BID                       # at first kickoff
    assert _win(b["offer_close"] - timedelta(minutes=1)) == TransferWindow.NEXT_GW_BID
    assert _win(b["offer_close"]) == TransferWindow.TRADE              # trades reopen
    assert _win(b["offer_close"] + timedelta(hours=2)) == TransferWindow.TRADE


def test_returns_upcoming_gw():
    _, gw = current_window(None, UP_FX, CONFIG, now=T0 - timedelta(hours=3),
                           prev_fixtures=PREV_FX, upcoming_gw=2)
    assert gw == 2


# ---------------------------------------------------------------------------
# GW1 (no previous GW): trades open from the start until the FA window
# ---------------------------------------------------------------------------

def test_gw1_no_prev_trade_open_from_start():
    up = [_fx(T0, gw=1)]
    b = compute_window_boundaries(None, up, CONFIG)
    assert b["trade_open"] is None

    def win(now):
        return current_window(None, up, CONFIG, now=now,
                              prev_fixtures=None, upcoming_gw=1)[0]

    assert win(T0 - timedelta(hours=8)) == TransferWindow.TRADE          # well before
    assert win(T0 - timedelta(hours=3)) == TransferWindow.FREE_AGENTS    # in FA window
    assert win(T0 - timedelta(minutes=30)) == TransferWindow.NONE        # locked
    assert win(T0) == TransferWindow.NEXT_GW_BID                         # live (offer)


# ---------------------------------------------------------------------------
# Guards / edges
# ---------------------------------------------------------------------------

def test_fa_open_never_after_squad_lock():
    b = compute_window_boundaries(None, [_fx(T0)], CONFIG)
    assert b["fa_open"] <= b["squad_lock"] <= b["t0"]


def test_no_upcoming_fixtures_returns_none():
    w, _ = current_window(None, [], CONFIG, now=T0,
                          prev_fixtures=PREV_FX, upcoming_gw=2)
    assert w == TransferWindow.NONE


def test_naive_now_is_treated_as_utc():
    naive = datetime(2026, 6, 16, 20, 0)  # within TRADE (15:30 16Jun .. 07:00 17Jun)
    w = current_window(None, UP_FX, CONFIG, now=naive,
                       prev_fixtures=PREV_FX, upcoming_gw=2)[0]
    assert w == TransferWindow.TRADE


def test_iso_string_kickoffs_supported():
    up = [{"kickoff": "2026-06-17T12:00:00Z", "gw": 2}]
    prev = [{"kickoff": "2026-06-16T12:00:00+00:00", "gw": 1}]
    b = compute_window_boundaries(prev, up, CONFIG)
    assert b["t0"] == T0
    assert b["trade_open"] == _utc(2026, 6, 16, 12, 0) + timedelta(minutes=150) + timedelta(hours=1)


# ---------------------------------------------------------------------------
# is_transfer_window_open wrapper (delegates to current_window via the calendar)
# ---------------------------------------------------------------------------

def test_is_transfer_window_open_wrapper():
    from fpl_predictor.game.wc_gameweeks import is_transfer_window_open, get_lock_time

    t0 = get_lock_time(2)  # GW2 lockAt = T0
    # In the FA window (T0-5h .. T0-1h) -> open.
    assert is_transfer_window_open(1, now=t0 - timedelta(hours=3)) is True
    # In the locked hour (T0-1h .. T0) -> closed.
    assert is_transfer_window_open(1, now=t0 - timedelta(minutes=30)) is False
    # Live GW just after kickoff -> OFFER window open.
    assert is_transfer_window_open(1, now=t0 + timedelta(minutes=30)) is True


def test_is_transfer_window_open_gw1():
    from fpl_predictor.game.wc_gameweeks import is_transfer_window_open, get_lock_time

    t0 = get_lock_time(1)  # GW1 lockAt
    # GW1 has no prev -> trade open from the start; 3h before lock = FA window.
    assert is_transfer_window_open(0, now=t0 - timedelta(hours=3)) is True
    # Locked hour -> closed.
    assert is_transfer_window_open(0, now=t0 - timedelta(minutes=30)) is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))


# ---------------------------------------------------------------------------
# Durable lineup lock (is_lineup_locked / lineup_lock_time, db-backed)
# ---------------------------------------------------------------------------

def _db_with_gw2():
    import test_helpers as H
    from fpl_predictor.game.wc_windows import lineup_lock_time, is_lineup_locked
    db = H.FakeDB()
    for fid, ko in [(2000, T0), (2001, UP_LAST)]:
        db.collection("wc_fixtures").document(str(fid)).set(
            {"id": fid, "gw": 2, "kickoff": ko})
    return db, lineup_lock_time, is_lineup_locked


def test_lineup_lock_time_is_t0_minus_1h():
    db, lineup_lock_time, _ = _db_with_gw2()
    assert lineup_lock_time(db, 2) == T0 - timedelta(hours=1)


def test_is_lineup_locked_crosses_at_squad_lock():
    db, _, is_lineup_locked = _db_with_gw2()
    assert is_lineup_locked(db, 2, now=T0 - timedelta(hours=2)) is False  # FREE_AGENTS
    assert is_lineup_locked(db, 2, now=T0 - timedelta(minutes=30)) is True  # locked
    assert is_lineup_locked(db, 2, now=T0 + timedelta(hours=1)) is True   # live


def test_is_lineup_locked_unlocked_when_no_kickoff():
    import test_helpers as H
    from fpl_predictor.game.wc_windows import is_lineup_locked
    db = H.FakeDB()  # no fixtures for the GW at all
    assert is_lineup_locked(db, 5, now=T0) is False


# ---------------------------------------------------------------------------
# Schedule timeline (build_window_schedule / locate_in_schedule)
# ---------------------------------------------------------------------------

# A two-GW fixture map: GW2 = the upcoming GW (T0 17 Jun 12:00, last 18:00),
# GW1 = previous (last kickoff 16 Jun 12:00), GW3 = next (T0 21 Jun 12:00).
_SCHED_FIXTURES = {
    1: [_fx(PREV_KO, gw=1), _fx(_utc(2026, 6, 16, 9, 0), gw=1)],
    2: [_fx(T0, gw=2), _fx(UP_LAST, gw=2)],
    3: [_fx(_utc(2026, 6, 21, 12, 0), gw=3), _fx(_utc(2026, 6, 21, 18, 0), gw=3)],
}


def test_schedule_orders_and_stitches_two_gws():
    from fpl_predictor.game.wc_windows import build_window_schedule
    segs = build_window_schedule(2, _SCHED_FIXTURES, CONFIG)
    phases = [(s["gw"], s["phase"]) for s in segs]
    assert phases == [
        (2, "trade"), (2, "free_agents"), (2, "none"), (2, "next_gw_bid"),
        (3, "trade"), (3, "free_agents"), (3, "none"), (3, "next_gw_bid"),
    ]
    # NEXT_GW_BID(2) ends exactly where TRADE(3) begins (contiguous timeline).
    bid2 = next(s for s in segs if s["gw"] == 2 and s["phase"] == "next_gw_bid")
    trade3 = next(s for s in segs if s["gw"] == 3 and s["phase"] == "trade")
    assert bid2["endsAt"] == trade3["startsAt"]


def test_schedule_gw1_trade_has_open_ended_start():
    from fpl_predictor.game.wc_windows import build_window_schedule
    segs = build_window_schedule(1, _SCHED_FIXTURES, CONFIG)
    trade1 = next(s for s in segs if s["gw"] == 1 and s["phase"] == "trade")
    assert trade1["startsAt"] is None  # no previous GW to reopen from


def test_locate_in_live_gw_reports_next_phase():
    from fpl_predictor.game.wc_windows import build_window_schedule, locate_in_schedule
    segs = build_window_schedule(2, _SCHED_FIXTURES, CONFIG)
    # 17 Jun 13:00 — GW2 live (NEXT_GW_BID); ends at offer_close 21:30, next is
    # GW3's TRADE starting at the same instant.
    ends, nxt, nxt_start = locate_in_schedule(segs, _utc(2026, 6, 17, 13, 0))
    assert ends == UP_LAST + timedelta(minutes=150) + timedelta(hours=1)
    assert nxt == "trade"
    assert nxt_start == ends


def test_locate_in_free_agents_window():
    from fpl_predictor.game.wc_windows import build_window_schedule, locate_in_schedule
    segs = build_window_schedule(2, _SCHED_FIXTURES, CONFIG)
    # 17 Jun 09:00 — inside FREE_AGENTS (07:00..11:00); next is NONE at 11:00.
    ends, nxt, nxt_start = locate_in_schedule(segs, _utc(2026, 6, 17, 9, 0))
    assert ends == T0 - timedelta(hours=1)
    assert nxt == "none"
    assert nxt_start == ends


def test_locate_past_end_is_all_none():
    from fpl_predictor.game.wc_windows import build_window_schedule, locate_in_schedule
    segs = build_window_schedule(2, _SCHED_FIXTURES, CONFIG)
    assert locate_in_schedule(segs, _utc(2026, 7, 1, 0, 0)) == (None, None, None)
