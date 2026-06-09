"""
WC 2026 gameweek calendar.

This hardcoded calendar is a db-less FALLBACK. The DURABLE source of truth for
kickoff times is ``wc_config/schedule`` + the ``wc_fixtures`` kickoffs (see
``fpl_predictor/seed/wc_simulator.py``): the live transfer-window state machine
(``wc_windows.current_window_from_db``) and the lineup lock
(``wc_windows.is_lineup_locked``) read those, so re-running the simulator never
moves the windows. Keep ``lockAt`` here aligned with that schedule for the
contexts that have no ``db`` handle (``get_current_gw``, predictions lock, the
``is_transfer_window_open`` calendar wrapper).

``lockAt`` = kickoff of the earliest match in that GW (= T0). These are the real
WC 2026 kickoff times (confirmed 6 Dec 2025 draw), in UTC, and mirror the FIRST
entry of each GW in ``wc_simulator.DEFAULT_GW_KICKOFFS``.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Hardcoded GW calendar — keep in sync with wc_simulator.DEFAULT_GW_KICKOFFS
# ---------------------------------------------------------------------------

# All times in UTC. Format: (start, end, lockAt, wc_round, label).
# lockAt = the GW's first real kickoff (T0).
_GW_CONFIG: Dict[int, Dict] = {
    1: {
        "start":    datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
        "wcRound":  "Group Stage - Round 1",
        "label":    "Group Stage R1",
    },
    2: {
        "start":    datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 6, 24, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 6, 18, 16, 0, tzinfo=timezone.utc),
        "wcRound":  "Group Stage - Round 2",
        "label":    "Group Stage R2",
    },
    3: {
        "start":    datetime(2026, 6, 24, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 6, 28, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 6, 24, 19, 0, tzinfo=timezone.utc),
        "wcRound":  "Group Stage - Round 3",
        "label":    "Group Stage R3",
    },
    4: {
        "start":    datetime(2026, 6, 28, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 7, 4, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 6, 28, 19, 0, tzinfo=timezone.utc),
        "wcRound":  "Round of 32",
        "label":    "Round of 32",
    },
    5: {
        "start":    datetime(2026, 7, 4, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 7, 9, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 7, 4, 17, 0, tzinfo=timezone.utc),
        "wcRound":  "Round of 16",
        "label":    "Round of 16",
    },
    6: {
        "start":    datetime(2026, 7, 9, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 7, 9, 20, 0, tzinfo=timezone.utc),
        "wcRound":  "Quarter-finals",
        "label":    "Quarter-finals",
    },
    7: {
        "start":    datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 7, 14, 19, 0, tzinfo=timezone.utc),
        "wcRound":  "Semi-finals",
        "label":    "Semi-finals",
    },
    8: {
        "start":    datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 7, 20, 23, 59, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 7, 18, 21, 0, tzinfo=timezone.utc),
        "wcRound":  "Final",
        "label":    "Final & 3rd Place",
    },
}

TOTAL_GWS = 8


def get_gw_config(gw: int) -> Optional[Dict]:
    """Full config dict for a GW, or None if invalid."""
    return _GW_CONFIG.get(gw)


def get_lock_time(gw: int) -> Optional[datetime]:
    """lockAt for a GW (= kickoff of first match). None if invalid GW."""
    cfg = _GW_CONFIG.get(gw)
    return cfg["lockAt"] if cfg else None


def is_locked(gw: int, now: Optional[datetime] = None) -> bool:
    """True if the GW's lockAt has passed."""
    lock = get_lock_time(gw)
    if lock is None:
        return True
    now = now or datetime.now(timezone.utc)
    return now >= lock


def get_gw_for_date(dt: Optional[datetime] = None) -> int:
    """
    Return the current fantasy GW for a given datetime (default: now).
    Returns 0 if before tournament, 8 after tournament ends.
    """
    dt = dt or datetime.now(timezone.utc)
    for gw in range(1, TOTAL_GWS + 1):
        cfg = _GW_CONFIG[gw]
        if cfg["start"] <= dt < cfg["end"]:
            return gw
    if dt >= _GW_CONFIG[TOTAL_GWS]["end"]:
        return TOTAL_GWS
    return 0


def get_current_gw() -> int:
    return get_gw_for_date()


def get_next_gw() -> int:
    cur = get_current_gw()
    return min(cur + 1, TOTAL_GWS)


