"""
FPL Draft Analyzer - Flask REST API.

All data is fetched live from the FPL API with in-memory caching.
No local database required.
"""

import os
import math
import logging
from flask import Flask, jsonify, request, send_from_directory, g
from flask_cors import CORS
import firebase_admin
from firebase_admin import auth as fb_auth, firestore as fb_firestore

firebase_admin.initialize_app(options={"projectId": "fpl-analyzer-792eb"})
db = fb_firestore.client(database_id="gamedb")
log = logging.getLogger(__name__)

from .data.fpl_api import FPLClient
from .engine.analysis import SquadAnalyzer, POSITION_NAMES
from .engine.predictor import PlayerPredictor
from .engine.team_form import TeamFormAnalyzer
from .engine.ndk import NDKSimulator
from .engine.lineup_predictor import LineupPredictor
from .engine.shared_stats import (
    clear_lineup_cache, compute_next_game_probability,
)
from .engine.trend_detector import trend_summary
from .engine.source_tracker import (
    SourceCredibilityTracker, build_actual_lineups,
    extract_source_predictions,
)
from .game import (
    LeagueManager, DraftEngine, SquadManager,
    ScoringEngine, TradeManager, WaiverManager, ScheduleManager,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

IS_CLOUD = os.environ.get("K_SERVICE") or os.environ.get("FUNCTION_TARGET")

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

from datetime import datetime as _datetime
from flask.json.provider import DefaultJSONProvider as _DefJP

class _SafeJSONProvider(_DefJP):
    def default(self, o):
        if isinstance(o, _datetime):
            return o.isoformat()
        return super().default(o)

app.json_provider_class = _SafeJSONProvider
app.json = _SafeJSONProvider(app)

fpl = FPLClient()
fpl.warm_cache()
lineup_pred = LineupPredictor(fpl)
predictor = PlayerPredictor(fpl, lineup_predictor=lineup_pred)
team_form_analyzer = TeamFormAnalyzer(fpl)
ndk_sim = NDKSimulator(fpl)
source_tracker = SourceCredibilityTracker()

league_mgr = LeagueManager(db)
squad_mgr = SquadManager(db, fpl)
draft_engine = DraftEngine(db, fpl)
scoring_engine = ScoringEngine(db, fpl, squad_mgr)
trade_mgr = TradeManager(db)
waiver_mgr = WaiverManager(db, fpl)
schedule_mgr = ScheduleManager(db)

# WC2026 Blueprint
from .api_wc import wc_bp, init_wc
init_wc(db)
app.register_blueprint(wc_bp, url_prefix="/api/v1/wc")


def _clean(obj):
    """Recursively replace NaN/inf floats and Firestore timestamps for JSON safety."""
    from datetime import datetime
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


@app.after_request
def _no_cache(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


AUTH_EXEMPT = {"/api/health", "/api/v1/wc/admin/seed-test-leagues"}


@app.before_request
def verify_firebase_token():
    if not request.path.startswith("/api/") or request.path in AUTH_EXEMPT:
        return None
    if request.method == "OPTIONS":
        return None
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        token = auth_header.split("Bearer ")[1]
        g.user = fb_auth.verify_id_token(token)
    except Exception as exc:
        log.warning("Token verification failed: %s", exc)
        return jsonify({"error": "Invalid or expired token"}), 401
    return None


# ──────────────────────────────────────────────────────────────────────
# Static files (local dev only - Netlify serves frontend in production)
# ──────────────────────────────────────────────────────────────────────

if not IS_CLOUD:
    @app.route("/")
    def serve_index():
        return send_from_directory(PROJECT_ROOT, "index.html")

    @app.route("/<path:path>")
    def serve_static(path):
        full = os.path.join(PROJECT_ROOT, path)
        if os.path.isfile(full):
            return send_from_directory(PROJECT_ROOT, path)
        return "Not found", 404


# ──────────────────────────────────────────────────────────────────────
# User preferences (Firestore-backed)
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/user/preferences", methods=["GET"])
def get_user_preferences():
    uid = g.user["uid"]
    doc = db.collection("users").document(uid).get()
    if doc.exists:
        return jsonify(doc.to_dict())
    return jsonify({})


@app.route("/api/user/preferences", methods=["POST"])
def set_user_preferences():
    uid = g.user["uid"]
    data = request.json or {}
    allowed = {"leagueId", "starPlayers", "displayName"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["lastLogin"] = fb_firestore.SERVER_TIMESTAMP
    db.collection("users").document(uid).set(update, merge=True)
    return jsonify({"status": "ok"})


def _game_error(fn):
    """Wrap game engine calls to return proper HTTP errors."""
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            log.exception("Game API error")
            return jsonify({"error": "Internal error"}), 500
    return wrapper


# ──────────────────────────────────────────────────────────────────────
# Leagues
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/game/leagues", methods=["GET"])
@_game_error
def game_list_leagues():
    return jsonify(league_mgr.get_my_leagues(g.user["uid"]))


@app.route("/api/game/leagues", methods=["POST"])
@_game_error
def game_create_league():
    data = request.json or {}
    display_name = data.get("displayName") or g.user.get("name", "Manager")
    result = league_mgr.create_league(
        uid=g.user["uid"],
        name=data.get("name", "My League"),
        display_name=display_name,
        fmt=data.get("format", "h2h"),
        trade_approval=data.get("tradeApproval", "vote"),
        pick_timer=data.get("pickTimer", 30),
        max_members=data.get("maxMembers", 8),
    )
    return jsonify(result), 201


@app.route("/api/game/leagues/import", methods=["POST"])
@_game_error
def game_import_league():
    """Import a real FPL Draft league with full schedule, results, and deadlines."""
    from collections import Counter, defaultdict

    data = request.json or {}
    fpl_league_id = int(data.get("fplLeagueId", 0))
    if not fpl_league_id:
        raise ValueError("fplLeagueId is required")

    uid = g.user["uid"]

    league_data = fpl.get_league(fpl_league_id)
    info = league_data.get("league", {})
    entries = league_data.get("league_entries", [])
    matches = league_data.get("matches", [])
    if not entries:
        raise ValueError("No entries found in that FPL league")

    current_gw = fpl.get_current_gw()
    player_map = fpl.get_player_map()
    team_map = fpl.get_team_map()
    POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    start_event = info.get("start_event", 1)

    fmt = "h2h" if info.get("scoring") == "h" else "classic"
    league_ref = db.collection("leagues").document()
    league_ref.set({
        "name": info.get("name", f"FPL League {fpl_league_id}"),
        "format": fmt,
        "status": "active",
        "imported": True,
        "adminUid": uid,
        "maxMembers": len(entries),
        "tradeApproval": "vote",
        "pickTimer": info.get("draft_pick_time_limit", 30),
        "inviteCode": f"IMP{fpl_league_id}",
        "fplLeagueId": fpl_league_id,
        "seasonStartGw": start_event,
        "currentGw": current_gw,
    })

    lid = league_ref.id

    # entry_map keyed by league_entry_id (entry["id"]) for match mapping
    le_map = {}
    # entry_id_map keyed by entry_id for squad fetching
    eid_map = {}

    for i, entry in enumerate(entries):
        entry_id = entry["entry_id"]
        league_entry_id = entry["id"]
        is_admin = entry_id == info.get("admin_entry")
        member_uid = uid if is_admin else f"bot_{entry_id}"

        le_map[league_entry_id] = member_uid
        eid_map[entry_id] = member_uid

        league_ref.collection("members").document(member_uid).set({
            "displayName": f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}".strip(),
            "teamName": entry.get("entry_name", f"Team {i+1}"),
            "draftPosition": i + 1,
            "role": "admin" if is_admin else "manager",
            "waiverPriority": i + 1,
            "fplEntryId": entry_id,
            "fplLeagueEntryId": league_entry_id,
        })

        picks = fpl.get_squad(entry_id, current_gw)
        squad_players = []
        starting, bench = [], []

        for pick in picks:
            pid = pick["element"]
            p = player_map.get(pid, {})
            squad_players.append({
                "playerId": pid,
                "webName": p.get("web_name", "?"),
                "position": p.get("element_type", 0),
                "positionName": POS.get(p.get("element_type", 0), "?"),
                "teamId": p.get("team", 0),
                "teamShort": team_map.get(p.get("team", 0), {}).get("short_name", "?"),
            })
            if pick.get("position", 99) <= 11:
                starting.append(pid)
            else:
                bench.append(pid)

        league_ref.collection("squads").document(member_uid).set({"players": squad_players})

        if starting:
            pc = Counter(player_map.get(p, {}).get("element_type", 0) for p in starting)
            league_ref.collection("lineups").document(f"{member_uid}_{current_gw}").set({
                "starting": starting, "bench": bench,
                "formation": [pc.get(1, 0), pc.get(2, 0), pc.get(3, 0), pc.get(4, 0)],
                "locked": False, "autoSubsMade": [],
            })

    # ── Import H2H schedule + results from real FPL ──
    gw_matches = defaultdict(list)
    for m in matches:
        gw = m.get("event")
        home_uid = le_map.get(m.get("league_entry_1"))
        away_uid = le_map.get(m.get("league_entry_2"))
        if not home_uid or not away_uid or not gw:
            continue
        gw_matches[gw].append({
            "home": home_uid,
            "away": away_uid,
            "homePoints": m.get("league_entry_1_points", 0),
            "awayPoints": m.get("league_entry_2_points", 0),
            "finished": bool(m.get("finished")),
        })

    for gw, match_list in gw_matches.items():
        league_ref.collection("schedule").document(str(gw)).set({
            "gw": gw, "matches": match_list,
        })

    # ── Import GW deadlines ──
    deadlines = {}
    try:
        events_data = fpl.get_bootstrap()["events"].get("data", [])
        for ev in events_data:
            gw_id = ev.get("id")
            if gw_id:
                deadlines[str(gw_id)] = {
                    "deadline": ev.get("deadline_time", ""),
                    "waivers": ev.get("waivers_time", ""),
                }
    except Exception:
        pass

    league_ref.update({"deadlines": deadlines})
    league_mgr._add_league_to_user(uid, lid)

    finished_gws = sum(1 for ml in gw_matches.values() if any(m["finished"] for m in ml))

    return jsonify({
        "leagueId": lid,
        "name": info.get("name", "?"),
        "membersImported": len(entries),
        "currentGw": current_gw,
        "format": fmt,
        "matchesImported": sum(len(v) for v in gw_matches.values()),
        "finishedGws": finished_gws,
    }), 201


@app.route("/api/game/leagues/join", methods=["POST"])
@_game_error
def game_join_league():
    data = request.json or {}
    display_name = data.get("displayName") or g.user.get("name", "Manager")
    result = league_mgr.join_league(
        uid=g.user["uid"],
        invite_code=data.get("inviteCode", ""),
        display_name=display_name,
        team_name=data.get("teamName"),
    )
    return jsonify(result)


@app.route("/api/game/leagues/<lid>", methods=["GET"])
@_game_error
def game_get_league(lid):
    return jsonify(league_mgr.get_league(lid, g.user["uid"]))


@app.route("/api/game/leagues/<lid>", methods=["PATCH"])
@_game_error
def game_update_league(lid):
    return jsonify(league_mgr.update_league(lid, g.user["uid"], request.json or {}))


@app.route("/api/game/leagues/<lid>/leave", methods=["POST"])
@_game_error
def game_leave_league(lid):
    league_mgr.leave_league(lid, g.user["uid"])
    return jsonify({"status": "ok"})


# ──────────────────────────────────────────────────────────────────────
# Draft
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/game/leagues/<lid>/draft/start", methods=["POST"])
@_game_error
def game_start_draft(lid):
    current_gw = fpl.get_current_gw()
    return jsonify(draft_engine.start_draft(lid, g.user["uid"], current_gw))


@app.route("/api/game/leagues/<lid>/draft", methods=["GET"])
@_game_error
def game_get_draft(lid):
    return jsonify(draft_engine.get_draft_state(lid))


@app.route("/api/game/leagues/<lid>/draft/pick", methods=["POST"])
@_game_error
def game_make_pick(lid):
    data = request.json or {}
    player_id = data.get("playerId")
    if not player_id:
        return jsonify({"error": "playerId required"}), 400
    return jsonify(draft_engine.make_pick(lid, g.user["uid"], player_id))


@app.route("/api/game/leagues/<lid>/draft/auto-pick", methods=["POST"])
@_game_error
def game_auto_pick(lid):
    return jsonify(draft_engine.auto_pick(lid))


@app.route("/api/game/leagues/<lid>/draft/available", methods=["GET"])
@_game_error
def game_available_players(lid):
    pos = request.args.get("position", type=int)
    return jsonify(draft_engine.get_available_players(lid, pos))


# ──────────────────────────────────────────────────────────────────────
# Squad & Lineup
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/game/leagues/<lid>/squad", methods=["GET"])
@_game_error
def game_get_squad(lid):
    return jsonify(squad_mgr.get_squad(lid, g.user["uid"]))


@app.route("/api/game/leagues/<lid>/lineup/<int:gw>", methods=["GET"])
@_game_error
def game_get_lineup(lid, gw):
    return jsonify(squad_mgr.get_lineup(lid, g.user["uid"], gw))


@app.route("/api/game/leagues/<lid>/lineup/<int:gw>", methods=["POST"])
@_game_error
def game_set_lineup(lid, gw):
    data = request.json or {}
    return jsonify(squad_mgr.set_lineup(
        lid, g.user["uid"], gw,
        data.get("starting", []),
        data.get("bench", []),
    ))


# ──────────────────────────────────────────────────────────────────────
# Scoring & Standings
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/game/leagues/<lid>/scores/<int:gw>/process", methods=["POST"])
@_game_error
def game_process_scores(lid, gw):
    return jsonify(scoring_engine.process_gw(lid, gw))


@app.route("/api/game/leagues/<lid>/scores/<int:gw>", methods=["GET"])
@_game_error
def game_get_scores(lid, gw):
    return jsonify(scoring_engine.get_gw_scores(lid, gw))


@app.route("/api/game/leagues/<lid>/standings", methods=["GET"])
@_game_error
def game_get_standings(lid):
    return jsonify(scoring_engine.get_standings(lid))


# ──────────────────────────────────────────────────────────────────────
# Schedule
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/game/leagues/<lid>/schedule/generate", methods=["POST"])
@_game_error
def game_generate_schedule(lid):
    data = request.json or {}
    start = data.get("startGw", 1)
    end = data.get("endGw", 38)
    return jsonify(schedule_mgr.generate_schedule(lid, start, end))


@app.route("/api/game/leagues/<lid>/schedule/<int:gw>", methods=["GET"])
@_game_error
def game_get_schedule(lid, gw):
    return jsonify(schedule_mgr.get_gw_schedule(lid, gw))


# ──────────────────────────────────────────────────────────────────────
# Trades
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/game/leagues/<lid>/trades", methods=["GET"])
@_game_error
def game_get_trades(lid):
    status = request.args.get("status")
    return jsonify(trade_mgr.get_trades(lid, status))


@app.route("/api/game/leagues/<lid>/trades", methods=["POST"])
@_game_error
def game_propose_trade(lid):
    data = request.json or {}
    return jsonify(trade_mgr.propose_trade(
        lid, g.user["uid"],
        data.get("targetUid", ""),
        data.get("proposerPlayers", []),
        data.get("targetPlayers", []),
    ))


@app.route("/api/game/leagues/<lid>/trades/<tid>/respond", methods=["POST"])
@_game_error
def game_respond_trade(lid, tid):
    data = request.json or {}
    return jsonify(trade_mgr.respond_trade(lid, tid, g.user["uid"], data.get("action", "")))


@app.route("/api/game/leagues/<lid>/trades/<tid>/approve", methods=["POST"])
@_game_error
def game_admin_approve_trade(lid, tid):
    return jsonify(trade_mgr.admin_approve(lid, tid, g.user["uid"]))


@app.route("/api/game/leagues/<lid>/trades/<tid>/veto", methods=["POST"])
@_game_error
def game_veto_trade(lid, tid):
    return jsonify(trade_mgr.cast_veto(lid, tid, g.user["uid"]))


# ──────────────────────────────────────────────────────────────────────
# Waivers & Free Agents
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/game/leagues/<lid>/waivers", methods=["POST"])
@_game_error
def game_submit_waiver(lid):
    data = request.json or {}
    gw = data.get("gw") or fpl.get_next_gw()
    return jsonify(waiver_mgr.submit_waiver(
        lid, g.user["uid"],
        data.get("playerIn", 0),
        data.get("playerOut", 0),
        gw,
    ))


@app.route("/api/game/leagues/<lid>/waivers/<wid>", methods=["DELETE"])
@_game_error
def game_cancel_waiver(lid, wid):
    waiver_mgr.cancel_waiver(lid, wid, g.user["uid"])
    return jsonify({"status": "ok"})


@app.route("/api/game/leagues/<lid>/waivers/process", methods=["POST"])
@_game_error
def game_process_waivers(lid):
    data = request.json or {}
    gw = data.get("gw") or fpl.get_next_gw()
    return jsonify(waiver_mgr.process_waivers(lid, gw))


@app.route("/api/game/leagues/<lid>/free-agents/sign", methods=["POST"])
@_game_error
def game_sign_fa(lid):
    data = request.json or {}
    return jsonify(waiver_mgr.sign_free_agent(
        lid, g.user["uid"],
        data.get("playerIn", 0),
        data.get("playerOut", 0),
    ))


@app.route("/api/game/leagues/<lid>/free-agents", methods=["GET"])
@_game_error
def game_free_agents(lid):
    pos = request.args.get("position", type=int)
    return jsonify(waiver_mgr.get_free_agents(lid, pos))


# ──────────────────────────────────────────────────────────────────────
# Enriched player data & live GW
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/game/leagues/<lid>/squad/enriched", methods=["GET"])
@_game_error
def game_get_enriched_squad(lid):
    """Squad with enriched player data: form, fixtures, xG, status."""
    member_uid = request.args.get("uid", g.user["uid"])
    squad_doc = (db.collection("leagues").document(lid)
                 .collection("squads").document(member_uid).get())
    if not squad_doc.exists:
        return jsonify({"players": []})

    players = squad_doc.to_dict().get("players", [])
    pids = [p["playerId"] for p in players]
    enriched = fpl.enrich_players_batch(pids)

    for p in players:
        extra = enriched.get(p["playerId"], {})
        p.update({
            "totalPoints": extra.get("totalPoints", 0),
            "form": extra.get("form", 0),
            "status": extra.get("status", "a"),
            "news": extra.get("news", ""),
            "next3": extra.get("next3", []),
        })
        if "xG" in extra:
            p["xG"] = extra["xG"]
            p["xA"] = extra["xA"]
            p["ict"] = extra["ict"]

    return jsonify({"players": players})


@app.route("/api/game/leagues/<lid>/live/<int:gw>", methods=["GET"])
@_game_error
def game_live_gw(lid, gw):
    """Live GW points for all managers in a league."""
    league_ref = db.collection("leagues").document(lid)
    members = list(league_ref.collection("members").get())

    live_data = fpl.get_gw_live(gw)
    live_map = {}
    for el in live_data:
        live_map[el.get("id")] = el.get("stats", {})

    results = {}
    for member in members:
        uid = member.id
        lineup_doc = league_ref.collection("lineups").document(f"{uid}_{gw}").get()
        if not lineup_doc.exists:
            results[uid] = {"total": 0, "players": [], "bench": []}
            continue

        lineup = lineup_doc.to_dict()
        starting = lineup.get("starting", [])
        bench = lineup.get("bench", [])

        player_map = fpl.get_player_map()
        total = 0
        player_scores = []
        for pid in starting:
            stats = live_map.get(pid, {})
            pts = stats.get("total_points", 0)
            total += pts
            p = player_map.get(pid, {})
            player_scores.append({
                "playerId": pid,
                "webName": p.get("web_name", "?"),
                "points": pts,
                "minutes": stats.get("minutes", 0),
            })

        bench_scores = []
        for pid in bench:
            stats = live_map.get(pid, {})
            p = player_map.get(pid, {})
            bench_scores.append({
                "playerId": pid,
                "webName": p.get("web_name", "?"),
                "points": stats.get("total_points", 0),
                "minutes": stats.get("minutes", 0),
            })

        m = member.to_dict()
        results[uid] = {
            "total": total,
            "teamName": m.get("teamName", "?"),
            "displayName": m.get("displayName", "?"),
            "players": player_scores,
            "bench": bench_scores,
        }

    schedule_doc = league_ref.collection("schedule").document(str(gw)).get()
    schedule = schedule_doc.to_dict() if schedule_doc.exists else {}

    return jsonify({"gw": gw, "results": results, "schedule": schedule})


@app.route("/api/game/leagues/<lid>/dashboard", methods=["GET"])
@_game_error
def game_dashboard(lid):
    """Dashboard data: league info, current GW, deadline, standings snapshot, upcoming match."""
    league_ref = db.collection("leagues").document(lid)
    league_doc = league_ref.get()
    if not league_doc.exists:
        raise ValueError("League not found")

    league = league_doc.to_dict()
    uid = g.user["uid"]
    current_gw = fpl.get_current_gw()
    next_gw = fpl.get_next_gw()

    deadlines = league.get("deadlines", {})
    next_deadline = deadlines.get(str(next_gw), {})

    schedule_doc = league_ref.collection("schedule").document(str(next_gw)).get()
    my_match = None
    if schedule_doc.exists:
        for m in schedule_doc.to_dict().get("matches", []):
            if m["home"] == uid or m["away"] == uid:
                opp_uid = m["away"] if m["home"] == uid else m["home"]
                opp_doc = league_ref.collection("members").document(opp_uid).get()
                opp = opp_doc.to_dict() if opp_doc.exists else {}
                my_match = {
                    "gw": next_gw,
                    "opponent": opp.get("teamName", "?"),
                    "opponentUid": opp_uid,
                    "isHome": m["home"] == uid,
                }
                break

    standings = scoring_engine.get_standings(lid)

    return jsonify({
        "league": {
            "id": lid,
            "name": league.get("name"),
            "format": league.get("format"),
            "imported": league.get("imported", False),
            "currentGw": current_gw,
            "nextGw": next_gw,
        },
        "deadline": next_deadline,
        "myMatch": my_match,
        "standings": standings,
    })


@app.route("/api/game/players/<int:pid>", methods=["GET"])
@_game_error
def game_player_detail(pid):
    """Detailed player view with stats, fixtures, injury info."""
    return jsonify(fpl.enrich_player(pid))


@app.route("/api/game/leagues/<lid>/schedule/full", methods=["GET"])
@_game_error
def game_full_schedule(lid):
    """All GW schedules for a league."""
    league_ref = db.collection("leagues").document(lid)
    docs = list(league_ref.collection("schedule").get())
    members = {m.id: m.to_dict() for m in league_ref.collection("members").get()}

    schedule = []
    for doc in sorted(docs, key=lambda d: int(d.id) if d.id.isdigit() else 0):
        data = doc.to_dict()
        gw = data.get("gw", int(doc.id) if doc.id.isdigit() else 0)
        matches = []
        for m in data.get("matches", []):
            h = members.get(m["home"], {})
            a = members.get(m["away"], {})
            matches.append({
                **m,
                "homeTeam": h.get("teamName", "?"),
                "awayTeam": a.get("teamName", "?"),
            })
        schedule.append({"gw": gw, "matches": matches})

    return jsonify({"schedule": schedule})


# ──────────────────────────────────────────────────────────────────────
# Health / meta
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "current_gw": fpl.get_current_gw()})


