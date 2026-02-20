#!/usr/bin/env python3
"""
Database Sync Validation Tool

Validates that all database tables are in sync with the latest JSON import.
"""

import json
import duckdb
from pathlib import Path
from datetime import datetime

def validate_sync():
    """Validate DB sync status."""
    
    # Find latest JSON file
    json_files = list(Path(".").glob("fpl_league_data_*.json"))
    if not json_files:
        print("❌ No JSON files found!")
        return False
    
    latest_json = max(json_files, key=lambda p: p.stem)
    print(f"📄 Latest JSON: {latest_json.name}")
    
    # Load JSON
    with open(latest_json, 'r') as f:
        json_data = json.load(f)
    
    json_gw = json_data.get('currentEvent', 'UNKNOWN')
    json_players = len(json_data.get('bootstrap', {}).get('elements', []))
    json_squads = len(json_data.get('squads', {}))
    json_transactions = len(json_data.get('transactions', []))
    
    print(f"\n=== JSON FILE DATA ===")
    print(f"📅 Current GW: {json_gw}")
    print(f"👤 Players: {json_players}")
    print(f"👥 Squads: {json_squads}")
    print(f"🔄 Transactions: {json_transactions}")
    
    # Check database
    db_path = Path("fpl_data.duckdb")
    if not db_path.exists():
        print(f"\n❌ Database not found at {db_path}")
        return False
    
    db_modified = datetime.fromtimestamp(db_path.stat().st_mtime)
    print(f"\n=== DATABASE STATUS ===")
    print(f"📁 Path: {db_path.absolute()}")
    print(f"🕐 Last Modified: {db_modified}")
    print(f"💾 Size: {db_path.stat().st_size / 1024 / 1024:.2f} MB")
    
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        
        # Get DB current GW
        result = con.execute("SELECT value FROM user_preferences WHERE key = 'current_gameweek'").fetchone()
        db_gw = int(result[0]) if result else None
        
        # Get transaction bookmark
        result = con.execute("SELECT value FROM user_preferences WHERE key = 'last_transaction_id'").fetchone()
        db_bookmark = int(result[0]) if result else None
        
        # Get data counts
        db_players = con.execute("SELECT COUNT(*) FROM pl_players").fetchone()[0]
        db_squads = con.execute("SELECT COUNT(*) FROM fpl_squads WHERE gameweek = ?", [db_gw]).fetchone()[0]
        db_transactions = con.execute("SELECT COUNT(*) FROM fpl_transactions").fetchone()[0]
        
        # Get GW data availability
        gw_stats = con.execute("SELECT DISTINCT gameweek FROM player_gameweeks ORDER BY gameweek DESC LIMIT 5").fetchall()
        squad_gws = con.execute("SELECT DISTINCT gameweek FROM fpl_squads ORDER BY gameweek DESC").fetchall()
        
        print(f"\n📊 Current GW: {db_gw}")
        print(f"👤 Players: {db_players}")
        print(f"👥 Squad slots (GW{db_gw}): {db_squads}")
        print(f"🔄 Transactions: {db_transactions}")
        print(f"🔖 Transaction Bookmark: {db_bookmark}")
        print(f"📈 GWs with stats: {[r[0] for r in gw_stats]}")
        print(f"📋 GWs with squads: {[r[0] for r in squad_gws]}")
        
        con.close()
        
        # Validation
        print(f"\n=== SYNC VALIDATION ===")
        issues = []
        
        if json_gw != db_gw:
            issues.append(f"❌ GW MISMATCH: JSON={json_gw}, DB={db_gw}")
        else:
            print(f"✅ GW in sync: {json_gw}")
        
        if json_players != db_players:
            issues.append(f"❌ PLAYER COUNT MISMATCH: JSON={json_players}, DB={db_players}")
        else:
            print(f"✅ Player count in sync: {json_players}")
        
        if json_transactions != db_transactions:
            issues.append(f"⚠️  TRANSACTION MISMATCH: JSON={json_transactions}, DB={db_transactions}")
        
        if db_squads != json_squads * 15:  # Each squad has 15 players
            issues.append(f"⚠️  SQUAD MISMATCH: Expected {json_squads * 15}, got {db_squads}")
        
        if issues:
            print(f"\n{'='*60}")
            for issue in issues:
                print(issue)
            print(f"{'='*60}")
            print(f"\n🔧 RECOMMENDED ACTION:")
            print(f"   1. Re-fetch FPL data for GW{json_gw + 2} (current real GW)")
            print(f"   2. Run: python -c 'from fpl_predictor.data.importer import import_from_file; import_from_file(\"{latest_json.name}\")'")
            return False
        else:
            print(f"\n✅ ALL SYSTEMS IN SYNC!")
            return True
            
    except Exception as e:
        print(f"\n❌ Error accessing database: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    validate_sync()
