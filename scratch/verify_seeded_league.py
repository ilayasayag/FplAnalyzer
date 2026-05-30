import os
import json
import sys
import firebase_admin
from firebase_admin import credentials, firestore

# Connect to production database using secrets.json
secrets_path = "secrets.json"
if os.path.exists(secrets_path):
    try:
        cred = credentials.Certificate(secrets_path)
        firebase_admin.initialize_app(cred, options={"projectId": "fpl-analyzer-792eb"})
    except Exception as e:
        try:
            firebase_admin.initialize_app(options={"projectId": "fpl-analyzer-792eb"})
        except Exception as e2:
            pass
else:
    print("secrets.json not found!")
    sys.exit(1)

db = firestore.client(database_id="gamedb")
mock_lid = "lg_mock_draft"

print("🔍 Validating seeded Mock League...")

# 1. Verify League Metadata
league_doc = db.collection("leagues").document(mock_lid).get()
if not league_doc.exists:
    print("❌ League document lg_mock_draft not found!")
    sys.exit(1)
ld = league_doc.to_dict()
print(f"✅ League Name: {ld.get('name')}")
print(f"✅ Invite Code: {ld.get('inviteCode')}")
print(f"✅ Status: {ld.get('status')}")
print(f"✅ Current GW: {ld.get('currentGw')}")
print(f"✅ leaguePhaseGws: {ld.get('leaguePhaseGws')}")
print(f"✅ knockoutStartGw: {ld.get('knockoutStartGw')}")

# 2. Verify Members
members = list(db.collection("leagues").document(mock_lid).collection("members").get())
print(f"✅ Number of Managers: {len(members)} (expected: 8)")
if len(members) != 8:
    print("❌ Managers count is not 8!")
    sys.exit(1)

# 3. Verify Squad Roster & Positions for all managers
squad_docs = db.collection("leagues").document(mock_lid).collection("squads").get()
qualified = True

# Load players database to check positions
json_path = os.path.join(os.path.dirname(__file__), "..", "fpl_predictor", "data", "wc_seeded_data.json")
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)
player_map = {str(p["id"]): p for p in data["players"]}

for sd in squad_docs:
    uid = sd.id
    players = sd.to_dict().get("players", [])
    print(f"👤 Manager UID {uid}: Roster size = {len(players)}")
    if len(players) != 15:
        print(f"   ❌ Roster size is {len(players)} instead of 15!")
        qualified = False
        
    pos_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for p in players:
        pid = str(p["playerId"])
        if pid in player_map:
            pos_counts[player_map[pid]["position"]] += 1
        else:
            print(f"   ❌ Player {pid} not found in players database!")
            qualified = False
            
    print(f"   Positions: GK={pos_counts[1]}, DEF={pos_counts[2]}, MID={pos_counts[3]}, FWD={pos_counts[4]}")
    if pos_counts[1] != 2 or pos_counts[2] != 5 or pos_counts[3] != 5 or pos_counts[4] != 3:
        print(f"   ❌ Roster positions do not match 2-5-5-3!")
        qualified = False

# 4. Verify Bracket
bracket_doc = db.collection("leagues").document(mock_lid).collection("knockout").document("bracket").get()
if bracket_doc.exists:
    bd = bracket_doc.to_dict()
    print("✅ Knockout Bracket Seeds:")
    for seed in bd.get("seeds", []):
        print(f"   Seed #{seed['seed']}: {seed['uid']}")
    print("✅ Semi-Final Matchups:")
    for match in bd.get("rounds", {}).get("sf", []):
        print(f"   Match {match['id']}: {match['home']} vs {match['away']} (GW {match['gw']})")
else:
    print("❌ Bracket document not found!")
    qualified = False

if qualified:
    print("🎉 ALL MOCK LEAGUE VERIFICATION CHECKS PASSED PERFECTLY!")
else:
    print("❌ SOME VERIFICATION CHECKS FAILED.")
    sys.exit(1)