@app.route("/api/clear-cache", methods=["POST"])
def clear_cache():
    fpl.clear_cache()
    clear_lineup_cache()
    return jsonify({"status": "cleared"})


# ──────────────────────────────────────────────────────────────────────
# Bootstrap data
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/players")
def get_players():
    players = fpl.get_players()
    team_map = fpl.get_team_map()
    result = []
    for p in players:
        t = team_map.get(p["team"], {})
        result.append({
            "id": p["id"],
            "web_name": p["web_name"],
            "first_name": p.get("first_name", ""),
            "second_name": p.get("second_name", ""),
            "team_id": p["team"],
            "team_short": t.get("short_name", "?"),
            "position": p["element_type"],
            "total_points": p.get("total_points", 0),
            "form": p.get("form", "0"),
            "points_per_game": p.get("points_per_game", "0"),
            "minutes": p.get("minutes", 0),
            "goals_scored": p.get("goals_scored", 0),
            "assists": p.get("assists", 0),
            "clean_sheets": p.get("clean_sheets", 0),
            "status": p.get("status", "a"),
            "news": p.get("news", ""),
            "draft_rank": p.get("draft_rank"),
        })
    return jsonify(_clean(result))


@app.route("/api/teams")
def get_teams():
    return jsonify(fpl.get_teams())


