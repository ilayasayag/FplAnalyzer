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
from .game.wc_wishlist_autorun import WishlistAutoRunner
from .game.wc_knockout import get_bracket, seed_knockout, advance_knockout_bracket
from .game.wc_scoring import finalize_gw, process_fixture
from .game.wc_gameweeks import (
    all_gws_as_dict, get_current_gw, is_locked, get_gw_config,
    compute_knockout_start_gw,
)
from .game.wc_windows import is_lineup_locked
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
_wishlist_autorun: WishlistAutoRunner = None
_sim = None

# The WC 2026 mock-draft showcase (lg_mock_draft) is locked to these 6 canonical
# managers. Used to (a) gate login auto-hydration so the roster can't regrow past
# 6, and (b) drive the one-shot roster-reset admin endpoint.
MOCK_LID = "lg_mock_draft"
MOCK_CANONICAL_ROSTER = ("u_ilay", "u_yuval", "u_netanel", "u_shay", "u_nadav", "u_roy")


def init_wc(db, firebase_auth=None):
    global _db, _wc, _league_mgr, _squad_mgr, _trade_mgr, _waiver_mgr, \
        _wishlist_mgr, _wishlist_autorun, _sim
    _db = db
    _wc = WC2026Client(db=db)
    _league_mgr = WCLeagueManager(db)
    _squad_mgr = WCSquadManager(db, _wc)
    _trade_mgr = WCTradeManager(db, _wc)
    _waiver_mgr = WCWaiverManager(db, _wc)
    _wishlist_mgr = WCWishlistManager(db, _wc)
    _wishlist_autorun = WishlistAutoRunner(db, _wishlist_mgr, _trade_mgr)
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


# Default super-admin (Ilay). Overridable via wc_config/tournament.superAdminUid.
DEFAULT_SUPER_ADMIN_UID = "u_ilay"


def _super_admin_uid() -> str:
    """The single super-admin (Ilay) uid: wc_config/tournament.superAdminUid,
    defaulting to ``u_ilay``."""
    cfg = _db.collection("wc_config").document("tournament").get()
    return (cfg.to_dict() or {}).get("superAdminUid", DEFAULT_SUPER_ADMIN_UID) if cfg.exists else DEFAULT_SUPER_ADMIN_UID


def _require_super_admin():
    """Ilay-only gate for window control. Fails closed: caller uid must equal
    the configured super-admin uid (``u_ilay`` by default). Used for the timed
    window schedule and the manual window switcher, which are Ilay-only."""
    uid, err = _require_auth()
    if err:
        return None, err
    if uid != _super_admin_uid():
        return None, _err("Ilay only", 403)
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


@wc_bp.route("/wc-bracket", methods=["GET"])
def get_wc_bracket():
    """The WC2026 tournament knockout bracket (national teams), self-updated by
    the daily scan (``scan_and_build_bracket``). Public read."""
    snap = _db.collection("wc_config").document("wc_bracket").get()
    return _ok(snap.to_dict() if snap.exists else {"rounds": {}, "qualified": {}})


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


_AUDIT_FIFA = {"rp": None, "at": 0.0}   # cached resolved FIFA round-points map


def _audit_fifa_rp():
    """The FIFA round-points map {pid: {gw: pts}}, cached 60s. This (HTTP fetch +
    fuzzy-resolving 1487 players) is the heavy part of the audit, so we don't
    redo it on every player/nation lookup."""
    import time as _time
    if _AUDIT_FIFA["rp"] is not None and (_time.time() - _AUDIT_FIFA["at"]) < 60:
        return _AUDIT_FIFA["rp"]
    from fpl_predictor.data.wc_live_ingest import _fetch_fifa_by_pid
    rp, _ = _fetch_fifa_by_pid(_db)
    _AUDIT_FIFA["rp"], _AUDIT_FIFA["at"] = rp, _time.time()
    return rp


@wc_bp.route("/score-audit", methods=["GET"])
def score_audit():
    """Read-only live reconciliation: compare what our league SHOULD have (live
    FIFA round points − scouting + DefCon) against the total we stored. Surfaces
    any drift. Nobody can change anything — pure transparency.

    Scoped to keep it light — pass ONE of:
      * ``?player=<pid>``  — just that player (one collection-group query)
      * ``?nation=<iso>``  — that nation's players
      * (nothing / ``?scope=all``) — the whole pool (heavy; on demand only)
    """
    import time as _time
    from fpl_predictor.data.wc_live_ingest import fifa_breakdown, _excluded_pts

    player_id = request.args.get("player", type=int)
    nation = (request.args.get("nation") or "").strip().upper()
    scope = "player" if player_id else ("nation" if nation else "all")

    fifa_rp = _audit_fifa_rp()

    # Resolve the target player docs + their playerScores, scanning as narrowly as
    # the scope allows.
    def _scores_for(pid):
        try:
            return list(_db.collection_group("playerScores")
                        .where("playerId", "==", pid).get())
        except Exception:
            return []

    if scope == "player":
        pool = {player_id: (_db.collection("wc_players").document(str(player_id)).get().to_dict() or {})}
        score_docs = _scores_for(player_id)
    elif scope == "nation":
        pool = {int(d.id): (d.to_dict() or {})
                for d in _db.collection("wc_players").where("teamIso", "==", nation).get()}
        pids = list(pool)
        score_docs = []
        # One collection-group `in` query per 30 ids (a 26-player squad = 1 query)
        # instead of 26 serial `==` queries; per-id fallback if `in` isn't indexed.
        for i in range(0, len(pids), 30):
            chunk = pids[i:i + 30]
            try:
                score_docs += list(_db.collection_group("playerScores")
                                   .where("playerId", "in", chunk).get())
            except Exception:
                for pid in chunk:
                    score_docs += _scores_for(pid)
    else:
        pool = {int(d.id): (d.to_dict() or {}) for d in _db.collection("wc_players").get()}
        score_docs = []
        for fx in _db.collection("wc_fixtures").get():
            score_docs += list(fx.reference.collection("playerScores").get())

    agg = {}
    for d in score_docs:
        r = d.to_dict() or {}
        fifa_stored = r.get("fifaPoints")
        if fifa_stored is None:
            continue
        try:
            pid = int(d.id)
        except (TypeError, ValueError):
            continue
        if pid not in pool:
            continue
        pdoc = pool[pid]
        pos = pdoc.get("position", 3)
        gw = r.get("gw")
        fifa_live = (fifa_rp.get(pid) or {}).get(str(gw), fifa_stored)
        # Recompute the breakdown with FIFA's OWN position (stored as ``fifaPos``
        # by P1) so the position-dependent itemization is right; otherwise the
        # mis-attributed points would leak into the reconciliation line and look
        # "unexplained". Scouting is position-independent so the existing total
        # reconciliation is unaffected.
        bd = fifa_breakdown(r.get("stats") or {}, pos, fifa_live,
                            pdoc.get("percentSelected"), fifa_position=r.get("fifaPos"))
        scouting = _excluded_pts(bd)
        # Residual FIFA-awarded points we still can't itemize from our feed: the
        # signed pts on the balancing reconciliation line. Track signed (so it
        # can net out across GWs) AND absolute (so +5/−5 in two GWs ≠ clean).
        unexplained_pts = sum((ln.get("pts") or 0) for ln in bd
                              if ln.get("label") in ("FIFA match points", "FIFA adjustment"))
        a = agg.setdefault(pid, {
            "pid": pid, "name": pdoc.get("name", f"#{pid}"),
            "iso": (pdoc.get("teamIso") or "").upper(),
            "team": pdoc.get("teamName") or pdoc.get("teamIso") or "",
            "pos": pos, "fifaLive": 0, "fifaStored": 0, "scouting": 0,
            "defcon": 0, "stored": 0, "unexplained": 0, "unexplainedAbs": 0,
        })
        a["fifaLive"] += fifa_live
        a["fifaStored"] += fifa_stored
        a["scouting"] += scouting
        a["defcon"] += r.get("defConBonus", 0) or 0
        a["stored"] += r.get("fantasyPoints", 0) or 0
        a["unexplained"] += unexplained_pts
        a["unexplainedAbs"] += abs(unexplained_pts)

    players = []
    for a in agg.values():
        a["expected"] = a["fifaLive"] - a["scouting"] + a["defcon"]
        a["match"] = a["expected"] == a["stored"]
        players.append(a)
    players.sort(key=lambda x: (-x["stored"], x["name"]))

    nations = {}
    for a in players:
        n = nations.setdefault(a["iso"] or "—", {
            "iso": a["iso"], "team": a["team"], "players": 0,
            "fifaLive": 0, "scouting": 0, "defcon": 0, "expected": 0, "stored": 0,
            "unexplained": 0, "unexplainedAbs": 0,
        })
        for k in ("fifaLive", "scouting", "defcon", "expected", "stored",
                  "unexplained", "unexplainedAbs"):
            n[k] += a[k]
        n["players"] += 1
    by_nation = sorted(nations.values(), key=lambda x: -x["stored"])
    for n in by_nation:
        n["match"] = n["expected"] == n["stored"]

    return _ok({
        "scope": scope,
        "players": players,
        "byNation": by_nation,
        "mismatches": sum(1 for a in players if not a["match"]),
        "unexplainedPlayers": sum(1 for a in players if a["unexplainedAbs"] != 0),
        "fifaLive": bool(fifa_rp),
        "updatedAt": _time.time(),
    })


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


