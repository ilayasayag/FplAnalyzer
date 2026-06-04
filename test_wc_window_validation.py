#!/usr/bin/env python3
"""Unit tests for the window GUARDS on the transfer/free-agent paths.

These verify the *routing* fix for the "everything is blocked by WINDOW_CLOSED
even though the admin opened a window" bug. The validators used to call the
legacy ``is_transfer_window_open`` helper which passed ``league_doc=None`` to
``current_window`` and therefore silently ignored an admin ``windowOverride``.
The fix routes both validators through the override-aware
``current_window_from_db`` state machine and gates on the SPECIFIC window:

  * free-agent pickups/drops (``WCSquadManager``) require ``FREE_AGENTS``;
  * trades (``WCTradeManager``) require ``TRADE`` or ``NEXT_GW_BID``.

PURE unit tests — no emulator. We stub the window state machine so each test
asserts only the gating decision, not the clock maths (covered separately in
test_wc_window_override.py / test_wc_windows.py).

Run:
    .venv/bin/python -m pytest test_wc_window_validation.py -q
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game import wc_windows  # noqa: E402
from fpl_predictor.game.wc_windows import TransferWindow  # noqa: E402
from fpl_predictor.game.wc_squads import WCSquadManager  # noqa: E402
from fpl_predictor.game.wc_trades import WCTradeManager  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal fake db: only needs the league doc to "exist" for the squad guard.
# ---------------------------------------------------------------------------

class _Snap:
    exists = True

    def to_dict(self):
        return {"currentGw": 2}


class _DocRef:
    def get(self):
        return _Snap()


class _Coll:
    def document(self, _id):
        return _DocRef()


class _FakeDB:
    def collection(self, _name):
        return _Coll()


ALL = [
    TransferWindow.NONE,
    TransferWindow.TRADE,
    TransferWindow.FREE_AGENTS,
    TransferWindow.NEXT_GW_BID,
]


# ---------------------------------------------------------------------------
# Free-agent guard (WCSquadManager): only FREE_AGENTS is allowed.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("window", ALL)
def test_squad_guard_only_free_agents(monkeypatch, window):
    monkeypatch.setattr(
        wc_windows, "current_window_from_db",
        lambda lid, db, **kw: (window, 2),
    )
    mgr = WCSquadManager(_FakeDB())
    if window == TransferWindow.FREE_AGENTS:
        mgr._validate_window_open("lg_x")  # must NOT raise
    else:
        with pytest.raises(ValueError, match="WINDOW_CLOSED"):
            mgr._validate_window_open("lg_x")


def test_squad_guard_open_overrides_closed_clock(monkeypatch):
    """The whole point of the bug fix: an override that opens FREE_AGENTS lets
    the pickup through even though the time-based clock would say closed."""
    monkeypatch.setattr(
        wc_windows, "current_window_from_db",
        lambda lid, db, **kw: (TransferWindow.FREE_AGENTS, 2),
    )
    WCSquadManager(_FakeDB())._validate_window_open("lg_x")


# ---------------------------------------------------------------------------
# Trade guard (WCTradeManager): TRADE or NEXT_GW_BID are allowed.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("window", ALL)
def test_trade_guard_allows_trade_and_next_gw_bid(monkeypatch, window):
    mgr = WCTradeManager(_FakeDB())
    # _validate_window_open delegates to _window_phase; stub it directly.
    monkeypatch.setattr(mgr, "_window_phase", lambda lid: (window, 2))
    league = {"currentGw": 2}
    if window in (TransferWindow.TRADE, TransferWindow.NEXT_GW_BID):
        mgr._validate_window_open("lg_x", league)  # must NOT raise
    else:
        with pytest.raises(ValueError, match="TRADES_BLOCKED_WINDOW_CLOSED"):
            mgr._validate_window_open("lg_x", league)