@app.route("/api/current-gw")
def get_current_gw():
    return jsonify({"current_gw": fpl.get_current_gw(), "next_gw": fpl.get_next_gw()})


# ──────────────────────────────────────────────────────────────────────
# Fixtures & FDR
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/fixtures/grid")
def get_fixture_grid():
    """Full fixture grid: team_id -> gw -> {opponent, fdr, is_home, display}."""
    grid = fpl.get_fixture_grid()
    teams = fpl.get_teams()
    current_gw = fpl.get_current_gw()

    rows = []
    for t in sorted(teams, key=lambda x: x["name"]):
        tid = t["id"]
        team_gws = grid.get(tid, {})
        fixtures = {}
        for gw in range(1, 39):
            f = team_gws.get(gw)
            if f:
                fixtures[str(gw)] = {
                    "display": f["display"],
                    "fdr": f["fdr"],
                    "is_home": f["is_home"],
                    "opponent_id": f["opponent_id"],
                }
        rows.append({
            "team_id": tid,
            "team_name": t["name"],
            "team_short": t["short_name"],
            "fixtures": fixtures,
        })

    return jsonify({"teams": rows, "current_gw": current_gw})


@app.route("/api/fixtures/raw")
def get_fixtures_raw():
    return jsonify(_clean(fpl.get_fixtures()))


