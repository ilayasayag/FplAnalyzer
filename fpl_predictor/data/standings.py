"""
Premier League standings fetcher

Fetches live standings from Football-Data.org API or falls back to 
FPL API team data for position estimates.
"""

import os
import json
import time
import requests
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from ..config import (
    FOOTBALL_DATA_API_URL,
    FOOTBALL_DATA_COMPETITION_ID,
    API_TIMEOUT,
    STANDINGS_CACHE_DURATION,
    DATA_DIR,
)
from ..models.team import Team, TeamStats


class StandingsFetcher:
    """
    Fetches and caches Premier League standings.
    
    Primary source: Football-Data.org API (free tier)
    Fallback: Manual standings or cached data
    """
    
    CACHE_FILE = "standings_cache.json"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the standings fetcher.
        
        Args:
            api_key: Football-Data.org API key (optional, can use env var)
        """
        self.api_key = api_key or os.environ.get('FOOTBALL_DATA_API_KEY', '')
        self.cache_path = Path(DATA_DIR) / self.CACHE_FILE
        self._cached_standings: Optional[Dict] = None
        self._cache_time: Optional[datetime] = None
    
    def fetch_standings(self, force_refresh: bool = False) -> Dict[int, int]:
        """
        Fetch current Premier League standings.
        
        Args:
            force_refresh: If True, bypass cache and fetch fresh data
            
        Returns:
            Dictionary mapping team_id to league position
        """
        # Try cache first
        if not force_refresh:
            cached = self._load_from_cache()
            if cached:
                return cached
        
        # Try Football-Data.org API
        if self.api_key:
            standings = self._fetch_from_football_data()
            if standings:
                self._save_to_cache(standings)
                return standings
        
        # Try alternative free API
        standings = self._fetch_from_alternative_api()
        if standings:
            self._save_to_cache(standings)
            return standings
        
        # Last resort: return cached data even if stale
        stale_cache = self._load_from_cache(ignore_expiry=True)
        if stale_cache:
            print("Warning: Using stale cached standings")
            return stale_cache
        
        # Absolute fallback: estimated positions
        print("Warning: No standings data available, using estimates")
        return self._get_fallback_standings()
    
    def _fetch_from_football_data(self) -> Optional[Dict[int, int]]:
        """Fetch standings from Football-Data.org API"""
        try:
            url = f"{FOOTBALL_DATA_API_URL}/competitions/{FOOTBALL_DATA_COMPETITION_ID}/standings"
            headers = {'X-Auth-Token': self.api_key}
            
            response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_football_data_response(data)
            elif response.status_code == 429:
                print("Football-Data API rate limit reached")
            else:
                print(f"Football-Data API error: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching from Football-Data: {e}")
        
        return None
    
    def _parse_football_data_response(self, data: Dict) -> Dict[int, int]:
        """Parse Football-Data.org API response"""
        standings = {}
        
        try:
            # Find the total standings (not home/away)
            standings_data = data.get('standings', [])
            total_standings = None
            
            for s in standings_data:
                if s.get('type') == 'TOTAL':
                    total_standings = s
                    break
            
            if not total_standings:
                total_standings = standings_data[0] if standings_data else None
            
            if total_standings:
                table = total_standings.get('table', [])
                
                for entry in table:
                    team_name = entry.get('team', {}).get('name', '')
                    position = entry.get('position', 0)
                    
                    # Map team name to FPL team ID
                    team_id = self._get_fpl_team_id(team_name)
                    if team_id:
                        standings[team_id] = position
                        
        except (KeyError, IndexError) as e:
            print(f"Error parsing Football-Data response: {e}")
        
        return standings
    
    def _fetch_from_alternative_api(self) -> Optional[Dict[int, int]]:
        """Fetch standings from alternative free API"""
        try:
            # API-Football free tier (limited)
            # Or OpenLigaDB for Bundesliga (as alternative example)
            # For now, we'll use a scraping fallback
            
            # Try fetching from FPL's own fixture data to estimate positions
            url = "https://fantasy.premierleague.com/api/bootstrap-static/"
            response = requests.get(url, timeout=API_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                return self._estimate_from_fpl_data(data)
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching from alternative API: {e}")
        
        return None
    
    def _estimate_from_fpl_data(self, fpl_data: Dict) -> Dict[int, int]:
        """
        Estimate standings from FPL bootstrap data.
        
        Uses team strength and other indicators to estimate positions.
        Not perfectly accurate but a reasonable fallback.
        """
        standings = {}
        teams = fpl_data.get('teams', [])
        
        # Sort teams by strength (higher = better)
        # FPL uses strength_overall_home/away values
        team_scores = []
        
        for team in teams:
            team_id = team.get('id', 0)
            # Combine strength indicators
            strength = (
                team.get('strength', 0) +
                team.get('strength_overall_home', 0) +
                team.get('strength_overall_away', 0)
            ) / 3
            
            team_scores.append((team_id, strength))
        
        # Sort by strength descending
        team_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Assign positions
        for position, (team_id, _) in enumerate(team_scores, start=1):
            standings[team_id] = position
        
        return standings
    
    def _get_fpl_team_id(self, team_name: str) -> Optional[int]:
        """Map external team name to FPL team ID"""
        # Team name mappings (Football-Data names -> FPL IDs)
        # These IDs are from FPL 2024/25 season
        name_to_id = {
            'Arsenal FC': 1,
            'Arsenal': 1,
            'Aston Villa FC': 2,
            'Aston Villa': 2,
            'AFC Bournemouth': 3,
            'Bournemouth': 3,
            'Brentford FC': 4,
            'Brentford': 4,
            'Brighton & Hove Albion FC': 5,
            'Brighton': 5,
            'Chelsea FC': 6,
            'Chelsea': 6,
            'Crystal Palace FC': 7,
            'Crystal Palace': 7,
            'Everton FC': 8,
            'Everton': 8,
            'Fulham FC': 9,
            'Fulham': 9,
            'Ipswich Town FC': 10,
            'Ipswich': 10,
            'Ipswich Town': 10,
            'Leicester City FC': 11,
            'Leicester': 11,
            'Leicester City': 11,
            'Liverpool FC': 12,
            'Liverpool': 12,
            'Manchester City FC': 13,
            'Manchester City': 13,
            'Man City': 13,
            'Manchester United FC': 14,
            'Manchester United': 14,
            'Man Utd': 14,
            'Newcastle United FC': 15,
            'Newcastle United': 15,
            'Newcastle': 15,
            'Nottingham Forest FC': 16,
            'Nottingham Forest': 16,
            "Nott'm Forest": 16,
            'Southampton FC': 17,
            'Southampton': 17,
            'Tottenham Hotspur FC': 18,
            'Tottenham Hotspur': 18,
            'Spurs': 18,
            'Tottenham': 18,
            'West Ham United FC': 19,
            'West Ham United': 19,
            'West Ham': 19,
            'Wolverhampton Wanderers FC': 20,
            'Wolverhampton': 20,
            'Wolves': 20,
        }
        
        return name_to_id.get(team_name)
    
    def _get_fallback_standings(self) -> Dict[int, int]:
        """
        Return hardcoded fallback standings.
        
        Based on typical mid-season standings (update as needed).
        """
        # Default estimated positions (rough estimates)
        return {
            12: 1,   # Liverpool
            13: 2,   # Man City
            1: 3,    # Arsenal
            6: 4,    # Chelsea
            16: 5,   # Nottingham Forest
            15: 6,   # Newcastle
            3: 7,    # Bournemouth
            2: 8,    # Aston Villa
            5: 9,    # Brighton
            9: 10,   # Fulham
            4: 11,   # Brentford
            18: 12,  # Spurs
            14: 13,  # Man Utd
            19: 14,  # West Ham
            7: 15,   # Crystal Palace
            8: 16,   # Everton
            20: 17,  # Wolves
            10: 18,  # Ipswich
            11: 19,  # Leicester
            17: 20,  # Southampton
        }
    
    def _load_from_cache(self, ignore_expiry: bool = False) -> Optional[Dict[int, int]]:
        """Load standings from cache file"""
        try:
            if not self.cache_path.exists():
                return None
            
            with open(self.cache_path, 'r') as f:
                cache_data = json.load(f)
            
            cached_time = datetime.fromisoformat(cache_data.get('timestamp', ''))
            
            # Check if cache is expired
            if not ignore_expiry:
                age = datetime.now() - cached_time
                if age.total_seconds() > STANDINGS_CACHE_DURATION:
                    return None
            
            # Convert string keys back to int
            standings = {
                int(k): v for k, v in cache_data.get('standings', {}).items()
            }
            
            return standings
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"Error loading cache: {e}")
            return None
    
    def _save_to_cache(self, standings: Dict[int, int]) -> None:
        """Save standings to cache file"""
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'standings': standings,
            }
            
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            
            with open(self.cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
                
        except IOError as e:
            print(f"Error saving cache: {e}")
    
    def get_team_position(self, team_id: int) -> int:
        """Get the current league position for a team"""
        standings = self.fetch_standings()
        return standings.get(team_id, 10)  # Default to mid-table
    
    def update_teams_with_positions(self, teams: Dict[int, Team]) -> None:
        """
        Update Team objects with their current league positions.
        
        Args:
            teams: Dictionary of team_id -> Team objects
        """
        standings = self.fetch_standings()
        
        for team_id, team in teams.items():
            position = standings.get(team_id, 10)
            team.position = position
    
    def get_detailed_standings(self) -> List[Dict[str, Any]]:
        """
        Get detailed standings with team stats.
        
        Returns list of dictionaries with position, team info, and stats.
        """
        standings = self.fetch_standings()
        
        # Sort by position
        sorted_teams = sorted(standings.items(), key=lambda x: x[1])
        
        result = []
        for team_id, position in sorted_teams:
            result.append({
                'position': position,
                'team_id': team_id,
            })
        
        return result


def set_standings_manually(standings: Dict[str, int]) -> Dict[int, int]:
    """
    Helper to set standings manually from team names.
    
    Args:
        standings: Dict mapping team name/short to position
        
    Returns:
        Dict mapping team_id to position
    """
    fetcher = StandingsFetcher()
    
    result = {}
    for name, position in standings.items():
        team_id = fetcher._get_fpl_team_id(name)
        if team_id:
            result[team_id] = position
        else:
            print(f"Warning: Unknown team '{name}'")
    
    return result

