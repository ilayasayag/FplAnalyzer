"""
Flask REST API for FPL Score Predictor

Provides HTTP endpoints for predictions, fixtures, and analysis.
Serves static frontend files.
"""

import os
import math
from typing import Optional, Dict, List, Any, Tuple
from flask import Flask, jsonify, request, abort, send_from_directory
from flask_cors import CORS

from .config import DATA_DIR, DEFAULT_BATCHES, BATCH_NAMES, Position
from .data.loader import DataLoader
from .data.standings import StandingsFetcher
from .engine.batch_analyzer import BatchAnalyzer, BatchStatistics
from .engine.player_stats import PlayerStatsEngine
from .engine.points_calculator import create_prediction_engine
from .export import PredictionExporter

# Get the directory where this file is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, static_folder=STATIC_DIR)
CORS(app)  # Enable CORS for all routes

# Global predictor instance
predictor = None


# ==============================================================================
# Fixture Data (hardcoded from HTML for GW20-38)
# ==============================================================================

TEAMS = [
    'Arsenal', 'Villa', 'Bournemouth', 'Brentford', 'Brighton',
    'Chelsea', 'Palace', 'Everton', 'Fulham', 'City',
    'Liverpool', 'United', 'Newcastle', 'Forest', 'Spurs',
    'West Ham', 'Sunderland', 'Burnley', 'Wolves', 'Leeds'
]

# Official FDR scores for GW20-38
OFFICIAL_FDR = {
    'City': {20:3, 21:3, 22:3, 23:2, 24:3, 25:4, 26:2, 27:3, 28:3, 29:2, 30:2, 31:3, 32:3, 33:4, 34:2, 35:3, 36:3, 37:3, 38:3},
    'Arsenal': {20:4, 21:4, 22:3, 23:3, 24:3, 25:2, 26:3, 27:3, 28:3, 29:3, 30:2, 31:2, 32:3, 33:4, 34:3, 35:2, 36:3, 37:4, 38:3},
    'Villa': {20:2, 21:3, 22:2, 23:4, 24:3, 25:4, 26:3, 27:2, 28:2, 29:3, 30:3, 31:2, 32:3, 33:2, 34:3, 35:2, 36:2, 37:2, 38:3},
    'Bournemouth': {20:4, 21:3, 22:3, 23:4, 24:2, 25:3, 26:3, 27:2, 28:2, 29:3, 30:2, 31:3, 32:3, 33:2, 34:3, 35:3, 36:2, 37:4, 38:4},
    'Brentford': {20:3, 21:2, 22:3, 23:2, 24:3, 25:4, 26:4, 27:3, 28:2, 29:4, 30:2, 31:3, 32:3, 33:4, 34:2, 35:3, 36:3, 37:4, 38:3},
    'Brighton': {20:2, 21:4, 22:3, 23:3, 24:2, 25:3, 26:3, 27:3, 28:2, 29:4, 30:3, 31:4, 32:2, 33:3, 34:3, 35:4, 36:2, 37:3, 38:4},
    'Burnley': {20:3, 21:3, 22:4, 23:3, 24:3, 25:2, 26:3, 27:3, 28:3, 29:3, 30:3, 31:3, 32:3, 33:3, 34:4, 35:3, 36:3, 37:5, 38:2},
    'Chelsea': {20:4, 21:3, 22:3, 23:3, 24:2, 25:2, 26:2, 27:2, 28:5, 29:3, 30:3, 31:3, 32:4, 33:3, 34:3, 35:2, 36:4, 37:3, 38:3},
    'Palace': {20:4, 21:3, 22:3, 23:3, 24:3, 25:3, 26:2, 27:2, 28:3, 29:3, 30:2, 31:4, 32:3, 33:2, 34:4, 35:4, 36:2, 37:3, 38:4},
    'Everton': {20:3, 21:2, 22:3, 23:2, 24:3, 25:3, 26:3, 27:3, 28:4, 29:2, 30:5, 31:3, 32:3, 33:4, 34:2, 35:4, 36:3, 37:2, 38:3},
    'Fulham': {20:4, 21:3, 22:3, 23:3, 24:3, 25:2, 26:3, 27:2, 28:4, 29:3, 30:3, 31:3, 32:3, 33:4, 34:2, 35:4, 36:3, 37:2, 38:3},
    'Liverpool': {20:3, 21:5, 22:2, 23:4, 24:3, 25:4, 26:3, 27:3, 28:2, 29:2, 30:3, 31:3, 32:4, 33:3, 34:3, 35:3, 36:3, 37:3, 38:3},
    'United': {20:3, 21:2, 22:4, 23:5, 24:2, 25:3, 26:2, 27:3, 28:3, 29:4, 30:3, 31:4, 32:2, 33:3, 34:3, 35:4, 36:3, 37:2, 38:3},
    'Newcastle': {20:3, 21:2, 22:2, 23:3, 24:4, 25:3, 26:3, 27:4, 28:2, 29:3, 30:3, 31:2, 32:3, 33:2, 34:3, 35:3, 36:3, 37:3, 38:3},
    'Forest': {20:3, 21:2, 22:2, 23:3, 24:3, 25:3, 26:3, 27:4, 28:2, 29:3, 30:3, 31:2, 32:3, 33:3, 34:5, 35:3, 36:3, 37:2, 38:3},
    'Spurs': {20:2, 21:4, 22:2, 23:2, 24:4, 25:3, 26:3, 27:4, 28:3, 29:4, 30:4, 31:2, 32:3, 33:3, 34:2, 35:3, 36:2, 37:3, 38:2},
    'Sunderland': {20:3, 21:3, 22:3, 23:2, 24:2, 25:5, 26:4, 27:2, 28:4, 29:3, 30:3, 31:4, 32:3, 33:3, 34:2, 35:2, 36:3, 37:3, 38:3},
    'West Ham': {20:2, 21:2, 22:3, 23:2, 24:3, 25:2, 26:3, 27:3, 28:4, 29:3, 30:4, 31:3, 32:2, 33:3, 34:2, 35:3, 36:4, 37:4, 38:2},
    'Wolves': {20:2, 21:3, 22:3, 23:4, 24:3, 25:3, 26:3, 27:3, 28:3, 29:4, 30:3, 31:4, 32:2, 33:3, 34:3, 35:2, 36:3, 37:2, 38:2},
    'Leeds': {20:3, 21:2, 22:3, 23:3, 24:3, 25:2, 26:4, 27:3, 28:3, 29:2, 30:3, 31:2, 32:4, 33:3, 34:3, 35:5, 36:3, 37:2, 38:3},
}