# ──────────────────────────────────────────────────────────────────────
# League
# ──────────────────────────────────────────────────────────────────────

def _get_league_id() -> int:
    lid = request.args.get("league_id", type=int)
    if not lid:
        lid = int(os.environ.get("FPL_LEAGUE_ID", "201560"))
    return lid


@app.route("/api/league")
def get_league():
    lid = _get_league_id()
    info = fpl.get_league_info(lid)
    entries = fpl.get_league_entries(lid)
    return jsonify({"league": info, "entries": entries})


@app.route("/api/league/entries")
def get_league_entries():
    return jsonify(fpl.get_league_entries(_get_league_id()))


@app.route("/api/league/standings")
def get_standings():
    return jsonify(fpl.get_standings(_get_league_id()))


@app.route("/api/league/matches")
def get_matches():
    matches = fpl.get_league_matches(_get_league_id())
    return jsonify(_clean(matches))


@app.route("/api/league/transactions")
def get_transactions():
    return jsonify(fpl.get_transactions(_get_league_id()))


@app.route("/api/league/trades")
def get_trades():
    return jsonify(fpl.get_trades(_get_league_id()))


# ──────────────────────────────────────────────────────────────────────
# Squads
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/squad/<int:entry_id>")
def get_squad(entry_id):
    gw = request.args.get("gw", type=int) or fpl.get_current_gw()
    lid = _get_league_id()
    squad = fpl.get_enriched_squad(lid, entry_id, gw)
    return jsonify(_clean(squad))


