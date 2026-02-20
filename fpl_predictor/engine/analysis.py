"""
Squad Fixture Analysis Engine.

Scores each manager's squad by position across gameweeks using FDR data.
Generates replacement recommendations and optimal lineups.
All data comes live from the FPL API client - no local database.
"""

from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from fpl_predictor.data.fpl_api import FPLClient

POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

EASY_FDR = 2.5
MEDIUM_FDR = 3.5

# Per-player score based on position + FDR tier + star status
# [position][is_star][difficulty_tier]
SCORING = {
    1: {False: {"easy": 1.5, "medium": 1.0, "hard": 0.0},
        True:  {"easy": 1.5, "medium": 1.0, "hard": 0.0}},
    2: {False: {"easy": 1.5, "medium": 1.0, "hard": 0.0},
        True:  {"easy": 2.0, "medium": 1.5, "hard": 0.5}},
    3: {False: {"easy": 1.5, "medium": 1.0, "hard": 0.5},
        True:  {"easy": 2.0, "medium": 1.5, "hard": 1.0}},
    4: {False: {"easy": 2.0, "medium": 1.5, "hard": 1.0},
        True:  {"easy": 2.0, "medium": 1.5, "hard": 1.0}},
}

# Thresholds for position aggregate score -> tier classification
TIER_THRESHOLDS = {
    1: {"hard": 1.0, "medium": 1.5},
    2: {"hard": 4.0, "medium": 5.0},
    3: {"hard": 4.5, "medium": 6.0},
    4: {"hard": 2.0, "medium": 3.0},
}

VALID_FORMATIONS = [
    (1, 3, 5, 2), (1, 3, 4, 3), (1, 4, 5, 1),
    (1, 4, 4, 2), (1, 4, 3, 3), (1, 5, 4, 1),
    (1, 5, 3, 2), (1, 5, 2, 3),
]


def fdr_tier(fdr: float) -> str:
    if fdr <= EASY_FDR:
        return "easy"
    if fdr <= MEDIUM_FDR:
        return "medium"
    return "hard"


def player_score(position: int, is_star: bool, fdr: float) -> float:
    tier = fdr_tier(fdr)
    return SCORING.get(position, SCORING[3])[is_star][tier]


def position_tier(total_score: float, position: int) -> str:
    t = TIER_THRESHOLDS.get(position, TIER_THRESHOLDS[3])
    if total_score < t["hard"]:
        return "hard"
    if total_score < t["medium"]:
        return "medium"
    return "easy"


