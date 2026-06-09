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

# ---------------------------------------------------------------------------
# Real WC 2026 group-stage schedule — 3 rounds × 24 games (48 teams). isoCodes
# match the player pool's teamIso (e.g. SAU, JAP, IRA, TUR — NOT the old
# fabricated KSA/JPN). (fid, group, home_iso, away_iso). This is THE source of
# truth for the group fixtures; used by both the seed and the live rebuild.
# ---------------------------------------------------------------------------
GROUP_STAGE_SCHEDULE = {
    1: [
        (101, "A", "MEX", "RSA"), (102, "A", "KOR", "CZE"), (103, "B", "CAN", "BOS"),
        (104, "D", "USA", "PAR"), (105, "B", "QAT", "SWI"), (106, "C", "BRA", "MOR"),
        (107, "C", "HAI", "SCO"), (108, "D", "AUS", "TUR"), (109, "E", "GER", "CUW"),
        (110, "F", "NED", "JAP"), (111, "E", "CIV", "ECU"), (112, "F", "SWE", "TUN"),
        (113, "H", "SPA", "CPV"), (114, "G", "BEL", "EGY"), (115, "H", "SAU", "URU"),
        (116, "G", "IRA", "NZL"), (117, "I", "FRA", "SEN"), (118, "I", "IRQ", "NOR"),
        (119, "J", "ARG", "ALG"), (120, "J", "AUT", "JOR"), (121, "K", "POR", "COD"),
        (122, "L", "ENG", "CRO"), (123, "L", "GHA", "PAN"), (124, "K", "UZB", "COL"),
    ],
    2: [
        (201, "A", "CZE", "RSA"), (202, "B", "SWI", "BOS"), (203, "B", "CAN", "QAT"),
        (204, "A", "MEX", "KOR"), (205, "D", "USA", "AUS"), (206, "C", "SCO", "MOR"),
        (207, "C", "BRA", "HAI"), (208, "D", "TUR", "PAR"), (209, "F", "NED", "SWE"),
        (210, "E", "GER", "CIV"), (211, "E", "ECU", "CUW"), (212, "F", "TUN", "JAP"),
        (213, "H", "SPA", "SAU"), (214, "G", "BEL", "IRA"), (215, "H", "URU", "CPV"),
        (216, "G", "NZL", "EGY"), (217, "J", "ARG", "AUT"), (218, "I", "FRA", "IRQ"),
        (219, "I", "NOR", "SEN"), (220, "J", "JOR", "ALG"), (221, "K", "POR", "UZB"),
        (222, "L", "ENG", "GHA"), (223, "L", "PAN", "CRO"), (224, "K", "COL", "COD"),
    ],
    3: [
        (301, "B", "SWI", "CAN"), (302, "B", "BOS", "QAT"), (303, "C", "MOR", "HAI"),
        (304, "C", "SCO", "BRA"), (305, "A", "RSA", "KOR"), (306, "A", "CZE", "MEX"),
        (307, "E", "ECU", "GER"), (308, "E", "CUW", "CIV"), (309, "F", "TUN", "NED"),
        (310, "F", "JAP", "SWE"), (311, "D", "TUR", "USA"), (312, "D", "PAR", "AUS"),
        (313, "I", "NOR", "FRA"), (314, "I", "SEN", "IRQ"), (315, "H", "URU", "SPA"),
        (316, "H", "CPV", "SAU"), (317, "G", "NZL", "BEL"), (318, "G", "EGY", "IRA"),
        (319, "L", "CRO", "GHA"), (320, "L", "PAN", "ENG"), (321, "K", "COD", "UZB"),
        (322, "K", "COL", "POR"), (323, "J", "JOR", "ARG"), (324, "J", "ALG", "AUT"),
    ],
}


def _mock_scoreline(home, away, gw):
    """Deterministic, reproducible, plausible group-stage scoreline (slight home
    edge). Pure function of the matchup + gw so re-seeds/rebuilds are stable."""
    import hashlib
    g = lambda s: int(hashlib.md5(f"{s}-{gw}".encode()).hexdigest(), 16)
    return {"home": g(home + away) % 4, "away": g(away + home) % 3}


