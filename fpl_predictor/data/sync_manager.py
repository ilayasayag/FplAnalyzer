"""
Sync Manager - Smart data reconciliation with bookmarks

Handles the complex logic of:
1. Tracking when trades were last fetched
2. Tracking when squads were last fetched
3. Deciding whether to trust squad data or apply trades
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import duckdb

from .database import get_connection


@dataclass
class SyncMetadata:
    """Metadata about when data was last synced."""
    squads_fetched_at: Optional[datetime] = None
    trades_fetched_at: Optional[datetime] = None
    last_trade_id: Optional[int] = None
    gameweek: Optional[int] = None


class SyncManager:
    """
    Manages smart reconciliation of squad data.
    
    Logic:
    1. If squads are newer than trades → Trust squads (they include all trades)
    2. If trades are newer than squads → Apply trades to squads
    3. Track bookmarks for incremental updates
    """
    
    def __init__(self, con: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = con or get_connection()
    
    def get_sync_metadata(self, gameweek: int) -> SyncMetadata:
        """Get sync metadata for a gameweek."""
        metadata = SyncMetadata(gameweek=gameweek)
        
        # Get squads fetch time
        result = self.con.execute(
            "SELECT value FROM user_preferences WHERE key = ?",
            [f'squads_fetched_at_gw{gameweek}']
        ).fetchone()
        if result and result[0]:
            metadata.squads_fetched_at = datetime.fromisoformat(result[0])
        
        # Get trades fetch time
        result = self.con.execute(
            "SELECT value FROM user_preferences WHERE key = ?",
            [f'trades_fetched_at_gw{gameweek}']
        ).fetchone()
        if result and result[0]:
            metadata.trades_fetched_at = datetime.fromisoformat(result[0])
        
        # Get last trade ID
        result = self.con.execute(
            "SELECT value FROM user_preferences WHERE key = 'last_trade_id'"
        ).fetchone()
        if result and result[0]:
            metadata.last_trade_id = int(result[0])
        
        return metadata
    
    def save_sync_metadata(self, metadata: SyncMetadata):
        """Save sync metadata."""
        gw = metadata.gameweek
        
        if metadata.squads_fetched_at:
            self.con.execute("""
                INSERT OR REPLACE INTO user_preferences (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, [f'squads_fetched_at_gw{gw}', metadata.squads_fetched_at.isoformat()])
        
        if metadata.trades_fetched_at:
            self.con.execute("""
                INSERT OR REPLACE INTO user_preferences (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, [f'trades_fetched_at_gw{gw}', metadata.trades_fetched_at.isoformat()])
        
        if metadata.last_trade_id:
            self.con.execute("""
                INSERT OR REPLACE INTO user_preferences (key, value, updated_at)
                VALUES ('last_trade_id', ?, CURRENT_TIMESTAMP)
            """, [str(metadata.last_trade_id)])
        
        self.con.commit()
    
    def should_trust_squads(self, metadata: SyncMetadata) -> bool:
        """
        Determine if we should trust squad data as absolute.
        
        Returns True if:
        - Squad fetch time is AFTER trade fetch time (squads include all trades)
        - OR no trade data exists
        """
        if not metadata.squads_fetched_at:
            return False  # No squad data
        
        if not metadata.trades_fetched_at:
            return True  # No trade data, so squads are truth
        
        # Compare timestamps
        return metadata.squads_fetched_at >= metadata.trades_fetched_at
    
    def get_new_trades_since_bookmark(
        self, 
        all_trades: List[Dict], 
        last_trade_id: Optional[int]
    ) -> List[Dict]:
        """Get only trades that are newer than our bookmark."""
        if not last_trade_id:
            return all_trades
        
        return [t for t in all_trades if t.get('id', 0) > last_trade_id]
    
    def process_import(
        self,
        squads_data: Dict[int, List[int]],
        trades_data: List[Dict],
        squads_fetch_time: datetime,
        trades_fetch_time: datetime,
        gameweek: int
    ) -> Tuple[Dict[int, List[int]], str]:
        """
        Process import with smart reconciliation.
        
        Returns:
            (final_squads, strategy_used)
        """
        metadata = self.get_sync_metadata(gameweek)
        
        # Scenario 1: Squads are newer than trades
        if squads_fetch_time >= trades_fetch_time:
            print(f"[SyncManager] Squads fetched at {squads_fetch_time} >= Trades at {trades_fetch_time}")
            print(f"[SyncManager] ✓ Trusting squad data as absolute (includes all trades)")
            
            # Update metadata
            metadata.squads_fetched_at = squads_fetch_time
            metadata.trades_fetched_at = trades_fetch_time
            if trades_data:
                metadata.last_trade_id = max((t.get('id', 0) for t in trades_data), default=0)
            self.save_sync_metadata(metadata)
            
            return squads_data, "trusted_squads"
        
        # Scenario 2: Trades are newer than squads
        else:
            print(f"[SyncManager] Trades fetched at {trades_fetch_time} > Squads at {squads_fetch_time}")
            print(f"[SyncManager] ⚠️ Applying new trades to squad data")
            
            # Get only NEW trades
            new_trades = self.get_new_trades_since_bookmark(
                trades_data,
                metadata.last_trade_id
            )
            
            if not new_trades:
                print(f"[SyncManager] No new trades to apply")
                return squads_data, "no_new_trades"
            
            print(f"[SyncManager] Applying {len(new_trades)} new trades")
            
            # Apply trades to squads
            final_squads = self._apply_trades_to_squads(squads_data, new_trades)
            
            # Update metadata
            metadata.squads_fetched_at = squads_fetch_time
            metadata.trades_fetched_at = trades_fetch_time
            metadata.last_trade_id = max((t.get('id', 0) for t in trades_data), default=0)
            self.save_sync_metadata(metadata)
            
            return final_squads, f"applied_{len(new_trades)}_trades"
    
    def _apply_trades_to_squads(
        self, 
        squads: Dict[int, List[int]], 
        trades: List[Dict]
    ) -> Dict[int, List[int]]:
        """
        Apply inter-manager trades to squads.
        
        Trade format:
        {
            'id': 12345,
            'kind': 't',
            'entry': 111,      # Manager 1
            'entry_2': 222,    # Manager 2
            'element_out': 10, # Manager 1 gives player 10
            'element_in': 20,  # Manager 1 gets player 20
            'element_out_2': 20, # Manager 2 gives player 20
            'element_in_2': 10,  # Manager 2 gets player 10
        }
        """
        result = {k: list(v) for k, v in squads.items()}  # Deep copy
        
        for trade in sorted(trades, key=lambda t: t.get('id', 0)):
            if trade.get('kind') != 't':
                continue  # Only process trades
            
            entry1 = trade.get('entry')
            entry2 = trade.get('entry_2')
            
            if not entry1 or not entry2:
                continue
            
            # Manager 1: Remove element_out, Add element_in
            player_out_1 = trade.get('element_out')
            player_in_1 = trade.get('element_in')
            
            # Manager 2: Remove element_out_2, Add element_in_2
            player_out_2 = trade.get('element_out_2')
            player_in_2 = trade.get('element_in_2')
            
            # Apply to manager 1
            if entry1 in result:
                if player_out_1 and player_out_1 in result[entry1]:
                    result[entry1].remove(player_out_1)
                if player_in_1 and player_in_1 not in result[entry1]:
                    result[entry1].append(player_in_1)
            
            # Apply to manager 2
            if entry2 in result:
                if player_out_2 and player_out_2 in result[entry2]:
                    result[entry2].remove(player_out_2)
                if player_in_2 and player_in_2 not in result[entry2]:
                    result[entry2].append(player_in_2)
            
            print(f"[SyncManager]   Trade {trade.get('id')}: Entry {entry1} ↔️ Entry {entry2}")
            print(f"[SyncManager]     {entry1}: Player {player_out_1} → {player_in_1}")
            print(f"[SyncManager]     {entry2}: Player {player_out_2} → {player_in_2}")
        
        return result
