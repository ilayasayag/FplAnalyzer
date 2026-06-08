"""WC 2026 random tournament simulator.

Generates synthetic-but-realistic match data for the whole World Cup so the
fantasy app can be exercised end-to-end without any live data source. For every
fixture in a gameweek it produces:

  * a random scoreline (knockout rounds are forced decisive),
  * goalscorers + assisters chosen with position-weighted probabilities
    (forwards/midfielders far more likely than defenders/keepers),
  * a Defensive-Contribution (DefCon) roll per player, weighted toward DEF/MID,
  * minutes (a starting XI on ~90', a couple of subs, the rest benched),
  * GK saves,
  * player ratings spread so the engine's 3/2/1 rating bonus naturally elects
    three "men of the match" per fixture (highest-rated players, with a boost
    for goalscorers).

The simulator deliberately does NOT compute fantasy points itself. It writes the
api-sports-shaped ``raw_stats`` and the fixture ``score``, then drives the REAL
scoring engine (:func:`fpl_predictor.game.wc_scoring.process_fixture` and
:func:`~fpl_predictor.game.wc_scoring.finalize_gw`). That keeps a single source
of truth for scoring and means everything the simulator produces reconciles with
production rules (DefCon thresholds, clean sheets derived from the scoreline,
rating bonus, H2H 3/1/0 + the +1 "best manager in the GW" bonus, cumulative
fantasy points, standings rank/qualified, and WC group-table eliminations).

Clean sheets / goals-conceded are intentionally omitted from the per-player
raw_stats: the engine derives them from the fixture score + which side the
player is on, so emitting them here would be redundant (and a second, drift-prone
source of truth).

Two layers:
  * PURE generation (``simulate_*`` functions) — deterministic given a seeded
    ``random.Random``, no Firestore, fully unit-testable.
  * DB DRIVER (``simulate_gw`` / ``simulate_tournament``) — reads teams/players,
    writes fixtures + raw stats, and calls the engine. Knockout rounds (GW >=
    ``knockout_start_gw``) create fresh ``wc_fixtures`` between surviving teams
    and mark the losers eliminated.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from fpl_predictor.game.wc_scoring import process_fixture, finalize_gw
from fpl_predictor.seed.seed_league import select_lineup

# --- Position constants (mirrors the rest of the codebase) -----------------
GK, DEF, MID, FWD = 1, 2, 3, 4

# --- Durable fixture kickoffs ----------------------------------------------
# The transfer-window state machine (game/wc_windows.py) derives every window
# boundary from each GW's first/last kickoff. Those times therefore have to be
# DURABLE: re-running the simulator must not stamp them with "now"
# (SERVER_TIMESTAMP), or the windows would silently follow whenever a sim last
# ran. The source of truth is the ``wc_config/schedule`` doc, which survives
# ``reset_simulation`` (that wipes wc_fixtures + league scoring, never
# wc_config). ``_write_fixture`` reads kickoffs from there; only when a GW has
# no scheduled time AND no existing fixture to preserve does it fall back to
# SERVER_TIMESTAMP.
#
# Real WC 2026 round dates (public schedule): group MD1 11 Jun, MD2 18 Jun,
# MD3 24 Jun; Round-of-32 28 Jun; Round-of-16 4 Jul; QF 9 Jul; SF 14 Jul;
# Final 19 Jul. Time-of-day is a 13:00 UTC PLACEHOLDER (the source data has
# day-granularity only) — replace with real per-match kickoff times via
# ``seed_schedule`` and every window recomputes automatically.
DEFAULT_GW_KICKOFFS: Dict[int, str] = {
    1: "2026-06-11T13:00:00+00:00",
    2: "2026-06-18T13:00:00+00:00",
    3: "2026-06-24T13:00:00+00:00",
    4: "2026-06-28T13:00:00+00:00",
    5: "2026-07-04T13:00:00+00:00",
    6: "2026-07-09T13:00:00+00:00",
    7: "2026-07-14T13:00:00+00:00",
    8: "2026-07-19T13:00:00+00:00",
}


def _coerce_kickoff(value) -> Optional[datetime]:
    """Coerce a stored kickoff (ISO string / datetime) to an aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def _load_schedule_kickoffs(db) -> Dict[int, List[datetime]]:
    """Read ``wc_config/schedule`` into ``{gw: [sorted kickoff datetimes]}``.

    Each GW's value may be a single time (all matches share it) or a list (one
    per match, assigned by fixture index). Returns ``{}`` when the doc is absent
    so callers transparently fall back to preserve-existing / SERVER_TIMESTAMP.
    """
    snap = db.collection("wc_config").document("schedule").get()
    raw = ((snap.to_dict() or {}).get("kickoffs") or {}) if snap.exists else {}
    out: Dict[int, List[datetime]] = {}
    for key, val in raw.items():
        try:
            gw = int(key)
        except (TypeError, ValueError):
            continue
        times = val if isinstance(val, list) else [val]
        dts = [d for d in (_coerce_kickoff(t) for t in times) if d is not None]
        if dts:
            out[gw] = sorted(dts)
    return out


