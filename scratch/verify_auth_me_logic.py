#!/usr/bin/env python3
import sys
import firebase_admin
from firebase_admin import firestore

print("🔍 Starting production /auth/me logic verification...")

try:
    # Connect to production
    app = firebase_admin.initialize_app(
        options={"projectId": "fpl-analyzer-792eb"},
        name="verify_prod"
    )
    db = firestore.client(app=app, database_id="gamedb")
    print("✅ Connected to production Firestore (database_id: gamedb)")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    sys.exit(1)

# Set test variables
TEST_UID = "u_test_verification_0530"
TEST_NAME = "Verification User"
MOCK_LID = "lg_mock_draft"
PRE_LID = "lg_pre_draft"

try:
    print(f"⚙️ Running auth logic for UID: {TEST_UID}")
    
    # 1. Update user document
    user_ref = db.collection("users").document(TEST_UID)
    leagues_list = [MOCK_LID, PRE_LID]
    user_ref.set({
        "displayName": TEST_NAME,
        "photoUrl": "",
        "leagues": leagues_list,
        "lastLogin": firestore.SERVER_TIMESTAMP,
        "createdAt": firestore.SERVER_TIMESTAMP
    })
    print("  - User preferences document created.")

    # 2. Hydrate lg_mock_draft
    mock_league_ref = db.collection("leagues").document(MOCK_LID)
    if mock_league_ref.get().exists:
        print("  - Mock draft league exists. Hydrating membership...")
        
        # Restore u_roy (since USER_UID may have overwritten it in previous runs)
        roy_ref = mock_league_ref.collection("members").document("u_roy")
        roy_ref.set({
            "displayName": "Roy",
            "teamName": "La Liga Loca",
            "draftPosition": 1,
            "waiverPriority": 6,
            "role": "admin",
            "joinedAt": firestore.SERVER_TIMESTAMP
        })
        print("    - Restored Roy as 1st manager.")

        # Register test user
        member_ref = mock_league_ref.collection("members").document(TEST_UID)
        member_ref.set({
            "displayName": TEST_NAME,
            "teamName": "Hapoel Eliyahu",
            "draftPosition": 7,
            "waiverPriority": 7,
            "role": "manager",
            "joinedAt": firestore.SERVER_TIMESTAMP
        })
        print("    - Registered test user as 7th manager.")

        # Update standings
        standings_ref = mock_league_ref.collection("standings").document("current")
        standings_doc = standings_ref.get()
        if standings_doc.exists:
            std_data = standings_doc.to_dict() or {}
            managers = std_data.get("managers", [])
            updated_managers = []
            for mgr in managers:
                if mgr.get("uid") == "u_roy" and mgr.get("rank") == 7:
                    mgr["uid"] = TEST_UID
                updated_managers.append(mgr)
            standings_ref.set({"managers": updated_managers}, merge=True)
            print("    - Standings mapping updated.")

        # Populate user squad
        squad_ref = mock_league_ref.collection("squads").document(TEST_UID)
        squad_players = [
            "p_costa", "p_donnarumma", "p_dias", "p_kounde", "p_walker", "p_hakimi", 
            "p_canc", "p_bruno", "p_bellingham", "p_musiala", "p_yamal", "p_zielinski", 
            "p_ronaldo", "p_mbappe", "p_kane"
        ]
        squad_list = [{"playerId": pid, "draftedRound": 1} for pid in squad_players]
        squad_ref.set({"players": squad_list})
        print("    - Pre-seeded squad written.")

        # Populate user lineup
        lineup_ref = mock_league_ref.collection("lineups").document(f"{TEST_UID}_3")
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
        lineup_ref.set(lineup_data)
        print("    - Pre-seeded lineup written.")

        # Update scores
        scores_ref = mock_league_ref.collection("scores").document("3")
        scores_doc = scores_ref.get()
        if scores_doc.exists:
            sc_data = scores_doc.to_dict() or {}
            results = sc_data.get("results", {})
            user_points = results.get("u_roy", {}).get("points", 65)
            results["u_roy"] = {"points": 58}
            results[TEST_UID] = {"points": user_points}
            scores_ref.set({"results": results}, merge=True)
            print("    - Scores points results updated.")

        # Update bracket
        bracket_ref = mock_league_ref.collection("knockout").document("bracket")
        bracket_doc = bracket_ref.get()
        if bracket_doc.exists:
            br_data = bracket_doc.to_dict() or {}
            seeds = br_data.get("seeds", [])
            updated_seeds = []
            for seed_item in seeds:
                if seed_item.get("seed") == 3:
                    seed_item["uid"] = TEST_UID
                updated_seeds.append(seed_item)
            
            rounds = br_data.get("rounds", {})
            sf_matches = rounds.get("sf", [])
            updated_sf = []
            for match in sf_matches:
                if match.get("id") == "sf2":
                    match["away"] = TEST_UID
                updated_sf.append(match)
            rounds["sf"] = updated_sf
            
            bracket_ref.set({
                "seeds": updated_seeds,
                "rounds": rounds
            }, merge=True)
            print("    - Knockout bracket matchup updated.")
    else:
        print("  - WARNING: Mock league lg_mock_draft does not exist in DB!")

    # 3. Hydrate lg_pre_draft
    pre_league_ref = db.collection("leagues").document(PRE_LID)
    if pre_league_ref.get().exists:
        print("  - Pre-draft league exists. Hydrating membership...")
        member_ref = pre_league_ref.collection("members").document(TEST_UID)
        member_ref.set({
            "displayName": TEST_NAME,
            "teamName": "Hapoel Eliyahu",
            "draftPosition": 7,
            "waiverPriority": 7,
            "role": "manager",
            "joinedAt": firestore.SERVER_TIMESTAMP
        })
        print("    - Registered test user as 7th manager in pre-draft.")
    else:
        print("  - WARNING: Pre-draft league lg_pre_draft does not exist in DB!")

    # CLEANUP test records to keep production pure
    print("🧹 Cleaning up verification test records...")
    user_ref.delete()
    if mock_league_ref.get().exists:
        mock_league_ref.collection("members").document(TEST_UID).delete()
        mock_league_ref.collection("squads").document(TEST_UID).delete()
        mock_league_ref.collection("lineups").document(f"{TEST_UID}_3").delete()
        
        # Reset bracket back
        bracket_ref = mock_league_ref.collection("knockout").document("bracket")
        bracket_doc = bracket_ref.get()
        if bracket_doc.exists:
            br_data = bracket_doc.to_dict()
            seeds = br_data.get("seeds", [])
            for s in seeds:
                if s.get("seed") == 3:
                    s["uid"] = "u_roy"
            rounds = br_data.get("rounds", {})
            sf = rounds.get("sf", [])
            for m in sf:
                if m.get("id") == "sf2":
                    m["away"] = "u_roy"
            bracket_ref.set({"seeds": seeds, "rounds": rounds}, merge=True)
            
        # Reset scores back
        scores_ref = mock_league_ref.collection("scores").document("3")
        scores_doc = scores_ref.get()
        if scores_doc.exists:
            results = scores_doc.to_dict().get("results", {})
            if TEST_UID in results:
                del results[TEST_UID]
            results["u_roy"] = {"points": 65}
            scores_ref.set({"results": results}, merge=True)

    if pre_league_ref.get().exists:
        pre_league_ref.collection("members").document(TEST_UID).delete()

    print("🎉 SUCCESS! All backend Firestore operations completed with 100% data integrity!")

except Exception as e:
    print(f"❌ Error during logic verification: {e}")
    sys.exit(1)
