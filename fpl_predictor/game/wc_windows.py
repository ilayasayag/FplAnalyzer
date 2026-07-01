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


_VALID_PHASES = {w.value for w in TransferWindow}


def parse_window_schedule(league_doc: Optional[Dict]) -> List[Tuple[datetime, str, Optional[int]]]:
    """Parse a league's ``windowSchedule`` into ``[(effectiveAt, phase, gw), ...]``
    sorted ascending by time, dropping malformed/invalid-phase entries.

    ``windowSchedule`` is an admin-authored list of *timed* phase overrides:
    ``[{phase, effectiveAt, gw?}]``. Each ``effectiveAt`` is the instant (UTC)
    that phase should take effect. Unlike the instant ``windowOverride``, these
    are applied LAZILY by :func:`current_window` as the clock passes each entry
    (no cron — the window is recomputed on every read). Pure / no I/O.
    """
    raw = (league_doc or {}).get("windowSchedule") or []
    out: List[Tuple[datetime, str, Optional[int]]] = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        phase = e.get("phase")
        if phase not in _VALID_PHASES:
            continue
        dt = _coerce_dt(e.get("effectiveAt"))
        if dt is None:
            continue
        out.append((dt, phase, e.get("gw")))
    out.sort(key=lambda x: x[0])
    return out


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

    # Timed schedule (windowSchedule): admin-authored phase changes that take
    # effect as the clock passes each ``effectiveAt``. The latest entry whose
    # time has already passed wins, and it takes precedence over the instant
    # ``windowOverride`` below. Applied lazily — this function is re-evaluated on
    # every read, so the transition "happens" the next time the window is read
    # after its time. See WC2026_WINDOWS_DESIGN.md.
    scheduled = parse_window_schedule(league_doc)
    if scheduled:
        passed = [s for s in scheduled if s[0] <= now]
        if passed:
            eff_dt, phase, sched_gw = passed[-1]
            try:
                return TransferWindow(phase), (sched_gw or upcoming_gw)
            except ValueError:
                pass

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

def lineup_lock_time(db, gw: int, config: Optional[Dict] = None,
                     lid: Optional[str] = None) -> Optional[datetime]:
    """The instant a GW's squads + XI lock = ``T0 - squad_lock_before_hours``,
    where ``T0`` is the GW's first real kickoff (from durable ``wc_fixtures``).

    Per-league override: when ``lid`` is given and
    ``leagues/{lid}.lineupLockOverride[str(gw)]`` holds an ISO-UTC instant, THAT
    wins over the fixture-clock calc — letting an admin extend/shorten a single
    GW's lineup lock for ONE league without touching real kickoff times. Leagues
    with no override keep the fixture clock.

    Returns ``None`` when the GW has no stored kickoff yet (so callers don't
    block edits on data that isn't there — e.g. the mock, whose simulated
    fixtures may carry no real-world clock).
    """
    if lid:
        snap = db.collection("leagues").document(lid).get()
        ov = ((snap.to_dict() or {}).get("lineupLockOverride") or {}) if snap.exists else {}
        iso = ov.get(str(gw), ov.get(gw))
        if iso:
            dt = _coerce_dt(iso)
            if dt is not None:
                return dt
    fixtures = [
        d.to_dict() for d in
        db.collection("wc_fixtures").where("gw", "==", gw).get()
    ]
    if config is None:
        snap = db.collection("wc_config").document("tournament").get()
        config = snap.to_dict() if snap.exists else {}
    bounds = compute_window_boundaries(None, fixtures, config)
    return bounds["squad_lock"] if bounds else None


def is_lineup_locked(db, gw: int, now: Optional[datetime] = None,
                     lid: Optional[str] = None) -> bool:
    """True once ``now`` has reached the GW's lineup lock (``T0 - 1h`` by
    default, or the per-league ``lineupLockOverride`` when set — see
    :func:`lineup_lock_time`). Squads + XI may no longer change for ``gw``.

    Durable: derived from the stored fixture kickoffs, so re-running the
    simulator never moves the lock. Falls back to *unlocked* when no kickoff is
    known for the GW.
    """
    lock = lineup_lock_time(db, gw, lid=lid)
    if lock is None:
        return False
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now >= lock


