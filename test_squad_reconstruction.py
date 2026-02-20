"""
Tests for Squad Reconstruction Logic

Tests the SquadProcessor class to ensure squads are correctly
reconstructed from baseline + transactions.
"""

import pytest
import duckdb
from pathlib import Path
from fpl_predictor.data.database import init_schema
from fpl_predictor.data.squad_processor import SquadProcessor


@pytest.fixture
def test_db():
    """Create a temporary in-memory database for testing."""
    con = duckdb.connect(':memory:')
    init_schema(con)
    
    # Insert test data
    # Teams
    con.execute("INSERT INTO pl_teams (id, name, short_name) VALUES (1, 'Arsenal', 'ARS')")
    con.execute("INSERT INTO pl_teams (id, name, short_name) VALUES (2, 'Chelsea', 'CHE')")
    
    # Players
    for i in range(1, 31):
        con.execute("""
            INSERT INTO pl_players (id, web_name, team_id, position)
            VALUES (?, ?, ?, ?)
        """, [i, f'Player{i}', 1 if i <= 15 else 2, (i % 4) + 1])
    
    # Entries
    con.execute("INSERT INTO fpl_entries (id, entry_id, entry_name, short_name) VALUES (1, 100, 'Team A', 'TA')")
    con.execute("INSERT INTO fpl_entries (id, entry_id, entry_name, short_name) VALUES (2, 200, 'Team B', 'TB')")
    
    yield con
    con.close()


def test_full_rebuild(test_db):
    """Test full squad reconstruction from baseline + all transactions."""
    processor = SquadProcessor(test_db)
    
    # Baseline squads
    baseline = {
        100: list(range(1, 16)),   # Team A: players 1-15
        200: list(range(16, 31))   # Team B: players 16-30
    }
    
    # Transactions: Team A trades player 1 for player 16
    transactions = [
        {
            'id': 1,
            'entry': 100,
            'element_in': 16,
            'element_out': 1,
            'result': 'a',  # approved
            'added_time': '2026-01-01T10:00:00'
        },
        {
            'id': 2,
            'entry': 200,
            'element_in': 1,
            'element_out': 16,
            'result': 'a',
            'added_time': '2026-01-01T10:00:00'
        }
    ]
    
    # Reconstruct
    stats = processor.reconstruct_squads_full(baseline, transactions, target_gw=21)
    
    # Verify
    assert stats['squads_updated'] == 2
    assert stats['transactions_applied'] == 2
    
    # Check database
    team_a_squad = test_db.execute("""
        SELECT player_id FROM fpl_squads 
        WHERE entry_id = 100 AND gameweek = 21
        ORDER BY player_id
    """).fetchall()
    
    team_a_players = [row[0] for row in team_a_squad]
    assert 1 not in team_a_players  # Player 1 traded out
    assert 16 in team_a_players     # Player 16 traded in
    assert len(team_a_players) == 15


def test_incremental_update(test_db):
    """Test incremental transaction application."""
    processor = SquadProcessor(test_db)
    
    # Set up existing squads
    for player_id in range(1, 16):
        test_db.execute("""
            INSERT INTO fpl_squads (entry_id, player_id, gameweek, squad_position)
            VALUES (100, ?, 21, ?)
        """, [player_id, player_id])
    
    for player_id in range(16, 31):
        test_db.execute("""
            INSERT INTO fpl_squads (entry_id, player_id, gameweek, squad_position)
            VALUES (200, ?, 21, ?)
        """, [player_id, player_id - 15])
    
    # Save bookmark
    processor.save_transaction_bookmark(0)
    
    # New transactions
    new_transactions = [
        {
            'id': 1,
            'entry': 100,
            'element_in': 16,
            'element_out': 1,
            'result': 'a',
            'added_time': '2026-01-02T10:00:00'
        }
    ]
    
    # Apply incrementally
    stats = processor.apply_transactions_incremental(new_transactions, current_gw=21)
    
    # Verify
    assert stats['entries_updated'] == 1
    assert stats['transactions_applied'] == 1
    
    # Check bookmark updated
    bookmark = processor.get_last_transaction_bookmark()
    assert bookmark == 1


def test_squad_validation(test_db):
    """Test 15-player squad validation."""
    processor = SquadProcessor(test_db)
    
    # Valid squad (15 players)
    valid_squad = list(range(1, 16))
    result = processor.validate_squad(valid_squad, entry_id=100)
    assert result['valid'] is True
    assert len(result['errors']) == 0
    
    # Invalid squad (14 players)
    invalid_squad = list(range(1, 15))
    result = processor.validate_squad(invalid_squad, entry_id=100)
    assert result['valid'] is False
    assert any('14 players' in err for err in result['errors'])
    
    # Invalid squad (duplicates)
    duplicate_squad = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 14]
    result = processor.validate_squad(duplicate_squad, entry_id=100)
    assert result['valid'] is False
    assert any('Duplicate' in err for err in result['errors'])


def test_element_status_sync(test_db):
    """Test element_status table stays in sync with squads."""
    processor = SquadProcessor(test_db)
    
    # Create squads
    for player_id in range(1, 16):
        test_db.execute("""
            INSERT INTO fpl_squads (entry_id, player_id, gameweek, squad_position)
            VALUES (100, ?, 21, ?)
        """, [player_id, player_id])
    
    # Sync element_status
    processor.update_element_status(current_gw=21)
    
    # Check owned players
    owned = test_db.execute("""
        SELECT element_id, owner_entry_id 
        FROM element_status 
        WHERE in_squad = TRUE
        ORDER BY element_id
    """).fetchall()
    
    assert len(owned) == 15
    assert all(row[1] == 100 for row in owned)  # All owned by entry 100
    
    # Check free agents
    free = test_db.execute("""
        SELECT COUNT(*) FROM element_status WHERE in_squad = FALSE
    """).fetchone()[0]
    
    assert free == 15  # Players 16-30 are free agents


def test_failed_transactions_ignored(test_db):
    """Test that failed/pending transactions are not applied."""
    processor = SquadProcessor(test_db)
    
    baseline = {
        100: list(range(1, 16))
    }
    
    transactions = [
        {
            'id': 1,
            'entry': 100,
            'element_in': 16,
            'element_out': 1,
            'result': 'p',  # pending - should be ignored
            'added_time': '2026-01-01T10:00:00'
        },
        {
            'id': 2,
            'entry': 100,
            'element_in': 17,
            'element_out': 2,
            'result': 'f',  # failed - should be ignored
            'added_time': '2026-01-01T11:00:00'
        }
    ]
    
    stats = processor.reconstruct_squads_full(baseline, transactions, target_gw=21)
    
    # No transactions should be applied
    assert stats['transactions_applied'] == 0
    
    # Squad should be unchanged
    squad = test_db.execute("""
        SELECT player_id FROM fpl_squads 
        WHERE entry_id = 100 AND gameweek = 21
        ORDER BY player_id
    """).fetchall()
    
    players = [row[0] for row in squad]
    assert players == list(range(1, 16))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
