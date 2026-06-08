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

Timeline, anchored on T0 = the upcoming GW's first kickoff (per
WC2026_WINDOWS_DESIGN.md §2.2)::

    Tprev_end+reopen ─TRADE─> T0-5h ─FREE_AGENTS─> T0-1h ─NONE(locked)─> T0
        T0 ─NEXT_GW_BID (live, OFFER-TRADES)─> Tlast_end+reopen ─TRADE─> …

where
  * ``Tprev_end``  = final whistle of GW(n-1)'s last match
                   = last kickoff of GW(n-1) + ``match_duration_minutes``
  * ``T0``         = first kickoff of GW(n)
  * ``Tlast_end``  = final whistle of GW(n)'s last match

Phases:
  * TRADE       — execute manager↔manager trades; squads change. Opens
                  ``reopen_h`` after the previous GW's last match ends, runs
                  until ``T0 - fa_open_before_h``.
  * FREE_AGENTS — free-agent pickups (+ the wishlist/waiver draft fires when
                  this opens). ``T0 - fa_open_before_h`` .. ``T0 - squad_lock_before_h``.
  * NONE        — squads + XI locked. ``T0 - squad_lock_before_h`` .. ``T0``.
  * NEXT_GW_BID — the GW is live: managers may only OFFER trades + edit their
                  bid-wishlist; squads stay frozen. ``T0`` until this GW's last
                  match end + ``reopen_h``, where it flips back to TRADE.

All boundaries are derived purely from ``wc_fixtures`` kickoff times + config
durations, so the windows do NOT depend on when ``finalize_gw`` actually runs.

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

# Window offsets in hours, configurable via wc_config/tournament. The timeline
# is anchored on T0 = the upcoming GW's first kickoff (see module docstring):
#   * FREE-AGENT window opens (and trades LOCK) at  T0 - FA_OPEN_BEFORE_HOURS
#   * squads + XI LOCK at                            T0 - SQUAD_LOCK_BEFORE_HOURS
#   * trades REOPEN at        (previous GW's last match end) + TRADE_REOPEN_AFTER_HOURS
DEFAULT_FA_OPEN_BEFORE_HOURS = 5      # T0 - 5h: trades lock + FA window + waiver draft
DEFAULT_SQUAD_LOCK_BEFORE_HOURS = 1   # T0 - 1h: squads + lineup lock
DEFAULT_TRADE_REOPEN_AFTER_HOURS = 1  # last match end + 1h: trades reopen

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


