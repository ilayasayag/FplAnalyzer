"""
WC2026 Fantasy Draft REST API — Flask Blueprint.

Register in api.py with: app.register_blueprint(wc_bp, url_prefix="/api/v1/wc")

Auth: Firebase ID token in Authorization: Bearer <token> header.
All endpoints return {"data": ..., "error": null} or {"data": null, "error": "..."}.
"""

import logging
import math
import os
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g
from firebase_admin import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from .data.wc_api import WC2026Client
from .game.wc_leagues import WCLeagueManager
from .game.wc_squads import WCSquadManager
from .game.wc_trades import WCTradeManager
from .game.wc_waivers import WCWaiverManager
from .game.wc_wishlist import WCWishlistManager
from .game.wc_knockout import get_bracket, seed_knockout, advance_knockout_bracket
from .game.wc_scoring import finalize_gw, process_fixture
from .game.wc_gameweeks import (
    all_gws_as_dict, get_current_gw, is_locked, get_gw_config,
    compute_knockout_start_gw,
)
from .seed.seed_league import seed_everything, seed_mock_league


wc_bp = Blueprint("wc", __name__)

log = logging.getLogger("wc_api")


# ---------------------------------------------------------------------------
# Dependency injection — set in api.py after creating the Blueprint
# ---------------------------------------------------------------------------

_db = None
_wc: WC2026Client = None
_league_mgr: WCLeagueManager = None
_squad_mgr: WCSquadManager = None
_trade_mgr: WCTradeManager = None
_waiver_mgr: WCWaiverManager = None
_wishlist_mgr: WCWishlistManager = None
_sim = None

# The WC 2026 mock-draft showcase (lg_mock_draft) is locked to these 6 canonical
# managers. Used to (a) gate login auto-hydration so the roster can't regrow past
# 6, and (b) drive the one-shot roster-reset admin endpoint.
MOCK_LID = "lg_mock_draft"
MOCK_CANONICAL_ROSTER = ("u_ilay", "u_yuval", "u_netanel", "u_shay", "u_nadav", "u_roy")


def init_wc(db, firebase_auth=None):
    global _db, _wc, _league_mgr, _squad_mgr, _trade_mgr, _waiver_mgr, _wishlist_mgr, _sim
    _db = db
    _wc = WC2026Client(db=db)
    _league_mgr = WCLeagueManager(db)
    _squad_mgr = WCSquadManager(db, _wc)
    _trade_mgr = WCTradeManager(db, _wc)
    _waiver_mgr = WCWaiverManager(db, _wc)
    _wishlist_mgr = WCWishlistManager(db, _wc)
    from .game.draft_simulator import DraftSimulator
    _sim = DraftSimulator(db, _wc)


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
        "savesPerPointGk": 3,
        "defConPoints": 2,
        "defConThresholdDef": 10,
        "defConThresholdMid": 12,
        "bonusByRatingRank": [3, 2, 1]
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

    data = request.get_json(silent=True) or {}
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
    limit = request.args.get("limit", 2000, type=int)

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


@wc_bp.route("/players/<int:player_id>/scores", methods=["GET"])
def get_player_scores(player_id: int):
    # Collection-group query needs a composite index; before any match is scored
    # the collection group may not exist yet. Either case should surface as an
    # empty list (benign "no match data yet" empty-state in the modal), NOT a 500
    # that the client renders as an error (GAP-502).
    try:
        docs = _db.collection_group("playerScores").where("playerId", "==", player_id).get()
    except Exception as exc:
        print(f"[warn] player scores query failed for {player_id}: {exc}")
        return _ok([])

    # Resolve the player's own team so we can name the OPPONENT for each GW
    # (VT-106 #47): the opponent is whichever side of the parent fixture is NOT
    # the player's team. Reading the parent fixture also lets us (a) drop orphaned
    # playerScores whose fixture was deleted and (b) collapse to one row per GW
    # (a player features in at most one fixture per GW) — both kill the duplicate
    # GW1 rows the modal History tab showed.
    player_doc = _db.collection("wc_players").document(str(player_id)).get()
    pdata = player_doc.to_dict() or {}
    own_team_id = pdata.get("teamId")
    own_iso = (pdata.get("teamIso") or "").strip().upper()
    team_map = _wc.get_team_map(_db)

    def _iso_of(side):
        iso = (side.get("isoCode") or "").strip().upper()
        if not iso and side.get("id") is not None:
            resolved = team_map.get(int(side["id"]))
            iso = _team_display_iso(resolved) if resolved else ""
        return iso

    by_gw = {}
    for d in docs:
        rec = d.to_dict()
        fix_ref = d.reference.parent.parent  # playerScores/{pid} -> wc_fixtures/{fid}
        fix_doc = fix_ref.get() if fix_ref is not None else None
        if not (fix_doc and fix_doc.exists):
            continue  # orphan score (fixture deleted) — skip
        fix = fix_doc.to_dict() or {}
        gw = rec.get("gw", fix.get("gw"))
        home = fix.get("homeTeam") or {}
        away = fix.get("awayTeam") or {}
        home_iso, away_iso = _iso_of(home), _iso_of(away)
        # Identify the player's own side by team id first, then iso. Legacy
        # fixtures drifted the numeric teamId but kept the isoCode, so the id
        # match alone misses them; the iso fallback recovers the opponent.
        opp = None
        if own_team_id is not None and home.get("id") == own_team_id:
            opp = away_iso
        elif own_team_id is not None and away.get("id") == own_team_id:
            opp = home_iso
        elif own_iso and home_iso == own_iso:
            opp = away_iso
        elif own_iso and away_iso == own_iso:
            opp = home_iso
        if opp:
            rec["opponent"] = opp
        # One row per GW. Prefer a row whose opponent resolved over one that
        # didn't — legacy duplicate fixtures can put the same player in two GW
        # docs, only one of which has a reconcilable team id/iso.
        prev = by_gw.get(gw)
        if prev is None or (not prev.get("opponent") and rec.get("opponent")):
            by_gw[gw] = rec

    scores = sorted(by_gw.values(), key=lambda x: (x.get("gw") or 0))
    return _ok(scores)


