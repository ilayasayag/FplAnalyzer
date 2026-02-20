"""
N-D-K Simulator for FPL Draft Teams.

Scores FPL teams based on their PL team composition and upcoming fixture difficulty.
N (Nailedness) - lineup reliability and minutes
D (Difficulty)  - fixture difficulty of owned PL teams  
K (Klean)      - clean sheet and defensive potential

Also handles GW-level team comparison and fixture batch analysis.
"""

from typing import Dict, List
from collections import defaultdict
from fpl_predictor.data.fpl_api import FPLClient, _safe_float


class NDKSimulator:

    def __init__(self, client: FPLClient):
        self.client = client

    def score_team(self, league_id: int, entry_id: int,
                   gw_start: int, gw_end: int) -> Dict:
        """
        Compute N-D-K scores for an FPL team.
        N (Nailedness): avg minutes & starts reliability (0-10)
        D (Difficulty):  fixture difficulty advantage (0-10)
        K (Klean):      defensive/CS potential (0-10)
        """
        current_gw = self.client.get_current_gw()
        squad = self.client.get_enriched_squad(league_id, entry_id, current_gw)
        grid = self.client.get_fixture_grid()
        team_stats = self.client.get_team_season_stats()
        batch_map = self.client.get_team_batch_map()

        n_score = self._nailedness(squad)
        d_score = self._difficulty(squad, grid, gw_start, gw_end)
        k_score = self._klean(squad, team_stats, grid, gw_start, gw_end)
        composite = round(n_score * 0.3 + d_score * 0.4 + k_score * 0.3, 1)

        pl_teams = defaultdict(list)
        for p in squad:
            pl_teams[p["team_short"]].append(p["web_name"])

        return {
            "entry_id": entry_id,
            "gw_range": [gw_start, gw_end],
            "nailedness": round(n_score, 1),
            "difficulty": round(d_score, 1),
            "klean": round(k_score, 1),
            "composite": composite,
            "pl_team_exposure": dict(pl_teams),
            "squad_size": len(squad),
        }

    def score_all_teams(self, league_id: int, gw_start: int, gw_end: int) -> List[Dict]:
        """Score all teams in a league, ranked by composite."""
        entries = self.client.get_league_entries(league_id)
        results = []
        for e in entries:
            entry_id = e["entry_id"]
            name = e.get("entry_name", "?")
            player_name = f"{e.get('player_first_name', '')} {e.get('player_last_name', '')}".strip()
            score = self.score_team(league_id, entry_id, gw_start, gw_end)
            score["entry_name"] = name
            score["player_name"] = player_name
            results.append(score)
        results.sort(key=lambda x: -x["composite"])
        for i, r in enumerate(results, 1):
            r["rank"] = i
        return results

    def compare_teams(self, league_id: int, entry1: int, entry2: int,
                      gw_start: int, gw_end: int) -> Dict:
        """Side-by-side N-D-K comparison of two FPL teams."""
        s1 = self.score_team(league_id, entry1, gw_start, gw_end)
        s2 = self.score_team(league_id, entry2, gw_start, gw_end)

        entries = {e["entry_id"]: e for e in self.client.get_league_entries(league_id)}
        e1 = entries.get(entry1, {})
        e2 = entries.get(entry2, {})

        return {
            "gw_range": [gw_start, gw_end],
            "team_1": {**s1, "entry_name": e1.get("entry_name", "?")},
            "team_2": {**s2, "entry_name": e2.get("entry_name", "?")},
            "advantage": {
                "nailedness": 1 if s1["nailedness"] > s2["nailedness"] else 2,
                "difficulty": 1 if s1["difficulty"] > s2["difficulty"] else 2,
                "klean": 1 if s1["klean"] > s2["klean"] else 2,
                "composite": 1 if s1["composite"] > s2["composite"] else 2,
            },
        }

    # ------------------------------------------------------------------
    # Internal scoring
    # ------------------------------------------------------------------

    def _nailedness(self, squad: List[Dict]) -> float:
        """Score 0-10 based on how nailed squad players are."""
        if not squad:
            return 0
        scores = []
        for p in squad:
            mins = p.get("minutes", 0)
            status = p.get("status", "a")

            if status == "i":
                scores.append(0)
                continue
            if status == "d":
                scores.append(2)
                continue

            # estimate starts from total minutes / GWs played
            current_gw = self.client.get_current_gw()
            avg_mins = mins / max(current_gw, 1)

            if avg_mins >= 80:
                scores.append(10)
            elif avg_mins >= 65:
                scores.append(8)
            elif avg_mins >= 45:
                scores.append(5)
            elif avg_mins >= 20:
                scores.append(3)
            else:
                scores.append(1)

        starting = squad[:11]
        bench = squad[11:]
        s_scores = scores[:11] if len(scores) >= 11 else scores
        b_scores = scores[11:] if len(scores) > 11 else []

        avg_s = sum(s_scores) / max(len(s_scores), 1)
        avg_b = sum(b_scores) / max(len(b_scores), 1) if b_scores else 3
        return avg_s * 0.8 + avg_b * 0.2

    def _difficulty(self, squad, grid, gw_start, gw_end) -> float:
        """Score 0-10 based on how easy the upcoming fixtures are."""
        fdr_score_map = {1: 10, 2: 7.5, 3: 5, 4: 2.5, 5: 0}
        scores = []
        seen_teams = set()
        for p in squad[:11]:
            team_id = p.get("team_id")
            if not team_id or team_id in seen_teams:
                continue
            seen_teams.add(team_id)
            for gw in range(gw_start, gw_end + 1):
                fix = grid.get(team_id, {}).get(gw)
                if fix:
                    scores.append(fdr_score_map.get(fix["fdr"], 5))

        if not scores:
            return 5.0
        return round(sum(scores) / len(scores), 1)

    def _klean(self, squad, team_stats, grid, gw_start, gw_end) -> float:
        """Score 0-10 for defensive/clean sheet potential."""
        def_players = [p for p in squad[:11] if p["position"] in (1, 2)]
        if not def_players:
            return 3.0

        cs_potentials = []
        for p in def_players:
            tid = p.get("team_id")
            ts = team_stats.get(tid, {})
            team_cs_rate = ts.get("cs_rate", 0.2)

            for gw in range(gw_start, gw_end + 1):
                fix = grid.get(tid, {}).get(gw)
                if not fix:
                    continue
                fdr = fix["fdr"]
                adj = {1: 1.4, 2: 1.2, 3: 1.0, 4: 0.7, 5: 0.5}.get(fdr, 1.0)
                cs_potentials.append(team_cs_rate * adj)

        if not cs_potentials:
            return 3.0

        avg_cs = sum(cs_potentials) / len(cs_potentials)
        return round(min(10, avg_cs * 25), 1)
