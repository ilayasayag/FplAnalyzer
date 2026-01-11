"""
Data Importer for FPL Database

Converts bookmarklet JSON data into DuckDB database records.
Handles upserts, diffing, and data transformation.
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

import duckdb

from .database import get_connection, init_schema


@dataclass
class ImportResult:
    """Result of an import operation."""
    success: bool
    teams_imported: int = 0
    players_imported: int = 0
    gameweeks_imported: int = 0
    squads_imported: int = 0
    entries_imported: int = 0
    matches_imported: int = 0
    transactions_imported: int = 0
    fixtures_imported: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'teams_imported': self.teams_imported,
            'players_imported': self.players_imported,
            'gameweeks_imported': self.gameweeks_imported,
            'squads_imported': self.squads_imported,
            'entries_imported': self.entries_imported,
            'matches_imported': self.matches_imported,
            'transactions_imported': self.transactions_imported,
            'fixtures_imported': self.fixtures_imported,
            'errors': self.errors
        }


class DataImporter:
    """
    Imports FPL data from JSON into DuckDB.
    
    Handles the complete bookmarklet JSON format with:
    - league: League info, entries, matches, standings
    - bootstrap: Teams, players, fixtures, events
    - playerDetails: Per-player gameweek history
    - squads: Current squad ownership
    - transactions: Waiver/trade history
    - elements: Element status (availability)
    """
    
    def __init__(self, con: Optional[duckdb.DuckDBPyConnection] = None):
        # Always use the global connection to avoid lock conflicts
        self.con = get_connection()
        init_schema(self.con)
    
    def import_from_json(self, data: Dict[str, Any]) -> ImportResult:
        """
        Import complete bookmarklet JSON into database.
        
        Args:
            data: Complete JSON object from bookmarklet
            
        Returns:
            ImportResult with counts and any errors
        """
        result = ImportResult(success=True)
        
        try:
            # Extract main sections
            bootstrap = data.get('bootstrap', {})
            league_data = data.get('league', {})
            player_details = data.get('playerDetails', {})
            squads = data.get('squads', {})
            transactions = data.get('transactions', {})
            elements = data.get('elements', {})
            current_gw = data.get('currentEvent', 1)
            
            # Import in dependency order
            
            # 1. Teams (from bootstrap)
            teams = bootstrap.get('teams', [])
            if teams:
                result.teams_imported = self._import_teams(teams)
            
            # 2. Players (from bootstrap)
            players = bootstrap.get('elements', [])
            if players:
                result.players_imported = self._import_players(players)
            
            # 3. Player gameweek history
            if player_details:
                result.gameweeks_imported = self._import_player_history(player_details)
            
            # 4. Fixtures (from bootstrap)
            fixtures = bootstrap.get('fixtures', [])
            if fixtures:
                result.fixtures_imported = self._import_fixtures(fixtures)
            
            # 5. League info - handle nested structure
            # league_data can be: { league: {...}, league_entries: [...], ... }
            if isinstance(league_data, dict):
                league = league_data.get('league', league_data)
                if isinstance(league, dict) and 'id' in league:
                    self._import_league(league)
            
            # 6. League entries (may be at league_data.league_entries or league_data.league.league_entries)
            entries = []
            if isinstance(league_data, dict):
                entries = league_data.get('league_entries', [])
                print(f"[Importer] Entries at league_data.league_entries: {len(entries)}")
                if not entries:
                    league = league_data.get('league', {})
                    if isinstance(league, dict):
                        entries = league.get('league_entries', [])
                        print(f"[Importer] Entries at league_data.league.league_entries: {len(entries)}")
            if entries:
                print(f"[Importer] Importing {len(entries)} entries")
                result.entries_imported = self._import_entries(entries)
            else:
                print(f"[Importer] No entries found. league_data keys: {list(league_data.keys()) if isinstance(league_data, dict) else 'not a dict'}")
            
            # 7. Squads
            if squads and isinstance(squads, dict):
                result.squads_imported = self._import_squads(squads, current_gw)
            
            # 8. Matches
            matches = league_data.get('matches', []) if isinstance(league_data, dict) else []
            if matches:
                result.matches_imported = self._import_matches(matches)
            
            # 9. Transactions
            if isinstance(transactions, dict):
                trans_list = transactions.get('transactions', [])
            elif isinstance(transactions, list):
                trans_list = transactions
            else:
                trans_list = []
            if trans_list:
                result.transactions_imported = self._import_transactions(trans_list)
            
            # 10. Element status
            if isinstance(elements, dict):
                element_status = elements.get('element_status', [])
            elif isinstance(elements, list):
                element_status = elements
            else:
                element_status = []
            if element_status:
                self._import_element_status(element_status)
            
            # 11. Update team batches based on standings
            self._update_team_batches()
            
            # 12. Import FDR data
            self._import_fdr(bootstrap, league_data)
            
            print(f"[Importer] Import complete: {result.to_dict()}")
            
        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            import traceback
            traceback.print_exc()
            print(f"[Importer] Error during import: {e}")
        
        return result
    
    def _import_teams(self, teams: List[Dict]) -> int:
        """Import teams from bootstrap."""
        if not teams:
            return 0
        
        for team in teams:
            self.con.execute("""
                INSERT OR REPLACE INTO pl_teams (
                    id, name, short_name, code,
                    strength_overall_home, strength_overall_away,
                    strength_attack_home, strength_attack_away,
                    strength_defence_home, strength_defence_away,
                    position, played, won, drawn, lost,
                    goals_for, goals_against, points,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, [
                team.get('id'),
                team.get('name'),
                team.get('short_name'),
                team.get('code'),
                team.get('strength_overall_home'),
                team.get('strength_overall_away'),
                team.get('strength_attack_home'),
                team.get('strength_attack_away'),
                team.get('strength_defence_home'),
                team.get('strength_defence_away'),
                team.get('position', 0),
                team.get('played', 0),
                team.get('win', 0),
                team.get('draw', 0),
                team.get('loss', 0),
                team.get('goals_for', 0) or team.get('team_goals_for', 0),
                team.get('goals_against', 0) or team.get('team_goals_against', 0),
                team.get('points', 0)
            ])
        
        return len(teams)
    
    def _import_players(self, players: List[Dict]) -> int:
        """Import players from bootstrap."""
        if not players:
            return 0
        
        for player in players:
            self.con.execute("""
                INSERT OR REPLACE INTO pl_players (
                    id, web_name, first_name, second_name, team_id,
                    position, status, news, news_added, chance_of_playing,
                    total_points, goals_scored, assists, clean_sheets,
                    saves, bonus, minutes, yellow_cards, red_cards,
                    form, points_per_game, ict_index, influence,
                    creativity, threat, expected_goals, expected_assists,
                    expected_goal_involvements, draft_rank, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, [
                player.get('id'),
                player.get('web_name'),
                player.get('first_name'),
                player.get('second_name'),
                player.get('team'),
                player.get('element_type'),
                player.get('status', 'a'),
                player.get('news'),
                player.get('news_added'),
                player.get('chance_of_playing_next_round'),
                player.get('total_points', 0),
                player.get('goals_scored', 0),
                player.get('assists', 0),
                player.get('clean_sheets', 0),
                player.get('saves', 0),
                player.get('bonus', 0),
                player.get('minutes', 0),
                player.get('yellow_cards', 0),
                player.get('red_cards', 0),
                self._safe_float(player.get('form')),
                self._safe_float(player.get('points_per_game')),
                self._safe_float(player.get('ict_index')),
                self._safe_float(player.get('influence')),
                self._safe_float(player.get('creativity')),
                self._safe_float(player.get('threat')),
                self._safe_float(player.get('expected_goals')),
                self._safe_float(player.get('expected_assists')),
                self._safe_float(player.get('expected_goal_involvements')),
                player.get('draft_rank')
            ])
        
        return len(players)
    
    def _import_player_history(self, player_details: Dict) -> int:
        """Import player gameweek history."""
        count = 0
        
        for player_id_str, details in player_details.items():
            try:
                player_id = int(player_id_str)
            except ValueError:
                continue
            
            if not isinstance(details, dict):
                continue
                
            history = details.get('history', [])
            if not isinstance(history, list):
                continue
            
            for game in history:
                if not isinstance(game, dict):
                    continue
                    
                try:
                    # Parse opponent - field is 'opponent_team' in FPL API
                    opponent_id = game.get('opponent_team')
                    was_home = game.get('was_home')
                    
                    # Try to infer from detail string like "MCI(H) 2-1" or "MUN (A) 0-1"
                    detail = game.get('detail', '')
                    if detail and was_home is None:
                        was_home = '(H)' in detail
                    
                    # Gameweek is 'event' in FPL API (or 'round')
                    gameweek = game.get('event') or game.get('round')
                    if not gameweek:
                        continue
                    
                    # Check if started (starts=1 or minutes >= 60)
                    started = game.get('starts', 0) == 1 or game.get('minutes', 0) >= 60
                    
                    self.con.execute("""
                        INSERT OR REPLACE INTO player_gameweeks (
                            player_id, gameweek, opponent_id, was_home,
                            minutes, started, total_points, goals_scored,
                            assists, clean_sheets, goals_conceded, saves,
                            bonus, penalties_saved, penalties_missed,
                            yellow_cards, red_cards, own_goals,
                            expected_goals, expected_assists,
                            expected_goal_involvements, expected_goals_conceded,
                            bps, detail
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        player_id,
                        gameweek,
                        opponent_id,
                        was_home,
                        game.get('minutes', 0),
                        started,
                        game.get('total_points', 0),
                        game.get('goals_scored', 0),
                        game.get('assists', 0),
                        game.get('clean_sheets', 0),
                        game.get('goals_conceded', 0),
                        game.get('saves', 0),
                        game.get('bonus', 0),
                        game.get('penalties_saved', 0),
                        game.get('penalties_missed', 0),
                        game.get('yellow_cards', 0),
                        game.get('red_cards', 0),
                        game.get('own_goals', 0),
                        self._safe_float(game.get('expected_goals')),
                        self._safe_float(game.get('expected_assists')),
                        self._safe_float(game.get('expected_goal_involvements')),
                        self._safe_float(game.get('expected_goals_conceded')),
                        game.get('bps', 0),
                        detail
                    ])
                    count += 1
                except Exception as e:
                    print(f"[Importer] Error importing game for player {player_id}: {e}")
        
        return count
    
    def _import_fixtures(self, fixtures) -> int:
        """Import PL fixtures."""
        if not fixtures:
            return 0
        
        count = 0
        
        # Handle both list and dict formats
        # Dict format: { "21": [...], "22": [...] }
        # List format: [fixture1, fixture2, ...]
        
        if isinstance(fixtures, dict):
            # Flatten dict of lists
            all_fixtures = []
            for gw_key, gw_fixtures in fixtures.items():
                if isinstance(gw_fixtures, list):
                    all_fixtures.extend(gw_fixtures)
            fixtures = all_fixtures
        
        if not isinstance(fixtures, list):
            return 0
        
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
                
            try:
                self.con.execute("""
                    INSERT OR REPLACE INTO pl_fixtures (
                        id, gameweek, home_team_id, away_team_id,
                        home_score, away_score, finished,
                        kickoff_time, home_fdr, away_fdr, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, [
                    fixture.get('id'),
                    fixture.get('event'),
                    fixture.get('team_h'),
                    fixture.get('team_a'),
                    fixture.get('team_h_score'),
                    fixture.get('team_a_score'),
                    fixture.get('finished', False),
                    fixture.get('kickoff_time'),
                    fixture.get('team_h_difficulty'),
                    fixture.get('team_a_difficulty')
                ])
                count += 1
            except Exception as e:
                print(f"[Importer] Error importing fixture: {e}")
        
        return count
    
    def _import_league(self, league: Dict):
        """Import league info."""
        self.con.execute("""
            INSERT OR REPLACE INTO fpl_league (
                id, name, admin_entry, scoring,
                start_event, stop_event, draft_status,
                transaction_mode, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, [
            league.get('id'),
            league.get('name'),
            league.get('admin_entry'),
            league.get('scoring'),
            league.get('start_event'),
            league.get('stop_event'),
            league.get('draft_status'),
            league.get('transaction_mode')
        ])
    
    def _import_entries(self, entries: List[Dict]) -> int:
        """Import league entries."""
        if not entries:
            return 0
        
        count = 0
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                print(f"[Importer] Entry {i} is not a dict: {type(entry)}")
                continue
            
            try:
                # Use INSERT ... ON CONFLICT with explicit conflict target
                self.con.execute("""
                    INSERT INTO fpl_entries (
                        id, entry_id, entry_name, player_first_name,
                        player_last_name, short_name, waiver_pick, joined_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        entry_id = EXCLUDED.entry_id,
                        entry_name = EXCLUDED.entry_name,
                        player_first_name = EXCLUDED.player_first_name,
                        player_last_name = EXCLUDED.player_last_name,
                        short_name = EXCLUDED.short_name,
                        waiver_pick = EXCLUDED.waiver_pick,
                        joined_time = EXCLUDED.joined_time
                """, [
                    entry.get('id'),
                    entry.get('entry_id'),
                    entry.get('entry_name'),
                    entry.get('player_first_name'),
                    entry.get('player_last_name'),
                    entry.get('short_name'),
                    entry.get('waiver_pick'),
                    entry.get('joined_time')
                ])
                count += 1
            except Exception as e:
                print(f"[Importer] Error importing entry {i}: {e}")
        
        return count
    
    def _import_squads(self, squads: Dict, current_gw: int) -> int:
        """Import squad ownership."""
        count = 0
        
        for entry_id_str, squad_data in squads.items():
            try:
                entry_id = int(entry_id_str)
            except (ValueError, TypeError):
                print(f"[Importer] Invalid entry_id: {entry_id_str}")
                continue
            
            if not isinstance(squad_data, dict):
                print(f"[Importer] Squad data for {entry_id_str} is not a dict: {type(squad_data)}")
                continue
            
            picks = squad_data.get('picks', [])
            if not isinstance(picks, list):
                continue
            
            for pick in picks:
                if not isinstance(pick, dict):
                    continue
                    
                try:
                    self.con.execute("""
                        INSERT OR REPLACE INTO fpl_squads (
                            entry_id, player_id, gameweek,
                            squad_position, is_captain, is_vice_captain
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, [
                        entry_id,
                        pick.get('element'),
                        current_gw,
                        pick.get('position'),
                        pick.get('is_captain', False),
                        pick.get('is_vice_captain', False)
                    ])
                    count += 1
                except Exception as e:
                    print(f"[Importer] Error importing pick for {entry_id}: {e}")
        
        return count
    
    def _import_matches(self, matches: List[Dict]) -> int:
        """Import H2H matches."""
        if not matches:
            return 0
        
        count = 0
        for i, match in enumerate(matches):
            if not isinstance(match, dict):
                continue
            
            try:
                # Generate ID from event + entries if not present
                match_id = match.get('id')
                if not match_id:
                    event = match.get('event', 0)
                    entry1 = match.get('league_entry_1', 0)
                    entry2 = match.get('league_entry_2', 0)
                    match_id = event * 1000000 + entry1 * 1000 + entry2 % 1000
                
                self.con.execute("""
                    INSERT OR REPLACE INTO fpl_matches (
                        id, gameweek, league_entry_1, league_entry_2,
                        entry_1_points, entry_2_points,
                        entry_1_win, entry_2_win, finished
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    match_id,
                    match.get('event'),
                    match.get('league_entry_1'),
                    match.get('league_entry_2'),
                    match.get('league_entry_1_points'),
                    match.get('league_entry_2_points'),
                    match.get('league_entry_1_win'),
                    match.get('league_entry_2_win'),
                    match.get('finished', False)
                ])
                count += 1
            except Exception as e:
                print(f"[Importer] Error importing match {i}: {e}")
        
        return count
    
    def _import_transactions(self, transactions: List[Dict]) -> int:
        """Import transactions."""
        if not transactions:
            return 0
        
        for trans in transactions:
            self.con.execute("""
                INSERT OR REPLACE INTO fpl_transactions (
                    id, entry_id, player_in, player_out,
                    transaction_type, gameweek, priority,
                    result, added_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                trans.get('id'),
                trans.get('entry'),
                trans.get('element_in'),
                trans.get('element_out'),
                trans.get('kind'),
                trans.get('event'),
                trans.get('priority'),
                trans.get('result'),
                trans.get('added')
            ])
        
        return len(transactions)
    
    def _import_element_status(self, element_status: List[Dict]):
        """Import element availability status."""
        count = 0
        for es in element_status:
            if not isinstance(es, dict):
                continue
                
            try:
                self.con.execute("""
                    INSERT OR REPLACE INTO element_status (
                        element_id, owner_entry_id, status,
                        in_squad, updated_at
                    ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, [
                    es.get('element'),
                    es.get('owner'),
                    es.get('status'),
                    es.get('in_accepted_trade', False)
                ])
                count += 1
            except Exception as e:
                print(f"[Importer] Error importing element status: {e}")
        
        return count
    
    def _update_team_batches(self):
        """Update team batch_id based on current position."""
        # Batch 1: 1-4, Batch 2: 5-8, Batch 3: 9-12, Batch 4: 13-17, Batch 5: 18-20
        self.con.execute("""
            UPDATE pl_teams
            SET batch_id = CASE
                WHEN position <= 4 THEN 1
                WHEN position <= 8 THEN 2
                WHEN position <= 12 THEN 3
                WHEN position <= 17 THEN 4
                ELSE 5
            END
            WHERE position > 0
        """)
    
    def _import_fdr(self, bootstrap: Dict, league_data: Dict):
        """Import FDR data from fixtures."""
        fixtures = bootstrap.get('fixtures', {})
        
        # Handle both dict and list formats
        if isinstance(fixtures, dict):
            all_fixtures = []
            for gw_key, gw_fixtures in fixtures.items():
                if isinstance(gw_fixtures, list):
                    all_fixtures.extend(gw_fixtures)
            fixtures = all_fixtures
        
        if not isinstance(fixtures, list):
            return
        
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
                
            gw = fixture.get('event')
            if not gw:
                continue
            
            home_team = fixture.get('team_h')
            away_team = fixture.get('team_a')
            home_fdr = fixture.get('team_h_difficulty')
            away_fdr = fixture.get('team_a_difficulty')
            
            if home_team and away_team:
                try:
                    # Home team's fixture
                    self.con.execute("""
                        INSERT OR REPLACE INTO fixture_difficulty (
                            team_id, gameweek, opponent_id, is_home,
                            official_fdr, weighted_fdr
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, [home_team, gw, away_team, True, home_fdr, home_fdr])
                    
                    # Away team's fixture
                    self.con.execute("""
                        INSERT OR REPLACE INTO fixture_difficulty (
                            team_id, gameweek, opponent_id, is_home,
                            official_fdr, weighted_fdr
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, [away_team, gw, home_team, False, away_fdr, away_fdr])
                except Exception as e:
                    print(f"[Importer] Error importing FDR: {e}")
    
    @staticmethod
    def _safe_float(value) -> Optional[float]:
        """Safely convert a value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


def import_from_file(filepath: str) -> ImportResult:
    """
    Import data from a JSON file.
    
    Args:
        filepath: Path to the JSON file
        
    Returns:
        ImportResult with import statistics
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        importer = DataImporter()
        return importer.import_from_json(data)
    except FileNotFoundError:
        return ImportResult(success=False, errors=[f"File not found: {filepath}"])
    except json.JSONDecodeError as e:
        return ImportResult(success=False, errors=[f"Invalid JSON: {e}"])
    except Exception as e:
        return ImportResult(success=False, errors=[str(e)])


def import_from_dict(data: Dict[str, Any]) -> ImportResult:
    """
    Import data from a dictionary.
    
    Args:
        data: Dictionary containing FPL data
        
    Returns:
        ImportResult with import statistics
    """
    importer = DataImporter()
    return importer.import_from_json(data)
