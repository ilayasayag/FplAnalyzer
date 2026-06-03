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

// Point to local emulators when running on localhost unless production override is set
const _useProd = localStorage.getItem("firebase_use_prod") === "true";
if ((window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") && !_useProd) {
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
  const baseUrl = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") && !_useProd
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

// Data Export/Import functions to sync Prod to local Emulator from the UI
async function exportFirestore() {
  alert("Exporting database... This will take a few seconds.");
  try {
    const data = {};
    const rootCollections = ["wc_teams", "wc_players", "wc_fixtures", "wc_config", "leagues"];
    
    for (const colName of rootCollections) {
      console.log(`Exporting root collection: ${colName}`);
      const snap = await _db.collection(colName).get();
      data[colName] = {};
      
      for (const doc of snap.docs) {
        data[colName][doc.id] = {
          _data: doc.data(),
          _subcollections: {}
        };
        
        // If leagues, fetch all subcollections
        if (colName === "leagues") {
          const subcols = ["members", "squads", "lineups", "scores", "schedule", "knockout", "transfer_windows", "transactions", "standings", "trades", "waivers"];
          for (const subcolName of subcols) {
            const subSnap = await doc.ref.collection(subcolName).get();
            if (!subSnap.empty) {
              data[colName][doc.id]._subcollections[subcolName] = {};
              for (const sdoc of subSnap.docs) {
                data[colName][doc.id]._subcollections[subcolName][sdoc.id] = sdoc.data();
              }
            }
          }
        }
        // If wc_fixtures, fetch playerScores subcollection
        if (colName === "wc_fixtures") {
          const subSnap = await doc.ref.collection("playerScores").get();
          if (!subSnap.empty) {
            data[colName][doc.id]._subcollections["playerScores"] = {};
            for (const sdoc of subSnap.docs) {
              data[colName][doc.id]._subcollections["playerScores"][sdoc.id] = sdoc.data();
            }
          }
        }
      }
    }
    
    // Download
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `firestore_export_${new Date().toISOString().slice(0,10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    alert("Export completed successfully!");
  } catch (error) {
    console.error("Export failed:", error);
    alert(`Export failed: ${error.message || error}`);
  }
}

async function importFirestore(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async (e) => {
    try {
      const data = JSON.parse(e.target.result);
      alert("Importing database... Please wait.");
      
      for (const [colName, docs] of Object.entries(data)) {
        console.log(`Importing collection: ${colName}`);
        for (const [docId, docObj] of Object.entries(docs)) {
          const docRef = _db.collection(colName).doc(docId);
          await docRef.set(docObj._data);
          
          if (docObj._subcollections) {
            for (const [subcolName, subdocs] of Object.entries(docObj._subcollections)) {
              for (const [sdocId, sdocData] of Object.entries(subdocs)) {
                await docRef.collection(subcolName).doc(sdocId).set(sdocData);
              }
            }
          }
        }
      }
      alert("Import completed successfully! Please reload the page to see the new data.");
      window.location.reload();
    } catch (error) {
      console.error("Import failed:", error);
      alert(`Import failed: ${error.message || error}`);
    }
  };
  reader.readAsText(file);
}

// Expose globally
Object.assign(window, { _db, _auth, apiCall, exportFirestore, importFirestore });
