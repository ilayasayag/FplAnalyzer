# 🔍 How to Find FPL Trade Data - Step by Step Guide

## Problem
Your JSON has 0 trades even though trades happened in your league. We need to find where FPL stores trade data.

## Solution - 3 Steps

### Step 1: Run the Diagnostic Tool

1. **Open the diagnostic file:**
   ```bash
   open /Users/ilay/RiderProjects/fpl_analyzer/fpl_trade_diagnostic.html
   ```

2. **Go to FPL Draft website** in another tab:
   - Navigate to: https://draft.premierleague.com/
   - **Log in** to your league

3. **Switch back to the diagnostic tool tab**

4. **Click these buttons in order:**
   - "Test /transactions" - Check if trades are in transactions
   - "Test /trades" - Check if there's a separate trades endpoint
   - "Analyze Transaction Types" - See the structure of each type
   - "Deep Search Entire League Data" - Search everywhere

5. **Take screenshots or copy results** and share with me

### Step 2: What I Need From You

Please share:

1. **What endpoints returned data?**
   - Did `/trades` work? (status 200)
   - What's in `/transactions`?

2. **Sample trade structure:**
   - If you found trades, copy ONE trade object
   - I need to see the exact fields FPL uses

3. **Your findings:**
   - Click "Export as JSON" and share the file, OR
   - Click "Copy to Clipboard" and paste in chat

### Step 3: Manual Browser Console Test

If the tool doesn't work, try this in browser console (on draft.premierleague.com):

```javascript
// Test trades endpoint
fetch('https://draft.premierleague.com/api/draft/league/201560/trades')
  .then(r => r.json())
  .then(d => {
    console.log('✅ TRADES RESPONSE:', d);
    console.log('Number of trades:', d.trades?.length || 0);
    if (d.trades && d.trades.length > 0) {
      console.log('Sample trade:', d.trades[0]);
    }
  })
  .catch(e => console.error('❌ Trades endpoint failed:', e));

// Also check transactions
fetch('https://draft.premierleague.com/api/draft/league/201560/transactions')
  .then(r => r.json())
  .then(d => {
    const trans = d.transactions || [];
    console.log('✅ TRANSACTIONS:', trans.length);
    
    // Look for trades
    const trades = trans.filter(t => 
      t.kind === 't' || 
      t.entry_2 || 
      t.element_in_2
    );
    
    console.log('Trades found:', trades.length);
    if (trades.length > 0) {
      console.log('Sample trade:', trades[0]);
    }
    
    // Show all unique fields
    const allFields = new Set();
    trans.forEach(t => Object.keys(t).forEach(k => allFields.add(k)));
    console.log('All fields in transactions:', Array.from(allFields));
  });
```

## What Happens Next

Once you share the data, I will:

1. ✅ **Update the bookmarklet** to fetch trades correctly
2. ✅ **Update the importer** to parse trade structure properly
3. ✅ **Update SyncManager** to handle trades correctly
4. ✅ **Test with your data** to ensure it works

## Expected Results

### Scenario A: Trades are in `/transactions` with `kind: 't'`
```json
{
  "id": 123456,
  "kind": "t",
  "entry": 830139,
  "entry_2": 827066,
  "element_in": 5,
  "element_out": 6,
  "element_in_2": 6,
  "element_out_2": 5,
  "added": "2026-01-20T12:00:00Z",
  "event": 21
}
```

### Scenario B: Trades are in separate `/trades` endpoint
```json
{
  "trades": [
    {
      "id": 123456,
      "entry_id_1": 830139,
      "entry_id_2": 827066,
      "player_id_1_in": 5,
      "player_id_1_out": 6,
      "player_id_2_in": 6,
      "player_id_2_out": 5,
      "added": "2026-01-20T12:00:00Z",
      "event": 21
    }
  ]
}
```

### Scenario C: Trades are NOT available via API
If FPL doesn't expose trades via API, we'll rely on squad snapshots:
- Fetch squads for GW22 (current state with trades applied)
- Trust this as the absolute truth
- No need to track individual trades

## Current Bookmarklet Status

**What it does NOW:**
1. ✅ Fetches `/transactions` (waivers + free agents)
2. ✅ ATTEMPTS `/trades` (but might fail or return empty)
3. ✅ Fetches squads (which already have trades applied)
4. ✅ Adds timestamps

**What needs fixing:**
- 🔧 Better error handling for trades endpoint
- 🔧 Proper parsing of trade structure (depends on your findings)
- 🔧 Better logging to show what was found

## Ready?

Run the diagnostic tool and share your findings! 🚀
