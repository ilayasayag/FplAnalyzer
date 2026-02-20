# Testing the New Trade Sync System

## Quick Summary
We've implemented a smart sync system that:
1. ✅ Fetches trades from FPL API (separate from transactions)
2. ✅ Uses bookmarks to track what's been synced
3. ✅ Smart reconciliation: If squads are newer than trades, trust squads. Otherwise apply trades.

## Step 1: Update the Bookmarklet
The bookmarklet has been updated to:
- Try fetching from `/api/draft/league/{id}/trades` endpoint
- Add fetch timestamps: `fetchedAt`, `squadsFetchedAt`, `tradesFetchedAt`

**Action Required:**
1. Go to your analyzer: http://localhost:5001
2. Click "Update Bookmarklet" button
3. Replace your old bookmarklet with the new one

## Step 2: Re-Fetch FPL Data
1. Go to https://draft.premierleague.com (must be logged in)
2. Click the new bookmarklet
3. Save the JSON with a new name: `fpl_league_data_2026-01-22_with_trades.json`

## Step 3: Test Trade Detection
Before importing, let's check if the FPL API actually has a trades endpoint:

```bash
# Open the diagnostic tool
open /Users/ilay/RiderProjects/fpl_analyzer/check_fpl_trades.html

# Or in browser: file:///Users/ilay/RiderProjects/fpl_analyzer/check_fpl_trades.html
```

This will test 5 different API endpoints and show you:
- ✅ Which endpoint has trades
- 📊 How many trades exist
- 🔍 Sample trade data

## Step 4: Import the New Data
Stop the server, import fresh data:

```bash
# Stop server
lsof -ti:5001 | xargs kill -9

# Import
cd /Users/ilay/RiderProjects/fpl_analyzer
python3 << 'PYTHON'
from fpl_predictor.data.importer import import_from_file
result = import_from_file('fpl_league_data_2026-01-22_with_trades.json')
print(f"\nImport Result:")
print(f"  Success: {result.success}")
print(f"  Players: {result.players_imported}")
print(f"  Squads: {result.squads_imported}")
print(f"  Transactions: {result.transactions_imported}")
PYTHON

# Restart server
python run_server.py --port 5001
```

## Step 5: Validate Squads
```bash
# Open the squad validator
open /Users/ilay/RiderProjects/fpl_analyzer/validate_squads.html

# Or in browser: file:///Users/ilay/RiderProjects/fpl_analyzer/validate_squads.html
```

This will:
1. Fetch current squads from live FPL
2. Compare with your database
3. Show any mismatches (players missing or extra)

## Expected Results

### If Trades Endpoint Exists:
- ✅ Bookmarklet fetches trades separately
- ✅ JSON contains trades with `kind: 't'`
- ✅ Importer detects trades and saves them
- ✅ Squads reflect all trades
- ✅ Validator shows 100% match

### If Trades Endpoint Doesn't Exist:
- ⚠️ No separate trades endpoint
- ✅ Squad data still includes trades (FPL applies them server-side)
- ✅ Importer trusts squad data directly
- ✅ Squads are correct even without trade data
- ✅ Validator shows 100% match

## Troubleshooting

### "No trades found in transactions"
This is OK if:
- Squad validator shows 100% match
- FPL API doesn't have separate trades endpoint
- Squad data already includes trades

### "Mismatches in validator"
This means:
1. Run the bookmarklet again (get fresh data)
2. Make sure you're on the correct gameweek
3. Check if FPL data is from GW20 but you're comparing GW22

### "Import failed"
Check:
- Is the JSON file valid?
- Is the server stopped before import?
- Check console for specific error messages

## Next Steps
After successful validation:
1. Your Saliba/Cunha ↔️ Gabriel/Casemiro trade should be reflected
2. All squad data should match live FPL exactly
3. Future imports will use smart reconciliation

## Architecture Docs
See `TRADE_SYNC_ARCHITECTURE.md` for full technical details.
