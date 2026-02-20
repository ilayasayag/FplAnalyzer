"""
Player Expected Points Predictor.

Calculates per-GW expected FPL points for each player based on:
- Season averages (goals, assists, CS, saves, bonus, cards per 90)
- Recent form (EWMA-weighted last 5 GW performance)
- Fixture difficulty and opponent quality
- Home/away adjustment
- Lineup probability (from minutes history + FPL news)
- Position-specific scoring rules

Output is a point range: {floor, expected, ceiling} for each GW.
"""

import math
from typing import Dict, List, Optional
from collections import defaultdict, Counter
from fpl_predictor.data.fpl_api import FPLClient, _safe_float
from fpl_predictor.engine.team_form import TeamFormAnalyzer

# Official FPL scoring rules
SCORING = {
    "minutes_1":   1,   # 1 pt for 1-59 min
    "minutes_60":  2,   # 2 pts for 60+ min
    "gk_goal":     10,
    "def_goal":    6,
    "mid_goal":    5,
    "fwd_goal":    4,
    "assist":      3,
    "gk_cs":       4,
    "def_cs":      4,
    "mid_cs":      1,
    "gk_save_per": 3,   # 1 pt per 3 saves
    "gc_penalty":  -0.5, # -1 pt per 2 goals conceded (GK/DEF)
    "pen_miss":    -2,
    "yellow":      -1,
    "red":         -3,
    "own_goal":    -2,
    "pen_save":    5,
}

GOAL_POINTS = {1: 10, 2: 6, 3: 5, 4: 4}
CS_POINTS = {1: 4, 2: 4, 3: 1, 4: 0}

FORM_WINDOW = 5
EWMA_ALPHA = 0.35