class SquadAnalyzer:
    """Analyzes a squad's fixture strength across a gameweek range."""

    def __init__(self, client: FPLClient, league_id: int):
        self.client = client
        self.league_id = league_id
        self._fixture_grid = None

    @property
    def fixture_grid(self) -> Dict:
        if self._fixture_grid is None:
            self._fixture_grid = self.client.get_fixture_grid()
        return self._fixture_grid

    def get_fdr(self, team_id: int, gw: int) -> Optional[float]:
        team_gws = self.fixture_grid.get(team_id, {})
        entry = team_gws.get(gw)
        return entry["fdr"] if entry else None

    def analyze_squad(
        self,
        entry_id: int,
        gw_start: int,
        gw_end: int,
        star_player_ids: Optional[List[int]] = None,
        excluded_player_ids: Optional[List[int]] = None,
        replacement_overrides: Optional[Dict[int, int]] = None,
    ) -> Dict:
        """
        Full squad fixture analysis.

        Args:
            entry_id: FPL entry ID
            gw_start / gw_end: gameweek range
            star_player_ids: players that get star bonuses
            excluded_player_ids: players to remove from analysis
            replacement_overrides: {old_player_id: new_player_id} for simulation
        """
        star_ids = set(star_player_ids or [])
        excluded = set(excluded_player_ids or [])
        replacements = replacement_overrides or {}
        current_gw = self.client.get_current_gw()

        squad = self.client.get_enriched_squad(self.league_id, entry_id, current_gw)

        # Apply replacements: swap out old players for new ones
        player_map = self.client.get_player_map()
        team_map = self.client.get_team_map()
        replaced_players = {}

        for old_id, new_id in replacements.items():
            new_player = player_map.get(new_id)
            if not new_player:
                continue
            new_team = team_map.get(new_player["team"], {})
            for i, p in enumerate(squad):
                if p["player_id"] == old_id:
                    replaced_players[old_id] = {
                        "old": p.copy(),
                        "new_id": new_id,
                        "new_name": new_player["web_name"],
                    }
                    squad[i] = {
                        **p,
                        "player_id": new_id,
                        "web_name": new_player["web_name"],
                        "team_id": new_player["team"],
                        "team_short": new_team.get("short_name", "?"),
                        "team_name": new_team.get("name", "?"),
                        "position": new_player["element_type"],
                        "total_points": new_player.get("total_points", 0),
                        "form": _safe_float(new_player.get("form", 0)),
                        "is_replacement": True,
                        "replaced_player_id": old_id,
                    }
                    break

        # Calculate per-player per-GW scores
        for p in squad:
            p["is_star"] = p["player_id"] in star_ids
            p["gw_scores"] = {}
            for gw in range(gw_start, gw_end + 1):
                fdr = self.get_fdr(p["team_id"], gw)
                p["gw_scores"][gw] = player_score(p["position"], p["is_star"], fdr) if fdr else 0.0

        # Filter excluded from analysis but keep in full_squad
        active = [p for p in squad if p["player_id"] not in excluded]
        by_pos = defaultdict(list)
        for p in active:
            by_pos[p["position"]].append(p)

        # Analyze each GW
        by_gameweek = []
        total_score = 0.0
        success_count = 0
        pos_failures = defaultdict(int)

        for gw in range(gw_start, gw_end + 1):
            gw_data = {"gw": gw}
            gw_ok = True
            for pos_id, pos_name in POSITION_NAMES.items():
                players = by_pos.get(pos_id, [])
                score = sum(p["gw_scores"].get(gw, 0) for p in players)
                tier = position_tier(score, pos_id)
                contributors = []
                for p in players:
                    fdr = self.get_fdr(p["team_id"], gw)
                    contributors.append({
                        "player_id": p["player_id"],
                        "name": p["web_name"],
                        "team": p["team_short"],
                        "fdr": fdr,
                        "score": round(p["gw_scores"].get(gw, 0), 2),
                        "tier": fdr_tier(fdr) if fdr else "hard",
                        "is_star": p.get("is_star", False),
                    })
                contributors.sort(key=lambda x: (-x["score"], x["fdr"] or 5))
                gw_data[pos_name] = {
                    "score": round(score, 2),
                    "tier": tier,
                    "thresholds": TIER_THRESHOLDS[pos_id],
                    "players": contributors,
                }
                total_score += score
                if tier != "easy":
                    gw_ok = False
                    pos_failures[pos_name] += 1

            if gw_ok:
                success_count += 1
            by_gameweek.append(gw_data)

        total_gws = gw_end - gw_start + 1
        weakest = max(pos_failures.items(), key=lambda x: x[1])[0] if pos_failures else None

        # Optimal lineups
        optimal = self._optimal_lineups(active, gw_start, gw_end)

        return {
            "entry_id": entry_id,
            "gw_range": {"start": gw_start, "end": gw_end},
            "current_gw": current_gw,
            "total_score": round(total_score, 2),
            "success_rate": round(success_count / total_gws * 100, 1) if total_gws else 0,
            "success_count": success_count,
            "total_gameweeks": total_gws,
            "weakest_position": weakest,
            "position_failures": dict(pos_failures),
            "by_gameweek": by_gameweek,
            "full_squad": squad,
            "optimal_lineups": optimal,
            "replaced_players": replaced_players,
        }

    def get_recommendations(
        self,
        entry_id: int,
        gw_start: int,
        gw_end: int,
        star_player_ids: Optional[List[int]] = None,
        free_agents_only: bool = True,
        limit: int = 50,
    ) -> List[Dict]:
        """
        Generate ranked transfer recommendations.

        Scores candidates based on how much they improve weak gameweeks,
        weighted by FPL performance and team diversity.
        """
        analysis = self.analyze_squad(entry_id, gw_start, gw_end, star_player_ids)

        weak_by_pos: Dict[str, List[int]] = defaultdict(list)
        for gw_data in analysis["by_gameweek"]:
            for pos_name in POSITION_NAMES.values():
                if gw_data[pos_name]["tier"] != "easy":
                    weak_by_pos[pos_name].append(gw_data["gw"])

        squad_team_counts = defaultdict(int)
        for p in analysis["full_squad"]:
            squad_team_counts[p["team_id"]] += 1

        if free_agents_only:
            candidates = self.client.get_free_agents(self.league_id, limit=300)
        else:
            candidates = [
                {"player_id": p["id"], **{k: p.get(k) for k in
                 ["web_name", "team", "element_type", "total_points", "form",
                  "minutes", "goals_scored", "assists", "clean_sheets", "status"]}}
                for p in self.client.get_players() if p.get("minutes", 0) > 0
            ]
            team_map = self.client.get_team_map()
            for c in candidates:
                tid = c.get("team") or c.get("team_id")
                t = team_map.get(tid, {})
                c["team_id"] = tid
                c["team_short"] = t.get("short_name", "?")
                c["team_name"] = t.get("name", "?")
                c["position"] = c.get("element_type", c.get("position", 3))
                c.setdefault("total_points", 0)

        scored = []
        for c in candidates:
            pos_id = c.get("position") or c.get("element_type", 3)
            pos_name = POSITION_NAMES.get(pos_id, "MID")
            weak_gws = weak_by_pos.get(pos_name, [])
            if not weak_gws:
                continue

            tid = c.get("team_id") or c.get("team", 0)
            fixture_score = 0.0
            for gw in weak_gws:
                fdr = self.get_fdr(tid, gw)
                if fdr is None:
                    continue
                tier = fdr_tier(fdr)
                if tier == "easy":
                    fixture_score += 1.0
                elif tier == "medium":
                    fixture_score += 0.5
                else:
                    fixture_score += 0.2

            if fixture_score == 0:
                continue

            fixture_pct = (fixture_score / len(weak_gws)) * 100
            pts = c.get("total_points", 0) or 0
            fpl_pct = min((pts / 150) * 100, 100)
            tc = squad_team_counts.get(tid, 0)
            diversity = max(0, 10 - tc * 5)
            combined = fixture_pct * 0.6 + fpl_pct * 0.4 + diversity

            scored.append({
                "player_id": c.get("player_id") or c.get("id"),
                "name": c.get("web_name", "?"),
                "team": c.get("team_short") or c.get("team_name", "?"),
                "team_id": tid,
                "position": pos_name,
                "position_id": pos_id,
                "total_points": pts,
                "form": _safe_float(c.get("form", 0)),
                "fixture_improvement": round(fixture_pct, 1),
                "fpl_performance": round(fpl_pct, 1),
                "combined_score": round(combined, 1),
                "weak_gws_helped": len(weak_gws),
            })

        scored.sort(key=lambda x: -x["combined_score"])
        return scored[:limit]

    def get_replacement_candidates(
        self,
        entry_id: int,
        player_id: int,
        gw_start: int,
        gw_end: int,
        star_player_ids: Optional[List[int]] = None,
        include_owned: bool = False,
        limit: int = 30,
    ) -> List[Dict]:
        """
        Get ranked replacement candidates for a specific player.

        For each candidate, computes the score impact if they replaced the target player.
        """
        current_gw = self.client.get_current_gw()
        squad = self.client.get_enriched_squad(self.league_id, entry_id, current_gw)
        star_ids = set(star_player_ids or [])
        player_map = self.client.get_player_map()
        team_map = self.client.get_team_map()

        target = None
        for p in squad:
            if p["player_id"] == player_id:
                target = p
                break
        if not target:
            return []

        pos_id = target["position"]

        old_scores = {}
        for gw in range(gw_start, gw_end + 1):
            fdr = self.get_fdr(target["team_id"], gw)
            old_scores[gw] = player_score(pos_id, player_id in star_ids, fdr) if fdr else 0.0

        ownership = self.get_ownership_map_cached()
        squad_ids = {p["player_id"] for p in squad}

        candidates = []
        for pid, pdata in player_map.items():
            if pid in squad_ids:
                continue
            if pdata["element_type"] != pos_id:
                continue
            if pdata.get("minutes", 0) == 0:
                continue
            if not include_owned and ownership.get(pid) is not None:
                continue

            new_scores = {}
            total_impact = 0.0
            for gw in range(gw_start, gw_end + 1):
                fdr = self.get_fdr(pdata["team"], gw)
                ns = player_score(pos_id, False, fdr) if fdr else 0.0
                new_scores[gw] = ns
                total_impact += ns - old_scores.get(gw, 0)

            t = team_map.get(pdata["team"], {})
            owner = ownership.get(pid)
            candidates.append({
                "player_id": pid,
                "name": pdata["web_name"],
                "team": t.get("short_name", "?"),
                "team_id": pdata["team"],
                "position": POSITION_NAMES[pos_id],
                "total_points": pdata.get("total_points", 0),
                "form": _safe_float(pdata.get("form", 0)),
                "impact": round(total_impact, 2),
                "is_free_agent": owner is None,
                "owner_entry_id": owner,
                "avg_new_score": round(sum(new_scores.values()) / max(len(new_scores), 1), 2),
            })

        candidates.sort(key=lambda x: (-x["impact"], -x["total_points"]))
        return candidates[:limit]

    def get_ownership_map_cached(self) -> Dict[int, Optional[int]]:
        return self.client.get_ownership_map(self.league_id)

    def analyze_all_managers(
        self, gw_start: int, gw_end: int,
        star_player_ids: Optional[List[int]] = None,
    ) -> List[Dict]:
        """Analyze and rank all managers in the league."""
        entries = self.client.get_league_entries(self.league_id)
        results = []
        for entry in entries:
            try:
                a = self.analyze_squad(entry["entry_id"], gw_start, gw_end, star_player_ids)
                results.append({
                    "entry_id": entry["entry_id"],
                    "league_entry_id": entry["id"],
                    "entry_name": entry["entry_name"],
                    "player_name": f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}".strip(),
                    "total_score": a["total_score"],
                    "success_rate": a["success_rate"],
                    "weakest_position": a["weakest_position"],
                })
            except Exception as e:
                continue

        results.sort(key=lambda x: -x["total_score"])
        for i, r in enumerate(results, 1):
            r["rank"] = i
        return results

    # ------------------------------------------------------------------
    # Optimal lineup
    # ------------------------------------------------------------------

    def _optimal_lineups(self, squad: List[Dict], gw_start: int, gw_end: int) -> List[Dict]:
        result = []
        for gw in range(gw_start, gw_end + 1):
            by_pos: Dict[int, List] = defaultdict(list)
            for p in squad:
                s = p["gw_scores"].get(gw, 0)
                by_pos[p["position"]].append({
                    "player_id": p["player_id"],
                    "name": p["web_name"],
                    "position": p["position"],
                    "score": s,
                    "team": p["team_short"],
                    "is_star": p.get("is_star", False),
                })
            for pos_id in by_pos:
                by_pos[pos_id].sort(key=lambda x: x["score"], reverse=True)

            best = None
            best_score = -1
            for formation in VALID_FORMATIONS:
                gk, df, mf, fw = formation
                if (len(by_pos.get(1, [])) < gk or len(by_pos.get(2, [])) < df or
                    len(by_pos.get(3, [])) < mf or len(by_pos.get(4, [])) < fw):
                    continue
                lineup = (by_pos[1][:gk] + by_pos[2][:df] +
                          by_pos[3][:mf] + by_pos[4][:fw])
                ts = sum(x["score"] for x in lineup)
                if ts > best_score:
                    best_score = ts
                    best = {"players": lineup,
                            "formation": f"{df}-{mf}-{fw}",
                            "score": round(ts, 2)}

            result.append({"gw": gw, **(best or {"players": [], "formation": "N/A", "score": 0})})
        return result


def _safe_float(val) -> float:
    try:
        f = float(val)
        return 0.0 if f != f else f
    except (ValueError, TypeError):
        return 0.0