def get_window_dates(gw: int) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Returns (windowOpen, windowClose) for the transfer window AFTER the given GW.
    windowOpen  = immediately after GW finalizes (approximate: end of GW)
    windowClose = lockAt of (gw + 1)
    """
    cfg = _GW_CONFIG.get(gw)
    next_cfg = _GW_CONFIG.get(gw + 1)
    if not cfg or not next_cfg:
        return None, None
    return cfg["end"], next_cfg["lockAt"]


def get_waiver_deadline(gw: int) -> Optional[datetime]:
    """
    Waiver processing runs T+24h after transfer window opens (after GW finalized).
    Returns the waiver processing timestamp for the window after gw.
    """
    window_open, _ = get_window_dates(gw)
    if window_open is None:
        return None
    from datetime import timedelta
    return window_open + timedelta(hours=24)


def gw_as_dict(gw: int) -> Dict:
    """Serializable representation of GW config for Firestore storage."""
    cfg = _GW_CONFIG.get(gw)
    if not cfg:
        return {}
    return {
        "gw": gw,
        "start": cfg["start"].isoformat(),
        "end": cfg["end"].isoformat(),
        "lockAt": cfg["lockAt"].isoformat(),
        "wcRound": cfg["wcRound"],
        "label": cfg["label"],
    }


def all_gws_as_dict() -> Dict[str, Dict]:
    """All 8 GWs serialized, suitable for wc_config/tournament.gwDates."""
    return {f"gw{gw}": gw_as_dict(gw) for gw in range(1, TOTAL_GWS + 1)}


def compute_knockout_start_gw(member_count: int = 0) -> int:
    """
    Returns the GW where knockout phase starts.
    If 9-10 players -> starts GW4 (top 8 qualifiers).
    If 6-8 players -> starts GW7 (top 4 qualifiers).
    """
    return 4 if member_count > 8 else 7


def compute_league_phase_gws(member_count: int = 0) -> list:
    """All GWs in the league (H2H) phase."""
    if member_count > 8:
        return list(range(1, 4))
    return list(range(1, 7))


def compute_knockout_qualifiers(member_count: int = 0) -> int:
    """Number of managers who advance to knockout."""
    if member_count > 8:
        return 8
    return 4


def is_transfer_window_open(gw: int, now: Optional[datetime] = None) -> bool:
    """
    True if any transfer window (trade / free-agents / next-gw-bid) is open now.

    Thin wrapper over the single source of truth, ``wc_windows.current_window``
    (see WC2026_WINDOWS_DESIGN.md §2.3). ``gw`` is the *just-finalized* GW — the
    window guards the *upcoming* GW ``gw + 1`` (this is the existing caller
    contract: callers pass ``currentGw - 1`` / ``0``). Returning the window for
    the upcoming GW is what fixes the historical off-by-one: with the old
    ``get_window_dates`` path, passing ``gw=0`` (GW1's window) returned
    ``(None, None)`` so GW1's window never opened. Now ``gw=0`` resolves to
    upcoming GW ``1`` and its window opens correctly.

    Window boundaries are derived from the hardcoded GW calendar's ``lockAt``
    times (= first kickoff per GW) so this stays dependency-free for the
    existing in-process callers. ``Tprev_end`` is approximated from the previous
    GW's ``lockAt`` (the only kickoff the calendar stores); the dedicated
    Firestore wrapper ``wc_windows.current_window_from_db`` uses real per-fixture
    kickoffs when a ``db`` handle is available.
    """
    from fpl_predictor.game.wc_windows import TransferWindow, current_window

    now = now or datetime.now(timezone.utc)
    upcoming_gw = gw + 1

    upcoming_cfg = _GW_CONFIG.get(upcoming_gw)
    if upcoming_cfg is None:
        return False

    # Build synthetic single-fixture lists from the calendar's lockAt (= first
    # kickoff of the GW) so the pure window function can be reused as-is.
    upcoming_fixtures = [{"kickoff": upcoming_cfg["lockAt"], "gw": upcoming_gw}]
    prev_cfg = _GW_CONFIG.get(upcoming_gw - 1)
    prev_fixtures = (
        [{"kickoff": prev_cfg["lockAt"], "gw": upcoming_gw - 1}]
        if prev_cfg else None
    )

    window, _ = current_window(
        league_doc=None,
        fixtures_for_gw=upcoming_fixtures,
        config=None,  # module defaults (5h / 5h / 150min)
        now=now,
        prev_fixtures=prev_fixtures,
        upcoming_gw=upcoming_gw,
    )
    return window != TransferWindow.NONE
