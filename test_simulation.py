#!/usr/bin/env python3
import os
import sys
import uuid
from datetime import datetime, timezone

# Point SDK exclusively to the local Firestore emulator
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = "localhost:9099"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import firebase_admin
from firebase_admin import firestore

if not firebase_admin._apps:
    firebase_admin.initialize_app(options={"projectId": "fpl-analyzer-792eb"})

db = firestore.client(database_id="gamedb")

from fpl_predictor.game.wc_scoring import finalize_gw, process_fixture
from fpl_predictor.game.wc_knockout import seed_knockout, advance_knockout_bracket, get_bracket
from fpl_predictor.game.wc_leagues import WCLeagueManager
from fpl_predictor.game.wc_squads import WCSquadManager
from fpl_predictor.game.wc_gameweeks import all_gws_as_dict, get_current_gw

# Initialize managers
league_mgr = WCLeagueManager(db)
squad_mgr = WCSquadManager(db)

def clear_emulator_db():
    print("🧹 Clearing local emulator collections...")
    for col in ["wc_teams", "wc_players", "wc_fixtures", "leagues", "users", "wc_config"]:
        docs = db.collection(col).get()
        for doc in docs:
            # Delete subcollections if any
            if col == "leagues":
                for subcol in ["members", "squads", "lineups", "scores", "schedule", "knockout", "transfer_windows", "transactions", "standings"]:
                    subdocs = doc.reference.collection(subcol).get()
                    for sdoc in subdocs:
                        sdoc.reference.delete()
            doc.reference.delete()
    print("✨ Local collections cleared.")

