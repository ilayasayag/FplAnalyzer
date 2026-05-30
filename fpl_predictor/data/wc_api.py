"""
WC2026Client — api-sports.io wrapper for World Cup 2026 data.

Replaces FPLClient entirely for the WC fantasy system.
API key loaded from secrets.json.
"""

import json
import os
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

import requests

_SECRETS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "secrets.json")

_secrets = {}
if os.path.exists(_SECRETS_PATH):
    try:
        with open(_SECRETS_PATH) as _f:
            _secrets = json.load(_f)
    except Exception as e:
        print(f"[wc_api] Failed to load secrets.json: {e}")

API_KEY = os.environ.get("FOOTBALL_API_KEY") or _secrets.get("FOOTBALL_API_KEY", "")
API_BASE = os.environ.get("FOOTBALL_API_BASE") or _secrets.get("FOOTBALL_API_BASE", "https://v3.football.api-sports.io")

WC_LEAGUE = 1       # api-sports league_id for FIFA World Cup
WC_SEASON = 2026

POS_MAP = {"Goalkeeper": 1, "Defender": 2, "Midfielder": 3, "Attacker": 4}
POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

LIVE_STATUSES = {"1H", "2H", "HT", "ET", "BT", "P"}
FINISHED_STATUSES = {"FT", "AET", "PEN"}