def resolve_durations(config: Optional[Dict]) -> Tuple[float, float, float, float]:
    """Pull the window-offset knobs from a ``wc_config/tournament`` dict.

    Falls back to the module defaults when keys are absent so nothing breaks on
    existing data. Returns
    ``(fa_open_before_h, squad_lock_before_h, trade_reopen_after_h, match_minutes)``.
    """
    config = config or {}
    fa_open_h = config.get("fa_open_before_hours", DEFAULT_FA_OPEN_BEFORE_HOURS)
    squad_lock_h = config.get("squad_lock_before_hours", DEFAULT_SQUAD_LOCK_BEFORE_HOURS)
    reopen_h = config.get("trade_reopen_after_hours", DEFAULT_TRADE_REOPEN_AFTER_HOURS)
    match_min = config.get("match_duration_minutes", DEFAULT_MATCH_DURATION_MINUTES)
    return float(fa_open_h), float(squad_lock_h), float(reopen_h), float(match_min)


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
    """Compute the window boundary instants for the upcoming/live GW.

    Anchored on ``t0`` = the upcoming GW's first kickoff. Returns a dict with:
      * ``t0``          — first kickoff of this GW (squads must already be locked)
      * ``offer_close`` — this GW's last match end + reopen_h; the live-GW
                          OFFER-TRADES window runs from ``t0`` until here
      * ``trade_open``  — previous GW's last match end + reopen_h (or ``None`` for
                          GW1); the TRADE window opens here
      * ``fa_open``     — ``t0`` - fa_open_before_h; trades LOCK and the
                          FREE-AGENT window + wishlist/waiver draft start
      * ``squad_lock``  — ``t0`` - squad_lock_before_h; squads + XI LOCK
    or ``None`` if there's no upcoming kickoff.

    Short-turnaround guard: if ``t0`` is so soon that ``squad_lock`` would
    precede ``fa_open``, both are clamped to keep ``fa_open <= squad_lock <= t0``.
    """
    this_kos = _kickoffs(upcoming_fixtures)
    if not this_kos:
        return None
    fa_open_h, squad_lock_h, reopen_h, match_min = resolve_durations(config)

    t0 = this_kos[0]
    # This GW's last match end (+ reopen) bounds the live OFFER-TRADES window.
    offer_close = this_kos[-1] + timedelta(minutes=match_min) + timedelta(hours=reopen_h)

    fa_open = t0 - timedelta(hours=fa_open_h)
    squad_lock = t0 - timedelta(hours=squad_lock_h)
    if squad_lock > t0:
        squad_lock = t0
    if fa_open > squad_lock:
        fa_open = squad_lock

    prev_kos = _kickoffs(prev_fixtures) if prev_fixtures else []
    trade_open = (prev_kos[-1] + timedelta(minutes=match_min)
                  + timedelta(hours=reopen_h)) if prev_kos else None

    return {
        "t0": t0,
        "offer_close": offer_close,
        "trade_open": trade_open,
        "fa_open": fa_open,
        "squad_lock": squad_lock,
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

    # Admin override (see WC2026_WINDOWS_DESIGN.md): an admin can force the
    # current phase from the UI for testing. A truthy `phase` that names a
    # valid TransferWindow short-circuits the time-based logic. `phase ==
    # "none"` is valid and force-closes the window (intended). An absent or
    # invalid override falls through to the real fixture-clock computation.
    override = (league_doc or {}).get("windowOverride")
    if isinstance(override, dict) and override.get("phase"):
        try:
            forced = TransferWindow(override["phase"])
        except ValueError:
            forced = None
        if forced is not None:
            return forced, (override.get("gw") or upcoming_gw)

    bounds = compute_window_boundaries(prev_fixtures, fixtures_for_gw, config)
    if bounds is None:
        return TransferWindow.NONE, upcoming_gw

    t0 = bounds["t0"]
    if now >= t0:
        # The GW is live (or just played, pre-finalize). OFFER-TRADES: managers
        # may offer trades + edit their bid-wishlist, but squads stay frozen.
        # Once past (last match end + reopen), trades reopen toward the next GW.
        if now < bounds["offer_close"]:
            return TransferWindow.NEXT_GW_BID, upcoming_gw
        return TransferWindow.TRADE, upcoming_gw

    # Pre-GW runway toward T0.
    trade_open = bounds["trade_open"]
    if trade_open is not None and now < trade_open:
        # Still inside the previous GW's OFFER-TRADES tail (its end + reopen_h).
        return TransferWindow.NEXT_GW_BID, upcoming_gw
    if now < bounds["fa_open"]:
        return TransferWindow.TRADE, upcoming_gw        # execute trades; squads change
    if now < bounds["squad_lock"]:
        return TransferWindow.FREE_AGENTS, upcoming_gw  # free-agent pickups (+ waiver draft at open)
    # squad_lock .. t0: squads + XI locked, nothing changes.
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


# ---------------------------------------------------------------------------
# Lineup lock (squad + XI freeze at T0 - squad_lock_before_hours)
# ---------------------------------------------------------------------------

def lineup_lock_time(db, gw: int, config: Optional[Dict] = None) -> Optional[datetime]:
    """The instant a GW's squads + XI lock = ``T0 - squad_lock_before_hours``,
    where ``T0`` is the GW's first real kickoff (from durable ``wc_fixtures``).

    Returns ``None`` when the GW has no stored kickoff yet (so callers don't
    block edits on data that isn't there — e.g. the mock, whose simulated
    fixtures may carry no real-world clock).
    """
    fixtures = [
        d.to_dict() for d in
        db.collection("wc_fixtures").where("gw", "==", gw).get()
    ]
    if config is None:
        snap = db.collection("wc_config").document("tournament").get()
        config = snap.to_dict() if snap.exists else {}
    bounds = compute_window_boundaries(None, fixtures, config)
    return bounds["squad_lock"] if bounds else None


def is_lineup_locked(db, gw: int, now: Optional[datetime] = None) -> bool:
    """True once ``now`` has reached the GW's lineup lock (``T0 - 1h`` by
    default). Squads + XI may no longer change for ``gw`` from this instant.

    Durable: derived from the stored fixture kickoffs, so re-running the
    simulator never moves the lock. Falls back to *unlocked* when no kickoff is
    known for the GW.
    """
    lock = lineup_lock_time(db, gw)
    if lock is None:
        return False
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now >= lock
