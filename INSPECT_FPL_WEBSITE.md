# 🔍 How to Inspect FPL Draft Website - Find Squad & Trade Data

## Method 1: Network Tab Inspection (Most Accurate)

### Step 1: Open Network Tab
1. Go to: https://draft.premierleague.com/
2. **Log in** to your account
3. Press **F12** (or Cmd+Option+I on Mac) to open DevTools
4. Click the **Network** tab
5. Check the box for **"Preserve log"** (so requests don't disappear)
6. Filter by **"Fetch/XHR"** to see only API calls

### Step 2: Navigate to Your League
1. In FPL website, click on your league
2. Watch the Network tab - you'll see API requests appearing
3. Look for URLs containing:
   - `league/201560/details`
   - `league/201560/element-status`
   - `entry/XXXXX/event/22` (squad for a team)
   - `league/201560/transactions`
   - `league/201560/trades` (might not exist)

### Step 3: Find Squad Data
1. In Network tab, find request like: `entry/830139/event/22`
2. Click on it
3. Click **"Response"** tab
4. You'll see JSON with structure like:
```json
{
  "picks": [
    {"element": 287, "position": 1, "is_captain": false},
    {"element": 6, "position": 2, "is_captain": false},
    // ... 15 players total
  ],
  "entry_history": {...},
  "subs": [...]
}
```

5. **Right-click on the response** → **"Copy Response"**
6. Paste it here and I'll analyze it!

### Step 4: Find Trade/Transaction Data
1. In Network tab, find: `league/201560/transactions`
2. Click on it → **"Response"** tab
3. Look at the JSON structure:
```json
{
  "transactions": [
    {
      "id": 123456,
      "kind": "w",  // or "f", or "t" for trade
      "entry": 830139,
      "element_in": 5,
      "element_out": 6,
      // ... if it's a trade, will have entry_2, element_in_2, etc
    }
  ]
}
```

4. **Copy the entire response** and share it

### Step 5: Check for Separate Trades Endpoint
1. In Network tab filter, type: `trades`
2. See if there's a request to: `league/201560/trades`
3. If yes:
   - Click it
   - Copy response
   - Share it
4. If no:
   - Trades are probably in the `/transactions` endpoint

---

## Method 2: Console Inspection (Quick Test)

### Open Console and Run This:

1. Go to draft.premierleague.com (logged in)
2. Open Console (F12)
3. Paste this code:

```javascript
// === FPL DATA INSPECTOR ===
const LEAGUE_ID = 201560;
const YOUR_ENTRY = 830139;  // Your team ID
const YONI_ENTRY = 827066;  // Yoni's team ID
const CURRENT_GW = 22;

console.log('🔍 === FPL DATA INSPECTOR ===\n');

// Test 1: Fetch YOUR current squad
fetch(`https://draft.premierleague.com/api/entry/${YOUR_ENTRY}/event/${CURRENT_GW}`)
  .then(r => r.json())
  .then(squad => {
    console.log(`📋 YOUR Squad (GW${CURRENT_GW}):`);
    console.log(`Total players: ${squad.picks?.length || 0}`);
    
    // Check for Saliba (6) and Gabriel (5)
    const playerIds = squad.picks?.map(p => p.element) || [];
    const hasSaliba = playerIds.includes(6);
    const hasGabriel = playerIds.includes(5);
    
    console.log(`  Saliba (6): ${hasSaliba ? '✅ IN SQUAD' : '❌ NOT IN SQUAD'}`);
    console.log(`  Gabriel (5): ${hasGabriel ? '✅ IN SQUAD' : '❌ NOT IN SQUAD'}`);
    
    console.log('\nFull squad player IDs:', playerIds);
    console.log('\nFull response:', squad);
  });

// Test 2: Fetch YONI's current squad
fetch(`https://draft.premierleague.com/api/entry/${YONI_ENTRY}/event/${CURRENT_GW}`)
  .then(r => r.json())
  .then(squad => {
    console.log(`\n📋 YONI's Squad (GW${CURRENT_GW}):`);
    const playerIds = squad.picks?.map(p => p.element) || [];
    const hasSaliba = playerIds.includes(6);
    const hasGabriel = playerIds.includes(5);
    
    console.log(`  Saliba (6): ${hasSaliba ? '✅ IN SQUAD' : '❌ NOT IN SQUAD'}`);
    console.log(`  Gabriel (5): ${hasGabriel ? '✅ IN SQUAD' : '❌ NOT IN SQUAD'}`);
    
    console.log('\nFull squad player IDs:', playerIds);
  });

// Test 3: Check transactions
fetch(`https://draft.premierleague.com/api/draft/league/${LEAGUE_ID}/transactions`)
  .then(r => r.json())
  .then(data => {
    const trans = data.transactions || [];
    console.log(`\n📊 Transactions:`);
    console.log(`Total: ${trans.length}`);
    
    // Count by type
    const byType = {};
    trans.forEach(t => {
      const kind = t.kind || 'unknown';
      byType[kind] = (byType[kind] || 0) + 1;
    });
    console.log('By type:', byType);
    
    // Look for trades
    const trades = trans.filter(t => t.kind === 't' || t.entry_2 || t.element_in_2);
    console.log(`Trades found: ${trades.length}`);
    
    if (trades.length > 0) {
      console.log('\n🔄 TRADE SAMPLE:', trades[0]);
    } else {
      console.log('\n⚠️ No trades detected in transactions');
    }
    
    // Check for YOUR recent transactions
    const yourTrans = trans.filter(t => 
      t.entry === YOUR_ENTRY || 
      t.entry_2 === YOUR_ENTRY
    ).slice(-5);
    
    console.log(`\nYour recent transactions (last 5):`);
    yourTrans.forEach(t => {
      console.log(`  GW${t.event}: ${t.kind} - IN:${t.element_in} OUT:${t.element_out}`);
    });
  });

// Test 4: Try separate trades endpoint
fetch(`https://draft.premierleague.com/api/draft/league/${LEAGUE_ID}/trades`)
  .then(r => {
    console.log(`\n🔄 /trades endpoint: ${r.status}`);
    return r.json();
  })
  .then(data => {
    console.log('Trades response:', data);
    if (data.trades) {
      console.log(`✅ Trades found: ${data.trades.length}`);
      if (data.trades.length > 0) {
        console.log('Sample:', data.trades[0]);
      }
    }
  })
  .catch(e => {
    console.log('❌ /trades endpoint not available');
  });

console.log('\n⏳ Fetching data... (check above for results)');
```

4. **Wait for all requests to complete**
5. **Copy the ENTIRE console output** and paste it here

---

## Method 3: Use FPL's Own UI to See Current State

### Manual Verification:
1. Go to your league on FPL website
2. Click on **YOUR team** (Hapoel Eliyahu or CHANGE NAME)
3. Click **"Squad"** or **"Team"** tab
4. **Take a screenshot** showing:
   - Which defenders you have
   - Is Saliba there? Is Gabriel there?

5. Click on **"Transactions"** or **"Trades"** tab
6. **Take a screenshot** showing recent trades

7. Share both screenshots here!

---

## What I'm Looking For:

### From Network Tab / Console:
1. **Squad Response Structure:**
   ```json
   {
     "picks": [
       {"element": 6, "position": 2},  // Is this Saliba or Gabriel?
       // ... rest of squad
     ]
   }
   ```

2. **Transaction/Trade Structure:**
   ```json
   {
     "transactions": [
       {
         "id": 123456,
         "kind": "?",  // What is this for trades?
         "entry": 830139,
         "entry_2": 827066,  // Does this exist?
         "element_in": 5,
         "element_out": 6,
         // ... what other fields?
       }
     ]
   }
   ```

3. **Key Questions:**
   - Does GW22 squad show Gabriel (5) or Saliba (6) for you?
   - Does Yoni have the opposite player?
   - Are trades in `/transactions` or separate `/trades` endpoint?
   - What fields do trades have?

---

## Quick Comparison Table

| Player | ID | Should Be In | Currently Shows In (GW20 JSON) |
|--------|----|--------------|---------------------------------|
| Saliba | 6  | Yoni (827066) | Hapoel Eliyahu (822133) |
| Gabriel | 5 | You (830139) | Johnny (827066) |

**If GW22 API shows the "Should Be In" column, the trade is reflected! ✅**

---

## After You Share Data:

I will:
1. ✅ Confirm current squad API structure
2. ✅ Identify where trades are stored (if at all)
3. ✅ Update bookmarklet to fetch correctly
4. ✅ Update importer to parse correctly
5. ✅ Test with your data
6. ✅ Verify Saliba/Gabriel trade is synced

---

**Pick whichever method is easiest for you and share the output!** 🚀

The Console method (Method 2) is fastest and will give me everything I need in one go.
