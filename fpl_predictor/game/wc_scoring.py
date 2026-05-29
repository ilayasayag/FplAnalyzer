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

VALID_FORMATIONS = [
    (1, 3, 5, 2), (1, 3, 4, 3), (1, 4, 5, 1),
    (1, 4, 4, 2), (1, 4, 3, 3), (1, 5, 4, 1),
    (1, 5, 3, 2),
]


# ---------------------------------------------------------------------------
# Per-player point calculation
# ---------------------------------------------------------------------------

def compute_player_points(stats: Dict, position: int) -> Tuple[int, int]:
    """
    Compute fantasy points for one player in one fixture.

    stats keys (all default to 0/False if absent):
      minutes, goals, assists, saves, cleanSheet, goalsConceded,
      yellowCards, redCards, penaltyMissed, penaltySaved, ownGoal, bps

    Returns (base_points, bonus_points).
    BPS bonus is computed separately via compute_bps_bonus().
    """
    minutes = stats.get("minutes") or 0
    if minutes == 0:
        return 0, 0

    pts = APPEAR_UNDER_60

    if minutes >= 60:
        pts = APPEAR_60_PLUS

    # Goals
    goals = stats.get("goals", 0) or 0
    pts += goals * GOAL_POINTS.get(position, 4)

    # Assists
    assists = stats.get("assists", 0) or 0
    pts += assists * ASSIST_POINTS

    # Clean sheet (only if played ≥ 60 min)
    if minutes >= 60 and stats.get("cleanSheet", False):
        pts += CS_POINTS.get(position, 0)

    # Goals conceded (GK and DEF only; not if clean sheet)
    if not stats.get("cleanSheet", False):
        gc = stats.get("goalsConceded", 0) or 0
        gc_pen = GC_POINTS_PER_2.get(position, 0)
        if gc_pen < 0:
            pts += (gc // 2) * gc_pen   # floor division

    # Cards
    yellow = stats.get("yellowCards", 0) or 0
    red = stats.get("redCards", 0) or 0
    pts += yellow * YELLOW_CARD_POINTS
    pts += red * RED_CARD_POINTS

    # Own goals
    own_goals = stats.get("ownGoal", 0) or 0
    pts += own_goals * OWN_GOAL_POINTS

    # Penalty miss
    pen_miss = stats.get("penaltyMissed", 0) or 0
    pts += pen_miss * PENALTY_MISS_POINTS

    # GK-only: saves + penalty saves
    if position == 1:
        saves = stats.get("saves", 0) or 0
        pts += (saves // SAVES_PER_POINT_GK)

        pen_saved = stats.get("penaltySaved", 0) or 0
        pts += pen_saved * PENALTY_SAVE_POINTS

    return pts, 0  # bonus is added separately


def compute_bps_bonus(player_bps_list: List[Tuple[int, int]]) -> Dict[int, int]:
    """
    Award 3/2/1 bonus points to the top 3 BPS scorers in a fixture.

    player_bps_list: [(player_id, bps_score), ...]
    Returns: {player_id: bonus_points (3, 2, or 1)}

    Ties: both players at a tied rank receive the higher award.
    e.g. two players tied for 2nd both get 2pts; the 4th-place player gets 0.
    """
    sorted_bps = sorted(player_bps_list, key=lambda x: -x[1])
    bonuses: Dict[int, int] = {}

    award_map = {0: 3, 1: 2, 2: 1}  # rank (0-based) → bonus

    i = 0
    rank = 0
    while i < len(sorted_bps) and rank < 3:
        pid, bps_val = sorted_bps[i]
        bonus = award_map.get(rank, 0)
        bonuses[pid] = bonus

        # Advance through ties
        j = i + 1
        while j < len(sorted_bps) and sorted_bps[j][1] == bps_val:
            tied_pid = sorted_bps[j][0]
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
    Resolve captain bonus for a manager's lineup.

    Returns (effective_captain_id, captain_bonus_points).
    effectiveCaptain = captain if played ≥ 1 min, else viceCaptain if played, else None.
    captainBonus = effectiveCaptain's base points (their score is doubled in total).
    """
    captain = lineup.get("captain")
    vc = lineup.get("viceCaptain")

    if captain and (player_minutes.get(captain, 0) >= 1):
        effective = captain
    elif vc and (player_minutes.get(vc, 0) >= 1):
        effective = vc
    else:
        return None, 0

    bonus = player_base_points.get(effective, 0)
    return effective, bonus


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
) -> Dict[int, Dict]:
    """
    Compute and persist fantasy points for one completed fixture.

    raw_stats: response from wc_client.get_fixture_player_stats(fixture_id)
    Returns {player_id: {fantasyPoints, stats, bonusPoints}}.
    """
    # Build per-player stat dicts
    player_stats: Dict[int, Dict] = {}
    bps_list: List[Tuple[int, int]] = []

    home_goals = 0
    away_goals = 0

    fixture_doc = db.collection("wc_fixtures").document(str(fixture_id)).get()
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

            minutes = games.get("minutes") or 0
            goals_scored = goals.get("total") or 0
            assists = goals.get("assists") or 0
            saves = goals.get("saves") or 0
            own_goals = goals.get("owngoals") or 0
            yellow = cards.get("yellow") or 0
            red = cards.get("red") or 0
            pen_miss = penalty.get("missed") or 0
            pen_saved = penalty.get("saved") or 0
            bps = raw.get("bps") or 0

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
                "bps": bps,
                "bonusPoints": 0,
            }
            player_stats[pid] = {
                "stats": stats,
                "teamId": team_id,
                "name": p_info.get("name", ""),
            }
            if bps > 0:
                bps_list.append((pid, bps))

    # Get player positions from Firestore
    pos_map: Dict[int, int] = {}
    player_docs = db.collection("wc_players").get()
    for doc in player_docs:
        d = doc.to_dict()
        pos_map[d.get("id", 0)] = d.get("position", 3)

    # Compute BPS bonuses
    bonuses = compute_bps_bonus(bps_list)

    # Compute points and persist
    results: Dict[int, Dict] = {}
    batch = db.batch()

    for pid, pdata in player_stats.items():
        pos = pos_map.get(pid, 3)
        base_pts, _ = compute_player_points(pdata["stats"], pos)
        bonus = bonuses.get(pid, 0)
        total_pts = base_pts + bonus

        pdata["stats"]["bonusPoints"] = bonus
        result = {
            "fantasyPoints": total_pts,
            "bonusPoints": bonus,
            "stats": pdata["stats"],
        }
        results[pid] = result

        score_ref = (db.collection("wc_fixtures").document(str(fixture_id))
                     .collection("playerScores").document(str(pid)))
        batch.set(score_ref, result)

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
    Uses atomic increments so concurrent fixture processing is safe.
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
    for fixture_doc in gw_fixtures:
        fid = fixture_doc.id
        score_docs = (db.collection("wc_fixtures").document(fid)
                      .collection("playerScores").get())
        for pdoc in score_docs:
            pid = int(pdoc.id)
            pdata = pdoc.to_dict()
            all_player_points[pid] = all_player_points.get(pid, 0) + pdata.get("fantasyPoints", 0)
            all_player_minutes[pid] = all_player_minutes.get(pid, 0) + (pdata.get("stats", {}).get("minutes") or 0)

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
            f"results.{uid}.points": total_pts,
            f"results.{uid}.rawPoints": base_pts,
            f"results.{uid}.captainBonus": captain_bonus,
            f"results.{uid}.effectiveCaptain": effective_captain,
            f"results.{uid}.captain": captain,
            f"results.{uid}.viceCaptain": vc,
            f"results.{uid}.autoSubs": subs_made,
        }, merge=True)

    # Re-read updated scores
    scores_doc = scores_ref.get()
    results = scores_doc.to_dict().get("results", {})

    # Step 3: H2H results (league phase only)
    if gw in league_phase_gws:
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

                match_update = {
                    "homePoints": home_pts,
                    "awayPoints": away_pts,
                    "finished": True,
                }

            scores_ref.set({"h2hResults": h2h_results}, merge=True)
            schedule_doc.reference.set({"matches": [
                {**m, "homePoints": results.get(m["home"], {}).get("points", 0),
                 "awayPoints": results.get(m["away"], {}).get("points", 0),
                 "finished": True}
                for m in matches
            ]}, merge=True)

    # Step 4: update standings
    _update_standings(lid, db)

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

    # Step 10: advance currentGw
    next_gw = gw + 1
    league_ref.update({"currentGw": next_gw})

    return {"gw": gw, "finalized": True, "nextGw": next_gw, "memberCount": len(uid_list)}


def _update_standings(lid: str, db):
    """Recompute H2H standings from all scores documents."""
    league_ref = db.collection("leagues").document(lid)
    members = list(league_ref.collection("members").get())
    stats = {m.id: {
        "uid": m.id,
        "displayName": m.to_dict().get("displayName", ""),
        "teamName": m.to_dict().get("teamName", ""),
        "hw": 0, "hd": 0, "hl": 0, "hpts": 0, "fpts": 0,
        "gwPoints": {},
    } for m in members}

    score_docs = league_ref.collection("scores").get()
    for doc in score_docs:
        gw_int = int(doc.id)
        data = doc.to_dict()
        h2h = data.get("h2hResults", {})
        results = data.get("results", {})

        for uid, res in results.items():
            if uid not in stats:
                continue
            stats[uid]["fpts"] += res.get("points", 0)
            stats[uid]["gwPoints"][str(gw_int)] = res.get("points", 0)

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

    league_ref.collection("standings").document("current").set({
        "managers": list(stats.values()),
        "updatedAt": SERVER_TIMESTAMP,
    })


def _check_eliminations_after_gw(gw: int, db, wc_client):
    """Trigger elimination detection after appropriate GWs."""
    if gw == 3:
        try:
            wc_client.detect_group_stage_eliminations(db=db)
        except Exception as exc:
            print(f"[warn] elimination detection deferred: {exc}")


def _open_transfer_window(lid: str, gw: int, db):
    """Open transfer window after GW finalization."""
    from fpl_predictor.game.wc_gameweeks import get_window_dates
    window_open, window_close = get_window_dates(gw)
    if window_open is None:
        return

    league_ref = db.collection("leagues").document(lid)
    league = league_ref.get().to_dict()
    knockout_start = league.get("knockoutStartGw", 4)
    n_members = len(list(league_ref.collection("members").get()))

    if n_members > 8 and gw >= knockout_start:
        return

    window_ref = league_ref.collection("transfer_windows").document()
    window_ref.set({
        "windowNumber": gw,
        "openAt": window_open,
        "closeAt": window_close,
        "status": "open",
        "transfersUsed": {},
        "freeTransfers": 2,
    })
