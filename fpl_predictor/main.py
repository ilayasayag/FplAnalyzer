#!/usr/bin/env python3
"""
FPL Score Predictor - CLI Interface

Command-line interface for predicting FPL player scores.
"""

import os
import sys
import json
import click
from pathlib import Path
from typing import Optional, List, Dict, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from config import DATA_DIR, OUTPUT_DIR, DEFAULT_BATCHES
from data.loader import DataLoader
from data.standings import StandingsFetcher
from engine.batch_analyzer import BatchAnalyzer
from engine.player_stats import PlayerStatsEngine
from engine.points_calculator import create_prediction_engine
from models.prediction import Prediction, SquadPrediction

console = Console()


class FPLPredictor:
    """Main predictor class that orchestrates all components"""
    
    def __init__(self, data_file: Optional[str] = None):
        self.loader = DataLoader()
        self.standings_fetcher = StandingsFetcher()
        self.batch_analyzer = BatchAnalyzer()
        self.player_stats = PlayerStatsEngine()
        self.points_calc = None
        self._initialized = False
        
        if data_file:
            self.load_data(data_file)
    
    def load_data(self, filepath: str) -> bool:
        """Load data from JSON file"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Loading data...", total=None)
            
            if not self.loader.load_from_file(filepath):
                console.print("[red]Failed to load data file[/red]")
                return False
            
            progress.update(task, description="Fetching standings...")
            self.standings_fetcher.update_teams_with_positions(self.loader.teams)
            
            progress.update(task, description="Initializing batch analyzer...")
            self.batch_analyzer.initialize(self.loader.teams, self.standings_fetcher)
            self.batch_analyzer.assign_opponent_batches_to_players(self.loader.players)
            
            progress.update(task, description="Analyzing players...")
            self.player_stats.analyze_all_players(self.loader.players)
            
            progress.update(task, description="Creating prediction engine...")
            self.points_calc = create_prediction_engine(
                self.player_stats, self.batch_analyzer
            )
            
            self._initialized = True
        
        stats = self.loader.get_statistics()
        console.print(Panel(
            f"[green]Data loaded successfully![/green]\n"
            f"Players: {stats['total_players']} ({stats['players_with_history']} with history)\n"
            f"Teams: {stats['total_teams']}\n"
            f"Current GW: {stats['current_gameweek']}\n"
            f"Fetched: {stats['fetched_at'] or 'Unknown'}",
            title="Data Summary"
        ))
        
        return True
    
    def predict_player(self, player_name: str, 
                       opponent_name: Optional[str] = None,
                       gameweek: Optional[int] = None) -> Optional[Prediction]:
        """Predict points for a single player"""
        if not self._initialized:
            console.print("[red]Please load data first[/red]")
            return None
        
        # Find player
        matches = self.loader.search_players(player_name, limit=5)
        if not matches:
            console.print(f"[red]Player '{player_name}' not found[/red]")
            return None
        
        player = matches[0]
        gw = gameweek or self.loader.current_gameweek
        
        # Find opponent
        if opponent_name:
            opponent = self.loader.get_team_by_name(opponent_name)
        else:
            # Use player's team's next opponent (simplified)
            opponent = list(self.loader.teams.values())[0]  # Placeholder
        
        if not opponent:
            console.print(f"[red]Opponent team not found[/red]")
            return None
        
        prediction = self.points_calc.calculate_expected_points(
            player, opponent, gw, is_home=True
        )
        
        return prediction
    
    def predict_squad(self, entry_id: int, 
                      gameweek: Optional[int] = None) -> Optional[SquadPrediction]:
        """Predict points for an entire squad"""
        if not self._initialized:
            console.print("[red]Please load data first[/red]")
            return None
        
        players = self.loader.get_squad_players(entry_id)
        if not players:
            console.print(f"[red]Squad not found for entry {entry_id}[/red]")
            return None
        
        entry_name = self.loader.get_entry_name(entry_id)
        gw = gameweek or self.loader.current_gameweek
        
        # Get opponents for each player's team
        # This is simplified - in reality, you'd need fixture data
        opponents = {}
        for player in players:
            if player.team_id not in opponents:
                # Find an opponent (simplified - just use a different team)
                for team in self.loader.teams.values():
                    if team.id != player.team_id:
                        opponents[player.team_id] = (team, True)
                        break
        
        squad_pred = self.points_calc.calculate_squad_predictions(
            entry_id, entry_name, players, opponents, gw
        )
        
        return squad_pred
    
    def get_batch_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all batches"""
        return self.batch_analyzer.get_batch_summary()