@wc_bp.route("/leagues/<lid>/draft/pause", methods=["POST"])
def pause_draft(lid: str):
    """EMERGENCY PAUSE — any authenticated league member can hit it. Freezes
    the draft for everyone (make_pick + auto_pick both reject while paused)
    and remembers the seconds left on the clock so resume continues exactly
    where it stopped."""
    import time as _time
    uid, err = _require_auth()
    if err:
        return err
    state_ref = (_db.collection("leagues").document(lid)
                 .collection("draft").document("state"))
    snap = state_ref.get()
    if not snap.exists:
        return _err("Draft not found", 404)
    state = snap.to_dict() or {}
    if state.get("status") != "active":
        return _err("Draft is not active")
    if state.get("paused"):
        return _ok({"paused": True, "alreadyPaused": True})
    remaining = max(0, (state.get("pickDeadline") or 0) - _time.time())
    state_ref.update({
        "paused": True,
        "pausedRemaining": remaining,
        "pausedBy": uid,
        "pausedAt": SERVER_TIMESTAMP,
    })
    return _ok({"paused": True, "secondsRemaining": round(remaining)})


@wc_bp.route("/leagues/<lid>/draft/resume", methods=["POST"])
def resume_draft(lid: str):
    """Resume a paused draft with the SAME seconds the clock had at pause."""
    import time as _time
    uid, err = _require_auth()
    if err:
        return err
    state_ref = (_db.collection("leagues").document(lid)
                 .collection("draft").document("state"))
    snap = state_ref.get()
    if not snap.exists:
        return _err("Draft not found", 404)
    state = snap.to_dict() or {}
    if not state.get("paused"):
        return _ok({"paused": False, "alreadyRunning": True})
    remaining = state.get("pausedRemaining")
    if remaining is None or remaining <= 0:
        remaining = state.get("pickTimer", 30)
    state_ref.update({
        "paused": False,
        "pickDeadline": _time.time() + remaining,
        "pausedRemaining": firestore.DELETE_FIELD,
        "resumedBy": uid,
    })
    return _ok({"paused": False, "secondsRemaining": round(remaining)})


@wc_bp.route("/leagues/<lid>/draft/rollback", methods=["POST"])
def rollback_draft(lid: str):
    """Rewind the draft to a previous pick (admin-only, paused-only). Body:
    {"toPick": <pickNumber>} — that pick goes back ON THE CLOCK; it and every
    later pick are deleted, pickedPlayerIds is rebuilt deduped. The draft
    stays paused; resume hands the re-picking manager a full clock."""
    uid, err = _require_auth()
    if err:
        return err
    league_doc = _db.collection("leagues").document(lid).get()
    if not league_doc.exists:
        return _err("League not found", 404)
    if (league_doc.to_dict() or {}).get("adminUid") != uid:
        return _err("Only the league admin can roll back the draft", 403)
    body = request.get_json(silent=True) or {}
    if "toPick" not in body:
        return _err("toPick required")
    try:
        to_pick = int(body["toPick"])
    except (TypeError, ValueError):
        return _err("toPick must be an integer")
    try:
        from .game.draft import DraftEngine
        return _ok(DraftEngine(_db, _wc).rollback_draft(lid, to_pick))
    except ValueError as exc:
        return _err(str(exc))


@wc_bp.route("/leagues/<lid>/draft/validate", methods=["GET"])
def validate_draft(lid: str):
    """Draft integrity report: duplicate players, quota/nation violations,
    pick gaps, state-vs-docs drift. Any league member can run it."""
    uid, err = _require_auth()
    if err:
        return err
    try:
        from .game.draft import DraftEngine
        return _ok(DraftEngine(_db, _wc).validate_draft(lid))
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
        # humanUids: live managers the bots must NOT pick for. Optional —
        # defaults to the previously stored list (or u_netanel legacy).
        _sim.start(lid, human_uids=body.get("humanUids"))
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


@wc_bp.route("/leagues/<lid>/draft/sim/advance", methods=["POST"])
def advance_draft_sim(lid: str):
    """Make bot picks synchronously while a NON-human manager is on the clock.

    Cloud Run throttles CPU between requests, so the background simulator
    thread stalls in production — this request-driven advance is how deployed
    drafts move bots forward. The client polls draft state and calls this when
    it sees a bot on the clock. Picks at most ``count`` (default 1, max 5) so
    each call is fast; stops early at a human's turn / pause / completion.
    Bots = anyone NOT in the state doc's humanUids. Sim-league gated.
    """
    _, err = _require_sim_league(lid)
    if err:
        return err
    from .game.draft import DraftEngine
    body = request.get_json(silent=True) or {}
    count = max(1, min(int(body.get("count", 1)), 5))
    engine = DraftEngine(_db, _wc)
    state_ref = (_db.collection("leagues").document(lid)
                 .collection("draft").document("state"))
    advanced = []
    for _i in range(count):
        snap = state_ref.get()
        if not snap.exists:
            break
        state = snap.to_dict() or {}
        if state.get("status") != "active" or state.get("paused"):
            break
        humans = set(state.get("humanUids") or [])
        drafter = engine._get_drafter(state.get("currentPick", 0),
                                      state.get("order", []))
        if drafter in humans:
            break
        try:
            pid = engine._find_best_available(lid, drafter, state)
            if not pid:
                break
            res = engine.make_pick(lid, drafter, pid, is_auto=True)
            advanced.append(res)
        except ValueError:
            break
    return _ok({"advanced": advanced, "n": len(advanced)})


@wc_bp.route("/admin/remove-non-squad-players", methods=["POST"])
def admin_remove_non_squad_players():
    """Delete the user-approved 236 provisional players who did NOT make their
    final 26-man squad (bundled kill list = the red entries of
    wc_non_squad_players.html, reviewed by the admin). Ownership-guarded: any
    player currently on a league squad is SKIPPED and reported (re-run after
    go-live wipes the mock squads). Deleted ids are scrubbed from every draft
    watchlist. Idempotent."""
    uid, err = _require_admin()
    if err:
        return err
    import json as _json
    spec_path = os.path.join(os.path.dirname(__file__), "data",
                             "non_squad_players.json")
    with open(spec_path, encoding="utf-8") as f:
        kill = _json.load(f)["players"]
    kill_keys = {(k["iso"], _fifa_norm(k["name"])) for k in kill}

    owned = set()
    for lid in (MOCK_LID, SANDBOX_LID):
        for sq in _db.collection("leagues").document(lid).collection("squads").get():
            owned.update(int(p["playerId"]) for p in (sq.to_dict() or {}).get("players", []))

    summary = {"deleted": 0, "skippedOwned": [], "notFound": 0,
               "watchlistsScrubbed": []}
    deleted_ids = []
    batch, ops = _db.batch(), 0
    for d in _db.collection("wc_players").get():
        pd = d.to_dict() or {}
        key = (pd.get("teamIso", ""), _fifa_norm(pd.get("name", "")))
        if key not in kill_keys:
            continue
        kill_keys.discard(key)
        try:
            pid = int(pd.get("id", d.id))
        except (TypeError, ValueError):
            pid = None
        if pid in owned:
            summary["skippedOwned"].append({"id": pid, "name": pd.get("name")})
            continue
        batch.delete(d.reference)
        ops += 1
        summary["deleted"] += 1
        if pid is not None:
            deleted_ids.append(pid)
        if ops >= 450:
            batch.commit()
            batch, ops = _db.batch(), 0
    if ops:
        batch.commit()
    summary["notFound"] = len(kill_keys)

    if deleted_ids:
        gone = {str(i) for i in deleted_ids} | set(deleted_ids)
        for lid in (MOCK_LID, SANDBOX_LID):
            league_ref = _db.collection("leagues").document(lid)
            wl_doc = league_ref.collection("draft").document("watchlists")
            for m in league_ref.collection("members").get():
                d = wl_doc.collection(m.id).document("list").get()
                if not d.exists:
                    continue
                ids = (d.to_dict() or {}).get("playerIds", [])
                kept = [x for x in ids if x not in gone and str(x) not in gone]
                if len(kept) != len(ids):
                    d.reference.update({"playerIds": kept})
                    summary["watchlistsScrubbed"].append(
                        f"{lid}/{m.id}: {len(ids)} -> {len(kept)}")
    return _ok(summary)


@wc_bp.route("/admin/leagues/<lid>/set-admin", methods=["POST"])
def admin_set_league_admin(lid: str):
    """Global-admin-only: set the league's adminUid (the uid that gates START
    DRAFT / pause-rollback / start-season). Body: {"uid": "u_..."} — must be
    an existing league member. Fixes legacy leagues whose admin is a seed bot
    (lg_mock_draft shipped with adminUid=u_mk_golden)."""
    caller, err = _require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    new_admin = body.get("uid")
    if not new_admin:
        return _err("uid required")
    league_ref = _db.collection("leagues").document(lid)
    if not league_ref.get().exists:
        return _err("League not found", 404)
    if not league_ref.collection("members").document(new_admin).get().exists:
        return _err(f"{new_admin} is not a member of {lid}")
    league_ref.update({"adminUid": new_admin})
    return _ok({"lid": lid, "adminUid": new_admin})


