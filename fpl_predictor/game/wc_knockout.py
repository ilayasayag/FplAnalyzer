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
    Seeds dynamic bracket (Quarter-finals or Semi-finals) based on rules.
    """
    league_ref = db.collection("leagues").document(lid)
    league = league_ref.get().to_dict()
    knockout_start_gw = league.get("knockoutStartGw", 7)

    standings_doc = league_ref.collection("standings").document("current").get()
    if not standings_doc.exists:
        raise ValueError("No standings available for seeding")

    managers = standings_doc.to_dict().get("managers", [])

    # Get draft positions for tiebreaking
    member_docs = league_ref.collection("members").get()
    draft_positions: Dict[str, int] = {
        m.id: m.to_dict().get("draftPosition", 99) for m in member_docs
    }

    # Load custom rules from Firestore config
    config_doc = db.collection("wc_config").document("tournament").get()
    rules = config_doc.to_dict().get("rules", {}) if config_doc.exists else {}

    n = len(managers)
    size_rules = rules.get("leagueSizeRules", {}).get(str(n), {})
    
    knockout_start_gw = size_rules.get("knockoutStartGw", league.get("knockoutStartGw", 7))
    knockout_qualifiers = size_rules.get("knockoutQualifiers", league.get("knockoutQualifiers", 4))
    knockout_structure = size_rules.get("knockoutStructure", "qf" if knockout_qualifiers == 8 else "sf") # "sf" or "qf"
    
    # Total-points knockout: the top ``knockout_qualifiers`` by season fpts
    # qualify and are seeded by fpts. H2H record is only an fpts tie-break.
    seeds = _compute_seeds(managers, knockout_qualifiers, draft_positions)

    if knockout_structure == "qf":
        bracket_type = "qf_start"
        first_round_key = "qf"
        matchups = [(1, 8), (4, 5), (2, 7), (3, 6)]
        rounds_structure = {
            "qf": [],
            "sf": [],
            "final": []
        }
    else:
        bracket_type = "sf_start"
        first_round_key = "sf"
        matchups = [(1, 4), (2, 3)]
        rounds_structure = {
            "sf": [],
            "final": []
        }

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

    rounds_structure[first_round_key] = matches

    bracket = {
        "type": bracket_type,
        "seededAt": SERVER_TIMESTAMP,
        "seeds": seeds,
        "rounds": rounds_structure,
        "champion": None,
    }

    league_ref.collection("knockout").document("bracket").set(bracket)
    league_ref.update({"status": "knockout"})

    # Non-qualifiers are eliminated the moment the bracket is seeded: mark them
    # and release their entire squad to the free-agent pool so the qualifiers'
    # knockout wishlist (this round's FA window) can pick those players up.
    seed_uids = {s["uid"] for s in seeds}
    eliminated = [m["uid"] for m in managers if m["uid"] not in seed_uids]
    for uid in eliminated:
        _eliminate_and_release(league_ref, uid, knockout_start_gw)

    # Knockout wishlist pick order = SEED order (seed 1 picks first), resolved as
    # an unlimited round-robin. This overrides the league phase's reverse-
    # standings waiver priority.
    _set_knockout_pick_order(league_ref, [s["uid"] for s in seeds])

    return {
        "leagueId": lid,
        "type": bracket_type,
        "seeds": seeds,
        "eliminated": eliminated,
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

    # Load custom rules from Firestore config
    config_doc = db.collection("wc_config").document("tournament").get()
    rules = config_doc.to_dict().get("rules", {}) if config_doc.exists else {}

    standings_doc = league_ref.collection("standings").document("current").get()
    n_managers = len(standings_doc.to_dict().get("managers", [])) if standings_doc.exists else 8

    size_rules = rules.get("leagueSizeRules", {}).get(str(n_managers), {})
    knockout_start_gw = size_rules.get("knockoutStartGw", league.get("knockoutStartGw", 7))
    knockout_structure = size_rules.get("knockoutStructure", "sf") # "sf" or "qf"

    bracket_ref = league_ref.collection("knockout").document("bracket")
    bracket_doc = bracket_ref.get()
    if not bracket_doc.exists:
        raise ValueError("Bracket not seeded yet")
    bracket = bracket_doc.to_dict()

    scores_doc = league_ref.collection("scores").document(str(gw)).get()
    if not scores_doc.exists:
        raise ValueError(f"No scores for GW {gw}")
    scores = scores_doc.to_dict().get("results", {})

    # Dynamic round mapping based on knockout_structure
    if knockout_structure == "qf":
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

            # The two SF losers are eliminated: release their squads so the
            # final's wishlist can pick those players up, and set the final pick
            # order by seed (higher seed = winners_sorted[0] picks first).
            for m in updated_matches:
                loser = m["home"] if m["winner"] == m["away"] else m["away"]
                _eliminate_and_release(league_ref, loser, gw + 1)
            _set_knockout_pick_order(
                league_ref, [winners_sorted[0][0], winners_sorted[1][0]]
            )

        elif next_round_key == "sf" and n == 4:
            if current_round_key == "qf":
                # SF 1: Winner of QF 0 (1v8) vs Winner of QF 1 (4v5)
                w0 = updated_matches[0]["winner"]
                s0 = seed_map[w0]
                w1 = updated_matches[1]["winner"]
                s1 = seed_map[w1]
                # SF 2: Winner of QF 2 (2v7) vs Winner of QF 3 (3v6)
                w2 = updated_matches[2]["winner"]
                s2 = seed_map[w2]
                w3 = updated_matches[3]["winner"]
                s3 = seed_map[w3]
                
                sf_matches = [
                    {
                        "id": f"sf_{s0}v{s1}",
                        "seedHome": s0,
                        "seedAway": s1,
                        "home": w0,
                        "away": w1,
                        "homePoints": None, "awayPoints": None, "winner": None,
                        "gw": gw + 1,
                    },
                    {
                        "id": f"sf_{s2}v{s3}",
                        "seedHome": s2,
                        "seedAway": s3,
                        "home": w2,
                        "away": w3,
                        "homePoints": None, "awayPoints": None, "winner": None,
                        "gw": gw + 1,
                    },
                ]
            else:
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
    Seed the top ``qualifiers`` managers purely by TOTAL season fantasy points
    (``fpts``). This is a total-points knockout: the H2H record does NOT decide
    who qualifies — it only breaks an fpts tie. Seed 1 = highest fpts (and so
    picks first + faces the lowest qualifying seed).

    Tie-break chain: fpts → hpts → draft order.
    """
    by_fpts = sorted(
        managers,
        key=lambda m: (
            -m.get("fpts", 0),
            -m.get("hpts", 0),
            draft_positions.get(m["uid"], 99),
        ),
    )

    seeds = []
    for i, m in enumerate(by_fpts[:qualifiers], start=1):
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