# Fixtures: Opponent for each team in each gameweek
FIXTURES = {
    'City': {20:'CHE(H)', 21:'BHA(H)', 22:'MUN(A)', 23:'WOL(H)', 24:'TOT(A)', 25:'LIV(A)', 26:'FUL(H)', 27:'NEW(H)', 28:'LEE(A)', 29:'NFO(H)', 30:'WHU(A)', 31:'CRY(H)', 32:'CHE(A)', 33:'ARS(H)', 34:'BUR(A)', 35:'EVE(A)', 36:'BRE(H)', 37:'BOU(A)', 38:'AVL(H)'},
    'Arsenal': {20:'BOU(A)', 21:'LIV(H)', 22:'NFO(A)', 23:'MUN(H)', 24:'LEE(A)', 25:'SUN(H)', 26:'BRE(A)', 27:'TOT(A)', 28:'CHE(H)', 29:'BHA(A)', 30:'EVE(H)', 31:'WOL(A)', 32:'BOU(H)', 33:'MCI(A)', 34:'NEW(H)', 35:'FUL(H)', 36:'WHU(A)', 37:'BUR(H)', 38:'CRY(A)'},
    'Villa': {20:'NFO(H)', 21:'CRY(A)', 22:'EVE(H)', 23:'NEW(A)', 24:'BRE(H)', 25:'BOU(A)', 26:'BHA(H)', 27:'LEE(H)', 28:'WOL(A)', 29:'CHE(H)', 30:'MUN(A)', 31:'WHU(H)', 32:'NFO(A)', 33:'MCI(A)', 34:'NEW(H)', 35:'FUL(H)', 36:'WHU(A)', 37:'BUR(H)', 38:'CRY(A)'},
    'Bournemouth': {20:'ARS(H)', 21:'TOT(H)', 22:'BHA(A)', 23:'LIV(H)', 24:'WOL(A)', 25:'AVL(H)', 26:'EVE(A)', 27:'WHU(A)', 28:'SUN(H)', 29:'BRE(H)', 30:'BUR(A)', 31:'MUN(H)', 32:'ARS(A)', 33:'SUN(H)', 34:'FUL(A)', 35:'TOT(H)', 36:'BUR(A)', 37:'LIV(H)', 38:'MCI(A)'},
    'Brentford': {20:'EVE(A)', 21:'SUN(H)', 22:'CHE(A)', 23:'NFO(H)', 24:'AVL(A)', 25:'NEW(A)', 26:'ARS(H)', 27:'BHA(H)', 28:'BUR(A)', 29:'BOU(A)', 30:'WOL(H)', 31:'LEE(A)', 32:'EVE(H)', 33:'FUL(H)', 34:'LEE(H)', 35:'CRY(H)', 36:'FUL(A)', 37:'MCI(H)', 38:'NFO(A)'},
    'Brighton': {20:'BUR(H)', 21:'MCI(A)', 22:'BOU(H)', 23:'FUL(A)', 24:'EVE(H)', 25:'CRY(H)', 26:'AVL(A)', 27:'BRE(A)', 28:'NFO(H)', 29:'ARS(H)', 30:'SUN(A)', 31:'LIV(H)', 32:'BUR(A)', 33:'TOT(A)', 34:'CHE(H)', 35:'NFO(H)', 36:'WOL(H)', 37:'LEE(A)', 38:'MUN(H)'},
    'Burnley': {20:'BHA(A)', 21:'MUN(H)', 22:'LIV(A)', 23:'TOT(H)', 24:'SUN(A)', 25:'WHU(H)', 26:'CRY(A)', 27:'CHE(A)', 28:'BRE(H)', 29:'EVE(A)', 30:'BOU(H)', 31:'FUL(A)', 32:'BHA(H)', 33:'NFO(A)', 34:'MCI(H)', 35:'LEE(A)', 36:'AVL(H)', 37:'ARS(A)', 38:'WOL(H)'},
    'Chelsea': {20:'MCI(A)', 21:'FUL(A)', 22:'BRE(H)', 23:'CRY(A)', 24:'WHU(H)', 25:'WOL(A)', 26:'LEE(H)', 27:'BUR(H)', 28:'ARS(A)', 29:'AVL(A)', 30:'NEW(H)', 31:'EVE(A)', 32:'MCI(H)', 33:'MUN(H)', 34:'BHA(A)', 35:'NFO(H)', 36:'LIV(A)', 37:'TOT(H)', 38:'SUN(A)'},
    'Palace': {20:'NEW(A)', 21:'AVL(H)', 22:'SUN(A)', 23:'CHE(H)', 24:'NFO(A)', 25:'BHA(A)', 26:'BUR(H)', 27:'WOL(H)', 28:'MUN(A)', 29:'TOT(A)', 30:'LEE(H)', 31:'MCI(A)', 32:'NEW(H)', 33:'WHU(H)', 34:'LIV(A)', 35:'BOU(A)', 36:'EVE(H)', 37:'BRE(A)', 38:'ARS(H)'},
    'Everton': {20:'BRE(H)', 21:'WOL(H)', 22:'AVL(A)', 23:'LEE(H)', 24:'BHA(A)', 25:'FUL(A)', 26:'BOU(H)', 27:'MUN(H)', 28:'NFO(H)', 29:'BUR(H)', 30:'ARS(A)', 31:'CHE(H)', 32:'BRE(A)', 33:'LIV(H)', 34:'WHU(A)', 35:'MCI(H)', 36:'CRY(A)', 37:'SUN(H)', 38:'TOT(H)'},
    'Fulham': {20:'LIV(H)', 21:'CHE(H)', 22:'LEE(A)', 23:'BHA(H)', 24:'MUN(A)', 25:'EVE(H)', 26:'BOU(H)', 27:'SUN(A)', 28:'NEW(A)', 29:'BUR(H)', 30:'ARS(A)', 31:'CHE(H)', 32:'BRE(A)', 33:'LIV(H)', 34:'WHU(A)', 35:'MCI(H)', 36:'CRY(H)', 37:'SUN(H)', 38:'TOT(A)'},
    'Liverpool': {20:'FUL(A)', 21:'ARS(A)', 22:'BUR(H)', 23:'BOU(A)', 24:'NEW(H)', 25:'MCI(H)', 26:'SUN(A)', 27:'NFO(A)', 28:'WHU(H)', 29:'WOL(A)', 30:'TOT(H)', 31:'BHA(A)', 32:'FUL(H)', 33:'EVE(A)', 34:'CRY(H)', 35:'MUN(A)', 36:'CHE(H)', 37:'AVL(A)', 38:'WHU(A)'},
    'United': {20:'LEE(A)', 21:'BUR(A)', 22:'MCI(H)', 23:'ARS(A)', 24:'FUL(H)', 25:'TOT(H)', 26:'WHU(A)', 27:'EVE(A)', 28:'CRY(H)', 29:'NEW(A)', 30:'AVL(H)', 31:'BOU(A)', 32:'LEE(H)', 33:'CHE(A)', 34:'BRE(H)', 35:'LIV(H)', 36:'SUN(A)', 37:'NFO(H)', 38:'BHA(A)'},
    'Newcastle': {20:'CRY(H)', 21:'LEE(H)', 22:'WOL(H)', 23:'AVL(H)', 24:'LIV(A)', 25:'BRE(H)', 26:'TOT(H)', 27:'MCI(A)', 28:'FUL(H)', 29:'MUN(H)', 30:'CHE(A)', 31:'SUN(H)', 32:'CRY(A)', 33:'BOU(A)', 34:'ARS(A)', 35:'BHA(H)', 36:'TOT(H)', 37:'WHU(H)', 38:'LEE(A)'},
    'Forest': {20:'AVL(A)', 21:'WHU(A)', 22:'ARS(H)', 23:'BRE(A)', 24:'CRY(H)', 25:'LIV(H)', 26:'WOL(H)', 27:'LIV(H)', 28:'EVE(H)', 29:'MCI(A)', 30:'CHE(A)', 31:'SUN(H)', 32:'CRY(A)', 33:'BOU(H)', 34:'ARS(H)', 35:'BHA(A)', 36:'NFO(A)', 37:'WHU(H)', 38:'FUL(A)'},
    'Spurs': {20:'SUN(H)', 21:'BOU(A)', 22:'WHU(H)', 23:'BUR(A)', 24:'MCI(H)', 25:'MUN(A)', 26:'NFO(A)', 27:'LIV(H)', 28:'BHA(A)', 29:'MCI(A)', 30:'LIV(A)', 31:'NFO(A)', 32:'AVL(H)', 33:'BUR(H)', 34:'SUN(A)', 35:'CHE(A)', 36:'NEW(H)', 37:'MUN(A)', 38:'BOU(H)'},
    'Sunderland': {20:'TOT(A)', 21:'BRE(A)', 22:'CRY(H)', 23:'WHU(A)', 24:'BUR(H)', 25:'ARS(A)', 26:'LIV(H)', 27:'FUL(H)', 28:'BOU(A)', 29:'LEE(A)', 30:'BHA(H)', 31:'NEW(A)', 32:'TOT(H)', 33:'AVL(A)', 34:'NFO(H)', 35:'WOL(A)', 36:'MUN(H)', 37:'EVE(A)', 38:'CHE(H)'},
    'West Ham': {20:'WOL(A)', 21:'NFO(H)', 22:'TOT(A)', 23:'SUN(H)', 24:'CHE(A)', 25:'BUR(A)', 26:'MUN(H)', 27:'BOU(H)', 28:'LIV(A)', 29:'FUL(A)', 30:'MCI(H)', 31:'AVL(A)', 32:'WOL(H)', 33:'CRY(A)', 34:'EVE(H)', 35:'BRE(A)', 36:'AVL(H)', 37:'NEW(A)', 38:'LEE(H)'},
    'Wolves': {20:'WHU(H)', 21:'EVE(A)', 22:'NEW(A)', 23:'MCI(A)', 24:'BOU(H)', 25:'CHE(H)', 26:'NFO(A)', 27:'CRY(A)', 28:'AVL(H)', 29:'LIV(H)', 30:'BRE(A)', 31:'ARS(H)', 32:'WHU(A)', 33:'LIV(H)', 34:'TOT(H)', 35:'SUN(H)', 36:'BHA(A)', 37:'FUL(A)', 38:'BUR(A)'},
    'Leeds': {20:'MUN(H)', 21:'NEW(A)', 22:'FUL(H)', 23:'EVE(A)', 24:'ARS(H)', 25:'NFO(H)', 26:'CHE(A)', 27:'SUN(A)', 28:'TOT(H)', 29:'WHU(H)', 30:'NFO(A)', 31:'BUR(H)', 32:'LIV(A)', 33:'BRE(A)', 34:'AVL(H)', 35:'ARS(A)', 36:'BOU(H)', 37:'WOL(A)', 38:'NEW(H)'},
}

