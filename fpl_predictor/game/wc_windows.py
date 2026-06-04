"""
WC 2026 transfer-window state machine.

This module is the *single source of truth* for "what transfer window is open
right now". It replaces three contradictory checks that previously coexisted
(see WC2026_WINDOWS_DESIGN.md §1):

  1. wc_gameweeks.is_transfer_window_open  (time-based, off-by-one)
  2. wc_scoring._open_transfer_window       (wrote a transfer_windows doc that
                                             was never closed)
  3. wc_waivers._validate_in_submission_phase (a stub)

Everything now gates on :func:`current_window`.

Timeline (all windows run *before* T0 = the upcoming GW's first kickoff = the
lineup lock), per WC2026_WINDOWS_DESIGN.md §2.2::

    Tprev_end --TRADE--> +trade_h --FREE_AGENTS--> +fa_h --NEXT_GW_BID--> T0 (lock)

where
  * ``Tprev_end`` = final whistle of GW(n-1)'s last match
                  = last kickoff of GW(n-1) + ``match_duration_minutes``
  * ``T0``        = first kickoff of GW(n)

Both are derived purely from ``wc_fixtures`` kickoff times + config durations,
so the windows do NOT depend on when ``finalize_gw`` actually runs.

The pure function :func:`current_window` performs no Firestore I/O — it takes
already-fetched data so it is trivially unit-testable. A thin
Firestore-fetching wrapper :func:`current_window_from_db` is provided for
callers that have a ``db`` handle and a league id.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple


class TransferWindow(str, Enum):
    """The four mutually-exclusive transfer-window states.

    Exactly one of {TRADE, FREE_AGENTS, NEXT_GW_BID} — or NONE — is active at
    any instant. Values are stable wire strings (do not rename).
    """

    NONE = "none"               # mid-GW; nothing open
    TRADE = "trade"             # wishlist bids + manager<->manager trades
    FREE_AGENTS = "free_agents"  # immediate same-position signings only
    NEXT_GW_BID = "next_gw_bid"  # propose trades + auto-approve-for-next only


# ---------------------------------------------------------------------------
# Config defaults (see WC2026_WINDOWS_DESIGN.md §3.4 + §11 open item)
# ---------------------------------------------------------------------------

# Window lengths in hours, configurable via wc_config/tournament.
DEFAULT_TRADE_WINDOW_HOURS = 5
DEFAULT_FREE_AGENT_WINDOW_HOURS = 5

# How long after kickoff a match is considered "ended", used to compute
# Tprev_end from the previous GW's last kickoff.
#
# Why 150: a football match is 90' + ~15' half-time + stoppage. Knockout ties
# can run to extra time (+30') and a penalty shootout. 90 + 15 + ~10 stoppage
# + 30 ET + ~5 shootout/admin ≈ 150 minutes. This is deliberately generous so
# that Tprev_end never lands *before* a match has truly finished (which would
# open the trade window while results are still being scored). Overshooting is
# cheap — it only shifts the windows slightly later toward T0, and the
# short-turnaround guard (§2.2) keeps everything bounded by the lock anyway.
DEFAULT_MATCH_DURATION_MINUTES = 150


def resolve_durations(config: Optional[Dict]) -> Tuple[float, float, float]:
    """Pull the three window/duration knobs from a ``wc_config/tournament`` dict.

    Falls back to the module defaults when keys are absent so nothing breaks on
    existing data. Returns ``(trade_hours, free_agent_hours, match_minutes)``.
    """
    config = config or {}
    trade_h = config.get("trade_window_hours", DEFAULT_TRADE_WINDOW_HOURS)
    fa_h = config.get("free_agent_window_hours", DEFAULT_FREE_AGENT_WINDOW_HOURS)
    match_min = config.get("match_duration_minutes", DEFAULT_MATCH_DURATION_MINUTES)
    return float(trade_h), float(fa_h), float(match_min)


# ---------------------------------------------------------------------------
# Kickoff extraction helpers
# ---------------------------------------------------------------------------

def _coerce_dt(value) -> Optional[datetime]:
    """Best-effort coercion of a fixture kickoff value into an aware datetime.

    Fixture docs store ``kickoff`` as a Firestore timestamp (surfaces as a
    timezone-aware ``datetime`` via the Admin SDK) but seed/test data may use
    naive datetimes or ISO strings. Naive values are assumed UTC.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return None


def _kickoffs(fixtures: Iterable[Dict]) -> List[datetime]:
    """Sorted list of valid kickoff datetimes from a fixtures iterable.

    The fixture kickoff field is ``kickoff`` (see data/wc_api.py:243)."""
    out: List[datetime] = []
    for f in fixtures or []:
        kt = _coerce_dt((f or {}).get("kickoff"))
        if kt is not None:
            out.append(kt)
    out.sort()
    return out


# ---------------------------------------------------------------------------
# The single source of truth
# ---------------------------------------------------------------------------