# ---------------------------------------------------------------------------
# Schedule timeline (current + next GW) — for the windows/timers UX
# ---------------------------------------------------------------------------

# What a manager may DO in each phase, surfaced to the timeline UI so server and
# client agree. The frontend may render its own copy, but these tokens are the
# contract.
PHASE_ALLOWED: Dict[TransferWindow, List[str]] = {
    TransferWindow.TRADE: ["trade", "wishlist"],
    TransferWindow.FREE_AGENTS: ["free_agent", "wishlist"],
    TransferWindow.NONE: [],
    TransferWindow.NEXT_GW_BID: ["offer_trade", "wishlist"],
}


def _gw_segments(
    prev_fixtures: Optional[Iterable[Dict]],
    upcoming_fixtures: Iterable[Dict],
    config: Optional[Dict],
) -> List[Tuple[TransferWindow, Optional[datetime], datetime]]:
    """Ordered phase segments for ONE upcoming GW's runup + live window.

    Returns ``[(phase, starts_at|None, ends_at), ...]`` chronologically:
    TRADE → FREE_AGENTS → NONE(locked) → NEXT_GW_BID, mirroring the boundaries
    in :func:`current_window`. ``starts_at`` is ``None`` only for GW1's TRADE
    (no previous GW to reopen from — open-ended start). Zero/negative-length
    segments (possible after the short-turnaround clamp) are dropped. Empty list
    if the GW has no kickoff yet.
    """
    bounds = compute_window_boundaries(prev_fixtures, upcoming_fixtures, config)
    if bounds is None:
        return []
    raw = [
        (TransferWindow.TRADE, bounds["trade_open"], bounds["fa_open"]),
        (TransferWindow.FREE_AGENTS, bounds["fa_open"], bounds["squad_lock"]),
        (TransferWindow.NONE, bounds["squad_lock"], bounds["t0"]),
        (TransferWindow.NEXT_GW_BID, bounds["t0"], bounds["offer_close"]),
    ]
    out = []
    for phase, start, end in raw:
        # Drop collapsed segments (start clamped onto/past end). A None start
        # (GW1 TRADE) is open-ended and always kept.
        if start is not None and start >= end:
            continue
        out.append((phase, start, end))
    return out


def build_window_schedule(
    upcoming_gw: Optional[int],
    fixtures_by_gw: Dict[int, List[Dict]],
    config: Optional[Dict],
) -> List[Dict]:
    """Contiguous phase segments spanning ``upcoming_gw`` and ``upcoming_gw + 1``.

    ``fixtures_by_gw`` maps a GW number to its fixtures list; each GW's segments
    need its own fixtures (for T0) plus the previous GW's (for ``trade_open``).
    The NEXT_GW_BID segment of GW n ends exactly where GW n+1's TRADE begins
    (both ``= offer_close_n``), so the two GWs stitch into one timeline.

    Each entry: ``{phase: str, startsAt: datetime|None, endsAt: datetime,
    gw: int, allowed: [str]}``. Returns ``[]`` when no fixtures are known.
    """
    if not upcoming_gw:
        return []
    segments: List[Dict] = []
    for n in (upcoming_gw, upcoming_gw + 1):
        upcoming = fixtures_by_gw.get(n)
        if not upcoming:
            continue
        prev = fixtures_by_gw.get(n - 1)
        for phase, start, end in _gw_segments(prev, upcoming, config):
            segments.append({
                "phase": phase.value,
                "startsAt": start,
                "endsAt": end,
                "gw": n,
                "allowed": PHASE_ALLOWED.get(phase, []),
            })
    return segments


