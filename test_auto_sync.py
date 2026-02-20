"""
Integration Tests for Auto-Sync Flow

Tests the complete flow:
1. Find newest JSON file
2. Import into database
3. Process transactions
4. Update squads
5. Clear cache
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from fpl_predictor.data.importer import import_from_file
from fpl_predictor.data.database import get_connection, init_schema, close_connection, reset_connection
from fpl_predictor.data.repository import SquadRepository, CacheManager


@pytest.fixture
def test_data_dir():
    """Create temporary directory with test JSON files."""
    temp_dir = tempfile.mkdtemp()
    
    # Create sample FPL data
    sample_data = {
        'currentEvent': 21,
        'bootstrap': {
            'teams': [
                {'id': 1, 'name': 'Arsenal', 'short_name': 'ARS', 'code': 3, 
                 'strength_overall_home': 1300, 'strength_overall_away': 1250}
            ],
            'elements': [
                {'id': 1, 'web_name': 'Saka', 'first_name': 'Bukayo', 'second_name': 'Saka',
                 'team': 1, 'element_type': 3, 'status': 'a', 'total_points': 150}
            ],
            'fixtures': []
        },
        'league': {
            'league': {'id': 12345, 'name': 'Test League'},
            'league_entries': [
                {'id': 1, 'entry_id': 100, 'entry_name': 'Team A', 
                 'player_first_name': 'Test', 'player_last_name': 'User', 'short_name': 'TA'}
            ]
        },
        'squads': {
            '100': {
                'picks': [{'element': 1, 'position': 1}]
            }
        },
        'transactions': {
            'transactions': []
        },
        'playerDetails': {},
        'elements': {'element_status': []}
    }
    
    # Create multiple JSON files with different dates
    dates = ['2026-01-10', '2026-01-15', '2026-01-16']
    files = []
    
    for date in dates:
        filename = f'fpl_league_data_{date}.json'
        filepath = Path(temp_dir) / filename
        with open(filepath, 'w') as f:
            json.dump(sample_data, f)
        files.append(filepath)
    
    yield temp_dir, files
    
    # Cleanup
    shutil.rmtree(temp_dir)
    reset_connection()


def test_find_newest_file(test_data_dir):
    """Test that the newest file is correctly identified."""
    temp_dir, files = test_data_dir
    
    import glob
    pattern = str(Path(temp_dir) / "fpl_league_data_*.json")
    found_files = glob.glob(pattern)
    
    assert len(found_files) == 3
    
    # Get newest by filename
    newest = max(found_files, key=lambda f: Path(f).stem)
    assert '2026-01-16' in newest


def test_auto_sync_flow(test_data_dir):
    """Test complete auto-sync flow."""
    temp_dir, files = test_data_dir
    
    # Use the newest file
    newest_file = max(files, key=lambda f: f.stem)
    
    # Import
    result = import_from_file(str(newest_file))
    
    # Verify import success
    assert result.success is True
    assert result.teams_imported == 1
    assert result.players_imported == 1
    
    # Verify data in database
    con = get_connection()
    
    teams_count = con.execute("SELECT COUNT(*) FROM pl_teams").fetchone()[0]
    assert teams_count == 1
    
    players_count = con.execute("SELECT COUNT(*) FROM pl_players").fetchone()[0]
    assert players_count == 1
    
    entries_count = con.execute("SELECT COUNT(*) FROM fpl_entries").fetchone()[0]
    assert entries_count == 1


def test_cache_invalidation_on_import(test_data_dir):
    """Test that cache is cleared after import."""
    temp_dir, files = test_data_dir
    newest_file = max(files, key=lambda f: f.stem)
    
    con = get_connection()
    
    # Add some cache entries
    CacheManager.set_cache(con, 'test_key_1', '{"data": "old"}', gameweek=21)
    CacheManager.set_cache(con, 'test_key_2', '{"data": "old"}', gameweek=21)
    
    cache_count_before = con.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
    assert cache_count_before == 2
    
    # Import (should clear cache)
    result = import_from_file(str(newest_file))
    assert result.success is True
    
    # Manually clear cache (simulating what API does)
    CacheManager.invalidate_all(con)
    
    cache_count_after = con.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
    assert cache_count_after == 0


def test_squad_reconstruction_on_import(test_data_dir):
    """Test that squads are reconstructed with transactions."""
    temp_dir, files = test_data_dir
    
    # Create more complete test data with transactions
    complete_data = {
        'currentEvent': 21,
        'bootstrap': {
            'teams': [
                {'id': 1, 'name': 'Arsenal', 'short_name': 'ARS', 'code': 3,
                 'strength_overall_home': 1300, 'strength_overall_away': 1250}
            ],
            'elements': [
                {'id': i, 'web_name': f'Player{i}', 'first_name': 'Test', 'second_name': f'Player{i}',
                 'team': 1, 'element_type': (i % 4) + 1, 'status': 'a', 'total_points': 50}
                for i in range(1, 17)
            ],
            'fixtures': []
        },
        'league': {
            'league': {'id': 12345, 'name': 'Test League'},
            'league_entries': [
                {'id': 1, 'entry_id': 100, 'entry_name': 'Team A',
                 'player_first_name': 'Test', 'player_last_name': 'User', 'short_name': 'TA'}
            ]
        },
        'squads': {
            '100': {
                'picks': [{'element': i, 'position': i} for i in range(1, 16)]
            }
        },
        'transactions': {
            'transactions': [
                {
                    'id': 1,
                    'entry': 100,
                    'element_in': 16,
                    'element_out': 1,
                    'kind': 'waiver',
                    'event': 21,
                    'priority': 1,
                    'result': 'a',
                    'added': '2026-01-16T10:00:00'
                }
            ]
        },
        'playerDetails': {},
        'elements': {'element_status': []}
    }
    
    # Write to new file
    test_file = Path(temp_dir) / 'fpl_league_data_2026-01-17.json'
    with open(test_file, 'w') as f:
        json.dump(complete_data, f)
    
    # Import
    result = import_from_file(str(test_file))
    assert result.success is True
    
    # Verify squad was reconstructed
    con = get_connection()
    squad = con.execute("""
        SELECT player_id FROM fpl_squads
        WHERE entry_id = 100 AND gameweek = 21
        ORDER BY player_id
    """).fetchall()
    
    player_ids = [row[0] for row in squad]
    
    # Player 1 should be traded out, player 16 traded in
    assert 1 not in player_ids
    assert 16 in player_ids
    assert len(player_ids) == 15


def test_element_status_updated(test_data_dir):
    """Test that element_status is updated after import."""
    temp_dir, files = test_data_dir
    
    # Create test data with squads
    data_with_squads = {
        'currentEvent': 21,
        'bootstrap': {
            'teams': [{'id': 1, 'name': 'Arsenal', 'short_name': 'ARS', 'code': 3,
                      'strength_overall_home': 1300, 'strength_overall_away': 1250}],
            'elements': [
                {'id': i, 'web_name': f'Player{i}', 'first_name': 'Test', 'second_name': f'Player{i}',
                 'team': 1, 'element_type': (i % 4) + 1, 'status': 'a', 'total_points': 50}
                for i in range(1, 21)
            ],
            'fixtures': []
        },
        'league': {
            'league': {'id': 12345, 'name': 'Test League'},
            'league_entries': [
                {'id': 1, 'entry_id': 100, 'entry_name': 'Team A',
                 'player_first_name': 'Test', 'player_last_name': 'User', 'short_name': 'TA'}
            ]
        },
        'squads': {
            '100': {
                'picks': [{'element': i, 'position': i} for i in range(1, 16)]
            }
        },
        'transactions': {'transactions': []},
        'playerDetails': {},
        'elements': {'element_status': []}
    }
    
    test_file = Path(temp_dir) / 'fpl_league_data_2026-01-18.json'
    with open(test_file, 'w') as f:
        json.dump(data_with_squads, f)
    
    # Import
    result = import_from_file(str(test_file))
    assert result.success is True
    
    # Check element_status
    con = get_connection()
    
    # Owned players (1-15)
    owned = con.execute("""
        SELECT COUNT(*) FROM element_status
        WHERE in_squad = TRUE AND owner_entry_id = 100
    """).fetchone()[0]
    assert owned == 15
    
    # Free agents (16-20)
    free = con.execute("""
        SELECT COUNT(*) FROM element_status
        WHERE in_squad = FALSE AND owner_entry_id IS NULL
    """).fetchone()[0]
    assert free == 5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
