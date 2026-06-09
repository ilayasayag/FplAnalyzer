import os
import json
import unicodedata
import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from fpl_predictor.game.wc_scoring import process_fixture, finalize_gw
from fpl_predictor.data.wc_api import WC2026Client

POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

# Cache a single offline-safe client for seeding so elimination detection
# (which runs at GW3 inside finalize_gw) can read wc_teams from Firestore.
_SEED_WC_CLIENT = None


def _seed_wc_client(db):
    global _SEED_WC_CLIENT
    if _SEED_WC_CLIENT is None:
        _SEED_WC_CLIENT = WC2026Client(db=db)
    return _SEED_WC_CLIENT

def normalize_name(name):
    name = name.replace("&apos;", "'").replace("’", "'").replace("ʻ", "'").replace("ʻ", "'")
    normalized = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    return normalized.lower().strip()

def match_player_event(p_name, ev_name):
    n_p = normalize_name(p_name)
    n_e = normalize_name(ev_name)
    if n_e == n_p or n_e in n_p or n_p in n_e:
        return True
    parts_p = n_p.split()
    parts_e = n_e.split()
    if len(parts_p) > 0 and len(parts_e) > 0:
        if parts_p[-1] == parts_e[-1] and parts_p[0][0] == parts_e[0][0]:
            return True
    return False


def build_team_raw_stats(team_id, players_list, events, conceded_map):
    """Build realistic, api-sports-shaped synthetic per-player stats for one
    team in one fixture, for seeding GW1-3 through the real scoring engine.

    Everything is CALCULATED (no injected legacy `bps`) and DETERMINISTIC —
    derived from the player id ordering + position — so re-seeds are
    reproducible. The distribution is deliberately shaped so the engine's new
    rules are observable in the seeded UI:
      - minutes vary (90 / 70 / 45 / 0) -> exercises the 60' appearance
        threshold and the minutes==0 => 0-points path.
      - tackles (total + interceptions + blocks) sum to >= 10 for at least one
        DEF and >= 12 for at least one MID -> DefCon (+2) fires.
      - games.rating spreads across players -> compute_rating_bonus yields a
        clean 3/2/1 ranking.

    `conceded_map` is accepted for call-site parity; goalsConceded/clean-sheet
    is derived by the engine from the fixture score, so it is not needed here.
    Returns the api-sports {"team": ..., "players": [...]} shape.
    """
    # Stable iteration order so the guaranteed-DefCon "anchor" picks (and the
    # rating spread) are reproducible across seeds.
    ordered = sorted(players_list, key=lambda pp: int(pp["id"]))

    # First DEF and first MID are guaranteed to clear the DefCon thresholds.
    def_anchor = next((int(pp["id"]) for pp in ordered if pp["position"] == 2), None)
    mid_anchor = next((int(pp["id"]) for pp in ordered if pp["position"] == 3), None)

    # Deterministic rating/minutes spreads (distinct early values -> clean
    # 3/2/1 bonus). The 0-minutes slot exercises the unused-player path.
    rating_cycle = [8.8, 8.2, 7.6, 7.1, 6.7, 6.3, 6.0]
    minutes_cycle = [90, 90, 70, 90, 45, 0, 70]

    plist = []
    for idx, p in enumerate(ordered):
        pid = int(p["id"])
        pos = p["position"]
        goals_scored = sum(1 for ev in events if ev[1] == "goal" and match_player_event(p["name"], ev[0]))
        assists_scored = sum(1 for ev in events if ev[1] == "assist" and match_player_event(p["name"], ev[0]))

        minutes = minutes_cycle[idx % len(minutes_cycle)]
        # A scorer/assister must have actually been on the pitch.
        if (goals_scored or assists_scored) and minutes == 0:
            minutes = 90
        rating = rating_cycle[idx % len(rating_cycle)] if minutes > 0 else 0.0

        # Defensive contributions split across the three buckets so we exercise
        # total + interceptions + blocks. Anchors clear the threshold; other
        # outfielders get a smaller deterministic (sub-threshold) share.
        if pos == 2 and pid == def_anchor:
            tackles = {"total": 5, "interceptions": 4, "blocks": 2}   # 11 >= 10
        elif pos == 3 and pid == mid_anchor:
            tackles = {"total": 6, "interceptions": 4, "blocks": 3}   # 13 >= 12
        elif pos in (2, 3) and minutes > 0:
            base = 3 + (idx % 3)  # 3..5, deterministic, below threshold
            tackles = {"total": base, "interceptions": idx % 2, "blocks": 0}
        else:
            tackles = {"total": 0, "interceptions": 0, "blocks": 0}

        plist.append({
            "player": {"id": pid, "name": p["name"]},
            "statistics": [
                {
                    "games": {"minutes": minutes, "rating": rating},
                    "goals": {"total": goals_scored, "assists": assists_scored, "saves": 0, "conceded": 0, "owngoals": 0},
                    "cards": {"yellow": 0, "red": 0},
                    "penalty": {"missed": 0, "saved": 0},
                    "tackles": tackles,
                }
            ]
        })
    return {"team": {"id": team_id}, "players": plist}