def seed_schedule(db, kickoffs: Optional[Dict[int, object]] = None) -> Dict[int, List[datetime]]:
    """Persist the durable per-GW kickoff schedule to ``wc_config/schedule``.

    ``kickoffs`` maps GW -> an ISO string / datetime, or a list of them (for a
    GW with several matches at different times). Defaults to
    :data:`DEFAULT_GW_KICKOFFS` (real WC round dates, 13:00 UTC placeholder).
    Stores ISO strings and returns the parsed ``{gw: [datetimes]}``.
    """
    src = kickoffs if kickoffs is not None else DEFAULT_GW_KICKOFFS
    stored: Dict[str, object] = {}
    parsed: Dict[int, List[datetime]] = {}
    for gw, val in src.items():
        items = val if isinstance(val, list) else [val]
        dts = [d for d in (_coerce_kickoff(v) for v in items) if d is not None]
        if not dts:
            continue
        dts.sort()
        parsed[int(gw)] = dts
        iso = [d.isoformat() for d in dts]
        stored[str(int(gw))] = iso if isinstance(val, list) else iso[0]
    db.collection("wc_config").document("schedule").set(
        {"kickoffs": stored}, merge=True)
    return parsed


def apply_schedule_to_fixtures(db) -> int:
    """Re-stamp every existing ``wc_fixtures`` doc's ``kickoff`` from the stored
    schedule (matching by GW, assigning multi-match GWs by fixture order).

    Idempotent; used to align fixtures already in the DB with the durable
    schedule without re-simulating. Returns the number of fixtures updated.
    """
    kickoffs = _load_schedule_kickoffs(db)
    if not kickoffs:
        return 0
    by_gw: Dict[int, List] = {}
    for fdoc in db.collection("wc_fixtures").get():
        gw = (fdoc.to_dict() or {}).get("gw")
        if gw is not None:
            by_gw.setdefault(int(gw), []).append(fdoc)
    updated = 0
    batch = db.batch()
    n = 0
    for gw, docs in by_gw.items():
        kos = kickoffs.get(gw)
        if not kos:
            continue
        docs.sort(key=lambda d: int((d.to_dict() or {}).get("id") or 0))
        for idx, fdoc in enumerate(docs):
            ko = kos[idx] if idx < len(kos) else kos[-1]
            batch.update(fdoc.reference, {"kickoff": ko})
            updated += 1
            n += 1
            if n % 400 == 0:
                batch.commit(); batch = db.batch()
    batch.commit()
    return updated

# Goal-count distribution for one team in one match (index == goals scored).
# Tuned so most matches land 0-3 with an occasional blowout.
_GOAL_WEIGHTS = (0.26, 0.34, 0.22, 0.11, 0.05, 0.02)  # 0,1,2,3,4,5

# Relative likelihood a given player is the SCORER / ASSISTER of a goal,
# by position. Forwards and midfielders dominate; keepers are ~never.
_SCORER_WEIGHT = {GK: 0.01, DEF: 0.12, MID: 0.37, FWD: 0.50}
_ASSIST_WEIGHT = {GK: 0.01, DEF: 0.18, MID: 0.46, FWD: 0.35}

# Probability a player on the pitch clears their DefCon threshold this match.
# "more % to def and mid" per the product spec.
_DEFCON_CLEAR_PROB = {GK: 0.04, DEF: 0.55, MID: 0.42, FWD: 0.12}

# Probability an assist is recorded for a given goal (some goals are solo).
_ASSIST_PROB = 0.72

# A starting XI shape used to decide who plays 90'. Falls back gracefully if a
# team doesn't have enough players in a slot.
_STARTER_SHAPE = {GK: 1, DEF: 4, MID: 3, FWD: 3}

# --- Team strength tiers ----------------------------------------------------
# Stronger nations should win more often so the mock World Cup looks plausible
# (no more Saudi Arabia lifting the trophy). Three tiers; a stronger tier beats
# a weaker one with the probability in `_TIER_WIN_PROB` (keyed by tier gap):
#   tier1 vs tier2 (gap 1) -> 70%   tier1 vs tier3 (gap 2) -> 80%
#   tier2 vs tier3 (gap 1) -> 70%   same tier            -> 50%
_TIER1 = {  # heavyweights — ~80% vs the weakest tier
    "spain", "brazil", "argentina", "france", "germany", "england",
    "belgium", "portugal",
}
_TIER2 = {  # strong — ~70% vs the weakest tier
    "canada", "morocco", "uruguay", "colombia", "senegal", "norway",
    "switzerland", "turkey", "usa", "croatia",
}
# Common name/iso spelling variants -> the canonical key used in the tier sets.
_TIER_ALIASES = {
    "columbia": "colombia", "swiss": "switzerland", "türkiye": "turkey",
    "turkiye": "turkey", "united states": "usa", "united states of america": "usa",
    "usmnt": "usa", "the netherlands": "netherlands",
}
# P(stronger team wins) by tier gap. Gap 0 (same tier) is a 50/50.
_TIER_WIN_PROB = {1: 0.70, 2: 0.80}


