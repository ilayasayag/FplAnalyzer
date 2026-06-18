"""READ-ONLY dry-run: compare a FRESH full-match WhoScored DefCon parse against
the STORED defConActions for every UNLOCKED fixture in a GW. NO writes.

For each unlocked fixture (with a mapped ws id) it parses WhoScored now (matches
are FT, so this is the authoritative final line), maps rows to our pool, and
diffs final defcon-actions vs stored. Prints per-fixture mismatches so we know
exactly which fixtures need a real resync.

Run: FS_TOKEN=$(...) .venv/bin/python scripts/dryrun_defcon_compare.py [GW]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google.oauth2.credentials import Credentials
from google.cloud import firestore

PROJECT, DATABASE = "fpl-analyzer-792eb", "gamedb"
GW = int(sys.argv[1]) if len(sys.argv) > 1 else 1
tok = os.environ["FS_TOKEN"]
db = firestore.Client(project=PROJECT, credentials=Credentials(token=tok), database=DATABASE)

from fpl_predictor.data.wc_live_ingest import (
    parse_whoscored_match, build_pool_index, match_to_pool, _defcon_actions,
)

pos, name = {}, {}
for d in db.collection("wc_players").stream():
    p = d.to_dict() or {}
    try:
        pid = int(d.id)
    except (TypeError, ValueError):
        continue
    pos[pid] = p.get("position", 3)
    name[pid] = p.get("name", str(pid))

pool = build_pool_index(db)
ws_map = (db.collection("wc_config").document("whoscored_map").get().to_dict() or {}).get("map", {})
THR = {2: 10, 3: 12}

fixtures = list(db.collection("wc_fixtures").where("gw", "==", GW).stream())
need_resync = []
for fx in sorted(fixtures, key=lambda d: d.id):
    f = fx.to_dict() or {}
    if f.get("dataLocked"):
        continue
    fid = fx.id
    h = (f.get("homeTeam", {}) or {}).get("isoCode", "?")
    a = (f.get("awayTeam", {}) or {}).get("isoCode", "?")
    ws_id = ws_map.get(fid)
    if not ws_id:
        print(f"{fid} {h} v {a}: NO ws id mapped — skip")
        continue

    try:
        meta, rows = parse_whoscored_match(int(ws_id))
    except Exception as e:
        print(f"{fid} {h} v {a}: WhoScored parse FAILED ({e!r}) — leave stored as-is")
        continue
    if not rows:
        print(f"{fid} {h} v {a}: WhoScored returned no rows — leave stored as-is")
        continue

    side_iso = {"home": h, "away": a}
    # fresh defcon by pid
    fresh = {}
    for row in rows:
        iso = side_iso.get(row["side"])
        pid = match_to_pool(row["name"], iso, pool)
        if pid is None or pos.get(pid) not in (2, 3):
            continue
        fresh[pid] = _defcon_actions(row["stats"], pos[pid]) or 0

    # stored defcon by pid
    stored = {}
    for d in fx.reference.collection("playerScores").stream():
        r = d.to_dict() or {}
        try:
            pid = int(d.id)
        except (TypeError, ValueError):
            continue
        if pos.get(pid) in (2, 3):
            stored[pid] = r.get("defConActions")

    diffs = []
    for pid, fdc in fresh.items():
        sdc = stored.get(pid)
        if sdc != fdc:
            # does the bonus flip? (threshold crossing is what actually matters)
            thr = THR[pos[pid]]
            flip = (((sdc or 0) >= thr) != (fdc >= thr))
            diffs.append((name.get(pid, pid), pos[pid], sdc, fdc, flip))

    fin = "FT" if meta.get("finished") else "NOT-FT(!)"
    if diffs:
        need_resync.append(fid)
        print(f"\n{fid} {h} v {a}  [WhoScored:{fin}]  {len(diffs)} mismatch(es):")
        for nm, p, sdc, fdc, flip in sorted(diffs, key=lambda x: -abs((x[3] or 0) - (x[2] or 0))):
            tag = "  <<< BONUS FLIPS" if flip else ""
            print(f"    {'DEF' if p==2 else 'MID'} {str(nm)[:22]:22} stored={sdc}  final={fdc}{tag}")
    else:
        print(f"{fid} {h} v {a}  [WhoScored:{fin}]  stored DefCon already matches final ✓")
    time.sleep(1.0)  # be polite to WhoScored

print("\n=== fixtures needing resync:", need_resync or "NONE", "===")
