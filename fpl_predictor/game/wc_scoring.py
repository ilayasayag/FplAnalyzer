"""
WC2026 scoring engine.

Computes fantasy points per player per fixture, applies captain bonus,
handles auto-substitutions, and finalizes GW scores.
"""

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from google.cloud.firestore_v1 import SERVER_TIMESTAMP

POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

# ---------------------------------------------------------------------------
# Scoring table (indexed by position int: 1=GK, 2=DEF, 3=MID, 4=FWD)
# ---------------------------------------------------------------------------

APPEAR_UNDER_60  = 1   # same for all
APPEAR_60_PLUS   = 2   # same for all (replaces the under-60 point)

GOAL_POINTS   = {1: 10, 2: 6, 3: 5, 4: 4}
ASSIST_POINTS = 3  # same for all
CS_POINTS     = {1: 4, 2: 4, 3: 1, 4: 0}
GC_POINTS_PER_2 = {1: -1, 2: -1, 3: 0, 4: 0}  # per 2 goals conceded

YELLOW_CARD_POINTS = -1
RED_CARD_POINTS    = -3
OWN_GOAL_POINTS    = -2
PENALTY_MISS_POINTS = -2
PENALTY_SAVE_POINTS = 5    # GK only, in-play only
SAVES_PER_POINT_GK  = 3   # 1 point per 3 in-play saves (GK only)

# Defensive Contribution (DefCon): all-or-nothing award.
# defCon = tackles.total + tackles.interceptions + tackles.blocks
DEFCON_POINTS         = 2
DEFCON_THRESHOLD_DEF  = 10  # DEF (position==2)
DEFCON_THRESHOLD_MID  = 12  # MID (position==3)

# Bonus by rating rank: top-3 by api-sports games.rating get 3/2/1.
BONUS_BY_RATING_RANK = [3, 2, 1]

VALID_FORMATIONS = [
    (1, 3, 5, 2), (1, 3, 4, 3), (1, 4, 5, 1),
    (1, 4, 4, 2), (1, 4, 3, 3), (1, 5, 4, 1),
    (1, 5, 3, 2),
]


# ---------------------------------------------------------------------------
# Per-player point calculation
# ---------------------------------------------------------------------------