def team_tier(name: str) -> int:
    """Strength tier for a national team by name: 1 (best) .. 3 (weakest)."""
    key = (name or "").strip().lower()
    key = _TIER_ALIASES.get(key, key)
    if key in _TIER1:
        return 1
    if key in _TIER2:
        return 2
    return 3


def win_prob(home_tier: int, away_tier: int) -> float:
    """P(home team beats away team) from their tiers. Lower tier number = stronger.

    Symmetric: ``win_prob(a, b) == 1 - win_prob(b, a)``. Same tier -> 0.5.
    """
    gap = away_tier - home_tier  # >0 when home is the stronger side
    if gap == 0:
        return 0.5
    fav = _TIER_WIN_PROB.get(abs(gap), 0.85)
    return fav if gap > 0 else (1.0 - fav)


# ---------------------------------------------------------------------------
# PURE generation helpers (deterministic given `rng`)
# ---------------------------------------------------------------------------
# Goal counts for the winning / losing side once an outcome is decided.
_WIN_GOALS = (1, 2, 3, 4, 5)
_WIN_GOAL_WEIGHTS = (0.40, 0.32, 0.16, 0.08, 0.04)
# Even-score goal counts for a drawn group game.
_DRAW_GOALS = (0, 1, 2, 3)
_DRAW_GOAL_WEIGHTS = (0.34, 0.40, 0.20, 0.06)
# Baseline probability a group game ends level (knockout games never draw).
_GROUP_DRAW_PROB = 0.24


def simulate_scoreline(rng: random.Random, knockout: bool = False,
                       p_home_win: float = 0.5) -> Tuple[int, int]:
    """Return ``(home_goals, away_goals)``.

    The match OUTCOME is decided first — a draw (group games only) with
    probability ``_GROUP_DRAW_PROB``, otherwise the home side wins with
    probability ``p_home_win`` — and a plausible scoreline is sampled to match.
    ``p_home_win`` lets callers bias results by team strength (see
    :func:`win_prob`); the default 0.5 is an even contest. Knockout games are
    forced decisive (extra-time / penalties), so no draw is ever returned.
    """
    if not knockout and rng.random() < _GROUP_DRAW_PROB:
        g = rng.choices(_DRAW_GOALS, weights=_DRAW_GOAL_WEIGHTS)[0]
        return g, g
    win_g = rng.choices(_WIN_GOALS, weights=_WIN_GOAL_WEIGHTS)[0]
    lose_g = rng.randint(0, win_g - 1)
    if rng.random() < p_home_win:
        return win_g, lose_g
    return lose_g, win_g


def _pick_starting_eleven(players: List[Dict], rng: random.Random) -> List[int]:
    """Choose up to 11 player ids to start (90'), respecting a sane shape.

    ``players`` entries need ``id`` and ``position``. Returns a list of ids.
    """
    by_pos: Dict[int, List[Dict]] = {GK: [], DEF: [], MID: [], FWD: []}
    for p in players:
        by_pos.get(int(p["position"]), by_pos[MID]).append(p)
    for pos in by_pos:
        rng.shuffle(by_pos[pos])

    starters: List[int] = []
    for pos, n in _STARTER_SHAPE.items():
        starters.extend(int(p["id"]) for p in by_pos[pos][:n])

    # Top up to 11 from whoever's left (handles thin squads / odd shapes).
    if len(starters) < 11:
        chosen = set(starters)
        leftovers = [int(p["id"]) for p in players if int(p["id"]) not in chosen]
        rng.shuffle(leftovers)
        starters.extend(leftovers[: 11 - len(starters)])
    return starters[:11]


def _roll_minutes(position: int, is_starter: bool, rng: random.Random) -> int:
    """Realistic minutes: starters mostly 90 (some subbed off), a few subs come
    on for cameos, the rest are unused (0')."""
    if is_starter:
        r = rng.random()
        if r < 0.78:
            return 90
        if r < 0.92:
            return rng.randint(60, 89)   # subbed off after the hour
        return rng.randint(30, 59)       # early sub / injury
    # Bench: a minority appear as substitutes.
    if rng.random() < 0.28:
        return rng.randint(1, 35)
    return 0


