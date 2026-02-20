"""
Minimal DataLoader stub for backward compatibility.

This is a simplified version that works alongside DuckDB.
The full refactor to remove this entirely is tracked separately.
"""

import json
from typing import Dict, List, Optional, Any
from pathlib import Path


class DataLoader:
    """
    Minimal data loader for backward compatibility with existing API.
    
    This loads data into memory without interfering with DuckDB.
    """
    
    def __init__(self):
        self.raw_data: Dict[str, Any] = {}
        self.players: Dict[int, Any] = {}
        self.teams: Dict[int, Any] = {}
        self.team_id_to_name: Dict[int, str] = {}
        self.team_name_to_id: Dict[str, int] = {}
        self.current_gameweek: int = 21
        self.fetched_at: Optional[str] = None
        self.league_entries: List[Dict] = []
        self.squads: Dict[int, List[int]] = {}
    
    def load_from_file(self, filepath: str) -> bool:
        """Load data from JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return self.load_from_dict(data)
        except Exception as e:
            print(f"[DataLoader] Error loading file: {e}")
            return False
    
    def load_from_dict(self, data: Dict[str, Any]) -> bool:
        """Load data from dictionary."""
        try:
            self.raw_data = data
            
            # Extract basic info
            bootstrap = data.get('bootstrap', {})
            league_data = data.get('league', {})
            
            # Determine current gameweek
            self.current_gameweek = data.get('currentEvent', 21)
            
            # Load teams (minimal)
            for team_data in bootstrap.get('teams', []):
                team_id = team_data.get('id')
                team_name = team_data.get('name', '')
                self.teams[team_id] = team_data
                self.team_id_to_name[team_id] = team_name
                self.team_name_to_id[team_name] = team_id
            
            # Load players (minimal)
            for element in bootstrap.get('elements', []):
                player_id = element.get('id')
                self.players[player_id] = element
            
            # Load league entries
            if isinstance(league_data, dict):
                self.league_entries = league_data.get('league_entries', [])
            
            # Load squads
            squads_data = data.get('squads', {})
            for entry_id_str, squad_info in squads_data.items():
                entry_id = int(entry_id_str)
                picks = squad_info.get('picks', [])
                player_ids = [pick.get('element') for pick in picks if isinstance(pick, dict)]
                self.squads[entry_id] = player_ids
            
            print(f"[DataLoader] Loaded {len(self.players)} players, {len(self.teams)} teams")
            return True
            
        except Exception as e:
            print(f"[DataLoader] Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_statistics(self) -> Dict:
        """Get basic statistics."""
        return {
            'total_players': len(self.players),
            'total_teams': len(self.teams),
            'current_gameweek': self.current_gameweek,
            'entries': len(self.league_entries)
        }
    
    def get_player(self, player_id: int):
        """Get a player by ID."""
        return self.players.get(player_id)
    
    def get_team(self, team_id: int):
        """Get a team by ID."""
        return self.teams.get(team_id)
    
    def get_squad_players(self, entry_id: int):
        """Get squad players for an entry."""
        return []  # Simplified for now
    
    def get_entry_name(self, entry_id: int) -> str:
        """Get entry name."""
        for entry in self.league_entries:
            if entry.get('entry_id') == entry_id:
                return entry.get('entry_name', '')
        return f'Entry {entry_id}'
    
    def get_all_entry_ids(self) -> List[int]:
        """Get all entry IDs."""
        return [e.get('entry_id') for e in self.league_entries if 'entry_id' in e]
    
    def search_players(self, search: str, limit: int = 50):
        """Search players by name."""
        return []
    
    def get_players_by_team(self, team_id: int):
        """Get players by team."""
        return [p for p in self.players.values() if p.get('team') == team_id]