# ---------------------------------------------------------------------------
# §2 — Fixtures
# ---------------------------------------------------------------------------

def _team_display_iso(team: dict) -> str:
    """The key the frontend uses to match a team: uppercased isoCode, falling
    back to short_name, then the numeric team id as a string. Mirrors the
    frontend's normalizeIso(p.teamIso || p.teamShort || String(p.teamId))."""
    if not team:
        return ""
    iso = (team.get("isoCode") or team.get("short_name") or "").strip()
    if not iso:
        tid = team.get("id")
        iso = str(tid) if tid is not None else ""
    return iso.upper()


def _enrich_fixtures_with_iso(fixtures: list, team_map: dict) -> list:
    """Stored fixtures carry team ids but an empty isoCode (see sync_fixtures).
    Resolve homeTeam/awayTeam isoCode from the team map so the client can key
    fixtures by the same iso it uses for players. Pure + idempotent."""
    for fx in fixtures or []:
        for side in ("homeTeam", "awayTeam"):
            t = fx.get(side)
            if not isinstance(t, dict):
                continue
            if not (t.get("isoCode") or "").strip():
                tid = t.get("id")
                resolved = team_map.get(int(tid)) if tid is not None else None
                if resolved:
                    t["isoCode"] = _team_display_iso(resolved)
    return fixtures


@wc_bp.route("/fixtures", methods=["GET"])
def list_fixtures():
    gw = request.args.get("gw", type=int)
    if gw:
        fixtures = _wc.get_gw_fixtures(gw, _db)
    else:
        docs = _db.collection("wc_fixtures").get()
        fixtures = [d.to_dict() for d in docs]
    fixtures = _enrich_fixtures_with_iso(fixtures, _wc.get_team_map(_db))
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


@wc_bp.route("/gameweeks", methods=["GET"])
def list_gameweeks():
    docs = _db.collection("wc_gameweeks").get()
    gws = [d.to_dict() for d in docs]
    gws.sort(key=lambda x: x.get("gw", 0))
    return _ok(gws)