def select_lineup(squad):
    gks = [p for p in squad if p["position"] == 1]
    defs = [p for p in squad if p["position"] == 2]
    mids = [p for p in squad if p["position"] == 3]
    fwds = [p for p in squad if p["position"] == 4]
    
    starting = [
        gks[0]["playerId"],
        defs[0]["playerId"], defs[1]["playerId"], defs[2]["playerId"], defs[3]["playerId"],
        mids[0]["playerId"], mids[1]["playerId"], mids[2]["playerId"], mids[3]["playerId"],
        fwds[0]["playerId"], fwds[1]["playerId"]
    ]
    bench = [
        gks[1]["playerId"],
        defs[4]["playerId"],
        mids[4]["playerId"],
        fwds[2]["playerId"]
    ]
    
    def get_player_quality(p):
        pid = int(p["playerId"])
        premium = {
            154: 1,      # Messi
            278: 2,      # Mbappe
            762: 3,      # Vinicius Jr
            129718: 4,   # Bellingham
            386828: 5,   # Yamal
            1485: 6,     # Bruno Fernandes
            203224: 7,   # Wirtz
            133609: 8,   # Pedri
            280: 9,      # Alisson
            22221: 10,   # Maignan
            730: 11,     # Courtois
            290: 12,     # van Dijk
            2285: 13,    # Rudiger
            9: 14,       # Hakimi
            257: 15,     # Marquinhos
            629: 16,     # De Bruyne
            631: 17,     # Foden
            152982: 18,  # Palmer
            754: 19,     # Modric
            756: 20,     # Valverde
            907: 21,     # Lukaku
            247: 22,     # Gakpo
            51617: 23,   # Nunez
            377122: 24,  # Endrick
            44: 25       # Rodri
        }
        if pid in premium:
            return premium[pid]
        return pid + 1000000

    starting_players = [p for p in squad if p["playerId"] in starting]
    starting_attackers = [p for p in starting_players if p["position"] in (3, 4)]
    starting_attackers.sort(key=get_player_quality)
    
    captain = starting_attackers[0]["playerId"] if starting_attackers else starting[0]
    vice = starting_attackers[1]["playerId"] if len(starting_attackers) > 1 else starting[1]
    
    return {
        "starting": starting,
        "bench": bench,
        "formation": [1, 4, 4, 2],
        "captain": None,
        "viceCaptain": None,
        "locked": True,
        "autoSubsMade": []
    }

