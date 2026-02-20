"""
Predicted Lineups Module.

Estimates likely starting XIs based on:
- FPL news/availability from the API
- Historical minutes and starts patterns
- Recent form and rotation patterns
- Injury/suspension status
"""

from typing import Dict, List, Optional
from collections import defaultdict
from fpl_predictor.data.fpl_api import FPLClient, _safe_float


POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


class LineupPredictor:

    def __init__(self, client: FPLClient):
        self.client = client

    def predict_team_lineup(self, team_id: int) -> Dict:
        """
        Predict likely starting XI for a PL team.
        Uses FPL news, minutes data, starts, and recent patterns.
        """
        draft_players = self.client.get_players()
        draft_to_main = self.client.get_draft_to_main_map()
        team_map = self.client.get_team_map()

        squad = [p for p in draft_players if p["team"] == team_id]
        current_gw = self.client.get_current_gw()

        scored = []
        for p in squad:
            main = draft_to_main.get(p["id"], {})
            score = self._availability_score(p, main, current_gw)
            scored.append({
                "player_id": p["id"],
                "web_name": p["web_name"],
                "position": p["element_type"],
                "pos_name": POS_NAMES.get(p["element_type"], "?"),
                "total_points": p.get("total_points", 0),
                "minutes": p.get("minutes", 0),
                "status": p.get("status", "a"),
                "news": main.get("news", p.get("news", "")),
                "chance_of_playing": main.get("chance_of_playing_next_round"),
                "form": _safe_float(p.get("form", 0)),
                "availability_score": score,
                "avg_mins": round(p.get("minutes", 0) / max(current_gw, 1), 1),
                "starts_est": self._estimate_starts(p, current_gw),
            })

        scored.sort(key=lambda x: (-x["availability_score"], -x["total_points"]))

        by_pos = defaultdict(list)
        for p in scored:
            by_pos[p["position"]].append(p)

        predicted_xi = []
        subs = []
        slots = {1: 1, 2: 4, 3: 4, 4: 2}

        for pos in [1, 2, 3, 4]:
            available = by_pos[pos]
            count = slots[pos]
            for p in available[:count]:
                predicted_xi.append({**p, "role": "starter"})
            for p in available[count:]:
                subs.append({**p, "role": "sub"})

        team = team_map.get(team_id, {})
        return {
            "team_id": team_id,
            "team_name": team.get("name", "?"),
            "team_short": team.get("short_name", "?"),
            "predicted_xi": predicted_xi,
            "subs": subs,
            "confidence": self._team_confidence(predicted_xi),
        }

    def predict_all_teams(self) -> List[Dict]:
        """Predict lineups for all 20 PL teams."""
        teams = self.client.get_teams()
        return [self.predict_team_lineup(t["id"]) for t in teams]

    def predict_gw_fixtures(self, gw: int) -> List[Dict]:
        """
        All fixtures for a GW with predicted lineups for both teams.
        """
        fixtures = self.client.get_fixtures()
        team_map = self.client.get_team_map()
        gw_fixtures = [f for f in fixtures if f.get("event") == gw]
        result = []
        for f in gw_fixtures:
            h_id, a_id = f["team_h"], f["team_a"]
            h_team = team_map.get(h_id, {})
            a_team = team_map.get(a_id, {})
            h_lineup = self.predict_team_lineup(h_id)
            a_lineup = self.predict_team_lineup(a_id)
            result.append({
                "fixture_id": f.get("id"),
                "kickoff": f.get("kickoff_time"),
                "home": {
                    "team_id": h_id,
                    "team_name": h_team.get("name", "?"),
                    "team_short": h_team.get("short_name", "?"),
                    "lineup": h_lineup,
                },
                "away": {
                    "team_id": a_id,
                    "team_name": a_team.get("name", "?"),
                    "team_short": a_team.get("short_name", "?"),
                    "lineup": a_lineup,
                },
                "finished": f.get("finished", False),
                "score": f"{f.get('team_h_score', '-')} - {f.get('team_a_score', '-')}" if f.get("finished") else None,
            })
        return result

    def validate_accuracy(self, gw: int) -> Dict:
        """
        Validate predicted lineups accuracy against actual minutes played
        in a past GW. Uses live GW data to check who actually played.
        """
        try:
            live_data = self.client.get_gw_live(gw)
        except Exception:
            return {"error": f"Could not fetch live data for GW {gw}"}

        actual_starters = {}
        for elem in live_data:
            pid = elem["id"]
            stats = elem.get("stats", {})
            mins = stats.get("minutes", 0)
            started = stats.get("starts", 0)
            if started > 0:
                actual_starters[pid] = mins

        player_map = self.client.get_player_map()
        teams = self.client.get_teams()
        actual_by_team = defaultdict(set)
        for pid in actual_starters:
            p = player_map.get(pid, {})
            if p:
                actual_by_team[p["team"]].add(pid)

        results = []
        for t in teams:
            tid = t["id"]
            predicted = self.predict_team_lineup(tid)
            pred_ids = {p["player_id"] for p in predicted.get("predicted_xi", [])}
            actual_ids = actual_by_team.get(tid, set())

            correct = pred_ids & actual_ids
            accuracy = round(len(correct) / max(len(pred_ids), 1) * 100, 1)

            results.append({
                "team_id": tid,
                "team_short": t.get("short_name", "?"),
                "team_name": t.get("name", "?"),
                "predicted_count": len(pred_ids),
                "actual_starters": len(actual_ids),
                "correct": len(correct),
                "accuracy": accuracy,
            })

        avg_accuracy = round(sum(r["accuracy"] for r in results) / max(len(results), 1), 1)
        return {
            "gw": gw,
            "teams": results,
            "avg_accuracy": avg_accuracy,
        }

    def get_player_availability(self, league_id: int) -> List[Dict]:
        """
        Get availability info for all players in a league's squads.
        Combines FPL news, minutes data, and predicted lineup status.
        """
        current_gw = self.client.get_current_gw()
        entries = self.client.get_league_entries(league_id)
        draft_to_main = self.client.get_draft_to_main_map()
        player_map = self.client.get_player_map()
        team_map = self.client.get_team_map()
        result = []

        for entry in entries:
            eid = entry["entry_id"]
            try:
                squad = self.client.get_squad(eid, current_gw)
            except Exception:
                continue
            for pick in squad:
                pid = pick["element"]
                p = player_map.get(pid, {})
                main = draft_to_main.get(pid, {})
                if not p:
                    continue
                team = team_map.get(p["team"], {})
                score = self._availability_score(p, main, current_gw)
                result.append({
                    "entry_id": eid,
                    "entry_name": entry.get("entry_name", "?"),
                    "player_id": pid,
                    "web_name": p.get("web_name", "?"),
                    "team_short": team.get("short_name", "?"),
                    "position": p.get("element_type", 0),
                    "status": p.get("status", "a"),
                    "news": main.get("news", ""),
                    "chance_of_playing": main.get("chance_of_playing_next_round"),
                    "availability_score": score,
                    "minutes": p.get("minutes", 0),
                    "form": _safe_float(p.get("form", 0)),
                })
        return result

    # ------------------------------------------------------------------
    # Internal scoring
    # ------------------------------------------------------------------

    def _availability_score(self, draft_p: Dict, main_p: Dict, current_gw: int) -> float:
        """0-100 availability score combining all signals."""
        status = draft_p.get("status", "a")
        if status == "u":
            return 0
        if status == "i":
            return 5
        if status == "s":
            return 0

        cop = main_p.get("chance_of_playing_next_round")
        if cop is not None:
            base = cop
        elif status == "d":
            base = 40
        elif status == "a":
            base = 85
        else:
            base = 50

        mins = draft_p.get("minutes", 0)
        avg_mins = mins / max(current_gw, 1)
        if avg_mins >= 80:
            mins_adj = 15
        elif avg_mins >= 60:
            mins_adj = 10
        elif avg_mins >= 30:
            mins_adj = 0
        else:
            mins_adj = -15

        return min(100, max(0, base + mins_adj))

    def _estimate_starts(self, player: Dict, current_gw: int) -> int:
        avg_mins = player.get("minutes", 0) / max(current_gw, 1)
        if avg_mins >= 70:
            return round(current_gw * 0.85)
        if avg_mins >= 50:
            return round(current_gw * 0.65)
        if avg_mins >= 25:
            return round(current_gw * 0.4)
        return round(current_gw * 0.15)

    def _team_confidence(self, xi: List[Dict]) -> str:
        avg_score = sum(p["availability_score"] for p in xi) / max(len(xi), 1)
        if avg_score >= 85:
            return "high"
        if avg_score >= 65:
            return "medium"
        return "low"
