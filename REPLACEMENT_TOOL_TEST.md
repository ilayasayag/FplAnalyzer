# 🔧 REPLACEMENT TOOL - TEST GUIDE

## ✅ What Was Fixed

### Before (Broken):
- ❌ JavaScript error: `filteredPlayers.slice is not a function`
- ❌ Confusing UI: Checkbox + "Replace" button
- ❌ No score impact shown
- ❌ Recommendations were generic free agents
- ❌ No way to see which replacement improves squad

### After (Working):
- ✅ Array validation & error handling
- ✅ Single click on player → opens modal
- ✅ Real score impact calculated
- ✅ Ranked by squad improvement
- ✅ Filter tabs: Free Agents | From Manager | All Players
- ✅ Loading states
- ✅ Batch replace mode (placeholder for now)

---

## 🎯 New User Flow

```
1. Open "Squad Fixture Analysis" tab
2. Select manager (e.g., "yr")
3. Choose GW range (e.g., 23-27)
4. Click "Analyze"
   ↓
5. See "Your Current Squad" section
6. Click ANY player card (e.g., Fofana)
   ↓
7. Modal opens with:
   - "Replace Fofana" header
   - Search bar
   - 3 filter tabs
   - Loading: "Calculating score impacts..."
   ↓
8. See ranked list:
   #1 Gabriel    +0.45  ← Best improvement
   #2 Saliba     +0.32
   #3 Timber     +0.21
   ...
   #10 SomePlayer -0.30  ← Would make squad worse
   ↓
9. Click a player (e.g., #1 Gabriel)
   ↓
10. Confirmation dialog:
    "Replace Fofana (Avg: 1.40) with Gabriel (Avg: 1.85)?
     Impact: +0.45 improvement ✅"
    ↓
11. Click "OK" → Analysis refreshes
```

---

## 🧪 Test Cases

### Test 1: Basic Replacement
1. Click on Fofana (CHE | DEF)
2. Modal should open instantly
3. Should show "Calculating score impacts..." for 1-2 seconds
4. Should display ranked list of defenders
5. Top ranked should have positive impact if they have better fixtures

### Test 2: Search Filter
1. Open replacement modal
2. Type "Gabriel" in search bar
3. List should filter to only Gabriel (if exists)
4. Clear search → full list returns

### Test 3: Filter Tabs
1. Click "Free Agents" → should show only unowned players
2. Click "All Players" → should show entire DB (200 players)
3. Click "From Manager" → dropdown appears
4. Select a manager → should show their squad (TODO)

### Test 4: Score Impact
1. Find a player with **green** impact (e.g., +0.45)
2. Find a player with **red** impact (e.g., -0.30)
3. Verify green = better than current, red = worse

### Test 5: Apply Replacement
1. Click on a high-impact player
2. Read confirmation dialog
3. Click OK
4. Modal closes
5. Analysis section should refresh
6. Original player should be excluded from analysis

### Test 6: Batch Mode (Placeholder)
1. Click 2+ players to exclude them
2. "Find Replacements (2)" button should appear
3. Click it → shows placeholder alert
4. Future: Will open multi-player optimizer

---

## 🐛 Known Issues / TODO

- [ ] "From Manager" filter needs to fetch actual squad data
- [ ] Batch replacement is placeholder (just an alert)
- [ ] No way to "un-exclude" a player without Reset All
- [ ] Should cache fixture data to avoid re-fetching

---

## 📊 Score Calculation Logic

For each candidate player:

1. Get their team's fixtures for GW range
2. For each GW, get FDR (Fixture Difficulty Rating)
3. Classify as:
   - Easy: FDR ≤ 2.5
   - Medium: FDR 2.5-3.5  
   - Hard: FDR > 3.5
4. Apply position-specific multiplier:
   - GK: 1.5 / 1.0 / 0.0 (easy/mid/hard)
   - DEF: 1.5 / 1.0 / 0.0
   - MID: 1.5 / 1.0 / 0.5
   - FWD: 2.0 / 1.5 / 1.0
5. Average across all GWs
6. Impact = Candidate Avg - Current Player Avg
7. Sort by impact (descending)

---

## 🔄 Next Steps

1. **Hard refresh browser** (Cmd+Shift+R)
2. Test all scenarios above
3. Report any bugs you find
4. If it works: Implement proper batch optimizer

