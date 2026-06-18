"""READ-ONLY DefCon coverage audit for a GW. No writes.

For each fixture in the GW: lock state, scoring source mix, and how many of its
DEF/MID players carry a DefCon line (defConActions present) vs none. A fixture
whose DEF/MID players are ESPN-sourced (no defensive components) never had
DefCon fetched.

Run: FS_TOKEN=$(gcloud auth print-access-token) .venv/bin/python scripts/validate_defcon_gw1.py [GW]
"""
import os, sys
from google.oauth2.credentials import Credentials
from google.cloud import firestore

PROJECT, DATABASE = "fpl-analyzer-792eb", "gamedb"
GW = int(sys.argv[1]) if len(sys.argv) > 1 else 1

tok = os.environ["FS_TOKEN"]
db = firestore.Client(project=PROJECT, credentials=Credentials(token=tok), database=DATABASE)

# pool positions: pid -> pos (2=DEF, 3=MID need DefCon)
pos = {}
for d in db.collection("wc_players").stream():
    p = d.to_dict() or {}
    try:
        pos[int(d.id)] = p.get("position", 3)
    except (TypeError, ValueError):
        pass

POS_NAME = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
fixtures = list(db.collection("wc_fixtures").where("gw", "==", GW).stream())
print(f"\n=== GW{GW}: {len(fixtures)} fixtures ===\n")

total_missing = 0
for fx in sorted(fixtures, key=lambda d: d.id):
    f = fx.to_dict() or {}
    h = (f.get("homeTeam", {}) or {}).get("isoCode", "?")
    a = (f.get("awayTeam", {}) or {}).get("isoCode", "?")
    hn = (f.get("homeTeam", {}) or {}).get("name", h)
    an = (f.get("awayTeam", {}) or {}).get("name", a)
    locked = bool(f.get("dataLocked"))
    status = f.get("status", "?")
    wss = f.get("whoscoredScored")

    ps = list(fx.reference.collection("playerScores").stream())
    src = {}
    defmid_total = defmid_withdc = 0
    for d in ps:
        r = d.to_dict() or {}
        src[r.get("source", "?")] = src.get(r.get("source", "?"), 0) + 1
        try:
            pid = int(d.id)
        except (TypeError, ValueError):
            continue
        if pos.get(pid) in (2, 3):
            defmid_total += 1
            if r.get("defConActions") is not None:
                defmid_withdc += 1

    gap = defmid_total - defmid_withdc
    flag = ""
    if not locked and defmid_total > 0 and defmid_withdc == 0:
        flag = "  <<< NO DEFCON AT ALL"
        total_missing += 1
    elif not locked and gap > 0:
        flag = f"  <<< partial: {gap} DEF/MID without DefCon"
        total_missing += 1

    lock_s = "LOCKED" if locked else "unlocked"
    print(f"{fx.id}  {hn} v {an}  [{status}, {lock_s}, wss={wss}]")
    print(f"    playerScores={len(ps)}  sources={src}  "
          f"DEF/MID with DefCon: {defmid_withdc}/{defmid_total}{flag}")

print(f"\n=== {total_missing} unlocked fixture(s) with missing/partial DefCon ===")
