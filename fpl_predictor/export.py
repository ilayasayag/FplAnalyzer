"""
JSON Export Module

Exports predictions in a format compatible with the HTML analyzer
for import and visualization.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from config import OUTPUT_DIR
from models.prediction import Prediction, SquadPrediction
from engine.player_stats import PlayerStatsEngine, PlayerAnalysis
from engine.batch_analyzer import BatchAnalyzer


class PredictionExporter:
    """
    Exports predictions to JSON format compatible with HTML analyzer.
    """
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize the exporter.
        
        Args:
            output_dir: Directory for output files (default: config.OUTPUT_DIR)
        """
        self.output_dir = Path(output_dir or OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_player_prediction(self, prediction: Prediction,
                                  filename: Optional[str] = None) -> str:
        """
        Export a single player prediction.
        
        Args:
            prediction: Prediction object
            filename: Output filename (auto-generated if not provided)
            
        Returns:
            Path to exported file
        """
        if filename is None:
            safe_name = prediction.player_name.replace(' ', '_').lower()
            filename = f"prediction_{safe_name}_gw{prediction.gameweek}.json"
        
        filepath = self.output_dir / filename
        
        export_data = {
            'type': 'player_prediction',
            'generated_at': datetime.now().isoformat(),
            'prediction': prediction.to_dict(),
        }
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        return str(filepath)
    
    def export_squad_prediction(self, squad: SquadPrediction,
                                 filename: Optional[str] = None) -> str:
        """
        Export squad predictions.
        
        Args:
            squad: SquadPrediction object
            filename: Output filename (auto-generated if not provided)
            
        Returns:
            Path to exported file
        """
        if filename is None:
            safe_name = squad.squad_name.replace(' ', '_').lower()
            filename = f"squad_{safe_name}_gw{squad.gameweek}.json"
        
        filepath = self.output_dir / filename
        
        export_data = {
            'type': 'squad_prediction',
            'generated_at': datetime.now().isoformat(),
            'squad': squad.to_dict(),
        }
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        return str(filepath)
    
    def export_all_predictions(self, 
                                squads: Dict[int, SquadPrediction],
                                gameweek: int,
                                filename: Optional[str] = None) -> str:
        """
        Export predictions for all squads.
        
        This format is designed for import into the HTML analyzer.
        
        Args:
            squads: Dict of entry_id -> SquadPrediction
            gameweek: Gameweek number
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        if filename is None:
            filename = f"predictions_gw{gameweek}.json"
        
        filepath = self.output_dir / filename
        
        # Format for HTML analyzer compatibility
        export_data = {
            'type': 'league_predictions',
            'generated_at': datetime.now().isoformat(),
            'gameweek': gameweek,
            'squads': {},
        }
        
        for entry_id, squad in squads.items():
            export_data['squads'][str(entry_id)] = {
                'name': squad.squad_name,
                'total_expected': round(squad.total_expected_points, 2),
                'formation': squad.optimal_formation,
                'players': [
                    {
                        'id': p.player_id,
                        'name': p.player_name,
                        'position': p.position,
                        'opponent': p.opponent_short,
                        'opponent_batch': p.opponent_batch,
                        'expected_points': round(p.expected_points, 2),
                        'in_optimal_11': p in squad.optimal_11,
                        'breakdown': {
                            'playing': round(p.breakdown.playing_points, 2),
                            'goals': round(p.breakdown.goal_points, 2),
                            'assists': round(p.breakdown.assist_points, 2),
                            'clean_sheet': round(p.breakdown.clean_sheet_points, 2),
                            'bonus': round(p.breakdown.expected_bonus, 2),
                        }
                    }
                    for p in squad.predictions
                ]
            }
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        return str(filepath)
    
    def export_player_analysis(self,
                                player_stats: PlayerStatsEngine,
                                filename: Optional[str] = None) -> str:
        """
        Export all player analysis data.
        
        Args:
            player_stats: Player statistics engine
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        if filename is None:
            filename = "player_analysis.json"
        
        filepath = self.output_dir / filename
        
        export_data = {
            'type': 'player_analysis',
            'generated_at': datetime.now().isoformat(),
            'players': {}
        }
        
        for player_id, analysis in player_stats.player_analyses.items():
            export_data['players'][str(player_id)] = self._analysis_to_dict(analysis)
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        return str(filepath)
    
    def _analysis_to_dict(self, analysis: PlayerAnalysis) -> Dict[str, Any]:
        """Convert PlayerAnalysis to exportable dict"""
        stats = analysis.overall_stats
        
        result = {
            'id': analysis.player_id,
            'name': analysis.player_name,
            'position': analysis.position,
            'team_id': analysis.team_id,
            'overall': {
                'games': stats.games_played,
                'minutes': stats.total_minutes,
                'goals': stats.goals,
                'assists': stats.assists,
                'clean_sheets': stats.clean_sheets,
                'bonus': stats.bonus_points,
                'points': stats.total_points,
                'goals_per_90': round(stats.goals_per_90, 3),
                'assists_per_90': round(stats.assists_per_90, 3),
                'clean_sheet_rate': round(stats.clean_sheet_rate, 3),
                'ppg': round(stats.points_per_game, 2),
            },
            'batch_stats': {},
            'rotation_risk': round(analysis.rotation_risk, 2),
            'data_quality': round(analysis.data_quality, 2),
        }
        
        # Add batch-specific stats
        for batch, batch_stats in analysis.batch_stats.items():
            batch_key = f"{batch[0]}-{batch[1]}"
            result['batch_stats'][batch_key] = {
                'games': batch_stats.games_played,
                'goals_per_90': round(batch_stats.goals_per_90, 3),
                'assists_per_90': round(batch_stats.assists_per_90, 3),
                'clean_sheet_rate': round(batch_stats.clean_sheet_rate, 3),
                'ppg': round(batch_stats.points_per_game, 2),
            }
        
        return result
    
    def export_batch_analysis(self,
                               batch_analyzer: BatchAnalyzer,
                               filename: Optional[str] = None) -> str:
        """
        Export batch analysis data.
        
        Args:
            batch_analyzer: Batch analyzer
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        if filename is None:
            filename = "batch_analysis.json"
        
        filepath = self.output_dir / filename
        
        export_data = {
            'type': 'batch_analysis',
            'generated_at': datetime.now().isoformat(),
            'batches': batch_analyzer.get_batch_summary(),
            'standings': {
                str(k): v for k, v in batch_analyzer.standings.items()
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        return str(filepath)


def export_for_analyzer(predictions: Dict[int, SquadPrediction],
                        gameweek: int,
                        output_path: Optional[str] = None) -> str:
    """
    Convenience function to export predictions for HTML analyzer.
    
    Args:
        predictions: Dict of entry_id -> SquadPrediction
        gameweek: Gameweek number
        output_path: Output file path
        
    Returns:
        Path to exported file
    """
    exporter = PredictionExporter()
    return exporter.export_all_predictions(predictions, gameweek, output_path)


def create_analyzer_import_format(predictions: List[Prediction],
                                   gameweek: int) -> Dict[str, Any]:
    """
    Create a data structure that can be imported by the HTML analyzer.
    
    This returns a dictionary that can be JSON-stringified and pasted
    into the analyzer's import field.
    
    Args:
        predictions: List of predictions
        gameweek: Gameweek number
        
    Returns:
        Dictionary in analyzer-compatible format
    """
    return {
        'predictedPoints': {
            str(p.player_id): {
                'expected_points': round(p.expected_points, 2),
                'gameweek': gameweek,
                'opponent': p.opponent_short,
                'breakdown': p.breakdown.to_short_string(),
                'confidence': round(p.confidence, 2),
            }
            for p in predictions
        },
        'generatedAt': datetime.now().isoformat(),
        'gameweek': gameweek,
    }