@app.route("/api/squads")
def get_all_squads():
    lid = _get_league_id()
    gw = request.args.get("gw", type=int) or fpl.get_current_gw()
    entries = fpl.get_league_entries(lid)
    result = {}
    for e in entries:
        eid = e["entry_id"]
        result[str(eid)] = {
            "entry_name": e["entry_name"],
            "squad": fpl.get_enriched_squad(lid, eid, gw),
        }
    return jsonify(_clean(result))


@app.route("/api/element-status")
def get_element_status():
    return jsonify(fpl.get_element_status(_get_league_id()))


# ──────────────────────────────────────────────────────────────────────
# Free agents
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/free-agents")
def get_free_agents():
    lid = _get_league_id()
    pos = request.args.get("position", type=int)
    sort = request.args.get("sort", "total_points")
    limit = request.args.get("limit", 100, type=int)
    agents = fpl.get_free_agents(lid, position=pos, sort_by=sort, limit=limit)
    return jsonify(_clean(agents))


# ──────────────────────────────────────────────────────────────────────
# Analysis
# ──────────────────────────────────────────────────────────────────────

def _get_analyzer() -> SquadAnalyzer:
    return SquadAnalyzer(fpl, _get_league_id(), lineup_predictor=lineup_pred)


def _parse_star_players() -> list:
    raw = request.args.get("star_players", "") or request.json.get("star_players", "") if request.is_json else request.args.get("star_players", "")
    if not raw:
        return []
    if isinstance(raw, list):
        return [int(x) for x in raw]
    return [int(x.strip()) for x in str(raw).split(",") if x.strip()]


@app.route("/api/analysis/<int:entry_id>")
def analyze_squad(entry_id):
    gw_start = request.args.get("gw_start", type=int) or fpl.get_current_gw()
    gw_end = request.args.get("gw_end", type=int) or min(gw_start + 5, 38)
    stars = _parse_star_players()

    excluded_raw = request.args.get("excluded", "")
    excluded = [int(x.strip()) for x in excluded_raw.split(",") if x.strip()] if excluded_raw else []

    analyzer = _get_analyzer()
    result = analyzer.analyze_squad(entry_id, gw_start, gw_end, stars, excluded)
    return jsonify(_clean(result))


@app.route("/api/analysis/all-managers")
def analyze_all():
    gw_start = request.args.get("gw_start", type=int) or fpl.get_current_gw()
    gw_end = request.args.get("gw_end", type=int) or min(gw_start + 5, 38)
    stars = _parse_star_players()
    analyzer = _get_analyzer()
    result = analyzer.analyze_all_managers(gw_start, gw_end, stars)
    return jsonify(_clean(result))


@app.route("/api/analysis/recommendations", methods=["GET", "POST"])
def get_recommendations():
    if request.is_json:
        data = request.json
        entry_id = data.get("entry_id", 0)
        gw_start = data.get("gw_start") or fpl.get_current_gw()
        gw_end = data.get("gw_end") or min(gw_start + 5, 38)
        stars = data.get("star_players", [])
        free_only = data.get("free_agents_only", True)
    else:
        entry_id = request.args.get("entry_id", 0, type=int)
        gw_start = request.args.get("gw_start", type=int) or fpl.get_current_gw()
        gw_end = request.args.get("gw_end", type=int) or min(gw_start + 5, 38)
        stars = _parse_star_players()
        free_only = request.args.get("free_agents_only", "true").lower() == "true"

    analyzer = _get_analyzer()
    result = analyzer.get_recommendations(entry_id, gw_start, gw_end, stars, free_only)
    return jsonify(_clean(result))


@app.route("/api/analysis/replacements", methods=["POST"])
def get_replacements():
    data = request.json or {}
    entry_id = data.get("entry_id", 0)
    player_id = data.get("player_id", 0)
    gw_start = data.get("gw_start") or fpl.get_current_gw()
    gw_end = data.get("gw_end") or min(gw_start + 5, 38)
    stars = data.get("star_players", [])
    include_owned = data.get("include_owned", False)

    analyzer = _get_analyzer()
    result = analyzer.get_replacement_candidates(
        entry_id, player_id, gw_start, gw_end, stars, include_owned
    )
    return jsonify(_clean(result))


@app.route("/api/analysis/simulate", methods=["POST"])
def simulate_replacements():
    """Run analysis with replacement overrides (what-if)."""
    data = request.json or {}
    entry_id = data.get("entry_id", 0)
    gw_start = data.get("gw_start") or fpl.get_current_gw()
    gw_end = data.get("gw_end") or min(gw_start + 5, 38)
    stars = data.get("star_players", [])
    replacements = data.get("replacements", {})
    replacements_int = {int(k): int(v) for k, v in replacements.items()}

    analyzer = _get_analyzer()
    result = analyzer.analyze_squad(
        entry_id, gw_start, gw_end, stars,
        replacement_overrides=replacements_int,
    )
    return jsonify(_clean(result))