class WC2026Client:
    """
    api-sports.io client for WC 2026.

    Free tier: 100 requests/day. All non-live responses are cached aggressively.
    Completed fixture stats are cached permanently (processedForFantasy gate prevents re-fetch).
    """

    def __init__(self, db=None):
        self.db = db  # optional Firestore db for usage tracking
        self._cache: Dict[str, Dict] = {}
        self._lock = Lock()
        self._session = requests.Session()
        self._session.headers.update({
            "x-apisports-key": API_KEY,
            "Accept": "application/json",
        })
        self._today_count = 0
        self._today_date = datetime.now(timezone.utc).date().isoformat()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _today(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _get(self, endpoint: str, params: Dict = None, ttl: float = 300) -> Any:
        """
        GET from api-sports with TTL cache.
        ttl=0 means no caching (always fresh).
        ttl=float("inf") means cache forever (for completed fixture data).
        """
        params = params or {}
        cache_key = f"{endpoint}?{sorted(params.items())}"

        if ttl > 0:
            with self._lock:
                entry = self._cache.get(cache_key)
                if entry:
                    age = time.time() - entry["fetched_at"]
                    if age < ttl:
                        return entry["data"]

        self._track_request()
        url = f"{API_BASE}/{endpoint.lstrip('/')}"
        resp = self._session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if ttl > 0:
            with self._lock:
                self._cache[cache_key] = {
                    "data": data,
                    "fetched_at": time.time(),
                }
        return data

    def _track_request(self):
        today = self._today()
        if today != self._today_date:
            self._today_date = today
            self._today_count = 0
        self._today_count += 1

        if self.db:
            try:
                ref = self.db.collection("wc_api_usage").document(today)
                from google.cloud.firestore_v1 import Increment
                ref.set({"requests": Increment(1)}, merge=True)
            except Exception:
                pass

    def get_daily_usage(self) -> int:
        return self._today_count

    # ------------------------------------------------------------------
    # One-time setup: sync squads + fixtures into Firestore
    # ------------------------------------------------------------------

    def sync_all_squads(self, db=None) -> Dict[str, int]:
        """
        Fetch all ~48 WC 2026 national team squads from api-sports
        and write wc_players + wc_teams into Firestore.

        Returns {"teams": 48, "players": N}.
        """
        db = db or self.db
        if not db:
            raise RuntimeError("Firestore db required for sync_all_squads")

        teams_data = self._get("teams", {
            "league": WC_LEAGUE,
            "season": WC_SEASON,
        }, ttl=86400)

        teams = teams_data.get("response", [])
        player_count = 0
        team_count = 0

        for t in teams:
            team = t.get("team", {})
            tid = team.get("id")
            if not tid:
                continue

            team_doc = {
                "id": tid,
                "name": team.get("name", ""),
                "logo": team.get("logo", ""),
                "isoCode": "",
                "group": "",
                "eliminated": False,
                "eliminatedAfterGw": None,
                "groupFinished": False,
            }
            db.collection("wc_teams").document(str(tid)).set(team_doc, merge=True)
            team_count += 1

            squad_data = self._get("players/squads", {"team": tid}, ttl=604800)
            for entry in squad_data.get("response", []):
                for player in entry.get("players", []):
                    pid = player.get("id")
                    if not pid:
                        continue
                    raw_pos = player.get("position", "")
                    pos_int = POS_MAP.get(raw_pos, 3)
                    player_doc = {
                        "id": pid,
                        "name": player.get("name", ""),
                        "photo": player.get("photo", ""),
                        "position": pos_int,
                        "positionName": POS_NAMES[pos_int],
                        "teamId": tid,
                        "teamName": team.get("name", ""),
                        "teamIso": "",
                        "eliminated": False,
                        "draftRank": 0,
                    }
                    db.collection("wc_players").document(str(pid)).set(
                        player_doc, merge=True
                    )
                    player_count += 1

        return {"teams": team_count, "players": player_count}

    def sync_fixtures(self, db=None) -> int:
        """
        Fetch all WC 2026 fixtures and write to wc_fixtures.
        Includes GW assignment based on WC round name.
        Returns count of fixtures written.
        """
        db = db or self.db
        if not db:
            raise RuntimeError("Firestore db required for sync_fixtures")

        data = self._get("fixtures", {
            "league": WC_LEAGUE,
            "season": WC_SEASON,
        }, ttl=3600)

        fixtures = data.get("response", [])
        written = 0

        for f in fixtures:
            fixture = f.get("fixture", {})
            league = f.get("league", {})
            teams = f.get("teams", {})
            goals = f.get("goals", {})

            fid = fixture.get("id")
            if not fid:
                continue

            wc_round = league.get("round", "")
            gw = _wc_round_to_gw(wc_round)
            if gw == 0:
                continue

            status_obj = fixture.get("status", {})
            status_short = status_obj.get("short", "NS")
            kickoff_raw = fixture.get("date")
            kickoff = None
            if kickoff_raw:
                try:
                    kickoff = datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00"))
                except ValueError:
                    pass

            doc = {
                "id": fid,
                "gw": gw,
                "wcRound": wc_round,
                "homeTeam": {
                    "id": teams.get("home", {}).get("id"),
                    "name": teams.get("home", {}).get("name", ""),
                    "isoCode": "",
                },
                "awayTeam": {
                    "id": teams.get("away", {}).get("id"),
                    "name": teams.get("away", {}).get("name", ""),
                    "isoCode": "",
                },
                "kickoff": kickoff,
                "status": _normalize_status(status_short),
                "score": {
                    "home": goals.get("home"),
                    "away": goals.get("away"),
                },
                "processedForFantasy": False,
            }
            db.collection("wc_fixtures").document(str(fid)).set(doc, merge=True)
            written += 1

        return written

    # ------------------------------------------------------------------
    # Player pool (reads from Firestore)
    # ------------------------------------------------------------------

    def _enrich_player_fpl_compat(self, p: Dict) -> Dict:
        if not p:
            return p
        p["element_type"] = p.get("position")
        p["web_name"] = p.get("name", "?")
        p["team"] = p.get("teamIso") or p.get("teamId", 0)
        p["teamShort"] = p.get("teamIso")
        p["draft_rank"] = p.get("draftRank", 0)
        p["total_points"] = p.get("totalPoints", 0)
        p["form"] = p.get("form", "0")
        return p

    def get_player(self, player_id: int, db=None) -> Optional[Dict]:
        db = db or self.db
        if not db:
            return None
        doc = db.collection("wc_players").document(str(player_id)).get()
        return self._enrich_player_fpl_compat(doc.to_dict()) if doc.exists else None

    def get_player_map(self, db=None) -> Dict[int, Dict]:
        db = db or self.db
        if not db:
            return {}
        docs = db.collection("wc_players").get()
        return {int(d.id): self._enrich_player_fpl_compat(d.to_dict()) for d in docs}

    def get_all_players(self, db=None) -> List[Dict]:
        db = db or self.db
        if not db:
            return []
        docs = db.collection("wc_players").stream()
        return [self._enrich_player_fpl_compat(d.to_dict()) for d in docs]

    def get_players(self, db=None) -> List[Dict]:
        return self.get_all_players(db)

    def get_players_by_team(self, team_id: int, db=None) -> List[Dict]:
        db = db or self.db
        if not db:
            return []
        docs = (db.collection("wc_players")
                .where("teamId", "==", team_id).get())
        return [self._enrich_player_fpl_compat(d.to_dict()) for d in docs]

    def get_team(self, team_id: int, db=None) -> Optional[Dict]:
        db = db or self.db
        if not db:
            return None
        doc = db.collection("wc_teams").document(str(team_id)).get()
        t = doc.to_dict() if doc.exists else None
        if t and "short_name" not in t:
            name = t.get("name", "")
            t["short_name"] = name[:3].upper() if name else "???"
        return t

    def get_all_teams(self, db=None) -> List[Dict]:
        db = db or self.db
        if not db:
            return []
        docs = db.collection("wc_teams").stream()
        res = []
        for d in docs:
            t = d.to_dict()
            if "short_name" not in t:
                name = t.get("name", "")
                t["short_name"] = name[:3].upper() if name else "???"
            res.append(t)
        return res

    def get_teams(self, db=None) -> List[Dict]:
        return self.get_all_teams(db)

    def get_team_map(self, db=None) -> Dict[int, Dict]:
        db = db or self.db
        if not db:
            return {}
        teams = self.get_all_teams(db)
        return {int(t["id"]): t for t in teams if "id" in t}

    # ------------------------------------------------------------------
    # Live data (hits api-sports, TTL-cached)
    # ------------------------------------------------------------------

    def get_live_fixtures(self) -> List[Dict]:
        """Returns fixtures currently in progress (1H, 2H, HT, ET)."""
        data = self._get("fixtures", {
            "league": WC_LEAGUE,
            "season": WC_SEASON,
            "live": "all",
        }, ttl=60)
        return data.get("response", [])

    def get_fixture_events(self, fixture_id: int, use_cache: bool = True) -> List[Dict]:
        """Goals, assists, cards, own goals, substitutions for a fixture."""
        ttl = 300 if use_cache else 0
        data = self._get("fixtures/events", {"fixture": fixture_id}, ttl=ttl)
        return data.get("response", [])

    def get_fixture_player_stats(self, fixture_id: int, use_cache: bool = True) -> List[Dict]:
        """
        Per-player stats for a fixture.
        Falls back to event reconstruction if stats not available (coverage gap).
        """
        ttl = 300 if use_cache else 0
        data = self._get("fixtures/players", {"fixture": fixture_id}, ttl=ttl)
        stats = data.get("response", [])

        if not stats:
            events = self.get_fixture_events(fixture_id, use_cache=use_cache)
            return _reconstruct_stats_from_events(events, fixture_id)

        return stats

    def get_fixture_statistics(self, fixture_id: int) -> List[Dict]:
        """Team-level fixture statistics (shots, possession, etc.)."""
        data = self._get("fixtures/statistics", {"fixture": fixture_id}, ttl=600)
        return data.get("response", [])

    def get_gw_fixtures(self, gw: int, db=None) -> List[Dict]:
        """Read GW fixtures from Firestore (already synced)."""
        db = db or self.db
        if not db:
            return []
        docs = db.collection("wc_fixtures").where("gw", "==", gw).get()
        return [d.to_dict() for d in docs]

    # ------------------------------------------------------------------
    # Group standings + elimination detection
    # ------------------------------------------------------------------

    def get_group_standings(self, group: str) -> List[Dict]:
        """
        Fetch group standings from api-sports.
        group = "A" through "L" for WC 2026.
        """
        data = self._get("standings", {
            "league": WC_LEAGUE,
            "season": WC_SEASON,
        }, ttl=1800)

        all_standings = data.get("response", [])
        for entry in all_standings:
            for league_data in entry.get("league", {}).get("standings", []):
                if not league_data:
                    continue
                group_name = league_data[0].get("group", "") if league_data else ""
                if group.upper() in group_name.upper():
                    return league_data
        return []

    def get_all_group_standings(self) -> Dict[str, List[Dict]]:
        """All 12 group standings in one call (api-sports returns all at once)."""
        data = self._get("standings", {
            "league": WC_LEAGUE,
            "season": WC_SEASON,
        }, ttl=1800)

        result: Dict[str, List[Dict]] = {}
        for entry in data.get("response", []):
            for league_data in entry.get("league", {}).get("standings", []):
                for group_standings in (league_data if isinstance(league_data[0], list) else [league_data]):
                    if group_standings:
                        grp_name = group_standings[0].get("group", "")
                        for letter in "ABCDEFGHIJKL":
                            if f"Group {letter}" == grp_name or grp_name.endswith(f" {letter}"):
                                result[letter] = group_standings
                                break
        return result

    def compute_group_standings_from_db(self, db=None) -> Dict[str, List[Dict]]:
        db = db or self.db
        if not db:
            raise RuntimeError("Firestore db required")
            
        # 1. Fetch all 48 teams to know their groups
        teams_docs = db.collection("wc_teams").get()
        teams_by_iso = {}
        group_teams = {} # group_letter -> list of team_info
        for doc in teams_docs:
            t = doc.to_dict()
            iso = t.get("isoCode")
            grp = t.get("group")
            if iso and grp:
                teams_by_iso[iso] = t
                if grp not in group_teams:
                    group_teams[grp] = []
                group_teams[grp].append(t)
                
        # 2. Fetch all group stage fixtures (GW 1, 2, 3)
        fixtures_docs = db.collection("wc_fixtures").where("gw", "in", [1, 2, 3]).get()
        
        # 3. Accumulate stats
        stats = {} # team_iso -> {P, W, D, L, GF, GA, GD, Pts}
        for iso in teams_by_iso:
            stats[iso] = {"P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "GD": 0, "Pts": 0}
            
        for doc in fixtures_docs:
            f = doc.to_dict()
            score = f.get("score", {})
            h_score = score.get("home")
            a_score = score.get("away")
            h_iso = f.get("homeTeam", {}).get("isoCode")
            a_iso = f.get("awayTeam", {}).get("isoCode")
            
            if h_iso not in stats or a_iso not in stats:
                continue
            if h_score is None or a_score is None:
                continue
                
            stats[h_iso]["P"] += 1
            stats[a_iso]["P"] += 1
            stats[h_iso]["GF"] += h_score
            stats[h_iso]["GA"] += a_score
            stats[a_iso]["GF"] += a_score
            stats[a_iso]["GA"] += h_score
            stats[h_iso]["GD"] = stats[h_iso]["GF"] - stats[h_iso]["GA"]
            stats[a_iso]["GD"] = stats[a_iso]["GF"] - stats[a_iso]["GA"]
            
            if h_score > a_score:
                stats[h_iso]["W"] += 1
                stats[h_iso]["Pts"] += 3
                stats[a_iso]["L"] += 1
            elif a_score > h_score:
                stats[a_iso]["W"] += 1
                stats[a_iso]["Pts"] += 3
                stats[h_iso]["L"] += 1
            else:
                stats[h_iso]["D"] += 1
                stats[h_iso]["Pts"] += 1
                stats[a_iso]["D"] += 1
                stats[a_iso]["Pts"] += 1
                
        # 4. Sort and build standings per group
        result = {}
        for grp, t_list in group_teams.items():
            grp_standings = []
            for t in t_list:
                iso = t["isoCode"]
                t_stats = stats[iso]
                grp_standings.append({
                    "team": {
                        "id": t["id"],
                        "name": t["name"],
                        "logo": t.get("logo"),
                        "isoCode": iso
                    },
                    "group": f"Group {grp}",
                    "points": t_stats["Pts"],
                    "goalsDiff": t_stats["GD"],
                    "all": {
                        "played": t_stats["P"],
                        "win": t_stats["W"],
                        "draw": t_stats["D"],
                        "lose": t_stats["L"],
                        "goals": {
                            "for": t_stats["GF"],
                            "against": t_stats["GA"]
                        }
                    }
                })
            # Sort by Pts desc, then GD desc, then GF desc
            grp_standings.sort(key=lambda x: (-x["points"], -x["goalsDiff"], -x["all"]["goals"]["for"]))
            # Assign rank
            for rank, entry in enumerate(grp_standings, 1):
                entry["rank"] = rank
            result[grp] = grp_standings
            
            # Persist to Firestore: wc_group_standings/{group}
            db.collection("wc_group_standings").document(grp).set({
                "group": grp,
                "teams": grp_standings
            })
            
        return result

    def check_team_eliminated(self, team_id: int, db=None) -> bool:
        """Check Firestore for team elimination status."""
        db = db or self.db
        if not db:
            return False
        doc = db.collection("wc_teams").document(str(team_id)).get()
        return doc.to_dict().get("eliminated", False) if doc.exists else False

    def detect_group_stage_eliminations(self, db=None) -> Dict[str, List[int]]:
        """
        Run after ALL GW3 fixtures are processedForFantasy.
        """
        db = db or self.db
        if not db:
            raise RuntimeError("Firestore db required")

        all_standings = self.compute_group_standings_from_db(db=db)
        if len(all_standings) < 12:
            raise ValueError(
                f"Only {len(all_standings)} groups found; need all 12 before detecting eliminations"
            )

        fourth_place: List[Dict] = []
        third_place: List[Dict] = []

        for group_letter, standings in all_standings.items():
            if len(standings) < 4:
                continue
            fourth_place.append(standings[3])
            third_place.append(standings[2])

        sorted_thirds = sorted(
            third_place,
            key=lambda t: (
                -t.get("points", 0),
                -(t.get("goalsDiff", 0)),
                -(t.get("all", {}).get("goals", {}).get("for", 0)),
            )
        )

        advancing_thirds = sorted_thirds[:8]
        eliminated_thirds = sorted_thirds[8:]
        advancing_third_ids = {t["team"]["id"] for t in advancing_thirds}

        eliminated_ids = [t["team"]["id"] for t in fourth_place]
        eliminated_ids += [t["team"]["id"] for t in eliminated_thirds]

        if db:
            batch = db.batch()
            for tid in eliminated_ids:
                ref = db.collection("wc_teams").document(str(tid))
                batch.update(ref, {"eliminated": True, "eliminatedAfterGw": 3, "status": "eliminated"})
            batch.commit()

            player_docs = db.collection("wc_players").get()
            player_batch = db.batch()
            for doc in player_docs:
                if doc.to_dict().get("teamId") in set(eliminated_ids):
                    player_batch.update(doc.reference, {"eliminated": True})
            player_batch.commit()

        return {
            "eliminated": eliminated_ids,
            "advancing_thirds": list(advancing_third_ids),
        }

    def mark_knockout_elimination(self, team_id: int, gw: int, db=None):
        """Mark a team eliminated after a knockout match loss."""
        db = db or self.db
        if not db:
            return
        db.collection("wc_teams").document(str(team_id)).update({
            "eliminated": True,
            "eliminatedAfterGw": gw,
            "status": "eliminated"
        })

        batch = db.batch()
        player_docs = (db.collection("wc_players")
                       .where("teamId", "==", team_id).get())
        for doc in player_docs:
            batch.update(doc.reference, {"eliminated": True})

        batch.commit()


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _wc_round_to_gw(round_name: str) -> int:
    """Map api-sports round name to fantasy GW number. Returns 0 for unknown."""
    r = round_name.upper()
    if "GROUP STAGE - 1" in r or "ROUND 1" in r or "MATCHDAY 1" in r:
        return 1
    if "GROUP STAGE - 2" in r or "ROUND 2" in r or "MATCHDAY 2" in r:
        return 2
    if "GROUP STAGE - 3" in r or "ROUND 3" in r or "MATCHDAY 3" in r:
        return 3
    if "ROUND OF 32" in r or "1/16" in r:
        return 4
    if "ROUND OF 16" in r or "1/8" in r:
        return 5
    if "QUARTER" in r or "1/4" in r:
        return 6
    if "SEMI" in r:
        return 7
    if "FINAL" in r or "3RD" in r or "THIRD" in r:
        return 8
    return 0


def _normalize_status(short: str) -> str:
    mapping = {
        "NS": "scheduled", "TBD": "scheduled",
        "1H": "live", "2H": "live", "HT": "live",
        "ET": "live", "BT": "live", "P": "live",
        "FT": "FT", "AET": "FT", "PEN": "FT",
        "PST": "postponed", "CANC": "cancelled",
        "ABD": "cancelled", "AWD": "FT", "WO": "FT",
    }
    return mapping.get(short, "scheduled")


def _reconstruct_stats_from_events(events: List[Dict], fixture_id: int) -> List[Dict]:
    """
    Build per-player stats from events endpoint when /fixtures/players is unavailable.
    Covers: goals, assists, yellow/red cards, own goals, substitutions (minutes).
    Missing: saves, BPS — those default to 0.
    """
    players: Dict[int, Dict] = {}

    def _get_or_create(pid: int, pname: str, team_id: int, team_name: str):
        if pid not in players:
            players[pid] = {
                "player": {"id": pid, "name": pname},
                "team": {"id": team_id, "name": team_name},
                "statistics": [{
                    "games": {"minutes": None, "number": 0},
                    "goals": {"total": 0, "assists": 0, "conceded": 0, "saves": 0},
                    "cards": {"yellow": 0, "red": 0},
                    "penalty": {"missed": 0, "saved": 0},
                    "offsides": 0,
                    "_own_goals": 0,
                    "_bps": 0,
                }]
            }
        return players[pid]

    for event in events:
        etype = event.get("type", "")
        detail = event.get("detail", "")
        player = event.get("player", {})
        assist = event.get("assist", {})
        team = event.get("team", {})
        pid = player.get("id")
        pname = player.get("name", "")
        tid = team.get("id", 0)
        tname = team.get("name", "")
        time_el = event.get("time", {}).get("elapsed", 0)
        extra_time = event.get("time", {}).get("extra", 0) or 0

        if not pid:
            continue

        entry = _get_or_create(pid, pname, tid, tname)
        stats = entry["statistics"][0]

        if etype == "Goal":
            if detail == "Own Goal":
                stats["_own_goals"] += 1
            elif detail == "Missed Penalty":
                stats["penalty"]["missed"] += 1
            else:
                stats["goals"]["total"] += 1

            a_pid = assist.get("id")
            a_name = assist.get("name", "")
            if a_pid:
                a_entry = _get_or_create(a_pid, a_name, tid, tname)
                a_entry["statistics"][0]["goals"]["assists"] += 1

        elif etype == "Card":
            if detail == "Yellow Card":
                stats["cards"]["yellow"] += 1
            elif detail in ("Red Card", "Second Yellow card"):
                stats["cards"]["red"] += 1

        elif etype == "subst":
            minutes_played = time_el + extra_time
            curr = stats["games"]["minutes"]
            if curr is None or minutes_played > curr:
                stats["games"]["minutes"] = minutes_played

    return list(players.values())
