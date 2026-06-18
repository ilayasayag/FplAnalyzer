"""READ-ONLY deep DefCon inspection for unlocked fixtures in a GW. No writes.

For each UNLOCKED fixture, for its DEF/MID players show:
  - defConActions value, defConBonus, whether stats still carry the raw
    defensive components (tackles/interceptions/blocks/clearances/ballRecoveries)
  - whether the breakdown has a "Defensive contribution" line
Then flag fixtures whose DEF/MID DefCon is all-zero or whose stats lost the
components (so a re-parse from WhoScored is needed to be sure).

Run: FS_TOKEN=$(...) .venv/bin/python scripts/inspect_defcon_detail.py [GW]
"""
import os, sys
from google.oauth2.credentials import Credentials
from google.cloud import firestore

PROJECT, DATABASE = "fpl-analyzer-792eb", "gamedb"
GW = int(sys.argv[1]) if len(sys.argv) > 1 else 1
tok = os.environ["FS_TOKEN"]
db = firestore.Client(project=PROJECT, credentials=Credentials(token=tok), database=DATABASE)

pos, name = {}, {}
for d in db.collection("wc_players").stream():
    p = d.to_dict() or {}
    try:
        pid = int(d.id)
    except (TypeError, ValueError):
        continue
    pos[pid] = p.get("position", 3)
    name[pid] = p.get("name", str(pid))

POS_NAME = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def has_components(st):
    tk = st.get("tackles") or {}
    return any([
        st.get("clearances"), st.get("ballRecoveries"), st.get("defCon"),
        tk.get("total"), tk.get("interceptions"), tk.get("blocks"),
    ])


fixtures = list(db.collection("wc_fixtures").where("gw", "==", GW).stream())
flagged = []
for fx in sorted(fixtures, key=lambda d: d.id):
    f = fx.to_dict() or {}
    if f.get("dataLocked"):
        continue
    h = (f.get("homeTeam", {}) or {}).get("isoCode", "?")
    a = (f.get("awayTeam", {}) or {}).get("isoCode", "?")
    ps = list(fx.reference.collection("playerScores").stream())
    rows = []
    nonzero_actions = 0
    bonus_sum = 0
    lost_components = 0
    src = {}
    for d in ps:
        r = d.to_dict() or {}
        src[r.get("source")] = src.get(r.get("source"), 0) + 1
        try:
            pid = int(d.id)
        except (TypeError, ValueError):
            continue
        if pos.get(pid) not in (2, 3):
            continue
        dca = r.get("defConActions")
        dcb = r.get("defConBonus", 0) or 0
        st = r.get("stats") or {}
        comp = has_components(st)
        if dca:
            nonzero_actions += 1
        bonus_sum += dcb
        if not comp:
            lost_components += 1
        rows.append((POS_NAME[pos[pid]], name.get(pid, pid), dca, dcb, comp))

    print(f"\n{fx.id}  {h} v {a}  sources={src}")
    print(f"    DEF/MID: {len(rows)}  | with defConActions>0: {nonzero_actions}"
          f"  | bonus players(Σpts): {bonus_sum}  | stats-lost-components: {lost_components}")
    # show top actions
    for posn, nm, dca, dcb, comp in sorted(rows, key=lambda x: -(x[2] or 0))[:6]:
        c = "comp" if comp else "NO-comp"
        print(f"      {posn:3} {str(nm)[:22]:22} actions={dca}  bonus={dcb}  stats:{c}")

    if nonzero_actions == 0:
        flagged.append((fx.id, f"{h} v {a}", "ALL defConActions == 0/None"))
    elif lost_components == len(rows) and rows:
        flagged.append((fx.id, f"{h} v {a}", "DefCon preserved but stats lost raw components"))

print("\n=== FLAGGED (worth a WhoScored re-parse) ===")
for fid, m, why in flagged:
    print(f"  {fid} {m}: {why}")
if not flagged:
    print("  none — every unlocked fixture has real, non-zero DefCon with components")