def seed_tournament_data(db):
    print("🌱 Seeding tournament teams and players from wc_seeded_data.json...")
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "wc_seeded_data.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    teams = data.get("teams", [])
    players = data.get("players", [])
    
    for t in teams:
        db.collection("wc_teams").document(str(t["id"])).set(t)
        
    for p in players:
        db.collection("wc_players").document(str(p["id"])).set(p)
        
    # missing stars
    missing_stars = [
        {
            "draftRank": 11, "name": "Bukayo Saka", "position": 3, "teamIso": "ENG",
            "id": 99901, "eliminated": False, "photo": "https://media.api-sports.io/football/players/99901.png",
            "teamId": 10, "positionName": "MID", "teamName": "England"
        },
        {
            "draftRank": 18, "name": "Cristiano Ronaldo", "position": 4, "teamIso": "POR",
            "id": 99902, "eliminated": False, "photo": "https://media.api-sports.io/football/players/99902.png",
            "teamId": 27, "positionName": "FWD", "teamName": "Portugal"
        },
        {
            "draftRank": 7, "name": "Harry Kane", "position": 4, "teamIso": "ENG",
            "id": 99903, "eliminated": False, "photo": "https://media.api-sports.io/football/players/99903.png",
            "teamId": 10, "positionName": "FWD", "teamName": "England"
        }
    ]
    for star in missing_stars:
        db.collection("wc_players").document(str(star["id"])).set(star)
        
    # Seed the wc_gameweeks collection
    from fpl_predictor.game.wc_gameweeks import gw_as_dict
    for gw in range(1, 9):
        db.collection("wc_gameweeks").document(str(gw)).set(gw_as_dict(gw))
        
    # Write tournament config if not present
    cfg_ref = db.collection("wc_config").document("tournament")
    if not cfg_ref.get().exists:
        cfg_ref.set({
            "rules": {
                "scoring": {
                    "appearUnder60": 1,
                    "appear60Plus": 2,
                    "goalPoints": {"1": 6, "2": 6, "3": 5, "4": 4},
                    "assistPoints": 3,
                    "csPoints": {"1": 4, "2": 4, "3": 1, "4": 0},
                    "gcPointsPer2": {"1": -1, "2": -1, "3": 0, "4": 0},
                    "yellowCardPoints": -1,
                    "redCardPoints": -3,
                    "ownGoalPoints": -2,
                    "penaltyMissPoints": -2,
                    "penaltySavePoints": 5,
                    "savesPerPointGk": 3
                }
            },
            "adminUids": []
        })

