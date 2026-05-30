#!/usr/bin/env python3
import os
import sys
import firebase_admin
from firebase_admin import credentials, auth, firestore

print("🚀 Starting Production Database Hydration & League Seeding script...")

# 1. Read existing hydrated players and teams from local Emulator (database: gamedb)
print("📥 Reading players and teams from Firestore Emulator...")
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
emulator_app = firebase_admin.initialize_app(
    options={"projectId": "fpl-analyzer-792eb"},
    name="emulator"
)
emulator_db = firestore.client(app=emulator_app, database_id="gamedb")

try:
    teams = [d.to_dict() for d in emulator_db.collection("wc_teams").get()]
    players = [d.to_dict() for d in emulator_db.collection("wc_players").get()]
    print(f"✅ Loaded {len(teams)} teams and {len(players)} players from emulator.")
except Exception as e:
    print(f"❌ Failed to load from emulator: {e}")
    sys.exit(1)

# Clean up emulator env variables for production init
del os.environ["FIRESTORE_EMULATOR_HOST"]
if "FIREBASE_AUTH_EMULATOR_HOST" in os.environ:
    del os.environ["FIREBASE_AUTH_EMULATOR_HOST"]

# 2. Connect to Production Firestore (database: gamedb)
print("📤 Connecting to Production Firebase (fpl-analyzer-792eb)...")
production_app = firebase_admin.initialize_app(
    options={"projectId": "fpl-analyzer-792eb"},
    name="production"
)
production_db = firestore.client(app=production_app, database_id="gamedb")

# Write teams to production
print("🌱 Writing 48 qualified teams to production wc_teams...")
for t in teams:
    production_db.collection("wc_teams").document(str(t["id"])).set(t)

# Write players to production
print("🌱 Writing 857 players to production wc_players...")
for p in players:
    production_db.collection("wc_players").document(str(p["id"])).set(p)

print("✅ Successfully hydrated players and teams in production!")

# 3. Retrieve authenticated production users to seed personal mock league
print("👤 Checking production Auth users list...")
try:
    auth_users = auth.list_users(app=production_app).users
    user_list = [u for u in auth_users]
    if user_list:
        real_user = user_list[0]
        USER_UID = real_user.uid
        USER_NAME = real_user.display_name or real_user.email.split("@")[0]
        print(f"🎯 Found production user: {USER_NAME} (UID: {USER_UID})")
    else:
        USER_UID = "u_me"
        USER_NAME = "Ilay (you)"
        print("⚠️ No production user found. Defaulting to 'u_me'.")
except Exception as e:
    USER_UID = "u_me"
    USER_NAME = "Ilay (you)"
    print(f"⚠️ Failed to list auth users ({e}). Defaulting to 'u_me'.")

# 4. Seed League 1: Mock Draft League (7 Managers, Knockout phase, MD3 complete)
MOCK_LID = "lg_mock_draft"
print(f"🏆 Seeding League 1: Mock Draft League (ID: {MOCK_LID}, Code: MOCKWC26)...")

mock_managers = [
    {"uid": "u_roy",     "name": "Roy",       "team": "La Liga Loca",     "flag": "ESP", "draftPos": 1, "waiverPri": 6},
    {"uid": "u_yonatan", "name": "Yonatan",   "team": "Tiki-Taka FC",     "flag": "ARG", "draftPos": 2, "waiverPri": 5},
    {"uid": "u_nadav",   "name": "Nadav",     "team": "Red Devils 2026", "flag": "BRA", "draftPos": 3, "waiverPri": 4},
    {"uid": "u_yuval",   "name": "Yuval",     "team": "The Gunners",      "flag": "ENG", "draftPos": 4, "waiverPri": 3},
    {"uid": "u_ido",     "name": "Ido",       "team": "Tel Aviv United",  "flag": "FRA", "draftPos": 5, "waiverPri": 2},
    {"uid": "u_shai",    "name": "Shai",      "team": "McShaike's XI",   "flag": "MEX", "draftPos": 6, "waiverPri": 1},
    {"uid": USER_UID,    "name": USER_NAME,   "team": "Hapoel Eliyahu",   "flag": "POR", "draftPos": 7, "waiverPri": 7},
]