# ──────────────────────────────────────────────────────────────────────
# Player Points Breakdown (per-GW detailed)
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/predict/breakdown/<int:entry_id>")
def predict_breakdown(entry_id):
    """Per-player points breakdown for a specific GW."""
    lid = _get_league_id()
    gw = request.args.get("gw", type=int) or fpl.get_next_gw()
    result = predictor.predict_squad_breakdown(lid, entry_id, gw)
    return jsonify(_clean(result))


# ──────────────────────────────────────────────────────────────────────
# Player Predictions (xPts)
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/predict/player/<int:player_id>")
def predict_player(player_id):
    """Full prediction for a single player across GW range."""
    gw_start = request.args.get("gw_start", type=int) or fpl.get_next_gw()
    gw_end = request.args.get("gw_end", type=int) or min(gw_start + 5, 38)
    result = predictor.predict_player(player_id, gw_start, gw_end)
    return jsonify(_clean(result))


@app.route("/api/predict/squad/<int:entry_id>")
def predict_squad(entry_id):
    """Predict all players in a squad with suggested lineups."""
    lid = _get_league_id()
    gw_start = request.args.get("gw_start", type=int) or fpl.get_next_gw()
    gw_end = request.args.get("gw_end", type=int) or min(gw_start + 5, 38)
    result = predictor.predict_squad(lid, entry_id, gw_start, gw_end)
    return jsonify(_clean(result))


@app.route("/api/predict/h2h")
def predict_h2h():
    """Compare two FPL squads for a GW."""
    lid = _get_league_id()
    e1 = request.args.get("entry1", type=int)
    e2 = request.args.get("entry2", type=int)
    gw = request.args.get("gw", type=int) or fpl.get_next_gw()
    if not e1 or not e2:
        return jsonify({"error": "entry1 and entry2 required"}), 400
    result = predictor.predict_h2h(lid, e1, e2, gw)
    return jsonify(_clean(result))


# ──────────────────────────────────────────────────────────────────────
# Team Form & PL Standings
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/pl/standings")
def pl_standings():
    return jsonify(_clean(fpl.get_pl_standings()))


@app.route("/api/pl/team-stats")
def pl_team_stats():
    return jsonify(_clean(fpl.get_team_season_stats()))


@app.route("/api/pl/form")
def pl_form():
    """Full team form report: standings, batch cross, recent form."""
    result = team_form_analyzer.get_full_form_report()
    return jsonify(_clean(result))


@app.route("/api/pl/match-predict")
def pl_match_predict():
    """Predict xG for a specific match."""
    home = request.args.get("home", type=int)
    away = request.args.get("away", type=int)
    if not home or not away:
        return jsonify({"error": "home and away team IDs required"}), 400
    result = team_form_analyzer.predict_match_goals(home, away)
    return jsonify(_clean(result))


# ──────────────────────────────────────────────────────────────────────
# N-D-K Scoring
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/ndk/<int:entry_id>")
def ndk_score(entry_id):
    lid = _get_league_id()
    gw_start = request.args.get("gw_start", type=int) or fpl.get_next_gw()
    gw_end = request.args.get("gw_end", type=int) or min(gw_start + 5, 38)
    result = ndk_sim.score_team(lid, entry_id, gw_start, gw_end)
    return jsonify(_clean(result))


@app.route("/api/ndk/all")
def ndk_all():
    lid = _get_league_id()
    gw_start = request.args.get("gw_start", type=int) or fpl.get_next_gw()
    gw_end = request.args.get("gw_end", type=int) or min(gw_start + 5, 38)
    result = ndk_sim.score_all_teams(lid, gw_start, gw_end)
    return jsonify(_clean(result))


@app.route("/api/ndk/compare")
def ndk_compare():
    lid = _get_league_id()
    e1 = request.args.get("entry1", type=int)
    e2 = request.args.get("entry2", type=int)
    gw_start = request.args.get("gw_start", type=int) or fpl.get_next_gw()
    gw_end = request.args.get("gw_end", type=int) or min(gw_start + 5, 38)
    if not e1 or not e2:
        return jsonify({"error": "entry1 and entry2 required"}), 400
    result = ndk_sim.compare_teams(lid, e1, e2, gw_start, gw_end)
    return jsonify(_clean(result))


# ──────────────────────────────────────────────────────────────────────
# Predicted Lineups
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/lineups/team/<int:team_id>")
def predicted_lineup(team_id):
    return jsonify(_clean(lineup_pred.predict_team_lineup(team_id)))


@app.route("/api/lineups/all")
def predicted_lineups_all():
    return jsonify(_clean(lineup_pred.predict_all_teams()))


@app.route("/api/lineups/availability")
def player_availability():
    lid = _get_league_id()
    result = lineup_pred.get_player_availability(lid)
    return jsonify(_clean(result))


@app.route("/api/lineups/gw/<int:gw>")
def predicted_lineups_gw(gw):
    """All fixtures for a GW with predicted lineups."""
    return jsonify(_clean(lineup_pred.predict_gw_fixtures(gw)))


@app.route("/api/lineups/gw/<int:gw>/source/<source>")
def predicted_lineups_gw_source(gw, source):
    """
    All fixtures for a GW with lineups from a specific source.
    Sources: rotowire, fplteam, ffs, combined
    """
    return jsonify(_clean(lineup_pred.get_source_gw_fixtures(gw, source)))


@app.route("/api/lineups/team/<int:team_id>/source/<source>")
def predicted_lineup_source(team_id, source):
    """Predicted lineup for a team from a specific source."""
    return jsonify(_clean(lineup_pred.get_source_lineup(team_id, source)))


@app.route("/api/lineups/validate/<int:gw>")
def validate_lineups(gw):
    """Validate lineup prediction accuracy against actual data."""
    return jsonify(_clean(lineup_pred.validate_accuracy(gw)))


