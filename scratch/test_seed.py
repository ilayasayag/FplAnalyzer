import sys
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

# Connect to production database using secrets.json or local authentication
secrets_path = "secrets.json"
if os.path.exists(secrets_path):
    with open(secrets_path) as f:
        config = json.load(f)
    print("Loaded secrets.json successfully!")
else:
    print("secrets.json not found!")
    sys.exit(1)

# Initialize Firebase Admin with production app using the credential from secrets.json or default credentials
try:
    cred = credentials.Certificate(secrets_path)
    firebase_admin.initialize_app(cred, options={"projectId": "fpl-analyzer-792eb"})
except Exception as e:
    # If already initialized
    try:
        firebase_admin.initialize_app(options={"projectId": "fpl-analyzer-792eb"})
    except Exception as e2:
        print("Initialization error:", e2)

db = firestore.client(database_id="gamedb")

# Import the logic
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from fpl_predictor.api_wc import seed_mock_league

try:
    print("Running seed_mock_league locally...")
    seed_mock_league("u_debug_test", "Debug Manager", db)
    print("✅ Seed mock league completed successfully locally!")
except Exception as e:
    import traceback
    traceback.print_exc()