TEAM_ABBREV = {
    'Arsenal': 'ARS', 'Villa': 'AVL', 'Bournemouth': 'BOU', 'Brentford': 'BRE', 'Brighton': 'BHA',
    'Chelsea': 'CHE', 'Palace': 'CRY', 'Everton': 'EVE', 'Fulham': 'FUL', 'City': 'MCI',
    'Liverpool': 'LIV', 'United': 'MUN', 'Newcastle': 'NEW', 'Forest': 'NFO', 'Spurs': 'TOT',
    'West Ham': 'WHU', 'Sunderland': 'SUN', 'Burnley': 'BUR', 'Wolves': 'WOL', 'Leeds': 'LEE'
}

GW_START = 20
GW_END = 38
EASY_THRESHOLD = 2.5


class APIPredictor:
    """Wrapper class for API predictions"""
    
    def __init__(self):
        self.loader = DataLoader()
        self.standings_fetcher = StandingsFetcher()
        self.batch_analyzer = BatchAnalyzer()
        self.player_stats = PlayerStatsEngine()
        self.points_calc = None
        self.exporter = PredictionExporter()
        self._initialized = False
        self._data_file = None
    
    def initialize(self, data_file: str) -> bool:
        """Initialize the predictor with data from file"""
        if not self.loader.load_from_file(data_file):
            return False
        return self._complete_initialization()
    
    def initialize_from_dict(self, data: Dict[str, Any]) -> bool:
        """Initialize the predictor with data from dictionary"""
        if not self.loader.load_from_dict(data):
            return False
        return self._complete_initialization()
    
    def _complete_initialization(self) -> bool:
        """Complete initialization after data is loaded"""
        self.standings_fetcher.update_teams_with_positions(self.loader.teams)
        self.batch_analyzer.initialize(self.loader.teams, self.standings_fetcher)
        self.batch_analyzer.assign_opponent_batches_to_players(self.loader.players)
        self.player_stats.analyze_all_players(self.loader.players)
        self.points_calc = create_prediction_engine(
            self.player_stats, self.batch_analyzer
        )
        self._initialized = True
        return True
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized


