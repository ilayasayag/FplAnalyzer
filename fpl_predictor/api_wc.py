"""
WC2026 Fantasy Draft REST API — Flask Blueprint.

Register in api.py with: app.register_blueprint(wc_bp, url_prefix="/api/v1/wc")

Auth: Firebase ID token in Authorization: Bearer <token> header.
All endpoints return {"data": ..., "error": null} or {"data": null, "error": "..."}.
"""

import math
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from .data.wc_api import WC2026Client
from .game.wc_leagues import WCLeagueManager
from .game.wc_squads import WCSquadManager
from .game.wc_trades import WCTradeManager
from .game.wc_waivers import WCWaiverManager
from .game.wc_knockout import get_bracket, seed_knockout, advance_knockout_bracket
from .game.wc_scoring import finalize_gw, process_fixture
from .game.wc_gameweeks import (
    all_gws_as_dict, get_current_gw, is_locked, get_gw_config,
    compute_knockout_start_gw,
)


wc_bp = Blueprint("wc", __name__)


# ---------------------------------------------------------------------------
# Dependency injection — set in api.py after creating the Blueprint
# ---------------------------------------------------------------------------

_db = None
_wc: WC2026Client = None
_league_mgr: WCLeagueManager = None
_squad_mgr: WCSquadManager = None
_trade_mgr: WCTradeManager = None
_waiver_mgr: WCWaiverManager = None


def init_wc(db, firebase_auth=None):
    global _db, _wc, _league_mgr, _squad_mgr, _trade_mgr, _waiver_mgr
    _db = db
    _wc = WC2026Client(db=db)
    _league_mgr = WCLeagueManager(db)
    _squad_mgr = WCSquadManager(db, _wc)
    _trade_mgr = WCTradeManager(db, _wc)
    _waiver_mgr = WCWaiverManager(db, _wc)


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

def _require_auth():
    """Extract uid from Firebase ID token. Returns uid or raises."""
    from firebase_admin import auth as fb_auth
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, _err("Unauthorized", 401)
    token = auth_header[7:]
    try:
        decoded = fb_auth.verify_id_token(token)
        return decoded["uid"], None
    except Exception:
        return None, _err("Invalid token", 401)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _ok(data=None, status=200):
    return jsonify({"data": _clean(data), "error": None}), status


def _err(msg: str, status=400):
    return jsonify({"data": None, "error": msg}), status


def _clean(obj):
    if obj is None:
        return None
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


# ---------------------------------------------------------------------------
# §0 — Tournament config
# ---------------------------------------------------------------------------

# §0 — Tournament config
# ---------------------------------------------------------------------------

DEFAULT_RULES = {
    "scoring": {
        "appearUnder60": 1,
        "appear60Plus": 2,
        "goalPoints": {"1": 10, "2": 6, "3": 5, "4": 4},
        "assistPoints": 3,
        "csPoints": {"1": 4, "2": 4, "3": 1, "4": 0},
        "gcPointsPer2": {"1": -1, "2": -1, "3": 0, "4": 0},
        "yellowCardPoints": -1,
        "redCardPoints": -3,
        "ownGoalPoints": -2,
        "penaltyMissPoints": -2,
        "penaltySavePoints": 5,
        "savesPerPointGk": 3
    },
    "squadLimit": {
        "totalPlayers": 15,
        "gk": 2,
        "def": 5,
        "mid": 5,
        "fwd": 3
    },
    "leagueSize": {
        "minManagers": 6,
        "maxManagers": 10,
        "optimalMin": 6,
        "optimalMax": 10
    },
    "bonus": {
        "gwTopScorerH2HBonus": 1
    },
    "leaguePhase": {
        "format": "h2h",
        "customGameWeeksCount": None
    },
    "knockout": {
        "qualifiersCount": 4,
        "qualificationCriteria": {
            "h2hSlots": 2,
            "fptsSlots": 2
        },
        "structure": "sf"
    },
    "leagueSizeRules": {
        "6": { "knockoutStartGw": 7, "leaguePhaseGws": [1,2,3,4,5,6], "knockoutQualifiers": 4, "knockoutStructure": "sf" },
        "7": { "knockoutStartGw": 7, "leaguePhaseGws": [1,2,3,4,5,6], "knockoutQualifiers": 4, "knockoutStructure": "sf" },
        "8": { "knockoutStartGw": 7, "leaguePhaseGws": [1,2,3,4,5,6], "knockoutQualifiers": 4, "knockoutStructure": "sf" },
        "9": { "knockoutStartGw": 4, "leaguePhaseGws": [1,2,3], "knockoutQualifiers": 8, "knockoutStructure": "qf" },
        "10": { "knockoutStartGw": 4, "leaguePhaseGws": [1,2,3], "knockoutQualifiers": 8, "knockoutStructure": "qf" }
    }
}

def _merge_dicts(default_dict, custom_dict):
    """Recursively merge custom config on top of default config."""
    res = {}
    for k, v in default_dict.items():
        if k in custom_dict:
            if isinstance(v, dict) and isinstance(custom_dict[k], dict):
                res[k] = _merge_dicts(v, custom_dict[k])
            else:
                res[k] = custom_dict[k]
        else:
            res[k] = v
    # Add any extra keys present in custom_dict that were not in default_dict
    for k, v in custom_dict.items():
        if k not in res:
            res[k] = v
    return res

@wc_bp.route("/config", methods=["GET"])
def get_config():
    doc = _db.collection("wc_config").document("tournament").get()
    base = doc.to_dict() if doc.exists else {}
    custom_rules = base.get("rules", {})
    base["rules"] = _merge_dicts(DEFAULT_RULES, custom_rules)
    base["gwDates"] = all_gws_as_dict()
    base["currentGw"] = get_current_gw()
    return _ok(base)

