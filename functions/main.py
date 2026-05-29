import os
import sys

# Ensure functions folder is in sys.path so that local modules import correctly
functions_dir = os.path.dirname(os.path.abspath(__file__))
if functions_dir not in sys.path:
    sys.path.insert(0, functions_dir)

# Import the Flask app (which automatically handles firebase_admin.initialize_app inside api.py)
from fpl_predictor.api import app

from firebase_functions import https_fn

# Expose the api endpoint to handle incoming Flask routes
@https_fn.on_request()
def api(req: https_fn.Request) -> https_fn.Response:
    with app.request_context(req.environ):
        return app.full_dispatch_request()