@wc_bp.route("/admin/golive-reset", methods=["POST"])
def admin_golive_reset():
    """GO-LIVE: transform the showcase league into THE real league, in place.

    One-shot, GLOBAL-ADMIN-only, run once on draft day BEFORE the real draft:
      - Backs up the league doc + squads + member list to wc_config/golive_backup.
      - Keeps: the 6 canonical members and every draft watchlist (draft prep).
      - Deletes: squads, lineups, scores, gw_history, standings, knockout,
        schedule, trades, transactions, wishlist bids/results, waivers,
        transfer_windows, old draft state + picks — ALL mock gameplay data.
      - League doc: simulated -> False (hides the mock chip / window switcher /
        sim+sandbox endpoints), status -> pre_draft, currentGw -> 1,
        pickTimer -> 45 (real draft clock), format h2h, clears windowOverride.
      - Globals: every wc_players totalPoints -> 0 / eliminated -> False,
        wc_fixtures rewritten to the real 72-game schedule ALL UNPLAYED,
        wc_gameweeks re-seeded, wc_config currentGw -> 1 + results cleared.
    After this the time-based window machine runs the real timeline (trades ->
    free agents at T0-5h -> squad/XI lock at T0-1h) off the real kickoffs, and
    the Draft Room START button begins the real draft. Idempotent."""
    uid, err = _require_admin()
    if err:
        return err
    league_ref = _db.collection("leagues").document(MOCK_LID)
    league_snap = league_ref.get()
    if not league_snap.exists:
        return _err("League not found", 404)
    league = league_snap.to_dict() or {}
    draft_state = league_ref.collection("draft").document("state").get()
    if draft_state.exists and (draft_state.to_dict() or {}).get("status") == "active":
        return _err("A draft is in progress — finish or reset it first", 409)

    summary = {"lid": MOCK_LID, "deleted": {}, "membersKept": [],
               "watchlistsKept": 0, "playersReset": 0}

    # 0. Backup (league doc + squads + members).
    backup = {"ts": SERVER_TIMESTAMP, "league": league, "squads": {}, "members": []}
    for sq in league_ref.collection("squads").get():
        backup["squads"][sq.id] = sq.to_dict()
    for m in league_ref.collection("members").get():
        backup["members"].append(m.id)
    _db.collection("wc_config").document("golive_backup").set(backup)

    # 1. Members: keep exactly the canonical 6.
    for m in league_ref.collection("members").get():
        if m.id in MOCK_CANONICAL_ROSTER:
            summary["membersKept"].append(m.id)
        else:
            m.reference.delete()
    wl_doc = league_ref.collection("draft").document("watchlists")
    for muid in summary["membersKept"]:
        if wl_doc.collection(muid).document("list").get().exists:
            summary["watchlistsKept"] += 1

    # 2. Wipe ALL mock gameplay data (keep members + watchlists).
    for coll in ("squads", "lineups", "scores", "gw_history", "standings",
                 "knockout", "schedule", "trades", "transactions",
                 "wishlist_bids", "wishlist_results", "waivers",
                 "transfer_windows"):
        n = 0
        for d in league_ref.collection(coll).get():
            d.reference.delete()
            n += 1
        summary["deleted"][coll] = n
    st = league_ref.collection("draft").document("state")
    if st.get().exists:
        n = 0
        for p in st.collection("picks").get():
            p.reference.delete()
            n += 1
        st.delete()
        summary["deleted"]["draftPicks"] = n

    # 3. League doc -> the real league, ready to draft.
    league_ref.update({
        "simulated": False,
        "adminUid": "u_ilay",   # START DRAFT / undo / rollback gate on this
        "status": "pre_draft",
        "currentGw": 1,
        "draftComplete": False,
        "pickTimer": 45,
        "format": "h2h",
        "maxMembers": len(MOCK_CANONICAL_ROSTER),
        "leaguePhaseGws": [1, 2, 3],
        "knockoutStartGw": 4,
        "knockoutQualifiers": 4,
        "windowOverride": firestore.DELETE_FIELD,
    })

    # 4. Global resets: player stats, fixtures (real schedule, all unplayed),
    #    gameweeks, tournament config.
    batch, ops = _db.batch(), 0
    for d in _db.collection("wc_players").get():
        pd = d.to_dict() or {}
        if pd.get("totalPoints") or pd.get("eliminated"):
            batch.update(d.reference, {"totalPoints": 0, "eliminated": False})
            ops += 1
            summary["playersReset"] += 1
            if ops >= 450:
                batch.commit()
                batch, ops = _db.batch(), 0
    if ops:
        batch.commit()

    from .seed.seed_league import seed_real_fixtures, GROUP_STAGE_EVENTS
    summary["fixtures"] = seed_real_fixtures(_db, {}, GROUP_STAGE_EVENTS,
                                             played_gws=())
    from .game.wc_gameweeks import gw_as_dict
    for gw in range(1, 9):
        _db.collection("wc_gameweeks").document(str(gw)).set(gw_as_dict(gw))
    _db.collection("wc_config").document("tournament").update({
        "currentGw": 1, "winner": None, "topScorer": None,
        # GW1 special: free agents open IMMEDIATELY after the draft (T0-36h is
        # already in the past) and still auto-lock at T0-1h. Restore to 5
        # after GW1 locks via /admin/window-config for the normal GW rhythm.
        "fa_open_before_hours": 36,
    })
    return _ok(summary)


@wc_bp.route("/admin/window-config", methods=["POST"])
def admin_window_config():
    """Global-admin: tune the transfer-window offsets on wc_config/tournament.
    Body keys (all optional): faOpenBeforeHours, squadLockBeforeHours,
    tradeReopenAfterHours. Used to restore the normal rhythm (fa=5) after the
    GW1 always-open free-agents special."""
    uid, err = _require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    mapping = {"faOpenBeforeHours": "fa_open_before_hours",
               "squadLockBeforeHours": "squad_lock_before_hours",
               "tradeReopenAfterHours": "trade_reopen_after_hours"}
    update = {}
    for k, field in mapping.items():
        if k in body:
            try:
                update[field] = float(body[k])
            except (TypeError, ValueError):
                return _err(f"{k} must be a number")
    if not update:
        return _err("nothing to update")
    _db.collection("wc_config").document("tournament").update(update)
    return _ok(update)


# Final-squad corrections vs the official Wikipedia 2026 squads (June 2026).
# adds: real squad members our pool lacks (the second BRA Danilo/Éderson the
# FIFA feed name-collided away, plus Geertruida). deletes: provisional players
# who did NOT make their final squad and were explicitly flagged by the admin.
SQUAD_CORRECTION_ADDS = [
    {"iso": "BRA", "name": "Danilo Oliveira", "specKey": "danilo", "pos": 3},
    # "Éderson Santos" (Atalanta MID) — distinct display name so he can't be
    # confused with (or idempotency-collide into) GK "Ederson".
    {"iso": "BRA", "name": "Éderson Santos", "specKey": "ederson", "pos": 3},
    {"iso": "NED", "name": "Lutsharel Geertruida", "specKey": "lutsharel geertruida", "pos": 2},
]
SQUAD_CORRECTION_DELETES = [
    {"iso": "NED", "name": "Xavi Simons"},
    {"iso": "NED", "name": "Jeremie Frimpong"},
]