def get_predictor() -> APIPredictor:
    """Get or create the global predictor instance"""
    global predictor
    if predictor is None:
        predictor = APIPredictor()
    return predictor


# ==============================================================================
# API Routes - Core
# ==============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    pred = get_predictor()
    return jsonify({
        'status': 'healthy',
        'initialized': pred.is_initialized,
        'data_loaded': pred.loader.get_statistics() if pred.is_initialized else None
    })


@app.route('/api/import', methods=['POST'])
def import_data():
    """
    Import FPL data directly from bookmarklet JSON.
    
    Request body: The complete JSON object from bookmarklet
    """
    pred = get_predictor()
    
    json_data = request.get_json()
    if not json_data:
        abort(400, description="Request body required")
    
    if pred.initialize_from_dict(json_data):
        return jsonify({
            'success': True,
            'message': 'Data imported successfully',
            'statistics': pred.loader.get_statistics()
        })
    else:
        abort(500, description="Failed to import data")


@app.route('/api/load', methods=['POST'])
def load_data():
    """
    Load data from a JSON file or direct data.
    
    Request body:
    {
        "file_path": "/path/to/data.json"
    }
    
    Or provide JSON data directly:
    {
        "data": { ... FPL data ... }
    }
    """
    pred = get_predictor()
    
    json_data = request.get_json()
    if not json_data:
        abort(400, description="Request body required")
    
    if 'file_path' in json_data:
        file_path = json_data['file_path']
        if not os.path.exists(file_path):
            abort(404, description=f"File not found: {file_path}")
        
        if pred.initialize(file_path):
            return jsonify({
                'success': True,
                'message': 'Data loaded successfully',
                'statistics': pred.loader.get_statistics()
            })
        else:
            abort(500, description="Failed to load data")
    
    elif 'data' in json_data:
        if pred.initialize_from_dict(json_data['data']):
            return jsonify({
                'success': True,
                'message': 'Data loaded successfully',
                'statistics': pred.loader.get_statistics()
            })
        else:
            abort(500, description="Failed to parse data")
    
    abort(400, description="Either 'file_path' or 'data' required")


# ==============================================================================
# API Routes - Fixtures
# ==============================================================================

@app.route('/api/fixtures/grid', methods=['GET'])
def get_fixture_grid():
    """
    Get fixture difficulty grid for all teams.
    
    Query params:
    - gw_start: Start gameweek (default 20)
    - gw_end: End gameweek (default 38)
    
    Returns fixture difficulty rating matrix with opponent info.
    """
    gw_start = request.args.get('gw_start', GW_START, type=int)
    gw_end = request.args.get('gw_end', GW_END, type=int)
    
    grid = []
    for team in TEAMS:
        fdr_data = OFFICIAL_FDR.get(team, {})
        fixtures_data = FIXTURES.get(team, {})
        
        gameweeks = []
        easy_count = 0
        total_fdr = 0
        
        for gw in range(gw_start, gw_end + 1):
            fdr = fdr_data.get(gw, 3)
            opponent = fixtures_data.get(gw, '???')
            is_easy = fdr <= EASY_THRESHOLD
            
            if is_easy:
                easy_count += 1
            total_fdr += fdr
            
            gameweeks.append({
                'gw': gw,
                'fdr': fdr,
                'opponent': opponent,
                'is_home': '(H)' in opponent,
                'is_easy': is_easy
            })
        
        num_gw = gw_end - gw_start + 1
        grid.append({
            'team': team,
            'abbrev': TEAM_ABBREV.get(team, team[:3].upper()),
            'gameweeks': gameweeks,
            'easy_count': easy_count,
            'avg_fdr': round(total_fdr / num_gw, 2) if num_gw > 0 else 0
        })
    
    # Sort by easy count (descending)
    grid.sort(key=lambda x: x['easy_count'], reverse=True)
    
    return jsonify({
        'gw_start': gw_start,
        'gw_end': gw_end,
        'teams': grid,
        'total_gameweeks': gw_end - gw_start + 1
    })


