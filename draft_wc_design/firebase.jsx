// firebase.jsx — Firebase initialisation + emulator wiring
// Loaded before all other .jsx files

const _firebaseConfig = {
  apiKey:            "AIzaSyDxl9uFOn-aTTrT53GKI5WSisOWpabxA0w",
  authDomain:        "fpl-analyzer-792eb.firebaseapp.com",
  projectId:         "fpl-analyzer-792eb",
  storageBucket:     "fpl-analyzer-792eb.firebasestorage.app",
  messagingSenderId: "210426262203",
  appId:             "1:210426262203:web:d060ad788d7d08b683ef9e",
};

firebase.initializeApp(_firebaseConfig);
const _db   = firebase.firestore();
const _auth = firebase.auth();

// Point to local emulators when running on localhost
if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
  _db.useEmulator("localhost", 8080);
  _auth.useEmulator("http://localhost:9099");
}

// Shared Fetch API fetch wrapper with Auth token injection and automatic refresh
async function apiCall(method, path, body) {
  const user = _auth.currentUser;
  const headers = {
    "Content-Type": "application/json",
  };
  if (user) {
    const token = await user.getIdToken(/* forceRefresh */ false);
    headers["Authorization"] = `Bearer ${token}`;
  }
  
  // Resolve API base URL dynamically: local Flask on localhost, otherwise the
  // direct Cloud Run URL. We bypass the same-origin Hosting rewrite because that
  // proxy intermittently times out (~40%) on the large /players read; the direct
  // endpoint is reliably ~0.9s. CORS allows the web.app origin + auth header.
  const baseUrl = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:5000"
    : "https://api-4anrfyrdxa-uc.a.run.app";
  
  const res = await fetch(`${baseUrl}/api/v1/wc${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  
  const data = await res.json();
  if (!res.ok) throw { status: res.status, ...data };
  return data.data;
}

// Expose globally
Object.assign(window, { _db, _auth, apiCall });