@wc_bp.route("/admin/squad-corrections", methods=["POST"])
def admin_squad_corrections():
    """One-shot, idempotent final-squad fix: add SQUAD_CORRECTION_ADDS to
    wc_players (draftRank from the bundled FIFA spec), delete
    SQUAD_CORRECTION_DELETES (refusing if owned by any squad in the mock or
    sandbox league), and scrub the deleted ids out of EVERY manager's draft
    watchlist in both leagues."""
    uid, err = _require_auth()
    if err:
        return err
    spec = _load_align_spec()
    summary = {"added": [], "addSkipped": [], "deleted": [], "deleteBlocked": [],
               "watchlistsScrubbed": []}

    all_docs = list(_db.collection("wc_players").get())
    max_id, by_iso_norm, team_meta = 0, {}, {}
    for d in all_docs:
        pd = d.to_dict() or {}
        try:
            pid = int(pd.get("id", d.id))
        except (TypeError, ValueError):
            pid = 0
        max_id = max(max_id, pid)
        iso = pd.get("teamIso", "")
        by_iso_norm[(iso, _fifa_norm(pd.get("name", "")))] = (d.reference, pd)
        if iso and iso not in team_meta and pd.get("teamId"):
            team_meta[iso] = {"teamId": pd["teamId"], "teamName": pd.get("teamName", "")}

    # 1. Adds (skip if an identically-named player already exists for the iso).
    next_id = max_id + 1
    for a in SQUAD_CORRECTION_ADDS:
        if (a["iso"], _fifa_norm(a["name"])) in by_iso_norm:
            summary["addSkipped"].append(a["name"])
            continue
        entry = spec["teams"].get(a["iso"], {}).get(a["specKey"]) or {}
        meta = team_meta.get(a["iso"], {"teamId": 0, "teamName": a["iso"]})
        pid, next_id = next_id, next_id + 1
        _db.collection("wc_players").document(str(pid)).set({
            "id": pid, "name": a["name"], "position": a["pos"],
            "positionName": _POS_NAME[a["pos"]], "element_type": a["pos"],
            "teamIso": a["iso"], "teamId": meta["teamId"],
            "teamName": meta["teamName"],
            "draftRank": entry.get("rank", 0), "totalPoints": 0,
            "eliminated": False, "photo": "",
        })
        summary["added"].append({"id": pid, "name": a["name"]})

    # 2. Deletes — but never orphan a squad: block if owned anywhere.
    owned = set()
    for lid in (MOCK_LID, SANDBOX_LID):
        for sq in _db.collection("leagues").document(lid).collection("squads").get():
            owned.update(int(p["playerId"]) for p in (sq.to_dict() or {}).get("players", []))
    deleted_ids = []
    for rm in SQUAD_CORRECTION_DELETES:
        hit = by_iso_norm.get((rm["iso"], _fifa_norm(rm["name"])))
        if not hit:
            continue  # already gone — idempotent
        ref, pd = hit
        pid = int(pd.get("id", ref.id))
        if pid in owned:
            summary["deleteBlocked"].append({"id": pid, "name": rm["name"]})
            continue
        ref.delete()
        deleted_ids.append(pid)
        summary["deleted"].append({"id": pid, "name": rm["name"]})

    # 3. Scrub deleted players from every draft watchlist (mock + sandbox).
    if deleted_ids:
        gone = {str(i) for i in deleted_ids} | set(deleted_ids)
        for lid in (MOCK_LID, SANDBOX_LID):
            league_ref = _db.collection("leagues").document(lid)
            wl_doc = league_ref.collection("draft").document("watchlists")
            for m in league_ref.collection("members").get():
                d = wl_doc.collection(m.id).document("list").get()
                if not d.exists:
                    continue
                ids = (d.to_dict() or {}).get("playerIds", [])
                kept = [x for x in ids if x not in gone and str(x) not in gone]
                if len(kept) != len(ids):
                    d.reference.update({"playerIds": kept})
                    summary["watchlistsScrubbed"].append(
                        f"{lid}/{m.id}: {len(ids)} -> {len(kept)}")
    return _ok(summary)


# --- Draft sandbox: a disposable clone league for live-draft rehearsal. -----
# All WRITES go to SANDBOX_LID only; the mock league is READ-ONLY source data.
SANDBOX_LID = "lg_draft_test"
assert SANDBOX_LID != MOCK_LID


@wc_bp.route("/admin/draft-sandbox", methods=["POST"])
def create_draft_sandbox():
    """Create/refresh the draft-rehearsal sandbox league (lg_draft_test).

    Copies FROM lg_mock_draft (reads only): the 6 canonical members and every
    manager's draft watchlist. Creates a fresh simulated league in pre_draft
    with adminUid=u_ilay so humans + bots can run a full draft there without
    touching ANY mock-league data (squads, wishlists, scores all stay put).
    Idempotent: wipes any previous sandbox state first (sandbox only).
    """
    uid, err = _require_auth()
    if err:
        return err
    src_ref = _db.collection("leagues").document(MOCK_LID)
    dst_ref = _db.collection("leagues").document(SANDBOX_LID)
    summary = {"lid": SANDBOX_LID, "members": [], "watchlistsCopied": 0}

    # 0. Wipe previous sandbox state (members/draft/squads/watchlists).
    if dst_ref.get().exists:
        st = dst_ref.collection("draft").document("state")
        if st.get().exists:
            for p in st.collection("picks").get():
                p.reference.delete()
            st.delete()
        wl_doc = dst_ref.collection("draft").document("watchlists")
        for m in dst_ref.collection("members").get():
            for d in wl_doc.collection(m.id).get():
                d.reference.delete()
            m.reference.delete()
        for sq in dst_ref.collection("squads").get():
            sq.reference.delete()

    # 1. League doc: simulated + pre_draft, admin u_ilay (sandbox-only knobs).
    dst_ref.set({
        "name": "DRAFT REHEARSAL (sandbox)",
        "simulated": True,
        "status": "pre_draft",
        "adminUid": "u_ilay",
        "maxMembers": len(MOCK_CANONICAL_ROSTER),
        "pickTimer": 45,   # match the real draft clock
        "draftComplete": False,
        "sandbox": True,
        "createdAt": SERVER_TIMESTAMP,
    })

    # 2. Copy the canonical members (read from mock, write to sandbox).
    for m in src_ref.collection("members").get():
        if m.id not in MOCK_CANONICAL_ROSTER:
            continue
        dst_ref.collection("members").document(m.id).set(m.to_dict() or {})
        summary["members"].append(m.id)

    # 3. Copy each member's draft watchlist (read mock, write sandbox).
    src_wl = src_ref.collection("draft").document("watchlists")
    dst_wl = dst_ref.collection("draft").document("watchlists")
    for muid in summary["members"]:
        d = src_wl.collection(muid).document("list").get()
        if d.exists:
            dst_wl.collection(muid).document("list").set(d.to_dict() or {})
            summary["watchlistsCopied"] += 1

    return _ok(summary)


@wc_bp.route("/admin/draft-sandbox", methods=["DELETE"])
def delete_draft_sandbox():
    """Tear the sandbox league down completely (sandbox docs only)."""
    uid, err = _require_auth()
    if err:
        return err
    dst_ref = _db.collection("leagues").document(SANDBOX_LID)
    if not dst_ref.get().exists:
        return _ok({"status": "absent"})
    _sim.stop()
    st = dst_ref.collection("draft").document("state")
    if st.get().exists:
        for p in st.collection("picks").get():
            p.reference.delete()
        st.delete()
    wl_doc = dst_ref.collection("draft").document("watchlists")
    members = [m.id for m in dst_ref.collection("members").get()]
    for muid in members:
        for d in wl_doc.collection(muid).get():
            d.reference.delete()
        dst_ref.collection("members").document(muid).delete()
    for sq in dst_ref.collection("squads").get():
        sq.reference.delete()
    dst_ref.delete()
    return _ok({"status": "deleted", "membersRemoved": members})


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


@wc_bp.route("/leagues/<lid>/edit-gw", methods=["GET"])
def get_edit_gw(lid: str):
    """The GW whose lineup a manager can currently edit = the earliest GW at or
    after the league's currentGw whose lineup is NOT yet locked. While GW1 is
    live (locked) this returns GW2, so Pick Team edits the upcoming GW without
    touching the frozen, already-scored current GW."""
    uid, err = _require_auth()
    if err:
        return err
    from fpl_predictor.game.wc_windows import is_lineup_locked
    league = _db.collection("leagues").document(lid).get()
    cur = (league.to_dict() or {}).get("currentGw", 1) if league.exists else 1
    gw = int(cur)
    # walk forward over locked GWs (cap the search so a misconfig can't loop)
    for _ in range(8):
        if not is_lineup_locked(_db, gw, lid=lid):
            break
        gw += 1
    return _ok({"editGw": gw, "currentGw": int(cur), "currentLocked": gw != int(cur)})


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
    if doc.exists:
        return _ok({"leagueId": lid, **doc.to_dict()})
    # No finalized snapshot yet. Pre-lock, lineups are private: a manager may
    # always see their own, but never an opponent's (mirrors get_opponent_lineup).
    if not is_lineup_locked(_db, gw, lid=lid):
        if uid != caller:
            return _err("lineups hidden until they lock", 403)
        return _err("gw_history not found", 404)
    # Locked but not finalized (GW in progress) → compose a LIVE snapshot from
    # the frozen lineup + live per-player points, same shape as the real one.
    live = _compose_live_gw_history(lid, uid, gw)
    if live is None:
        return _err("gw_history not found", 404)
    return _ok({"leagueId": lid, **live})


def _live_gw_player_scores(gw: int) -> dict:
    """{pool_id -> {"points", "stats"}} for a GW, read from each GW fixture's
    playerScores subcollection — the same per-fixture join the live ingest's
    ``_gw_points_map`` does (kept local so the API never imports the ingest's
    private helpers)."""
    out = {}
    for fx in _db.collection("wc_fixtures").where("gw", "==", gw).get():
        for pdoc in fx.reference.collection("playerScores").get():
            pdata = pdoc.to_dict() or {}
            out[int(pdoc.id)] = {
                "points": pdata.get("fantasyPoints", 0) or 0,
                "stats": pdata.get("stats", {}) or {},
            }
    return out