def seed_mock_league(db, USER_UID, USER_NAME):
    mock_lid = "lg_mock_draft"
    print(f"🏆 Seeding Mock League {mock_lid}...")
    
    # 1. Setup Mock League metadata
    db.collection("leagues").document(mock_lid).set({
        "leagueId": mock_lid,
        "name": "WC 2026 Expert Mock Draft",
        "inviteCode": "MOCKWC26",
        "adminUid": "u_mk_golden",
        "format": "h2h",
        "status": "group_phase",  # Starts in group_phase, finalized sequentially
        # Platform A is the SIMULATION / time-machine. Drives the data-source
        # banner so the UI honestly shows "Simulated Data Mode".
        "simulated": True,
        "maxMembers": 8,
        "pickTimer": 60,
        "tradeApproval": "vote",
        "knockoutStartGw": 4,
        "leaguePhaseGws": [1, 2, 3],
        "knockoutQualifiers": 4,
        "currentGw": 1,
        "draftAt": None,
        "seasonStartedAt": None,
        "createdAt": SERVER_TIMESTAMP,
    })
    
    # 2. Setup mock managers.
    # Platform A is a SIMULATED showcase: its 7 AI opponents use dedicated
    # u_mk_* identities that can NEVER collide with a real logged-in user
    # (real friends own u_roy/u_yonatan/... in the Platform B draft). Only the
    # logged-in user (USER_UID) is a real participant here. Keeping these
    # namespaces separate guarantees the showcase always has 8 DISTINCT members
    # and an uncorrupted H2H schedule regardless of who seeds it.
    mock_managers = [
        {"uid": "u_mk_golden", "name": "GoldenGoalFF", "team": "GoldenGoalFF's Squad", "flag": "EGY", "draftPos": 1, "waiverPri": 7},
        {"uid": "u_mk_fpltfs", "name": "FPLtfs", "team": "FPLtfs's Squad", "flag": "BRA", "draftPos": 2, "waiverPri": 6},
        {"uid": USER_UID, "name": USER_NAME, "team": "FPLFRAN's Squad", "flag": "SPA", "draftPos": 3, "waiverPri": 5},
        {"uid": "u_mk_lloyd", "name": "LloydHassell", "team": "LloydHassell's Squad", "flag": "ENG", "draftPos": 4, "waiverPri": 4},
        {"uid": "u_mk_nord", "name": "nordburfor", "team": "nordburfor's Squad", "flag": "TUN", "draftPos": 5, "waiverPri": 3},
        {"uid": "u_mk_mate", "name": "FPLMate", "team": "FPLMate's Squad", "flag": "SCO", "draftPos": 6, "waiverPri": 2},
        {"uid": "u_mk_cant", "name": "CantWinFPL", "team": "CantWinFPL's Squad", "flag": "TUR", "draftPos": 7, "waiverPri": 1},
        {"uid": "u_mk_opp", "name": "Opponent", "team": "Opponent XI", "flag": "GER", "draftPos": 8, "waiverPri": 8},
    ]
    
    for m in mock_managers:
        db.collection("leagues").document(mock_lid).collection("members").document(m["uid"]).set({
            "displayName": m["name"],
            "teamName": m["team"],
            "flag": m["flag"],
            "draftPosition": m["draftPos"],
            "waiverPriority": m["waiverPri"],
            "joinedAt": SERVER_TIMESTAMP,
        })
        
    # 3. Load mapped squads
    squad_ids_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "squad_ids.json")
    with open(squad_ids_path, "r", encoding="utf-8") as f:
        squad_data_raw = json.load(f)
        
    squads = {}
    for k, v in squad_data_raw.items():
        uid = USER_UID if k == "USER_UID" else k
        squads[uid] = v
        
    # Generate squad for Opponent XI
    seeded_json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "wc_seeded_data.json")
    with open(seeded_json_path, "r", encoding="utf-8") as f:
        seeded_data = json.load(f)
    all_players = seeded_data.get("players", [])
    
    drafted_player_ids = set()
    for squad in squads.values():
        for p in squad:
            drafted_player_ids.add(int(p["id"]))
            
    available_players = [p for p in all_players if int(p["id"]) not in drafted_player_ids]
    available_players.sort(key=lambda p: p.get("draftRank", 999))
    
    opp_gks = [p for p in available_players if p["position"] == 1][:2]
    opp_defs = [p for p in available_players if p["position"] == 2][:5]
    opp_mids = [p for p in available_players if p["position"] == 3][:5]
    opp_fwds = [p for p in available_players if p["position"] == 4][:3]
    
    opp_squad = opp_gks + opp_defs + opp_mids + opp_fwds
    squads["u_mk_opp"] = []
    for idx, p in enumerate(opp_squad):
        squads["u_mk_opp"].append({
            "id": int(p["id"]),
            "name": p["name"],
            "position": p["position"],
            "positionName": p["positionName"],
            "teamIso": p["teamIso"]
        })
        
    # Write squads to Firestore
    for uid, squad in squads.items():
        squad_list = []
        for idx, p in enumerate(squad):
            squad_list.append({
                "playerId": int(p["id"]),
                "draftedRound": (idx // 8) + 1,
                "position": int(p["position"]),
                "name": p["name"],
                "positionName": p["positionName"],
                "teamIso": p["teamIso"],
                "eliminated": False,
                "teamId": p.get("teamId", 0),
                "teamName": p.get("teamName", "")
            })
        db.collection("leagues").document(mock_lid).collection("squads").document(uid).set({
            "players": squad_list
        })
        
    # 4. H2H schedule & events mapping
    schedule_by_gw = {
        1: [("u_mk_golden", "u_mk_cant"), ("u_mk_fpltfs", "u_mk_opp"), ("u_mk_lloyd", "u_mk_mate"), (USER_UID, "u_mk_nord")],
        2: [("u_mk_golden", "u_mk_opp"), ("u_mk_fpltfs", "u_mk_mate"), ("u_mk_lloyd", "u_mk_nord"), (USER_UID, "u_mk_cant")],
        3: [("u_mk_golden", "u_mk_mate"), ("u_mk_fpltfs", "u_mk_nord"), ("u_mk_opp", "u_mk_cant"), (USER_UID, "u_mk_lloyd")]
    }
    
    for gw, matches in schedule_by_gw.items():
        match_list = [{"home": m[0], "away": m[1]} for m in matches]
        db.collection("leagues").document(mock_lid).collection("schedule").document(str(gw)).set({
            "gw": gw,
            "matches": match_list
        })
        
    fixtures_data = {
        1: [
            {"id": 101, "home": "GER", "away": "CUW", "score": {"home": 5, "away": 0}},
            {"id": 102, "home": "SPA", "away": "CPV", "score": {"home": 4, "away": 1}},
            {"id": 103, "home": "NOR", "away": "IRQ", "score": {"home": 3, "away": 1}},
            {"id": 104, "home": "COL", "away": "UZB", "score": {"home": 5, "away": 0}},
            {"id": 105, "home": "FRA", "away": "SEN", "score": {"home": 5, "away": 0}},
            {"id": 106, "home": "URU", "away": "KSA", "score": {"home": 4, "away": 1}},
            {"id": 107, "home": "BRA", "away": "MOR", "score": {"home": 5, "away": 0}},
            {"id": 108, "home": "POR", "away": "COD", "score": {"home": 6, "away": 0}},
            {"id": 109, "home": "SWI", "away": "QAT", "score": {"home": 2, "away": 1}},
            {"id": 110, "home": "MEX", "away": "RSA", "score": {"home": 2, "away": 2}},
            {"id": 111, "home": "ENG", "away": "HAI", "score": {"home": 4, "away": 1}},
            {"id": 112, "home": "ARG", "away": "JOR", "score": {"home": 4, "away": 0}},
            {"id": 113, "home": "NED", "away": "TUN", "score": {"home": 4, "away": 1}},
            {"id": 114, "home": "BEL", "away": "ALG", "score": {"home": 5, "away": 1}},
            {"id": 115, "home": "USA", "away": "PAR", "score": {"home": 3, "away": 1}},
            {"id": 116, "home": "CAN", "away": "ECU", "score": {"home": 2, "away": 0}}
        ],
        2: [
            {"id": 201, "home": "GER", "away": "NOR", "score": {"home": 3, "away": 1}},
            {"id": 202, "home": "SPA", "away": "COL", "score": {"home": 3, "away": 0}},
            {"id": 203, "home": "FRA", "away": "URU", "score": {"home": 4, "away": 0}},
            {"id": 204, "home": "BRA", "away": "POR", "score": {"home": 1, "away": 1}},
            {"id": 205, "home": "ENG", "away": "ARG", "score": {"home": 1, "away": 0}},
            {"id": 206, "home": "NED", "away": "BEL", "score": {"home": 2, "away": 2}},
            {"id": 207, "home": "USA", "away": "CAN", "score": {"home": 0, "away": 2}},
            {"id": 208, "home": "CUW", "away": "IRQ", "score": {"home": 2, "away": 0}},
            {"id": 209, "home": "CPV", "away": "UZB", "score": {"home": 0, "away": 1}},
            {"id": 210, "home": "SEN", "away": "KSA", "score": {"home": 4, "away": 2}},
            {"id": 211, "home": "MOR", "away": "COD", "score": {"home": 2, "away": 0}},
            {"id": 212, "home": "SWI", "away": "MEX", "score": {"home": 2, "away": 2}},
            {"id": 213, "home": "QAT", "away": "RSA", "score": {"home": 2, "away": 2}},
            {"id": 214, "home": "HAI", "away": "JOR", "score": {"home": 2, "away": 1}},
            {"id": 215, "home": "TUN", "away": "ALG", "score": {"home": 0, "away": 1}},
            {"id": 216, "home": "PAR", "away": "ECU", "score": {"home": 2, "away": 0}}
        ],
        3: [
            {"id": 301, "home": "GER", "away": "IRQ", "score": {"home": 4, "away": 1}},
            {"id": 302, "home": "SPA", "away": "UZB", "score": {"home": 5, "away": 0}},
            {"id": 303, "home": "FRA", "away": "KSA", "score": {"home": 6, "away": 0}},
            {"id": 304, "home": "BRA", "away": "COD", "score": {"home": 6, "away": 1}},
            {"id": 305, "home": "ENG", "away": "JOR", "score": {"home": 4, "away": 1}},
            {"id": 306, "home": "NED", "away": "ALG", "score": {"home": 3, "away": 0}},
            {"id": 307, "home": "USA", "away": "ECU", "score": {"home": 2, "away": 1}},
            {"id": 308, "home": "NOR", "away": "CUW", "score": {"home": 4, "away": 0}},
            {"id": 309, "home": "COL", "away": "CPV", "score": {"home": 5, "away": 0}},
            {"id": 310, "home": "URU", "away": "SEN", "score": {"home": 4, "away": 0}},
            {"id": 311, "home": "POR", "away": "MOR", "score": {"home": 4, "away": 0}},
            {"id": 312, "home": "SWI", "away": "RSA", "score": {"home": 0, "away": 1}},
            {"id": 313, "home": "MEX", "away": "QAT", "score": {"home": 2, "away": 1}},
            {"id": 314, "home": "CAN", "away": "PAR", "score": {"home": 2, "away": 0}},
            {"id": 315, "home": "BEL", "away": "TUN", "score": {"home": 3, "away": 0}},
            {"id": 316, "home": "CRO", "away": "JPN", "score": {"home": 3, "away": 0}}
        ]
    }
    
    conceded_gw1 = {
        "GER": 0, "CUW": 5, "SPA": 1, "CPV": 4, "NOR": 1, "IRQ": 3, "COL": 0, "UZB": 5,
        "FRA": 0, "SEN": 5, "URU": 1, "KSA": 4, "BRA": 0, "MOR": 5, "POR": 0, "COD": 6,
        "SWI": 1, "QAT": 2, "MEX": 2, "RSA": 2, "ENG": 1, "HAI": 4, "ARG": 0, "JOR": 4,
        "NED": 1, "TUN": 4, "BEL": 1, "ALG": 5, "USA": 1, "PAR": 3, "CAN": 0, "ECU": 2
    }
    conceded_gw2 = {
        "GER": 1, "NOR": 3, "SPA": 0, "COL": 3, "FRA": 0, "URU": 4, "BRA": 1, "POR": 1,
        "ENG": 0, "ARG": 1, "NED": 2, "BEL": 2, "USA": 2, "CAN": 0, "CUW": 0, "IRQ": 2,
        "CPV": 1, "UZB": 0, "SEN": 2, "KSA": 4, "MOR": 0, "COD": 2, "SWI": 2, "MEX": 2,
        "QAT": 2, "RSA": 2, "HAI": 1, "JOR": 2, "TUN": 1, "ALG": 0, "PAR": 0, "ECU": 2
    }
    conceded_gw3 = {
        "GER": 1, "IRQ": 4, "SPA": 0, "UZB": 5, "FRA": 0, "KSA": 6, "BRA": 1, "COD": 6,
        "ENG": 1, "JOR": 4, "NED": 0, "ALG": 3, "USA": 1, "ECU": 2, "NOR": 0, "CUW": 4,
        "COL": 0, "CPV": 5, "URU": 0, "SEN": 4, "POR": 0, "MOR": 4, "SWI": 1, "RSA": 0,
        "MEX": 1, "QAT": 2, "CAN": 0, "PAR": 2, "BEL": 0, "TUN": 3, "CRO": 0, "JPN": 3
    }
    
    events_gw1 = [
        ("Pedri", "goal"), ("Aymeric Laporte", "goal"), ("Borja Iglesias", "goal"),
        ("Borja Iglesias", "assist"), ("Willy Semedo", "goal"), ("E. Haaland", "goal"),
        ("Amir Al Ammari", "assist"), ("J. Rodríguez", "assist"), ("A. Tchouaméni", "assist"),
        ("Kylian Mbappé", "goal"), ("O. Dembélé", "assist"), ("A. Rabiot", "goal"),
        ("A. Rabiot", "assist"), ("D. Núñez", "goal"), ("Gabriel Martinelli", "goal"),
        ("Raphinha", "goal"), ("Gonçalo Ramos", "goal"), ("Gonçalo Ramos", "goal"),
        ("João Neves", "goal"), ("João Neves", "assist"), ("Rúben Neves", "goal"),
        ("A. Jashari", "assist"), ("P. Foden", "goal"), ("E. Anderson", "assist")
    ]
    events_gw2 = [
        ("Borja Iglesias", "goal"), ("Aymeric Laporte", "goal"), ("Mikel Oyarzabal", "goal"),
        ("A. Tchouaméni", "goal"), ("A. Rabiot", "assist"), ("Gabriel Martinelli", "goal"),
        ("Gabriel Magalhães", "assist"), ("A. Amenda", "assist"), ("B. Dia", "goal"),
        ("O. O'runov", "goal")
    ]
    events_gw3 = [
        ("Borja Iglesias", "goal"), ("Yeremy Pino", "goal"), ("Lamine Yamal", "goal"),
        ("O. Dembélé", "goal"), ("O. Dembélé", "goal"), ("O. Dembélé", "assist"),
        ("M. Olise", "assist"), ("A. Rabiot", "assist"), ("A. Tchouaméni", "assist"),
        ("Vinícius Júnior", "goal"), ("Vinícius Júnior", "assist"), ("Endrick", "goal"),
        ("Raphinha", "goal"), ("J. Stones", "goal"), ("J. Bowen", "goal"),
        ("J. Bowen", "assist"), ("C. Gakpo", "goal"), ("B. Aaronson", "assist"),
        ("E. Haaland", "goal"), ("J. Rodríguez", "goal"), ("J. Rodríguez", "assist"),
        ("A. Canobbio", "goal"), ("A. Canobbio", "goal"), ("Gonçalo Ramos", "goal"),
        ("Gonçalo Ramos", "goal"), ("Rúben Neves", "assist"), ("António Silva", "goal")
    ]

    all_drafted_players = {}
    for uid, squad in squads.items():
        for p in squad:
            all_drafted_players[int(p["id"])] = p

    # Set up lineups for GW1, GW2, GW3
    for uid, squad in squads.items():
        squad_rich = [{"playerId": int(p["id"]), "position": p["position"]} for p in squad]
        for gw in (1, 2, 3):
            lineup = select_lineup(squad_rich)
            db.collection("leagues").document(mock_lid).collection("lineups").document(f"{uid}_{gw}").set(lineup)

    gw_params = {
        1: (events_gw1, conceded_gw1),
        2: (events_gw2, conceded_gw2),
        3: (events_gw3, conceded_gw3)
    }

    # Run game engine sequential finalization
    for gw in (1, 2, 3):
        print(f"🎬 Processing GW {gw}...")
        events, conceded_map = gw_params[gw]
        
        # Write un-processed fixtures first
        for f in fixtures_data[gw]:
            db.collection("wc_fixtures").document(str(f["id"])).set({
                "id": f["id"],
                "gw": gw,
                "wcRound": f"Group Stage · MD{gw}",
                # team ids MUST match the synthetic team_id passed to
                # build_team_raw_stats below (home=1, away=2). process_fixture
                # resolves is_home via homeTeam.id == team_id; without these ids
                # is_home is always False and home-side goals-conceded/clean-sheet
                # are computed against the wrong team's score.
                "homeTeam": {"id": 1, "isoCode": f["home"], "name": f["home"]},
                "awayTeam": {"id": 2, "isoCode": f["away"], "name": f["away"]},
                "kickoff": SERVER_TIMESTAMP,
                "status": "FT",
                "score": f["score"],
                "processedForFantasy": False
            })
            
            # Construct raw_stats for process_fixture
            home_team = f["home"]
            away_team = f["away"]
            
            home_players = [p for p in all_drafted_players.values() if p["teamIso"] == home_team]
            away_players = [p for p in all_drafted_players.values() if p["teamIso"] == away_team]
            
            # Synthetic per-player stats are built by the module-level
            # build_team_raw_stats helper (see its docstring): realistic
            # api-sports shape, deterministic, and deliberately shaped so the
            # engine's DefCon + rating-bonus + 60' rules are observable.
            raw_stats = [
                build_team_raw_stats(1, home_players, events, conceded_map),
                build_team_raw_stats(2, away_players, events, conceded_map),
            ]
            
            # Call process_fixture
            process_fixture(f["id"], raw_stats, None, db)

        # Set league currentGw to gw so finalize_gw runs on the correct gw
        db.collection("leagues").document(mock_lid).update({"currentGw": gw})

        # Call finalize_gw with a real client so group-stage elimination
        # detection (runs at GW3) can populate wc_teams.status = "eliminated".
        finalize_gw(mock_lid, gw, db, _seed_wc_client(db))
        
    print(f"✅ Mock League {mock_lid} successfully seeded via the real engine!")

def seed_pre_draft_league(db, USER_UID, USER_NAME):
    pre_lid = "lg_pre_draft"
    print(f"📅 Seeding Pre-Draft League {pre_lid}...")

    # Idempotent re-seed: clear any pre-existing members so we never accumulate
    # stale managers (or duplicate/conflicting draft positions) across runs.
    for existing in db.collection("leagues").document(pre_lid).collection("members").get():
        existing.reference.delete()

    db.collection("leagues").document(pre_lid).set({
        "leagueId": pre_lid,
        "name": "World Cup Real Draft (7 Managers)",
        "inviteCode": "REALWC26",
        # The logged-in user owns/admins their real draft league so they can
        # start the draft and the season themselves.
        "adminUid": USER_UID,
        "format": "h2h",
        "status": "pre_draft",
        # Platform B is the REAL draft — its results are not simulated. Drives
        # the data-source banner (down | simulated | live) on the frontend.
        "simulated": False,
        "maxMembers": 7,
        "pickTimer": 30,
        "tradeApproval": "vote",
        "knockoutStartGw": 7,
        "leaguePhaseGws": [1, 2, 3, 4, 5, 6],
        "knockoutQualifiers": 4,
        "currentGw": None,
        "draftAt": "2026-06-08T18:00:00Z",
        "seasonStartedAt": None,
        "createdAt": SERVER_TIMESTAMP,
    })

    # 7 managers for the real draft: the logged-in user (also admin, drafts
    # first) plus 6 friends. We dedupe against USER_UID so the production seed
    # (which logs in as one of the named friends, e.g. u_roy/Roy) still yields
    # exactly 7 DISTINCT members instead of silently collapsing to 6.
    friend_pool = [
        {"uid": "u_roy",     "name": "Roy",     "team": "La Liga Loca",     "flag": "ESP"},
        {"uid": "u_yonatan", "name": "Yonatan", "team": "Tiki-Taka FC",     "flag": "ARG"},
        {"uid": "u_nadav",   "name": "Nadav",   "team": "Red Devils 2026",  "flag": "BRA"},
        {"uid": "u_yuval",   "name": "Yuval",   "team": "The Gunners",      "flag": "ENG"},
        {"uid": "u_ido",     "name": "Ido",     "team": "Tel Aviv United",  "flag": "FRA"},
        {"uid": "u_shai",    "name": "Shai",    "team": "McShaike's XI",    "flag": "MEX"},
        {"uid": "u_omer",    "name": "Omer",    "team": "Catenaccio Kings", "flag": "ITA"},
    ]
    friends = [f for f in friend_pool if f["uid"] != USER_UID][:6]
    roster = [{"uid": USER_UID, "name": USER_NAME,
               "team": f"{USER_NAME}'s XI", "flag": "POR"}] + friends

    mock_managers = []
    n = len(roster)
    for i, m in enumerate(roster):
        mock_managers.append({**m, "draftPos": i + 1, "waiverPri": n - i})

    for m in mock_managers:
        db.collection("leagues").document(pre_lid).collection("members").document(m["uid"]).set({
            "displayName": m["name"],
            "teamName": m["team"],
            "flag": m["flag"],
            "draftPosition": m["draftPos"],
            "waiverPriority": m["waiverPri"],
            "joinedAt": SERVER_TIMESTAMP,
        })
        
    print(f"✅ Pre-Draft League {pre_lid} successfully seeded!")

def seed_everything(db, user_uid, user_name):
    seed_tournament_data(db)
    seed_mock_league(db, user_uid, user_name)
    seed_pre_draft_league(db, user_uid, user_name)
