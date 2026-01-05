"""
Data loader for FPL analyzer JSON exports

Parses the combined JSON output from the bookmarklet/analyzer
and creates Player and Team objects.
"""

import json
import os
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from ..models.player import Player, PlayerGameweek
from ..models.team import Team, TeamStats


class DataLoader:
    """
    Loads and parses FPL data from JSON exports.
    
    Expected JSON structure (from analyzer bookmarklet):
    {
        "league": { ... league details, squads, matches ... },
        "elements": { ... element status ... },
        "bootstrap": { "elements": [...], "teams": [...], "events": [...] },
        "playerDetails": { "player_id": { "history": [...] }, ... },
        "transactions": { ... },
        "fetchedAt": "ISO timestamp"
    }
    """
    
    def __init__(self):
        self.raw_data: Dict[str, Any] = {}
        self.players: Dict[int, Player] = {}
        self.teams: Dict[int, Team] = {}
        self.team_id_to_name: Dict[int, str] = {}
        self.team_name_to_id: Dict[str, int] = {}
        self.current_gameweek: int = 1
        self.fetched_at: Optional[str] = None
        
        # League-specific data
        self.league_entries: List[Dict] = []
        self.squads: Dict[int, List[int]] = {}  # entry_id -> list of player_ids
    
    def load_from_file(self, filepath: str) -> bool:
        """
        Load data from a JSON file.
        
        Args:
            filepath: Path to the JSON file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return self.load_from_dict(data)
        except FileNotFoundError:
            print(f"Error: File not found: {filepath}")
            return False
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {filepath}: {e}")
            return False
    
    def load_from_string(self, json_string: str) -> bool:
        """
        Load data from a JSON string.
        
        Args:
            json_string: JSON string to parse
            
        Returns:
            True if successful, False otherwise
        """
        try:
            data = json.loads(json_string)
            return self.load_from_dict(data)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON: {e}")
            return False
    
    def load_from_dict(self, data: Dict[str, Any]) -> bool:
        """
        Load data from a dictionary.
        
        Args:
            data: Dictionary containing FPL data
            
        Returns:
            True if successful, False otherwise
        """
        self.raw_data = data
        
        # Handle different export formats
        # Format 1: Combined bookmarklet export with nested structure
        # Format 2: Direct localStorage export with league/elements/bootstrap at top level
        
        bootstrap = data.get('bootstrap', {})
        player_details = data.get('playerDetails', {})
        league_data = data.get('league', {})
        
        # Check if this is the localStorage format (has savedAt instead of fetchedAt)
        if 'savedAt' in data:
            self.fetched_at = data.get('savedAt')
        else:
            self.fetched_at = data.get('fetchedAt') or league_data.get('fetchedAt')
        
        # Build team mappings first
        self._build_team_mappings(bootstrap)
        
        # Determine current gameweek
        self._determine_current_gameweek(bootstrap, league_data)
        
        # Load teams
        self._load_teams(bootstrap)
        
        # Load players with their history
        self._load_players(bootstrap, player_details)
        
        # Load league entries and squads
        self._load_league_data(league_data)
        
        print(f"Loaded {len(self.players)} players, {len(self.teams)} teams")
        print(f"Current gameweek: {self.current_gameweek}")
        
        return True
    
    def _build_team_mappings(self, bootstrap: Dict[str, Any]) -> None:
        """Build team ID <-> name mappings from bootstrap data"""
        teams = bootstrap.get('teams', [])
        
        for team in teams:
            team_id = team.get('id', 0)
            name = team.get('name', f'Team {team_id}')
            short_name = team.get('short_name', '')
            
            self.team_id_to_name[team_id] = name
            self.team_name_to_id[name] = team_id
            
            # Also map short names
            if short_name:
                self.team_name_to_id[short_name] = team_id
    
    def _determine_current_gameweek(self, bootstrap: Dict[str, Any], 
                                     league_data: Dict[str, Any]) -> None:
        """Determine the current gameweek from event data"""
        events = bootstrap.get('events', [])
        
        if events and isinstance(events, list):
            # Find current event
            for event in events:
                if event.get('is_current'):
                    self.current_gameweek = event.get('id', 1)
                    return
            
            # Find next unfinished event
            for event in events:
                if not event.get('finished'):
                    self.current_gameweek = event.get('id', 1)
                    return
            
            # Fallback to last event + 1
            finished_events = [e for e in events if e.get('finished')]
            if finished_events:
                last_event = max(finished_events, key=lambda x: x.get('id', 0))
                self.current_gameweek = min(last_event.get('id', 0) + 1, 38)
                return
        
        # Fallback to league data
        if league_data.get('currentEvent'):
            self.current_gameweek = league_data['currentEvent']
        elif league_data.get('league', {}).get('start_event'):
            self.current_gameweek = league_data['league']['start_event']
        else:
            self.current_gameweek = 21  # Reasonable default for mid-season
    
    def _load_teams(self, bootstrap: Dict[str, Any]) -> None:
        """Load teams from bootstrap data"""
        teams_data = bootstrap.get('teams', [])
        
        for team_data in teams_data:
            team = Team.from_fpl_bootstrap(team_data)
            self.teams[team.id] = team
    
    def _load_players(self, bootstrap: Dict[str, Any], 
                      player_details: Dict[str, Any]) -> None:
        """Load players with their gameweek history"""
        elements = bootstrap.get('elements', [])
        
        for element in elements:
            player_id = element.get('id', 0)
            
            # Get player's gameweek history if available
            details = player_details.get(str(player_id), {})
            history = details.get('history', [])
            
            # Create player object
            player = Player.from_fpl_data(
                bootstrap_element=element,
                team_map=self.team_id_to_name,
                history=history
            )
            
            # Set team short name
            team = self.teams.get(player.team_id)
            if team:
                player.team_short = team.short_name
            
            self.players[player_id] = player
    
    def _load_league_data(self, league_data: Dict[str, Any]) -> None:
        """Load league entries and squad data"""
        # League entries
        self.league_entries = league_data.get('league_entries', [])
        
        # Squads
        squads_data = league_data.get('squads', {})
        
        for entry_id_str, squad_info in squads_data.items():
            entry_id = int(entry_id_str)
            picks = squad_info.get('picks', [])
            
            # Extract player IDs from picks
            player_ids = [pick.get('element', 0) for pick in picks]
            self.squads[entry_id] = player_ids
    
    def get_player(self, player_id: int) -> Optional[Player]:
        """Get a player by ID"""
        return self.players.get(player_id)
    
    def get_players_by_team(self, team_id: int) -> List[Player]:
        """Get all players from a specific team"""
        return [p for p in self.players.values() if p.team_id == team_id]
    
    def get_players_by_position(self, position: int) -> List[Player]:
        """Get all players of a specific position"""
        return [p for p in self.players.values() if p.position == position]
    
    def get_team(self, team_id: int) -> Optional[Team]:
        """Get a team by ID"""
        return self.teams.get(team_id)
    
    def get_team_by_name(self, name: str) -> Optional[Team]:
        """Get a team by name (full or short)"""
        team_id = self.team_name_to_id.get(name)
        if team_id:
            return self.teams.get(team_id)
        return None
    
    def get_squad_players(self, entry_id: int) -> List[Player]:
        """Get all players in a squad"""
        player_ids = self.squads.get(entry_id, [])
        return [self.players[pid] for pid in player_ids if pid in self.players]
    
    def get_entry_name(self, entry_id: int) -> str:
        """Get the name of a league entry"""
        for entry in self.league_entries:
            if entry.get('entry_id') == entry_id:
                return entry.get('entry_name', f'Entry {entry_id}')
        return f'Entry {entry_id}'
    
    def get_all_entry_ids(self) -> List[int]:
        """Get all entry IDs in the league"""
        return [entry.get('entry_id') for entry in self.league_entries]
    
    def search_players(self, query: str, limit: int = 10) -> List[Player]:
        """
        Search for players by name.
        
        Args:
            query: Search string (case-insensitive)
            limit: Maximum results to return
            
        Returns:
            List of matching players
        """
        query_lower = query.lower()
        matches = []
        
        for player in self.players.values():
            if (query_lower in player.web_name.lower() or 
                query_lower in player.full_name.lower()):
                matches.append(player)
                if len(matches) >= limit:
                    break
        
        return matches
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get summary statistics about loaded data"""
        players_with_history = sum(
            1 for p in self.players.values() if len(p.gameweeks) > 0
        )
        
        return {
            'total_players': len(self.players),
            'players_with_history': players_with_history,
            'total_teams': len(self.teams),
            'league_entries': len(self.league_entries),
            'squads_loaded': len(self.squads),
            'current_gameweek': self.current_gameweek,
            'fetched_at': self.fetched_at,
        }