def compute_player_points(stats: Dict, position: int, rules: Optional[Dict] = None) -> Tuple[int, int]:
    """
    Compute fantasy points for one player in one fixture.

    stats keys (all default to 0/False if absent):
      minutes, goals, assists, saves, cleanSheet, goalsConceded,
      yellowCards, redCards, penaltyMissed, penaltySaved, ownGoal,
      tackles ({total, interceptions, blocks} for DefCon)

    Returns (base_points, bonus_points).
    Bonus is computed separately via compute_rating_bonus().
    """
    minutes = stats.get("minutes") or 0
    if minutes == 0:
        return 0, 0

    rules = rules or {}
    scoring_rules = rules.get("scoring", {})

    appear_under_60 = scoring_rules.get("appearUnder60", APPEAR_UNDER_60)
    appear_60_plus = scoring_rules.get("appear60Plus", APPEAR_60_PLUS)

    pts = appear_under_60

    if minutes >= 60:
        pts = appear_60_plus

    # Position-based mappings
    goal_points_raw = scoring_rules.get("goalPoints", GOAL_POINTS)
    goal_points = {int(k): v for k, v in goal_points_raw.items()} if isinstance(goal_points_raw, dict) else GOAL_POINTS

    assist_points = scoring_rules.get("assistPoints", ASSIST_POINTS)

    cs_points_raw = scoring_rules.get("csPoints", CS_POINTS)
    cs_points = {int(k): v for k, v in cs_points_raw.items()} if isinstance(cs_points_raw, dict) else CS_POINTS

    gc_points_per_2_raw = scoring_rules.get("gcPointsPer2", GC_POINTS_PER_2)
    gc_points_per_2 = {int(k): v for k, v in gc_points_per_2_raw.items()} if isinstance(gc_points_per_2_raw, dict) else GC_POINTS_PER_2

    yellow_card_points = scoring_rules.get("yellowCardPoints", YELLOW_CARD_POINTS)
    red_card_points = scoring_rules.get("redCardPoints", RED_CARD_POINTS)
    own_goal_points = scoring_rules.get("ownGoalPoints", OWN_GOAL_POINTS)
    penalty_miss_points = scoring_rules.get("penaltyMissPoints", PENALTY_MISS_POINTS)
    penalty_save_points = scoring_rules.get("penaltySavePoints", PENALTY_SAVE_POINTS)
    saves_per_point_gk = scoring_rules.get("savesPerPointGk", SAVES_PER_POINT_GK)

    defcon_points = scoring_rules.get("defConPoints", DEFCON_POINTS)
    defcon_threshold_def = scoring_rules.get("defConThresholdDef", DEFCON_THRESHOLD_DEF)
    defcon_threshold_mid = scoring_rules.get("defConThresholdMid", DEFCON_THRESHOLD_MID)

    # Goals
    goals = stats.get("goals", 0) or 0
    pts += goals * goal_points.get(position, 4)

    # Assists
    assists = stats.get("assists", 0) or 0
    pts += assists * assist_points

    # Clean sheet (only if played ≥ 60 min)
    if minutes >= 60 and stats.get("cleanSheet", False):
        pts += cs_points.get(position, 0)

    # Goals conceded (GK and DEF only; not if clean sheet)
    if not stats.get("cleanSheet", False):
        gc = stats.get("goalsConceded", 0) or 0
        gc_pen = gc_points_per_2.get(position, 0)
        if gc_pen < 0:
            pts += (gc // 2) * gc_pen   # floor division

    # Cards
    yellow = stats.get("yellowCards", 0) or 0
    red = stats.get("redCards", 0) or 0
    pts += yellow * yellow_card_points
    pts += red * red_card_points

    # Own goals
    own_goals = stats.get("ownGoal", 0) or 0
    pts += own_goals * own_goal_points

    # Penalty miss
    pen_miss = stats.get("penaltyMissed", 0) or 0
    pts += pen_miss * penalty_miss_points

    # GK-only: saves + penalty saves
    if position == 1:
        saves = stats.get("saves", 0) or 0
        pts += (saves // saves_per_point_gk)

        pen_saved = stats.get("penaltySaved", 0) or 0
        pts += pen_saved * penalty_save_points

    # Defensive Contribution (DefCon): all-or-nothing.
    # defCon = tackles.total + tackles.interceptions + tackles.blocks.
    # DEF awarded at >= defcon_threshold_def, MID at >= defcon_threshold_mid.
    # No award for GK (1) or FWD (4).
    if position in (2, 3):
        tackles = stats.get("tackles") or {}
        def_con = ((tackles.get("total") or 0)
                   + (tackles.get("interceptions") or 0)
                   + (tackles.get("blocks") or 0))
        threshold = defcon_threshold_def if position == 2 else defcon_threshold_mid
        if def_con >= threshold:
            pts += defcon_points

    return pts, 0  # bonus is added separately



def compute_rating_bonus(rating_list: List[Tuple[int, float]]) -> Dict[int, int]:
    """
    Award 3/2/1 bonus points to the top 3 players by api-sports games.rating
    in a fixture. This is the ONE bonus award per fixture set.

    rating_list: [(player_id, rating_float), ...]
    Returns: {player_id: bonus_points (3, 2, or 1)}

    Players with no/zero rating get no bonus.
    Ties: both players at a tied rank receive the higher award.
    e.g. two players tied for 2nd both get 2pts; the 4th-place player gets 0.
    """
    # Drop players with no/zero rating (no bonus eligibility).
    rated = [(pid, r) for pid, r in rating_list if r]
    sorted_ratings = sorted(rated, key=lambda x: -x[1])
    bonuses: Dict[int, int] = {}

    award_map = {0: 3, 1: 2, 2: 1}  # rank (0-based) → bonus

    i = 0
    rank = 0
    while i < len(sorted_ratings) and rank < 3:
        pid, rating_val = sorted_ratings[i]
        bonus = award_map.get(rank, 0)
        bonuses[pid] = bonus

        # Advance through ties
        j = i + 1
        while j < len(sorted_ratings) and sorted_ratings[j][1] == rating_val:
            tied_pid = sorted_ratings[j][0]
            bonuses[tied_pid] = bonus
            j += 1

        rank += (j - i)
        i = j

    return bonuses


# ---------------------------------------------------------------------------
# Captain / vice-captain bonus
# ---------------------------------------------------------------------------

def resolve_captain_bonus(
    lineup: Dict,
    player_minutes: Dict[int, int],
    player_base_points: Dict[int, int],
) -> Tuple[Optional[int], int]:
    """
    Resolve captain bonus for a manager's lineup. Disabled in this game.
    """
    return None, 0


# ---------------------------------------------------------------------------
# Auto-substitutions
# ---------------------------------------------------------------------------

def apply_auto_subs(
    starting: List[int],
    bench: List[int],
    player_minutes: Dict[int, int],
    player_position: Dict[int, int],
) -> Tuple[List[int], List[int], List[Dict]]:
    """
    Apply auto-substitutions after a GW completes.

    bench[0] must be GK; only substitutes for a non-playing GK.
    bench[1..3] = outfield; substitute for any non-playing outfield starter
                  in order, subject to valid formation.

    Returns (new_starting, new_bench, subs_made).
    subs_made: [{"out": pid, "in": pid}]
    """
    starting = list(starting)
    bench = list(bench)
    subs_made = []

    def formation(starters):
        counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for pid in starters:
            pos = player_position.get(pid, 3)
            counts[pos] = counts.get(pos, 0) + 1
        return tuple(counts[i] for i in (1, 2, 3, 4))

    for i, pid in enumerate(starting):
        if (player_minutes.get(pid, 0) or 0) >= 1:
            continue  # player played

        pos = player_position.get(pid, 3)

        for j, bench_pid in enumerate(bench):
            bench_pos = player_position.get(bench_pid, 3)

            # bench[0] (GK) can only replace starting GK
            if j == 0 and bench_pos != 1:
                continue
            if j == 0 and pos != 1:
                continue

            # Outfield bench slots cannot sub in for GK
            if j > 0 and bench_pos == 1:
                continue

            if (player_minutes.get(bench_pid, 0) or 0) == 0:
                continue  # bench player also didn't play

            test = starting.copy()
            test[i] = bench_pid
            if formation(test) in VALID_FORMATIONS:
                starting[i] = bench_pid
                bench.pop(j)
                subs_made.append({"out": pid, "in": bench_pid})
                break

    return starting, bench, subs_made


# ---------------------------------------------------------------------------
# Fixture processing
# ---------------------------------------------------------------------------

def process_fixture(
    fixture_id: int,
    raw_stats: List[Dict],
    wc_client,
    db,
    pos_map: Optional[Dict[int, int]] = None,
    rules: Optional[Dict] = None,
) -> Dict[int, Dict]:
    """
    Compute and persist fantasy points for one completed fixture.

    raw_stats: response from wc_client.get_fixture_player_stats(fixture_id)
    Returns {player_id: {fantasyPoints, stats, bonusPoints}}.

    ``pos_map`` (player_id -> position) and ``rules`` may be supplied by callers
    that process many fixtures in a row (e.g. the tournament simulator) to avoid
    re-reading the entire ``wc_players`` collection and the config doc on every
    fixture. When omitted they are loaded from Firestore exactly as before, so
    existing callers are unaffected.
    """
    # Build per-player stat dicts
    player_stats: Dict[int, Dict] = {}
    rating_list: List[Tuple[int, float]] = []

    home_goals = 0
    away_goals = 0

    fixture_doc = db.collection("wc_fixtures").document(str(fixture_id)).get()

    # Idempotency guard (EP2-W1/W3): a fixture already marked processedForFantasy
    # must not be re-scored. Re-running would double-count both the per-player
    # playerScores write AND the wc_players.totalPoints season Increment below,
    # and would re-fire the league propagation increments. Early-return so every
    # downstream Increment is fired at most once per fixture.
    if fixture_doc.exists and fixture_doc.to_dict().get("processedForFantasy"):
        return {}

    if fixture_doc.exists:
        score = fixture_doc.to_dict().get("score", {})
        home_goals = score.get("home") or 0
        away_goals = score.get("away") or 0

    for team_data in raw_stats:
        team = team_data.get("team", {})
        team_id = team.get("id")
        is_home = fixture_doc.to_dict().get("homeTeam", {}).get("id") == team_id if fixture_doc.exists else False
        goals_conceded = away_goals if is_home else home_goals

        for player in team_data.get("players", []):
            p_info = player.get("player", {})
            pid = p_info.get("id")
            if not pid:
                continue

            raw = player.get("statistics", [{}])[0]
            games = raw.get("games", {})
            goals = raw.get("goals", {})
            cards = raw.get("cards", {})
            penalty = raw.get("penalty", {})
            tackles_raw = raw.get("tackles", {}) or {}

            minutes = games.get("minutes") or 0
            rating = games.get("rating")
            goals_scored = goals.get("total") or 0
            assists = goals.get("assists") or 0
            saves = goals.get("saves") or 0
            own_goals = goals.get("owngoals") or 0
            yellow = cards.get("yellow") or 0
            red = cards.get("red") or 0
            pen_miss = penalty.get("missed") or 0
            pen_saved = penalty.get("saved") or 0

            tackles = {
                "total": tackles_raw.get("total") or 0,
                "interceptions": tackles_raw.get("interceptions") or 0,
                "blocks": tackles_raw.get("blocks") or 0,
            }

            clean_sheet = (goals_conceded == 0) and (minutes >= 60)

            stats = {
                "minutes": minutes,
                "goals": goals_scored,
                "assists": assists,
                "saves": saves,
                "cleanSheet": clean_sheet,
                "goalsConceded": goals_conceded,
                "yellowCards": yellow,
                "redCards": red,
                "penaltyMissed": pen_miss,
                "penaltySaved": pen_saved,
                "ownGoal": own_goals,
                "tackles": tackles,
                "bonusPoints": 0,
            }
            player_stats[pid] = {
                "stats": stats,
                "teamId": team_id,
                "name": p_info.get("name", ""),
            }

            # api-sports rating arrives as a string (e.g. "7.2"); coerce safely.
            try:
                rating_val = float(rating) if rating is not None else 0.0
            except (TypeError, ValueError):
                rating_val = 0.0
            if rating_val and minutes > 0:
                rating_list.append((pid, rating_val))

    # Get player positions from Firestore (unless the caller supplied a cache).
    if pos_map is None:
        pos_map = {}
        player_docs = db.collection("wc_players").get()
        for doc in player_docs:
            d = doc.to_dict()
            pos_map[d.get("id", 0)] = d.get("position", 3)

    # Compute rating-rank bonuses (one award set per fixture)
    bonuses = compute_rating_bonus(rating_list)

    # Load custom rules from Firestore config (unless the caller supplied them).
    if rules is None:
        config_doc = db.collection("wc_config").document("tournament").get()
        rules = config_doc.to_dict().get("rules", {}) if config_doc.exists else {}

    gw = fixture_doc.to_dict().get("gw", 1) if fixture_doc.exists else 1

    # Compute points and persist
    from google.cloud.firestore_v1 import Increment

    results: Dict[int, Dict] = {}
    batch = db.batch()

    for pid, pdata in player_stats.items():
        pos = pos_map.get(pid, 3)
        base_pts, _ = compute_player_points(pdata["stats"], pos, rules)

        bonus = bonuses.get(pid, 0)
        total_pts = base_pts + bonus

        pdata["stats"]["bonusPoints"] = bonus
        result = {
            "playerId": pid,
            "gw": gw,
            # fantasyPoints already INCLUDES the rating bonus (base_pts + bonus).
            "fantasyPoints": total_pts,
            "bonusPoints": bonus,
            "stats": pdata["stats"],
        }
        results[pid] = result

        score_ref = (db.collection("wc_fixtures").document(str(fixture_id))
                     .collection("playerScores").document(str(pid)))
        batch.set(score_ref, result)

        # EP2-W1: aggregate the player's season total onto wc_players.totalPoints.
        # The delta is this fixture's total = fantasyPoints (which ALREADY folds
        # in the bonus). Adding bonusPoints again would double-count the bonus.
        # Atomic Increment so concurrent fixture processing is safe; the
        # processedForFantasy early-return above makes this fire at most once.
        if total_pts:
            player_ref = db.collection("wc_players").document(str(pid))
            batch.set(player_ref, {"totalPoints": Increment(total_pts)}, merge=True)

    # Mark fixture as processed
    fixture_ref = db.collection("wc_fixtures").document(str(fixture_id))
    batch.update(fixture_ref, {"processedForFantasy": True})

    batch.commit()

    # Propagate to leagues
    _propagate_to_leagues(fixture_id, results, db)

    return results


def _propagate_to_leagues(
    fixture_id: int,
    player_points: Dict[int, Dict],
    db,
):
    """
    Update running GW scores in all active leagues for players in this fixture.

    EP2-W3 — set-vs-increment decision: this is an INCREMENT (accrual) path,
    intentionally. Fixtures within a GW land independently/concurrently, so each
    contributes its delta to a running ``scores/{gw}.results.{uid}.points`` live
    total via an atomic ``Increment``. A SET here would be wrong: it would clobber
    the contributions of fixtures already processed for the same GW.

    Idempotency is enforced UPSTREAM, not here: ``process_fixture`` early-returns
    when the fixture is already ``processedForFantasy``, so this function fires at
    most once per fixture and can never double-accrue.

    The ``if delta:`` guard is therefore safe: a net-zero contribution adds
    nothing, and skipping the write leaves no stale value because this running
    total is NOT the authoritative figure. ``finalize_gw`` re-derives each
    manager's points from scratch (post-autosub) and writes them with an absolute
    ``scores_ref.set({"results": {uid: {"points": ...}}}, merge=True)``, which
    fully OVERWRITES the running total. That finalize SET is what makes the GW
    self-correcting and re-finalize-idempotent — any drift in the live accrual is
    discarded at finalize.
    """
    from google.cloud.firestore_v1 import Increment

    fixture_player_ids = set(player_points.keys())

    active_leagues = db.collection("leagues").where("status", "==", "group_phase").get()
    active_leagues += db.collection("leagues").where("status", "==", "knockout").get()

    for league_doc in active_leagues:
        lid = league_doc.id
        league = league_doc.to_dict()
        gw = league.get("currentGw", 1)

        for squad_doc in db.collection("leagues").document(lid).collection("squads").get():
            uid = squad_doc.id
            players = squad_doc.to_dict().get("players", [])
            squad_ids = {p["playerId"] for p in players}

            lineup_doc = (db.collection("leagues").document(lid)
                          .collection("lineups").document(f"{uid}_{gw}").get())
            if not lineup_doc.exists:
                continue

            lineup = lineup_doc.to_dict()
            if lineup.get("locked") and not lineup.get("autoSubsMade"):
                # GW not complete yet — accrue points for starters
                starting = set(lineup.get("starting", []))
            else:
                starting = set(lineup.get("starting", []))

            delta = 0
            for pid in starting:
                if pid in fixture_player_ids:
                    delta += player_points[pid].get("fantasyPoints", 0)

            if delta:
                score_ref = (db.collection("leagues").document(lid)
                             .collection("scores").document(str(gw)))
                score_ref.set(
                    {f"results.{uid}.points": Increment(delta)},
                    merge=True,
                )


# ---------------------------------------------------------------------------
# GW finalization
# ---------------------------------------------------------------------------

def finalize_gw(lid: str, gw: int, db, wc_client) -> Dict:
    """
    Full GW finalization flow:
    1. Verify all fixtures processed
    2. Apply auto-subs + captain bonus for all managers
    3. Record H2H results (if league phase)
    4. Update standings
    5. Mark GW complete
    6. Detect eliminations
    7. Open transfer window
    8. Seed knockout (if last league GW)
    9. Advance knockout bracket (if knockout GW)
    10. Advance currentGw
    """
    league_ref = db.collection("leagues").document(lid)
    league = league_ref.get().to_dict()
    league_phase_gws = league.get("leaguePhaseGws", [1, 2, 3])
    knockout_start_gw = league.get("knockoutStartGw", 4)

    # Step 1: all fixtures processed?
    gw_fixtures = db.collection("wc_fixtures").where("gw", "==", gw).get()
    unprocessed = [f.id for f in gw_fixtures if not f.to_dict().get("processedForFantasy")]
    if unprocessed:
        raise ValueError(f"Fixtures not yet processed for fantasy: {unprocessed}")

    # Build full GW player points: player_id -> {fantasyPoints, stats}
    all_player_points: Dict[int, int] = {}
    all_player_minutes: Dict[int, int] = {}
    # EP2-W2: carry per-player per-GW stats through to the gw_history snapshot
    # so the frontend modal can reconcile each player's points breakdown.
    all_player_stats: Dict[int, Dict] = {}
    for fixture_doc in gw_fixtures:
        fid = fixture_doc.id
        score_docs = (db.collection("wc_fixtures").document(fid)
                      .collection("playerScores").get())
        for pdoc in score_docs:
            pid = int(pdoc.id)
            pdata = pdoc.to_dict()
            all_player_points[pid] = all_player_points.get(pid, 0) + pdata.get("fantasyPoints", 0)
            all_player_minutes[pid] = all_player_minutes.get(pid, 0) + (pdata.get("stats", {}).get("minutes") or 0)
            # A player appears in at most one fixture per GW; last-write is fine.
            all_player_stats[pid] = pdata.get("stats", {}) or {}

    # Get position map
    pos_map: Dict[int, int] = {}
    player_docs = db.collection("wc_players").get()
    for doc in player_docs:
        d = doc.to_dict()
        pos_map[int(doc.id)] = d.get("position", 3)

    members = list(league_ref.collection("members").get())
    uid_list = [m.id for m in members]

    scores_ref = league_ref.collection("scores").document(str(gw))
    scores_doc = scores_ref.get()
    current_scores = scores_doc.to_dict().get("results", {}) if scores_doc.exists else {}

    # Step 2: auto-subs + captain bonus
    for uid in uid_list:
        doc_id = f"{uid}_{gw}"
        lineup_ref = league_ref.collection("lineups").document(doc_id)
        lineup_doc = lineup_ref.get()
        if not lineup_doc.exists:
            continue

        lineup = lineup_doc.to_dict()
        starting = lineup.get("starting", [])
        bench = lineup.get("bench", [])
        captain = lineup.get("captain")
        vc = lineup.get("viceCaptain")

        new_starting, new_bench, subs_made = apply_auto_subs(
            starting, bench, all_player_minutes, pos_map
        )

        # Recompute base points with new starting XI
        base_pts = sum(all_player_points.get(pid, 0) for pid in new_starting)
        effective_captain, captain_bonus = resolve_captain_bonus(
            {"captain": captain, "viceCaptain": vc},
            all_player_minutes,
            all_player_points,
        )
        total_pts = base_pts + captain_bonus

        lineup_ref.update({
            "starting": new_starting,
            "bench": new_bench,
            "autoSubsMade": subs_made,
            "effectiveCaptain": effective_captain,
            "locked": True,
        })

        scores_ref.set({
            "results": {
                uid: {
                    "points": total_pts,
                    "rawPoints": base_pts,
                    "captainBonus": captain_bonus,
                    "effectiveCaptain": effective_captain,
                    "captain": captain,
                    "viceCaptain": vc,
                    "autoSubs": subs_made,
                }
            }
        }, merge=True)

    # Re-read updated scores
    scores_doc = scores_ref.get()
    results = scores_doc.to_dict().get("results", {})

    n_members = len(uid_list)
    # 6-player leagues use all-against-all ranking for GW6 instead of H2H
    is_aaa_gw = (n_members == 6 and gw == 6)

    # Step 3: H2H / all-against-all results (league phase only)
    if gw in league_phase_gws:
        if is_aaa_gw:
            # All-against-all: rank all managers by GW fantasy score
            aaa = compute_all_against_all_standings(results)
            aaa_h2h_results = {
                uid: {
                    "result": "AAA",
                    "h2hPoints": h2h_pts,
                    "pointsFor": results.get(uid, {}).get("points", 0),
                }
                for uid, h2h_pts in aaa.items()
            }
            scores_ref.set(
                {"h2hResults": aaa_h2h_results, "gwType": "all_against_all"},
                merge=True,
            )
        else:
            schedule_doc = league_ref.collection("schedule").document(str(gw)).get()
            if schedule_doc.exists:
                matches = schedule_doc.to_dict().get("matches", [])
                h2h_results = {}
                for match in matches:
                    home = match.get("home")
                    away = match.get("away")
                    home_pts = results.get(home, {}).get("points", 0)
                    away_pts = results.get(away, {}).get("points", 0)

                    if home_pts > away_pts:
                        h_result, a_result = "W", "L"
                    elif home_pts < away_pts:
                        h_result, a_result = "L", "W"
                    else:
                        h_result, a_result = "D", "D"

                    h2h_results[home] = {
                        "opponent": away, "result": h_result,
                        "pointsFor": home_pts, "pointsAgainst": away_pts,
                    }
                    h2h_results[away] = {
                        "opponent": home, "result": a_result,
                        "pointsFor": away_pts, "pointsAgainst": home_pts,
                    }

                scores_ref.set({"h2hResults": h2h_results}, merge=True)
                schedule_doc.reference.set({"matches": [
                    {**m, "homePoints": results.get(m["home"], {}).get("points", 0),
                     "awayPoints": results.get(m["away"], {}).get("points", 0),
                     "finished": True}
                    for m in matches
                ]}, merge=True)

    # Step 3b: award +1 H2H bonus to top fantasy scorer(s) this GW
    if gw in league_phase_gws:
        _award_gw_bonus(results, scores_ref)

    # Step 4: update standings
    _update_standings(lid, db, gw)

    # Step 5: mark GW complete
    scores_ref.set({"processed": True, "processedAt": SERVER_TIMESTAMP}, merge=True)

    # Step 6: detect eliminations
    _check_eliminations_after_gw(gw, db, wc_client)

    # Step 7: open transfer window
    _open_transfer_window(lid, gw, db)

    # Step 8: seed knockout if this was last league GW
    if gw == knockout_start_gw - 1:
        from fpl_predictor.game.wc_knockout import seed_knockout
        seed_knockout(lid, db)

    # Step 9: advance bracket if knockout GW
    if gw >= knockout_start_gw:
        from fpl_predictor.game.wc_knockout import advance_knockout_bracket
        advance_knockout_bracket(lid, gw, db)

    # Step 9b: apply predictions bonus at GW8 (end of tournament)
    if gw == 8:
        _apply_predictions_bonus(lid, db, wc_client)

    # Step 9c: Snapshot bracket per GW
    bracket_ref = league_ref.collection("knockout").document("bracket")
    bracket_snap = bracket_ref.get()
    if bracket_snap.exists:
        league_ref.collection("knockout").document(f"bracket_gw{gw}").set(bracket_snap.to_dict())

    # Step 9d: snapshot gw_history (lineup IDs -> playerScores join, per manager)
    _snapshot_gw_history(
        league_ref, gw, uid_list, all_player_points, results,
        league_phase_gws, knockout_start_gw, db,
        all_player_stats=all_player_stats,
    )

    # Step 10: advance currentGw
    next_gw = gw + 1
    league_ref.update({"currentGw": next_gw})

    return {"gw": gw, "finalized": True, "nextGw": next_gw, "memberCount": n_members}


def _snapshot_gw_history(league_ref, gw, uid_list, all_player_points, results,
                         league_phase_gws, knockout_start_gw, db,
                         all_player_stats=None):
    """Write per-manager gw_history snapshot docs at GW finalize.

    Performs the lineup-IDs -> playerScores points join (the per-manager,
    per-player breakdown) and resolves opponent/result. Path:
    ``leagues/{lid}/gw_history/{uid}_{gw}``. Full overwrite via ``.set`` so
    re-finalizing a GW is idempotent. See WC2026_WINDOWS_DESIGN.md §3.3.

    ``all_player_stats`` (EP2-W2): optional ``pid -> stats`` map. When provided,
    each ``players[]`` entry also carries that player's per-GW ``stats`` so the
    frontend can reconcile the points breakdown. Defaults to an empty dict
    (entries then get ``stats: {}``) to stay backwards-compatible.
    """
    all_player_stats = all_player_stats or {}
    # H2H results for league-phase GWs (opponent/result/opponentPoints).
    h2h_results = {}
    if gw in league_phase_gws:
        scores_ref = league_ref.collection("scores").document(str(gw))
        scores_doc = scores_ref.get()
        if scores_doc.exists:
            h2h_results = scores_doc.to_dict().get("h2hResults", {}) or {}

    # Knockout bracket matches for this GW (opponent/result resolution).
    bracket_matches = []
    if gw >= knockout_start_gw:
        bracket_doc = league_ref.collection("knockout").document("bracket").get()
        if bracket_doc.exists:
            for round_matches in (bracket_doc.to_dict().get("rounds", {}) or {}).values():
                for match in (round_matches or []):
                    if match.get("gw") == gw:
                        bracket_matches.append(match)

    for uid in uid_list:
        doc_id = f"{uid}_{gw}"
        lineup_doc = league_ref.collection("lineups").document(doc_id).get()
        if not lineup_doc.exists:
            continue
        lineup = lineup_doc.to_dict()
        fielded = list(lineup.get("starting", [])) + list(lineup.get("bench", []))
        players = [{"id": pid,
                    "points": all_player_points.get(pid, 0),
                    "stats": all_player_stats.get(pid, {})}
                   for pid in fielded]
        total_points = results.get(uid, {}).get("points", 0)

        opponent = None
        opponent_points = None
        result = None

        if gw in league_phase_gws:
            h2h = h2h_results.get(uid)
            if h2h:
                result = h2h.get("result")
                if result == "AAA":
                    opponent = None
                    opponent_points = None
                else:
                    opponent = h2h.get("opponent")
                    opponent_points = h2h.get("pointsAgainst")
        elif gw >= knockout_start_gw:
            for match in bracket_matches:
                home = match.get("home")
                away = match.get("away")
                if uid == home:
                    opponent = away
                elif uid == away:
                    opponent = home
                else:
                    continue
                if uid == home:
                    opponent_points = match.get("awayPoints")
                else:
                    opponent_points = match.get("homePoints")
                winner = match.get("winner")
                if winner is None:
                    result = None
                elif winner == uid:
                    result = "W"
                elif opponent is not None and winner == opponent:
                    result = "L"
                else:
                    result = "D"
                break

        payload = {
            "uid": uid,
            "gw": gw,
            "players": players,
            "totalPoints": total_points,
            "opponent": opponent,
            "opponentPoints": opponent_points,
            "result": result,
        }
        league_ref.collection("gw_history").document(doc_id).set(payload)


def _update_standings(lid: str, db, gw: Optional[int] = None):
    """
    Recompute H2H standings from all scores documents.
    Handles: normal H2H (W/D/L), all-against-all GW6 (AAA), bonus points,
    and prediction bonus doc (isPredictionBonus=True → fpts only).
    """
    league_ref = db.collection("leagues").document(lid)
    members = list(league_ref.collection("members").get())
    stats = {m.id: {
        "uid": m.id,
        "displayName": m.to_dict().get("displayName", ""),
        "teamName": m.to_dict().get("teamName", ""),
        "hw": 0, "hd": 0, "hl": 0, "hpts": 0, "fpts": 0,
        "bonusPoints": 0,
        "gwPoints": {},
    } for m in members}

    # Load tournament rules to get dynamic H2H bonus point value
    config_doc = db.collection("wc_config").document("tournament").get()
    rules = config_doc.to_dict().get("rules", {}) if config_doc.exists else {}
    bonus_value = rules.get("bonus", {}).get("gwTopScorerH2HBonus", 1)

    score_docs = league_ref.collection("scores").get()
    for doc in score_docs:
        doc_id = doc.id
        data = doc.to_dict()
        h2h = data.get("h2hResults", {})
        results = data.get("results", {})

        # Try to parse gw_int; prediction bonus doc has id="predictions"
        try:
            gw_int = int(doc_id)
        except ValueError:
            gw_int = None

        for uid, res in results.items():
            if uid not in stats:
                continue
            pts = res.get("points", 0)
            stats[uid]["fpts"] += pts
            if gw_int is not None and not res.get("isPredictionBonus"):
                stats[uid]["gwPoints"][str(gw_int)] = pts
            # GW top-scorer bonus point (stored per-score-doc)
            if res.get("bonusPoint"):
                stats[uid]["hpts"] += bonus_value
                stats[uid]["bonusPoints"] += bonus_value


        for uid, h in h2h.items():
            if uid not in stats:
                continue
            r = h.get("result", "")
            if r == "W":
                stats[uid]["hw"] += 1
                stats[uid]["hpts"] += 3
            elif r == "D":
                stats[uid]["hd"] += 1
                stats[uid]["hpts"] += 1
            elif r == "L":
                stats[uid]["hl"] += 1
            elif r == "AAA":
                # All-against-all GW6: h2hPoints directly stored
                stats[uid]["hpts"] += h.get("h2hPoints", 0)

    # Sort by H2H points (primary) then fantasy points (tiebreak), assign rank,
    # and flag qualification. Without this the table rendered every row as "#1"
    # and "Qualified" because the client relies on a pre-sorted array + rank +
    # knockedOut (GAP-503/504).
    league_doc = league_ref.get().to_dict() or {}
    qualifiers = int(league_doc.get("knockoutQualifiers", 8) or 8)

    ranked = sorted(
        stats.values(),
        key=lambda s: (s.get("hpts", 0), s.get("fpts", 0)),
        reverse=True,
    )
    for idx, s in enumerate(ranked, start=1):
        s["rank"] = idx
        # A manager is knocked out if their team was eliminated OR they finished
        # outside the qualifying places. (During the group phase this previews
        # the cut line; it's authoritative once the knockout bracket is built.)
        below_line = idx > qualifiers
        s["qualified"] = not below_line
        s["knockedOut"] = below_line

    standings_data = {
        "managers": ranked,
        "qualifiers": qualifiers,
        "updatedAt": SERVER_TIMESTAMP,
    }
    league_ref.collection("standings").document("current").set(standings_data)
    
    current_gw = gw or league_ref.get().to_dict().get("currentGw", 1)
    league_ref.collection("standings").document(str(current_gw)).set(standings_data)


def _check_eliminations_after_gw(gw: int, db, wc_client):
    """Trigger elimination detection after appropriate GWs."""
    if gw == 3:
        try:
            wc_client.detect_group_stage_eliminations(db=db)
        except Exception as exc:
            print(f"[warn] elimination detection deferred: {exc}")


def _open_transfer_window(lid: str, gw: int, db):
    """Record a transfer-window AUDIT doc after GW finalization (GWs 1-6 only).

    NOTE (WC2026_WINDOWS_DESIGN.md §2.3 / §11): this doc is **audit-only and is
    NOT a gate**. The authoritative "is the window open?" check is
    ``wc_windows.current_window`` (surfaced via
    ``wc_gameweeks.is_transfer_window_open``). Previously this wrote
    ``status:"open"`` and never closed it, creating a 4th, perpetually-open
    source of truth that the trade/free-agent gates ignored. We now write the
    doc already ``closed`` with explicit ``openAt``/``closeAt`` so it serves as
    a historical record + the per-manager ``transfersUsed`` counter
    (wc_squads._track_transfer keys off ``windowNumber``), without ever acting
    as an open flag.
    """
    from fpl_predictor.game.wc_gameweeks import get_window_dates
    window_open, window_close = get_window_dates(gw)
    if window_open is None:
        return

    # No transfer windows during knockout phase (GW7+)
    if gw >= 7:
        return

    league_ref = db.collection("leagues").document(lid)
    window_ref = league_ref.collection("transfer_windows").document()
    window_ref.set({
        "windowNumber": gw,
        "openAt": window_open,
        "closeAt": window_close,
        # Audit-only: stored already-closed so this never gates anything.
        # The live gate is wc_windows.current_window.
        "status": "closed",
        "closedAt": window_close,
        "transfersUsed": {},
        "freeTransfers": 2,
    })


# ---------------------------------------------------------------------------
# GW bonus helpers
# ---------------------------------------------------------------------------

def _award_gw_bonus(results: Dict[str, Dict], scores_ref) -> List[str]:
    """
    +1 H2H bonus to manager(s) with the highest fantasy score this GW.
    All managers tied at the maximum score each receive the bonus.
    Returns the list of UIDs who received it.
    """
    if not results:
        return []
    max_pts = max(r.get("points", 0) for r in results.values())
    bonus_uids = [uid for uid, r in results.items() if r.get("points", 0) == max_pts]
    for uid in bonus_uids:
        scores_ref.set({
            "results": {
                uid: {
                    "bonusPoint": True
                }
            }
        }, merge=True)
    return bonus_uids


def compute_all_against_all_standings(results: Dict[str, Dict]) -> Dict[str, int]:
    """
    All-against-all H2H points for 6-player GW6.
    Managers ranked by descending fantasy score.
    Points awarded: 1st=6, 2nd=4, 3rd=3, 4th=2, 5th=1, 6th=0.
    Ties: all tied managers receive the higher rank's points.

    Returns {uid: h2h_points}.
    """
    pts_table = [6, 4, 3, 2, 1, 0]
    sorted_uids = sorted(results, key=lambda u: -results[u].get("points", 0))

    aaa_pts: Dict[str, int] = {}
    i = 0
    while i < len(sorted_uids):
        cur_score = results[sorted_uids[i]].get("points", 0)
        # Collect all managers tied at this score
        tied = [u for u in sorted_uids[i:] if results[u].get("points", 0) == cur_score]
        rank_pts = pts_table[i] if i < len(pts_table) else 0
        for u in tied:
            aaa_pts[u] = rank_pts
        i += len(tied)

    return aaa_pts


def _apply_predictions_bonus(lid: str, db, wc_client) -> Dict[str, int]:
    """
    Applied once at GW8 finalization.
    Reads actual WC winner + top scorer from wc_config/tournament,
    awards +15 (correct winner) / +10 (correct top scorer) to qualifying managers.
    Stored as a special 'predictions' score doc (counted in season fpts).

    wc_config/tournament must have fields:
      winner: str   — national team id matching predictedWinner
      topScorer: int — player id matching predictedTopScorer
    """
    config_doc = db.collection("wc_config").document("tournament").get()
    if not config_doc.exists:
        print("[warn] wc_config/tournament not found — skipping predictions bonus")
        return {}

    config = config_doc.to_dict()
    actual_winner = config.get("winner")         # team id string
    actual_top_scorer = config.get("topScorer")  # player id int

    if not actual_winner and not actual_top_scorer:
        print("[warn] No winner/topScorer set in wc_config/tournament — skipping predictions bonus")
        return {}

    league_ref = db.collection("leagues").document(lid)
    members = list(league_ref.collection("members").get())
    bonuses: Dict[str, int] = {}

    for m in members:
        md = m.to_dict()
        preds = md.get("predictions") or {}
        pts = 0
        if actual_winner and preds.get("predictedWinner") == actual_winner:
            pts += 15
        if actual_top_scorer and preds.get("predictedTopScorer") == actual_top_scorer:
            pts += 10
        if pts:
            bonuses[m.id] = pts

    if bonuses:
        pred_ref = league_ref.collection("scores").document("predictions")
        pred_ref.set({
            "results": {
                uid: {"points": pts, "isPredictionBonus": True}
                for uid, pts in bonuses.items()
            },
            "processedAt": SERVER_TIMESTAMP,
        })
        # Recompute standings so fpts includes prediction bonuses
        _update_standings(lid, db)

    return bonuses