# ──────────────────────────────────────────────────────────────────────
# Lineup Steals - source-backed surprise starters with good fixtures
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/lineup-steals")
def lineup_steals():
    """
    Players predicted to start by multiple sources who historically
    DON'T start regularly. These are high-upside "steal" picks,
    especially when they face easy opponents.
    """
    lid = _get_league_id()
    gw = request.args.get("gw", type=int) or fpl.get_next_gw()
    limit = request.args.get("limit", 20, type=int)

    current_gw = fpl.get_current_gw()
    ownership = fpl.get_ownership_map(lid)
    team_map = fpl.get_team_map()
    grid = fpl.get_fixture_grid()

    all_lineups = lineup_pred.predict_all_teams()
    steals = []

    for team_result in all_lineups:
        team_id = team_result.get("team_id")
        if not team_id:
            continue

        fixture = grid.get(team_id, {}).get(gw)
        fdr = fixture["fdr"] if fixture else None

        for p in team_result.get("predicted_xi", []):
            n_src = len(p.get("external_sources", []))
            if n_src < 2:
                continue

            pid = p["player_id"]
            history = fpl.get_player_gw_history(pid)
            prob_data = compute_next_game_probability(
                pid, team_id, history, current_gw,
                lineup_predictor=lineup_pred,
                source_tracker=source_tracker,
            )
            ts = trend_summary(history, current_gw)

            hist_rate = prob_data["hist_rate"]
            if hist_rate > 0.50:
                continue

            team_short = team_map.get(team_id, {}).get("short_name", "?")
            is_owned = ownership.get(pid) is not None

            steals.append({
                "player_id": pid,
                "web_name": p["web_name"],
                "team": team_short,
                "team_id": team_id,
                "position": p.get("pos_name", "?"),
                "total_points": p.get("total_points", 0),
                "start_probability": prob_data["probability"],
                "hist_start_rate": round(hist_rate, 3),
                "trend": ts["trend"],
                "trend_factor": ts["trend_factor"],
                "consecutive_starts": ts["consecutive_starts"],
                "n_sources": n_src,
                "sources": prob_data["sources"],
                "fdr": fdr,
                "fixture": fixture["display"] if fixture else "?",
                "is_easy_fixture": fdr is not None and fdr <= 2.5,
                "is_owned": is_owned,
            })

    steals.sort(key=lambda x: (
        -x["is_easy_fixture"],
        -x["start_probability"],
        -x["trend_factor"],
        -x["total_points"],
    ))
    return jsonify(_clean(steals[:limit]))


@app.route("/api/player/<int:player_id>/start-probability")
def player_start_probability(player_id):
    """Full start probability breakdown for a single player."""
    p = fpl.get_player_map().get(player_id)
    if not p:
        return jsonify({"error": "Player not found"}), 404

    current_gw = fpl.get_current_gw()
    history = fpl.get_player_gw_history(player_id)
    team_id = p.get("team", 0)

    prob_data = compute_next_game_probability(
        player_id, team_id, history, current_gw,
        lineup_predictor=lineup_pred,
        source_tracker=source_tracker,
    )
    ts = trend_summary(history, current_gw)

    return jsonify(_clean({
        "player_id": player_id,
        "web_name": p.get("web_name", "?"),
        "team_id": team_id,
        **prob_data,
        **ts,
    }))


# ──────────────────────────────────────────────────────────────────────
# Source Credibility Tracking
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/sources/credibility")
def get_source_credibility():
    """Current credibility scores for each prediction source."""
    return jsonify(_clean(source_tracker.get_results_summary()))


@app.route("/api/sources/snapshot", methods=["POST"])
def snapshot_source_predictions():
    """
    Snapshot current predictions for the upcoming GW.
    Call this BEFORE the GW starts to record what sources predicted.
    """
    gw = request.args.get("gw", type=int) or fpl.get_next_gw()
    if source_tracker.has_snapshot(gw):
        return jsonify({"status": "already_snapshotted", "gw": gw})

    teams = fpl.get_teams()
    team_ids = [t["id"] for t in teams]
    clear_lineup_cache()
    preds = extract_source_predictions(lineup_pred, team_ids)
    source_tracker.snapshot_predictions(gw, preds)

    counts = {s: len(teams_dict) for s, teams_dict in preds.items()}
    return jsonify({"status": "snapshotted", "gw": gw, "teams_per_source": counts})


@app.route("/api/sources/evaluate", methods=["POST"])
def evaluate_source_accuracy():
    """
    Evaluate prediction accuracy for a completed GW.
    Compares snapshotted predictions against actual lineups from FPL API.
    """
    from .engine.lineup_predictor import _name_match

    gw = request.args.get("gw", type=int)
    if not gw:
        return jsonify({"error": "gw parameter required"}), 400

    actual = build_actual_lineups(fpl, gw)
    if not actual:
        return jsonify({"error": f"No actual lineup data for GW{gw}"}), 400

    source_tracker.evaluate_gw(gw, actual, name_match_fn=_name_match)
    return jsonify(_clean(source_tracker.get_results_summary()))


# ──────────────────────────────────────────────────────────────────────
# Player detail with history
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/player/<int:player_id>/history")
def player_history(player_id):
    """Per-GW history for a player."""
    history = fpl.get_player_gw_history(player_id)
    return jsonify(_clean(history))


@app.route("/api/player/<int:player_id>/upcoming")
def player_upcoming(player_id):
    """Upcoming fixtures with difficulty."""
    upcoming = fpl.get_player_upcoming(player_id)
    return jsonify(_clean(upcoming))


# ──────────────────────────────────────────────────────────────────────
# FA suggestions for specific fixtures
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/suggest/fixture")
def suggest_fa_fixture():
    """Best FAs for a specific GW fixture."""
    lid = _get_league_id()
    entry_id = request.args.get("entry_id", type=int)
    pos = request.args.get("position", type=int) or 0
    gw = request.args.get("gw", type=int) or fpl.get_next_gw()
    result = predictor.suggest_fa_for_fixture(lid, entry_id, pos, gw)
    return jsonify(_clean(result))


@app.route("/api/suggest/range")
def suggest_fa_range():
    """Best FAs over a GW range."""
    lid = _get_league_id()
    entry_id = request.args.get("entry_id", type=int)
    pos = request.args.get("position", type=int) or 0
    gw_start = request.args.get("gw_start", type=int) or fpl.get_next_gw()
    gw_end = request.args.get("gw_end", type=int) or min(gw_start + 2, 38)
    result = predictor.suggest_fa_multi_gw(lid, entry_id, pos, gw_start, gw_end)
    return jsonify(_clean(result))


@app.route("/api/suggest/weak")
def suggest_fa_weak():
    """Best FAs for GWs where team is weakest (hardest fixtures)."""
    lid = _get_league_id()
    entry_id = request.args.get("entry_id", type=int)
    gw_start = request.args.get("gw_start", type=int) or fpl.get_next_gw()
    gw_end = request.args.get("gw_end", type=int) or min(gw_start + 5, 38)
    analyzer = _get_analyzer()
    analysis = analyzer.analyze_squad(entry_id, gw_start, gw_end)
    weak_positions = analysis.get("position_failures", {})
    suggestions = {}
    POS_MAP = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
    for pos_name, fail_count in weak_positions.items():
        if fail_count > 0:
            pos_id = POS_MAP.get(pos_name, 3)
            fa_list = predictor.suggest_fa_for_fixture(lid, entry_id, pos_id, gw_start)
            suggestions[pos_name] = fa_list[:5]
    return jsonify(_clean({"weak_positions": weak_positions, "suggestions": suggestions}))


