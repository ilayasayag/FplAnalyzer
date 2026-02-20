"""
Live FPL API Client with in-memory caching.

Fetches all data directly from draft.premierleague.com and fantasy.premierleague.com.
Replaces the old DuckDB + bookmarklet pipeline entirely.
"""

import time
import requests
from typing import Dict, List, Optional, Any
from threading import Lock
from dataclasses import dataclass, field

DRAFT_BASE = "https://draft.premierleague.com/api"
FPL_BASE = "https://fantasy.premierleague.com/api"

DEFAULT_CACHE_TTL = 300  # 5 minutes


@dataclass
class CacheEntry:
    data: Any
    fetched_at: float
    ttl: float

    @property
    def expired(self) -> bool:
        return time.time() - self.fetched_at > self.ttl


class FPLClient:
    """
    Stateless FPL API client with TTL-based caching.
    
    All league data is fetched live from the FPL API.
    Cache prevents hammering the API on repeated requests.
    """

    def __init__(self, cache_ttl: float = DEFAULT_CACHE_TTL):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
        self._ttl = cache_ttl
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "FPLAnalyzer/2.0",
            "Accept": "application/json",
        })

    def _get(self, url: str, ttl: Optional[float] = None) -> Any:
        ttl = ttl or self._ttl
        with self._lock:
            entry = self._cache.get(url)
            if entry and not entry.expired:
                return entry.data

        resp = self._session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        with self._lock:
            self._cache[url] = CacheEntry(data=data, fetched_at=time.time(), ttl=ttl)
        return data

    def clear_cache(self):
        with self._lock:
            self._cache.clear()

    # ------------------------------------------------------------------
    # Bootstrap: players, teams, gameweek info
    # ------------------------------------------------------------------

    def get_bootstrap(self) -> Dict:
        """Core data: all players, teams, events, element_types."""
        return self._get(f"{DRAFT_BASE}/bootstrap-static")

    def get_players(self) -> List[Dict]:
        return self.get_bootstrap()["elements"]

    def get_teams(self) -> List[Dict]:
        return self.get_bootstrap()["teams"]

    def get_element_types(self) -> List[Dict]:
        return self.get_bootstrap()["element_types"]

    def get_current_gw(self) -> int:
        events = self.get_bootstrap()["events"]
        return events.get("current") or 1

    def get_next_gw(self) -> int:
        events = self.get_bootstrap()["events"]
        return events.get("next") or (self.get_current_gw() + 1)

    def get_player_map(self) -> Dict[int, Dict]:
        """Map of player_id -> player dict for quick lookups."""
        return {p["id"]: p for p in self.get_players()}

    def get_team_map(self) -> Dict[int, Dict]:
        """Map of team_id -> team dict for quick lookups."""
        return {t["id"]: t for t in self.get_teams()}

    # ------------------------------------------------------------------
    # Fixtures + FDR (from main FPL site, has difficulty ratings)
    # ------------------------------------------------------------------

    def get_fixtures(self) -> List[Dict]:
        """All 380 PL fixtures with FDR ratings."""
        return self._get(f"{FPL_BASE}/fixtures/")

    def get_fixture_grid(self) -> Dict[int, Dict[int, Dict]]:
        """
        Build a fixture grid: team_id -> gw -> {opponent_id, is_home, fdr, opponent_short}
        
        Uses the official FPL FDR ratings from the fixtures endpoint.
        """
        fixtures = self.get_fixtures()
        team_map = self.get_team_map()
        grid: Dict[int, Dict[int, Dict]] = {}

        for f in fixtures:
            gw = f.get("event")
            if gw is None:
                continue
            h, a = f["team_h"], f["team_a"]
            h_fdr, a_fdr = f.get("team_h_difficulty", 3), f.get("team_a_difficulty", 3)

            home_team = team_map.get(h, {})
            away_team = team_map.get(a, {})

            grid.setdefault(h, {})[gw] = {
                "opponent_id": a,
                "opponent_short": away_team.get("short_name", "?"),
                "is_home": True,
                "fdr": h_fdr,
                "display": f"{away_team.get('short_name', '?')}(H)",
            }
            grid.setdefault(a, {})[gw] = {
                "opponent_id": h,
                "opponent_short": home_team.get("short_name", "?"),
                "is_home": False,
                "fdr": a_fdr,
                "display": f"{home_team.get('short_name', '?')}(A)",
            }
        return grid

    def get_fdr(self, team_id: int, gw: int) -> Optional[int]:
        """Get FDR for a specific team in a specific gameweek."""
        grid = self.get_fixture_grid()
        team_gws = grid.get(team_id, {})
        entry = team_gws.get(gw)
        return entry["fdr"] if entry else None

    # ------------------------------------------------------------------
    # League data
    # ------------------------------------------------------------------

    def get_league(self, league_id: int) -> Dict:
        """League details, entries, and match results."""
        return self._get(f"{DRAFT_BASE}/league/{league_id}/details")

    def get_league_entries(self, league_id: int) -> List[Dict]:
        return self.get_league(league_id).get("league_entries", [])

    def get_league_matches(self, league_id: int) -> List[Dict]:
        return self.get_league(league_id).get("matches", [])

    def get_league_info(self, league_id: int) -> Dict:
        return self.get_league(league_id).get("league", {})

    # ------------------------------------------------------------------
    # Element status (ownership)
    # ------------------------------------------------------------------

    def get_element_status(self, league_id: int) -> List[Dict]:
        data = self._get(f"{DRAFT_BASE}/league/{league_id}/element-status")
        return data.get("element_status", [])

    def get_ownership_map(self, league_id: int) -> Dict[int, Optional[int]]:
        """Map of player_id -> owner_entry_id (None if free agent)."""
        statuses = self.get_element_status(league_id)
        return {s["element"]: s.get("owner") for s in statuses}

    # ------------------------------------------------------------------
    # Squads
    # ------------------------------------------------------------------

    def get_squad(self, entry_id: int, gw: int) -> List[Dict]:
        """Get squad picks for an entry in a specific gameweek."""
        data = self._get(f"{DRAFT_BASE}/entry/{entry_id}/event/{gw}")
        return data.get("picks", [])

    def get_all_squads(self, league_id: int, gw: int) -> Dict[int, List[Dict]]:
        """Get squads for all entries in a league for a gameweek."""
        entries = self.get_league_entries(league_id)
        squads = {}
        for entry in entries:
            eid = entry["entry_id"]
            try:
                squads[eid] = self.get_squad(eid, gw)
            except Exception:
                squads[eid] = []
        return squads

    # ------------------------------------------------------------------
    # Transactions & Trades
    # ------------------------------------------------------------------

    def get_transactions(self, league_id: int) -> List[Dict]:
        data = self._get(f"{DRAFT_BASE}/draft/league/{league_id}/transactions")
        return data.get("transactions", [])

    def get_trades(self, league_id: int) -> List[Dict]:
        data = self._get(f"{DRAFT_BASE}/draft/league/{league_id}/trades")
        return data.get("trades", [])

    # ------------------------------------------------------------------
    # Main FPL site (richer stats: xG, xA, per_90, ep_next, etc.)
    # ------------------------------------------------------------------

    def get_main_bootstrap(self) -> Dict:
        """Main FPL bootstrap with richer stats than draft version."""
        return self._get(f"{FPL_BASE}/bootstrap-static/", ttl=600)

    def get_main_players(self) -> List[Dict]:
        return self.get_main_bootstrap()["elements"]

    def get_main_player_map(self) -> Dict[int, Dict]:
        return {p["id"]: p for p in self.get_main_players()}

    def get_main_teams(self) -> List[Dict]:
        return self.get_main_bootstrap()["teams"]

    def get_main_team_map(self) -> Dict[int, Dict]:
        return {t["id"]: t for t in self.get_main_teams()}

    def get_player_history(self, player_id: int) -> Dict:
        """
        Per-GW history + upcoming fixtures for a single player.
        Returns {history: [...], fixtures: [...], history_past: [...]}.
        Cached for 30 minutes (data only changes post-match).
        """
        return self._get(f"{FPL_BASE}/element-summary/{player_id}/", ttl=1800)

    def get_player_gw_history(self, player_id: int) -> List[Dict]:
        """Per-gameweek stats for a player this season."""
        return self.get_player_history(player_id).get("history", [])

    def get_player_upcoming(self, player_id: int) -> List[Dict]:
        """Upcoming fixtures with difficulty for a player."""
        return self.get_player_history(player_id).get("fixtures", [])

    def get_gw_live(self, gw: int) -> List[Dict]:
        """Live stats for all players in a specific gameweek."""
        data = self._get(f"{FPL_BASE}/event/{gw}/live/", ttl=120)
        return data.get("elements", [])

    # ------------------------------------------------------------------
    # Team form from fixture results
    # ------------------------------------------------------------------

    def get_team_season_stats(self) -> Dict[int, Dict]:
        """
        Compute per-team season stats from finished fixtures.
        Returns {team_id: {played, wins, draws, losses, gf, ga, cs, home_gf, ...}}
        """
        fixtures = self.get_fixtures()
        stats: Dict[int, Dict] = {}

        for t in self.get_teams():
            stats[t["id"]] = {
                "team_id": t["id"], "name": t["name"], "short_name": t["short_name"],
                "played": 0, "wins": 0, "draws": 0, "losses": 0,
                "gf": 0, "ga": 0, "cs": 0, "cs_against": 0,
                "home_played": 0, "home_gf": 0, "home_ga": 0, "home_cs": 0,
                "away_played": 0, "away_gf": 0, "away_ga": 0, "away_cs": 0,
            }

        for f in fixtures:
            if not f.get("finished"):
                continue
            h, a = f["team_h"], f["team_a"]
            hs = f.get("team_h_score") or 0
            as_ = f.get("team_a_score") or 0
            if h not in stats or a not in stats:
                continue

            for tid, gf, ga, venue in [(h, hs, as_, "home"), (a, as_, hs, "away")]:
                s = stats[tid]
                s["played"] += 1
                s["gf"] += gf
                s["ga"] += ga
                s[f"{venue}_played"] += 1
                s[f"{venue}_gf"] += gf
                s[f"{venue}_ga"] += ga
                if ga == 0:
                    s["cs"] += 1
                    s[f"{venue}_cs"] += 1
                if gf == 0:
                    s["cs_against"] += 1
                if gf > ga:
                    s["wins"] += 1
                elif gf == ga:
                    s["draws"] += 1
                else:
                    s["losses"] += 1

        for s in stats.values():
            p = max(s["played"], 1)
            s["gf_per_game"] = round(s["gf"] / p, 2)
            s["ga_per_game"] = round(s["ga"] / p, 2)
            s["cs_rate"] = round(s["cs"] / p, 2)
            s["points"] = s["wins"] * 3 + s["draws"]
            hp = max(s["home_played"], 1)
            ap = max(s["away_played"], 1)
            s["home_gf_per_game"] = round(s["home_gf"] / hp, 2)
            s["home_ga_per_game"] = round(s["home_ga"] / hp, 2)
            s["away_gf_per_game"] = round(s["away_gf"] / ap, 2)
            s["away_ga_per_game"] = round(s["away_ga"] / ap, 2)
            s["home_cs_rate"] = round(s["home_cs"] / hp, 2)
            s["away_cs_rate"] = round(s["away_cs"] / ap, 2)

        return stats

    def get_pl_standings(self) -> List[Dict]:
        """PL table sorted by points."""
        stats = self.get_team_season_stats()
        ranked = sorted(stats.values(), key=lambda s: (-s["points"], -(s["gf"] - s["ga"]), -s["gf"]))
        for i, s in enumerate(ranked, 1):
            s["position"] = i
        return ranked

    def get_team_batch_map(self) -> Dict[int, int]:
        """Map team_id -> batch (1-5) based on league position."""
        standings = self.get_pl_standings()
        batch_map = {}
        for s in standings:
            pos = s["position"]
            if pos <= 4:
                batch = 1
            elif pos <= 8:
                batch = 2
            elif pos <= 14:
                batch = 3
            elif pos <= 17:
                batch = 4
            else:
                batch = 5
            batch_map[s["team_id"]] = batch
        return batch_map

    # ------------------------------------------------------------------
    # Bulk player history fetching (for squad players)
    # ------------------------------------------------------------------

    def get_bulk_player_histories(self, player_ids: List[int]) -> Dict[int, List[Dict]]:
        """Fetch GW history for multiple players. Uses cache aggressively."""
        result = {}
        for pid in player_ids:
            try:
                result[pid] = self.get_player_gw_history(pid)
            except Exception:
                result[pid] = []
        return result

    # ------------------------------------------------------------------
    # Enriched data helpers
    # ------------------------------------------------------------------

    def get_enriched_squad(self, league_id: int, entry_id: int, gw: int) -> List[Dict]:
        """
        Get a squad with full player + team details attached.
        
        Returns list of dicts with: player_id, web_name, team_id, team_short,
        position, total_points, form, is_captain, squad_position, etc.
        """
        picks = self.get_squad(entry_id, gw)
        player_map = self.get_player_map()
        team_map = self.get_team_map()

        enriched = []
        for pick in picks:
            pid = pick["element"]
            player = player_map.get(pid)
            if not player:
                continue
            team = team_map.get(player["team"], {})
            enriched.append({
                "player_id": pid,
                "web_name": player["web_name"],
                "first_name": player.get("first_name", ""),
                "second_name": player.get("second_name", ""),
                "team_id": player["team"],
                "team_short": team.get("short_name", "?"),
                "team_name": team.get("name", "?"),
                "position": player["element_type"],
                "total_points": player.get("total_points", 0),
                "form": _safe_float(player.get("form", 0)),
                "points_per_game": _safe_float(player.get("points_per_game", 0)),
                "minutes": player.get("minutes", 0),
                "goals_scored": player.get("goals_scored", 0),
                "assists": player.get("assists", 0),
                "clean_sheets": player.get("clean_sheets", 0),
                "status": player.get("status", "a"),
                "news": player.get("news", ""),
                "chance_of_playing": player.get("chance_of_playing_next_round"),
                "is_captain": pick.get("is_captain", False),
                "is_vice_captain": pick.get("is_vice_captain", False),
                "squad_position": pick.get("position", 0),
            })
        return enriched

    def get_free_agents(self, league_id: int, position: Optional[int] = None,
                        sort_by: str = "total_points", limit: int = 100) -> List[Dict]:
        """
        Get unowned players (free agents) enriched with team info.
        
        Args:
            league_id: League ID
            position: Filter by position (1-4), None for all
            sort_by: Sort field (total_points, form, minutes)
            limit: Max results
        """
        ownership = self.get_ownership_map(league_id)
        player_map = self.get_player_map()
        team_map = self.get_team_map()

        free = []
        for pid, owner in ownership.items():
            if owner is not None:
                continue
            player = player_map.get(pid)
            if not player:
                continue
            if position and player["element_type"] != position:
                continue
            if player.get("minutes", 0) == 0:
                continue

            team = team_map.get(player["team"], {})
            free.append({
                "player_id": pid,
                "web_name": player["web_name"],
                "team_id": player["team"],
                "team_short": team.get("short_name", "?"),
                "team_name": team.get("name", "?"),
                "position": player["element_type"],
                "total_points": player.get("total_points", 0),
                "form": _safe_float(player.get("form", 0)),
                "points_per_game": _safe_float(player.get("points_per_game", 0)),
                "minutes": player.get("minutes", 0),
                "goals_scored": player.get("goals_scored", 0),
                "assists": player.get("assists", 0),
                "clean_sheets": player.get("clean_sheets", 0),
                "status": player.get("status", "a"),
            })

        free.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
        return free[:limit]

    def get_standings(self, league_id: int) -> List[Dict]:
        """Compute league standings from match results."""
        entries = self.get_league_entries(league_id)
        matches = self.get_league_matches(league_id)

        entry_map = {e["id"]: e for e in entries}
        stats: Dict[int, Dict] = {}
        for e in entries:
            stats[e["id"]] = {
                "id": e["id"],
                "entry_id": e["entry_id"],
                "entry_name": e["entry_name"],
                "player_name": f"{e.get('player_first_name', '')} {e.get('player_last_name', '')}".strip(),
                "wins": 0, "draws": 0, "losses": 0,
                "points_for": 0, "points_against": 0, "league_points": 0,
            }

        for m in matches:
            if not m.get("finished"):
                continue
            e1, e2 = m.get("league_entry_1"), m.get("league_entry_2")
            p1 = m.get("league_entry_1_points", 0) or 0
            p2 = m.get("league_entry_2_points", 0) or 0
            if e1 not in stats or e2 not in stats:
                continue

            stats[e1]["points_for"] += p1
            stats[e1]["points_against"] += p2
            stats[e2]["points_for"] += p2
            stats[e2]["points_against"] += p1

            if p1 > p2:
                stats[e1]["wins"] += 1
                stats[e1]["league_points"] += 3
                stats[e2]["losses"] += 1
            elif p2 > p1:
                stats[e2]["wins"] += 1
                stats[e2]["league_points"] += 3
                stats[e1]["losses"] += 1
            else:
                stats[e1]["draws"] += 1
                stats[e1]["league_points"] += 1
                stats[e2]["draws"] += 1
                stats[e2]["league_points"] += 1

        ranked = sorted(stats.values(),
                        key=lambda s: (-s["league_points"], -s["points_for"]))
        for i, s in enumerate(ranked, 1):
            s["rank"] = i
            s["played"] = s["wins"] + s["draws"] + s["losses"]
        return ranked


def _safe_float(val) -> float:
    try:
        f = float(val)
        if f != f:  # NaN check
            return 0.0
        return f
    except (ValueError, TypeError):
        return 0.0