@app.route('/api/fixtures/overlap', methods=['GET'])
def get_fixture_overlap():
    """
    Get rotation/overlap analysis between teams.
    
    Query params:
    - team1: First team name
    - team2: Second team name (optional, returns all pairs if not provided)
    
    Returns overlap statistics for fixture rotation planning.
    """
    team1 = request.args.get('team1')
    team2 = request.args.get('team2')
    
    def get_easy_gameweeks(team: str) -> set:
        """Get set of easy gameweeks for a team"""
        fdr_data = OFFICIAL_FDR.get(team, {})
        return {gw for gw in range(GW_START, GW_END + 1) if fdr_data.get(gw, 3) <= EASY_THRESHOLD}
    
    def calculate_overlap(t1: str, t2: str) -> Dict[str, Any]:
        """Calculate overlap statistics between two teams"""
        easy1 = get_easy_gameweeks(t1)
        easy2 = get_easy_gameweeks(t2)
        
        total_gw = GW_END - GW_START + 1
        duplications = len(easy1 & easy2)  # Both easy
        empty = total_gw - len(easy1 | easy2)  # Neither easy
        coverage = len(easy1 | easy2)  # At least one easy
        
        return {
            'team1': t1,
            'team2': t2,
            'duplications': duplications,
            'empty_weeks': empty,
            'coverage': coverage,
            'coverage_pct': round(coverage / total_gw * 100, 1),
            'easy1_gws': sorted(easy1),
            'easy2_gws': sorted(easy2),
            'overlap_gws': sorted(easy1 & easy2),
            'unique1_gws': sorted(easy1 - easy2),
            'unique2_gws': sorted(easy2 - easy1)
        }
    
    if team1 and team2:
        # Single pair analysis
        if team1 not in TEAMS or team2 not in TEAMS:
            abort(404, description="Team not found")
        
        return jsonify(calculate_overlap(team1, team2))
    
    elif team1:
        # All pairs for one team
        if team1 not in TEAMS:
            abort(404, description="Team not found")
        
        overlaps = []
        for t2 in TEAMS:
            if t2 != team1:
                overlaps.append(calculate_overlap(team1, t2))
        
        # Sort by coverage (best rotation partners first)
        overlaps.sort(key=lambda x: (-x['coverage'], x['duplications']))
        
        return jsonify({
            'team': team1,
            'best_partners': overlaps[:5],
            'all_pairs': overlaps
        })
    
    else:
        # All possible pairs (top combinations)
        all_overlaps = []
        for i, t1 in enumerate(TEAMS):
            for t2 in TEAMS[i+1:]:
                all_overlaps.append(calculate_overlap(t1, t2))
        
        # Sort by coverage
        all_overlaps.sort(key=lambda x: (-x['coverage'], x['duplications']))
        
        return jsonify({
            'best_pairs': all_overlaps[:20],
            'total_pairs': len(all_overlaps)
        })


# ==============================================================================
# API Routes - Squad Analysis
# ==============================================================================

@app.route('/api/squad/analysis/<int:entry_id>', methods=['GET'])
def get_squad_analysis(entry_id: int):
    """
    Get detailed squad coverage analysis.
    
    Returns fixture coverage by gameweek, position breakdown,
    and improvement suggestions.
    """
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    players = pred.loader.get_squad_players(entry_id)
    if not players:
        abort(404, description=f"Squad not found for entry {entry_id}")
    
    entry_name = pred.loader.get_entry_name(entry_id)
    
    # Group players by position
    by_position = {'GK': [], 'DEF': [], 'MID': [], 'FWD': []}
    team_counts = {}
    
    for player in players:
        pos = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}.get(player.position, 'UNK')
        team_name = player.team_name
        
        by_position[pos].append({
            'id': player.id,
            'name': player.web_name,
            'team': team_name,
            'position': pos
        })
        
        team_counts[team_name] = team_counts.get(team_name, 0) + 1
    
    # Calculate coverage by gameweek
    coverage_by_gw = {}
    for gw in range(GW_START, GW_END + 1):
        easy_count = 0
        easy_players = []
        
        for player in players:
            team_name = player.team_name
            fdr_data = OFFICIAL_FDR.get(team_name, {})
            fdr = fdr_data.get(gw, 3)
            
            if fdr <= EASY_THRESHOLD:
                easy_count += 1
                easy_players.append(player.web_name)
        
        coverage_by_gw[gw] = {
            'easy_count': easy_count,
            'easy_players': easy_players,
            'has_11': easy_count >= 11
        }
    
    # Find weak gameweeks
    weak_gws = [gw for gw, data in coverage_by_gw.items() if data['easy_count'] < 11]
    
    # Calculate suggestions
    suggestions = []
    
    if weak_gws:
        suggestions.append({
            'type': 'weak_coverage',
            'priority': 'high',
            'message': f"{len(weak_gws)} gameweeks with <11 easy fixtures",
            'gameweeks': weak_gws[:5]
        })
    
    # Check team concentration
    overloaded = [(t, c) for t, c in team_counts.items() if c > 3]
    if overloaded:
        suggestions.append({
            'type': 'team_concentration',
            'priority': 'medium',
            'message': f"Heavy concentration: {', '.join(f'{t} ({c})' for t, c in overloaded)}",
            'teams': overloaded
        })
    
    return jsonify({
        'entry_id': entry_id,
        'entry_name': entry_name,
        'squad': {
            'by_position': by_position,
            'team_counts': team_counts
        },
        'coverage': {
            'by_gameweek': coverage_by_gw,
            'weak_gameweeks': weak_gws,
            'total_weak': len(weak_gws)
        },
        'suggestions': suggestions
    })


# ==============================================================================
# API Routes - Head to Head
# ==============================================================================