# ──────────────────────────────────────────────────────────────────────
# H2H auto-predictions for all GW matchups
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/predict/gw-matchups")
def predict_gw_matchups():
    """Auto-predict all league H2H matchups for a GW."""
    lid = _get_league_id()
    gw = request.args.get("gw", type=int) or fpl.get_next_gw()
    matches = fpl.get_league_matches(lid)
    gw_matches = [m for m in matches if m.get("event") == gw]
    entries = {e["id"]: e for e in fpl.get_league_entries(lid)}

    results = []
    for m in gw_matches:
        le1 = m.get("league_entry_1")
        le2 = m.get("league_entry_2")
        e1 = entries.get(le1, {})
        e2 = entries.get(le2, {})
        eid1 = e1.get("entry_id")
        eid2 = e2.get("entry_id")
        if not eid1 or not eid2:
            continue
        try:
            h2h = predictor.predict_h2h(lid, eid1, eid2, gw)
            results.append({
                "entry_1_name": e1.get("entry_name", "?"),
                "entry_2_name": e2.get("entry_name", "?"),
                "entry_1_xpts": h2h["entry_1"]["xpts"],
                "entry_2_xpts": h2h["entry_2"]["xpts"],
                "advantage": h2h["advantage"],
                "finished": m.get("finished", False),
                "actual_1": m.get("league_entry_1_points"),
                "actual_2": m.get("league_entry_2_points"),
            })
        except Exception:
            results.append({
                "entry_1_name": e1.get("entry_name", "?"),
                "entry_2_name": e2.get("entry_name", "?"),
                "error": True,
            })
    return jsonify(_clean(results))


# ──────────────────────────────────────────────────────────────────────
# Team color scheme
# ──────────────────────────────────────────────────────────────────────

TEAM_COLORS = {
    "ARS": {"primary": "#EF0107", "secondary": "#FFFFFF", "accent": "#063672"},
    "AVL": {"primary": "#670E36", "secondary": "#95BFE5", "accent": "#FFFFFF"},
    "BOU": {"primary": "#DA291C", "secondary": "#000000", "accent": "#FFFFFF"},
    "BRE": {"primary": "#E30613", "secondary": "#FFFFFF", "accent": "#FFB81C"},
    "BHA": {"primary": "#0057B8", "secondary": "#FFFFFF", "accent": "#FFCD00"},
    "BUR": {"primary": "#6C1D45", "secondary": "#99D6EA", "accent": "#FFFFFF"},
    "CHE": {"primary": "#034694", "secondary": "#FFFFFF", "accent": "#DBA111"},
    "CRY": {"primary": "#1B458F", "secondary": "#C4122E", "accent": "#FFFFFF"},
    "EVE": {"primary": "#003399", "secondary": "#FFFFFF", "accent": "#FFFFFF"},
    "FUL": {"primary": "#000000", "secondary": "#FFFFFF", "accent": "#CC0000"},
    "LEE": {"primary": "#FFFFFF", "secondary": "#1D428A", "accent": "#FFCD00"},
    "LIV": {"primary": "#C8102E", "secondary": "#FFFFFF", "accent": "#00B2A9"},
    "MCI": {"primary": "#6CABDD", "secondary": "#FFFFFF", "accent": "#1C2C5B"},
    "MUN": {"primary": "#DA291C", "secondary": "#FFFFFF", "accent": "#FBE122"},
    "NEW": {"primary": "#241F20", "secondary": "#FFFFFF", "accent": "#41B6E6"},
    "NFO": {"primary": "#DD0000", "secondary": "#FFFFFF", "accent": "#FFFFFF"},
    "SUN": {"primary": "#EB172B", "secondary": "#FFFFFF", "accent": "#211E1F"},
    "TOT": {"primary": "#132257", "secondary": "#FFFFFF", "accent": "#FFFFFF"},
    "WHU": {"primary": "#7A263A", "secondary": "#1BB1E7", "accent": "#F3D459"},
    "WOL": {"primary": "#FDB913", "secondary": "#231F20", "accent": "#FFFFFF"},
}

NAME_ALIASES = {
    792: {"web_name": "Taty", "full_name": "Valentín Castellanos"},
}


@app.route("/api/team-colors")
def team_colors():
    return jsonify(TEAM_COLORS)


# ──────────────────────────────────────────────────────────────────────
# Background Live Scoring Polling Scheduler (Sprint 3)
# ──────────────────────────────────────────────────────────────────────

_scheduler_started = False

def init_background_scheduler(interval_seconds=300):
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    
    import threading
    import time
    
    def poll_loop():
        # wait 10 seconds before first poll to let app stabilize
        time.sleep(10)
        while True:
            try:
                from .api_wc import background_poll_and_process_fixtures
                print("[Background Poller] Polling live fixtures...")
                res = background_poll_and_process_fixtures()
                proc = res.get("processed", [])
                errs = res.get("errors", [])
                if proc:
                    print(f"[Background Poller] Processed FT fixtures: {proc}")
                if errs:
                    print(f"[Background Poller] Errors encountered during polling: {errs}")
            except Exception as e:
                print(f"[Background Poller] Unexpected exception in loop: {e}")
            time.sleep(interval_seconds)

    thread = threading.Thread(target=poll_loop, name="WCLivePollingThread", daemon=True)
    thread.start()
    print("[Background Poller] Started background polling daemon thread.")


# Import-time auto-start is OPT-IN only. On serverless (Cloud Functions),
# `functions/main.py` imports this module on every cold start; a daemon
# thread there can't run reliably (instances freeze between requests) and
# every cold start would spawn another. Live scoring in that deployment is
# driven by Cloud Scheduler -> POST /admin/process-live-fixtures instead.
# Long-running hosts (gunicorn/Cloud Run, single instance) can opt in by
# setting WC_ENABLE_POLLER=true. `run_server` (local dev) starts it directly.
if os.environ.get("FPL_TESTING") != "true" and os.environ.get("WC_ENABLE_POLLER") == "true":
    init_background_scheduler(300)


# ──────────────────────────────────────────────────────────────────────
# Server runner
# ──────────────────────────────────────────────────────────────────────

def run_server(host="0.0.0.0", port=5000, debug=False):
    # Explicitly ensure background scheduler starts
    init_background_scheduler(300)
    app.run(host=host, port=port, debug=debug)
