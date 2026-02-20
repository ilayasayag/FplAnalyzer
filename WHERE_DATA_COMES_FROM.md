# Where FPL Data Comes From - Complete API Map

## Bookmarklet Fetch Sequence

### 1. **Squads** (Current State with ALL trades applied)
```javascript
// Line 9264 in fpl_fixture_analyzer.html
const squadRes = await fetch(
  'https://draft.premierleague.com/api/entry/' + entry.entry_id + '/event/' + currentEvent
);
```
**Stored in JSON:** `data.squads[entry_id]`
**What it contains:** 15 players (picks) for that team for that GW
**Important:** This is the CURRENT state - FPL has already applied all trades server-side!

### 2. **Transactions** (Waivers + Free Agents ONLY)
```javascript
// Line 9220
const transRes = await fetch(
  'https://draft.premierleague.com/api/draft/league/' + leagueId + '/transactions'
);
```
**Stored in JSON:** `data.transactions.transactions[]`
**What it contains:**
- `kind: 'w'` - Waivers (107 in your data)
- `kind: 'f'` - Free agent pickups (18 in your data)
- **NO trades** (`kind: 't'`) ❌

### 3. **Trades** (Separate endpoint - ATTEMPTED but might not exist)
```javascript
// Line 9231 - NEW CODE
const tradesRes = await fetch(
  'https://draft.premierleague.com/api/draft/league/' + leagueId + '/trades'
);
```
**Stored in JSON:** Merged into `data.transactions.transactions[]` if found
**Status:** 🔍 Need to test if this endpoint exists for your league

## Your Current JSON Analysis

### ✅ What You Have:
- **Squads:** 8 teams ✓
- **Squad timestamp:** `2026-01-22T19:15:09.688Z` ✓
- **Transactions:** 125 waivers/free agents ✓
- **Trades:** 0 ❌
- **Gameweek:** 20 (OLD - should be 22!)

### ❌ What's Missing/Wrong:
1. **No trades in transactions** - Either:
   - FPL API doesn't return trades in `/transactions` endpoint
   - `/trades` endpoint doesn't exist or failed
   - Trades are only in squad data (already applied)

2. **GW20 data** - You need GW22!

3. **No trade activity** - Even though bookmarklet tried, it found nothing

## The Real Question: Does Your League Have a Trades Endpoint?

Test this in your browser console (while logged into draft.premierleague.com):

```javascript
fetch('https://draft.premierleague.com/api/draft/league/201560/trades')
  .then(r => {
    console.log('Response status:', r.status);
    return r.json();
  })
  .then(d => console.log('✅ TRADES ENDPOINT EXISTS:', d))
  .catch(e => console.log('❌ No trades endpoint:', e));
```

## Why Saliba Appeared in Your DB

Your squad data shows **GW20 state:**
- **Entry 822133 (Hapoel Eliyahu - YOUR team)**: Has Saliba ✓
- **Entry 830139 (CHANGE NAME - YOUR team)**: No Saliba, no Gabriel

**The trade happened AFTER GW20 but your JSON is from GW20!**

## Solution

You need to:

1. **Re-fetch for GW22** (current GW)
2. The squad data will already have the trade applied
3. Import the fresh data
4. Your DB will reflect the current state

## Why "Smart Sync" Will Still Work

Even if `/trades` endpoint doesn't exist:
- Squad data from `/api/entry/{id}/event/{gw}` is the **absolute truth**
- FPL applies trades server-side before returning squad data
- We trust this data directly (no reconstruction needed)
- Your trade WILL be reflected in GW22 squad data!

## Testing Plan

1. **Test trades endpoint** (console command above)
2. **Re-fetch with current GW** (bookmarklet on FPL website)
3. **Check JSON has GW22** (`data.currentEvent` should be 22)
4. **Import and validate**