def compute_window_boundaries(
    prev_fixtures: Optional[Iterable[Dict]],
    upcoming_fixtures: Iterable[Dict],
    config: Optional[Dict],
) -> Optional[Dict[str, datetime]]:
    """Compute the four window boundary instants for the upcoming GW.

    Returns a dict with keys ``trade_open``, ``trade_close``, ``fa_close`` and
    ``t0`` (lineup lock), or ``None`` if the boundaries can't be computed (no
    upcoming kickoff, i.e. nothing to open a window before).

    Applies the short-turnaround guard (§2.2): if there isn't enough room
    between ``Tprev_end`` and ``T0`` for the full trade + free-agent windows,
    both are compressed proportionally and NEXT_GW_BID gets whatever (possibly
    zero) time remains. No window ever closes after ``T0``.
    """
    upcoming_kos = _kickoffs(upcoming_fixtures)
    if not upcoming_kos:
        return None
    t0 = upcoming_kos[0]  # first kickoff of upcoming GW = lineup lock

    trade_h, fa_h, match_min = resolve_durations(config)

    prev_kos = _kickoffs(prev_fixtures) if prev_fixtures else []
    if prev_kos:
        # Final whistle of the previous GW's last match.
        tprev_end = prev_kos[-1] + timedelta(minutes=match_min)
    else:
        # No previous GW (this is GW1) — the trade window opens at the start of
        # the available runway. Anchor it so the full trade + FA windows fit if
        # possible, otherwise the guard below compresses against T0.
        tprev_end = t0 - timedelta(hours=trade_h + fa_h)

    # Tprev_end can't sit after the lock (e.g. ultra-short turnaround). Clamp it.
    if tprev_end > t0:
        tprev_end = t0

    gap = (t0 - tprev_end).total_seconds()
    requested = (trade_h + fa_h) * 3600.0

    if requested <= 0:
        trade_secs = fa_secs = 0.0
    elif gap < requested:
        # Short-turnaround guard: scale trade + FA proportionally to fit `gap`.
        scale = gap / requested
        trade_secs = trade_h * 3600.0 * scale
        fa_secs = fa_h * 3600.0 * scale
    else:
        trade_secs = trade_h * 3600.0
        fa_secs = fa_h * 3600.0

    trade_open = tprev_end
    trade_close = trade_open + timedelta(seconds=trade_secs)
    fa_close = trade_close + timedelta(seconds=fa_secs)

    # Float arithmetic guard: never overrun the lock.
    if fa_close > t0:
        fa_close = t0
    if trade_close > fa_close:
        trade_close = fa_close

    return {
        "trade_open": trade_open,
        "trade_close": trade_close,
        "fa_close": fa_close,
        "t0": t0,
    }


def current_window(
    league_doc: Optional[Dict],
    fixtures_for_gw: Iterable[Dict],
    config: Optional[Dict],
    now: Optional[datetime] = None,
    prev_fixtures: Optional[Iterable[Dict]] = None,
    upcoming_gw: Optional[int] = None,
) -> Tuple[TransferWindow, Optional[int]]:
    """Pure function — the single source of truth for transfer windows.

    Returns ``(window, gw)`` where ``gw`` is the upcoming GW the window guards.

    Args:
        league_doc: the league dict (currently only used to derive the upcoming
            GW from ``currentGw`` when ``upcoming_gw`` isn't given). May be None.
        fixtures_for_gw: fixtures of the **upcoming** GW (need their ``kickoff``
            fields). ``T0`` = earliest kickoff among these.
        config: ``wc_config/tournament`` dict (durations); defaults applied when
            keys absent.
        now: instant to evaluate (defaults to ``datetime.now(timezone.utc)``).
        prev_fixtures: fixtures of the **previous** GW; ``Tprev_end`` = last
            kickoff + ``match_duration_minutes``. Omit/empty for GW1.
        upcoming_gw: explicit upcoming GW number; if omitted it's derived from
            ``league_doc['currentGw']`` (the next GW to be played).

    No Firestore writes. ``current_window_from_db`` is the I/O wrapper.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if upcoming_gw is None and league_doc is not None:
        upcoming_gw = league_doc.get("currentGw")

    bounds = compute_window_boundaries(prev_fixtures, fixtures_for_gw, config)
    if bounds is None:
        return TransferWindow.NONE, upcoming_gw

    if now < bounds["trade_open"]:
        return TransferWindow.NONE, upcoming_gw
    if now < bounds["trade_close"]:
        return TransferWindow.TRADE, upcoming_gw
    if now < bounds["fa_close"]:
        return TransferWindow.FREE_AGENTS, upcoming_gw
    if now < bounds["t0"]:
        return TransferWindow.NEXT_GW_BID, upcoming_gw
    # At/after T0 the lineup is locked — nothing is open.
    return TransferWindow.NONE, upcoming_gw


# ---------------------------------------------------------------------------
# Thin Firestore-fetching wrapper
# ---------------------------------------------------------------------------

def current_window_from_db(
    lid: str,
    db,
    now: Optional[datetime] = None,
    upcoming_gw: Optional[int] = None,
) -> Tuple[TransferWindow, Optional[int]]:
    """Fetch league/fixtures/config from Firestore, then call :func:`current_window`.

    Determines the upcoming GW from the league's ``currentGw`` (the next GW to
    be played), reads that GW's fixtures (for ``T0``) and the previous GW's
    fixtures (for ``Tprev_end``), plus ``wc_config/tournament`` durations.
    """
    league_ref = db.collection("leagues").document(lid)
    league_snap = league_ref.get()
    league_doc = league_snap.to_dict() if league_snap.exists else {}

    if upcoming_gw is None:
        upcoming_gw = league_doc.get("currentGw", 1)

    config_snap = db.collection("wc_config").document("tournament").get()
    config = config_snap.to_dict() if config_snap.exists else {}

    upcoming_fixtures = [
        d.to_dict() for d in
        db.collection("wc_fixtures").where("gw", "==", upcoming_gw).get()
    ]
    prev_fixtures = None
    if upcoming_gw and upcoming_gw > 1:
        prev_fixtures = [
            d.to_dict() for d in
            db.collection("wc_fixtures").where("gw", "==", upcoming_gw - 1).get()
        ]

    return current_window(
        league_doc=league_doc,
        fixtures_for_gw=upcoming_fixtures,
        config=config,
        now=now,
        prev_fixtures=prev_fixtures,
        upcoming_gw=upcoming_gw,
    )
