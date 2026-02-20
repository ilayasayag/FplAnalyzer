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
        main_players = self.client.get_main_player_map()
        team_map = self.client.get_team_map()

        squad = [p for p in draft_players if p["team"] == team_id]
        current_gw = self.client.get_current_gw()

        scored = []
        for p in squad:
            main = main_players.get(p["id"], {})
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

    def get_player_availability(self, league_id: int) -> List[Dict]:
        """
        Get availability info for all players in a league's squads.
        Combines FPL news, minutes data, and predicted lineup status.
        """
        current_gw = self.client.get_current_gw()
        entries = self.client.get_league_entries(league_id)
        main_players = self.client.get_main_player_map()
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
                main = main_players.get(pid, {})
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