@wc_bp.route("/group-standings", methods=["GET"])
def list_group_standings():
    docs = _db.collection("wc_group_standings").get()
    result = {d.id: d.to_dict().get("teams", []) for d in docs}
    return _ok(result)


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
    body = request.get_json(silent=True) or {}
    try:
        result = _league_mgr.create_league(
            uid=uid,
            name=body.get("name", ""),
            display_name=body.get("displayName", "Manager"),
            trade_approval=body.get("tradeApproval", "vote"),
            pick_timer=body.get("pickTimer", 30),
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
    body = request.get_json(silent=True) or {}
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
        body = request.get_json(silent=True) or {}
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
    # 1. lg_mock_draft — the showcase is LOCKED to its 6 canonical managers.
    #    Only those uids are (re)added on login; every other account is NOT
    #    auto-joined, so the roster can never regrow past 6. We also no longer
    #    re-run seed_mock_league here (it would re-create the legacy u_mk_* AI
    #    opponents). A missing canonical member just gets a lightweight member
    #    doc — never a full re-seed.
    mock_league_ref = _db.collection("leagues").document(mock_lid)
    mock_league_doc = mock_league_ref.get()
    if mock_league_doc.exists and uid in MOCK_CANONICAL_ROSTER:
        member_ref = mock_league_ref.collection("members").document(uid)
        if not member_ref.get().exists:
            try:
                member_ref.set({
                    "displayName": display_name,
                    "teamName": f"{display_name}'s Squad",
                    "role": "manager",
                    "joinedAt": SERVER_TIMESTAMP,
                })
            except Exception as exc:
                log.warning("Mock league hydration failed for %s: %s", uid, exc)

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
        result = _league_mgr.update_league(lid, uid, request.get_json(silent=True) or {})
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
    body = request.get_json(silent=True) or {}
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
    # Delegate to the engine so the response includes currentDrafter (snake
    # position resolved server-side) and the picks subcollection. The frontend
    # Draft Room reads data.currentDrafter / isMyTurn directly — returning the
    # raw doc here would leave both undefined and brick the room.
    from .game.draft import DraftEngine
    draft = DraftEngine(_db, _wc)
    state = draft.get_draft_state(lid)
    if state.get("status") == "pending":
        return _err("Draft not started", 404)
    return _ok({"leagueId": lid, **state})


@wc_bp.route("/leagues/<lid>/draft/start", methods=["POST"])
def start_draft(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        from .game.draft import DraftEngine
        draft = DraftEngine(_db, _wc)
        cfg_doc = _db.collection("wc_config").document("tournament").get()
        current_gw = cfg_doc.to_dict().get("currentGw", 1) if cfg_doc.exists else 1
        result = draft.start_draft(lid, uid, current_gw)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/draft/pick", methods=["POST"])
def make_pick(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json(silent=True) or {}
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


@wc_bp.route("/leagues/<lid>/draft/auto-pick", methods=["POST"])
def auto_pick(lid: str):
    """Fire the best-available auto-pick when the on-the-clock manager's
    deadline has expired. ANY authenticated league member may call this — it's
    a cooperative watchdog: typically the frontend timer of whoever is watching
    the room fires it, but a scheduled fallback could too. The engine itself
    enforces `time.time() >= pickDeadline`, so a premature call returns 400."""
    uid, err = _require_auth()
    if err:
        return err
    try:
        from .game.draft import DraftEngine
        draft = DraftEngine(_db, _wc)
        result = draft.auto_pick(lid)
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
    body = request.get_json(silent=True) or {}
    # Dedupe preserving order: a player may occupy only ONE watchlist position per
    # manager (one player per pick slot; the same player can't sit in two slots).
    player_ids = list(dict.fromkeys(body.get("playerIds", [])))
    (_db.collection("leagues").document(lid)
     .collection("draft").document("watchlists")
     .collection(uid).document("list")
     .set({"playerIds": player_ids, "updatedAt": SERVER_TIMESTAMP}))
    return _ok({"playerIds": player_ids})


def _require_sim_league(lid: str):
    """Auth + simulated-only guard for the draft-simulator endpoints. These are
    mock-testing tools that mutate (and reset() wipes) squads/draft state, so
    they must never be callable anonymously or against a real league. Returns
    ``(league_dict, None)`` on success or ``(None, error_response)``."""
    uid, err = _require_auth()
    if err:
        return None, err
    snap = _db.collection("leagues").document(lid).get()
    if not snap.exists:
        return None, _err("League not found", 404)
    ld = snap.to_dict() or {}
    if not ld.get("simulated"):
        return None, _err("MOCK_ONLY: the draft simulator only runs on simulated leagues", 403)
    return ld, None


@wc_bp.route("/leagues/<lid>/draft/sim/toggle", methods=["POST"])
def toggle_draft_sim(lid: str):
    _, err = _require_sim_league(lid)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    active = body.get("active", False)
    if active:
        _sim.start(lid)
    else:
        _sim.stop(lid)
    return _ok({"active": _sim.active, "status": _sim.last_status})


@wc_bp.route("/leagues/<lid>/draft/sim/state", methods=["GET"])
def get_draft_sim_state(lid: str):
    _, err = _require_sim_league(lid)
    if err:
        return err
    return _ok({"active": _sim.active, "status": _sim.last_status})


@wc_bp.route("/leagues/<lid>/draft/sim/reset", methods=["POST"])
def reset_draft_sim(lid: str):
    _, err = _require_sim_league(lid)
    if err:
        return err
    _sim.stop()
    league_ref = _db.collection("leagues").document(lid)
    state_ref = league_ref.collection("draft").document("state")
    if state_ref.get().exists:
        for pick in state_ref.collection("picks").get():
            pick.reference.delete()
        state_ref.delete()
    for sq in league_ref.collection("squads").get():
        sq.reference.delete()
    league_ref.update({"status": "pre_draft", "draftComplete": False})
    return _ok({"status": "reset"})


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
    body = request.get_json(silent=True) or {}
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
    body = request.get_json(silent=True) or {}
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


@wc_bp.route("/leagues/<lid>/gw-history/<uid>", methods=["GET"])
def get_gw_history(lid: str, uid: str):
    """Per-manager GW snapshot (lineup IDs joined to GW points). ``uid`` may
    be the literal ``me`` to mean the caller. Requires ?gw=<int>."""
    caller, err = _require_auth()
    if err:
        return err
    if uid == "me":
        uid = caller
    gw_raw = request.args.get("gw")
    if gw_raw is None:
        return _err("gw query param required")
    try:
        gw = int(gw_raw)
    except (TypeError, ValueError):
        return _err("gw must be an integer")
    doc = (_db.collection("leagues").document(lid)
           .collection("gw_history").document(f"{uid}_{gw}").get())
    if not doc.exists:
        return _err("gw_history not found", 404)
    return _ok({"leagueId": lid, **doc.to_dict()})


@wc_bp.route("/leagues/<lid>/standings", methods=["GET"])
def get_standings(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    gw = request.args.get("gw")
    doc_id = str(gw) if gw else "current"
    doc = (_db.collection("leagues").document(lid)
           .collection("standings").document(doc_id).get())
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
    # Live gate: derive from wc_windows.current_window (the single source of
    # truth) instead of the legacy transfer_windows status flag, which is now
    # an audit-only record (see WC2026_WINDOWS_DESIGN.md §2.3).
    from fpl_predictor.game.wc_windows import TransferWindow, current_window_from_db
    window, upcoming_gw = current_window_from_db(lid, _db)
    league_snap = _db.collection("leagues").document(lid).get()
    league_doc = league_snap.to_dict() if league_snap.exists else {}
    overridden = bool((league_doc or {}).get("windowOverride"))
    if window == TransferWindow.NONE:
        return _ok({"status": "closed", "window": None, "overridden": overridden})
    return _ok({
        "status": "open",
        "window": {"phase": window.value, "gw": upcoming_gw},
        "overridden": overridden,
    })


@wc_bp.route("/me/admin", methods=["GET"])
def get_is_admin():
    """Report whether the caller is an admin, for UI gating only (no 403)."""
    uid, err = _require_auth()
    if err:
        return err
    cfg = _db.collection("wc_config").document("tournament").get()
    admin_uids = (cfg.to_dict() or {}).get("adminUids", []) if cfg.exists else []
    return _ok({"isAdmin": uid in admin_uids})


@wc_bp.route("/leagues/<lid>/admin/window-override", methods=["POST"])
def set_window_override(lid: str):
    """Admin-only: force (or clear) the league's transfer-window phase.

    Body ``{phase, gw}``. ``phase`` of None/""/"auto" clears the override and
    returns to the time-based fixture-clock logic. A valid phase forces that
    window. Echoes the resolved effective window so the client can update.

    Admin-only on real leagues; on ``simulated`` (mock) leagues any authenticated
    member can flip the window so the showcase window-switcher works.
    """
    uid, err = _require_auth()
    if err:
        return err
    league_ref = _db.collection("leagues").document(lid)
    league_snap = league_ref.get()
    if not league_snap.exists:
        return _err("League not found", 404)
    if not (league_snap.to_dict() or {}).get("simulated"):
        _, admin_err = _require_admin()
        if admin_err:
            return admin_err
    body = request.get_json(silent=True) or {}
    phase = body.get("phase")
    gw = body.get("gw")
    if phase in (None, "", "auto"):
        league_ref.update({"windowOverride": firestore.DELETE_FIELD})
    elif phase in {"none", "trade", "free_agents", "next_gw_bid"}:
        league_ref.update({"windowOverride": {"phase": phase, "gw": gw}})
    else:
        return _err(f"Invalid phase: {phase}", 400)

    from fpl_predictor.game.wc_windows import TransferWindow, current_window_from_db
    window, upcoming_gw = current_window_from_db(lid, _db)
    league_snap = league_ref.get()
    overridden = bool((league_snap.to_dict() or {}).get("windowOverride")) if league_snap.exists else False
    if window == TransferWindow.NONE:
        return _ok({"status": "closed", "window": None, "overridden": overridden})
    return _ok({
        "status": "open",
        "window": {"phase": window.value, "gw": upcoming_gw},
        "overridden": overridden,
    })


@wc_bp.route("/leagues/<lid>/free-agent", methods=["POST"])
def sign_free_agent(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json(silent=True) or {}
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
    body = request.get_json(silent=True) or {}
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
    body = request.get_json(silent=True) or {}
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


@wc_bp.route("/leagues/<lid>/wishlist-bids", methods=["POST"])
def submit_wishlist_bids(lid: str):
    """Submit an ORDERED list of same-position wishlist swap bids for a GW.

    Body: {gw, bids: [{playerIn, playerOut, position}, ...]}. Index 0 is tried
    first by the auction. Re-submission overwrites the manager's bid doc.
    """
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    try:
        gw = int(body.get("gw"))
    except (TypeError, ValueError):
        return _err("gw is required")
    try:
        result = _wishlist_mgr.submit_bids(lid, uid, gw, body.get("bids", []))
        return _ok(result, 201)
    except ValueError as exc:
        code = str(exc)
        if "ALREADY_OWNED" in code:
            return _err(code, 409)
        return _err(code)


@wc_bp.route("/leagues/<lid>/wishlist-bids/me", methods=["GET"])
def get_my_wishlist_bids(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    try:
        gw = int(request.args.get("gw"))
    except (TypeError, ValueError):
        return _err("gw query param is required")
    return _ok(_wishlist_mgr.get_my_bids(lid, uid, gw))


@wc_bp.route("/leagues/<lid>/trades/<trade_id>/respond", methods=["POST"])
def respond_trade(lid: str, trade_id: str):
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json(silent=True) or {}
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
    gw = request.args.get("gw")
    if gw:
        doc = (_db.collection("leagues").document(lid)
               .collection("knockout").document(f"bracket_gw{gw}").get())
        if doc.exists:
            return _ok({"leagueId": lid, **doc.to_dict()})
        else:
            return _ok({"leagueId": lid, "rounds": {}})
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


@wc_bp.route("/leagues/<lid>/wishlist-results", methods=["GET"])
def get_wishlist_results(lid: str):
    """Durable per-GW wishlist-auction records (ordered bids + claimed/cancelled
    outcome per manager). Survives the bids being deleted at auction time, so
    the wishlist history is viewable after the fact. Newest GW first."""
    uid, err = _require_auth()
    if err:
        return err
    docs = (_db.collection("leagues").document(lid)
            .collection("wishlist_results").get())
    out = [d.to_dict() for d in docs]
    out.sort(key=lambda r: r.get("gw", 0), reverse=True)
    return _ok({"results": out})


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
    # This is a legacy function. The engine uses seed_league's version.
    from .seed.seed_league import select_lineup as sl
    return sl(squad)

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
        # Get user UID from auth
        USER_UID = uid
        USER_NAME = "Ilay"
        try:
            from firebase_admin import auth
            user_record = auth.get_user(USER_UID)
            USER_NAME = user_record.display_name or user_record.email.split("@")[0]
        except Exception:
            pass
            
        # Register the seeding user as an admin so the bootstrap gate in
        # _require_admin self-closes after the first run.
        cfg_ref = _db.collection("wc_config").document("tournament")
        cfg_snap = cfg_ref.get()
        existing_admins = (cfg_snap.to_dict() or {}).get("adminUids", []) if cfg_snap.exists else []
        if uid not in existing_admins:
            cfg_ref.set({"adminUids": existing_admins + [uid]}, merge=True)

        # Force complete delete of mock league to trigger fresh seed
        mock_league_ref = _db.collection("leagues").document("lg_mock_draft")
        for sub_name in ["members", "squads", "lineups", "scores", "standings", "knockout", "schedule"]:
            coll = mock_league_ref.collection(sub_name)
            for doc in coll.get():
                doc.reference.delete()
        mock_league_ref.delete()
        
        # Force complete delete of pre draft league
        pre_league_ref = _db.collection("leagues").document("lg_pre_draft")
        for sub_name in ["members", "squads", "lineups", "scores", "standings", "knockout", "schedule"]:
            coll = pre_league_ref.collection(sub_name)
            for doc in coll.get():
                doc.reference.delete()
        pre_league_ref.delete()

        # Run consolidated seed everything
        seed_everything(_db, USER_UID, USER_NAME)
        
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


@wc_bp.route("/admin/leagues/<lid>/simulate", methods=["POST"])
def admin_simulate_tournament(lid: str):
    """Generate a random World Cup for ``lid`` and drive it through the real
    scoring engine. Body (all optional JSON):
      ``seed``     int  — RNG seed for reproducible runs.
      ``startGw``  int  — first GW to generate (default 1).
      ``endGw``    int  — last GW to generate  (default 8).
      ``reset``    bool — wipe prior fixtures/scores first (default true).

    Returns the per-GW summary + the persisted tournament export. This is the
    "forward" generator; backward navigation just reads the per-GW snapshots
    that every finalized GW already writes.
    """
    uid, err = _require_admin()
    if err:
        return err
    from .seed.wc_simulator import simulate_tournament
    body = request.get_json(silent=True) or {}
    try:
        result = simulate_tournament(
            _db, lid,
            seed=body.get("seed"),
            start_gw=int(body.get("startGw", 1)),
            end_gw=int(body.get("endGw", 8)),
            reset=bool(body.get("reset", True)),
            wc_client=_wc,
        )
        # Keep the response light — the full export is persisted in Firestore.
        return _ok({"league": lid, "gws": result["gws"],
                    "managers": result["export"].get("managers", {})})
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/leagues/<lid>/simulate-gw", methods=["POST"])
def admin_simulate_one_gw(lid: str):
    """Generate + score + finalize a SINGLE gameweek (the "play next week"
    button). Body (optional JSON): ``gw`` (defaults to the league's currentGw),
    ``seed`` (reproducible RNG). Returns the GW summary + new currentGw so the
    client can advance week-by-week."""
    uid, err = _require_admin()
    if err:
        return err
    from .seed.wc_simulator import simulate_one_gw
    body = request.get_json(silent=True) or {}
    try:
        gw = body.get("gw")
        result = simulate_one_gw(
            _db, lid,
            gw=int(gw) if gw is not None else None,
            seed=body.get("seed"),
            wc_client=_wc,
        )
        return _ok(result)
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/leagues/<lid>/sim-reset", methods=["POST"])
def admin_sim_reset(lid: str):
    """Wipe the league's simulation state back to a fresh GW1 (deletes fixtures
    + playerScores, resets player/team flags, clears scores/standings/history/
    lineups/knockout/windows). Members, squads and the H2H schedule survive."""
    uid, err = _require_admin()
    if err:
        return err
    from .seed.wc_simulator import reset_simulation
    try:
        reset_simulation(_db, lid)
        return _ok({"league": lid, "currentGw": 1, "status": "group_phase"})
    except Exception as exc:
        return _err(str(exc), 500)


def _round_robin(uids, num_rounds):
    """Circle-method H2H pairings: each manager faces a different opponent each
    round. ``uids`` must be even-length. Returns {round: [(home, away), ...]}."""
    arr = list(uids)
    n = len(arr)
    rounds = {}
    for r in range(num_rounds):
        rounds[r + 1] = [(arr[i], arr[n - 1 - i]) for i in range(n // 2)]
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]   # rotate all but the first
    return rounds


@wc_bp.route("/admin/leagues/<lid>/reset-to-roster", methods=["POST"])
def admin_reset_to_roster(lid: str):
    """MOCK-ONLY one-shot: collapse the showcase league back to its 6 canonical
    managers and roll the season to BEFORE GW3 (GW1 + GW2 finalized).

    - Deletes every non-canonical member + their squad / lineups / wishlist bids
      (the legacy u_mk_* AI bots and any stray real joiners). The 6 canonical
      managers' squads are KEPT untouched.
    - Drops malformed wc_players docs (no position) — the "UNDEFINED" pool junk.
    - Clears the knockout bracket + GW>=3 scores/history, writes a fresh
      6-manager H2H schedule, and re-finalizes GW1 then GW2 so scores + standings
      are clean for exactly the 6. Lands at currentGw=3, group_phase.
    Idempotent. Gated to simulated leagues + authenticated callers."""
    _, err = _require_sim_league(lid)
    if err:
        return err
    from .game.wc_scoring import finalize_gw
    from .seed.seed_league import seed_real_fixtures, GROUP_STAGE_EVENTS

    league_ref = _db.collection("leagues").document(lid)
    keep = set(MOCK_CANONICAL_ROSTER)
    summary = {"removedMembers": [], "junkPlayersDeleted": 0,
               "finalized": [], "finalizeErrors": {}, "fixtures": None}

    # 1. Remove non-canonical members + their squads.
    for m in league_ref.collection("members").get():
        if m.id in keep:
            continue
        summary["removedMembers"].append(m.id)
        m.reference.delete()
        sq = league_ref.collection("squads").document(m.id)
        if sq.get().exists:
            sq.delete()
    # ...and their lineups / wishlist bids (doc id is "{uid}_{gw}").
    for coll in ("lineups", "wishlist_bids"):
        for d in league_ref.collection(coll).get():
            if d.id.rsplit("_", 1)[0] not in keep:
                d.reference.delete()

    # 2. Drop malformed player-pool docs (no position == not a real player).
    for d in _db.collection("wc_players").get():
        if (d.to_dict() or {}).get("position") is None:
            d.reference.delete()
            summary["junkPlayersDeleted"] += 1

    # 3. Wipe knockout + GW>=3 scores/history + standings (recomputed below).
    for k in league_ref.collection("knockout").get():
        k.reference.delete()
    for coll in ("scores", "gw_history", "wishlist_results"):
        for d in league_ref.collection(coll).get():
            try:
                g = int(d.id)
            except (TypeError, ValueError):
                g = None
            if g is None or g >= 3:
                d.reference.delete()
    for st in league_ref.collection("standings").get():
        st.reference.delete()

    # 4. Fresh 6-manager H2H schedule for GW1-3 (deterministic order).
    order = [u for u in MOCK_CANONICAL_ROSTER]
    for gw, pairs in _round_robin(order, 3).items():
        league_ref.collection("schedule").document(str(gw)).set(
            {"gw": gw, "matches": [{"home": h, "away": a} for h, a in pairs]})

    # 5. Ensure each canonical manager has a GW1 & GW2 lineup (derive from their
    #    current squad if missing) so the re-finalize can score them.
    present = {m.id for m in league_ref.collection("members").get()}
    summary["members"] = sorted(present)
    for uid in present:
        sqd = league_ref.collection("squads").document(uid).get()
        if not sqd.exists:
            continue
        rich = [{"playerId": p["playerId"], "position": p["position"]}
                for p in (sqd.to_dict() or {}).get("players", [])]
        for gw in (1, 2):
            ln_ref = league_ref.collection("lineups").document(f"{uid}_{gw}")
            if not ln_ref.get().exists and rich:
                ln_ref.set(select_lineup(rich))

    # 6. League back to a 6-manager group phase before GW3.
    league_ref.update({
        "status": "group_phase", "currentGw": 1,
        "leaguePhaseGws": [1, 2, 3], "knockoutStartGw": 4,
        "knockoutQualifiers": 4, "maxMembers": 6,
        "windowOverride": firestore.DELETE_FIELD,
    })

    # 6b. Rebuild the team fixtures to the REAL group-stage schedule (3 rounds ×
    #     24 games, correct isos). Wipes the old fabricated/duplicate wc_fixtures
    #     + playerScores, scores GW1-2 from the 6 managers' drafted players, and
    #     leaves GW3 upcoming.
    drafted = {}
    for uid in present:
        sqd = league_ref.collection("squads").document(uid).get()
        for p in (sqd.to_dict() or {}).get("players", []) if sqd.exists else []:
            drafted[int(p["playerId"])] = {
                "id": int(p["playerId"]), "name": p.get("name", ""),
                "position": int(p["position"]), "teamIso": p.get("teamIso", ""),
            }
    summary["fixtures"] = seed_real_fixtures(_db, drafted, GROUP_STAGE_EVENTS, played_gws=(1, 2))

    # 7. Re-finalize GW1 then GW2 → clean scores/standings for the 6; advances
    #    currentGw to 3. Each finalize is best-effort so one bad GW can't half-
    #    abort the reset.
    for gw in (1, 2):
        try:
            finalize_gw(lid, gw, _db, _wc)
            summary["finalized"].append(gw)
        except Exception as exc:
            summary["finalizeErrors"][gw] = str(exc)

    # 8. Force the final "before GW3" state regardless of finalize side-effects.
    league_ref.update({"currentGw": 3, "status": "group_phase"})
    summary["currentGw"] = 3
    return _ok(summary)


# Wingers to reclassify FWD -> MID. Matched by NAME against the LIVE wc_players
# pool (the single source of truth — the seed file is divergent), never by id.
REPOSITION_FWD_TO_MID = [
    "Julián Alvarez", "Jeremy Doku", "Leandro Trossard", "Bukayo Saka",
    "Anthony Gordon", "Morgan Rogers", "Bradley Barcola", "Rayan Cherki",
    "Desire Doue", "Michael Olise", "Rafael Leão", "Lamine Yamal",
    "Dani Olmo", "Yéremy Pino",
]
_POS_NAME = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _name_tokens(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return [t for t in s.replace("'", "").replace(".", " ").replace("-", " ").split() if t]


def _name_match(target, pname):
    """Last-name match + first token (full or initial) — robust to 'J. Álvarez'
    vs 'Julián Alvarez' without false-matching e.g. Wan-Bissaka to Saka."""
    t, p = _name_tokens(target), _name_tokens(pname)
    if not t or not p or t[-1] != p[-1]:
        return False
    return t[0] == p[0] or t[0][0] == p[0][0]


@wc_bp.route("/admin/leagues/<lid>/reposition-fwd-to-mid", methods=["POST"])
def admin_reposition_fwd_to_mid(lid: str):
    """MOCK-ONLY: reclassify the REPOSITION_FWD_TO_MID wingers from FWD(4)->MID(3)
    in the live wc_players pool (matched by name). Any squad that owned one is
    now 6 MID/2 FWD, so rebalance it back to a legal 2/5/5/3 by dropping a random
    NON-flipped MID and adding a random free-agent FWD. Then regenerate the
    affected GW1/GW2 lineups, rebuild playerScores (process_fixture re-reads the
    new positions -> MID scoring), and re-finalize GW1+GW2 so points/standings
    are complete. Idempotent. Gated to simulated leagues + authed callers."""
    _, err = _require_sim_league(lid)
    if err:
        return err
    from .seed.seed_league import seed_real_fixtures, GROUP_STAGE_EVENTS
    from .game.wc_scoring import finalize_gw
    import random
    rng = random.Random(2026)
    league_ref = _db.collection("leagues").document(lid)
    summary = {"flipped": [], "alreadyMid": [], "notFound": [],
               "rebalanced": {}, "finalized": [], "finalizeErrors": {}}

    def _pid(pd, doc):
        try:
            return int(pd.get("id", doc.id))
        except (TypeError, ValueError):
            return None

    # 1. Flip FWD -> MID in the live pool (source of truth).
    all_docs = list(_db.collection("wc_players").get())
    flipped_ids = set()
    for target in REPOSITION_FWD_TO_MID:
        matches = [d for d in all_docs if _name_match(target, (d.to_dict() or {}).get("name", ""))]
        if not matches:
            summary["notFound"].append(target)
            continue
        did = False
        for d in matches:
            pd = d.to_dict() or {}
            if pd.get("position") == 4:
                d.reference.update({"position": 3, "positionName": "MID", "element_type": 3})
                pid = _pid(pd, d)
                if pid is not None:
                    flipped_ids.add(pid)
                summary["flipped"].append({"id": pid, "name": pd.get("name")})
                did = True
        if not did:
            summary["alreadyMid"].append(target)

    # 2. Read squads + ownership; build a pool of free-agent FWDs.
    squads, owned = {}, set()
    for sq in league_ref.collection("squads").get():
        players = (sq.to_dict() or {}).get("players", [])
        squads[sq.id] = players
        owned.update(int(p["playerId"]) for p in players)

    def _sqplayer(pd, pid):
        pos = int(pd.get("position", 4))
        return {"playerId": pid, "draftedRound": 99, "position": pos,
                "positionName": _POS_NAME.get(pos, "FWD"), "name": pd.get("name", ""),
                "teamIso": pd.get("teamIso", ""), "teamId": pd.get("teamId", 0),
                "teamName": pd.get("teamName", ""), "eliminated": False}

    avail_fwds = []
    for d in all_docs:
        pd = d.to_dict() or {}
        if pd.get("position") == 4:
            pid = _pid(pd, d)
            if pid is not None and pid not in owned and pid not in flipped_ids:
                avail_fwds.append(_sqplayer(pd, pid))
    rng.shuffle(avail_fwds)

    # 3. Per squad: flip owned players -> MID, then rebalance to 5 MID / 3 FWD.
    affected = set()
    for uid, players in squads.items():
        changed = False
        for p in players:
            if int(p["playerId"]) in flipped_ids and int(p["position"]) != 3:
                p["position"] = 3
                p["positionName"] = "MID"
                changed = True

        def counts():
            c = {1: 0, 2: 0, 3: 0, 4: 0}
            for p in players:
                c[int(p["position"])] = c.get(int(p["position"]), 0) + 1
            return c

        swaps, c = [], counts()
        while c[3] > 5 and c[4] < 3 and avail_fwds:
            mids = [p for p in players if int(p["position"]) == 3 and int(p["playerId"]) not in flipped_ids]
            if not mids:
                break
            drop = rng.choice(mids)
            add = avail_fwds.pop()
            players.remove(drop)
            players.append(add)
            owned.discard(int(drop["playerId"]))
            owned.add(int(add["playerId"]))
            swaps.append({"out": drop.get("name"), "in": add.get("name")})
            changed = True
            c = counts()
        if changed:
            league_ref.collection("squads").document(uid).set({"players": players})
            affected.add(uid)
            summary["rebalanced"][uid] = {"swaps": swaps, "counts": c}

    # 4. Rebuild playerScores with the new positions, regenerate the AFFECTED
    #    managers' lineups (their old XI is now an illegal formation), re-finalize.
    drafted = {}
    for players in squads.values():
        for p in players:
            drafted[int(p["playerId"])] = {
                "id": int(p["playerId"]), "name": p.get("name", ""),
                "position": int(p["position"]), "teamIso": p.get("teamIso", ""),
            }
    summary["fixtures"] = seed_real_fixtures(_db, drafted, GROUP_STAGE_EVENTS, played_gws=(1, 2))

    for uid in affected:
        rich = [{"playerId": p["playerId"], "position": int(p["position"])} for p in squads[uid]]
        for gw in (1, 2):
            try:
                league_ref.collection("lineups").document(f"{uid}_{gw}").set(select_lineup(rich))
            except Exception as exc:
                summary["finalizeErrors"][f"lineup_{uid}_{gw}"] = str(exc)

    for gw in (1, 2):
        try:
            finalize_gw(lid, gw, _db, _wc)
            summary["finalized"].append(gw)
        except Exception as exc:
            summary["finalizeErrors"][gw] = str(exc)
    league_ref.update({"currentGw": 3, "status": "group_phase"})
    return _ok(summary)


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


@wc_bp.route("/admin/leagues/<lid>/process-wishlist-auction/<int:gw>", methods=["POST"])
def admin_process_wishlist_auction(lid: str, gw: int):
    """Run the wishlist auction for ``gw`` and return its summary.

    Auto-triggering on window transition is out of scope for PR 4 — the window
    switcher only sets an override field with no side-effects. This explicit
    admin trigger is how the auction is exercised/tested. PR 5 will run deferred
    trade processing BEFORE calling this resolver.
    """
    uid, err = _require_admin()
    if err:
        return err
    try:
        result = _wishlist_mgr.run_auction(lid, gw)
        return _ok(result)
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/leagues/<lid>/open-trade-window/<int:gw>", methods=["POST"])
def admin_open_trade_window(lid: str, gw: int):
    """Open the next GW's trade window: deferred trades FIRST, then auction.

    Per WC2026_WINDOWS_DESIGN.md §6, trades auto-approved during the previous
    NEXT_GW_BID window execute atomically BEFORE the wishlist auction resolves,
    so a deferred trade can free/poison a player the auction would otherwise
    contest. Returns a combined summary of both phases.
    """
    uid, err = _require_admin()
    if err:
        return err
    try:
        deferred = _trade_mgr.process_deferred_trades(lid, gw)
        auction = _wishlist_mgr.run_auction(lid, gw)
        return _ok({"deferredTrades": deferred, "wishlistAuction": auction})
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/leagues/<lid>/run-mock-wishlist", methods=["POST"])
def admin_run_mock_wishlist(lid: str):
    """MOCK ONLY: demo the wishlist auction end-to-end in one click.

    Opens the FREE_AGENTS window (closing the trade window), auto-fills 1-3
    wishlist bids for every manager EXCEPT the caller/viewed manager (top free
    agents in, their worst players out — same position), then resolves the
    auction so squads actually change. Gated to ``simulated`` leagues so it can
    never touch the real league.

    Body: ``{gw?, excludeUid?}``. ``excludeUid`` (the manager running it) keeps
    their own real bids; defaults to the authenticated uid.
    """
    uid, err = _require_auth()
    if err:
        return err
    league_snap = _db.collection("leagues").document(lid).get()
    if not league_snap.exists:
        return _err("League not found", 404)
    ld = league_snap.to_dict() or {}
    if not ld.get("simulated"):
        return _err("MOCK_ONLY: this endpoint only runs on simulated leagues", 403)
    body = request.get_json(silent=True) or {}
    try:
        gw = int(body.get("gw") or ld.get("currentGw") or 1)
    except (TypeError, ValueError):
        gw = int(ld.get("currentGw") or 1)
    exclude_uid = body.get("excludeUid") or uid
    try:
        mock = _wishlist_mgr.generate_mock_bids(lid, gw, exclude_uid=exclude_uid)
        # Open the FREE_AGENTS window (closes the trade window) so the page
        # re-renders into the free-agent phase. current_window honours this.
        _db.collection("leagues").document(lid).update(
            {"windowOverride": {"phase": "free_agents", "gw": gw}})
        try:
            deferred = _trade_mgr.process_deferred_trades(lid, gw)
        except Exception:
            deferred = {"skipped": True}
        auction = _wishlist_mgr.run_auction(lid, gw)
        return _ok({
            "gw": gw,
            "mockBidsGenerated": mock,
            "deferredTrades": deferred,
            "wishlistAuction": auction,
            "window": {"phase": "free_agents", "gw": gw},
        })
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
            if status not in ("group_phase", "knockout"):
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
