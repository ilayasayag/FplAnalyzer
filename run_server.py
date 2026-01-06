#!/usr/bin/env python3
"""
FPL Analyzer Server Runner

Run this script from the project root to start the Flask API server.

Usage:
    python run_server.py --debug
    python run_server.py -p 8080
    python run_server.py --data fpl_league_data_2026-01-05.json
"""

import sys
import os
import click

# Ensure the project root is in the path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.api import app, run_server, get_predictor


@click.command()
@click.option('--host', '-h', default='0.0.0.0', help='Host to bind to')
@click.option('--port', '-p', default=5000, type=int, help='Port to listen on')
@click.option('--debug', '-d', is_flag=True, help='Enable debug mode')
@click.option('--data', '-f', type=click.Path(exists=True), help='Pre-load data file')
def main(host, port, debug, data):
    """Start the FPL Analyzer API server"""
    if data:
        pred = get_predictor()
        if pred.initialize(data):
            print(f"Pre-loaded data from {data}")
        else:
            print(f"Warning: Failed to pre-load {data}")
    
    print(f"\n🏈 FPL Analyzer API")
    print(f"   Server: http://{host}:{port}")
    print(f"   Open in browser: http://localhost:{port}")
    print(f"   Debug mode: {'ON' if debug else 'OFF'}\n")
    run_server(host, port, debug)


if __name__ == '__main__':
    main()