@app.route('/api/h2h/<int:entry1>/<int:entry2>', methods=['GET'])
def get_h2h_prediction(entry1: int, entry2: int):
    """
    Get head-to-head prediction between two squads.
    
    Query params:
    - gameweek: Gameweek number (optional, defaults to current)
    """
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    gameweek = request.args.get('gameweek', pred.loader.current_gameweek, type=int)
    
    # Get both squads
    players1 = pred.loader.get_squad_players(entry1)
    players2 = pred.loader.get_squad_players(entry2)
    
    if not players1:
        abort(404, description=f"Squad not found for entry {entry1}")
    if not players2:
        abort(404, description=f"Squad not found for entry {entry2}")
    
    name1 = pred.loader.get_entry_name(entry1)
    name2 = pred.loader.get_entry_name(entry2)
    
    # Get predictions for both squads
    def get_squad_predictions(players, entry_id, entry_name):
        opponents = {}
        for player in players:
            if player.team_id not in opponents:
                for team in pred.loader.teams.values():
                    if team.id != player.team_id:
                        opponents[player.team_id] = (team, True)
                        break
        
        return pred.points_calc.calculate_squad_predictions(
            entry_id, entry_name, players, opponents, gameweek
        )
    
    squad1_pred = get_squad_predictions(players1, entry1, name1)
    squad2_pred = get_squad_predictions(players2, entry2, name2)
    
    # Calculate win probability using normal distribution approximation
    pts1 = squad1_pred.total_expected_points
    pts2 = squad2_pred.total_expected_points
    
    # Estimate standard deviation based on squad uncertainty
    # Higher for squads with rotation-risk players
    def estimate_std(squad_pred):
        base_std = 12.0
        low_conf = sum(1 for p in squad_pred.optimal_11 if p.confidence < 0.4)
        med_conf = sum(1 for p in squad_pred.optimal_11 if 0.4 <= p.confidence < 0.7)
        return base_std + low_conf * 2.0 + med_conf * 1.0
    
    std1 = estimate_std(squad1_pred)
    std2 = estimate_std(squad2_pred)
    combined_std = math.sqrt(std1**2 + std2**2)
    
    # Normal CDF approximation
    def normal_cdf(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    
    diff = pts1 - pts2
    if combined_std > 0:
        win_prob1 = normal_cdf(diff / combined_std)
    else:
        win_prob1 = 0.5 if diff == 0 else (1.0 if diff > 0 else 0.0)
    
    win_prob2 = 1 - win_prob1
    
    return jsonify({
        'gameweek': gameweek,
        'team1': {
            'entry_id': entry1,
            'name': name1,
            'expected_points': round(pts1, 1),
            'formation': squad1_pred.optimal_formation,
            'win_probability': round(win_prob1 * 100, 1),
            'optimal_11': [p.to_dict() for p in squad1_pred.optimal_11]
        },
        'team2': {
            'entry_id': entry2,
            'name': name2,
            'expected_points': round(pts2, 1),
            'formation': squad2_pred.optimal_formation,
            'win_probability': round(win_prob2 * 100, 1),
            'optimal_11': [p.to_dict() for p in squad2_pred.optimal_11]
        },
        'differential': round(abs(diff), 1),
        'favorite': name1 if win_prob1 > win_prob2 else name2
    })


# ==============================================================================
# API Routes - Trades
# ==============================================================================

@app.route('/api/trades/suggestions/<int:entry_id>', methods=['GET'])
def get_trade_suggestions(entry_id: int):
    """
    Get trade suggestions for a squad.
    
    Analyzes current squad and suggests improvements based on:
    - Fixture coverage
    - Player form
    - Position balance
    """
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    players = pred.loader.get_squad_players(entry_id)
    if not players:
        abort(404, description=f"Squad not found for entry {entry_id}")
    
    entry_name = pred.loader.get_entry_name(entry_id)
    
    # Get current squad team coverage
    squad_teams = set(p.team_name for p in players)
    
    # Find teams with good upcoming fixtures not in squad
    suggestions = []
    
    # Calculate average FDR for remaining GWs
    current_gw = pred.loader.current_gameweek
    remaining_gws = list(range(max(current_gw, GW_START), GW_END + 1))
    
    team_avg_fdr = {}
    for team in TEAMS:
        fdr_data = OFFICIAL_FDR.get(team, {})
        fdr_sum = sum(fdr_data.get(gw, 3) for gw in remaining_gws)
        team_avg_fdr[team] = fdr_sum / len(remaining_gws) if remaining_gws else 3.0
    
    # Teams with good fixtures not heavily represented
    squad_team_counts = {}
    for p in players:
        squad_team_counts[p.team_name] = squad_team_counts.get(p.team_name, 0) + 1
    
    target_teams = [
        t for t in TEAMS 
        if team_avg_fdr.get(t, 3) < 3.0 and squad_team_counts.get(t, 0) < 2
    ]
    target_teams.sort(key=lambda t: team_avg_fdr.get(t, 3))
    
    # Find best available players from target teams
    for team in target_teams[:3]:
        team_players = pred.loader.get_players_by_team(
            next((t.id for t in pred.loader.teams.values() if t.name == team), 0)
        )
        
        # Get top players by PPG
        top_players = sorted(
            [p for p in team_players if p.games_played >= 3],
            key=lambda p: p.points_per_game,
            reverse=True
        )[:3]
        
        if top_players:
            suggestions.append({
                'type': 'target_team',
                'team': team,
                'reason': f"Good fixtures (avg FDR: {team_avg_fdr[team]:.1f})",
                'players': [
                    {
                        'id': p.id,
                        'name': p.web_name,
                        'position': p.position_name,
                        'ppg': round(p.points_per_game, 1)
                    }
                    for p in top_players
                ]
            })
    
    # Identify underperformers in current squad
    underperformers = []
    for player in players:
        if player.games_played >= 5 and player.points_per_game < 3.0:
            underperformers.append({
                'id': player.id,
                'name': player.web_name,
                'team': player.team_name,
                'position': player.position_name,
                'ppg': round(player.points_per_game, 1),
                'reason': 'Low PPG despite regular playing time'
            })
    
    return jsonify({
        'entry_id': entry_id,
        'entry_name': entry_name,
        'current_gw': current_gw,
        'target_teams': suggestions,
        'underperformers': underperformers[:5],
        'squad_teams': list(squad_teams)
    })


# ==============================================================================
# API Routes - Predictions
# ==============================================================================

@app.route('/api/predict/player/<int:player_id>', methods=['GET'])
def predict_player(player_id: int):
    """
    Get prediction for a specific player.
    
    Query params:
    - opponent_id: FPL team ID of opponent (required)
    - gameweek: Gameweek number (optional, defaults to current)
    - is_home: Whether playing at home (optional, defaults to true)
    """
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    player = pred.loader.get_player(player_id)
    if not player:
        abort(404, description=f"Player {player_id} not found")
    
    opponent_id = request.args.get('opponent_id', type=int)
    if not opponent_id:
        abort(400, description="opponent_id query parameter required")
    
    opponent = pred.loader.get_team(opponent_id)
    if not opponent:
        abort(404, description=f"Team {opponent_id} not found")
    
    gameweek = request.args.get('gameweek', pred.loader.current_gameweek, type=int)
    is_home = request.args.get('is_home', 'true').lower() == 'true'
    
    prediction = pred.points_calc.calculate_expected_points(
        player, opponent, gameweek, is_home
    )
    
    return jsonify(prediction.to_dict())


@app.route('/api/predict/squad/<int:entry_id>', methods=['GET'])
def predict_squad(entry_id: int):
    """
    Get predictions for a squad.
    
    Query params:
    - gameweek: Gameweek number (optional, defaults to current)
    """
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    players = pred.loader.get_squad_players(entry_id)
    if not players:
        abort(404, description=f"Squad not found for entry {entry_id}")
    
    entry_name = pred.loader.get_entry_name(entry_id)
    gameweek = request.args.get('gameweek', pred.loader.current_gameweek, type=int)
    
    # Get opponents for each player's team
    opponents = {}
    for player in players:
        if player.team_id not in opponents:
            for team in pred.loader.teams.values():
                if team.id != player.team_id:
                    opponents[player.team_id] = (team, True)
                    break
    
    squad_pred = pred.points_calc.calculate_squad_predictions(
        entry_id, entry_name, players, opponents, gameweek
    )
    
    return jsonify(squad_pred.to_dict())


# ==============================================================================
# API Routes - Players & Teams
# ==============================================================================

@app.route('/api/players', methods=['GET'])
def list_players():
    """
    List all players.
    
    Query params:
    - search: Search string for player name
    - position: Filter by position (1=GK, 2=DEF, 3=MID, 4=FWD)
    - team_id: Filter by team
    - limit: Maximum results (default 50)
    """
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    search = request.args.get('search', '')
    position = request.args.get('position', type=int)
    team_id = request.args.get('team_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    
    if search:
        players = pred.loader.search_players(search, limit)
    else:
        players = list(pred.loader.players.values())
    
    if position:
        players = [p for p in players if p.position == position]
    if team_id:
        players = [p for p in players if p.team_id == team_id]
    
    players = players[:limit]
    
    return jsonify({
        'count': len(players),
        'players': [p.to_dict() for p in players]
    })


@app.route('/api/players/<int:player_id>', methods=['GET'])
def get_player(player_id: int):
    """Get detailed information about a player"""
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    player = pred.loader.get_player(player_id)
    if not player:
        abort(404, description=f"Player {player_id} not found")
    
    analysis = pred.player_stats.get_player_analysis(player_id)
    summary = pred.player_stats.get_player_summary(player_id) if analysis else {}
    
    return jsonify({
        'player': player.to_dict(),
        'analysis': summary,
    })


@app.route('/api/teams', methods=['GET'])
def list_teams():
    """List all teams with their current standings"""
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    teams = list(pred.loader.teams.values())
    teams.sort(key=lambda t: t.position)
    
    return jsonify({
        'count': len(teams),
        'teams': [t.to_dict() for t in teams]
    })


@app.route('/api/teams/<int:team_id>', methods=['GET'])
def get_team(team_id: int):
    """Get detailed information about a team"""
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    team = pred.loader.get_team(team_id)
    if not team:
        abort(404, description=f"Team {team_id} not found")
    
    batch_performance = pred.batch_analyzer.get_team_batch_performance(team_id, team)
    
    return jsonify({
        'team': team.to_dict(),
        'batch_performance': batch_performance,
    })


@app.route('/api/batches', methods=['GET'])
def list_batches():
    """Get batch summary"""
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    summary = pred.batch_analyzer.get_batch_summary()
    
    return jsonify({
        'batches': summary
    })


@app.route('/api/league', methods=['GET'])
def get_league_info():
    """Get league information"""
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    entries = pred.loader.league_entries
    
    return jsonify({
        'current_gameweek': pred.loader.current_gameweek,
        'entries': entries,
        'entry_ids': pred.loader.get_all_entry_ids(),
    })


@app.route('/api/export/predictions', methods=['POST'])
def export_predictions():
    """
    Export predictions for all squads.
    
    Request body:
    {
        "gameweek": 22  // optional
    }
    """
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/import first")
    
    json_data = request.get_json() or {}
    gameweek = json_data.get('gameweek', pred.loader.current_gameweek)
    
    squads = {}
    for entry_id in pred.loader.get_all_entry_ids():
        players = pred.loader.get_squad_players(entry_id)
        if players:
            entry_name = pred.loader.get_entry_name(entry_id)
            
            opponents = {}
            for player in players:
                if player.team_id not in opponents:
                    for team in pred.loader.teams.values():
                        if team.id != player.team_id:
                            opponents[player.team_id] = (team, True)
                            break
            
            squad_pred = pred.points_calc.calculate_squad_predictions(
                entry_id, entry_name, players, opponents, gameweek
            )
            squads[entry_id] = squad_pred
    
    filepath = pred.exporter.export_all_predictions(squads, gameweek)
    
    return jsonify({
        'success': True,
        'file_path': filepath,
        'squads_exported': len(squads),
    })


# ==============================================================================
# Error Handlers
# ==============================================================================

@app.errorhandler(400)
def bad_request(error):
    return jsonify({
        'error': 'Bad Request',
        'message': str(error.description)
    }), 400


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Not Found',
        'message': str(error.description)
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'Internal Server Error',
        'message': str(error.description)
    }), 500


