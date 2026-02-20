"""
Squad Processor - Reconstructs Current Squads from Transactions

This module handles squad reconstruction logic:
- Full rebuild: baseline squads + all transactions
- Incremental: apply only new transactions since bookmark
- Validation: ensure exactly 15 players per squad
- Element status sync: update ownership tables
"""

from typing import Dict, List, Optional, Set
from datetime import datetime
import duckdb


class SquadProcessor:
    """
    Processes transactions to maintain accurate squad state.
    
    Handles both full rebuilds (from scratch) and incremental updates
    (applying only new transactions since last bookmark).
    """
    
    def __init__(self, con: duckdb.DuckDBPyConnection):
        """
        Initialize processor with database connection.
        
        Args:
            con: DuckDB connection
        """
        self.con = con
    
    def get_last_transaction_bookmark(self) -> Optional[int]:
        """
        Get ID of last processed transaction from bookmarks.
        
        Returns:
            Transaction ID or None if no bookmark exists
        """
        try:
            result = self.con.execute("""
                SELECT value FROM user_preferences 
                WHERE key = 'last_transaction_bookmark'
            """).fetchone()
            
            if result and result[0]:
                return int(result[0])
        except Exception as e:
            print(f"[SquadProcessor] No bookmark found: {e}")
        
        return None
    
    def save_transaction_bookmark(self, transaction_id: int):
        """
        Save bookmark for last processed transaction.
        
        Args:
            transaction_id: ID of last transaction processed
        """
        self.con.execute("""
            INSERT OR REPLACE INTO user_preferences (key, value, updated_at)
            VALUES ('last_transaction_bookmark', ?, CURRENT_TIMESTAMP)
        """, [str(transaction_id)])
        
        print(f"[SquadProcessor] Saved transaction bookmark: {transaction_id}")
    
    def reconstruct_squads_full(
        self, 
        baseline_squads: Dict[int, List[int]], 
        transactions: List[Dict], 
        target_gw: int
    ) -> Dict[str, any]:
        """
        Full rebuild: Start from baseline squads and apply ALL transactions.
        
        This method reconstructs the current state of all squads by:
        1. Starting with baseline squads (from JSON import)
        2. Applying each transaction in chronological order
        3. Validating final squad state
        4. Saving to fpl_squads table
        
        Args:
            baseline_squads: Dict[entry_id, List[player_ids]] - initial squads
            transactions: All transactions sorted by added_time
            target_gw: Current gameweek to save squads for
            
        Returns:
            Dict with statistics: squads_updated, transactions_applied, errors
        """
        print(f"[SquadProcessor] Full rebuild for GW{target_gw}")
        print(f"  Baseline squads: {len(baseline_squads)} entries")
        print(f"  Transactions to apply: {len(transactions)}")
        
        # Clone baseline to avoid modifying original
        current_squads = {
            entry_id: list(players) 
            for entry_id, players in baseline_squads.items()
        }
        
        applied = 0
        failed = 0
        errors = []
        
        # Sort transactions by time to apply in order
        sorted_transactions = sorted(
            transactions, 
            key=lambda t: t.get('added_time', ''), 
            reverse=False
        )
        
        # Apply each transaction
        for trans in sorted_transactions:
            result = trans.get('result')
            if result != 'a':  # Only apply successful transactions (result='a' = approved)
                continue
            
            entry_id = trans.get('entry')
            player_in = trans.get('element_in')
            player_out = trans.get('element_out')
            trans_id = trans.get('id')
            
            if entry_id not in current_squads:
                errors.append(f"Transaction {trans_id}: Unknown entry {entry_id}")
                failed += 1
                continue
            
            squad = current_squads[entry_id]
            
            try:
                # Remove player_out if specified
                if player_out:
                    if player_out in squad:
                        squad.remove(player_out)
                    else:
                        print(f"[SquadProcessor] Warning: Player {player_out} not in squad for entry {entry_id}")
                
                # Add player_in if specified
                if player_in:
                    if player_in not in squad:
                        squad.append(player_in)
                    else:
                        print(f"[SquadProcessor] Warning: Player {player_in} already in squad for entry {entry_id}")
                
                applied += 1
                
            except Exception as e:
                errors.append(f"Transaction {trans_id}: {str(e)}")
                failed += 1
        
        # Validate all squads
        validation_errors = []
        for entry_id, squad in current_squads.items():
            validation = self.validate_squad(squad, entry_id)
            if not validation['valid']:
                validation_errors.extend(validation['errors'])
        
        # Save to database
        saved = self._save_squads_to_db(current_squads, target_gw)
        
        # Save bookmark if we processed any transactions
        if sorted_transactions:
            last_trans_id = max(t.get('id', 0) for t in sorted_transactions)
            self.save_transaction_bookmark(last_trans_id)
        
        stats = {
            'squads_updated': saved,
            'transactions_applied': applied,
            'transactions_failed': failed,
            'validation_errors': validation_errors,
            'errors': errors
        }
        
        print(f"[SquadProcessor] Full rebuild complete: {stats}")
        return stats
    
    def apply_transactions_incremental(
        self, 
        new_transactions: List[Dict], 
        current_gw: int
    ) -> Dict[str, any]:
        """
        Incremental: Apply only NEW transactions to existing squads.
        
        This method:
        1. Loads current squads from fpl_squads table
        2. Applies each new transaction in order
        3. Updates only changed entries in database
        4. Saves bookmark
        
        Args:
            new_transactions: List of transactions to apply (sorted by time)
            current_gw: Current gameweek
            
        Returns:
            Dict with statistics: entries_updated, transactions_applied, errors
        """
        print(f"[SquadProcessor] Incremental update for GW{current_gw}")
        print(f"  New transactions: {len(new_transactions)}")
        
        if not new_transactions:
            return {'entries_updated': 0, 'transactions_applied': 0, 'errors': []}
        
        # Load current squads from database
        current_squads = self._load_squads_from_db(current_gw)
        
        if not current_squads:
            print(f"[SquadProcessor] No existing squads found for GW{current_gw}, cannot apply incremental update")
            return {
                'entries_updated': 0,
                'transactions_applied': 0,
                'errors': ['No existing squads found for incremental update']
            }
        
        applied = 0
        failed = 0
        errors = []
        modified_entries = set()
        
        # Sort by time
        sorted_transactions = sorted(
            new_transactions,
            key=lambda t: t.get('added_time', ''),
            reverse=False
        )
        
        # Apply each transaction
        for trans in sorted_transactions:
            result = trans.get('result')
            if result != 'a':  # Only approved transactions
                continue
            
            entry_id = trans.get('entry')
            player_in = trans.get('element_in')
            player_out = trans.get('element_out')
            trans_id = trans.get('id')
            
            if entry_id not in current_squads:
                errors.append(f"Transaction {trans_id}: Unknown entry {entry_id}")
                failed += 1
                continue
            
            squad = current_squads[entry_id]
            
            try:
                # Remove player_out
                if player_out and player_out in squad:
                    squad.remove(player_out)
                
                # Add player_in
                if player_in and player_in not in squad:
                    squad.append(player_in)
                
                modified_entries.add(entry_id)
                applied += 1
                
            except Exception as e:
                errors.append(f"Transaction {trans_id}: {str(e)}")
                failed += 1
        
        # Validate modified squads
        validation_errors = []
        for entry_id in modified_entries:
            validation = self.validate_squad(current_squads[entry_id], entry_id)
            if not validation['valid']:
                validation_errors.extend(validation['errors'])
        
        # Save only modified entries
        saved = 0
        for entry_id in modified_entries:
            self._update_entry_squad(entry_id, current_squads[entry_id], current_gw)
            saved += 1
        
        # Save bookmark
        if sorted_transactions:
            last_trans_id = max(t.get('id', 0) for t in sorted_transactions)
            self.save_transaction_bookmark(last_trans_id)
        
        stats = {
            'entries_updated': saved,
            'transactions_applied': applied,
            'transactions_failed': failed,
            'validation_errors': validation_errors,
            'errors': errors
        }
        
        print(f"[SquadProcessor] Incremental update complete: {stats}")
        return stats
    
    def validate_squad(self, squad: List[int], entry_id: int = None) -> Dict:
        """
        Validate squad has exactly 15 players with correct position mix.
        
        FPL Draft rules:
        - Exactly 15 players total
        - 2 GK, 5 DEF, 5 MID, 3 FWD (standard formation)
        - Alternative formations allowed but must total 15
        
        Args:
            squad: List of player IDs
            entry_id: Optional entry ID for error messages
            
        Returns:
            Dict with 'valid' (bool) and 'errors' (List[str])
        """
        errors = []
        entry_label = f"Entry {entry_id}" if entry_id else "Squad"
        
        # Check total count
        if len(squad) != 15:
            errors.append(f"{entry_label}: Has {len(squad)} players, expected 15")
        
        # Check for duplicates
        if len(squad) != len(set(squad)):
            duplicates = [pid for pid in squad if squad.count(pid) > 1]
            errors.append(f"{entry_label}: Duplicate players: {duplicates}")
        
        # Check positions (if we can query them)
        try:
            if squad:
                position_counts = self.con.execute("""
                    SELECT position, COUNT(*) 
                    FROM pl_players 
                    WHERE id IN ({})
                    GROUP BY position
                """.format(','.join(str(p) for p in squad))).fetchall()
                
                positions = {pos: count for pos, count in position_counts}
                
                # Validate position mix (standard: 2 GK, 5 DEF, 5 MID, 3 FWD)
                expected = {1: 2, 2: 5, 3: 5, 4: 3}
                for pos, expected_count in expected.items():
                    actual_count = positions.get(pos, 0)
                    if actual_count != expected_count:
                        pos_name = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}[pos]
                        errors.append(
                            f"{entry_label}: Has {actual_count} {pos_name}, expected {expected_count}"
                        )
        except Exception as e:
            # If we can't validate positions, just warn
            print(f"[SquadProcessor] Could not validate positions: {e}")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def update_element_status(self, current_gw: int):
        """
        Sync element_status table from current fpl_squads.
        
        This updates the ownership status for all players based on
        who currently owns them in fpl_squads.
        
        Args:
            current_gw: Current gameweek to sync from
        """
        print(f"[SquadProcessor] Syncing element_status from fpl_squads GW{current_gw}")
        
        # Clear and rebuild element_status from current squads
        self.con.execute("DELETE FROM element_status")
        
        # Insert ownership records for all owned players
        self.con.execute("""
            INSERT INTO element_status (element_id, owner_entry_id, status, in_squad, updated_at)
            SELECT DISTINCT
                fs.player_id as element_id,
                fs.entry_id as owner_entry_id,
                'a' as status,
                TRUE as in_squad,
                CURRENT_TIMESTAMP as updated_at
            FROM fpl_squads fs
            WHERE fs.gameweek = ?
        """, [current_gw])
        
        # Insert records for free agents (players not in any squad)
        self.con.execute("""
            INSERT INTO element_status (element_id, owner_entry_id, status, in_squad, updated_at)
            SELECT 
                p.id as element_id,
                NULL as owner_entry_id,
                'a' as status,
                FALSE as in_squad,
                CURRENT_TIMESTAMP as updated_at
            FROM pl_players p
            WHERE p.id NOT IN (
                SELECT player_id FROM fpl_squads WHERE gameweek = ?
            )
        """, [current_gw])
        
        count = self.con.execute("SELECT COUNT(*) FROM element_status").fetchone()[0]
        owned = self.con.execute("SELECT COUNT(*) FROM element_status WHERE in_squad = TRUE").fetchone()[0]
        
        print(f"[SquadProcessor] Element status synced: {count} players ({owned} owned, {count - owned} free)")
    
    # Private helper methods
    
    def _load_squads_from_db(self, gameweek: int) -> Dict[int, List[int]]:
        """Load current squads from fpl_squads table."""
        result = self.con.execute("""
            SELECT entry_id, player_id
            FROM fpl_squads
            WHERE gameweek = ?
            ORDER BY entry_id, squad_position
        """, [gameweek]).fetchall()
        
        squads = {}
        for entry_id, player_id in result:
            if entry_id not in squads:
                squads[entry_id] = []
            squads[entry_id].append(player_id)
        
        print(f"[SquadProcessor] Loaded {len(squads)} squads from DB")
        return squads
    
    def _save_squads_to_db(self, squads: Dict[int, List[int]], gameweek: int) -> int:
        """
        Save all squads to fpl_squads table (replaces existing for this gameweek).
        
        Returns: Number of squads saved
        """
        # Delete existing squads for this gameweek
        self.con.execute("DELETE FROM fpl_squads WHERE gameweek = ?", [gameweek])
        
        # Insert new squads
        count = 0
        for entry_id, player_ids in squads.items():
            for position, player_id in enumerate(player_ids, start=1):
                self.con.execute("""
                    INSERT INTO fpl_squads (
                        entry_id, player_id, gameweek, squad_position,
                        is_captain, is_vice_captain
                    ) VALUES (?, ?, ?, ?, FALSE, FALSE)
                """, [entry_id, player_id, gameweek, position])
            count += 1
        
        self.con.commit()
        print(f"[SquadProcessor] Saved {count} squads to database")
        return count
    
    def _update_entry_squad(self, entry_id: int, player_ids: List[int], gameweek: int):
        """Update a single entry's squad (incremental update)."""
        # Delete existing squad for this entry/gameweek
        self.con.execute("""
            DELETE FROM fpl_squads 
            WHERE entry_id = ? AND gameweek = ?
        """, [entry_id, gameweek])
        
        # Insert updated squad
        for position, player_id in enumerate(player_ids, start=1):
            self.con.execute("""
                INSERT INTO fpl_squads (
                    entry_id, player_id, gameweek, squad_position,
                    is_captain, is_vice_captain
                ) VALUES (?, ?, ?, ?, FALSE, FALSE)
            """, [entry_id, player_id, gameweek, position])
        
        self.con.commit()
