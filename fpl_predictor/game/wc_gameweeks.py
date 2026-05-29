"""
WC 2026 gameweek calendar.

All GW dates are hardcoded — they don't change once the tournament starts.
lockAt = kickoff of the earliest match in that GW.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Hardcoded GW calendar — update lockAt if schedule changes pre-tournament
# ---------------------------------------------------------------------------

# All times in UTC. Format: (start, end, lockAt, wc_round, label)
_GW_CONFIG: Dict[int, Dict] = {
    1: {
        "start":    datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 6, 11, 17, 0, tzinfo=timezone.utc),
        "wcRound":  "Group Stage - Round 1",
        "label":    "Group Stage R1",
    },
    2: {
        "start":    datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 6, 22, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 6, 16, 17, 0, tzinfo=timezone.utc),
        "wcRound":  "Group Stage - Round 2",
        "label":    "Group Stage R2",
    },
    3: {
        "start":    datetime(2026, 6, 22, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 6, 27, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 6, 22, 17, 0, tzinfo=timezone.utc),
        "wcRound":  "Group Stage - Round 3",
        "label":    "Group Stage R3",
    },
    4: {
        "start":    datetime(2026, 6, 27, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 7, 5, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 6, 27, 17, 0, tzinfo=timezone.utc),
        "wcRound":  "Round of 32",
        "label":    "Round of 32",
    },
    5: {
        "start":    datetime(2026, 7, 5, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 7, 10, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 7, 5, 17, 0, tzinfo=timezone.utc),
        "wcRound":  "Round of 16",
        "label":    "Round of 16",
    },
    6: {
        "start":    datetime(2026, 7, 10, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 7, 10, 17, 0, tzinfo=timezone.utc),
        "wcRound":  "Quarter-finals",
        "label":    "Quarter-finals",
    },
    7: {
        "start":    datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 7, 14, 17, 0, tzinfo=timezone.utc),
        "wcRound":  "Semi-finals",
        "label":    "Semi-finals",
    },
    8: {
        "start":    datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc),
        "end":      datetime(2026, 7, 20, 23, 59, tzinfo=timezone.utc),
        "lockAt":   datetime(2026, 7, 18, 17, 0, tzinfo=timezone.utc),
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
    League is always 6-8 players → always GW7 (SF bracket, top 4 qualify).
    """
    return 7


def compute_league_phase_gws(member_count: int = 0) -> list:
    """All GWs in the league (H2H) phase — always GWs 1-6."""
    return list(range(1, 7))


def compute_knockout_qualifiers(member_count: int = 0) -> int:
    """Number of managers who advance to knockout — always 4."""
    return 4


def is_transfer_window_open(gw: int, now: Optional[datetime] = None) -> bool:
    """
    True if a transfer window is open right now.
    Windows are open between GW finalization and next GW lockAt.
    GW must be active or after active GW.
    """
    now = now or datetime.now(timezone.utc)
    window_open, window_close = get_window_dates(gw)
    if window_open is None or window_close is None:
        return False
    return window_open <= now < window_close
