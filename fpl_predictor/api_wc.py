"""
WC2026 Fantasy Draft REST API — Flask Blueprint.

Register in api.py with: app.register_blueprint(wc_bp, url_prefix="/api/v1/wc")

Auth: Firebase ID token in Authorization: Bearer <token> header.
All endpoints return {"data": ..., "error": null} or {"data": null, "error": "..."}.
"""

import math
import os
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


def _require_admin():
    """Auth + admin-allowlist gate. Fails closed: a caller must be in
    wc_config/tournament.adminUids. The sole exception is a fresh emulator
    with no admins configured yet (bootstrap), so local dev can seed."""
    uid, err = _require_auth()
    if err:
        return None, err
    cfg = _db.collection("wc_config").document("tournament").get()
    admin_uids = (cfg.to_dict() or {}).get("adminUids", []) if cfg.exists else []
    if admin_uids:
        if uid not in admin_uids:
            return None, _err("Admin only", 403)
    elif not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return None, _err("Admin only", 403)
    return uid, None


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
    uid, err = _require_admin()
    if err:
        return err

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
    import unicodedata
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP
    
    # 1. Setup the mock league document
    mock_lid = "lg_mock_draft"
    db.collection("leagues").document(mock_lid).set({
        "leagueId": mock_lid,
        "name": "WC 2026 Expert Mock Draft",
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
    
    # 2. Setup mock managers with custom names, teams, and flags
    mock_managers = [
        {"uid": "u_roy", "name": "GoldenGoalFF", "team": "GoldenGoalFF's Squad", "flag": "EGY", "draftPos": 1, "waiverPri": 7},
        {"uid": "u_yonatan", "name": "FPLtfs", "team": "FPLtfs's Squad", "flag": "BRA", "draftPos": 2, "waiverPri": 6},
        {"uid": USER_UID, "name": USER_NAME, "team": "FPLFRAN's Squad", "flag": "SPA", "draftPos": 3, "waiverPri": 5},
        {"uid": "u_nadav", "name": "LloydHassell", "team": "LloydHassell's Squad", "flag": "ENG", "draftPos": 4, "waiverPri": 4},
        {"uid": "u_yuval", "name": "nordburfor", "team": "nordburfor's Squad", "flag": "TUN", "draftPos": 5, "waiverPri": 3},
        {"uid": "u_ido", "name": "FPLMate", "team": "FPLMate's Squad", "flag": "SCO", "draftPos": 6, "waiverPri": 2},
        {"uid": "u_shai", "name": "CantWinFPL", "team": "CantWinFPL's Squad", "flag": "TUR", "draftPos": 7, "waiverPri": 1},
        {"uid": "u_opponent", "name": "Opponent", "team": "Opponent XI", "flag": "GER", "draftPos": 8, "waiverPri": 8},
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
        
    # 3. Load mapped squad IDs from json
    squad_ids_path = os.path.join(os.path.dirname(__file__), "data", "squad_ids.json")
    with open(squad_ids_path, "r", encoding="utf-8") as f:
        squad_data_raw = json.load(f)
        
    squads = {}
    for k, v in squad_data_raw.items():
        uid = USER_UID if k == "USER_UID" else k
        squads[uid] = v
        
    # 4. Generate high-quality squad for Opponent XI using leftovers from wc_seeded_data.json
    seeded_json_path = os.path.join(os.path.dirname(__file__), "data", "wc_seeded_data.json")
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
    squads["u_opponent"] = []
    for idx, p in enumerate(opp_squad):
        squads["u_opponent"].append({
            "id": int(p["id"]),
            "name": p["name"],
            "position": p["position"],
            "positionName": p["positionName"],
            "teamIso": p["teamIso"]
        })
        
    # 5. Write squad allocations to Firestore
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
        
    # 6. Ensure missing star players are explicitly added to wc_players in Firestore
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
        
    # 7. Setup fixtures for GW1, GW2, GW3 (16 matches per gameweek)
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
    
    # Write fixtures to wc_fixtures in Firestore
    for gw, f_list in fixtures_data.items():
        for f in f_list:
            db.collection("wc_fixtures").document(str(f["id"])).set({
                "id": f["id"],
                "gw": gw,
                "wcRound": f"Group Stage · MD{gw}",
                "homeTeam": {"isoCode": f["home"], "name": f["home"]},
                "awayTeam": {"isoCode": f["away"], "name": f["away"]},
                "kickoff": SERVER_TIMESTAMP,
                "status": "FT",
                "score": f["score"],
                "processedForFantasy": True
            })
            
    # 8. Setup concession and event maps for organic point calculations
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
        
    def compute_player_points(gw, player, events, conceded_map):
        pts = 2
        team = player["teamIso"]
        conceded = conceded_map.get(team, 0)
        pos = player["position"]
        
        if conceded == 0:
            if pos in (1, 2): pts += 4
            elif pos == 3: pts += 1
            
        if pos in (1, 2) and conceded >= 2:
            pts -= (conceded // 2)
            
        goals_scored = 0
        assists_scored = 0
        for ev_name, ev_type in events:
            if match_player_event(player["name"], ev_name):
                if ev_type == "goal":
                    goals_scored += 1
                    if pos in (1, 2): pts += 6
                    elif pos == 3: pts += 5
                    elif pos == 4: pts += 4
                elif ev_type == "assist":
                    assists_scored += 1
                    pts += 3
                    
        return max(0, pts), goals_scored, assists_scored, (conceded == 0 and pos in (1, 2, 3))

    # Calculate points for all players across GW1-GW3
    player_gw_scores = {1: {}, 2: {}, 3: {}}
    player_total_points = {}
    
    gw_params = {
        1: (events_gw1, conceded_gw1, 100),
        2: (events_gw2, conceded_gw2, 200),
        3: (events_gw3, conceded_gw3, 300)
    }
    
    # Gather all player models in squads
    all_drafted_players = {}
    for uid, squad in squads.items():
        for p in squad:
            all_drafted_players[int(p["id"])] = p
            
    for gw in (1, 2, 3):
        events, conceded_map, offset = gw_params[gw]
        for pid, p in all_drafted_players.items():
            pts, goals, assists, cs = compute_player_points(gw, p, events, conceded_map)
            player_gw_scores[gw][pid] = pts
            player_total_points[pid] = player_total_points.get(pid, 0) + pts
            
            # Map player to their team's fixture
            assigned_fid = offset + 1
            for f in fixtures_data[gw]:
                if f["home"] == p["teamIso"] or f["away"] == p["teamIso"]:
                    assigned_fid = f["id"]
                    break
                    
            db.collection("wc_fixtures").document(str(assigned_fid)).collection("playerScores").document(str(pid)).set({
                "fantasyPoints": pts,
                "stats": {
                    "minutes": 90,
                    "goals": goals,
                    "assists": assists,
                    "cleanSheet": cs,
                    "yellowCard": 0,
                    "redCard": 0
                }
            })
            
    # Update totalPoints in wc_players
    for pid, tot_pts in player_total_points.items():
        db.collection("wc_players").document(str(pid)).update({
            "totalPoints": tot_pts
        })
        
    # 9. Generate and write starting XI / Lineups & aggregate scores
    lineups_by_manager_gw = {m["uid"]: {} for m in mock_managers}
    manager_scores_by_gw = {1: {}, 2: {}, 3: {}}
    
    for uid, squad in squads.items():
        # Map to playerId position representation
        squad_rich = [{"playerId": int(p["id"]), "position": p["position"]} for p in squad]
        for gw in (1, 2, 3):
            lineup = select_lineup(squad_rich)
            lineups_by_manager_gw[uid][gw] = lineup
            db.collection("leagues").document(mock_lid).collection("lineups").document(f"{uid}_{gw}").set(lineup)
            
            # Compute total score
            tot = 0
            starting = lineup["starting"]
            cap = lineup["captain"]
            for pid in starting:
                pid_int = int(pid)
                pts = player_gw_scores[gw].get(pid_int, 2) # Default 2 appearance pts
                if pid == cap:
                    tot += 2 * pts
                else:
                    tot += pts
            manager_scores_by_gw[gw][uid] = tot
            
    # Write H2H Match Schedule
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
        
    # Write Scores to Firestore
    for gw in (1, 2, 3):
        results = {}
        for uid in [m["uid"] for m in mock_managers]:
            results[uid] = {"points": manager_scores_by_gw[gw][uid]}
        db.collection("leagues").document(mock_lid).collection("scores").document(str(gw)).set({
            "processed": True,
            "processedAt": SERVER_TIMESTAMP,
            "results": results
        })
        
    # 10. Generate Organic Standings
    h2h_stats = {m["uid"]: {"hw": 0, "hd": 0, "hl": 0, "hpts": 0, "fpts": 0} for m in mock_managers}
    for gw in (1, 2, 3):
        for A, B in schedule_by_gw[gw]:
            ap = manager_scores_by_gw[gw][A]
            bp = manager_scores_by_gw[gw][B]
            h2h_stats[A]["fpts"] += ap
            h2h_stats[B]["fpts"] += bp
            if ap > bp:
                h2h_stats[A]["hw"] += 1
                h2h_stats[A]["hpts"] += 3
                h2h_stats[B]["hl"] += 1
            elif bp > ap:
                h2h_stats[B]["hw"] += 1
                h2h_stats[B]["hpts"] += 3
                h2h_stats[A]["hl"] += 1
            else:
                h2h_stats[A]["hd"] += 1
                h2h_stats[A]["hpts"] += 1
                h2h_stats[B]["hd"] += 1
                h2h_stats[B]["hpts"] += 1
                
    # Sort managers by H2H points, then fantasy points
    sorted_managers = sorted(mock_managers, key=lambda m: (h2h_stats[m["uid"]]["hpts"], h2h_stats[m["uid"]]["fpts"]), reverse=True)
    standings_managers = []
    for rank, m in enumerate(sorted_managers, 1):
        uid = m["uid"]
        stats = h2h_stats[uid]
        standings_managers.append({
            "uid": uid,
            "rank": rank,
            "hw": stats["hw"],
            "hd": stats["hd"],
            "hl": stats["hl"],
            "hpts": stats["hpts"],
            "fpts": stats["fpts"],
            "mv": 0,
            "knockedOut": False
        })
    db.collection("leagues").document(mock_lid).collection("standings").document("current").set({"managers": standings_managers})
    
    # 11. Seed Knockout Bracket with Top 4 Qualifiers
    bracket_data = {
        "seeds": [
            {"uid": standings_managers[0]["uid"], "seed": 1},
            {"uid": standings_managers[1]["uid"], "seed": 2},
            {"uid": standings_managers[2]["uid"], "seed": 3},
            {"uid": standings_managers[3]["uid"], "seed": 4},
        ],
        "rounds": {
            "sf": [
                {"id": "sf1", "home": standings_managers[0]["uid"], "away": standings_managers[3]["uid"], "homeSeed": 1, "awaySeed": 4, "gw": 4},
                {"id": "sf2", "home": standings_managers[1]["uid"], "away": standings_managers[2]["uid"], "homeSeed": 2, "awaySeed": 3, "gw": 4},
            ],
            "final": [
                {"id": "f1", "home": None, "away": None, "homeSrc": "sf1", "awaySrc": "sf2", "gw": 5}
            ]
        }
    }
    db.collection("leagues").document(mock_lid).collection("knockout").document("bracket").set(bracket_data)

@wc_bp.route("/admin/seed-test-leagues", methods=["POST"])
def admin_seed_test_leagues():
    uid, err = _require_admin()
    if err:
        return err
    # Refuse to (re)seed — which wipes leagues — against production unless
    # explicitly overridden. Emulator is always allowed.
    if not os.environ.get("FIRESTORE_EMULATOR_HOST") and os.environ.get("WC_ALLOW_PROD_SEED") != "true":
        return _err("Seeding is disabled against production. Set WC_ALLOW_PROD_SEED=true to override.", 403)
    try:
        import json
        json_path = os.path.join(os.path.dirname(__file__), "data", "wc_seeded_data.json")
        if not os.path.exists(json_path):
            return _err("wc_seeded_data.json not found in function package", 404)
            
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        teams = data.get("teams", [])
        players = data.get("players", [])

        # Register the seeding user as an admin so the bootstrap gate in
        # _require_admin self-closes after the first run.
        cfg_ref = _db.collection("wc_config").document("tournament")
        cfg_snap = cfg_ref.get()
        existing_admins = (cfg_snap.to_dict() or {}).get("adminUids", []) if cfg_snap.exists else []
        if uid not in existing_admins:
            cfg_ref.set({"adminUids": existing_admins + [uid]}, merge=True)

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
