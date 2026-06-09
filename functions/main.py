import os
import sys

# Ensure functions folder is in sys.path so that local modules import correctly
functions_dir = os.path.dirname(os.path.abspath(__file__))
if functions_dir not in sys.path:
    sys.path.insert(0, functions_dir)

# Import the Flask app (which automatically handles firebase_admin.initialize_app inside api.py)
from fpl_predictor.api import app

from firebase_functions import https_fn, options

# Expose the api endpoint to handle incoming Flask routes.
# min_instances=1 keeps one warm instance with a primed player cache so the
# live draft never hits a cold-instance stall on the large wc_players read.
# timeout_sec is raised well above the 60s default so heavy one-shot admin
# operations (e.g. the roster reset / full fixtures rebuild, which deletes and
# rewrites the whole wc_fixtures collection) can finish in one request; normal
# endpoints return in well under a second so this never affects them. 512MB
# gives the player-pool cache + fixture processing comfortable headroom.
@https_fn.on_request(min_instances=1, timeout_sec=540, memory=options.MemoryOption.MB_512)
def api(req: https_fn.Request) -> https_fn.Response:
    with app.request_context(req.environ):
        return app.full_dispatch_request()