def display_prediction(prediction: Prediction) -> None:
    """Display a single player prediction"""
    breakdown = prediction.breakdown
    
    table = Table(title=f"{prediction.player_name} - GW{prediction.gameweek}", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Points", justify="right")
    
    # Playing time
    table.add_row(
        "Playing (60+ min)",
        f"{breakdown.playing_prob_60_plus:.0%}",
        f"{breakdown.playing_points:.2f}"
    )
    
    # Goals
    table.add_row(
        "Expected Goals",
        f"{breakdown.expected_goals:.2f}",
        f"{breakdown.goal_points:.2f}"
    )
    
    # Assists
    table.add_row(
        "Expected Assists",
        f"{breakdown.expected_assists:.2f}",
        f"{breakdown.assist_points:.2f}"
    )
    
    # Clean sheet
    if breakdown.clean_sheet_prob > 0:
        table.add_row(
            "Clean Sheet Prob",
            f"{breakdown.clean_sheet_prob:.0%}",
            f"{breakdown.clean_sheet_points:.2f}"
        )
    
    # Saves
    if breakdown.expected_saves > 0:
        table.add_row(
            "Expected Saves",
            f"{breakdown.expected_saves:.1f}",
            f"{breakdown.saves_points:.2f}"
        )
    
    # Bonus
    table.add_row(
        "Expected Bonus",
        f"{breakdown.expected_bonus:.1f}",
        f"{breakdown.expected_bonus:.2f}"
    )
    
    # Yellow card
    table.add_row(
        "Yellow Card Risk",
        f"{breakdown.yellow_card_risk:.0%}",
        f"{breakdown.yellow_card_penalty:.2f}"
    )
    
    # Total
    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        "",
        f"[bold]{prediction.expected_points:.2f}[/bold]"
    )
    
    console.print(table)
    
    # Fixture info
    console.print(f"\nFixture: {prediction.fixture_string}")
    console.print(f"Opponent Batch: {prediction.opponent_batch} (Pos: {prediction.opponent_position})")
    console.print(f"Confidence: {prediction.confidence:.0%} ({prediction.data_quality})")
    
    if prediction.warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for warning in prediction.warnings:
            console.print(f"  ⚠️  {warning}")


def display_squad_prediction(squad: SquadPrediction) -> None:
    """Display squad predictions"""
    table = Table(
        title=f"{squad.squad_name} - GW{squad.gameweek}",
        box=box.ROUNDED
    )
    table.add_column("Player", style="cyan")
    table.add_column("Pos", style="yellow")
    table.add_column("Opponent", style="magenta")
    table.add_column("xPts", justify="right", style="green")
    table.add_column("Breakdown", style="dim")
    
    # Sort by expected points
    sorted_preds = sorted(squad.predictions, 
                          key=lambda x: x.expected_points, reverse=True)
    
    for pred in sorted_preds:
        in_11 = "✓" if pred in squad.optimal_11 else ""
        table.add_row(
            f"{pred.player_name} {in_11}",
            pred.position,
            pred.fixture_string,
            f"{pred.expected_points:.1f}",
            pred.breakdown.to_short_string()
        )
    
    console.print(table)
    
    console.print(f"\n[bold]Optimal Formation:[/bold] {squad.optimal_formation}")
    console.print(f"[bold]Total Expected Points (Best 11):[/bold] {squad.total_expected_points:.1f}")