def populate_mock_data():
    print("🌱 Populating mock teams, players, and fixtures...")
    
    # 1. Config
    db.collection("wc_config").document("tournament").set({
        "winner": "1",        # Team 1 (Argentina)
        "topScorer": 101,          # Player 101 (Messi)
        "gwDates": all_gws_as_dict(),
        "currentGw": 1
    })
    
    # 2. Mock 32 National Teams
    team_names = [
        "Argentina", "Brazil", "France", "England", "Spain", "Germany", "Italy", "Portugal",
        "Netherlands", "Belgium", "Uruguay", "Croatia", "Senegal", "USA", "Mexico", "Canada",
        "Morocco", "Japan", "South Korea", "Australia", "Iran", "Saudi Arabia", "Switzerland", "Denmark",
        "Sweden", "Ukraine", "Poland", "Colombia", "Chile", "Ecuador", "Nigeria", "Egypt"
    ]
    for idx, name in enumerate(team_names, 1):
        db.collection("wc_teams").document(str(idx)).set({
            "id": idx,
            "name": name,
            "logo": f"https://logo.api-sports.io/football/teams/{idx}.png",
            "isoCode": name[:3].upper(),
            "group": chr(65 + ((idx - 1) // 4)), # Group A to H
            "eliminated": False,
            "eliminatedAfterGw": None,
            "groupFinished": False
        })
        
    # 3. Mock 160 Players (5 per team: 1 GK, 2 DEF, 1 MID, 1 FWD to make it simple)
    # Actually, we need to satisfy squad quota: 2 GK, 5 DEF, 5 MID, 3 FWD per squad.
    # With 7 or 8 managers, we need a pool large enough. Let's create:
    # 20 GK (pos 1), 45 DEF (pos 2), 45 MID (pos 3), 30 FWD (pos 4)
    # GK IDs: 101 - 120
    # DEF IDs: 201 - 245
    # MID IDs: 301 - 345
    # FWD IDs: 401 - 430
    
    positions = [
        (1, 20, 101, "GK"),
        (2, 45, 201, "DEF"),
        (3, 45, 301, "MID"),
        (4, 30, 401, "FWD")
    ]
    
    player_idx = 0
    all_mock_players = []
    
    for pos_val, count, start_id, pos_name in positions:
        for offset in range(count):
            pid = start_id + offset
            team_id = (player_idx % 32) + 1
            team_name = team_names[team_id - 1]
            player_doc = {
                "id": pid,
                "name": f"Player {pid} ({pos_name})",
                "photo": f"https://photo.api-sports.io/football/players/{pid}.png",
                "position": pos_val,
                "positionName": pos_name,
                "teamId": team_id,
                "teamName": team_name,
                "teamIso": team_name[:3].upper(),
                "eliminated": False,
                "draftRank": player_idx + 1
            }
            db.collection("wc_players").document(str(pid)).set(player_doc)
            all_mock_players.append(player_doc)
            player_idx += 1

    # 4. Mock Fixtures for all 8 Gameweeks
    # 48 group stage matches (GW 1-3)
    # 16 Round of 32 matches (GW 4)
    # 8 Round of 16 matches (GW 5)
    # 4 Quarter-final matches (GW 6)
    # 2 Semi-final matches (GW 7)
    # 1 Final match (GW 8)
    
    # We will just write 1 fixture per GW to keep it fast, or standard count. Let's make 2 fixtures per GW!
    for gw in range(1, 9):
        # We need at least one fixture per GW to avoid finalizing empty GWs
        for f_idx in [1, 2]:
            fid = gw * 10 + f_idx
            home_team_id = ((gw * 2 + f_idx) % 32) + 1
            away_team_id = ((gw * 2 + f_idx + 1) % 32) + 1
            db.collection("wc_fixtures").document(str(fid)).set({
                "id": fid,
                "gw": gw,
                "wcRound": f"Gameweek {gw}",
                "homeTeam": {"id": home_team_id, "name": team_names[home_team_id-1], "isoCode": ""},
                "awayTeam": {"id": away_team_id, "name": team_names[away_team_id-1], "isoCode": ""},
                "kickoff": datetime(2026, 6, 11 + gw, 18, 0, tzinfo=timezone.utc),
                "status": "NS",
                "score": {"home": None, "away": None},
                "processedForFantasy": False
            })
            
    print(f"✅ Mock database hydrated with 32 teams, {len(all_mock_players)} players, and 16 fixtures.")

def get_draft_squad(gk_pool, def_pool, mid_pool, fwd_pool, manager_idx):
    # Retrieve exactly 2 GK, 5 DEF, 5 MID, 3 FWD for each manager from the pools
    # Shift indices to ensure no players overlap!
    squad_players = []
    # GK
    squad_players.extend(gk_pool[manager_idx*2 : (manager_idx+1)*2])
    # DEF
    squad_players.extend(def_pool[manager_idx*5 : (manager_idx+1)*5])
    # MID
    squad_players.extend(mid_pool[manager_idx*5 : (manager_idx+1)*5])
    # FWD
    squad_players.extend(fwd_pool[manager_idx*3 : (manager_idx+1)*3])
    
    return [{
        "playerId": p["id"],
        "position": p["position"],
        "name": p["name"],
        "positionName": p["positionName"],
        "teamId": p["teamId"],
        "teamName": p["teamName"],
        "teamIso": p["teamIso"],
        "eliminated": False
    } for p in squad_players]

def get_starting_and_bench(squad):
    # squad has 15 players:
    # 2 GK (indices 0, 1)
    # 5 DEF (indices 2, 3, 4, 5, 6)
    # 5 MID (indices 7, 8, 9, 10, 11)
    # 3 FWD (indices 12, 13, 14)
    # Pick a valid 1-4-4-2 formation
    starting = [
        squad[0]["playerId"], # GK[0]
        squad[2]["playerId"], squad[3]["playerId"], squad[4]["playerId"], squad[5]["playerId"], # DEF[0..3]
        squad[7]["playerId"], squad[8]["playerId"], squad[9]["playerId"], squad[10]["playerId"], # MID[0..3]
        squad[12]["playerId"], squad[13]["playerId"] # FWD[0..1]
    ]
    bench = [
        squad[1]["playerId"], # GK[1] (reserve GK, must be bench[0])
        squad[6]["playerId"], # DEF[4]
        squad[11]["playerId"], # MID[4]
        squad[14]["playerId"] # FWD[2]
    ]
    return starting, bench

def simulate_fixtures_scoring(gw, player_points_map):
    # player_points_map: {pid: points}
    fixtures = db.collection("wc_fixtures").where("gw", "==", gw).get()
    print(f"🔍 simulate_fixtures_scoring: found {len(fixtures)} fixtures for GW {gw}")
    for f in fixtures:
        fid = f.id
        
        # Set to finished
        f.reference.update({
            "status": "FT",
            "score": {"home": 2, "away": 1},
            "processedForFantasy": True
        })
        
        # Write playerScores subcollection
        # We need to simulate who played in these fixtures. Let's write scores for ALL drafted players!
        written_scores = 0
        for pid, pts in player_points_map.items():
            f.reference.collection("playerScores").document(str(pid)).set({
                "fantasyPoints": pts,
                "stats": {
                    "minutes": 90 if pts > 0 else 0,
                    "goals": 1 if pts >= 5 else 0,
                    "cleanSheet": True if pts >= 4 else False
                }
            })
            written_scores += 1
        print(f"   Fixture {fid}: wrote {written_scores} playerScores")
            
def run_7_player_simulation():
    print("\n==============================================")
    print("🏃 RUNNING SIMULATION 1: 7-PLAYER LEAGUE (ODD BYE)")
    print("==============================================")
    
    # 1. Create league
    admin_uid = "mgr_1"
    res = league_mgr.create_league(
        uid=admin_uid,
        name="FIFA World Cup 7-League",
        display_name="Manager 1",
        max_members=7,
        pick_timer=30
    )
    lid = res["leagueId"]
    invite_code = res["inviteCode"]
    print(f"🏆 League '{res['name']}' created. ID: {lid}, Invite Code: {invite_code}")
    
    # 2. Join 6 other friends
    for idx in range(2, 8):
        uid = f"mgr_{idx}"
        league_mgr.join_league(
            uid=uid,
            invite_code=invite_code,
            display_name=f"Manager {idx}",
            team_name=f"Team Manager {idx}"
        )
    print(f"👥 7 managers have joined the league successfully.")
    
    # 3. Every manager registers predictions before GW1 locks
    # predictedWinner: team 1 (Argentina), predictedTopScorer: 101 (Messi)
    # Manager 1 gets correct predictions. Others get them wrong.
    for idx in range(1, 8):
        uid = f"mgr_{idx}"
        pred_winner = "1" if idx in [1, 2] else "3" # 1 = Argentina, 3 = France
        pred_scorer = 101 if idx in [1, 3] else 102 # 101 = Messi
        db.collection("leagues").document(lid).collection("members").document(uid).update({
            "predictions": {
                "predictedWinner": pred_winner,
                "predictedTopScorer": pred_scorer,
                "predictionsLockedAt": datetime.now(timezone.utc)
            }
        })
    print("🔮 All managers submitted their predictions.")
    
    # 4. Lock for draft (calculates knockoutStartGw, actualMemberCount, etc.)
    lock_res = league_mgr.lock_for_draft(lid, admin_uid)
    print(f"🔒 League locked for draft: actualMemberCount = {lock_res['memberCount']}")
    
    # 5. Populate Draft Squads
    # In a real draft, members make picks. Here we populate valid squads directly!
    gk_players = db.collection("wc_players").where("position", "==", 1).get()
    def_players = db.collection("wc_players").where("position", "==", 2).get()
    mid_players = db.collection("wc_players").where("position", "==", 3).get()
    fwd_players = db.collection("wc_players").where("position", "==", 4).get()
    
    gk_pool = [g.to_dict() for g in gk_players]
    def_pool = [d.to_dict() for d in def_players]
    mid_pool = [m.to_dict() for m in mid_players]
    fwd_pool = [f.to_dict() for f in fwd_players]
    
    managers_squads = {}
    for idx in range(1, 8):
        uid = f"mgr_{idx}"
        squad_players = get_draft_squad(gk_pool, def_pool, mid_pool, fwd_pool, idx - 1)
        db.collection("leagues").document(lid).collection("squads").document(uid).set({
            "players": squad_players,
            "updatedAt": datetime.now(timezone.utc)
        })
        managers_squads[uid] = squad_players
        
    print("🎮 Draft complete! All 7 managers drafted 15 valid players.")
    
    # Transition league status to group_phase and generate schedule
    db.collection("leagues").document(lid).update({"status": "drafting"})
    start_season_res = league_mgr.start_season(lid, admin_uid)
    print(f"🚀 Season started! League status: {start_season_res['status']}. Schedule generated.")
    
    # 6. Run Group Stage (GW 1-6)
    # We will simulate lineups, score fixtures, award top-scorer bonus, and finalize each GW
    for gw in range(1, 7):
        print(f"\n--- Gameweek {gw} Simulation ---")
        
        # A. Set Lineups for all 7 managers
        for idx in range(1, 8):
            uid = f"mgr_{idx}"
            squad = managers_squads[uid]
            starting, bench = get_starting_and_bench(squad)
            squad_mgr.set_lineup(
                lid=lid, uid=uid, gw=gw,
                starting=starting, bench=bench,
                captain=starting[0], vice_captain=starting[1]
            )
            
        # B. Simulate scores. Let's make Manager 1 always score the highest to earn the +1 H2H Standings Bonus!
        # Manager 1: all starting players get 8 points. Total points = 11*8 + 8(captain) = 96 points!
        # Other managers: starting players get 3 points. Total points = 11*3 + 3(captain) = 36 points!
        points_map = {}
        for idx in range(1, 8):
            uid = f"mgr_{idx}"
            squad = managers_squads[uid]
            starting, bench = get_starting_and_bench(squad)
            for p in starting:
                points_map[p] = 8 if idx == 1 else 3
                
        simulate_fixtures_scoring(gw, points_map)
        
        # C. Finalize Gameweek!
        fin_res = finalize_gw(lid, gw, db, None)
        print(f"GW {gw} Finalized: nextGw = {fin_res['nextGw']}")
        
        # D. Validate Standings and +1 Standings Bonus
        standings_doc = db.collection("leagues").document(lid).collection("standings").document("current").get()
        standings = standings_doc.to_dict()
        managers_stats = standings["managers"]
        
        # Let's inspect Manager 1
        m1_stat = next(m for m in managers_stats if m["uid"] == "mgr_1")
        print(f"📊 Manager 1 Standings after GW {gw}: hpts = {m1_stat['hpts']}, fpts = {m1_stat['fpts']}, hw = {m1_stat['hw']}, hl = {m1_stat['hl']}, hd = {m1_stat['hd']}, bonusPoints = {m1_stat['bonusPoints']}")
        
        # Assert Manager 1 got the +1 bonus points in each GW!
        assert m1_stat["bonusPoints"] == gw, f"Expected Manager 1 to have {gw} bonus points, got {m1_stat['bonusPoints']}"
        
        # Check bye manager behaviour.
        # Round robin scheduling with 7 players means in each GW, one manager is on bye (played against __BYE__).
        # For a bye manager, they don't have a H2H match in the schedule.
        # Let's verify their H2H wins + losses + draws in this GW are unchanged, but their fpts increased!
        schedule = db.collection("leagues").document(lid).collection("schedule").document(str(gw)).get().to_dict()
        matched_uids = set()
        print(f"   Schedule matches: {schedule['matches']}")
        for m in schedule["matches"]:
            matched_uids.add(m["home"])
            matched_uids.add(m["away"])
            
        print(f"   Matched UIDs: {matched_uids}")
        bye_uid = next(uid for uid in [f"mgr_{i}" for i in range(1, 8)] if uid not in matched_uids)
        bye_stat = next(m for m in managers_stats if m["uid"] == bye_uid)
        print(f"🛌 GW {gw} Bye Manager: {bye_uid}. Stats: hpts = {bye_stat['hpts']}, fpts = {bye_stat['fpts']}")
        # Ensure they still got their fantasy points!
        assert bye_stat["fpts"] > 0, "Bye manager fantasy points should be recorded"

    # 7. GW6 completed! Seeding Knockout for GW7
    print("\n--- Seeding Semi-finals (GW 7) Knockout Bracket ---")
    bracket_res = get_bracket(lid, db)
    assert bracket_res, "Bracket should be seeded successfully"
    print(f"🏆 Bracket type: {bracket_res['type']}")
    print("Seeds:")
    for s in bracket_res["seeds"]:
        print(f"  Seed {s['seed']}: {s['displayName']} ({s['teamName']}) - hpts: {s['hpts']}, fpts: {s['fpts']}, via: {s['qualifiedVia']}")
        
    # Check that Manager 1 is Seed 1 or Seed 2 (H2H path)
    seeds = bracket_res["seeds"]
    m1_seed = next((s for s in seeds if s["uid"] == "mgr_1"), None)
    assert m1_seed is not None, "Manager 1 must qualify"
    assert m1_seed["seed"] in [1, 2], "Manager 1 must qualify via H2H (Seed 1 or 2)"
    
    # 8. Run GW7 Semi-finals
    print("\n--- GW 7 Semi-finals Simulation ---")
    # Set lineup for the 4 qualified semi-finalists
    sf_uids = [s["uid"] for s in seeds]
    for uid in sf_uids:
        squad = managers_squads[uid]
        starting, bench = get_starting_and_bench(squad)
        squad_mgr.set_lineup(
            lid=lid, uid=uid, gw=7,
            starting=starting, bench=bench,
            captain=starting[0], vice_captain=starting[1]
        )
        
    # Simulate scores. Make SF 1 Winner be the higher seed, SF 2 Winner be the lower seed!
    # sf_1v4 matchup: Seed 1 uid wins.
    # sf_2v3 matchup: Seed 3 uid wins.
    s1_uid = next(s["uid"] for s in seeds if s["seed"] == 1)
    s4_uid = next(s["uid"] for s in seeds if s["seed"] == 4)
    s2_uid = next(s["uid"] for s in seeds if s["seed"] == 2)
    s3_uid = next(s["uid"] for s in seeds if s["seed"] == 3)
    
    sf_points_map = {}
    for uid in sf_uids:
        squad = managers_squads[uid]
        starting, bench = get_starting_and_bench(squad)
        for p in starting:
            if uid in [s1_uid, s3_uid]:
                sf_points_map[p] = 10  # Winners score 10 per player
            else:
                sf_points_map[p] = 2   # Losers score 2 per player
                
    simulate_fixtures_scoring(7, sf_points_map)
    
    # Finalize GW7
    finalize_gw(lid, 7, db, None)
    
    # Verify bracket advancement
    bracket_res = get_bracket(lid, db)
    final_match = bracket_res["rounds"]["final"][0]
    print(f"🎫 SF Results: {bracket_res['rounds']['sf']}")
    print(f"🎫 Final Matchup generated: {final_match['home']} vs {final_match['away']}")
    assert final_match["home"] in [s1_uid, s3_uid], "Winners must advance to final"
    assert final_match["away"] in [s1_uid, s3_uid], "Winners must advance to final"
    
    # 9. Run GW8 Final
    print("\n--- GW 8 Final Simulation ---")
    final_uids = [final_match["home"], final_match["away"]]
    for uid in final_uids:
        squad = managers_squads[uid]
        starting, bench = get_starting_and_bench(squad)
        squad_mgr.set_lineup(
            lid=lid, uid=uid, gw=8,
            starting=starting, bench=bench,
            captain=starting[0], vice_captain=starting[1]
        )
        
    # Simulate final points. Let's make final_match['home'] win the championship!
    final_points_map = {}
    for uid in final_uids:
        squad = managers_squads[uid]
        starting, bench = get_starting_and_bench(squad)
        for p in starting:
            final_points_map[p] = 12 if uid == final_match["home"] else 4
            
    simulate_fixtures_scoring(8, final_points_map)
    
    # Finalize GW8 (triggers predictions bonus!)
    finalize_gw(lid, 8, db, None)
    
    # Verify League is complete and Champion crowned!
    league_doc = db.collection("leagues").document(lid).get().to_dict()
    print(f"🏁 League Status: {league_doc['status']}. Champion: {league_doc['champion']}")
    assert league_doc["status"] == "complete", "League status must be complete"
    assert league_doc["champion"] == final_match["home"], "Champion must be the winner of final match"
    
    # Verify predictions bonus was awarded!
    # Manager 1: correct winner ('team_1'/Argentina) and correct top scorer (101/Messi) → +25 pts!
    # Manager 2: correct winner only → +15 pts
    # Manager 3: correct top scorer only → +10 pts
    # Manager 4: wrong predictions → +0 pts
    standings_final = db.collection("leagues").document(lid).collection("standings").document("current").get().to_dict()
    managers_final = standings_final["managers"]
    
    m1_final = next(m for m in managers_final if m["uid"] == "mgr_1")
    m2_final = next(m for m in managers_final if m["uid"] == "mgr_2")
    m3_final = next(m for m in managers_final if m["uid"] == "mgr_3")
    m4_final = next(m for m in managers_final if m["uid"] == "mgr_4")
    
    print(f"🔮 Predictions Bonus Awards:")
    print(f"  Manager 1: +25 bonus points. Final fpts: {m1_final['fpts']}")
    print(f"  Manager 2: +15 bonus points. Final fpts: {m2_final['fpts']}")
    print(f"  Manager 3: +10 bonus points. Final fpts: {m3_final['fpts']}")
    print(f"  Manager 4: +0 bonus points. Final fpts: {m4_final['fpts']}")
    
    # Check predictions scores doc
    pred_doc = db.collection("leagues").document(lid).collection("scores").document("predictions").get()
    assert pred_doc.exists, "Predictions scores document must be created"
    pred_data = pred_doc.to_dict()
    print(f"🔮 Predictions doc content: {pred_data}")
    assert pred_data["results"]["mgr_1"]["points"] == 25
    assert pred_data["results"]["mgr_2"]["points"] == 15
    assert pred_data["results"]["mgr_3"]["points"] == 10
    print("✅ Predictions bonus verified successfully!")
    print("🏆 Simulation 1 passed perfectly!")

def run_6_player_simulation():
    print("\n==============================================")
    print("🏃 RUNNING SIMULATION 2: 6-PLAYER LEAGUE (AAA GW6)")
    print("==============================================")
    
    # 1. Create league
    admin_uid = "mgr_1"
    res = league_mgr.create_league(
        uid=admin_uid,
        name="FIFA World Cup 6-League",
        display_name="Manager 1",
        max_members=6,
        pick_timer=30
    )
    lid = res["leagueId"]
    invite_code = res["inviteCode"]
    print(f"🏆 League '{res['name']}' created. ID: {lid}, Invite Code: {invite_code}")
    
    # 2. Join 5 other friends
    for idx in range(2, 7):
        uid = f"mgr_{idx}"
        league_mgr.join_league(
            uid=uid,
            invite_code=invite_code,
            display_name=f"Manager {idx}",
            team_name=f"Team Manager {idx}"
        )
    print(f"👥 6 managers have joined.")
    
    # 3. Lock for draft
    lock_res = league_mgr.lock_for_draft(lid, admin_uid)
    print(f"🔒 League locked for draft: actualMemberCount = {lock_res['memberCount']}")
    
    # 4. Populate Draft Squads
    gk_players = db.collection("wc_players").where("position", "==", 1).get()
    def_players = db.collection("wc_players").where("position", "==", 2).get()
    mid_players = db.collection("wc_players").where("position", "==", 3).get()
    fwd_players = db.collection("wc_players").where("position", "==", 4).get()
    
    gk_pool = [g.to_dict() for g in gk_players]
    def_pool = [d.to_dict() for d in def_players]
    mid_pool = [m.to_dict() for m in mid_players]
    fwd_pool = [f.to_dict() for f in fwd_players]
    
    managers_squads = {}
    for idx in range(1, 7):
        uid = f"mgr_{idx}"
        squad_players = get_draft_squad(gk_pool, def_pool, mid_pool, fwd_pool, idx - 1)
        db.collection("leagues").document(lid).collection("squads").document(uid).set({
            "players": squad_players,
            "updatedAt": datetime.now(timezone.utc)
        })
        managers_squads[uid] = squad_players
        
    # Start season
    db.collection("leagues").document(lid).update({"status": "drafting"})
    league_mgr.start_season(lid, admin_uid)
    print("🚀 Season started for 6-player league.")
    
    # 5. Run GW 1-5 H2H
    for gw in range(1, 6):
        for idx in range(1, 7):
            uid = f"mgr_{idx}"
            squad = managers_squads[uid]
            starting, bench = get_starting_and_bench(squad)
            squad_mgr.set_lineup(
                lid=lid, uid=uid, gw=gw,
                starting=starting, bench=bench,
                captain=starting[0], vice_captain=starting[1]
            )
        
        # Simple points: all score equal
        points_map = {}
        for idx in range(1, 7):
            uid = f"mgr_{idx}"
            squad = managers_squads[uid]
            starting, bench = get_starting_and_bench(squad)
            for p in starting:
                points_map[p] = 5
                
        simulate_fixtures_scoring(gw, points_map)
        finalize_gw(lid, gw, db, None)
        print(f"H2H GW {gw} Finalized.")
        
    # 6. Run GW 6 (AAA - All-Against-All scoring!)
    # Managers rank points table: 1st=6, 2nd=4, 3rd=3, 4th=2, 5th=1, 6th=0
    # Let's construct a tied score to verify tied ranks get the higher rank points!
    # Manager 1 score: 80 fpts (Rank 1 -> 6 pts)
    # Manager 2 score: 70 fpts (Rank 2 -> 4 pts)
    # Manager 3 score: 70 fpts (Rank 2 tied -> 4 pts!)
    # Manager 4 score: 50 fpts (Rank 4 -> 2 pts)
    # Manager 5 score: 40 fpts (Rank 5 -> 1 pt)
    # Manager 6 score: 10 fpts (Rank 6 -> 0 pts)
    print("\n--- Running GW 6 All-Against-All Phase ---")
    gw = 6
    for idx in range(1, 7):
        uid = f"mgr_{idx}"
        squad = managers_squads[uid]
        starting, bench = get_starting_and_bench(squad)
        squad_mgr.set_lineup(
            lid=lid, uid=uid, gw=gw,
            starting=starting, bench=bench,
            captain=starting[0], vice_captain=starting[1]
        )
        
    expected_fpts = {
        "mgr_1": 80,
        "mgr_2": 70,
        "mgr_3": 70,
        "mgr_4": 50,
        "mgr_5": 40,
        "mgr_6": 10
    }
    
    # Distribute points across starting players to match target fpts exactly (remember starting has 11 players, captain is doubled, so 12 multiplier)
    # Easiest way: assign points directly to fixturesScores.
    points_map = {}
    for idx in range(1, 7):
        uid = f"mgr_{idx}"
        squad = managers_squads[uid]
        starting, bench = get_starting_and_bench(squad)
        target = expected_fpts[uid]
        # assign points per player: base = target // 12, remainder distributed
        base = target // 12
        rem = target % 12
        for p_idx, p in enumerate(starting):
            pts = base
            if p_idx == 0: # Captain doubles!
                pts += rem // 2
            points_map[p] = pts
            
    simulate_fixtures_scoring(gw, points_map)
    finalize_gw(lid, gw, db, None)
    
    # 7. Verify Standings after GW6 AAA points award
    standings_doc = db.collection("leagues").document(lid).collection("standings").document("current").get().to_dict()
    managers_stats = standings_doc["managers"]
    
    # Read the scores document for GW6 to inspect h2hResults
    scores_gw6 = db.collection("leagues").document(lid).collection("scores").document("6").get().to_dict()
    h2h_results = scores_gw6["h2hResults"]
    print("AAA Standings points awarded in GW6:")
    for uid, r in h2h_results.items():
        print(f"  {uid}: pointsFor = {r['pointsFor']}, h2hPoints = {r['h2hPoints']}, result = {r['result']}")
        
    assert h2h_results["mgr_1"]["h2hPoints"] == 6, "Rank 1 gets 6 points"
    assert h2h_results["mgr_2"]["h2hPoints"] == 4, "Rank 2 gets 4 points"
    assert h2h_results["mgr_3"]["h2hPoints"] == 4, "Tied Rank 2 gets 4 points (no splitting!)"
    assert h2h_results["mgr_4"]["h2hPoints"] == 2, "Rank 4 gets 2 points"
    assert h2h_results["mgr_5"]["h2hPoints"] == 1, "Rank 5 gets 1 points"
    assert h2h_results["mgr_6"]["h2hPoints"] == 0, "Rank 6 gets 0 points"
    
    # Assert GW6 top-scorer standings bonus point was awarded to mgr_1
    assert scores_gw6["results"]["mgr_1"].get("bonusPoint") is True, "mgr_1 (top scorer) must be awarded the standings bonus point"
    assert scores_gw6["results"]["mgr_2"].get("bonusPoint") is not True, "mgr_2 must not have the standings bonus point"
    print("✅ GW6 Top Scorer standings bonus point verified successfully!")
    
    print("✅ AAA scoring and ties verified perfectly!")
    print("🏆 Simulation 2 passed perfectly!")

def run_8_player_schedule_simulation():
    print("\n==============================================")
    print("🏃 RUNNING SIMULATION 3: 8-PLAYER LEAGUE SCHEDULE (NO SELF-PAIRINGS)")
    print("==============================================")
    
    admin_uid = "mgr_1"
    res = league_mgr.create_league(
        uid=admin_uid,
        name="FIFA World Cup 8-League",
        display_name="Manager 1",
        max_members=8,
        pick_timer=30
    )
    lid = res["leagueId"]
    invite_code = res["inviteCode"]
    print(f"🏆 League '{res['name']}' created. ID: {lid}, Invite Code: {invite_code}")
    
    # 2. Join 7 other friends
    for idx in range(2, 9):
        uid = f"mgr_{idx}"
        league_mgr.join_league(
            uid=uid,
            invite_code=invite_code,
            display_name=f"Manager {idx}",
            team_name=f"Team Manager {idx}"
        )
    print(f"👥 8 managers have joined.")
    
    # 3. Lock for draft
    lock_res = league_mgr.lock_for_draft(lid, admin_uid)
    print(f"🔒 League locked for draft: actualMemberCount = {lock_res['memberCount']}")
    
    # 4. Mock squads to allow season start
    gk_players = db.collection("wc_players").where("position", "==", 1).get()
    def_players = db.collection("wc_players").where("position", "==", 2).get()
    mid_players = db.collection("wc_players").where("position", "==", 3).get()
    fwd_players = db.collection("wc_players").where("position", "==", 4).get()
    
    gk_pool = [g.to_dict() for g in gk_players]
    def_pool = [d.to_dict() for d in def_players]
    mid_pool = [m.to_dict() for m in mid_players]
    fwd_pool = [f.to_dict() for f in fwd_players]
    
    for idx in range(1, 9):
        uid = f"mgr_{idx}"
        squad_players = get_draft_squad(gk_pool, def_pool, mid_pool, fwd_pool, idx - 1)
        db.collection("leagues").document(lid).collection("squads").document(uid).set({
            "players": squad_players,
            "updatedAt": datetime.now(timezone.utc)
        })
        
    # Start season (generates H2H schedule)
    db.collection("leagues").document(lid).update({"status": "drafting"})
    league_mgr.start_season(lid, admin_uid)
    print("🚀 Season started. H2H Schedule generated.")
    
    # 5. Verify no self-pairings in any match of GW1 to GW6
    for gw in range(1, 7):
        schedule = db.collection("leagues").document(lid).collection("schedule").document(str(gw)).get().to_dict()
        matches = schedule.get("matches", [])
        print(f"   GW {gw} Matches: {matches}")
        assert len(matches) == 4, f"GW {gw} must have exactly 4 matches scheduled for an 8-player league"
        for m in matches:
            home = m["home"]
            away = m["away"]
            assert home != away, f"Self-pairing detected in GW {gw}: {home} vs {away}"
            
    print("✅ 8-player schedule verified: exactly 4 matches per round, 0 self-pairings!")
    print("🏆 Simulation 3 passed perfectly!")

def main():
    clear_emulator_db()
    populate_mock_data()
    run_7_player_simulation()
    run_6_player_simulation()
    run_8_player_schedule_simulation()
    print("\n🎉 ALL WORLD CUP FANTASY INTEGRATION TESTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
