# Trade Sync Architecture

## Problem
Inter-manager trades were not being tracked, causing squad data to be incorrect.

## Root Cause
1. **Trades are NOT in `/api/draft/league/{id}/transactions`** - only waivers/free agents
2. **Trades ARE in squad data** - FPL API returns current squads (with trades applied)
3. **Old system was "reconstructing"** - Tried to rebuild squads from transactions, which UNDID trades

## Solution: Smart Sync with Bookmarks

### 1. Data Sources
- **Squads**: `/api/entry/{id}/event/{gw}` - Current state (includes all trades)
- **Transactions**: `/api/draft/league/{id}/transactions` - Waivers & free agents only
- **Trades**: `/api/draft/league/{id}/trades` - Inter-manager trades (separate endpoint)

### 2. Fetch Metadata
Track timestamps in `user_preferences`:
- `squads_fetched_at_gw{N}` - When squads were last fetched
- `trades_fetched_at_gw{N}` - When trades were last fetched
- `last_trade_id` - ID of last processed trade

### 3. Smart Reconciliation Logic

```python
if squads_fetch_time >= trades_fetch_time:
    # Squads are ABSOLUTE TRUTH (they include all trades)
    save_squads_directly()
else:
    # Trades are newer than squads
    # Apply only NEW trades to squads
    new_trades = get_trades_since_bookmark()
    final_squads = apply_trades_to_squads(squads, new_trades)
    save_squads(final_squads)
```

### 4. Bookmarklet Changes
Now fetches:
1. `/api/draft/league/{id}/transactions` - Waivers
2. `/api/draft/league/{id}/trades` - Trades (if endpoint exists)
3. Adds fetch timestamps: `fetchedAt`, `squadsFetchedAt`, `tradesFetchedAt`

### 5. Database Changes
- `SyncManager` class handles reconciliation
- Metadata stored in `user_preferences` table
- Squads saved directly (not "reconstructed")

## Benefits
- ✅ Trades are now tracked correctly
- ✅ Incremental updates (only new trades)
- ✅ Smart reconciliation based on timestamps
- ✅ Squad data is always correct
- ✅ Future-proof for any data source timing

## Validation
Use `validate_squads.html` to compare DB vs live FPL:
```bash
open /Users/ilay/RiderProjects/fpl_analyzer/validate_squads.html
```

## Testing Trade Detection
Check if FPL API has separate trades endpoint:
```bash
open /Users/ilay/RiderProjects/fpl_analyzer/check_fpl_trades.html
```
