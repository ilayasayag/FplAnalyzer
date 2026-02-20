"""
PL Team Form Analyzer.

Computes team-level stats for scoring/conceding probabilities,
clean sheet rates, and batch-level cross statistics.
"""

from typing import Dict, List, Optional, Tuple
from fpl_predictor.data.fpl_api import FPLClient

BATCH_NAMES = {1: "Top 4", 2: "Top 8", 3: "Mid-table", 4: "Lower", 5: "Bottom 3"}


class TeamFormAnalyzer:

    def __init__(self, client: FPLClient):
        self.client = client
        self._fixture_results = None

    def get_fixture_results(self) -> List[Dict]:
        """All finished fixtures with goals, teams, and GW."""
        if self._fixture_results is None:
            raw = self.client.get_fixtures()
            self._fixture_results = [f for f in raw if f.get("finished") and f.get("event")]
        return self._fixture_results

    def get_full_form_report(self) -> Dict:
        """
        Complete team form report: standings, per-team stats,
        batch cross-tables, and scoring probabilities.
        """
        standings = self.client.get_pl_standings()
        batch_map = self.client.get_team_batch_map()
        team_map = self.client.get_team_map()
        fixtures = self.get_fixture_results()

        cross = self._batch_cross_stats(fixtures, batch_map, team_map)
        teams_form = self._recent_form(fixtures, team_map, n=6)

        return {
            "standings": standings,
            "batch_map": {str(k): v for k, v in batch_map.items()},
            "batch_names": BATCH_NAMES,
            "batch_cross": cross,
            "recent_form": teams_form,
        }

    # ------------------------------------------------------------------
    # Batch cross-table: how does batch X perform vs batch Y?
    # ------------------------------------------------------------------

    def _batch_cross_stats(self, fixtures, batch_map, team_map) -> Dict:
        """
        Cross-table: for each (attacking_batch, defending_batch),
        compute avg goals scored, clean sheet rate, sample size.
        """
        buckets: Dict[Tuple[int, int], Dict] = {}

        for f in fixtures:
            h, a = f["team_h"], f["team_a"]
            hs = f.get("team_h_score") or 0
            as_ = f.get("team_a_score") or 0
            hb = batch_map.get(h)
            ab = batch_map.get(a)
            if hb is None or ab is None:
                continue

            for atk_batch, def_batch, goals, conceded in [
                (hb, ab, hs, as_), (ab, hb, as_, hs)
            ]:
                key = (atk_batch, def_batch)
                if key not in buckets:
                    buckets[key] = {"games": 0, "goals": 0, "cs": 0, "scored": 0}
                buckets[key]["games"] += 1
                buckets[key]["goals"] += goals
                if goals > 0:
                    buckets[key]["scored"] += 1
                if conceded == 0:
                    buckets[key]["cs"] += 1

        result = {}
        for (ab, db), s in buckets.items():
            g = max(s["games"], 1)
            result[f"{ab}_vs_{db}"] = {
                "attacking_batch": ab,
                "defending_batch": db,
                "games": s["games"],
                "avg_goals": round(s["goals"] / g, 2),
                "cs_rate": round(s["cs"] / g, 2),
                "scoring_pct": round(s["scored"] / g * 100, 1),
            }
        return result

    # ------------------------------------------------------------------
    # Recent form (last N fixtures per team)
    # ------------------------------------------------------------------

    def _recent_form(self, fixtures, team_map, n=6) -> List[Dict]:
        """Per-team recent form over last n finished games."""
        by_team: Dict[int, List] = {}
        sorted_fix = sorted(fixtures, key=lambda f: (f["event"], f.get("kickoff_time", "")))

        for f in sorted_fix:
            h, a = f["team_h"], f["team_a"]
            hs = f.get("team_h_score") or 0
            as_ = f.get("team_a_score") or 0
            for tid, gf, ga, venue in [(h, hs, as_, "H"), (a, as_, hs, "A")]:
                by_team.setdefault(tid, []).append({
                    "gw": f["event"], "gf": gf, "ga": ga, "venue": venue,
                    "result": "W" if gf > ga else ("D" if gf == ga else "L"),
                })

        result = []
        for tid, games in by_team.items():
            recent = games[-n:]
            t = team_map.get(tid, {})
            gf = sum(g["gf"] for g in recent)
            ga = sum(g["ga"] for g in recent)
            cs = sum(1 for g in recent if g["ga"] == 0)
            wins = sum(1 for g in recent if g["result"] == "W")
            form_str = "".join(g["result"] for g in recent)
            result.append({
                "team_id": tid,
                "team_name": t.get("name", "?"),
                "team_short": t.get("short_name", "?"),
                "last_n": len(recent),
                "form_string": form_str,
                "wins": wins,
                "draws": sum(1 for g in recent if g["result"] == "D"),
                "losses": sum(1 for g in recent if g["result"] == "L"),
                "gf": gf, "ga": ga, "cs": cs,
                "gf_per_game": round(gf / max(len(recent), 1), 2),
                "ga_per_game": round(ga / max(len(recent), 1), 2),
                "cs_rate": round(cs / max(len(recent), 1), 2),
            })
        result.sort(key=lambda x: (-x["wins"], -x["gf"]))
        return result

    # ------------------------------------------------------------------
    # Match prediction: expected goals for home/away given team pair
    # ------------------------------------------------------------------

    def predict_match_goals(self, home_team_id: int, away_team_id: int) -> Dict:
        """
        Predict expected goals for a match using team season stats,
        home/away rates, and league averages.
        """
        all_stats = self.client.get_team_season_stats()
        h = all_stats.get(home_team_id, {})
        a = all_stats.get(away_team_id, {})

        league_avg_gf = sum(s.get("gf_per_game", 0) for s in all_stats.values()) / max(len(all_stats), 1)
        league_avg = max(league_avg_gf, 1.0)

        h_attack = h.get("home_gf_per_game", league_avg) / league_avg
        a_defend = a.get("away_ga_per_game", league_avg) / league_avg
        a_attack = a.get("away_gf_per_game", league_avg) / league_avg
        h_defend = h.get("home_ga_per_game", league_avg) / league_avg

        home_xg = round(league_avg * h_attack * a_defend, 2)
        away_xg = round(league_avg * a_attack * h_defend, 2)

        import math
        h_cs_prob = round(math.exp(-away_xg), 2)
        a_cs_prob = round(math.exp(-home_xg), 2)

        return {
            "home_xg": home_xg,
            "away_xg": away_xg,
            "home_cs_prob": h_cs_prob,
            "away_cs_prob": a_cs_prob,
            "total_xg": round(home_xg + away_xg, 2),
        }
