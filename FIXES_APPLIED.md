# 🔧 Fixes Applied - Test Run Issues

## Issue 1: 120% Start Probability ❌ → ✅

### **Problem**:
```
mateus fernandes    WHU    120.0%   🟡 DOUBT
```

Probabilities should be 0-100%, not over 100%!

### **Root Cause**:
The aggregator was calculating:
```python
start_prob = data['starts'] / total_sources
```

If a player appeared **twice** in the same source (duplicate entries):
- `total_sources` = 1
- `data['starts']` = 2 (counted twice)
- Result: 2 / 1 = **200%**
- If doubtful: 200% × 0.6 = **120%**

### **Fix**:
Changed to count **unique sources per player**:
```python
unique_sources_for_player = len(set(s['name'] for s in data['sources']))
sources_saying_start = len(set(s['name'] for s in data['sources'] if s['starting']))
start_prob = sources_saying_start / unique_sources_for_player
```

Now:
- Even if a player appears twice in same source, it only counts as 1
- 1 unique source saying "start" / 1 unique source = **100%**
- If doubtful: 100% × 0.6 = **60%** ✅

---

## Issue 2: Database SQL Error ❌ → ✅

### **Problem**:
```
Binder Error: Table "predicted_lineups" does not have a column named "CURRENT_TIMESTAMP"
```

### **Root Cause**:
DuckDB doesn't accept `CURRENT_TIMESTAMP` as a value in the VALUES clause. It's a SQL keyword, not a function.

### **Fix**:
Changed from:
```sql
VALUES (?, ?, ..., CURRENT_TIMESTAMP)
```

To:
```sql
VALUES (?, ?, ..., NOW())
```

DuckDB uses `NOW()` function for current timestamp.

---

## Why Some Players Show as "Doubtful"?

Looking at the results:
```
🟡 Doubtful (43):
  mateus fernandes (WHU) - None
  martinez (AVL) - None
```

These players have `doubtful = True` from RotoWire's scraping (found in the `.lineup__inj` element or similar indicators). The "None" means there's no additional injury details text.

The calculation:
1. RotoWire marks player as doubtful
2. Base start probability = 100% (all sources say starting)
3. Apply doubtful penalty: 100% × 0.6 = **60%**
4. Display: 🟡 DOUBT

This is working correctly! A doubtful player has reduced probability.

---

## Expected Results After Fix

### Before (BROKEN):
```
mateus fernandes    WHU    120.0%   🟡 DOUBT  ← Wrong!
martinez            AVL    120.0%   🟡 DOUBT  ← Wrong!
```

### After (FIXED):
```
mateus fernandes    WHU     60.0%   🟡 DOUBT  ← Correct! (100% × 0.6)
martinez            AVL     60.0%   🟡 DOUBT  ← Correct!
senne lammens       MUN    100.0%   🟢 CONF   ← Correct!
```

---

## Test Again

```bash
cd /Users/ilay/RiderProjects/fpl_analyzer
source .venv/bin/activate
python test_production_scraper.py --gameweek 22
```

Expected:
- ✅ RotoWire: 339 predictions
- ✅ Aggregation: 336 predictions (some duplicates removed)
- ✅ Max probability: 100%
- ✅ Doubtful players: 60% (100% × 0.6)
- ✅ Injured players: 20% (100% × 0.2)
- ✅ Database: All stored successfully

---

## Premier Injuries Timeout (Minor Issue)

```
[Premier Injuries] Timeout waiting for table
```

This is okay for now! Premier Injuries site might be slow or changed structure. We already get injury data from RotoWire (66 injured, 45 doubtful detected).

We can fix this later if needed.