@wc_bp.route("/config", methods=["POST", "PUT"])
def save_config():
    uid, err = _require_auth()
    if err:
        return err

    # admin gate — tournament config is global, not per-league.
    cfg = _db.collection("wc_config").document("tournament").get()
    admin_uids = (cfg.to_dict() or {}).get("adminUids", []) if cfg.exists else []
    if admin_uids and uid not in admin_uids:
        return _err("Admin only", 403)

    # Freeze config once the tournament starts
    from fpl_predictor.game.wc_gameweeks import is_locked
    if is_locked(1):   # GW1 kickoff has passed → tournament live
        return _err("Config is frozen once the tournament starts", 409)

    data = request.json or {}
    rules = data.get("rules")
    if not rules:
        return _err("Missing rules object", 400)
    if not isinstance(rules, dict):
        return _err("Rules must be a dictionary", 400)
    
    ref = _db.collection("wc_config").document("tournament")
    ref.set({"rules": rules}, merge=True)
    return _ok({"status": "ok", "rules": rules})




# ---------------------------------------------------------------------------
# §1 — Teams + Players (public data)
# ---------------------------------------------------------------------------

@wc_bp.route("/teams", methods=["GET"])
def list_teams():
    teams = _wc.get_all_teams(_db)
    return _ok(teams)


@wc_bp.route("/players", methods=["GET"])
def list_players():
    position = request.args.get("position", type=int)
    team_id = request.args.get("teamId", type=int)
    search = request.args.get("q", "").strip()
    limit = request.args.get("limit", 200, type=int)

    players = _wc.get_all_players(_db)

    if position:
        players = [p for p in players if p.get("position") == position]
    if team_id:
        players = [p for p in players if p.get("teamId") == team_id]
    if search:
        search_lower = search.lower()
        players = [p for p in players if search_lower in p.get("name", "").lower()]

    return _ok(players[:limit])


@wc_bp.route("/players/<int:player_id>", methods=["GET"])
def get_player(player_id: int):
    player = _wc.get_player(player_id, _db)
    if not player:
        return _err("Player not found", 404)
    return _ok(player)


# ---------------------------------------------------------------------------
# §2 — Fixtures
# ---------------------------------------------------------------------------

@wc_bp.route("/fixtures", methods=["GET"])
def list_fixtures():
    gw = request.args.get("gw", type=int)
    if gw:
        fixtures = _wc.get_gw_fixtures(gw, _db)
    else:
        docs = _db.collection("wc_fixtures").get()
        fixtures = [d.to_dict() for d in docs]
    return _ok(fixtures)


@wc_bp.route("/fixtures/live", methods=["GET"])
def live_fixtures():
    try:
        fixtures = _wc.get_live_fixtures()
    except Exception as exc:
        return _err(str(exc), 502)
    return _ok(fixtures)


@wc_bp.route("/fixtures/<int:fixture_id>/scores", methods=["GET"])
def fixture_scores(fixture_id: int):
    docs = (_db.collection("wc_fixtures").document(str(fixture_id))
            .collection("playerScores").get())
    scores = {int(d.id): d.to_dict() for d in docs}
    return _ok(scores)


# ---------------------------------------------------------------------------
# §3 — API usage stats (admin only)
# ---------------------------------------------------------------------------

@wc_bp.route("/api-usage", methods=["GET"])
def api_usage():
    uid, err = _require_auth()
    if err:
        return err
    today = datetime.now(timezone.utc).date().isoformat()
    doc = _db.collection("wc_api_usage").document(today).get()
    count = doc.to_dict().get("requests", 0) if doc.exists else 0
    return _ok({"date": today, "requests": count, "limit": 100, "inProcess": _wc.get_daily_usage()})


# ---------------------------------------------------------------------------
# §4 — Leagues
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues", methods=["POST"])
def create_league():
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    try:
        result = _league_mgr.create_league(
            uid=uid,
            name=body.get("name", ""),
            display_name=body.get("displayName", "Manager"),
            trade_approval=body.get("tradeApproval", "vote"),
            pick_timer=body.get("pickTimer", 60),
            max_members=body.get("maxMembers", 8),
        )
        return _ok(result, 201)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/join", methods=["POST"])
def join_league():
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    try:
        result = _league_mgr.join_league(
            uid=uid,
            invite_code=body.get("inviteCode", ""),
            display_name=body.get("displayName", "Manager"),
            team_name=body.get("teamName"),
        )
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/auth/me", methods=["POST", "GET"])
def auth_me():
    uid, err = _require_auth()
    if err:
        return err
        
    display_name = "Manager"
    photo_url = ""
    if request.method == "POST":
        body = request.get_json() or {}
        display_name = body.get("displayName") or display_name
        photo_url = body.get("photoUrl") or photo_url
    else:
        try:
            from firebase_admin import auth as fb_auth
            user_record = fb_auth.get_user(uid)
            display_name = user_record.display_name or user_record.email.split("@")[0]
        except Exception:
            pass

    user_ref = _db.collection("users").document(uid)
    user_doc = user_ref.get()
    
    mock_lid = "lg_mock_draft"
    pre_lid = "lg_pre_draft"
    leagues_list = [mock_lid, pre_lid]
    
    if user_doc.exists:
        ud = user_doc.to_dict() or {}
        existing_leagues = ud.get("leagues", [])
        updated_leagues = list(existing_leagues)
        for lid in leagues_list:
            if lid not in updated_leagues:
                updated_leagues.append(lid)
        
        user_ref.update({
            "displayName": display_name,
            "photoUrl": photo_url,
            "leagues": updated_leagues,
            "lastLogin": SERVER_TIMESTAMP
        })
    else:
        user_ref.set({
            "displayName": display_name,
            "photoUrl": photo_url,
            "leagues": leagues_list,
            "lastLogin": SERVER_TIMESTAMP,
            "createdAt": SERVER_TIMESTAMP
        })

    # Hydrate their membership in both test leagues if the leagues exist
    # 1. Hydrate lg_mock_draft
    mock_league_ref = _db.collection("leagues").document(mock_lid)
    mock_league_doc = mock_league_ref.get()
    if mock_league_doc.exists:
        member_ref = mock_league_ref.collection("members").document(uid)
        if not member_ref.get().exists:
            seed_mock_league(uid, display_name, _db)

    # 2. Hydrate lg_pre_draft
    pre_league_ref = _db.collection("leagues").document(pre_lid)
    pre_league_doc = pre_league_ref.get()
    if pre_league_doc.exists:
        member_ref = pre_league_ref.collection("members").document(uid)
        if not member_ref.get().exists:
            member_ref.set({
                "displayName": display_name,
                "teamName": "Hapoel Eliyahu",
                "draftPosition": 7,
                "waiverPriority": 7,
                "role": "manager",
                "joinedAt": SERVER_TIMESTAMP
            })

    return _ok({
        "uid": uid,
        "displayName": display_name,
        "photoUrl": photo_url,
        "leagues": leagues_list
    })