class PlayerPredictor:
    """Predicts expected FPL points for players across upcoming gameweeks."""

    def __init__(self, client: FPLClient):
        self.client = client
        self.team_form = TeamFormAnalyzer(client)
        self._draft_to_main = None

    @property
    def main_players(self) -> Dict[int, Dict]:
        """Draft-ID -> main API player data (cross-referenced by name+team)."""
        if self._draft_to_main is None:
            self._draft_to_main = self.client.get_draft_to_main_map()
        return self._draft_to_main

    def predict_player(self, player_id: int, gw_start: int, gw_end: int) -> Dict:
        """
        Full prediction for a single player across GW range.
        Returns season stats, form, per-GW predictions with breakdown.
        """
        draft_map = self.client.get_player_map()
        draft_p = draft_map.get(player_id, {})
        main_p = self.main_players.get(player_id, {})
        team_map = self.client.get_team_map()
        grid = self.client.get_fixture_grid()

        if not draft_p:
            return {"error": "Player not found"}

        team_id = draft_p["team"]
        pos = draft_p["element_type"]
        team = team_map.get(team_id, {})

        history = self._get_history_safe(player_id)
        season = self._season_rates(history, pos)
        form = self._form_rates(history, pos)
        lineup_prob = self._lineup_probability(history, draft_p, main_p)

        predictions = []
        for gw in range(gw_start, gw_end + 1):
            fixture = grid.get(team_id, {}).get(gw)
            if not fixture:
                predictions.append({"gw": gw, "expected": 0, "floor": 0, "ceiling": 0, "no_fixture": True})
                continue

            opp_id = fixture["opponent_id"]
            is_home = fixture["is_home"]
            fdr = fixture["fdr"]
            match_pred = self.team_form.predict_match_goals(
                team_id if is_home else opp_id,
                opp_id if is_home else team_id,
            )

            pred = self._predict_gw(
                pos, season, form, lineup_prob, fdr, is_home, match_pred, team_id
            )
            pred["gw"] = gw
            pred["opponent"] = fixture["display"]
            pred["opponent_id"] = opp_id
            pred["fdr"] = fdr
            pred["is_home"] = is_home
            predictions.append(pred)

        avg_xpts = sum(p.get("expected", 0) for p in predictions) / max(len(predictions), 1)
        batch_stats = self._batch_level_stats(history, pos)
        score_dist = self._score_distribution(history)
        predicted_repeats = self._predicted_repeat_scores(history, predictions, grid, team_id)

        return {
            "player_id": player_id,
            "web_name": draft_p.get("web_name", "?"),
            "team_id": team_id,
            "team_short": team.get("short_name", "?"),
            "position": pos,
            "total_points": draft_p.get("total_points", 0),
            "form": _safe_float(draft_p.get("form", 0)),
            "season_rates": season,
            "form_rates": form,
            "lineup_prob": round(lineup_prob, 2),
            "avg_xpts": round(avg_xpts, 2),
            "predictions": predictions,
            "batch_stats": batch_stats,
            "score_distribution": score_dist,
            "predicted_repeats": predicted_repeats,
        }

    def predict_squad(self, league_id: int, entry_id: int,
                      gw_start: int, gw_end: int) -> Dict:
        """Predict all players in a squad with suggested lineup."""
        current_gw = self.client.get_current_gw()
        squad = self.client.get_enriched_squad(league_id, entry_id, current_gw)

        player_preds = []
        for p in squad:
            pred = self.predict_player(p["player_id"], gw_start, gw_end)
            pred["squad_position"] = p.get("squad_position", 0)
            pred["is_captain"] = p.get("is_captain", False)
            player_preds.append(pred)

        suggested = self._suggest_lineups(player_preds, gw_start, gw_end)

        return {
            "entry_id": entry_id,
            "gw_range": {"start": gw_start, "end": gw_end},
            "players": player_preds,
            "suggested_lineups": suggested,
        }

    def predict_h2h(self, league_id: int, entry1: int, entry2: int,
                    gw: int) -> Dict:
        """Compare two FPL squads for a specific GW."""
        s1 = self.predict_squad(league_id, entry1, gw, gw)
        s2 = self.predict_squad(league_id, entry2, gw, gw)

        def squad_xpts(squad_data):
            lineup = squad_data.get("suggested_lineups", [{}])
            if lineup:
                return lineup[0].get("total_xpts", 0)
            return sum(
                p["predictions"][0]["expected"]
                for p in squad_data["players"]
                if p["predictions"]
            )

        xp1 = squad_xpts(s1)
        xp2 = squad_xpts(s2)

        return {
            "gw": gw,
            "entry_1": {"entry_id": entry1, "xpts": round(xp1, 1), "squad": s1},
            "entry_2": {"entry_id": entry2, "xpts": round(xp2, 1), "squad": s2},
            "advantage": 1 if xp1 > xp2 else (2 if xp2 > xp1 else 0),
        }

    # ------------------------------------------------------------------
    # Internal: fetch + compute
    # ------------------------------------------------------------------

    def _get_history_safe(self, player_id: int) -> List[Dict]:
        try:
            return self.client.get_player_gw_history(player_id)
        except Exception:
            return []

    def _season_rates(self, history: List[Dict], pos: int) -> Dict:
        """Per-90 rates from full season history."""
        total_mins = sum(h.get("minutes", 0) for h in history)
        if total_mins < 90:
            return self._default_rates(pos)

        nineties = total_mins / 90
        games = len([h for h in history if h.get("minutes", 0) > 0])

        return {
            "goals_p90": _div(sum(h.get("goals_scored", 0) for h in history), nineties),
            "assists_p90": _div(sum(h.get("assists", 0) for h in history), nineties),
            "cs_rate": _div(sum(h.get("clean_sheets", 0) for h in history), games),
            "saves_p90": _div(sum(h.get("saves", 0) for h in history), nineties),
            "bonus_pg": _div(sum(h.get("bonus", 0) for h in history), games),
            "bps_pg": _div(sum(h.get("bps", 0) for h in history), games),
            "yellow_pg": _div(sum(h.get("yellow_cards", 0) for h in history), games),
            "red_pg": _div(sum(h.get("red_cards", 0) for h in history), games),
            "gc_p90": _div(sum(h.get("goals_conceded", 0) for h in history), nineties),
            "xg_p90": _div(sum(_safe_float(h.get("expected_goals", 0)) for h in history), nineties),
            "xa_p90": _div(sum(_safe_float(h.get("expected_assists", 0)) for h in history), nineties),
            "pts_pg": _div(sum(h.get("total_points", 0) for h in history), games),
            "mins_pg": _div(total_mins, games),
            "games": games,
            "total_mins": total_mins,
            "defcon_p90": _div(sum(h.get("defensive_contribution", 0) for h in history), nineties),
        }

    def _form_rates(self, history: List[Dict], pos: int) -> Dict:
        """EWMA-weighted rates from recent games."""
        played = [h for h in history if h.get("minutes", 0) > 0]
        recent = played[-FORM_WINDOW:] if len(played) >= FORM_WINDOW else played
        if not recent:
            return self._default_rates(pos)

        weights = [EWMA_ALPHA * (1 - EWMA_ALPHA) ** i for i in range(len(recent) - 1, -1, -1)]
        wsum = sum(weights) or 1

        def wt_avg(key, per_90=False):
            vals = []
            for h in recent:
                mins = max(h.get("minutes", 0), 1)
                v = _safe_float(h.get(key, 0))
                vals.append(v / (mins / 90) if per_90 else v)
            return round(sum(v * w for v, w in zip(vals, weights)) / wsum, 3)

        return {
            "goals_p90": wt_avg("goals_scored", True),
            "assists_p90": wt_avg("assists", True),
            "cs_rate": wt_avg("clean_sheets"),
            "saves_p90": wt_avg("saves", True),
            "bonus_pg": wt_avg("bonus"),
            "bps_pg": wt_avg("bps"),
            "yellow_pg": wt_avg("yellow_cards"),
            "red_pg": wt_avg("red_cards"),
            "gc_p90": wt_avg("goals_conceded", True),
            "xg_p90": wt_avg("expected_goals", True),
            "xa_p90": wt_avg("expected_assists", True),
            "pts_pg": wt_avg("total_points"),
            "defcon_p90": wt_avg("defensive_contribution", True),
        }

    def _lineup_probability(self, history: List[Dict], draft_p: Dict, main_p: Dict) -> float:
        """Estimate probability of playing 60+ minutes."""
        cop = main_p.get("chance_of_playing_next_round")
        if cop is not None and cop < 100:
            return cop / 100 * 0.85

        if draft_p.get("status") == "i":
            return 0.0
        if draft_p.get("status") == "d":
            return 0.25

        played = [h for h in history if h.get("minutes", 0) > 0]
        if not played:
            return 0.3

        recent = played[-6:]
        starts = sum(1 for h in recent if h.get("starts", 0))
        avg_mins = sum(h.get("minutes", 0) for h in recent) / len(recent)

        if avg_mins >= 75 and starts >= len(recent) * 0.7:
            return 0.92
        if avg_mins >= 60:
            return 0.80
        if avg_mins >= 40:
            return 0.55
        if avg_mins >= 15:
            return 0.35
        return 0.15

    def _predict_gw(self, pos, season, form, lineup_prob, fdr, is_home,
                    match_pred, team_id) -> Dict:
        """
        Predict expected points for a single GW.
        Blends season rates (40%) with form (60%), adjusted by fixture.
        """
        sw, fw = 0.4, 0.6

        def blend(key):
            return season.get(key, 0) * sw + form.get(key, 0) * fw

        fixture_mult = _fixture_multiplier(fdr)
        home_mult = 1.08 if is_home else 0.92
        cs_from_match = match_pred.get("home_cs_prob" if is_home else "away_cs_prob", 0.25)
        team_xg = match_pred.get("home_xg" if is_home else "away_xg", 1.3)

        xgoals = blend("xg_p90") * fixture_mult * home_mult
        if pos in (3, 4):
            xgoals *= (team_xg / 1.3)

        xassists = blend("xa_p90") * fixture_mult * home_mult
        cs_rate = cs_from_match if pos in (1, 2) else cs_from_match * 0.6
        xsaves = blend("saves_p90") if pos == 1 else 0
        xbonus = blend("bonus_pg") * fixture_mult
        xyellow = blend("yellow_pg")
        xred = blend("red_pg")
        xgc = blend("gc_p90") * (1 / max(fixture_mult, 0.5))

        # Compute expected points from probabilities
        prob_60 = lineup_prob * 0.85
        prob_sub = lineup_prob * 0.15
        prob_not = 1 - lineup_prob

        pts_playing = SCORING["minutes_60"]
        pts_sub = SCORING["minutes_1"]

        goal_pts = GOAL_POINTS.get(pos, 4)
        cs_pts = CS_POINTS.get(pos, 0)

        xpts_goals = xgoals * goal_pts
        xpts_assists = xassists * SCORING["assist"]
        xpts_cs = cs_rate * cs_pts if cs_pts > 0 else 0
        xpts_saves = (xsaves / SCORING["gk_save_per"]) if pos == 1 else 0
        xpts_bonus = xbonus
        xpts_yellow = xyellow * SCORING["yellow"]
        xpts_red = xred * SCORING["red"]
        xpts_gc = 0
        if pos in (1, 2):
            xpts_gc = max(xgc, 0) * SCORING["gc_penalty"]

        xpts_if_play = (pts_playing + xpts_goals + xpts_assists + xpts_cs +
                        xpts_saves + xpts_bonus + xpts_yellow + xpts_red + xpts_gc)
        xpts_if_sub = pts_sub + xpts_goals * 0.3 + xpts_assists * 0.3

        expected = round(prob_60 * xpts_if_play + prob_sub * xpts_if_sub, 1)
        floor_val = round(max(prob_60 * 2 + xpts_yellow * lineup_prob, 0), 1)
        ceiling_val = round(
            prob_60 * (pts_playing + goal_pts * min(xgoals * 3, 2) +
                       SCORING["assist"] * min(xassists * 3, 2) + cs_pts + 3), 1
        )

        return {
            "expected": expected,
            "floor": floor_val,
            "ceiling": ceiling_val,
            "lineup_prob": round(lineup_prob, 2),
            "breakdown": {
                "playing": round(prob_60 * pts_playing + prob_sub * pts_sub, 2),
                "goals": round(xpts_goals * lineup_prob, 2),
                "assists": round(xpts_assists * lineup_prob, 2),
                "clean_sheet": round(xpts_cs * prob_60, 2),
                "saves": round(xpts_saves * prob_60, 2),
                "bonus": round(xpts_bonus * lineup_prob, 2),
                "cards": round((xpts_yellow + xpts_red) * lineup_prob, 2),
                "goals_conceded": round(xpts_gc * prob_60, 2),
            },
            "xg": round(xgoals, 3),
            "xa": round(xassists, 3),
            "cs_prob": round(cs_rate, 2),
        }

    def _suggest_lineups(self, player_preds: List[Dict],
                         gw_start: int, gw_end: int) -> List[Dict]:
        """Suggest best XI for each GW based on predicted points."""
        formations = [
            (1, 3, 5, 2), (1, 3, 4, 3), (1, 4, 5, 1),
            (1, 4, 4, 2), (1, 4, 3, 3), (1, 5, 4, 1),
            (1, 5, 3, 2),
        ]
        result = []
        for gw in range(gw_start, gw_end + 1):
            gw_idx = gw - gw_start
            by_pos = defaultdict(list)
            for pp in player_preds:
                preds = pp.get("predictions", [])
                xpts = preds[gw_idx]["expected"] if gw_idx < len(preds) else 0
                by_pos[pp["position"]].append({
                    "player_id": pp["player_id"],
                    "web_name": pp["web_name"],
                    "team_short": pp["team_short"],
                    "position": pp["position"],
                    "xpts": xpts,
                    "floor": preds[gw_idx].get("floor", 0) if gw_idx < len(preds) else 0,
                    "ceiling": preds[gw_idx].get("ceiling", 0) if gw_idx < len(preds) else 0,
                })
            for pos_id in by_pos:
                by_pos[pos_id].sort(key=lambda x: x["xpts"], reverse=True)

            best = None
            best_score = -1
            for f in formations:
                gk, df, mf, fw = f
                if any(len(by_pos.get(i + 1, [])) < c for i, c in enumerate(f)):
                    continue
                lineup = (by_pos[1][:gk] + by_pos[2][:df] +
                          by_pos[3][:mf] + by_pos[4][:fw])
                score = sum(p["xpts"] for p in lineup)
                if score > best_score:
                    best_score = score
                    best = {
                        "lineup": lineup,
                        "formation": f"{df}-{mf}-{fw}",
                        "total_xpts": round(score, 1),
                        "total_floor": round(sum(p["floor"] for p in lineup), 1),
                        "total_ceiling": round(sum(p["ceiling"] for p in lineup), 1),
                    }

            lineup_ids = {p["player_id"] for p in (best["lineup"] if best else [])}
            bench = [p for pp in player_preds for p in [pp]
                     if pp["player_id"] not in lineup_ids]
            bench_entries = []
            for bp in bench:
                preds = bp.get("predictions", [])
                xpts = preds[gw_idx]["expected"] if gw_idx < len(preds) else 0
                bench_entries.append({
                    "player_id": bp["player_id"], "web_name": bp["web_name"],
                    "team_short": bp["team_short"], "position": bp["position"],
                    "xpts": xpts,
                })
            bench_entries.sort(key=lambda x: x["xpts"], reverse=True)

            result.append({
                "gw": gw,
                **(best or {"lineup": [], "formation": "N/A",
                            "total_xpts": 0, "total_floor": 0, "total_ceiling": 0}),
                "bench": bench_entries,
            })
        return result

    def _score_distribution(self, history: List[Dict]) -> Dict:
        """Build histogram of points scored across the season."""
        played = [h for h in history if h.get("minutes", 0) > 0]
        if not played:
            return {"bins": [], "max_pts": 0, "avg_pts": 0, "median_pts": 0}

        pts_list = [h.get("total_points", 0) for h in played]
        counts = Counter(pts_list)

        bins = []
        for pts in sorted(counts.keys()):
            bins.append({"points": pts, "count": counts[pts], "pct": round(counts[pts] / len(pts_list) * 100, 1)})

        sorted_pts = sorted(pts_list)
        mid = len(sorted_pts) // 2
        median = sorted_pts[mid] if len(sorted_pts) % 2 else (sorted_pts[mid - 1] + sorted_pts[mid]) / 2

        return {
            "bins": bins,
            "max_pts": max(pts_list),
            "min_pts": min(pts_list),
            "avg_pts": round(sum(pts_list) / len(pts_list), 1),
            "median_pts": median,
            "games_played": len(pts_list),
        }

    def _predicted_repeat_scores(self, history: List[Dict], predictions: List[Dict],
                                  grid: Dict, team_id: int) -> List[Dict]:
        """
        For each upcoming GW, find the top 2 most likely score outcomes
        based on similar historical matchups (same batch, same venue type).
        """
        batch_map = self.client.get_team_batch_map()
        result = []

        for pred in predictions:
            if pred.get("no_fixture"):
                continue
            opp_id = pred.get("opponent_id")
            is_home = pred.get("is_home", True)
            opp_batch = batch_map.get(opp_id, 3)

            similar = []
            for h in history:
                if h.get("minutes", 0) < 45:
                    continue
                h_opp = h.get("opponent_team")
                h_batch = batch_map.get(h_opp, 3)
                h_home = h.get("was_home", True)
                similarity = 0
                if h_batch == opp_batch:
                    similarity += 3
                elif abs(h_batch - opp_batch) <= 1:
                    similarity += 1
                if h_home == is_home:
                    similarity += 1
                if h_opp == opp_id:
                    similarity += 5
                if similarity >= 2:
                    similar.append({
                        "gw": h.get("round"),
                        "opponent_team": h_opp,
                        "was_home": h_home,
                        "points": h.get("total_points", 0),
                        "goals": h.get("goals_scored", 0),
                        "assists": h.get("assists", 0),
                        "minutes": h.get("minutes", 0),
                        "similarity": similarity,
                    })

            similar.sort(key=lambda x: -x["similarity"])
            if similar:
                pts_counts = Counter(s["points"] for s in similar)
                top_scores = pts_counts.most_common(2)
                total = len(similar)
                top2 = [
                    {"points": pts, "occurrences": cnt,
                     "probability": round(cnt / total * 100, 1)}
                    for pts, cnt in top_scores
                ]
            else:
                top2 = []

            result.append({
                "gw": pred.get("gw"),
                "opponent": pred.get("opponent", "?"),
                "similar_matches": len(similar),
                "top_predicted_scores": top2,
                "similar_details": similar[:5],
            })
        return result

    def suggest_fa_for_fixture(self, league_id: int, entry_id: int,
                                position: int, gw: int, limit: int = 10) -> List[Dict]:
        """
        Suggest best free agents for a specific fixture/GW.
        Ranks by predicted xPts for that specific GW.
        """
        free = self.client.get_free_agents(league_id, position=position, limit=200)
        results = []
        for fa in free:
            pred = self.predict_player(fa["player_id"], gw, gw)
            if not pred.get("predictions"):
                continue
            gw_pred = pred["predictions"][0]
            if gw_pred.get("no_fixture"):
                continue
            results.append({
                "player_id": fa["player_id"],
                "web_name": fa["web_name"],
                "team_short": fa["team_short"],
                "position": fa["position"],
                "total_points": fa["total_points"],
                "form": fa["form"],
                "gw_xpts": gw_pred["expected"],
                "gw_floor": gw_pred["floor"],
                "gw_ceiling": gw_pred["ceiling"],
                "opponent": gw_pred.get("opponent", "?"),
                "fdr": gw_pred.get("fdr", 3),
                "lineup_prob": pred["lineup_prob"],
            })
        results.sort(key=lambda x: -x["gw_xpts"])
        return results[:limit]

    def suggest_fa_multi_gw(self, league_id: int, entry_id: int,
                             position: int, gw_start: int, gw_end: int,
                             limit: int = 10) -> List[Dict]:
        """Suggest best FA over a GW range, ranked by total expected points."""
        free = self.client.get_free_agents(league_id, position=position, limit=150)
        results = []
        for fa in free:
            pred = self.predict_player(fa["player_id"], gw_start, gw_end)
            total_xpts = sum(p.get("expected", 0) for p in pred.get("predictions", []))
            results.append({
                "player_id": fa["player_id"],
                "web_name": fa["web_name"],
                "team_short": fa["team_short"],
                "position": fa["position"],
                "total_points": fa["total_points"],
                "form": fa["form"],
                "total_xpts": round(total_xpts, 1),
                "avg_xpts": pred.get("avg_xpts", 0),
                "lineup_prob": pred.get("lineup_prob", 0),
                "predictions": pred.get("predictions", []),
            })
        results.sort(key=lambda x: -x["total_xpts"])
        return results[:limit]

    def _batch_level_stats(self, history: List[Dict], pos: int) -> Dict:
        """
        Compute per-batch stats: how the player performs against different
        quality opponents (top 4 vs mid-table vs bottom, etc.)
        """
        batch_map = self.client.get_team_batch_map()
        BATCH_NAMES = {1: "Top 4", 2: "Top 8", 3: "Mid-table", 4: "Lower", 5: "Bottom 3"}

        buckets: Dict[int, List[Dict]] = defaultdict(list)
        for h in history:
            if h.get("minutes", 0) < 30:
                continue
            opp = h.get("opponent_team")
            batch = batch_map.get(opp, 3)
            buckets[batch].append(h)

        result = {}
        for batch_id, games in sorted(buckets.items()):
            n = len(games)
            mins = sum(g.get("minutes", 0) for g in games)
            nineties = max(mins / 90, 0.1)
            result[BATCH_NAMES.get(batch_id, str(batch_id))] = {
                "games": n,
                "minutes": mins,
                "goals_p90": _div(sum(g.get("goals_scored", 0) for g in games), nineties),
                "assists_p90": _div(sum(g.get("assists", 0) for g in games), nineties),
                "cs_rate": _div(sum(g.get("clean_sheets", 0) for g in games), n),
                "defcon_p90": _div(sum(g.get("defensive_contribution", 0) for g in games), nineties),
                "pts_pg": _div(sum(g.get("total_points", 0) for g in games), n),
                "bonus_pg": _div(sum(g.get("bonus", 0) for g in games), n),
                "xg_p90": _div(sum(_safe_float(g.get("expected_goals", 0)) for g in games), nineties),
                "gc_p90": _div(sum(g.get("goals_conceded", 0) for g in games), nineties),
            }
        return result

    @staticmethod
    def _default_rates(pos):
        defaults = {
            1: {"goals_p90": 0, "assists_p90": 0, "cs_rate": 0.28, "saves_p90": 3.2,
                "bonus_pg": 0.5, "bps_pg": 15, "yellow_pg": 0.05, "red_pg": 0.001,
                "gc_p90": 1.3, "xg_p90": 0, "xa_p90": 0, "pts_pg": 4, "defcon_p90": 0},
            2: {"goals_p90": 0.04, "assists_p90": 0.06, "cs_rate": 0.28, "saves_p90": 0,
                "bonus_pg": 0.4, "bps_pg": 18, "yellow_pg": 0.12, "red_pg": 0.003,
                "gc_p90": 1.3, "xg_p90": 0.04, "xa_p90": 0.06, "pts_pg": 4, "defcon_p90": 8},
            3: {"goals_p90": 0.10, "assists_p90": 0.10, "cs_rate": 0.28, "saves_p90": 0,
                "bonus_pg": 0.4, "bps_pg": 16, "yellow_pg": 0.10, "red_pg": 0.002,
                "gc_p90": 0, "xg_p90": 0.10, "xa_p90": 0.10, "pts_pg": 4, "defcon_p90": 3},
            4: {"goals_p90": 0.18, "assists_p90": 0.08, "cs_rate": 0, "saves_p90": 0,
                "bonus_pg": 0.5, "bps_pg": 14, "yellow_pg": 0.08, "red_pg": 0.002,
                "gc_p90": 0, "xg_p90": 0.18, "xa_p90": 0.08, "pts_pg": 4, "defcon_p90": 1},
        }
        return defaults.get(pos, defaults[3])


def _fixture_multiplier(fdr: int) -> float:
    return {1: 1.35, 2: 1.20, 3: 1.00, 4: 0.80, 5: 0.65}.get(fdr, 1.0)


def _div(a, b):
    return round(a / b, 3) if b else 0.0