def _compose_live_gw_history(lid: str, uid: str, gw: int):
    """LIVE stand-in for a gw_history snapshot while a locked GW is in progress.

    Joins the frozen lineup (``leagues/{lid}/lineups/{uid}_{gw}``) to the GW's
    live playerScores. Captain doubles (mirroring the live ingest's running
    totals); auto-subs/H2H result only exist after finalize_gw, so ``autoSubs``
    is empty and ``opponent``/``result`` stay null. Marked ``live: True``.
    """
    lineup_doc = (_db.collection("leagues").document(lid)
                  .collection("lineups").document(f"{uid}_{gw}").get())
    if not lineup_doc.exists:
        return None
    lineup = lineup_doc.to_dict() or {}
    starting = list(lineup.get("starting", []) or [])
    bench = list(lineup.get("bench", []) or [])
    scores = _live_gw_player_scores(gw)

    def _pts(pid):
        return scores.get(int(pid), {}).get("points", 0)

    players = [{"id": pid,
                "points": _pts(pid),
                "stats": scores.get(int(pid), {}).get("stats", {})}
               for pid in starting + bench]
    total = sum(_pts(pid) for pid in starting)
    captain = lineup.get("captain")
    if captain is not None and int(captain) in [int(p) for p in starting]:
        total += _pts(captain)  # captain doubles
    return {
        "uid": uid,
        "gw": gw,
        "players": players,
        "starting": starting,
        "bench": bench,
        "autoSubs": [],
        "totalPoints": total,
        "opponent": None,
        "opponentPoints": None,
        "result": None,
        "live": True,
    }


@wc_bp.route("/leagues/<lid>/standings", methods=["GET"])
def get_standings(lid: str):
    uid, err = _require_auth()
    if err:
        return err
    gw = request.args.get("gw")
    league_ref = _db.collection("leagues").document(lid)
    league_snap = league_ref.get()
    league = league_snap.to_dict() if league_snap.exists else {}
    current_gw = int(league.get("currentGw", 1) or 1)
    active = league.get("status") in ("group_phase", "knockout")

    # A finalized snapshot for the requested/current GW always wins (unchanged
    # behaviour). For no-?gw requests we look for the CURRENT GW's snapshot —
    # finalize_gw advances currentGw right after writing it, so mid-GW this
    # doesn't exist and an active league falls through to the live overlay.
    doc_id = str(gw) if gw else str(current_gw)
    doc = league_ref.collection("standings").document(doc_id).get()
    if doc.exists:
        return _ok({"leagueId": lid, **doc.to_dict()})

    # No finalized doc for this view → compose a LIVE overlay so an active
    # league's standings are never empty mid-GW.
    if active and (not gw or str(gw) == str(current_gw)):
        live = _compose_live_standings(league_ref, league, current_gw)
        if live is not None:
            return _ok({"leagueId": lid, **live})

    # Inactive league / past GW with no snapshot: legacy behaviour ("current"
    # doc for the no-?gw case, else empty).
    if not gw:
        cur_doc = league_ref.collection("standings").document("current").get()
        if cur_doc.exists:
            return _ok({"leagueId": lid, **cur_doc.to_dict()})
    return _ok({"leagueId": lid, "managers": []})


def _compose_live_standings(league_ref, league: dict, current_gw: int):
    """LIVE standings for an active league mid-GW (no finalized snapshot yet).

    Baseline = every member with zeros, overlaid with the last finalized
    ``standings/current`` (H2H record/points stay FROZEN — no provisional W/D/L
    for the live GW), plus the in-progress GW's live points from
    ``scores/{currentGw}`` added to each manager's total fantasy points.
    Ranked exactly like ``_update_standings`` (H2H pts, then fantasy pts).
    """
    members = list(league_ref.collection("members").get())
    if not members:
        return None
    rows = {}
    for m in members:
        mdata = m.to_dict() or {}
        rows[m.id] = {
            "uid": m.id,
            "displayName": mdata.get("displayName", ""),
            "teamName": mdata.get("teamName", ""),
            "hw": 0, "hd": 0, "hl": 0, "hpts": 0, "fpts": 0,
            "bonusPoints": 0,
            "gwPoints": {},
        }

    # Overlay the last finalized standings (frozen H2H + season totals so far).
    final_doc = league_ref.collection("standings").document("current").get()
    if final_doc.exists:
        for m in (final_doc.to_dict() or {}).get("managers", []) or []:
            row = rows.get(m.get("uid"))
            if row is None:
                continue
            for key in ("displayName", "teamName", "hw", "hd", "hl",
                        "hpts", "fpts", "bonusPoints"):
                if m.get(key) is not None:
                    row[key] = m[key]
            row["gwPoints"] = dict(m.get("gwPoints") or {})

    # Add the live in-progress GW's points on top of the fantasy totals.
    updated_at = None
    scores_doc = league_ref.collection("scores").document(str(current_gw)).get()
    if scores_doc.exists:
        sdata = scores_doc.to_dict() or {}
        updated_at = sdata.get("updatedAt")
        for muid, res in (sdata.get("results", {}) or {}).items():
            row = rows.get(muid)
            if row is None:
                continue
            pts = (res or {}).get("points", 0) or 0
            row["fpts"] += pts
            row["gwPoints"][str(current_gw)] = pts

    qualifiers = int(league.get("knockoutQualifiers", 8) or 8)
    ranked = sorted(
        rows.values(),
        key=lambda s: (s.get("hpts", 0), s.get("fpts", 0)),
        reverse=True,
    )
    for idx, s in enumerate(ranked, start=1):
        s["rank"] = idx
        s["qualified"] = idx <= qualifiers
        s["knockedOut"] = idx > qualifiers

    if updated_at is None:
        updated_at = datetime.now(timezone.utc)
    return {
        "managers": ranked,
        "qualifiers": qualifiers,
        "gw": current_gw,
        "live": True,
        "updatedAt": updated_at,
    }


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
    #
    # transfer_window_state bundles the override-aware current phase with the
    # real-clock schedule + next-phase boundaries (current + next GW) so the UI
    # can render live countdowns and a window timeline. `status`/`window` keep
    # their legacy shape so existing callers don't break.
    from fpl_predictor.game.wc_windows import TransferWindow, transfer_window_state
    state = transfer_window_state(lid, _db)
    is_none = state["phase"] == TransferWindow.NONE.value
    return _ok({
        "status": "closed" if is_none else "open",
        "window": None if is_none else {"phase": state["phase"], "gw": state["gw"]},
        "overridden": state["overridden"],
        "phaseEndsAt": state["phaseEndsAt"],
        "nextPhase": state["nextPhase"],
        "nextPhaseStartsAt": state["nextPhaseStartsAt"],
        "schedule": state["schedule"],
        "scheduledOverrides": state.get("scheduledOverrides", []),
        "wishlistAutoRun": state.get("wishlistAutoRun"),
    })


@wc_bp.route("/me/admin", methods=["GET"])
def get_is_admin():
    """Report whether the caller is an admin, for UI gating only (no 403)."""
    uid, err = _require_auth()
    if err:
        return err
    cfg = _db.collection("wc_config").document("tournament").get()
    cfg_d = cfg.to_dict() or {}
    admin_uids = cfg_d.get("adminUids", []) if cfg.exists else []
    super_uid = cfg_d.get("superAdminUid", DEFAULT_SUPER_ADMIN_UID) if cfg.exists else DEFAULT_SUPER_ADMIN_UID
    return _ok({"isAdmin": uid in admin_uids, "isSuperAdmin": uid == super_uid})


@wc_bp.route("/leagues/<lid>/admin/window-override", methods=["POST"])
def set_window_override(lid: str):
    """Ilay-only (on real leagues): force (or clear) the league's transfer-window phase.

    Body ``{phase, gw}``. ``phase`` of None/""/"auto" clears the override and
    returns to the time-based fixture-clock logic. A valid phase forces that
    window. Echoes the resolved effective window so the client can update.

    Ilay-only on real leagues (the window switcher is a super-admin power); on
    ``simulated`` (mock) leagues any authenticated member can flip the window so
    the showcase window-switcher works.
    """
    uid, err = _require_auth()
    if err:
        return err
    league_ref = _db.collection("leagues").document(lid)
    league_snap = league_ref.get()
    if not league_snap.exists:
        return _err("League not found", 404)
    if not (league_snap.to_dict() or {}).get("simulated"):
        _, admin_err = _require_super_admin()
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

    # AUTO-RUN: switching INTO free_agents fires the wishlist pipeline (same
    # rule as the timed schedule / cron tick — user decision: both paths).
    # Gated on both the admin's intent (phase) AND the resolved phase, so a
    # schedule/override precedence surprise can't run the auction on a switch
    # to some other phase. run_if_due itself no-ops on simulated leagues and
    # already-resolved GWs, and takes a lease against concurrent triggers.
    auto_run = None
    if phase == "free_agents" and window == TransferWindow.FREE_AGENTS:
        try:
            auto_run = _wishlist_autorun.run_if_due(lid, source="manual_override")
        except Exception as exc:  # surface, never fail the switch itself
            auto_run = {"lid": lid, "status": "failed", "error": str(exc)}

    league_snap = league_ref.get()
    overridden = bool((league_snap.to_dict() or {}).get("windowOverride")) if league_snap.exists else False
    if window == TransferWindow.NONE:
        return _ok({"status": "closed", "window": None, "overridden": overridden,
                    "wishlistAutoRun": auto_run})
    return _ok({
        "status": "open",
        "window": {"phase": window.value, "gw": upcoming_gw},
        "overridden": overridden,
        "wishlistAutoRun": auto_run,
    })