@wc_bp.route("/leagues/my", methods=["GET"])
def my_leagues():
    uid, err = _require_auth()
    if err:
        return err
    return _ok(_league_mgr.get_my_leagues(uid))


@wc_bp.route("/leagues/<lid>", methods=["GET"])
def get_league(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        return _ok(_league_mgr.get_league(lid, uid))
    except ValueError as exc:
        return _err(str(exc), 404)


@wc_bp.route("/leagues/<lid>", methods=["PATCH"])
def update_league(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        result = _league_mgr.update_league(lid, uid, request.get_json() or {})
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/lock", methods=["POST"])
def lock_league(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        result = _league_mgr.lock_for_draft(lid, uid)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/start-season", methods=["POST"])
def start_season(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        result = _league_mgr.start_season(lid, uid)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/kick", methods=["POST"])
def kick_member(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    target = body.get("targetUid")
    if not target:
        return _err("targetUid required")
    try:
        result = _league_mgr.kick_member(lid, uid, target)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/leave", methods=["POST"])
def leave_league(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        _league_mgr.leave_league(lid, uid)
        return _ok({"status": "left"})
    except ValueError as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# §5 — Draft
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues/<lid>/draft/state", methods=["GET"])
def get_draft_state(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    doc = (_db.collection("leagues").document(lid)
           .collection("draft").document("state").get())
    if not doc.exists:
        return _err("Draft not started", 404)
    return _ok({"leagueId": lid, **doc.to_dict()})


@wc_bp.route("/leagues/<lid>/draft/start", methods=["POST"])
def start_draft(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        from .game.draft import DraftEngine
        draft = DraftEngine(_db, _wc)
        result = draft.start_draft(lid, uid)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/draft/pick", methods=["POST"])
def make_pick(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    player_id = body.get("playerId")
    idempotency_key = body.get("idempotencyKey")
    if not player_id:
        return _err("playerId required")
    try:
        from .game.draft import DraftEngine
        draft = DraftEngine(_db, _wc)
        result = draft.make_pick(lid, uid, player_id, idempotency_key=idempotency_key)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/draft/watchlist", methods=["GET"])
def get_watchlist(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    doc = (_db.collection("leagues").document(lid)
           .collection("draft").document("watchlists")
           .collection(uid).document("list").get())
    players = doc.to_dict().get("playerIds", []) if doc.exists else []
    return _ok({"playerIds": players})


@wc_bp.route("/leagues/<lid>/draft/watchlist", methods=["PUT"])
def update_watchlist(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    player_ids = body.get("playerIds", [])
    (_db.collection("leagues").document(lid)
     .collection("draft").document("watchlists")
     .collection(uid).document("list")
     .set({"playerIds": player_ids, "updatedAt": SERVER_TIMESTAMP}))
    return _ok({"playerIds": player_ids})


# ---------------------------------------------------------------------------
# §6 — Squads
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues/<lid>/squads/<target_uid>", methods=["GET"])
def get_squad(lid: str, target_uid: str):
    uid, err = _require_auth()
    if err:
        return err
    squad = _squad_mgr.get_squad(lid, target_uid)
    return _ok({"leagueId": lid, "uid": target_uid, **squad})


@wc_bp.route("/leagues/<lid>/squads/me", methods=["GET"])
def get_my_squad(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    squad = _squad_mgr.get_squad(lid, uid)
    return _ok({"leagueId": lid, "uid": uid, **squad})


@wc_bp.route("/leagues/<lid>/squad/drop", methods=["POST"])
def drop_player(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    player_out = body.get("playerOut")
    if not player_out:
        return _err("playerOut required")
    try:
        result = _squad_mgr.drop_player(lid, uid, player_out)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# §7 — Lineup
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues/<lid>/lineup/<int:gw>", methods=["GET"])
def get_lineup(lid: str, gw: int):
    uid, err = _require_auth()
    if err:
        return err
    lineup = _squad_mgr.get_lineup(lid, uid, gw)
    locked = is_locked(gw)
    return _ok({"leagueId": lid, "uid": uid, "gw": gw, "locked": locked, **lineup})


@wc_bp.route("/leagues/<lid>/lineup/<target_uid>/<int:gw>", methods=["GET"])
def get_opponent_lineup(lid: str, target_uid: str, gw: int):
    uid, err = _require_auth()
    if err:
        return err
    if not is_locked(gw):
        return _err("Opponent lineup only visible after GW lockAt", 403)
    lineup = _squad_mgr.get_lineup(lid, target_uid, gw)
    return _ok({"leagueId": lid, "uid": target_uid, "gw": gw, "locked": True, **lineup})


@wc_bp.route("/leagues/<lid>/lineup/<int:gw>", methods=["PUT"])
def set_lineup(lid: str, gw: int):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    try:
        result = _squad_mgr.set_lineup(
            lid=lid,
            uid=uid,
            gw=gw,
            starting=body.get("starting", []),
            bench=body.get("bench", []),
            captain=body.get("captain"),
            vice_captain=body.get("viceCaptain"),
        )
        return _ok(result)
    except ValueError as exc:
        code = str(exc)
        if code in ("LINEUP_LOCKED", "SQUAD_INCOMPLETE"):
            return _err(code, 409)
        return _err(code)


# ---------------------------------------------------------------------------
# §8 — Scores + Standings
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues/<lid>/scores/<int:gw>", methods=["GET"])
def get_scores(lid: str, gw: int):
    uid, err = _require_auth()
    if err:
        return err
    doc = (_db.collection("leagues").document(lid)
           .collection("scores").document(str(gw)).get())
    if not doc.exists:
        return _ok({"leagueId": lid, "gw": gw, "results": {}, "processed": False})
    return _ok({"leagueId": lid, "gw": gw, **doc.to_dict()})


@wc_bp.route("/leagues/<lid>/standings", methods=["GET"])
def get_standings(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    doc = (_db.collection("leagues").document(lid)
           .collection("standings").document("current").get())
    if not doc.exists:
        return _ok({"leagueId": lid, "managers": []})
    return _ok({"leagueId": lid, **doc.to_dict()})


@wc_bp.route("/leagues/<lid>/schedule", methods=["GET"])
def get_schedule(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    gw = request.args.get("gw", type=int)
    if gw:
        doc = (_db.collection("leagues").document(lid)
               .collection("schedule").document(str(gw)).get())
        schedule = doc.to_dict() if doc.exists else {"gw": gw, "matches": []}
        return _ok({"leagueId": lid, **schedule})
    else:
        docs = (_db.collection("leagues").document(lid)
                .collection("schedule").get())
        all_gws = sorted([d.to_dict() for d in docs], key=lambda x: x.get("gw", 0))
        return _ok({"leagueId": lid, "schedule": all_gws})


# ---------------------------------------------------------------------------
# §9 — Transfer windows + Free agent pickups
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues/<lid>/transfer-window", methods=["GET"])
def get_transfer_window(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    windows = (_db.collection("leagues").document(lid)
               .collection("transfer_windows")
               .where("status", "==", "open").limit(1).get())
    if not windows:
        return _ok({"status": "closed", "window": None})
    w = windows[0].to_dict()
    w["windowId"] = windows[0].id
    return _ok({"status": "open", "window": w})


@wc_bp.route("/leagues/<lid>/free-agent", methods=["POST"])
def sign_free_agent(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    player_in = body.get("playerIn")
    player_out = body.get("playerOut")
    window_number = body.get("windowNumber", 1)
    if not player_in or not player_out:
        return _err("playerIn and playerOut required")
    try:
        result = _squad_mgr.sign_free_agent(lid, uid, player_in, player_out, window_number)
        return _ok(result)
    except ValueError as exc:
        code = str(exc)
        if code in ("PLAYER_ALREADY_OWNED", "WINDOW_CLOSED", "PLAYER_TEAM_ELIMINATED"):
            return _err(code, 409)
        return _err(code)


@wc_bp.route("/leagues/<lid>/free-agents", methods=["GET"])
def list_free_agents(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    position = request.args.get("position", type=int)
    search = request.args.get("q", "")
    limit = request.args.get("limit", 50, type=int)
    agents = _waiver_mgr.get_free_agents(lid, position=position, search=search, limit=limit)
    return _ok(agents)


# ---------------------------------------------------------------------------
# §10 — Waivers
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues/<lid>/waivers", methods=["POST"])
def submit_waiver(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    try:
        result = _waiver_mgr.submit_waiver(
            lid=lid,
            uid=uid,
            player_in=body.get("playerIn"),
            player_out=body.get("playerOut"),
            window_number=body.get("windowNumber", 1),
        )
        return _ok(result, 201)
    except ValueError as exc:
        code = str(exc)
        if "DUPLICATE_WAIVER" in code or "WAIVER_LIMIT" in code:
            return _err(code, 409)
        return _err(code)


@wc_bp.route("/leagues/<lid>/waivers", methods=["GET"])
def get_waivers(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    window_number = request.args.get("window", 1, type=int)
    waivers = _waiver_mgr.get_my_waivers(lid, uid, window_number)
    return _ok(waivers)


@wc_bp.route("/leagues/<lid>/waivers/<waiver_id>", methods=["DELETE"])
def cancel_waiver(lid: str, waiver_id: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        _waiver_mgr.cancel_waiver(lid, waiver_id, uid)
        return _ok({"status": "cancelled"})
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/waivers/order", methods=["GET"])
def waiver_order(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    order = _waiver_mgr.get_waiver_order(lid)
    return _ok({"leagueId": lid, "waiverOrder": order})


@wc_bp.route("/leagues/<lid>/waivers/order/reset", methods=["POST"])
def reset_waiver_order(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        _waiver_mgr.reset_waiver_priority_to_standings(lid, uid)
        return _ok({"status": "reset"})
    except ValueError as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# §11 — Trades
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues/<lid>/trades", methods=["GET"])
def list_trades(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    status = request.args.get("status")
    trades = _trade_mgr.get_trades(lid, status=status)
    return _ok(trades)


@wc_bp.route("/leagues/<lid>/trades", methods=["POST"])
def propose_trade(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    try:
        result = _trade_mgr.propose_trade(
            lid=lid,
            proposer_uid=uid,
            target_uid=body.get("targetUid", ""),
            proposer_player_ids=body.get("proposerPlayerIds", []),
            target_player_ids=body.get("targetPlayerIds", []),
            message=body.get("message", ""),
        )
        return _ok(result, 201)
    except ValueError as exc:
        code = str(exc)
        if "PLAYER_MID_FIXTURE" in code or "TRADE_LIMIT" in code:
            return _err(code, 409)
        return _err(code)


@wc_bp.route("/leagues/<lid>/trades/<trade_id>/respond", methods=["POST"])
def respond_trade(lid: str, trade_id: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json() or {}
    action = body.get("action")
    if action not in ("accept", "decline"):
        return _err("action must be 'accept' or 'decline'")
    try:
        result = _trade_mgr.respond_trade(lid, trade_id, uid, action)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/trades/<trade_id>/veto", methods=["POST"])
def veto_trade(lid: str, trade_id: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        result = _trade_mgr.cast_veto(lid, trade_id, uid)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/trades/<trade_id>/cancel", methods=["POST"])
def cancel_trade(lid: str, trade_id: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        result = _trade_mgr.cancel_trade(lid, trade_id, uid)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/trades/<trade_id>/admin-approve", methods=["POST"])
def admin_approve_trade(lid: str, trade_id: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        result = _trade_mgr.admin_approve(lid, trade_id, uid)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# §12 — Knockout bracket
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues/<lid>/knockout", methods=["GET"])
def get_knockout(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    bracket = get_bracket(lid, _db)
    return _ok(bracket)


# ---------------------------------------------------------------------------
# §13 — Transactions log
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues/<lid>/transactions", methods=["GET"])
def get_transactions(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    limit = request.args.get("limit", 20, type=int)
    docs = (_db.collection("leagues").document(lid)
            .collection("transactions")
            .order_by("timestamp", direction="DESCENDING")
            .limit(limit)
            .get())
    txns = [{"id": d.id, **d.to_dict()} for d in docs]
    return _ok(txns)


# ---------------------------------------------------------------------------
# §14 — Admin / background operations
# ---------------------------------------------------------------------------

@wc_bp.route("/admin/sync-squads", methods=["POST"])
def admin_sync_squads():
    uid, err = _require_auth()
    if err:
        return err
    try:
        result = _wc.sync_all_squads(_db)
        return _ok(result)
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/sync-fixtures", methods=["POST"])
def admin_sync_fixtures():
    uid, err = _require_auth()
    if err:
        return err
    try:
        count = _wc.sync_fixtures(_db)
        return _ok({"fixturesWritten": count})
    except Exception as exc:
        return _err(str(exc), 500)

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
        "captain": captain,
        "viceCaptain": vice,
        "locked": True,
        "autoSubsMade": []
    }

def seed_mock_league(USER_UID, USER_NAME, db):
    import os
    import json
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP
    
    json_path = os.path.join(os.path.dirname(__file__), "data", "wc_seeded_data.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    teams = data.get("teams", [])
    players = data.get("players", [])
    
    mock_lid = "lg_mock_draft"
    db.collection("leagues").document(mock_lid).set({
        "leagueId": mock_lid,
        "name": "El Clásico Friends (Mock)",
        "inviteCode": "MOCKWC26",
        "adminUid": "u_roy",
        "format": "h2h",
        "status": "active",
        "maxMembers": 8,
        "pickTimer": 60,
        "tradeApproval": "vote",
        "knockoutStartGw": 4,
        "leaguePhaseGws": [1, 2, 3],
        "knockoutQualifiers": 4,
        "currentGw": 3,
        "draftAt": None,
        "seasonStartedAt": None,
        "createdAt": SERVER_TIMESTAMP,
    })
    
    mock_managers = [
        {"uid": "u_roy", "name": "Roy", "team": "La Liga Loca", "flag": "SPA", "draftPos": 1, "waiverPri": 6},
        {"uid": "u_yonatan", "name": "Yonatan", "team": "Tiki-Taka FC", "flag": "ARG", "draftPos": 2, "waiverPri": 5},
        {"uid": "u_nadav", "name": "Nadav", "team": "Red Devils 2026", "flag": "BRA", "draftPos": 3, "waiverPri": 4},
        {"uid": "u_yuval", "name": "Yuval", "team": "The Gunners", "flag": "ENG", "draftPos": 4, "waiverPri": 3},
        {"uid": "u_ido", "name": "Ido", "team": "Tel Aviv United", "flag": "FRA", "draftPos": 5, "waiverPri": 2},
        {"uid": "u_shai", "name": "Shai", "team": "McShaike's XI", "flag": "MEX", "draftPos": 6, "waiverPri": 1},
        {"uid": USER_UID, "name": USER_NAME, "team": "Hapoel Eliyahu", "flag": "POR", "draftPos": 7, "waiverPri": 7},
        {"uid": "u_opponent", "name": "Opponent", "team": "Opponent XI", "flag": "GER", "draftPos": 8, "waiverPri": 8},
    ]
    
    for m in mock_managers:
        db.collection("leagues").document(mock_lid).collection("members").document(m["uid"]).set({
            "displayName": m["name"],
            "teamName": m["team"],
            "draftPosition": m["draftPos"],
            "waiverPriority": m["waiverPri"],
            "joinedAt": SERVER_TIMESTAMP,
        })
        
    def get_player_quality(p):
        pid = p.get("id")
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
        return p.get("draftRank", 999) * 100000 + pid

    gks = sorted([p for p in players if p["position"] == 1], key=get_player_quality)
    defs = sorted([p for p in players if p["position"] == 2], key=get_player_quality)
    mids = sorted([p for p in players if p["position"] == 3], key=get_player_quality)
    fwds = sorted([p for p in players if p["position"] == 4], key=get_player_quality)
    
    draft_order = []
    for round_idx in range(1, 16):
        managers_round = ["u_roy", "u_yonatan", "u_nadav", "u_yuval", "u_ido", "u_shai", USER_UID, "u_opponent"]
        if round_idx % 2 == 0:
            managers_round.reverse()
        draft_order.extend(managers_round)
        
    squads = {m["uid"]: [] for m in mock_managers}
    pos_counts = {m["uid"]: {1: 0, 2: 0, 3: 0, 4: 0} for m in mock_managers}
    pos_limits = {1: 2, 2: 5, 3: 5, 4: 3}
    pools = {1: list(gks), 2: list(defs), 3: list(mids), 4: list(fwds)}
    
    for turn_idx, uid in enumerate(draft_order):
        round_num = (turn_idx // 8) + 1
        needed_pos = [pos for pos, limit in pos_limits.items() if pos_counts[uid][pos] < limit]
        
        best_player = None
        best_quality = float('inf')
        best_pos = None
        
        for pos in needed_pos:
            if pools[pos]:
                p = pools[pos][0]
                q = get_player_quality(p)
                if q < best_quality:
                    best_quality = q
                    best_player = p
                    best_pos = pos
                    
        if best_player:
            pools[best_pos].pop(0)
            squads[uid].append({
                "playerId": str(best_player["id"]),
                "draftedRound": round_num,
                "position": best_player["position"],
                "name": best_player["name"],
                "teamIso": best_player["teamIso"]
            })
            pos_counts[uid][best_pos] += 1
            
    for uid, squad in squads.items():
        squad_list = [{"playerId": p["playerId"], "draftedRound": p["draftedRound"]} for p in squad]
        db.collection("leagues").document(mock_lid).collection("squads").document(uid).set({
            "players": squad_list
        })
        
    lineups_by_manager_gw = {m["uid"]: {} for m in mock_managers}
    for uid, squad in squads.items():
        for gw in (1, 2, 3):
            lineup = select_lineup(squad)
            lineups_by_manager_gw[uid][gw] = lineup
            db.collection("leagues").document(mock_lid).collection("lineups").document(f"{uid}_{gw}").set(lineup)
            
    schedule_by_gw = {
        1: [("u_roy", "u_shai"), ("u_yonatan", "u_opponent"), ("u_nadav", "u_ido"), (USER_UID, "u_yuval")],
        2: [("u_roy", "u_opponent"), ("u_yonatan", "u_ido"), ("u_nadav", "u_yuval"), (USER_UID, "u_shai")],
        3: [("u_roy", "u_ido"), ("u_yonatan", "u_yuval"), ("u_opponent", "u_shai"), (USER_UID, "u_nadav")]
    }
    for gw, matches in schedule_by_gw.items():
        match_list = [{"home": m[0], "away": m[1]} for m in matches]
        db.collection("leagues").document(mock_lid).collection("schedule").document(str(gw)).set({
            "gw": gw,
            "matches": match_list
        })
        
    iso_to_team = {t["isoCode"]: t for t in teams}
    def get_team_or_default(iso, name):
        if iso in iso_to_team:
            return iso_to_team[iso]
        return {"id": 999, "name": name, "logo": "", "isoCode": iso}
        
    fixtures_data = {
        1: [
            {"id": 101, "home": "BRA", "away": "GER", "score": {"home": 2, "away": 1}},
            {"id": 102, "home": "FRA", "away": "ENG", "score": {"home": 1, "away": 1}},
            {"id": 103, "home": "ARG", "away": "SPA", "score": {"home": 2, "away": 2}}
        ],
        2: [
            {"id": 201, "home": "POR", "away": "NED", "score": {"home": 3, "away": 2}},
            {"id": 202, "home": "USA", "away": "URU", "score": {"home": 1, "away": 2}},
            {"id": 203, "home": "BEL", "away": "MEX", "score": {"home": 2, "away": 0}}
        ],
        3: [
            {"id": 301, "home": "BRA", "away": "FRA", "score": {"home": 1, "away": 2}},
            {"id": 302, "home": "ARG", "away": "ENG", "score": {"home": 2, "away": 1}},
            {"id": 303, "home": "SPA", "away": "POR", "score": {"home": 3, "away": 3}}
        ]
    }
    
    for gw, f_list in fixtures_data.items():
        for f in f_list:
            h_team = get_team_or_default(f["home"], f["home"])
            a_team = get_team_or_default(f["away"], f["away"])
            db.collection("wc_fixtures").document(str(f["id"])).set({
                "id": f["id"],
                "gw": gw,
                "wcRound": f"Group Stage · MD{gw}",
                "homeTeam": {"id": h_team["id"], "name": h_team["name"], "isoCode": h_team["isoCode"]},
                "awayTeam": {"id": a_team["id"], "name": a_team["name"], "isoCode": a_team["isoCode"]},
                "kickoff": SERVER_TIMESTAMP,
                "status": "FT",
                "score": f["score"],
                "processedForFantasy": True
            })
            
    player_gw_scores = {1: {}, 2: {}, 3: {}}
    for gw in (1, 2, 3):
        targets = {
            "u_roy": {1: 57, 2: 64, 3: 71}[gw],
            "u_yonatan": {1: 64, 2: 71, 3: 78}[gw],
            "u_nadav": {1: 71, 2: 78, 3: 58}[gw],
            "u_yuval": {1: 58, 2: 69, 3: 69}[gw],
            "u_ido": {1: 58, 2: 58, 3: 58}[gw],
            "u_shai": {1: 61, 2: 62, 3: 55}[gw],
            USER_UID: {1: 65, 2: 58, 3: 65}[gw],
            "u_opponent": {1: 72, 2: 72, 3: 55}[gw]
        }
        for uid, target in targets.items():
            lineup = lineups_by_manager_gw[uid][gw]
            starting = lineup["starting"]
            captain = lineup["captain"]
            
            cap_base = 8 if target > 60 else 6
            remaining = target - (2 * cap_base)
            
            num_others = len(starting) - 1
            base_share = remaining // num_others
            leftover = remaining % num_others
            
            for pid in starting:
                if pid == captain:
                    player_gw_scores[gw][pid] = cap_base
                else:
                    pts = base_share
                    if leftover > 0:
                        pts += 1
                        leftover -= 1
                    player_gw_scores[gw][pid] = pts
            for pid in lineup["bench"]:
                player_gw_scores[gw][pid] = 1 if int(pid) % 2 == 0 else 0
                
    for gw in (1, 2, 3):
        fixtures_in_gw = [101, 102, 103] if gw == 1 else ([201, 202, 203] if gw == 2 else [301, 302, 303])
        for uid, squad in squads.items():
            for p in squad:
                pid = p["playerId"]
                pts = player_gw_scores[gw].get(pid, 0)
                pos = p["position"]
                
                assigned_fid = fixtures_in_gw[0]
                for fid in fixtures_in_gw:
                    f_data = next(f for f in fixtures_data[gw] if f["id"] == fid)
                    if f_data["home"] == p["teamIso"] or f_data["away"] == p["teamIso"]:
                        assigned_fid = fid
                        break
                        
                db.collection("wc_fixtures").document(str(assigned_fid)).collection("playerScores").document(str(pid)).set({
                    "fantasyPoints": pts,
                    "stats": {
                        "minutes": 90 if pts > 0 else 0,
                        "goals": 1 if pts >= 5 else 0,
                        "assists": 1 if pts >= 4 else 0,
                        "cleanSheet": True if pts >= 4 and pos == 2 else False,
                        "yellowCard": 0,
                        "redCard": 0
                    }
                })
                
    for gw in (1, 2, 3):
        results = {
            "u_roy": {"points": {1: 57, 2: 64, 3: 71}[gw]},
            "u_yonatan": {"points": {1: 64, 2: 71, 3: 78}[gw]},
            "u_nadav": {"points": {1: 71, 2: 78, 3: 58}[gw]},
            "u_yuval": {"points": {1: 58, 2: 69, 3: 69}[gw]},
            "u_ido": {"points": {1: 58, 2: 58, 3: 58}[gw]},
            "u_shai": {"points": {1: 61, 2: 62, 3: 55}[gw]},
            USER_UID: {"points": {1: 65, 2: 58, 3: 65}[gw]},
            "u_opponent": {"points": {1: 72, 2: 72, 3: 55}[gw]}
        }
        db.collection("leagues").document(mock_lid).collection("scores").document(str(gw)).set({
            "processed": True,
            "processedAt": SERVER_TIMESTAMP,
            "results": results
        })
        
    standings_data = {
        "managers": [
            {"uid": "u_opponent", "rank": 1, "hw": 2, "hd": 1, "hl": 0, "hpts": 7, "fpts": 199, "mv": 0},
            {"uid": "u_shai", "rank": 2, "hw": 2, "hd": 1, "hl": 0, "hpts": 7, "fpts": 178, "mv": 0},
            {"uid": "u_yonatan", "rank": 3, "hw": 2, "hd": 0, "hl": 1, "hpts": 6, "fpts": 213, "mv": 0},
            {"uid": "u_nadav", "rank": 4, "hw": 2, "hd": 0, "hl": 1, "hpts": 6, "fpts": 207, "mv": 0},
            {"uid": USER_UID, "rank": 5, "hw": 2, "hd": 0, "hl": 1, "hpts": 6, "fpts": 188, "mv": 0},
            {"uid": "u_roy", "rank": 6, "hw": 1, "hd": 0, "hl": 2, "hpts": 3, "fpts": 192, "mv": 0},
            {"uid": "u_yuval", "rank": 7, "hw": 0, "hd": 0, "hl": 3, "hpts": 0, "fpts": 196, "mv": 0},
            {"uid": "u_ido", "rank": 8, "hw": 0, "hd": 0, "hl": 3, "hpts": 0, "fpts": 174, "mv": 0},
        ]
    }
    db.collection("leagues").document(mock_lid).collection("standings").document("current").set(standings_data)
    
    bracket_data = {
        "seeds": [
            {"uid": "u_opponent", "seed": 1},
            {"uid": "u_shai", "seed": 2},
            {"uid": "u_yonatan", "seed": 3},
            {"uid": USER_UID, "seed": 4},
        ],
        "rounds": {
            "sf": [
                {"id": "sf1", "home": "u_opponent", "away": USER_UID, "homeSeed": 1, "awaySeed": 4, "gw": 4},
                {"id": "sf2", "home": "u_shai", "away": "u_yonatan", "homeSeed": 2, "awaySeed": 3, "gw": 4},
            ],
            "final": [
                {"id": "f1", "home": None, "away": None, "homeSrc": "sf1", "awaySrc": "sf2", "gw": 5}
            ]
        }
    }
    db.collection("leagues").document(mock_lid).collection("knockout").document("bracket").set(bracket_data)

@wc_bp.route("/admin/seed-test-leagues", methods=["POST"])
def admin_seed_test_leagues():
    secret = request.args.get("secret")
    is_admin = False
    if secret == "73314c7b7198d9a5f4248e44a1fb63c9":
        is_admin = True
        uid = "u_roy"
        
    if not is_admin:
        uid, err = _require_auth()
        if err:
            return err
    try:
        import os
        import json
        json_path = os.path.join(os.path.dirname(__file__), "data", "wc_seeded_data.json")
        if not os.path.exists(json_path):
            return _err("wc_seeded_data.json not found in function package", 404)
            
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        teams = data.get("teams", [])
        players = data.get("players", [])
        
        # Write teams to production
        for t in teams:
            _db.collection("wc_teams").document(str(t["id"])).set(t)
            
        # Write players to production
        for p in players:
            _db.collection("wc_players").document(str(p["id"])).set(p)
            
        # Get user UID from auth
        USER_UID = uid
        USER_NAME = "Ilay"
        try:
            from firebase_admin import auth
            user_record = auth.get_user(USER_UID)
            USER_NAME = user_record.display_name or user_record.email.split("@")[0]
        except Exception:
            pass
            
        # Force complete delete of mock league to trigger fresh seed
        mock_league_ref = _db.collection("leagues").document("lg_mock_draft")
        for sub_name in ["members", "squads", "lineups", "scores", "standings", "knockout", "schedule"]:
            coll = mock_league_ref.collection(sub_name)
            for doc in coll.get():
                doc.reference.delete()
        mock_league_ref.delete()
        
        # Now run seed immediately for the current user
        seed_mock_league(USER_UID, USER_NAME, _db)
        
        # Seed Real Pre-Draft League
        PRE_LID = "lg_pre_draft"
        _db.collection("leagues").document(PRE_LID).set({
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
            "createdAt": SERVER_TIMESTAMP,
        })
        
        # Seed 6 mock managers so there is exactly 1 slot left for the real user to join!
        mock_managers = [
            {"uid": "u_roy",     "name": "Roy",       "team": "La Liga Loca",     "flag": "SPA", "draftPos": 1, "waiverPri": 6},
            {"uid": "u_yonatan", "name": "Yonatan",   "team": "Tiki-Taka FC",     "flag": "ARG", "draftPos": 2, "waiverPri": 5},
            {"uid": "u_nadav",   "name": "Nadav",     "team": "Red Devils 2026", "flag": "BRA", "draftPos": 3, "waiverPri": 4},
            {"uid": "u_yuval",   "name": "Yuval",     "team": "The Gunners",      "flag": "ENG", "draftPos": 4, "waiverPri": 3},
            {"uid": "u_ido",     "name": "Ido",       "team": "Tel Aviv United",  "flag": "FRA", "draftPos": 5, "waiverPri": 2},
            {"uid": "u_shai",    "name": "Shai",      "team": "McShaike's XI",   "flag": "MEX", "draftPos": 6, "waiverPri": 1},
        ]
        for m in mock_managers:
            _db.collection("leagues").document(PRE_LID).collection("members").document(m["uid"]).set({
                "displayName": m["name"],
                "teamName": m["team"],
                "draftPosition": m["draftPos"],
                "waiverPriority": m["waiverPri"],
                "joinedAt": SERVER_TIMESTAMP,
            })
            
        return _ok({"status": "seeded"})
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/process-fixture/<int:fixture_id>", methods=["POST"])
def admin_process_fixture(fixture_id: int):
    uid, err = _require_auth()
    if err:
        return err
    try:
        raw_stats = _wc.get_fixture_player_stats(fixture_id, use_cache=False)
        results = process_fixture(fixture_id, raw_stats, _wc, _db)
        return _ok({"fixtureId": fixture_id, "playersScored": len(results)})
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/leagues/<lid>/finalize-gw/<int:gw>", methods=["POST"])
def admin_finalize_gw(lid: str, gw: int):
    uid, err = _require_auth()
    if err:
        return err
    try:
        result = finalize_gw(lid, gw, _db, _wc)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/leagues/<lid>/process-waivers/<int:window_number>", methods=["POST"])
def admin_process_waivers(lid: str, window_number: int):
    uid, err = _require_auth()
    if err:
        return err
    try:
        result = _waiver_mgr.process_waivers(lid, window_number)
        return _ok(result)
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/detect-eliminations", methods=["POST"])
def admin_detect_eliminations():
    uid, err = _require_auth()
    if err:
        return err
    try:
        result = _wc.detect_group_stage_eliminations(_db)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/leagues/<lid>/expire-trades", methods=["POST"])
def admin_expire_trades(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    _trade_mgr.expire_stale_trades(lid)
    return _ok({"status": "done"})


@wc_bp.route("/admin/set-tournament-result", methods=["POST"])
def admin_set_tournament_result():
    uid, err = _require_auth()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    winner = data.get("winner")          # national team id (string)
    top_scorer = data.get("topScorer")  # player id (int)

    if winner is not None and not isinstance(winner, str):
        return _err("winner must be a string team ID", 400)
    if top_scorer is not None and not isinstance(top_scorer, int):
        return _err("topScorer must be an integer player ID", 400)

    try:
        ref = _db.collection("wc_config").document("tournament")
        update_data = {}
        if winner is not None:
            update_data["winner"] = winner
        if top_scorer is not None:
            update_data["topScorer"] = top_scorer
        
        if update_data:
            ref.set(update_data, merge=True)
            
        return _ok({"status": "updated", "winner": winner, "topScorer": top_scorer})
    except Exception as exc:
        return _err(str(exc), 500)


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

@wc_bp.route("/leagues/<lid>/predictions", methods=["PUT"])
def set_predictions(lid: str):
    """
    Set a manager's pre-tournament predictions.
    Locked once GW1 starts (at GW1 lockAt).
    Body: {"predictedWinner": "team_id", "predictedTopScorer": 12345}
    """
    uid, err = _require_auth()
    if err:
        return err

    if is_locked(1):
        return _err("Predictions are locked once GW1 starts", 400)

    data = request.get_json(silent=True) or {}
    predicted_winner = data.get("predictedWinner")         # team id (string)
    predicted_top_scorer = data.get("predictedTopScorer")  # player id (int)

    league_ref = _db.collection("leagues").document(lid)
    member_ref = league_ref.collection("members").document(uid)
    if not member_ref.get().exists:
        return _err("Not a member of this league", 403)

    member_ref.update({
        "predictions.predictedWinner": predicted_winner,
        "predictions.predictedTopScorer": predicted_top_scorer,
        "predictions.predictionsLockedAt": SERVER_TIMESTAMP,
    })
    return _ok({
        "predictedWinner": predicted_winner,
        "predictedTopScorer": predicted_top_scorer,
    })


# ---------------------------------------------------------------------------
# Live fixture polling
# ---------------------------------------------------------------------------

def background_poll_and_process_fixtures():
    """Poll api-sports.io for live fixtures; process any that just went FT in the background."""
    if _wc is None or _db is None:
        return {"processed": [], "count": 0, "errors": [{"error": "Client or DB not initialized"}]}
    try:
        live = _wc.get_live_fixtures()
    except Exception as exc:
        return {"processed": [], "count": 0, "errors": [{"error": f"Failed to fetch live fixtures: {exc}"}]}

    processed = []
    errors = []
    for f in live:
        status = f.get("fixture", {}).get("status", {}).get("short", "")
        fid = f.get("fixture", {}).get("id")
        if not fid:
            continue
        if status in ("FT", "AET", "PEN"):
            doc = _db.collection("wc_fixtures").document(str(fid)).get()
            if doc.exists and doc.to_dict().get("processedForFantasy"):
                continue
            try:
                raw_stats = _wc.get_fixture_player_stats(fid, use_cache=False)
                process_fixture(fid, raw_stats, _wc, _db)
                processed.append(fid)
            except Exception as exc:
                errors.append({"fid": fid, "error": str(exc)})
                print(f"[warn] process-live fixture {fid}: {exc}")

    # Auto-finalize gameweeks for active leagues if all matches for the current gameweek are completed and processed
    try:
        leagues = _db.collection("leagues").get()
        for ldoc in leagues:
            lid = ldoc.id
            league = ldoc.to_dict()
            status = league.get("status")
            if status in ("complete", "pre_draft", "drafting"):
                continue
            cgw = league.get("currentGw")
            if not cgw:
                continue
            
            gw_fixtures = _db.collection("wc_fixtures").where("gw", "==", cgw).get()
            if not gw_fixtures:
                continue
            
            all_processed = all(f.to_dict().get("processedForFantasy") for f in gw_fixtures)
            if all_processed:
                try:
                    print(f"[Background Poller] Auto-finalizing GW {cgw} for league {lid}...")
                    finalize_gw(lid, cgw, _db, _wc)
                    processed.append(f"finalize_gw_{lid}_gw{cgw}")
                except Exception as f_exc:
                    print(f"[warn] Auto-finalize failed for league {lid} GW {cgw}: {f_exc}")
                    errors.append({"lid": lid, "gw": cgw, "error": str(f_exc)})
    except Exception as exc:
        print(f"[warn] Failed during leagues auto-finalization check: {exc}")
        errors.append({"error": f"Failed leagues auto-finalization check: {exc}"})

    return {"processed": processed, "count": len(processed), "errors": errors}


@wc_bp.route("/admin/process-live-fixtures", methods=["POST"])
def admin_process_live_fixtures():
    """
    Poll api-sports.io for live fixtures; process any that just went FT.
    Run every 5 minutes on match days (Cloud Scheduler or cron).
    """
    uid, err = _require_auth()
    if err:
        return err

    res = background_poll_and_process_fixtures()
    # If it failed to fetch live fixtures and got an error, propagate it
    if res.get("errors") and not res.get("processed"):
        err_msg = res["errors"][0].get("error", "")
        if "Failed to fetch live" in err_msg:
            return _err(err_msg, 500)

    return _ok(res)