# Set top-level League document
production_db.collection("leagues").document(MOCK_LID).set({
    "leagueId": MOCK_LID,
    "name": "El Clásico Friends (Mock)",
    "inviteCode": "MOCKWC26",
    "adminUid": "u_roy",
    "format": "h2h",
    "status": "knockout",
    "maxMembers": 7,
    "pickTimer": 60,
    "tradeApproval": "vote",
    "knockoutStartGw": 7,
    "leaguePhaseGws": [1, 2, 3, 4, 5, 6],
    "knockoutQualifiers": 4,
    "currentGw": 7,
    "draftAt": None,
    "seasonStartedAt": None,
    "createdAt": firestore.SERVER_TIMESTAMP,
})

# Set members
for m in mock_managers:
    production_db.collection("leagues").document(MOCK_LID).collection("members").document(m["uid"]).set({
        "displayName": m["name"],
        "teamName": m["team"],
        "draftPosition": m["draftPos"],
        "waiverPriority": m["waiverPri"],
        "joinedAt": firestore.SERVER_TIMESTAMP,
    })

# Set Standings (Real user at Rank 7, Seed #7)
standings_data = {
    "managers": [
        {"uid": "u_roy",     "rank": 1, "hw": 5, "hd": 0, "hl": 1, "hpts": 15, "fpts": 382, "mv": 0, "bonusPoints": 12},
        {"uid": "u_yonatan", "rank": 2, "hw": 4, "hd": 0, "hl": 2, "hpts": 12, "fpts": 361, "mv": 1, "bonusPoints": 10},
        {"uid": "u_ido",     "rank": 3, "hw": 3, "hd": 0, "hl": 3, "hpts": 9,  "fpts": 368, "mv": 0, "ptsSeed": True, "bonusPoints": 9},
        {"uid": "u_nadav",   "rank": 4, "hw": 3, "hd": 0, "hl": 3, "hpts": 9,  "fpts": 354, "mv": -1, "knockedOut": True, "bonusPoints": 8},
        {"uid": "u_yuval",   "rank": 5, "hw": 2, "hd": 0, "hl": 4, "hpts": 6,  "fpts": 340, "mv": 1, "knockedOut": True, "bonusPoints": 7},
        {"uid": "u_shai",    "rank": 6, "hw": 1, "hd": 0, "hl": 5, "hpts": 3,  "fpts": 310, "mv": -1, "knockedOut": True, "bonusPoints": 5},
        {"uid": USER_UID,    "rank": 7, "hw": 3, "hd": 0, "hl": 3, "hpts": 9,  "fpts": 379, "mv": -2, "ptsSeed": True, "bonusPoints": 15},
    ]
}
production_db.collection("leagues").document(MOCK_LID).collection("standings").document("current").set(standings_data)

# Set Squads (Pre-seeded player rosters from recommended players list)
squad_players = {
    USER_UID: [
        "p_costa", "p_donnarumma", "p_dias", "p_kounde", "p_walker", "p_hakimi", 
        "p_canc", "p_bruno", "p_bellingham", "p_musiala", "p_yamal", "p_zielinski", 
        "p_ronaldo", "p_mbappe", "p_kane"
    ],
    "u_roy": ["p_martinez", "p_verbruggen", "p_cucurella", "p_dumfries", "p_tagliafico", "p_wirtz", "p_olise", "p_de_bruyne", "p_saka", "p_foden", "p_oyarzabal", "p_havertz", "p_gyokeres"],
    "u_yonatan": ["p_rochet", "p_nyland", "p_romero", "p_kimmich", "p_muñoz", "p_palmer", "p_williams", "p_griezmann", "p_guler", "p_rice", "p_messi", "p_gakpo", "p_david"],
}

