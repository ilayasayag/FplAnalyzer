"""
WC2026 knockout bracket engine.

Seeds bracket after last league GW, runs matches GW-by-GW, advances winners.
Tie-breaking: higher seed advances → total season fpts → draft order.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from google.cloud.firestore_v1 import SERVER_TIMESTAMP


def seed_knockout(lid: str, db) -> dict:
    """
    Called after the last league-phase GW finalizes.

    N > 8 → QF bracket: top 8 → seeds 1–4 (best H2H) + seeds 5–8 (best fpts)
             Matchups: 1v8, 2v7, 3v6, 4v5
    N ≤ 8 → SF bracket: top 4 → seeds 1–2 (best H2H) + seeds 3–4 (best fpts)
             Matchups: 1v4, 2v3
    """
    league_ref = db.collection("leagues").document(lid)
    league = league_ref.get().to_dict()
    qualifiers = league.get("knockoutQualifiers", 8)
    knockout_start_gw = league.get("knockoutStartGw", 4)

    standings_doc = league_ref.collection("standings").document("current").get()
    if not standings_doc.exists:
        raise ValueError("No standings available for seeding")

    managers = standings_doc.to_dict().get("managers", [])

    # Get draft positions for tiebreaking
    member_docs = league_ref.collection("members").get()
    draft_positions: Dict[str, int] = {
        m.id: m.to_dict().get("draftPosition", 99) for m in member_docs
    }

    seeds = _compute_seeds(managers, qualifiers, draft_positions)

    if qualifiers == 8:
        bracket_type = "qf_start"
        first_round_key = "qf"
        matchups = [(1, 8), (2, 7), (3, 6), (4, 5)]
    else:
        bracket_type = "sf_start"
        first_round_key = "sf"
        matchups = [(1, 4), (2, 3)]

    matches = []
    for seed_home, seed_away in matchups:
        home = next((s["uid"] for s in seeds if s["seed"] == seed_home), None)
        away = next((s["uid"] for s in seeds if s["seed"] == seed_away), None)
        if not home or not away:
            continue
        matches.append({
            "id": f"{first_round_key}_{seed_home}v{seed_away}",
            "seedHome": seed_home,
            "seedAway": seed_away,
            "home": home,
            "away": away,
            "homePoints": None,
            "awayPoints": None,
            "winner": None,
            "gw": knockout_start_gw,
        })

    bracket = {
        "type": bracket_type,
        "seededAt": SERVER_TIMESTAMP,
        "seeds": seeds,
        "rounds": {
            first_round_key: matches,
            "sf": [] if bracket_type == "qf_start" else matches,
            "final": [],
        },
        "champion": None,
    }
    if bracket_type == "qf_start":
        bracket["rounds"]["qf"] = matches
        bracket["rounds"]["sf"] = []
        bracket["rounds"]["final"] = []
    else:
        bracket["rounds"]["sf"] = matches
        bracket["rounds"]["final"] = []

    league_ref.collection("knockout").document("bracket").set(bracket)

    league_ref.update({"status": "knockout"})

    return {
        "leagueId": lid,
        "type": bracket_type,
        "seeds": seeds,
        "firstRound": matches,
        "knockoutStartGw": knockout_start_gw,
    }


def advance_knockout_bracket(lid: str, gw: int, db) -> dict:
    """
    Called after a knockout GW finalizes.
    Reads GW scores, records results, advances winners to next round.
    """
    league_ref = db.collection("leagues").document(lid)
    league = league_ref.get().to_dict()
    knockout_start_gw = league.get("knockoutStartGw", 4)
    qualifiers = league.get("knockoutQualifiers", 8)

    bracket_ref = league_ref.collection("knockout").document("bracket")
    bracket_doc = bracket_ref.get()
    if not bracket_doc.exists:
        raise ValueError("Bracket not seeded yet")
    bracket = bracket_doc.to_dict()

    scores_doc = league_ref.collection("scores").document(str(gw)).get()
    if not scores_doc.exists:
        raise ValueError(f"No scores for GW {gw}")
    scores = scores_doc.to_dict().get("results", {})

    # Determine which bracket round this GW corresponds to
    if qualifiers == 8:
        round_gw_map = {
            knockout_start_gw: "qf",
            knockout_start_gw + 1: "sf",
            knockout_start_gw + 2: "final",
        }
    else:
        round_gw_map = {
            knockout_start_gw: "sf",
            knockout_start_gw + 1: "final",
        }

    current_round_key = round_gw_map.get(gw)
    if not current_round_key:
        return {"gw": gw, "skipped": True}

    rounds = bracket.get("rounds", {})
    current_matches = rounds.get(current_round_key, [])
    next_round_key = _next_round(current_round_key)

    seeds: List[Dict] = bracket.get("seeds", [])
    seed_map: Dict[str, int] = {s["uid"]: s["seed"] for s in seeds}

    updated_matches = []
    winners: List[Tuple[str, int]] = []  # (uid, seed)

    for match in current_matches:
        home = match["home"]
        away = match["away"]
        home_pts = scores.get(home, {}).get("points", 0)
        away_pts = scores.get(away, {}).get("points", 0)

        winner = _resolve_match(
            home, away, home_pts, away_pts,
            match.get("seedHome", 99), match.get("seedAway", 99),
            seed_map, _get_season_fpts(lid, home, db), _get_season_fpts(lid, away, db),
        )
        winner_seed = match["seedHome"] if winner == home else match["seedAway"]

        updated_match = {
            **match,
            "homePoints": home_pts,
            "awayPoints": away_pts,
            "winner": winner,
        }
        updated_matches.append(updated_match)
        winners.append((winner, winner_seed))

    rounds[current_round_key] = updated_matches

    # Build next-round matches
    if next_round_key and winners:
        winners_sorted = sorted(winners, key=lambda w: w[1])
        n = len(winners_sorted)

        if next_round_key == "final" and n == 2:
            new_match = {
                "id": "final_1v2",
                "seedHome": winners_sorted[0][1],
                "seedAway": winners_sorted[1][1],
                "home": winners_sorted[0][0],
                "away": winners_sorted[1][0],
                "homePoints": None,
                "awayPoints": None,
                "winner": None,
                "gw": gw + 1,
            }
            rounds["final"] = [new_match]

        elif next_round_key == "sf" and n == 4:
            sf_matches = [
                {
                    "id": f"sf_{winners_sorted[0][1]}v{winners_sorted[3][1]}",
                    "seedHome": winners_sorted[0][1],
                    "seedAway": winners_sorted[3][1],
                    "home": winners_sorted[0][0],
                    "away": winners_sorted[3][0],
                    "homePoints": None, "awayPoints": None, "winner": None,
                    "gw": gw + 1,
                },
                {
                    "id": f"sf_{winners_sorted[1][1]}v{winners_sorted[2][1]}",
                    "seedHome": winners_sorted[1][1],
                    "seedAway": winners_sorted[2][1],
                    "home": winners_sorted[1][0],
                    "away": winners_sorted[2][0],
                    "homePoints": None, "awayPoints": None, "winner": None,
                    "gw": gw + 1,
                },
            ]
            rounds["sf"] = sf_matches

    # Check for champion
    champion = None
    if current_round_key == "final" and updated_matches:
        champion = updated_matches[0].get("winner")
        if champion:
            league_ref.update({"status": "complete", "champion": champion})

    bracket_ref.update({
        "rounds": rounds,
        "champion": champion,
    })

    return {
        "gw": gw,
        "round": current_round_key,
        "results": [
            {"home": m["home"], "away": m["away"],
             "homePoints": m["homePoints"], "awayPoints": m["awayPoints"],
             "winner": m["winner"]}
            for m in updated_matches
        ],
        "champion": champion,
    }


def get_bracket(lid: str, db) -> dict:
    """Read the knockout bracket for a league."""
    doc = (db.collection("leagues").document(lid)
           .collection("knockout").document("bracket").get())
    if not doc.exists:
        return {}
    return {"leagueId": lid, **doc.to_dict()}


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------

def _compute_seeds(
    managers: List[Dict],
    qualifiers: int,
    draft_positions: Dict[str, int],
) -> List[Dict]:
    """
    Assign seeds 1..qualifiers.

    N > 8: seeds 1–4 = best H2H record → tiebreak: fpts → mutual H2H → draft order
           seeds 5–8 = next 4 by total fpts (from non-top-4 H2H)
    N ≤ 8: seeds 1–2 = best H2H record → same tiebreak
           seeds 3–4 = next 2 by total fpts
    """
    h2h_slots = qualifiers // 2
    fpts_slots = qualifiers - h2h_slots

    def sort_key_h2h(m):
        return (
            -m.get("hpts", 0),
            -m.get("fpts", 0),
            draft_positions.get(m["uid"], 99),
        )

    sorted_by_h2h = sorted(managers, key=sort_key_h2h)
    h2h_qualifiers = sorted_by_h2h[:h2h_slots]
    remaining = sorted_by_h2h[h2h_slots:]

    def sort_key_fpts(m):
        return (
            -m.get("fpts", 0),
            draft_positions.get(m["uid"], 99),
        )

    fpts_qualifiers = sorted(remaining, key=sort_key_fpts)[:fpts_slots]

    seeds = []
    for i, m in enumerate(h2h_qualifiers, start=1):
        seeds.append({
            "seed": i,
            "uid": m["uid"],
            "displayName": m.get("displayName", ""),
            "teamName": m.get("teamName", ""),
            "hpts": m.get("hpts", 0),
            "fpts": m.get("fpts", 0),
            "qualifiedVia": "h2h",
        })
    for i, m in enumerate(fpts_qualifiers, start=h2h_slots + 1):
        seeds.append({
            "seed": i,
            "uid": m["uid"],
            "displayName": m.get("displayName", ""),
            "teamName": m.get("teamName", ""),
            "hpts": m.get("hpts", 0),
            "fpts": m.get("fpts", 0),
            "qualifiedVia": "fpts",
        })

    return seeds


def _resolve_match(
    home: str,
    away: str,
    home_pts: int,
    away_pts: int,
    seed_home: int,
    seed_away: int,
    seed_map: Dict[str, int],
    home_season_fpts: int,
    away_season_fpts: int,
) -> str:
    """
    Determine winner. Tie-breaking chain:
    1. Higher GW points wins
    2. Higher seed (lower seed number) advances
    3. Higher total season fpts
    4. Draft order (already encoded in seed)
    """
    if home_pts > away_pts:
        return home
    if away_pts > home_pts:
        return away

    # Tied — higher seed (lower number) advances
    if seed_home < seed_away:
        return home
    if seed_away < seed_home:
        return away

    # Same seed number shouldn't happen, but fall back to season fpts
    if home_season_fpts >= away_season_fpts:
        return home
    return away


def _get_season_fpts(lid: str, uid: str, db) -> int:
    doc = (db.collection("leagues").document(lid)
           .collection("standings").document("current").get())
    if not doc.exists:
        return 0
    for m in doc.to_dict().get("managers", []):
        if m.get("uid") == uid:
            return m.get("fpts", 0)
    return 0


def _next_round(current: str) -> Optional[str]:
    return {"qf": "sf", "sf": "final", "final": None}.get(current)
