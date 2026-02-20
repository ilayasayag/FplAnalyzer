#!/usr/bin/env python3
"""FPL Draft Analyzer - Server Entry Point."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.api import app, run_server


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"

    print(f"\n  FPL Draft Analyzer")
    print(f"  Server: http://{host}:{port}")
    print(f"  Open:   http://localhost:{port}")
    print(f"  Debug:  {'ON' if debug else 'OFF'}\n")

    run_server(host, port, debug)


if __name__ == "__main__":
    main()