def locate_in_schedule(
    segments: List[Dict], now: datetime,
) -> Tuple[Optional[datetime], Optional[str], Optional[datetime]]:
    """Given the real-clock ``segments`` and ``now``, return
    ``(phase_ends_at, next_phase, next_phase_starts_at)``.

    ``phase_ends_at`` is the end of the segment containing ``now`` (a ``None``
    start means open-ended, i.e. matches any earlier ``now``); the next two
    fields describe the following segment. All ``None`` when ``now`` is past the
    final known segment. When ``now`` precedes the whole timeline, the first
    segment is reported as the upcoming one with no current end.
    """
    for idx, seg in enumerate(segments):
        start, end = seg["startsAt"], seg["endsAt"]
        if now >= end:
            continue
        # First segment whose end is still ahead of us.
        if start is not None and now < start:
            # now sits in a gap before this segment starts → it's "next".
            return None, seg["phase"], start
        nxt = segments[idx + 1] if idx + 1 < len(segments) else None
        return (end,
                nxt["phase"] if nxt else None,
                nxt["startsAt"] if nxt else None)
    return None, None, None


def transfer_window_state(
    lid: str, db, now: Optional[datetime] = None,
) -> Dict:
    """One-shot transfer-window view for the API: the current phase
    (override-aware) plus the real-clock schedule + next-phase boundaries.

    Reads the league, ``wc_config/tournament`` durations, and fixtures for the
    previous / current / next GW in a single pass (no double-fetch with
    :func:`current_window`). The *current phase* honours ``windowOverride``; the
    *schedule and next-phase timestamps* are always the real fixture clock, so
    an admin override flips the banner while the timeline keeps showing reality.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    league_snap = db.collection("leagues").document(lid).get()
    league_doc = league_snap.to_dict() if league_snap.exists else {}
    upcoming_gw = league_doc.get("currentGw", 1)

    config_snap = db.collection("wc_config").document("tournament").get()
    config = config_snap.to_dict() if config_snap.exists else {}

    fixtures_by_gw: Dict[int, List[Dict]] = {}
    for n in (upcoming_gw - 1, upcoming_gw, upcoming_gw + 1):
        if n and n >= 1:
            fixtures_by_gw[n] = [
                d.to_dict() for d in
                db.collection("wc_fixtures").where("gw", "==", n).get()
            ]

    window, win_gw = current_window(
        league_doc=league_doc,
        fixtures_for_gw=fixtures_by_gw.get(upcoming_gw, []),
        config=config,
        now=now,
        prev_fixtures=fixtures_by_gw.get(upcoming_gw - 1),
        upcoming_gw=upcoming_gw,
    )

    segments = build_window_schedule(upcoming_gw, fixtures_by_gw, config)
    phase_ends_at, next_phase, next_phase_starts_at = locate_in_schedule(segments, now)

    # When an admin timed schedule is in force, the live countdown should point
    # at the next *scheduled* flip rather than the fixture-clock timeline. The
    # current phase already reflects the schedule (via current_window).
    scheduled = parse_window_schedule(league_doc)
    if scheduled:
        pending = [s for s in scheduled if s[0] > now]
        if pending:
            ndt, nphase, _ = pending[0]
            phase_ends_at, next_phase, next_phase_starts_at = ndt, nphase, ndt
        else:
            phase_ends_at, next_phase, next_phase_starts_at = None, None, None

    return {
        "phase": window.value,
        "gw": win_gw,
        "overridden": bool((league_doc or {}).get("windowOverride")) or bool(scheduled),
        "phaseEndsAt": phase_ends_at,
        "nextPhase": next_phase,
        "nextPhaseStartsAt": next_phase_starts_at,
        "schedule": segments,
        "scheduledOverrides": [
            {"phase": p, "effectiveAt": dt, "gw": gw} for (dt, p, gw) in scheduled
        ],
        # Last wishlist auto-run outcome (done/blocked/failed/rolled_back),
        # written by WishlistAutoRunner — lets the admin UI surface a blocked
        # auto-run without polling anything else.
        "wishlistAutoRun": (league_doc or {}).get("wishlistAutoRun"),
    }