for uid, p_ids in squad_players.items():
    squad_list = [{"playerId": pid, "draftedRound": 1} for pid in p_ids]
    production_db.collection("leagues").document(MOCK_LID).collection("squads").document(uid).set({
        "players": squad_list
    })

# Set Lineup for GW3 (Starting XI / Bench / formation)
lineup_data = {
    "starting": [
        "p_costa", "p_dias", "p_kounde", "p_walker", "p_hakimi", 
        "p_bruno", "p_bellingham", "p_musiala", "p_yamal", "p_ronaldo", "p_mbappe"
    ],
    "bench": ["p_donnarumma", "p_canc", "p_zielinski", "p_kane"],
    "formation": [1, 4, 4, 2],
    "captain": "p_kane",
    "viceCaptain": "p_mbappe",
    "locked": True,
    "autoSubsMade": [{"in": "p_ronaldo", "out": "p_kane"}]
}
production_db.collection("leagues").document(MOCK_LID).collection("lineups").document(f"{USER_UID}_3").set(lineup_data)

# Set GW3 Scores
scores_data = {
    "processed": True,
    "processedAt": firestore.SERVER_TIMESTAMP,
    "results": {
        USER_UID: {"points": 65},
        "u_roy": {"points": 58},
        "u_yonatan": {"points": 70},
    }
}
production_db.collection("leagues").document(MOCK_LID).collection("scores").document("3").set(scores_data)

# Set Knockout Bracket QF matchup previews
bracket_data = {
    "seeds": [
        {"uid": "u_roy", "seed": 1},
        {"uid": "u_yonatan", "seed": 2},
        {"uid": USER_UID, "seed": 3},
        {"uid": "u_ido", "seed": 4},
    ],
    "rounds": {
        "sf": [
            {"id": "sf1", "home": "u_roy", "away": "u_ido", "homeSeed": 1, "awaySeed": 4, "gw": 7},
            {"id": "sf2", "home": "u_yonatan", "away": USER_UID, "homeSeed": 2, "awaySeed": 3, "gw": 7},
        ],
        "final": [
            {"id": "f1", "home": None, "away": None, "homeSrc": "sf1", "awaySrc": "sf2", "gw": 8}
        ]
    }
}
production_db.collection("leagues").document(MOCK_LID).collection("knockout").document("bracket").set(bracket_data)


# 5. Seed League 2: Real Pre-Draft League (7 Managers, Pre-draft countdown)
PRE_LID = "lg_pre_draft"
print(f"📅 Seeding League 2: Real Pre-Draft League (ID: {PRE_LID}, Code: REALWC26)...")

production_db.collection("leagues").document(PRE_LID).set({
    "leagueId": PRE_LID,
    "name": "World Cup Real Draft (7 Managers)",
    "inviteCode": "REALWC26",
    "adminUid": "u_roy",
    "format": "h2h",
    "status": "pre_draft",
    "maxMembers": 7,
    "pickTimer": 90,
    "tradeApproval": "vote",
    "knockoutStartGw": 7,
    "leaguePhaseGws": [1, 2, 3, 4, 5, 6],
    "knockoutQualifiers": 4,
    "currentGw": None,
    "draftAt": "2026-06-08T18:00:00Z",
    "seasonStartedAt": None,
    "createdAt": firestore.SERVER_TIMESTAMP,
})

# Seed 6 mock managers so there is exactly 1 slot left for the real user to join!
for m in mock_managers[:6]:
    production_db.collection("leagues").document(PRE_LID).collection("members").document(m["uid"]).set({
        "displayName": m["name"],
        "teamName": m["team"],
        "draftPosition": m["draftPos"],
        "waiverPriority": m["waiverPri"],
        "joinedAt": firestore.SERVER_TIMESTAMP,
    })

print("\n✨ ALL SEEDING PROCEDURES COMPLETED SUCCESSFULLY!")