@wc_bp.route("/leagues/<lid>/admin/window-schedule", methods=["GET"])
def get_window_schedule(lid: str):
    """Return the league's timed window schedule (``[{phase, effectiveAt, gw}]``).

    Read access for any authenticated user (UI gating only); editing is
    Ilay-only via the POST below. ``effectiveAt`` is returned as stored (a
    Firestore timestamp → ISO on the wire)."""
    uid, err = _require_auth()
    if err:
        return err
    snap = _db.collection("leagues").document(lid).get()
    if not snap.exists:
        return _err("League not found", 404)
    return _ok({"schedule": (snap.to_dict() or {}).get("windowSchedule") or []})


@wc_bp.route("/leagues/<lid>/admin/window-schedule", methods=["POST"])
def set_window_schedule(lid: str):
    """Ilay-only: set (or clear) the league's timed window schedule.

    Body ``{schedule: [{phase, effectiveAt, gw?}]}`` where ``effectiveAt`` is a
    UTC ISO-8601 string (the client converts the admin's Israel-time input to
    UTC). Entries are validated, parsed to timestamps, sorted ascending, and
    written to ``leagues/{lid}.windowSchedule``. An empty list / null clears it.
    The schedule is applied LAZILY by the window resolver as the clock passes
    each entry — there is no background job. Echoes the resolved current window.
    """
    uid, err = _require_super_admin()
    if err:
        return err
    league_ref = _db.collection("leagues").document(lid)
    if not league_ref.get().exists:
        return _err("League not found", 404)

    body = request.get_json(silent=True) or {}
    raw = body.get("schedule")
    if raw in (None, [], {}):
        league_ref.update({"windowSchedule": firestore.DELETE_FIELD})
    elif isinstance(raw, list):
        valid = {"none", "trade", "free_agents", "next_gw_bid"}
        cleaned = []
        for e in raw:
            if not isinstance(e, dict):
                return _err("each schedule entry must be an object", 400)
            phase = e.get("phase")
            if phase not in valid:
                return _err(f"invalid phase: {phase}", 400)
            eff = e.get("effectiveAt")
            try:
                dt = datetime.fromisoformat(str(eff).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return _err(f"invalid effectiveAt: {eff}", 400)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            entry = {"phase": phase, "effectiveAt": dt}
            if e.get("gw") is not None:
                try:
                    entry["gw"] = int(e["gw"])
                except (TypeError, ValueError):
                    return _err(f"invalid gw: {e.get('gw')}", 400)
            cleaned.append(entry)
        cleaned.sort(key=lambda x: x["effectiveAt"])
        league_ref.update({"windowSchedule": cleaned})
    else:
        return _err("schedule must be a list", 400)

    from fpl_predictor.game.wc_windows import TransferWindow, current_window_from_db
    window, upcoming_gw = current_window_from_db(lid, _db)

    # AUTO-RUN: if the schedule just saved already resolves to free_agents
    # RIGHT NOW (an effectiveAt in the past), the wishlist pipeline is due —
    # don't make it wait for the next cron tick. Future entries are picked up
    # by /cron/window-tick as the clock passes them.
    auto_run = None
    if window == TransferWindow.FREE_AGENTS:
        try:
            auto_run = _wishlist_autorun.run_if_due(lid, source="schedule_save")
        except Exception as exc:  # surface, never fail the save itself
            auto_run = {"lid": lid, "status": "failed", "error": str(exc)}

    sched = (league_ref.get().to_dict() or {}).get("windowSchedule") or []
    return _ok({
        "schedule": sched,
        "window": None if window == TransferWindow.NONE else {"phase": window.value, "gw": upcoming_gw},
        "wishlistAutoRun": auto_run,
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
        from fpl_predictor.game.wc_wishlist_batches import batch_bids, enforce_cap
        bids = body.get("bids", [])
        if isinstance(bids, list):
            enforce_cap(bids)
        result = _wishlist_mgr.submit_bids(lid, uid, gw, bids)
        # Derived batch view of what was just stored (batched editor renders
        # the server's grouping, never its own).
        result["batches"] = batch_bids(result.get("bids") or [])
        return _ok(result, 201)
    except ValueError as exc:
        code = str(exc)
        # WISHLIST_LOCKED / AUCTION_RUNNING: stale-tab writes into a closed or
        # currently-resolving gw bucket — a conflict, not a bad request.
        if ("ALREADY_OWNED" in code or "WISHLIST_LOCKED" in code
                or "AUCTION_RUNNING" in code):
            return _err(code, 409)
        return _err(code)


@wc_bp.route("/leagues/<lid>/wishlist-bids-batched", methods=["POST"])
def submit_wishlist_bids_batched(lid: str):
    """Save the wishlist from the BATCHED editor.

    Body: ``{gw, batches: [{position, outs: [pid], ins: [pid]}, ...]}`` —
    both sides ordered (outs = leave order, ins = claim priority). The server
    expands OUT-major to the canonical flat list, enforces the expanded-size
    cap, and stores through the SAME ``submit_bids`` path as the flat editor,
    so per-bid ownership / free-agent / same-position validation and the
    closed-bucket gate apply unchanged. The flat list stays the only stored
    source of truth; the response carries both views, with ``batches``
    re-derived from what was actually stored (round-tripped).
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
        from fpl_predictor.game.wc_wishlist_batches import (
            batch_bids, enforce_cap, unbatch, validate_batches)
        batches = validate_batches(body.get("batches"))
        flat = unbatch(batches)
        enforce_cap(flat)
        result = _wishlist_mgr.submit_bids(lid, uid, gw, flat)
        result["batches"] = batch_bids(result.get("bids") or [])
        return _ok(result, 201)
    except ValueError as exc:
        code = str(exc)
        if ("ALREADY_OWNED" in code or "WISHLIST_LOCKED" in code
                or "AUCTION_RUNNING" in code):
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
    result = _wishlist_mgr.get_my_bids(lid, uid, gw)
    # Batch view only makes sense for a still-editable (pending) list —
    # resolved docs carry status fields and are display-only history.
    if not result.get("resolved"):
        from fpl_predictor.game.wc_wishlist_batches import batch_bids
        result["batches"] = batch_bids(result.get("bids") or [])
    return _ok(result)


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


def _fifa_norm(s):
    """Match the normaliser used to build fifa_alignment_spec.json exactly:
    NFKD -> ASCII-ignore (drops ø/ß/accents to nothing) -> lower -> strip '/./-."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("'", "").replace(".", " ").replace("-", " ")
    return " ".join(s.split())


_ALIGN_SPEC = None


def _load_align_spec():
    global _ALIGN_SPEC
    if _ALIGN_SPEC is None:
        import json
        p = os.path.join(os.path.dirname(__file__), "data", "fifa_alignment_spec.json")
        with open(p, encoding="utf-8") as f:
            _ALIGN_SPEC = json.load(f)
    return _ALIGN_SPEC


@wc_bp.route("/admin/leagues/<lid>/align-to-fifa", methods=["POST"])
def admin_align_to_fifa(lid: str):
    """MOCK-ONLY: align the live wc_players pool + the 6 canonical squads to the
    FIFA fantasy dataset, then re-score GW1+GW2.

    Per player (matched by team + normalised name against the bundled
    fifa_alignment_spec.json): adopt FIFA position + canonical name + draftRank
    (FIFA price ordering). Colliding names (two players sharing a normalised name
    within a team) KEEP their current position — never guessed. Adds the 244
    FIFA-only players, drops the 10 DB-only players that are not owned. Each
    squad is relabelled and rebalanced back to a legal 2/5/5/3 by dropping its
    lowest-value surplus-position player and adding a VALUE-MATCHED free agent
    (closest draftRank). GW1/GW2 playerScores + lineups are rebuilt and
    re-finalised so points/standings reflect the new positions.

    Body ``{"dryRun": true}`` computes the entire plan and returns it with NO
    writes. Idempotent. Gated to simulated leagues + authenticated callers.
    """
    _, err = _require_sim_league(lid)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    dry = bool(body.get("dryRun"))
    spec = _load_align_spec()
    teams, renames = spec["teams"], spec["renames"]
    collisions = {tuple(c.split("|", 1)) for c in spec["collisions"]}
    drops_set = {(d["iso"], d["norm"]) for d in spec["drops"]}
    from .seed.seed_league import seed_real_fixtures, GROUP_STAGE_EVENTS
    league_ref = _db.collection("leagues").document(lid)
    QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}
    summary = {"dryRun": dry, "poolFlips": [], "poolRenames": [], "added": [],
               "dropped": [], "dropBlockedOwned": [], "collisionKept": [],
               "unmatched": [], "rebalanced": {}, "finalized": [],
               "finalizeErrors": {}}

    # 1. Squads + ownership first (needed for drop-safety + rebalance).
    squads, owned = {}, set()
    for sq in league_ref.collection("squads").get():
        players = (sq.to_dict() or {}).get("players", [])
        squads[sq.id] = players
        owned.update(int(p["playerId"]) for p in players)

    # 2. Walk wc_players: relabel / flip / rename / collision-keep / mark drops.
    all_docs = list(_db.collection("wc_players").get())

    # 2a. Backup the pre-migration pool + squads to a single doc (apply only) so
    #     the change has a one-shot rollback point. gamedb is not writable from a
    #     local SDK, so the snapshot lives server-side.
    if not dry:
        backup = {"ts": SERVER_TIMESTAMP, "players": {}, "squads": {}}
        for d in all_docs:
            pd = d.to_dict() or {}
            backup["players"][str(d.id)] = {
                "name": pd.get("name"), "position": pd.get("position"),
                "positionName": pd.get("positionName"),
                "draftRank": pd.get("draftRank")}
        for uid, players in squads.items():
            backup["squads"][uid] = players
        _db.collection("wc_config").document("fifa_align_backup").set(backup)

    new_by_id = {}        # pid -> {pos,name,iso,rank,teamId,teamName}
    existing_norm = {}    # (iso, norm) -> pid  (post-rename; for add idempotency)
    team_meta = {}        # iso -> {teamId, teamName}
    drop_refs, max_id = [], 0
    for d in all_docs:
        pd = d.to_dict() or {}
        try:
            pid = int(pd.get("id", d.id))
        except (TypeError, ValueError):
            pid = None
        if pid and pid > max_id:
            max_id = pid
        iso = pd.get("teamIso", "")
        tid, tname = pd.get("teamId"), pd.get("teamName", "")
        if iso and iso not in team_meta and tid:
            team_meta[iso] = {"teamId": tid, "teamName": tname}
        cur_pos = pd.get("position")
        name = pd.get("name", "")
        nn = _fifa_norm(name)

        def _remember(pos, nm, rank, key_norm):
            if pid is not None:
                new_by_id[pid] = {"pos": pos, "name": nm, "iso": iso, "rank": rank,
                                  "teamId": tid, "teamName": tname}
                existing_norm[(iso, key_norm)] = pid

        if (iso, nn) in collisions:
            entry = teams.get(iso, {}).get(nn)
            rank = entry["rank"] if entry else pd.get("draftRank", 0)
            if not dry:
                d.reference.update({"draftRank": rank})
            summary["collisionKept"].append({"id": pid, "name": name, "pos": cur_pos})
            _remember(cur_pos, name, rank, nn)
            continue

        target = renames.get(iso, {}).get(nn, nn)
        entry = teams.get(iso, {}).get(target)
        if entry:
            np_, nname, rank = entry["pos"], entry["name"], entry["rank"]
            if not dry:
                d.reference.update({"position": np_, "positionName": _POS_NAME[np_],
                                    "element_type": np_, "name": nname, "draftRank": rank})
            if np_ != cur_pos:
                summary["poolFlips"].append({"id": pid, "name": nname,
                                             "from": cur_pos, "to": np_})
            if nname != name:
                summary["poolRenames"].append({"id": pid, "from": name, "to": nname})
            _remember(np_, nname, rank, _fifa_norm(nname))
        elif (iso, nn) in drops_set:
            if pid in owned:
                summary["dropBlockedOwned"].append({"id": pid, "name": name})
                _remember(cur_pos, name, pd.get("draftRank", 0), nn)
            else:
                drop_refs.append(d.reference)
                summary["dropped"].append({"id": pid, "name": name, "iso": iso})
        else:
            summary["unmatched"].append({"id": pid, "name": name, "iso": iso})
            _remember(cur_pos, name, pd.get("draftRank", 0), nn)

    # 3. Drop the unowned not-in-FIFA players.
    if not dry:
        for ref in drop_refs:
            ref.delete()

    # 4. Add the FIFA-only players (idempotent — skip any already present).
    next_id = max_id + 1
    for a in spec["adds"]:
        iso, name, pos, rank = a["iso"], a["name"], a["pos"], a["rank"]
        nn = _fifa_norm(name)
        if (iso, nn) in existing_norm:
            continue
        meta = team_meta.get(iso, {"teamId": 0, "teamName": iso})
        pid, next_id = next_id, next_id + 1
        doc = {"id": pid, "name": name, "position": pos, "positionName": _POS_NAME[pos],
               "element_type": pos, "teamIso": iso, "teamId": meta["teamId"],
               "teamName": meta["teamName"], "draftRank": rank, "totalPoints": 0,
               "eliminated": False, "photo": ""}
        if not dry:
            _db.collection("wc_players").document(str(pid)).set(doc)
        summary["added"].append({"id": pid, "name": name, "iso": iso, "pos": pos})
        new_by_id[pid] = {"pos": pos, "name": name, "iso": iso, "rank": rank,
                          "teamId": meta["teamId"], "teamName": meta["teamName"]}
        existing_norm[(iso, nn)] = pid

    # 5. Relabel each squad's denormalised fields, then rebalance to 2/5/5/3.
    def _free_agents(pos, exclude):
        out = []
        for fid, info in new_by_id.items():
            if info["pos"] == pos and fid not in owned and fid not in exclude:
                out.append((info["rank"], fid, info))
        out.sort(key=lambda x: x[0])
        return out

    picked = set()
    for uid in MOCK_CANONICAL_ROSTER:
        players = squads.get(uid)
        if not players:
            continue
        for p in players:
            info = new_by_id.get(int(p["playerId"]))
            if info:
                p["position"] = info["pos"]
                p["positionName"] = _POS_NAME[info["pos"]]
                p["name"] = info["name"]

        def _counts():
            c = {1: 0, 2: 0, 3: 0, 4: 0}
            for p in players:
                c[int(p["position"])] += 1
            return c

        def _rank(p):
            info = new_by_id.get(int(p["playerId"]))
            return info["rank"] if info else 99999

        drops, adds = [], []
        # trim surplus: drop the LOWEST-value (highest rank number) player
        for pos in (1, 2, 3, 4):
            while _counts()[pos] > QUOTA[pos]:
                cands = sorted((p for p in players if int(p["position"]) == pos),
                               key=_rank)
                victim = cands[-1]
                players.remove(victim)
                owned.discard(int(victim["playerId"]))
                drops.append(victim)
        # fill deficits with value-matched free agents (closest rank to a drop)
        deficit = []
        cc = _counts()
        for pos in (1, 2, 3, 4):
            deficit += [pos] * (QUOTA[pos] - cc[pos])
        drop_ranks = sorted((_rank(v) for v in drops), reverse=True)
        for i, pos in enumerate(deficit):
            target = drop_ranks[i] if i < len(drop_ranks) else 0
            fa = _free_agents(pos, picked)
            if not fa:
                continue
            fa.sort(key=lambda x: abs(x[0] - target))
            rank, fid, info = fa[0]
            picked.add(fid)
            owned.add(fid)
            adds.append({"playerId": fid, "draftedRound": 99, "position": pos,
                         "positionName": _POS_NAME[pos], "name": info["name"],
                         "teamIso": info["iso"], "teamId": info["teamId"],
                         "teamName": info["teamName"], "eliminated": False})
        for a in adds:
            players.append(a)
        if drops or adds:
            if not dry:
                league_ref.collection("squads").document(uid).update({"players": players})
            summary["rebalanced"][uid] = {
                "drop": [v.get("name") for v in drops],
                "add": [a["name"] for a in adds],
                "counts": _counts()}

    # 6. Rebuild playerScores with the new positions, regenerate every squad's
    #    GW1/GW2 lineup (positions changed -> old XI may be illegal) and
    #    re-finalise so points + standings are consistent. (apply mode only)
    if not dry:
        drafted = {}
        for uid in MOCK_CANONICAL_ROSTER:
            for p in squads.get(uid, []):
                drafted[int(p["playerId"])] = {
                    "id": int(p["playerId"]), "name": p.get("name", ""),
                    "position": int(p["position"]), "teamIso": p.get("teamIso", "")}
        summary["fixtures"] = seed_real_fixtures(
            _db, drafted, GROUP_STAGE_EVENTS, played_gws=(1, 2))
        for uid in MOCK_CANONICAL_ROSTER:
            rich = [{"playerId": p["playerId"], "position": int(p["position"])}
                    for p in squads.get(uid, [])]
            if not rich:
                continue
            for gw in (1, 2):
                try:
                    league_ref.collection("lineups").document(f"{uid}_{gw}").set(
                        select_lineup(rich))
                except Exception as exc:
                    summary["finalizeErrors"][f"lineup_{uid}_{gw}"] = str(exc)
        for gw in (1, 2):
            try:
                finalize_gw(lid, gw, _db, _wc)
                summary["finalized"].append(gw)
            except Exception as exc:
                summary["finalizeErrors"][gw] = str(exc)
        league_ref.update({"currentGw": 3, "status": "group_phase"})

    summary["totals"] = {
        "poolFlips": len(summary["poolFlips"]),
        "poolRenames": len(summary["poolRenames"]),
        "added": len(summary["added"]),
        "dropped": len(summary["dropped"]),
        "dropBlockedOwned": len(summary["dropBlockedOwned"]),
        "collisionKept": len(summary["collisionKept"]),
        "unmatched": len(summary["unmatched"]),
        "squadsRebalanced": len(summary["rebalanced"])}
    return _ok(summary)


@wc_bp.route("/admin/leagues/<lid>/clear-history", methods=["POST"])
def admin_clear_history(lid: str):
    """MOCK-ONLY: wipe the transfer/trade/wishlist HISTORY (all reset/seed/demo
    artifacts that no longer reflect real activity). Deletes every doc in the
    league's ``transactions``, ``wishlist_results`` and ``trades`` collections —
    the exact sources the History tab reads. Squads, lineups, scores, standings,
    gw_history and current pending ``wishlist_bids`` are NOT touched, and the
    write paths are unchanged, so any NEW trade / wishlist claim records cleanly
    from here on. Snapshots the cleared docs to ``wc_config/history_backup``
    first. Idempotent. Gated to simulated leagues + authenticated callers.
    """
    _, err = _require_sim_league(lid)
    if err:
        return err
    league_ref = _db.collection("leagues").document(lid)
    colls = ["transactions", "wishlist_results", "trades"]
    backup = {"ts": SERVER_TIMESTAMP, "lid": lid}
    summary = {"deleted": {}}
    for c in colls:
        docs = list(league_ref.collection(c).get())
        backup[c] = [{"id": d.id, **(d.to_dict() or {})} for d in docs]
        for d in docs:
            d.reference.delete()
        summary["deleted"][c] = len(docs)
    _db.collection("wc_config").document("history_backup").set(backup)
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
    force = bool((request.get_json(silent=True) or {}).get("force"))
    try:
        result = _wishlist_mgr.run_auction(lid, gw, force=force)
        return _ok(result)
    except ValueError as exc:
        # Idempotency guard (already resolved) → 409 Conflict, not a 500.
        return _err(str(exc), 409)
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
    force = bool((request.get_json(silent=True) or {}).get("force"))
    try:
        deferred = _trade_mgr.process_deferred_trades(lid, gw)
        auction = _wishlist_mgr.run_auction(lid, gw, force=force)
        return _ok({"deferredTrades": deferred, "wishlistAuction": auction})
    except ValueError as exc:
        return _err(str(exc), 409)
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/leagues/<lid>/rollback-wishlist/<int:gw>", methods=["POST"])
def admin_rollback_wishlist(lid: str, gw: int):
    """Ilay-only: undo a GW's wishlist auction so it can be cleanly re-run.

    Reverses every wishlist_claim swap (all-or-nothing — 409 if not cleanly
    reversible), un-resolves the bid docs back to pending, and clears the
    results doc + the gw's wishlist_claim transactions.
    """
    uid, err = _require_super_admin()
    if err:
        return err
    try:
        return _ok(_wishlist_mgr.rollback_auction(lid, gw))
    except ValueError as exc:
        return _err(str(exc), 409)
    except Exception as exc:
        return _err(str(exc), 500)


@wc_bp.route("/admin/leagues/<lid>/run-mock-wishlist", methods=["POST"])
def admin_run_mock_wishlist(lid: str):
    """MOCK ONLY: demo the wishlist auction end-to-end in one click.

    Opens the FREE_AGENTS window (closing the trade window), auto-fills 1-3
    wishlist bids for every manager EXCEPT the caller/viewed manager (top free
    agents in, their worst players out — same position), then resolves the
    auction so squads actually change.

    SIMULATED LEAGUES ONLY — it fabricates bids, so it must NEVER touch a real
    league (this once polluted the real draft with fake bids). Hard-gated via
    ``_require_sim_league``; the real-league path is removed.

    Body: ``{gw?, excludeUid?}``. ``excludeUid`` (the manager running it) keeps
    their own real bids; defaults to the authenticated uid.
    """
    ld, err = _require_sim_league(lid)
    if err:
        return err
    uid, _ = _require_auth()
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


@wc_bp.route("/admin/ingest-live-scores", methods=["POST"])
def admin_ingest_live_scores():
    """Free live-scoring pass: FIFA fantasy round points + ESPN stat lines ->
    playerScores + live per-manager totals. Body: {gw, date} (date=YYYYMMDD).
    gw defaults to the current GW of lg_mock_draft; date defaults to today UTC.
    Safe to call every ~10 min during matches and ~1h after (the writes are
    idempotent and never set processedForFantasy, so finalize still runs)."""
    uid, err = _require_auth()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    gw = body.get("gw")
    date = body.get("date")
    if gw is None:
        lg = _db.collection("leagues").document("lg_mock_draft").get()
        gw = (lg.to_dict() or {}).get("currentGw", 1) if lg.exists else 1
    if not date:
        from datetime import datetime, timezone
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
    try:
        from fpl_predictor.data.wc_live_ingest import ingest_live
        res = ingest_live(_db, int(gw), str(date))
        return _ok(res)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return _err(f"ingest failed: {exc}", 500)


@wc_bp.route("/sync-live-scores", methods=["POST"])
def sync_live_scores_user():
    """The 'Sync data' button: ANY signed-in league member can pull fresh
    scores on demand (same self-healing catch_up_scan the cron runs — scores
    live matches, retro-scores missed finished ones, sets bookmarks).

    Debounced via wc_config/scan_state.lastScanAt: if a scan ran in the last
    60s the call returns {skipped: true} immediately, so a click-happy league
    can't hammer FIFA/ESPN. From cloud hosting WhoScored is unreachable, so
    this delivers FIFA points + ESPN stats; DefCon layers on from the
    residential-IP scheduled runs."""
    uid, err = _require_auth()
    if err:
        return err
    from datetime import datetime, timezone, timedelta
    st = _db.collection("wc_config").document("scan_state").get().to_dict() or {}
    last = st.get("lastScanAt")
    if last is not None and (datetime.now(timezone.utc) - last) < timedelta(seconds=60):
        return _ok({"skipped": True, "reason": "synced less than 60s ago"})
    try:
        days = max(0, min(int(request.args.get("daysBack", 1)), 7))
    except (TypeError, ValueError):
        days = 1
    try:
        from fpl_predictor.data.wc_live_ingest import catch_up_scan
        res = catch_up_scan(_db, days_back=days)
        return _ok({"skipped": False, "requestedBy": uid, **res})
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return _err(f"sync failed: {exc}", 500)


@wc_bp.route("/cron/ingest-live-scores", methods=["POST", "GET"])
def cron_ingest_live_scores():
    """Secret-gated scheduled scorer for Cloud Scheduler (no Firebase login).
    One pass: refresh the WhoScored id map + score every live/finished WC match
    from WhoScored (DefCon + FIFA points), ESPN fallback. Idempotent + never
    finalizes. Auth: ?key=<cron secret stored at wc_config/cron.secret>.

    The response reports whoscoredOk so we can see if WhoScored is reachable from
    this host (it may block datacenter IPs)."""
    key = request.args.get("key") or (request.get_json(silent=True) or {}).get("key")
    cfg = _db.collection("wc_config").document("cron").get()
    secret = (cfg.to_dict() or {}).get("secret") if cfg.exists else None
    if not secret or key != secret:
        return _err("Unauthorized", 401)
    try:
        from fpl_predictor.data.wc_live_ingest import (
            catch_up_scan, discover_whoscored_ids, _ws_match_centre)
        # quick reachability probe (one known match) so the run is observable
        ws_ok = False
        try:
            ws_ok = bool(_ws_match_centre(1953853))
        except Exception:
            ws_ok = False
        try:
            discover_whoscored_ids(_db)
        except Exception:
            pass
        # catch_up_scan is self-healing: it scores live matches AND retroactively
        # any FINISHED match not yet bookmarked (scoredFinal), so a redeploy or
        # downtime never loses a game. Every cron tick is also a catch-up pass.
        days = int(request.args.get("daysBack", 3))
        res = catch_up_scan(_db, days_back=days)
        res["whoscoredOk"] = ws_ok
        return _ok(res)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return _err(f"cron ingest failed: {exc}", 500)


@wc_bp.route("/cron/window-tick", methods=["POST", "GET"])
def cron_window_tick():
    """Secret-gated scheduled window tick (Cloud Scheduler, every ~5 min).

    For every REAL league: when the FREE_AGENTS window is open and that GW's
    wishlist auction hasn't run, fire the auto-run pipeline (snapshot → sweep
    stale bids → deferred trades → auction) exactly once — a transactional
    lease makes overlapping ticks/admin clicks no-ops. This is what actually
    executes the Trade → Free-agents transition's auction; the timed
    ``windowSchedule`` only flips the PHASE (lazily, on read) and by design
    runs nothing. Blocked runs (previous GW not finalized, earlier auction
    skipped, failed/rolled-back lease) are surfaced on
    ``leagues/{lid}.wishlistAutoRun`` and retried on later ticks.

    Auth: ``?key=<cron secret stored at wc_config/cron.secret>`` (same as
    ``/cron/ingest-live-scores``). Simulated leagues are never touched.
    """
    key = request.args.get("key") or (request.get_json(silent=True) or {}).get("key")
    cfg = _db.collection("wc_config").document("cron").get()
    secret = (cfg.to_dict() or {}).get("secret") if cfg.exists else None
    if not secret or key != secret:
        return _err("Unauthorized", 401)
    results = []
    for snap in _db.collection("leagues").get():
        ld = snap.to_dict() or {}
        if ld.get("simulated"):
            continue
        try:
            results.append(_wishlist_autorun.run_if_due(snap.id, source="cron"))
        except Exception as exc:
            results.append({"lid": snap.id, "status": "error", "error": str(exc)})
    return _ok({"leagues": results})
