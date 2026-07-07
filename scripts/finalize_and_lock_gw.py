"""Finalize + lock a GW for the real league (AUTHORIZED prod mutation).

Order (see .claude/skills/gw-end-validations Step 4):
  1. Snapshot before-state.
  2. Set processedForFantasy on every GW fixture WITHOUT re-scoring (our
     WhoScored/FIFA playerScores are already authoritative; running the legacy
     process_fixture would clobber DefCon).
  3. finalize_gw  -> auto-subs, H2H (W3/D1/L0) + '+1 מצטיין מחזור' bonus,
     standings, lock lineups, advance currentGw, transfer-window audit doc.
  4. Set dataLocked on every GW fixture (freeze the data; no code path otherwise).
  5. reset_waiver_priority_to_standings so the next wishlist order is last-first.
  6. Print after-state.

Run: FS_TOKEN=$(...SA...) .venv/bin/python scripts/finalize_and_lock_gw.py <gw> [lid]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google.oauth2.credentials import Credentials
from google.cloud import firestore

PROJECT, DATABASE = "fpl-analyzer-792eb", "gamedb"
GW = int(sys.argv[1]) if len(sys.argv) > 1 else 1
LID = sys.argv[2] if len(sys.argv) > 2 else "lg_mock_draft"
db = firestore.Client(project=PROJECT, credentials=Credentials(token=os.environ["FS_TOKEN"]), database=DATABASE)

from fpl_predictor.game.wc_scoring import finalize_gw
from fpl_predictor.data.wc_api import WC2026Client
from fpl_predictor.game.wc_waivers import WCWaiverManager

lref = db.collection("leagues").document(LID)
league = lref.get().to_dict() or {}
admin = league.get("adminUid")
print(f"league={LID} currentGw={league.get('currentGw')} admin={admin}")

# 1. before
sc_before = lref.collection("scores").document(str(GW)).get().to_dict() or {}
res_before = {u: v.get("points") for u, v in (sc_before.get("results") or {}).items()}
print("before points:", res_before)

# 2. processedForFantasy (no re-score)
fixtures = list(db.collection("wc_fixtures").where("gw", "==", GW).stream())
for fx in fixtures:
    fx.reference.set({"processedForFantasy": True}, merge=True)
print(f"marked processedForFantasy on {len(fixtures)} fixtures (no re-score)")

# 3. finalize  (wc_client unused for group-phase GW1; safe to construct)
result = finalize_gw(LID, GW, db, WC2026Client(db=db))
print("finalize_gw:", result)

# 4. dataLocked
for fx in fixtures:
    fx.reference.set({"dataLocked": True}, merge=True)
print(f"set dataLocked on {len(fixtures)} fixtures")

# 5. reset waiver priority from new standings — LEAGUE PHASE ONLY.
#    Entering the knockout (GW == knockoutStartGw-1) and each knockout round set
#    SEED-order pick priority inside seed_knockout / advance_knockout_bracket;
#    the reverse-standings reset would clobber it, so skip it from then on.
ks = league.get("knockoutStartGw", 7)
if GW < ks - 1:
    try:
        WCWaiverManager(db, WC2026Client(db=db)).reset_waiver_priority_to_standings(LID, admin)
        print("waiver priority reset to reverse-standings")
    except Exception as e:
        print("waiver reset FAILED:", repr(e))
else:
    print(f"skipped waiver reset (GW{GW} ≥ knockoutStartGw-1={ks-1}: knockout engine sets seed-order pick priority)")

# 6. after
sc_after = lref.collection("scores").document(str(GW)).get().to_dict() or {}
res_after = {u: v.get("points") for u, v in (sc_after.get("results") or {}).items()}
h2h = sc_after.get("h2hResults") or {}
st = lref.collection("standings").document("current").get().to_dict() or {}
print("\nafter points:", res_after)
print("changed by auto-subs:", {u: (res_before.get(u), res_after.get(u)) for u in res_after if res_before.get(u) != res_after.get(u)} or "none")
print("h2hResults:", {u: h2h[u].get("result") for u in h2h})
print("standings:")
for m in st.get("managers", []):
    print(f"  #{m.get('rank')} {m['uid']:11} hpts={m.get('hpts')} fpts={m.get('fpts')} bonus={m.get('bonusPoints')}")
print("currentGw now:", (lref.get().to_dict() or {}).get("currentGw"))
print("waiverPriority now:", {m.id: (m.to_dict() or {}).get("waiverPriority") for m in lref.collection("members").stream()})