# ==============================================================================
# Auto-Import Data Files
# ==============================================================================

# Project root (one level above fpl_predictor)
PROJECT_ROOT = os.path.dirname(BASE_DIR)

import glob
import re
from datetime import datetime


@app.route('/api/data-files', methods=['GET'])
def list_data_files():
    """
    List all available fpl_league_data_*.json files in the project root.
    Returns files sorted by date (newest first).
    """
    pattern = os.path.join(PROJECT_ROOT, 'fpl_league_data_*.json')
    files = glob.glob(pattern)
    
    # Extract date from filename and sort
    file_info = []
    date_pattern = re.compile(r'fpl_league_data_(\d{4}-\d{2}-\d{2})\.json$')
    
    for filepath in files:
        filename = os.path.basename(filepath)
        match = date_pattern.search(filename)
        if match:
            date_str = match.group(1)
            try:
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                file_size = os.path.getsize(filepath)
                file_info.append({
                    'filename': filename,
                    'date': date_str,
                    'size': file_size,
                    'size_mb': round(file_size / (1024 * 1024), 2),
                    'path': f'/{filename}'
                })
            except ValueError:
                pass
    
    # Sort by date descending (newest first)
    file_info.sort(key=lambda x: x['date'], reverse=True)
    
    return jsonify({
        'files': file_info,
        'count': len(file_info),
        'newest': file_info[0] if file_info else None
    })


