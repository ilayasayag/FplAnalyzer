# Database Sync Issue - Diagnosis & Fix

## Problem Summary

Your FPL Analyzer is showing **outdated data** (GW20-21) when the real FPL season is at **GW22**.

## Root Causes

### 1. **Outdated JSON Source File** ❌
- File: `fpl_league_data_2026-01-22.json`
- Contains: **GW20** data
- Expected: **GW22** data
- **The bookmarklet/fetcher needs to be run again on the FPL website!**

### 2. **Database Not Updated** ❌
- Database last modified: `2026-01-17 02:22:48` (5 days ago)
- Latest JSON created: `2026-01-22 20:16` (today)
- **The import ran but didn't update the DB!**

### 3. **Silent Import Failure** ❌
- `/api/db/import` returns 200 OK
- But database file timestamp doesn't change
- No error shown to user
- **Import is failing silently!**

## Detailed Analysis

### JSON File Contents (2026-01-22)
```
📅 Current GW: 20
👤 Players: 801
👥 Squads: 8
🔄 Transactions: 1 (!!!)
⚽ Matches: 0 (!!!)
```

**Issues:**
- Only 1 transaction (should have 100+)
- No matches data
- GW20 instead of GW22

### Database Contents (Last Updated: 2026-01-17)
```
📊 Current GW: 20 (from old import)
👤 Players: 801
👥 Squad slots: 120
🔄 Transactions: 125
```

## The Fix

### Step 1: Re-Fetch FPL Data ⚠️ **CRITICAL**

You need to **go to the FPL Draft website** and run the bookmarklet again to get **GW22** data:

1. Go to: `https://draft.premierleague.com/league/YOUR_LEAGUE_ID/status`
2. Click the "FPL Data Fetcher" bookmarklet
3. Wait for it to complete
4. Save the JSON as `fpl_league_data_2026-01-22_GW22.json`

### Step 2: Force Database Update

Once you have the correct JSON file, run:

```bash
cd /Users/ilay/RiderProjects/fpl_analyzer

# Stop the Flask server first (to release DB lock)
lsof -ti:5001 | xargs kill -9

# Import directly using Python
python3 << 'EOF'
from fpl_predictor.data.importer import import_from_file
result = import_from_file('fpl_league_data_2026-01-22_GW22.json')
print(f"Import result: {result.to_dict()}")
EOF

# Restart server
python run_server.py --port 5001
```

### Step 3: Validate Sync

```bash
python validate_db_sync.py
```

## Why The Current System Fails

1. **DuckDB Single-Writer Limitation**: Only one process can write at a time
2. **Flask holds persistent connection**: Blocks other write attempts
3. **No error propagation**: Import failures aren't surfaced to the UI
4. **No timestamp validation**: System doesn't check if JSON is newer than DB

## Long-Term Fix Needed

1. **Add import validation** in `/api/db/import`:
   - Check if JSON GW > DB GW
   - Verify transaction count
   - Confirm DB file timestamp changes after import
   
2. **Add sync status endpoint** `/api/db/sync-status`:
   - Compare JSON file timestamp vs DB timestamp
   - Show GW mismatch warnings
   - Display last successful import time

3. **Improve error handling**:
   - Catch and log DuckDB lock errors
   - Return 503 if DB is locked
   - Show clear error messages in UI

4. **Add GW detection**:
   - Auto-detect current real-world GW from PL API
   - Warn if local data is behind
   - Show "Data is X gameweeks old" warning

## Immediate Action Required

**🚨 YOU MUST RE-FETCH THE FPL DATA FROM THE WEBSITE! 🚨**

The JSON file you have is from GW20. You need GW22 data.

After re-fetching, stop the server and import manually to bypass the lock issue.