def _roll_defcon(position: int, minutes: int, rng: random.Random) -> Dict[str, int]:
    """Per-player tackles/interceptions/blocks. Weighted so DEF (>=10) and MID
    (>=12) clear their DefCon threshold at the rates in ``_DEFCON_CLEAR_PROB``.
    GK/FWD get only incidental actions (DefCon doesn't apply to them anyway)."""
    if minutes <= 0:
        return {"total": 0, "interceptions": 0, "blocks": 0}

    clears = rng.random() < _DEFCON_CLEAR_PROB.get(position, 0.1)
    if position in (DEF, MID) and clears:
        target = 10 if position == DEF else 12
        total_actions = target + rng.randint(0, 4)
    else:
        total_actions = rng.randint(0, 7)

    # Split the actions across the three buckets.
    blocks = rng.randint(0, total_actions // 3)
    interceptions = rng.randint(0, (total_actions - blocks) // 2) if total_actions - blocks > 0 else 0
    tackles = max(0, total_actions - blocks - interceptions)
    return {"total": tackles, "interceptions": interceptions, "blocks": blocks}


def _weighted_player_choices(players: List[Dict], n: int, weight_map: Dict[int, float],
                             rng: random.Random) -> List[int]:
    """Pick ``n`` player ids (with replacement) weighted by position. Only
    players with minutes > 0 are eligible. Returns [] if no one is eligible."""
    eligible = [p for p in players if p.get("_minutes", 0) > 0]
    if not eligible or n <= 0:
        return []
    weights = [weight_map.get(int(p["position"]), 0.1) for p in eligible]
    chosen = rng.choices(eligible, weights=weights, k=n)
    return [int(p["id"]) for p in chosen]


def simulate_team_player_stats(players: List[Dict], goals_for: int,
                               rng: random.Random) -> List[Dict]:
    """Build the api-sports ``players`` list for ONE team in ONE fixture.

    ``players``: that team's roster, each ``{id, name, position}``. ``goals_for``
    is the team's scoreline so the individual ``goals`` reconcile with it.

    Returns the list of ``{"player": ..., "statistics": [...]}`` dicts. Note:
    goalsConceded / cleanSheet are NOT emitted — the engine derives them from the
    fixture score.
    """
    pool = [dict(p) for p in players]  # shallow copy; we annotate _minutes
    starters = set(_pick_starting_eleven(pool, rng))

    for p in pool:
        is_starter = int(p["id"]) in starters
        p["_minutes"] = _roll_minutes(int(p["position"]), is_starter, rng)

    # Distribute goals + assists across players who were on the pitch.
    goal_ids = _weighted_player_choices(pool, goals_for, _SCORER_WEIGHT, rng)
    goals_by_pid: Dict[int, int] = {}
    for pid in goal_ids:
        goals_by_pid[pid] = goals_by_pid.get(pid, 0) + 1

    assist_ids: List[int] = []
    for pid in goal_ids:
        if rng.random() < _ASSIST_PROB:
            # Assister can be anyone on the pitch except the scorer of THAT goal.
            cands = [p for p in pool if p.get("_minutes", 0) > 0 and int(p["id"]) != pid]
            if cands:
                weights = [_ASSIST_WEIGHT.get(int(p["position"]), 0.1) for p in cands]
                assist_ids.append(int(rng.choices(cands, weights=weights)[0]["id"]))
    assists_by_pid: Dict[int, int] = {}
    for pid in assist_ids:
        assists_by_pid[pid] = assists_by_pid.get(pid, 0) + 1

    out: List[Dict] = []
    for p in pool:
        pid = int(p["id"])
        pos = int(p["position"])
        minutes = p["_minutes"]

        goals_scored = goals_by_pid.get(pid, 0)
        assists_made = assists_by_pid.get(pid, 0)

        # A scorer/assister must have been on the pitch (guaranteed: only
        # minutes>0 players were eligible).
        if minutes <= 0:
            rating = 0.0
            tackles = {"total": 0, "interceptions": 0, "blocks": 0}
            saves = 0
        else:
            # Base rating ~6.0-7.5, boosted by goals/assists so scorers tend to
            # be the men of the match (drives the engine's 3/2/1 rating bonus).
            rating = round(6.0 + rng.uniform(0.0, 1.5)
                           + 0.8 * goals_scored + 0.4 * assists_made, 2)
            rating = min(rating, 10.0)
            tackles = _roll_defcon(pos, minutes, rng)
            saves = rng.randint(1, 6) if pos == GK else 0

        out.append({
            "player": {"id": pid, "name": p.get("name", "")},
            "statistics": [{
                "games": {"minutes": minutes, "rating": rating},
                "goals": {"total": goals_scored, "assists": assists_made,
                          "saves": saves, "conceded": 0, "owngoals": 0},
                "cards": {"yellow": 0, "red": 0},
                "penalty": {"missed": 0, "saved": 0},
                "tackles": tackles,
            }],
        })
    return out


def simulate_fixture(home_team_id: int, home_players: List[Dict],
                     away_team_id: int, away_players: List[Dict],
                     rng: random.Random, knockout: bool = False,
                     p_home_win: float = 0.5
                     ) -> Tuple[int, int, List[Dict]]:
    """Generate one fixture's scoreline + both teams' api-sports raw_stats.

    ``p_home_win`` biases the result toward the stronger side (see
    :func:`win_prob`); default 0.5 is an even contest.

    Returns ``(home_goals, away_goals, raw_stats)`` where ``raw_stats`` is the
    two-element list the scoring engine expects.
    """
    home_goals, away_goals = simulate_scoreline(rng, knockout=knockout,
                                                p_home_win=p_home_win)
    raw_stats = [
        {"team": {"id": home_team_id},
         "players": simulate_team_player_stats(home_players, home_goals, rng)},
        {"team": {"id": away_team_id},
         "players": simulate_team_player_stats(away_players, away_goals, rng)},
    ]
    return home_goals, away_goals, raw_stats


# ---------------------------------------------------------------------------
# Schedule helpers (pure)
# ---------------------------------------------------------------------------
def round_robin(team_ids: List[int]) -> List[List[Tuple[int, int]]]:
    """Single round-robin schedule via the circle method.

    Returns one list of ``(home, away)`` pairs per round. For a group of 4 this
    yields 3 rounds of 2 matches — i.e. each team plays the other three once,
    one game per matchday. An odd-sized group gets a bye each round.
    """
    ids = list(team_ids)
    if len(ids) % 2:
        ids.append(None)  # bye marker
    n = len(ids)
    rounds: List[List[Tuple[int, int]]] = []
    fixed = ids[0]
    rotating = ids[1:]
    for r in range(n - 1):
        order = [fixed] + rotating
        pairs: List[Tuple[int, int]] = []
        for i in range(n // 2):
            a, b = order[i], order[n - 1 - i]
            if a is None or b is None:
                continue
            # Alternate home/away by round for a touch of variety.
            pairs.append((a, b) if r % 2 == 0 else (b, a))
        rounds.append(pairs)
        rotating = rotating[-1:] + rotating[:-1]
    return rounds


def knockout_pairs(team_ids: List[int], rng: random.Random) -> List[Tuple[int, int]]:
    """Pair up surviving teams for a single-elimination round. Odd team out gets
    an implicit bye (handled by the caller — it isn't returned as a pair)."""
    ids = list(team_ids)
    rng.shuffle(ids)
    pairs = []
    for i in range(0, len(ids) - 1, 2):
        pairs.append((ids[i], ids[i + 1]))
    return pairs


# ===========================================================================
# DB DRIVER — reads teams/players, writes fixtures + raw stats, drives the
# real scoring engine. Everything below talks to Firestore.
# ===========================================================================
_KNOCKOUT_ROUND_NAMES = {
    32: "Round of 32", 16: "Round of 16", 8: "Quarter-final",
    4: "Semi-final", 2: "Final",
}


def _load_players_by_team(db) -> Dict[int, List[Dict]]:
    """player roster per team id, each entry ``{id, name, position}``."""
    by_team: Dict[int, List[Dict]] = {}
    for doc in db.collection("wc_players").get():
        d = doc.to_dict() or {}
        tid = int(d.get("teamId") or 0)
        by_team.setdefault(tid, []).append({
            "id": int(d.get("id") or int(doc.id)),
            "name": d.get("name", ""),
            "position": int(d.get("position") or MID),
        })
    return by_team


def _load_teams(db) -> List[Dict]:
    out = []
    for doc in db.collection("wc_teams").get():
        d = doc.to_dict() or {}
        out.append({
            "id": int(d.get("id") or int(doc.id)),
            "name": d.get("name", ""),
            "isoCode": d.get("isoCode", ""),
            "group": d.get("group", ""),
            "eliminated": bool(d.get("eliminated")),
        })
    return out


def _pos_map_and_rules(db) -> Tuple[Dict[int, int], Dict]:
    """Cache the player->position map + scoring rules once for a whole run, so
    ``process_fixture`` doesn't re-read 1000+ player docs per fixture."""
    pos_map: Dict[int, int] = {}
    for doc in db.collection("wc_players").get():
        d = doc.to_dict() or {}
        pos_map[int(d.get("id") or int(doc.id))] = int(d.get("position") or MID)
    cfg = db.collection("wc_config").document("tournament").get()
    rules = (cfg.to_dict() or {}).get("rules", {}) if cfg.exists else {}
    return pos_map, rules


def _write_fixture(db, fid: int, gw: int, round_name: str,
                   home: Dict, away: Dict, hg: int, ag: int,
                   kickoff=None):
    """Persist a wc_fixtures doc (real team ids + isoCodes so the engine resolves
    is_home/goals-conceded correctly and the WC group tables read the scoreline).

    The ``kickoff`` is DURABLE: use the scheduled time when given, else preserve
    the existing fixture's kickoff (so a re-sim never clobbers a real time), and
    only fall back to SERVER_TIMESTAMP when neither exists. See the
    ``wc_config/schedule`` note at the top of this module.
    """
    doc_ref = db.collection("wc_fixtures").document(str(fid))
    ko = kickoff
    if ko is None:
        existing = doc_ref.get()
        if existing.exists:
            ko = (existing.to_dict() or {}).get("kickoff")
    if ko is None:
        ko = SERVER_TIMESTAMP
    doc_ref.set({
        "id": fid,
        "gw": gw,
        "wcRound": round_name,
        "homeTeam": {"id": home["id"], "isoCode": home["isoCode"], "name": home["name"]},
        "awayTeam": {"id": away["id"], "isoCode": away["isoCode"], "name": away["name"]},
        "kickoff": ko,
        "status": "FT",
        "score": {"home": hg, "away": ag},
        "processedForFantasy": False,
    })


def _write_lineups(db, lid: str, gw: int):
    """Write a lineup doc for every league member for ``gw`` by running the same
    XI selection the seed uses against each manager's current squad."""
    league_ref = db.collection("leagues").document(lid)
    for mdoc in league_ref.collection("members").get():
        uid = mdoc.id
        squad_doc = league_ref.collection("squads").document(uid).get()
        if not squad_doc.exists:
            continue
        squad = (squad_doc.to_dict() or {}).get("players", [])
        if len(squad) < 15:
            continue
        lineup = select_lineup(squad)
        league_ref.collection("lineups").document(f"{uid}_{gw}").set(lineup)


def simulate_gw(db, lid: str, gw: int, rng: random.Random, *,
                teams: List[Dict], players_by_team: Dict[int, List[Dict]],
                pos_map: Dict[int, int], rules: Dict, wc_client,
                group_schedule: Optional[Dict[int, List[Tuple[int, int]]]] = None,
                kickoffs: Optional[Dict[int, List[datetime]]] = None
                ) -> Dict:
    """Generate, score and finalize ONE gameweek.

    Group GWs (those in ``group_schedule``) play the pre-built round-robin.
    Knockout GWs pair the surviving (non-eliminated) teams, force a decisive
    result, and eliminate the losers. Then the real engine finalizes the GW
    (auto-subs, H2H/bonus, standings, gw_history, league bracket).
    """
    teams_by_id = {t["id"]: t for t in teams}
    league_ref = db.collection("leagues").document(lid)
    knockout = group_schedule is None or gw not in group_schedule

    if not knockout:
        pairs = list(group_schedule[gw])
        round_name = f"Group Stage · MD{gw}"
    else:
        # Refresh elimination flags from the DB before pairing. The in-memory
        # `teams` list is loaded once per tournament, so it would otherwise miss
        # the GW3 group-stage eliminations (written to wc_teams by the engine's
        # detect_group_stage_eliminations) and any prior knockout eliminations.
        elim = {int(d.id): bool((d.to_dict() or {}).get("eliminated"))
                for d in db.collection("wc_teams").get()}
        for t in teams:
            if t["id"] in elim:
                teams_by_id[t["id"]]["eliminated"] = elim[t["id"]]
        survivors = [t["id"] for t in teams if not teams_by_id[t["id"]]["eliminated"]]
        pairs = knockout_pairs(survivors, rng)
        round_name = _KNOCKOUT_ROUND_NAMES.get(len(survivors), f"Knockout · GW{gw}")

    fid_base = gw * 1000
    gw_kos = (kickoffs or {}).get(gw) or []
    eliminated_this_gw: List[int] = []
    for idx, (home_id, away_id) in enumerate(pairs):
        home, away = teams_by_id[home_id], teams_by_id[away_id]
        # Bias the result by relative team strength so heavyweights advance.
        p_home = win_prob(team_tier(home.get("name", "")),
                          team_tier(away.get("name", "")))
        hg, ag, raw_stats = simulate_fixture(
            home_id, players_by_team.get(home_id, []),
            away_id, players_by_team.get(away_id, []),
            rng, knockout=knockout, p_home_win=p_home,
        )
        # Durable kickoff: scheduled time for this match (by fixture order),
        # else None -> _write_fixture preserves any existing time.
        ko = gw_kos[idx] if idx < len(gw_kos) else (gw_kos[-1] if gw_kos else None)
        _write_fixture(db, fid_base + idx, gw, round_name, home, away, hg, ag,
                       kickoff=ko)
        process_fixture(fid_base + idx, raw_stats, wc_client, db,
                        pos_map=pos_map, rules=rules)

        if knockout:
            loser_id = away_id if hg > ag else home_id
            eliminated_this_gw.append(loser_id)

    # Knockout: mark losing teams (and their players) eliminated so the WC
    # tables + UI reflect who's out. (Group eliminations are handled by the
    # engine's detect_group_stage_eliminations at GW3 finalize.)
    if knockout and eliminated_this_gw:
        for tid in eliminated_this_gw:
            teams_by_id[tid]["eliminated"] = True
            if wc_client is not None:
                try:
                    wc_client.mark_knockout_elimination(tid, gw, db=db)
                except Exception as exc:  # noqa: BLE001 — best-effort in a mock
                    print(f"[warn] mark_knockout_elimination({tid}) failed: {exc}")
        # Mark that team's players eliminated too (greys them out in the UI).
        batch = db.batch()
        n = 0
        for pdoc in db.collection("wc_players").get():
            if int((pdoc.to_dict() or {}).get("teamId") or 0) in set(eliminated_this_gw):
                batch.update(pdoc.reference, {"eliminated": True})
                n += 1
                if n % 400 == 0:
                    batch.commit(); batch = db.batch()
        batch.commit()

    _write_lineups(db, lid, gw)
    league_ref.update({"currentGw": gw})
    finalize_gw(lid, gw, db, wc_client)
    return {"gw": gw, "matches": len(pairs), "knockout": knockout,
            "eliminated": eliminated_this_gw}


def build_group_schedule(teams: List[Dict]) -> Dict[int, List[Tuple[int, int]]]:
    """Build the GW1-3 group-stage schedule (one matchday per GW) for every
    group, using a round-robin within each group of 4."""
    groups: Dict[str, List[int]] = {}
    for t in teams:
        if t.get("group"):
            groups.setdefault(t["group"], []).append(t["id"])
    schedule: Dict[int, List[Tuple[int, int]]] = {1: [], 2: [], 3: []}
    for _grp, ids in sorted(groups.items()):
        ids.sort()
        for md_idx, pairs in enumerate(round_robin(ids), start=1):
            if md_idx in schedule:
                schedule[md_idx].extend(pairs)
    return schedule


def reset_simulation(db, lid: str):
    """Wipe prior scoring state so a fresh tournament can be generated:
    delete all wc_fixtures, reset wc_players (totalPoints=0, eliminated=False),
    reset wc_teams elimination flags, and clear the league's scoring
    subcollections (scores/standings/gw_history/lineups/knockout/transfer_windows).
    Members, squads and the H2H schedule are preserved.
    """
    # wc_fixtures — also delete each fixture's playerScores subcollection.
    # Firestore does NOT cascade-delete subcollections when the parent doc is
    # removed; orphaned playerScores would otherwise still be returned by the
    # /players/{id}/scores collection-group query (duplicate/stale history rows).
    batch = db.batch(); n = 0
    for fdoc in db.collection("wc_fixtures").get():
        for sdoc in fdoc.reference.collection("playerScores").get():
            batch.delete(sdoc.reference); n += 1
            if n % 400 == 0:
                batch.commit(); batch = db.batch()
        batch.delete(fdoc.reference); n += 1
        if n % 400 == 0:
            batch.commit(); batch = db.batch()
    batch.commit()

    # wc_players
    batch = db.batch(); n = 0
    for pdoc in db.collection("wc_players").get():
        batch.update(pdoc.reference, {"totalPoints": 0, "eliminated": False}); n += 1
        if n % 400 == 0:
            batch.commit(); batch = db.batch()
    batch.commit()

    # wc_teams
    batch = db.batch(); n = 0
    for tdoc in db.collection("wc_teams").get():
        batch.update(tdoc.reference, {"eliminated": False, "eliminatedAfterGw": None,
                                      "status": "active", "groupFinished": False}); n += 1
        if n % 400 == 0:
            batch.commit(); batch = db.batch()
    batch.commit()

    # league scoring subcollections
    league_ref = db.collection("leagues").document(lid)
    for sub in ["scores", "standings", "gw_history", "lineups", "knockout",
                "transfer_windows"]:
        coll = league_ref.collection(sub)
        for doc in coll.get():
            doc.reference.delete()
    league_ref.update({"currentGw": 1, "status": "group_phase"})


def simulate_tournament(db, lid: str, *, seed: Optional[int] = None,
                        start_gw: int = 1, end_gw: int = 8,
                        reset: bool = True, wc_client=None) -> Dict:
    """Generate the whole World Cup (GW ``start_gw``..``end_gw``) for league
    ``lid`` and drive every GW through the real scoring engine.

    Returns a summary dict and persists a per-tournament export at
    ``leagues/{lid}/simulation/export`` (see :func:`build_tournament_export`).
    """
    rng = random.Random(seed)
    if wc_client is None:
        from fpl_predictor.seed.seed_league import _seed_wc_client
        wc_client = _seed_wc_client(db)

    if reset:
        reset_simulation(db, lid)

    teams = _load_teams(db)
    players_by_team = _load_players_by_team(db)
    pos_map, rules = _pos_map_and_rules(db)
    group_schedule = build_group_schedule(teams)
    kickoffs = _load_schedule_kickoffs(db)

    per_gw = []
    for gw in range(start_gw, end_gw + 1):
        res = simulate_gw(db, lid, gw, rng, teams=teams,
                          players_by_team=players_by_team, pos_map=pos_map,
                          rules=rules, wc_client=wc_client,
                          group_schedule=group_schedule, kickoffs=kickoffs)
        per_gw.append(res)
        print(f"  ✓ GW{gw}: {res['matches']} matches"
              + (f", {len(res['eliminated'])} eliminated" if res["knockout"] else ""))

    export = build_tournament_export(db, lid)
    return {"league": lid, "seed": seed, "gws": per_gw, "export": export}


def simulate_one_gw(db, lid: str, *, gw: Optional[int] = None,
                    seed: Optional[int] = None, end_gw: int = 8,
                    wc_client=None) -> Dict:
    """Generate, score and finalize a SINGLE gameweek — the "play next week"
    button. ``gw`` defaults to the league's ``currentGw`` (the next unplayed
    GW). Loads everything ``simulate_gw`` needs, runs one GW, refreshes the
    tournament export, and reports the new ``currentGw``.

    Returns ``{"done": True, ...}`` (no-op) once the tournament is finished.
    """
    league_ref = db.collection("leagues").document(lid)
    league_doc = league_ref.get().to_dict() or {}
    if gw is None:
        gw = int(league_doc.get("currentGw", 1) or 1)
    if gw > end_gw:
        return {"done": True, "gw": gw, "currentGw": gw,
                "message": f"Tournament complete (GW{end_gw} was the last)."}

    if wc_client is None:
        from fpl_predictor.seed.seed_league import _seed_wc_client
        wc_client = _seed_wc_client(db)
    # Vary the RNG per GW even when a fixed seed is supplied, so stepping
    # week-by-week doesn't replay correlated scorelines.
    rng = random.Random(None if seed is None else seed * 1000 + gw)

    teams = _load_teams(db)
    players_by_team = _load_players_by_team(db)
    pos_map, rules = _pos_map_and_rules(db)
    group_schedule = build_group_schedule(teams)
    kickoffs = _load_schedule_kickoffs(db)

    res = simulate_gw(db, lid, gw, rng, teams=teams,
                      players_by_team=players_by_team, pos_map=pos_map,
                      rules=rules, wc_client=wc_client,
                      group_schedule=group_schedule, kickoffs=kickoffs)
    export = build_tournament_export(db, lid)
    new_cur = int((league_ref.get().to_dict() or {}).get("currentGw", gw))
    return {"done": False, "gw": gw, "currentGw": new_cur,
            "matches": res["matches"], "knockout": res["knockout"],
            "eliminated": res["eliminated"],
            "managers": export.get("managers", {})}


def build_tournament_export(db, lid: str) -> Dict:
    """Read back the finalized data into a compact, navigable export:

      * ``managers``: per-manager cumulative ``totalPoints`` (fantasy), total
        ``h2hPoints`` (3/1/0 + the +1 best-manager-in-GW bonus), ``rank``,
        ``qualified``, and per-GW points (``gwPoints``).
      * ``gws``: per-GW ``{uid: points}`` plus the GW ``winner(s)``.

    Persisted to ``leagues/{lid}/simulation/export`` and returned.
    """
    league_ref = db.collection("leagues").document(lid)

    standings_doc = league_ref.collection("standings").document("current").get()
    managers_raw = (standings_doc.to_dict() or {}).get("managers", []) if standings_doc.exists else []
    managers = {
        m["uid"]: {
            "displayName": m.get("displayName", ""),
            "teamName": m.get("teamName", ""),
            "totalPoints": m.get("fpts", 0),
            "h2hPoints": m.get("hpts", 0),
            "rank": m.get("rank"),
            "qualified": m.get("qualified"),
            "gwPoints": m.get("gwPoints", {}),
        }
        for m in managers_raw
    }

    gws: Dict[str, Dict] = {}
    for sdoc in league_ref.collection("scores").get():
        try:
            gw_int = int(sdoc.id)
        except ValueError:
            continue
        results = (sdoc.to_dict() or {}).get("results", {})
        points = {uid: r.get("points", 0) for uid, r in results.items()}
        winner = []
        if points:
            top = max(points.values())
            winner = [uid for uid, p in points.items() if p == top]
        gws[str(gw_int)] = {"results": points, "winner": winner}

    export = {
        "league": lid,
        "managers": managers,
        "gws": gws,
        "generatedAt": SERVER_TIMESTAMP,
    }
    league_ref.collection("simulation").document("export").set(export)
    return export
