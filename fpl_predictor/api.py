"""
Flask REST API for FPL Score Predictor

Provides HTTP endpoints for predictions and analysis.
"""

import os
from typing import Optional
from flask import Flask, jsonify, request, abort
from flask_cors import CORS

from config import DATA_DIR
from data.loader import DataLoader
from data.standings import StandingsFetcher
from engine.batch_analyzer import BatchAnalyzer
from engine.player_stats import PlayerStatsEngine
from engine.points_calculator import create_prediction_engine
from export import PredictionExporter

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Global predictor instance
predictor = None


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
        """Initialize the predictor with data"""
        if not self.loader.load_from_file(data_file):
            return False
        
        self.standings_fetcher.update_teams_with_positions(self.loader.teams)
        self.batch_analyzer.initialize(self.loader.teams, self.standings_fetcher)
        self.batch_analyzer.assign_opponent_batches_to_players(self.loader.players)
        self.player_stats.analyze_all_players(self.loader.players)
        self.points_calc = create_prediction_engine(
            self.player_stats, self.batch_analyzer
        )
        
        self._initialized = True
        self._data_file = data_file
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
# API Routes
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


@app.route('/api/load', methods=['POST'])
def load_data():
    """
    Load data from a JSON file.
    
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
        if pred.loader.load_from_dict(json_data['data']):
            # Initialize other components
            pred.standings_fetcher.update_teams_with_positions(pred.loader.teams)
            pred.batch_analyzer.initialize(pred.loader.teams, pred.standings_fetcher)
            pred.batch_analyzer.assign_opponent_batches_to_players(pred.loader.players)
            pred.player_stats.analyze_all_players(pred.loader.players)
            pred.points_calc = create_prediction_engine(
                pred.player_stats, pred.batch_analyzer
            )
            pred._initialized = True
            
            return jsonify({
                'success': True,
                'message': 'Data loaded successfully',
                'statistics': pred.loader.get_statistics()
            })
        else:
            abort(500, description="Failed to parse data")
    
    abort(400, description="Either 'file_path' or 'data' required")


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
        abort(400, description="Data not loaded. Call /api/load first")
    
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
        abort(400, description="Data not loaded. Call /api/load first")
    
    players = pred.loader.get_squad_players(entry_id)
    if not players:
        abort(404, description=f"Squad not found for entry {entry_id}")
    
    entry_name = pred.loader.get_entry_name(entry_id)
    gameweek = request.args.get('gameweek', pred.loader.current_gameweek, type=int)
    
    # Get opponents (simplified - uses available teams)
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
        abort(400, description="Data not loaded. Call /api/load first")
    
    search = request.args.get('search', '')
    position = request.args.get('position', type=int)
    team_id = request.args.get('team_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    
    if search:
        players = pred.loader.search_players(search, limit)
    else:
        players = list(pred.loader.players.values())
    
    # Apply filters
    if position:
        players = [p for p in players if p.position == position]
    if team_id:
        players = [p for p in players if p.team_id == team_id]
    
    # Limit results
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
        abort(400, description="Data not loaded. Call /api/load first")
    
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
        abort(400, description="Data not loaded. Call /api/load first")
    
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
        abort(400, description="Data not loaded. Call /api/load first")
    
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
        abort(400, description="Data not loaded. Call /api/load first")
    
    summary = pred.batch_analyzer.get_batch_summary()
    
    return jsonify({
        'batches': summary
    })


@app.route('/api/league', methods=['GET'])
def get_league_info():
    """Get league information"""
    pred = get_predictor()
    if not pred.is_initialized:
        abort(400, description="Data not loaded. Call /api/load first")
    
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
        abort(400, description="Data not loaded. Call /api/load first")
    
    json_data = request.get_json() or {}
    gameweek = json_data.get('gameweek', pred.loader.current_gameweek)
    
    # Generate predictions for all squads
    squads = {}
    for entry_id in pred.loader.get_all_entry_ids():
        players = pred.loader.get_squad_players(entry_id)
        if players:
            entry_name = pred.loader.get_entry_name(entry_id)
            
            # Get opponents
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
    
    # Export to file
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
        run_server(host, port, debug)
    
    main()

