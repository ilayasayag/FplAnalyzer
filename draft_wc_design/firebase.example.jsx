// firebase.example.jsx — Template for Firebase initialization + emulator wiring
// Copy this to firebase.jsx and fill in your actual config from Firebase console if deploying.

const _firebaseConfig = {
  apiKey:            "YOUR_API_KEY_HERE",
  authDomain:        "fpl-analyzer-792eb.firebaseapp.com",
  projectId:         "fpl-analyzer-792eb",
  storageBucket:     "fpl-analyzer-792eb.appspot.com",
  messagingSenderId: "YOUR_SENDER_ID_HERE",
  appId:             "YOUR_APP_ID_HERE",
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
  if (!user) throw new Error("Not authenticated");
  const token = await user.getIdToken(/* forceRefresh */ false);
  
  const res = await fetch(`http://localhost:5000/api/v1/wc${path}`, {
    method,
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  
  const data = await res.json();
  if (!res.ok) throw { status: res.status, ...data };
  return data.data;
}

// Expose globally
Object.assign(window, { _db, _auth, apiCall });