def seed_real_fixtures(db, drafted_players, events_by_gw, played_gws=(1, 2)):
    """Wipe wc_fixtures and write the real WC group-stage schedule (72 games).

    For each GW in ``played_gws``: write the fixture FT with a deterministic
    scoreline, synthesise per-player stats for the drafted players on each side,
    and run process_fixture -> playerScores. Other GWs are written UPCOMING
    (status NS, unprocessed). ``drafted_players`` maps pid -> {id,name,position,
    teamIso}. Returns counts. (Wiping first kills the duplicate/fabricated docs.)"""
    deleted = 0
    for fx in db.collection("wc_fixtures").get():
        for ps in fx.reference.collection("playerScores").get():
            ps.reference.delete()
        fx.reference.delete()
        deleted += 1

    written = 0
    for gw, games in GROUP_STAGE_SCHEDULE.items():
        played = gw in played_gws
        events = events_by_gw.get(gw, [])
        for fid, group, home, away in games:
            doc = {
                "id": fid, "gw": gw, "wcRound": f"Group Stage · MD{gw}", "group": group,
                "homeTeam": {"id": 1, "isoCode": home, "name": home},
                "awayTeam": {"id": 2, "isoCode": away, "name": away},
                "kickoff": SERVER_TIMESTAMP,
                "status": "FT" if played else "NS",
                "processedForFantasy": False,
            }
            if played:
                doc["score"] = _mock_scoreline(home, away, gw)
            db.collection("wc_fixtures").document(str(fid)).set(doc)
            written += 1
            if not played:
                continue
            home_players = [p for p in drafted_players.values() if p.get("teamIso") == home]
            away_players = [p for p in drafted_players.values() if p.get("teamIso") == away]
            raw_stats = [
                build_team_raw_stats(1, home_players, events, {}),
                build_team_raw_stats(2, away_players, events, {}),
            ]
            process_fixture(fid, raw_stats, None, db)
    return {"deleted": deleted, "written": written}


# Real per-GW goal/assist events (by player name) — give the stars attacking
# returns; players not on a scoring team are ignored by match_player_event.
GROUP_STAGE_EVENTS = {
    1: [
        ("Pedri", "goal"), ("Aymeric Laporte", "goal"), ("Borja Iglesias", "goal"),
        ("Borja Iglesias", "assist"), ("Willy Semedo", "goal"), ("E. Haaland", "goal"),
        ("Amir Al Ammari", "assist"), ("J. Rodríguez", "assist"), ("A. Tchouaméni", "assist"),
        ("Kylian Mbappé", "goal"), ("O. Dembélé", "assist"), ("A. Rabiot", "goal"),
        ("A. Rabiot", "assist"), ("D. Núñez", "goal"), ("Gabriel Martinelli", "goal"),
        ("Raphinha", "goal"), ("Gonçalo Ramos", "goal"), ("João Neves", "goal"),
        ("João Neves", "assist"), ("Rúben Neves", "goal"), ("P. Foden", "goal"),
        ("E. Anderson", "assist"),
    ],
    2: [
        ("Pedri", "goal"), ("Lamine Yamal", "goal"), ("Vinícius Júnior", "goal"),
        ("Raphinha", "assist"), ("Kylian Mbappé", "goal"), ("O. Dembélé", "goal"),
        ("E. Haaland", "goal"), ("Gonçalo Ramos", "goal"), ("J. Bowen", "goal"),
        ("C. Gakpo", "goal"), ("J. Rodríguez", "goal"), ("D. Núñez", "assist"),
    ],
    3: [
        ("Borja Iglesias", "goal"), ("Yeremy Pino", "goal"), ("Lamine Yamal", "goal"),
        ("O. Dembélé", "goal"), ("O. Dembélé", "assist"), ("M. Olise", "assist"),
        ("Vinícius Júnior", "goal"), ("Vinícius Júnior", "assist"), ("Endrick", "goal"),
        ("Raphinha", "goal"), ("J. Stones", "goal"), ("J. Bowen", "goal"),
        ("C. Gakpo", "goal"), ("E. Haaland", "goal"), ("J. Rodríguez", "goal"),
        ("Gonçalo Ramos", "goal"), ("Rúben Neves", "assist"), ("António Silva", "goal"),
    ],
}


