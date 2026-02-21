"""
FPL Draft Analyzer - Flask REST API.

All data is fetched live from the FPL API with in-memory caching.
No local database required.
"""

import os
import math
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from .data.fpl_api import FPLClient
from .engine.analysis import SquadAnalyzer, POSITION_NAMES
from .engine.predictor import PlayerPredictor
from .engine.team_form import TeamFormAnalyzer
from .engine.ndk import NDKSimulator
from .engine.lineup_predictor import LineupPredictor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

app = Flask(__name__)
CORS(app)

fpl = FPLClient()
predictor = PlayerPredictor(fpl)
team_form_analyzer = TeamFormAnalyzer(fpl)
ndk_sim = NDKSimulator(fpl)
lineup_pred = LineupPredictor(fpl)


def _clean(obj):
    """Recursively replace NaN/inf floats with None for JSON safety."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
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


# ──────────────────────────────────────────────────────────────────────
# Static files
# ──────────────────────────────────────────────────────────────────────

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
# Health / meta
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "current_gw": fpl.get_current_gw()})


@app.route("/api/clear-cache", methods=["POST"])
def clear_cache():
    fpl.clear_cache()
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
    return SquadAnalyzer(fpl, _get_league_id())


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


@app.route("/api/lineups/validate/<int:gw>")
def validate_lineups(gw):
    """Validate lineup prediction accuracy against actual data."""
    return jsonify(_clean(lineup_pred.validate_accuracy(gw)))


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
# Server runner
# ──────────────────────────────────────────────────────────────────────

def run_server(host="0.0.0.0", port=5000, debug=False):
    app.run(host=host, port=port, debug=debug)
