"""Guarded DefCon resync for UNLOCKED fixtures: re-score each from the FINAL
full-match WhoScored line via ingest_whoscored_fixture.

SAFETY:
  * Skips dataLocked fixtures entirely (never re-touches finalized data).
  * ingest_whoscored_fixture writes ONLY on a successful parse (returns an error
    dict without writing when WhoScored yields no rows) — so a parse failure
    leaves the stored DefCon exactly as-is. Never nulls on error.
  * Per-fixture guard: if the call errors or writes 0, we log and move on.
After all fixtures: one refresh_pool_aggregates pass to recompute season +
manager totals consistently.

Run: FS_TOKEN=$(...) .venv/bin/python scripts/resync_defcon.py <gw> <fid> [fid ...]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google.oauth2.credentials import Credentials
from google.cloud import firestore

PROJECT, DATABASE = "fpl-analyzer-792eb", "gamedb"
GW = int(sys.argv[1])
FIDS = sys.argv[2:]
tok = os.environ["FS_TOKEN"]
db = firestore.Client(project=PROJECT, credentials=Credentials(token=tok), database=DATABASE)

from fpl_predictor.data.wc_live_ingest import ingest_whoscored_fixture, refresh_pool_aggregates

ws_map = (db.collection("wc_config").document("whoscored_map").get().to_dict() or {}).get("map", {})

ok, skipped = [], []
for fid in FIDS:
    fref = db.collection("wc_fixtures").document(fid)
    f = fref.get().to_dict() or {}
    if f.get("dataLocked"):
        print(f"{fid}: dataLocked — SKIP (never re-touch finalized)")
        skipped.append((fid, "locked"))
        continue
    ws_id = ws_map.get(fid)
    if not ws_id:
        print(f"{fid}: no ws id — SKIP")
        skipped.append((fid, "no-ws-id"))
        continue
    try:
        r = ingest_whoscored_fixture(db, int(ws_id), fid, GW)
    except Exception as e:
        print(f"{fid}: parse RAISED ({e!r}) — SKIP (stored DefCon left intact)")
        skipped.append((fid, "raised"))
        continue
    if not r or r.get("error") or not r.get("playerScoresWritten"):
        print(f"{fid}: no usable WhoScored data ({r}) — SKIP (stored DefCon intact)")
        skipped.append((fid, "no-data"))
        continue
    print(f"{fid}: re-scored {r['playerScoresWritten']} players from WhoScored "
          f"(ws={ws_id}, finished={r.get('meta',{}).get('finished')})")
    ok.append(fid)
    time.sleep(1.0)

print("\n--- refresh_pool_aggregates (season + manager totals) ---")
agg = refresh_pool_aggregates(db)
print("rescoredPlayers:", agg.get("rescoredPlayers"),
      "| rescoredGws:", agg.get("rescoredGws"),
      "| seasonStatsPlayers:", agg.get("seasonStatsPlayers"))

print(f"\n=== resynced: {ok} | skipped: {skipped} ===")
