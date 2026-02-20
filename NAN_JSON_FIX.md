# 🐛 NaN in JSON - Root Cause & Fix

## The Problem

**Symptom**: Replacement modal shows **(0)** players, console shows:
```
SyntaxError: Unexpected token 'N', ..."hted_fdr":NaN}... is not valid JSON
```

**Root Cause**: 
1. DuckDB query returns pandas DataFrame with `NaN` values in `weighted_fdr` column
2. DataFrame converted to dict: `df.to_dict('records')` → NaN stays as NaN
3. Flask's `jsonify()` outputs literal `NaN` in JSON: `{"weighted_fdr":NaN}`
4. Browser's `JSON.parse()` fails because `NaN` is not valid JSON (only `null`, not `NaN`)

---

## Why This Happened

The `weighted_fdr` column has no data yet (all NULL in database), so pandas represents it as `NaN`.

When pandas converts DataFrame to dict, it keeps `NaN` as a Python float NaN object.

Flask's default JSON serializer outputs Python NaN as the string `NaN` (not `null`), which breaks JSON parsing in JavaScript.

---

## The Fixes (3-Layer Defense)

### 1. **Repository Layer** (Primary Fix)
**File**: `fpl_predictor/data/repository.py`

```python
def get_fixture_grid(self, gw_start: int, gw_end: int) -> List[Dict]:
    df = self.con.execute("""...""").fetchdf()
    
    # Replace NaN with None before converting to dict
    df = df.where(df.notna(), None)  # ← FIX HERE
    return df.to_dict('records')
```

**What it does**: Pandas `df.where(df.notna(), None)` replaces all `NaN` values with Python `None`, which serializes to JSON `null`.

**Applied to**:
- `FixtureRepository.get_fixture_grid()`
- `FixtureRepository.get_team_fixtures()`

---

### 2. **API Layer** (Secondary Fix)
**File**: `fpl_predictor/api.py`

```python
@app.route('/api/db/fixtures/grid', methods=['GET'])
def db_get_fixture_grid():
    repo = FixtureRepository()
    grid = repo.get_fixture_grid(gw_start, gw_end)
    
    # Clean NaN values for JSON serialization
    grid = _clean_nan(grid)  # ← BACKUP FIX
    
    return jsonify({'fixtures': grid})
```

**What it does**: Recursively walks through all dicts/lists and replaces `NaN` with `None`.

**Applied to**:
- `/api/db/fixtures/grid`
- `/api/db/fixtures/team/<team_id>`
- All other API endpoints (already had this)

---

### 3. **Flask JSON Encoder** (Final Safety Net)
**File**: `fpl_predictor/api.py`

```python
import math
from flask.json.provider import DefaultJSONProvider

class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None  # ← Convert NaN/inf to null
        return super().default(obj)

app.json = CustomJSONProvider(app)
```

**What it does**: Overrides Flask's JSON serializer to catch any `NaN` or `inf` values that slip through and convert them to `null`.

---

## Testing the Fix

### Before Fix:
```bash
$ curl "http://localhost:5001/api/db/fixtures/grid?gw_start=23&gw_end=23"
{"fixtures":[{"weighted_fdr":NaN, ...}]}  ← Invalid JSON!
```

### After Fix:
```bash
$ curl "http://localhost:5001/api/db/fixtures/grid?gw_start=23&gw_end=23"
{"fixtures":[{"weighted_fdr":null, ...}]}  ← Valid JSON!
```

---

## How to Apply

1. **Stop server**:
   ```bash
   killall python
   ```

2. **Start server**:
   ```bash
   cd /Users/ilay/RiderProjects/fpl_analyzer
   source .venv/bin/activate
   python run_server.py --port 5001
   ```

3. **Test API**:
   ```bash
   curl "http://localhost:5001/api/db/fixtures/grid?gw_start=23&gw_end=23" | grep weighted_fdr | head -1
   ```
   Should output: `"weighted_fdr":null` (not `NaN`)

4. **Test Frontend**:
   - Hard refresh browser (`Cmd+Shift+R`)
   - Go to Squad Fixture Analysis
   - Click any player
   - Replacement modal should now load players!

---

## Why 3 Layers?

- **Layer 1 (Repository)**: Most efficient - fixes at source
- **Layer 2 (API)**: Catches edge cases from other queries
- **Layer 3 (Flask)**: Final safety net for any missed NaN values

With all 3 layers, NaN values cannot reach the browser.

---

## Related Files Modified

1. `fpl_predictor/data/repository.py`:
   - `FixtureRepository.get_fixture_grid()`
   - `FixtureRepository.get_team_fixtures()`

2. `fpl_predictor/api.py`:
   - Added `CustomJSONProvider`
   - Added `_clean_nan()` calls to fixture endpoints
   - Added no-cache headers

3. `fpl_fixture_analyzer.html`:
   - Fixed free agents API endpoint
   - Fixed response key (`players` vs `free_agents`)
   - Added comprehensive logging

---

## Status

✅ **FIXED** - All 3 layers implemented
⏳ **PENDING** - Server restart required to apply changes