def seed_mock_league(db, USER_UID, USER_NAME):
    mock_lid = "lg_mock_draft"
    print(f"🏆 Seeding Mock League {mock_lid}...")
    
    # 1. Setup Mock League metadata
    db.collection("leagues").document(mock_lid).set({
        "leagueId": mock_lid,
        "name": "WC 2026 Expert Mock Draft",
        "inviteCode": "MOCKWC26",
        "adminUid": "u_ilay",
        "format": "h2h",
        "status": "group_phase",  # Starts in group_phase, finalized sequentially
        # Platform A is the SIMULATION / time-machine. Drives the data-source
        # banner so the UI honestly shows "Simulated Data Mode".
        "simulated": True,
        "maxMembers": 6,
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
    # The showcase is LOCKED to 6 canonical managers (the real friend group).
    # u_ilay is the admin. (Previously this seeded 7 u_mk_* AI bots + the logged-
    # in user, which is how the live roster grew past 6.)
    mock_managers = [
        {"uid": "u_ilay",    "name": "Ilay",    "team": "Ilay's Squad",    "flag": "GER", "draftPos": 1, "waiverPri": 6},
        {"uid": "u_yuval",   "name": "Yuval",   "team": "Yuval's Squad",   "flag": "GER", "draftPos": 2, "waiverPri": 5},
        {"uid": "u_netanel", "name": "Netanel", "team": "Netanel's Squad", "flag": "GER", "draftPos": 3, "waiverPri": 4},
        {"uid": "u_shay",    "name": "Shay",    "team": "Shay's Squad",    "flag": "GER", "draftPos": 4, "waiverPri": 3},
        {"uid": "u_nadav",   "name": "Nadav",   "team": "Nadav's Squad",   "flag": "GER", "draftPos": 5, "waiverPri": 2},
        {"uid": "u_roy",     "name": "Roy",     "team": "Roy's Squad",     "flag": "GER", "draftPos": 6, "waiverPri": 1},
    ]

    for m in mock_managers:
        db.collection("leagues").document(mock_lid).collection("members").document(m["uid"]).set({
            "displayName": m["name"],
            "teamName": m["team"],
            "flag": m["flag"],
            "draftPosition": m["draftPos"],
            "waiverPriority": m["waiverPri"],
            "role": "admin" if m["uid"] == "u_ilay" else "manager",
            "joinedAt": SERVER_TIMESTAMP,
        })

    # 3. Load mapped squads — map the 6 stored squads (squad_ids.json keys) onto
    #    the 6 canonical managers deterministically.
    squad_ids_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "squad_ids.json")
    with open(squad_ids_path, "r", encoding="utf-8") as f:
        squad_data_raw = json.load(f)

    _SQUAD_KEY_FOR = {
        "u_ilay": "USER_UID", "u_yuval": "u_mk_golden", "u_netanel": "u_mk_fpltfs",
        "u_shay": "u_mk_lloyd", "u_nadav": "u_mk_nord", "u_roy": "u_mk_mate",
    }
    squads = {}
    for canon_uid, src_key in _SQUAD_KEY_FOR.items():
        if src_key in squad_data_raw:
            squads[canon_uid] = squad_data_raw[src_key]

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
        
    # 4. H2H schedule & events mapping — circle-method round-robin over the 6
    #    canonical managers (each faces a different opponent each GW).
    _order = [m["uid"] for m in mock_managers]
    schedule_by_gw = {}
    _arr = list(_order)
    for _r in range(3):
        schedule_by_gw[_r + 1] = [(_arr[i], _arr[len(_arr) - 1 - i]) for i in range(len(_arr) // 2)]
        _arr = [_arr[0]] + [_arr[-1]] + _arr[1:-1]
    
    for gw, matches in schedule_by_gw.items():
        match_list = [{"home": m[0], "away": m[1]} for m in matches]
        db.collection("leagues").document(mock_lid).collection("schedule").document(str(gw)).set({
            "gw": gw,
            "matches": match_list
        })
        
    all_drafted_players = {}
    for uid, squad in squads.items():
        for p in squad:
            all_drafted_players[int(p["id"])] = p

    # Set up lineups for GW1, GW2 (the played GWs; GW3 is upcoming).
    for uid, squad in squads.items():
        squad_rich = [{"playerId": int(p["id"]), "position": p["position"]} for p in squad]
        for gw in (1, 2):
            lineup = select_lineup(squad_rich)
            db.collection("leagues").document(mock_lid).collection("lineups").document(f"{uid}_{gw}").set(lineup)

    seed_real_fixtures(db, all_drafted_players, GROUP_STAGE_EVENTS, played_gws=(1, 2))

    # Finalize the PLAYED GWs (1 & 2) through the real engine, then pin the
    # canonical "before GW3" group-phase state (GW3 fixtures stay UPCOMING).
    for gw in (1, 2):
        db.collection("leagues").document(mock_lid).update({"currentGw": gw})
        finalize_gw(mock_lid, gw, db, _seed_wc_client(db))
    db.collection("leagues").document(mock_lid).update({"currentGw": 3, "status": "group_phase"})

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
