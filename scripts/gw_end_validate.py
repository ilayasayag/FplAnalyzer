"""End-of-gameweek validation suite (READ-ONLY — never writes prod).

Runs every GW-end check and prints a pass/fail report:
  1. DefCon   — every unlocked fixture's DEF/MID carry DefCon; bonus matches the
                DEF>=10 / MID>=12 threshold; scoring invariant holds.
  2. Points   — each manager's stored scores/{gw} total == recomputed Σ(starters)
                (+captain x2) from our playerScores.
  3. Managers — a locked lineup exists per member with the right XI size; captain
                (if set) is among the starters.
  4. H2H      — from schedule/{gw} + GW points: W=3 / D=1 / L=0 plus a +1 bonus
                to the top GW scorer ('מצטיין מחזור'). If the GW is finalized we
                verify the STORED h2hResults/standings; otherwise we PREVIEW what
                finalize will produce.
  5. Wishlist — the auction pick order (wc_wishlist._ordered_managers over the
                reset waiver priority) must be LAST-PLACE-FIRST by standings.

Usage:
  FS_TOKEN=$(gcloud auth print-access-token \
      --account=firebase-adminsdk-fbsvc@fpl-analyzer-792eb.iam.gserviceaccount.com) \
      .venv/bin/python scripts/gw_end_validate.py <gw> [league_id]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google.oauth2.credentials import Credentials
from google.cloud import firestore

PROJECT, DATABASE = "fpl-analyzer-792eb", "gamedb"
GW = int(sys.argv[1]) if len(sys.argv) > 1 else 1
LID = sys.argv[2] if len(sys.argv) > 2 else "lg_mock_draft"
db = firestore.Client(project=PROJECT, credentials=Credentials(token=os.environ["FS_TOKEN"]), database=DATABASE)

PASS, FAIL = "PASS ✓", "FAIL ✗"
results = {}


def hdr(t): print(f"\n{'='*70}\n{t}\n{'='*70}")


# pool positions
pos = {}
for d in db.collection("wc_players").stream():
    p = d.to_dict() or {}
    try: pos[int(d.id)] = p.get("position", 3)
    except (TypeError, ValueError): pass

# our per-pid GW points + per-fixture lock/source
gp = {}
fixtures = list(db.collection("wc_fixtures").where("gw", "==", GW).stream())

# rules
sr = ((db.collection("wc_config").document("tournament").get().to_dict() or {}).get("rules", {}) or {}).get("scoring", {})
DCP = sr.get("defConPoints", 2); THR = {2: sr.get("defConThresholdDef", 10), 3: sr.get("defConThresholdMid", 12)}

# ---------------------------------------------------------------- 1. DefCon ---
hdr("1. DEFCON")
inv_bad = bonus_bad = null_bad = nodc_fixtures = 0
unlocked = 0
for fx in sorted(fixtures, key=lambda d: d.id):
    f = fx.to_dict() or {}
    locked = bool(f.get("dataLocked"))
    defmid = withdc = 0
    for d in fx.reference.collection("playerScores").stream():
        r = d.to_dict() or {}
        try: pid = int(d.id)
        except (TypeError, ValueError): continue
        gp[pid] = r.get("fantasyPoints", 0) or 0
        if pos.get(pid) in (2, 3):
            defmid += 1
            dca = r.get("defConActions"); dcb = r.get("defConBonus", 0) or 0
            if dca is not None: withdc += 1
            # invariant
            fifa = r.get("fifaPoints"); fb = r.get("fifaBonus", 0) or 0; fp = r.get("fantasyPoints")
            if fifa is not None and fp is not None and fp != fifa - fb + dcb: inv_bad += 1
            # bonus vs threshold
            if dca is not None and dcb != (DCP if dca >= THR[pos[pid]] else 0): bonus_bad += 1
            # null with components
            st = r.get("stats") or {}
            if (isinstance(st.get("tackles"), dict) or "defCon" in st or "ballRecoveries" in st) and dca is None:
                null_bad += 1
    if not locked:
        unlocked += 1
        if defmid and withdc == 0:
            nodc_fixtures += 1
            print(f"  {fx.id}: NO DefCon on any DEF/MID")
ok = (inv_bad == bonus_bad == null_bad == nodc_fixtures == 0)
results["DefCon"] = ok
print(f"  unlocked fixtures={unlocked}  invariant_viol={inv_bad}  bonus_mismatch={bonus_bad}"
      f"  null_defcon={null_bad}  fixtures_no_defcon={nodc_fixtures}  -> {PASS if ok else FAIL}")
print("  (deep freshness vs final WhoScored: run scripts/dryrun_defcon_compare.py)")

# ---------------------------------------------------------------- 2. Points ---
hdr("2. POINTS (stored manager totals == recomputed)")
sc = db.collection("leagues").document(LID).collection("scores").document(str(GW)).get().to_dict() or {}
res = sc.get("results") or {}
members = [m.id for m in db.collection("leagues").document(LID).collection("members").get()]
pts_bad = 0
for uid in members:
    lu = db.collection("leagues").document(LID).collection("lineups").document(f"{uid}_{GW}").get().to_dict() or {}
    start = lu.get("starting", []) or []; cap = lu.get("captain")
    recomp = sum(gp.get(int(p), 0) for p in start)
    if cap is not None and int(cap) in [int(p) for p in start]: recomp += gp.get(int(cap), 0)
    stored = res.get(uid, {}).get("points")
    if stored is not None and stored != recomp:
        pts_bad += 1; print(f"  {uid}: stored={stored} recomputed={recomp}  MISMATCH")
results["Points"] = (pts_bad == 0 and bool(res))
print(f"  managers={len(members)}  mismatches={pts_bad}  -> {PASS if results['Points'] else FAIL}"
      + ("" if res else "  (no scores doc yet)"))

# -------------------------------------------------------------- 3. Managers ---
hdr("3. MANAGERS (locked lineup, XI size, captain valid)")
mgr_bad = 0
for uid in members:
    lu = db.collection("leagues").document(LID).collection("lineups").document(f"{uid}_{GW}").get().to_dict() or {}
    start = lu.get("starting", []) or []; cap = lu.get("captain")
    issues = []
    if not lu: issues.append("no lineup")
    if len(start) != 11: issues.append(f"{len(start)} starters")
    if cap is not None and int(cap) not in [int(p) for p in start]: issues.append("captain not in XI")
    if issues:
        mgr_bad += 1; print(f"  {uid}: {', '.join(issues)}")
results["Managers"] = (mgr_bad == 0)
print(f"  members={len(members)}  with_issues={mgr_bad}  -> {PASS if results['Managers'] else FAIL}")

# ------------------------------------------------------------------- 4. H2H ---
hdr("4. H2H (W=3 D=1 L=0 + '+1 מצטיין מחזור' bonus)")
sch = db.collection("leagues").document(LID).collection("schedule").document(str(GW)).get().to_dict() or {}
matches = sch.get("matches", [])
pts_by = {u: res.get(u, {}).get("points", 0) for u in members}
exp_h2h, exp_hpts = {}, {u: 0 for u in members}
for m in matches:
    h, a = m.get("home"), m.get("away")
    hp, ap = pts_by.get(h, 0), pts_by.get(a, 0)
    if hp > ap: exp_h2h[h], exp_h2h[a] = "W", "L"; exp_hpts[h] += 3
    elif hp < ap: exp_h2h[h], exp_h2h[a] = "L", "W"; exp_hpts[a] += 3
    else: exp_h2h[h], exp_h2h[a] = "D", "D"; exp_hpts[h] += 1; exp_hpts[a] += 1
top = max(pts_by.values()) if pts_by else 0
bonus_uids = [u for u in members if pts_by.get(u, 0) == top and top > 0]
for u in bonus_uids: exp_hpts[u] += 1
finalized = bool(sc.get("processed"))
print(f"  GW finalized? {finalized}")
print("  expected H2H + bonus:")
for m in matches:
    h, a = m.get("home"), m.get("away")
    print(f"    {h}({pts_by.get(h,0)}) {exp_h2h.get(h,'?')} vs {a}({pts_by.get(a,0)}) {exp_h2h.get(a,'?')}")
print(f"  מצטיין מחזור (+1): {bonus_uids}  | expected hpts: { {u: exp_hpts[u] for u in members} }")
if finalized:
    stored_h2h = sc.get("h2hResults", {}) or {}
    st_doc = db.collection("leagues").document(LID).collection("standings").document("current").get().to_dict() or {}
    st_hpts = {m["uid"]: m.get("hpts", 0) for m in st_doc.get("managers", [])}
    h2h_ok = all(stored_h2h.get(u, {}).get("result") == exp_h2h.get(u) for u in members) and st_hpts == exp_hpts
    results["H2H"] = h2h_ok
    print(f"  stored vs expected -> {PASS if h2h_ok else FAIL}")
    if not h2h_ok: print(f"    stored hpts={st_hpts}")
else:
    results["H2H"] = None
    print("  -> PREVIEW only (run finalize_gw to apply; re-run this to verify)")

# -------------------------------------------------------------- 5. Wishlist ---
hdr("5. WISHLIST AUCTION ORDER (must be last-place-first by standings)")
st_doc = db.collection("leagues").document(LID).collection("standings").document("current").get().to_dict() or {}
mgrs = st_doc.get("managers", [])
if not mgrs:
    # preview from expected standings
    ranked = sorted(members, key=lambda u: (exp_hpts[u], pts_by.get(u, 0)), reverse=True)
    print("  (no standings yet — previewing from expected GW result)")
else:
    ranked = [m["uid"] for m in sorted(mgrs, key=lambda m: (m.get("hpts", 0), m.get("fpts", 0)), reverse=True)]
# emulate reset_waiver_priority_to_standings: worst -> wp 1
wp = {u: r for r, u in enumerate(reversed(ranked), start=1)}
# emulate wc_wishlist._ordered_managers actual sort
mem_meta = {m.id: (m.to_dict() or {}) for m in db.collection("leagues").document(LID).collection("members").get()}
actual = sorted(members, key=lambda u: (-wp[u], -(mem_meta[u].get("draftPosition", 0) or 0), u))
expected = list(reversed(ranked))  # last place first
wl_ok = (actual == expected)
results["Wishlist"] = wl_ok
print(f"  standings best->worst: {ranked}")
print(f"  ACTUAL auction order  : {actual}")
print(f"  EXPECTED (last-first) : {expected}")
print(f"  -> {PASS if wl_ok else FAIL}" + ("" if wl_ok else "   <<< ORDER INVERTED (best picks first)"))

# ----------------------------------------------------------------- summary ---
hdr("SUMMARY")
for k, v in results.items():
    tag = "PREVIEW" if v is None else (PASS if v else FAIL)
    print(f"  {k:10} {tag}")
hard_fail = any(v is False for v in results.values())
print(f"\nOVERALL: {'ISSUES FOUND' if hard_fail else 'ALL CHECKS PASS (or preview)'}")
sys.exit(1 if hard_fail else 0)