def display_batch_summary(batches: List[Dict[str, Any]]) -> None:
    """Display batch summary"""
    table = Table(title="Team Batches", box=box.ROUNDED)
    table.add_column("Batch", style="cyan")
    table.add_column("Name", style="yellow")
    table.add_column("Teams", style="magenta")
    table.add_column("Avg GPG", justify="right")
    table.add_column("Avg GC", justify="right")
    table.add_column("CS Rate", justify="right")
    
    for batch in batches:
        table.add_row(
            batch['range'],
            batch['name'],
            ", ".join(batch['teams'][:3]) + ("..." if len(batch['teams']) > 3 else ""),
            str(batch['avg_goals_per_game']),
            str(batch['avg_goals_conceded']),
            f"{batch['avg_clean_sheet_rate']}%"
        )
    
    console.print(table)


# CLI Commands
@click.group()
@click.pass_context
def cli(ctx):
    """FPL Score Predictor - Predict fantasy football player points"""
    ctx.ensure_object(dict)


@cli.command()
@click.argument('data_file', type=click.Path(exists=True))
@click.option('--player', '-p', help='Player name to predict')
@click.option('--opponent', '-o', help='Opponent team name')
@click.option('--gameweek', '-g', type=int, help='Gameweek number')
@click.pass_context
def predict(ctx, data_file, player, opponent, gameweek):
    """Predict points for a player"""
    predictor = FPLPredictor(data_file)
    
    if player:
        prediction = predictor.predict_player(player, opponent, gameweek)
        if prediction:
            display_prediction(prediction)
    else:
        console.print("[yellow]Use --player to specify a player name[/yellow]")


@cli.command()
@click.argument('data_file', type=click.Path(exists=True))
@click.option('--entry-id', '-e', type=int, required=True, help='League entry ID')
@click.option('--gameweek', '-g', type=int, help='Gameweek number')
@click.pass_context
def squad(ctx, data_file, entry_id, gameweek):
    """Predict points for a squad"""
    predictor = FPLPredictor(data_file)
    squad_pred = predictor.predict_squad(entry_id, gameweek)
    
    if squad_pred:
        display_squad_prediction(squad_pred)


@cli.command()
@click.argument('data_file', type=click.Path(exists=True))
@click.pass_context
def batches(ctx, data_file):
    """Show team batch summary"""
    predictor = FPLPredictor(data_file)
    summary = predictor.get_batch_summary()
    display_batch_summary(summary)


@cli.command()
@click.argument('data_file', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), help='Output JSON file')
@click.pass_context
def analyze(ctx, data_file, output):
    """Analyze all players and export results"""
    predictor = FPLPredictor(data_file)
    
    results = []
    for player_id, analysis in predictor.player_stats.player_analyses.items():
        results.append(predictor.player_stats.get_player_summary(player_id))
    
    # Sort by PPG
    results.sort(key=lambda x: x.get('ppg', 0), reverse=True)
    
    if output:
        with open(output, 'w') as f:
            json.dump(results, f, indent=2)
        console.print(f"[green]Results exported to {output}[/green]")
    else:
        # Display top players
        table = Table(title="Top Players by PPG", box=box.ROUNDED)
        table.add_column("Player", style="cyan")
        table.add_column("Pos", style="yellow")
        table.add_column("Games", justify="right")
        table.add_column("PPG", justify="right", style="green")
        table.add_column("G/90", justify="right")
        table.add_column("A/90", justify="right")
        
        for player in results[:20]:
            table.add_row(
                player['name'],
                player['position'],
                str(player['games_played']),
                str(player['ppg']),
                str(player['goals_per_90']),
                str(player['assists_per_90'])
            )
        
        console.print(table)


@cli.command()
def info():
    """Show information about the predictor"""
    console.print(Panel(
        "[bold]FPL Score Predictor[/bold]\n\n"
        "A statistical tool for predicting Fantasy Premier League player points.\n\n"
        "[cyan]Features:[/cyan]\n"
        "• Team batch analysis (Top 4, Mid-table, Relegation)\n"
        "• Per-player performance statistics\n"
        "• Weighted predictions based on opponent strength\n"
        "• Optimal 11 selection with formation rules\n\n"
        "[yellow]Usage:[/yellow]\n"
        "1. Export data from FPL Analyzer HTML tool\n"
        "2. Run: python main.py predict <data.json> -p 'Salah'\n"
        "3. Or: python main.py squad <data.json> -e <entry_id>",
        title="About"
    ))


if __name__ == '__main__':
    cli()