@app.route('/api/auto-load', methods=['POST'])
def auto_load_newest():
    """
    Auto-load the newest fpl_league_data_*.json file.
    Returns the loaded data for client-side processing.
    """
    import json
    
    pattern = os.path.join(PROJECT_ROOT, 'fpl_league_data_*.json')
    files = glob.glob(pattern)
    
    if not files:
        return jsonify({
            'success': False,
            'error': 'No data files found',
            'message': 'No fpl_league_data_*.json files found in project root'
        }), 404
    
    # Find newest file by date in filename
    date_pattern = re.compile(r'fpl_league_data_(\d{4}-\d{2}-\d{2})\.json$')
    newest_file = None
    newest_date = None
    
    for filepath in files:
        filename = os.path.basename(filepath)
        match = date_pattern.search(filename)
        if match:
            date_str = match.group(1)
            try:
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                if newest_date is None or file_date > newest_date:
                    newest_date = file_date
                    newest_file = filepath
            except ValueError:
                pass
    
    if not newest_file:
        return jsonify({
            'success': False,
            'error': 'No valid data files',
            'message': 'No files matching fpl_league_data_YYYY-MM-DD.json pattern found'
        }), 404
    
    try:
        with open(newest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        filename = os.path.basename(newest_file)
        
        # Also initialize the predictor with this data
        pred = get_predictor()
        initialized = pred.initialize_from_dict(data)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'date': newest_date.strftime('%Y-%m-%d'),
            'data': data,
            'predictor_initialized': initialized
        })
        
    except json.JSONDecodeError as e:
        return jsonify({
            'success': False,
            'error': 'Invalid JSON',
            'message': f'Failed to parse {os.path.basename(newest_file)}: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Load failed',
            'message': str(e)
        }), 500


# ==============================================================================
# Static File Serving (MUST be after API routes)
# ==============================================================================

@app.route('/')
def serve_index():
    """
    Serve the main frontend page.
    
    Priorities:
    1. Original fpl_fixture_analyzer.html in project root (full featured)
    2. Modern modular index.html in static folder (in development)
    """
    # First check for the original analyzer in project root
    original_html = os.path.join(PROJECT_ROOT, 'fpl_fixture_analyzer.html')
    if os.path.exists(original_html):
        return send_from_directory(PROJECT_ROOT, 'fpl_fixture_analyzer.html')
    
    # Fall back to modular frontend
    return send_from_directory(STATIC_DIR, 'index.html')


@app.route('/modern')
def serve_modern_index():
    """Serve the modern modular frontend (in development)"""
    return send_from_directory(STATIC_DIR, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files - catches non-API paths"""
    # Don't intercept API routes
    if path.startswith('api/'):
        abort(404, description=f"API endpoint not found: {path}")
    
    # Try static folder first
    static_path = os.path.join(STATIC_DIR, path)
    if os.path.exists(static_path):
        return send_from_directory(STATIC_DIR, path)
    
    # Then try project root (for JSON files, etc.)
    project_path = os.path.join(PROJECT_ROOT, path)
    if os.path.exists(project_path):
        return send_from_directory(PROJECT_ROOT, path)
    
    abort(404, description=f"File not found: {path}")


# ==============================================================================
# Run Server
# ==============================================================================

def run_server(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
    """Run the Flask server"""
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    import click
    
    @click.command()
    @click.option('--host', '-h', default='0.0.0.0', help='Host to bind to')
    @click.option('--port', '-p', default=5000, type=int, help='Port to listen on')
    @click.option('--debug', '-d', is_flag=True, help='Enable debug mode')
    @click.option('--data', '-f', type=click.Path(exists=True), help='Pre-load data file')
    def main(host, port, debug, data):
        """Start the FPL Predictor API server"""
        if data:
            pred = get_predictor()
            if pred.initialize(data):
                print(f"Pre-loaded data from {data}")
            else:
                print(f"Warning: Failed to pre-load {data}")
        
        print(f"Starting FPL Predictor API on http://{host}:{port}")
        print(f"Static files served from: {STATIC_DIR}")
        run_server(host, port, debug)
    
    main()