def _eliminate_and_release(league_ref, uid: str, gw: int) -> None:
    """Eliminate a manager and release their ENTIRE squad to the free-agent pool.

    Free agents are simply players in no squad (see WCWaiverManager.get_free_agents
    / _get_all_owned), so emptying the eliminated manager's ``squads/{uid}.players``
    list drops every one of their players into the pool for the next knockout
    wishlist. The manager is flagged ``eliminated`` so the scorer skips them and
    the UI can grey them out. Idempotent: re-running finds an already-empty squad
    and logs nothing new.
    """
    league_ref.collection("members").document(uid).set(
        {"eliminated": True, "eliminatedAtGw": gw}, merge=True
    )

    squad_ref = league_ref.collection("squads").document(uid)
    squad_doc = squad_ref.get()
    released = (squad_doc.to_dict() or {}).get("players", []) if squad_doc.exists else []
    if not released:
        return
    squad_ref.set({"players": []}, merge=True)
    league_ref.collection("transactions").document().set({
        "type": "squad_released",
        "uid": uid,
        "playerIds": [p.get("playerId") for p in released],
        "gw": gw,
        "timestamp": SERVER_TIMESTAMP,
    })


def _set_knockout_pick_order(league_ref, uids_in_seed_order: List[str]) -> None:
    """Set ``waiverPriority`` = seed order for the active knockout managers.

    The top seed gets ``waiverPriority=1`` (picks first). The wishlist auction
    resolves in ascending ``waiverPriority`` as an unlimited round-robin, so this
    makes the best seed pick first — the opposite of the league phase's
    reverse-standings (worst-first) order.
    """
    for priority, uid in enumerate(uids_in_seed_order, start=1):
        league_ref.collection("members").document(uid).set(
            {"waiverPriority": priority}, merge=True
        )
