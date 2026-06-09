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
// Use the named "gamedb" database — the real data lives there, NOT in
// "(default)" (which is empty in prod). The backend admin SDK already targets
// gamedb; the client must match or standings/scores/draft snapshots come back
// empty. The emulator also serves gamedb as its canonical store.
const _db   = firebase.app().firestore("gamedb");
const _auth = firebase.auth();

// Point to local emulators when running on localhost unless production override is set
const _useProd = localStorage.getItem("firebase_use_prod") === "true";
if ((window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") && !_useProd) {
  _db.useEmulator("localhost", 8080);
  _auth.useEmulator("http://localhost:9099");
}

// Shared Fetch API fetch wrapper with Auth token injection and automatic refresh.
//
// Resilience: each request has a hard timeout (AbortController) and transient
// NETWORK failures ("TypeError: Failed to fetch", aborted timeouts) are retried
// with a short backoff. This is the root fix for the "squads disappear" bug —
// a single dropped connection on the direct Cloud Run endpoint used to surface
// as a fatal error that blanked already-loaded data. Retries are limited to
// idempotent GET/HEAD requests so a flaky POST/PUT/PATCH/DELETE can never be
// silently double-applied. HTTP error responses (4xx/5xx) are NOT retried —
// they carry a real status and are thrown straight to the caller.
async function apiCall(method, path, body, opts = {}) {
  // opts: { timeoutMs?, _attempt? }. Back-compat: callers passing only 3 args
  // get the 12s default. Slow admin operations (e.g. the mock GW simulator,
  // which runs synchronously server-side for ~30-50s) pass a longer timeoutMs
  // so the fetch isn't aborted before the server finishes.
  const _attempt = opts._attempt || 0;
  const user = _auth.currentUser;
  const headers = {
    "Content-Type": "application/json",
  };
  if (user) {
    const token = await user.getIdToken(/* forceRefresh */ false);
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Resolve API base URL dynamically: local Flask on localhost, otherwise the
  // SAME-ORIGIN Hosting rewrite ("/api/**" -> the `api` function, configured in
  // firebase.json). Same-origin is the key fix for the "squads disappear" bug on
  // some clients: the previous direct Cloud Run URL (api-*.run.app) is a
  // cross-origin request, which privacy browsers / ad-blockers / tracking
  // prevention (e.g. Edge InPrivate) silently block as "TypeError: Failed to
  // fetch". The rewrite was once abandoned for ~40% timeouts, but min_instances
  // keeps the function warm now (reliably ~0.3s) and the apiCall retry above
  // absorbs any rare hiccup. Empty base => requests stay on the page's origin.
  const baseUrl = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") && !_useProd
    ? "http://localhost:5000"
    : "";

  const MAX_RETRIES = 2;
  const TIMEOUT_MS = opts.timeoutMs || 12000;
  const isIdempotent = method === "GET" || method === "HEAD";

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res;
  try {
    res = await fetch(`${baseUrl}/api/v1/wc${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    // fetch() rejected before any response: network down, connection reset,
    // CORS block, or our timeout aborted it. Retry idempotent reads with backoff.
    clearTimeout(timer);
    if (isIdempotent && _attempt < MAX_RETRIES) {
      await new Promise(r => setTimeout(r, 400 * (_attempt + 1)));
      return apiCall(method, path, body, { ...opts, _attempt: _attempt + 1 });
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  const data = await res.json();
  if (!res.ok) throw { status: res.status, ...data };
  return data.data;
}

// ---------------------------------------------------------------------------
// Dev-only DB sync: export prod Firestore to a JSON file, and import a JSON
// file into the LOCAL emulator. Intended as a development convenience (e.g.
// pull a snapshot of prod squads into your emulator to test against real data).
//
// NOT a full backup. The Web SDK can only read what the security rules grant
// the signed-in user, and cannot enumerate (sub)collections. So this captures
// only client-readable, explicitly-listed collections. It deliberately OMITS:
//   - users              (rules: a user may read only their OWN doc)
//   - wc_gameweeks        (no client read rule → permission denied)
//   - wc_group_standings  (no client read rule → permission denied)
// For a complete/authoritative backup use `gcloud firestore export` or
// `firebase emulators:export`.
//
// Each exported doc is a node { _data, _subcollections } applied RECURSIVELY,
// so nested subcollections (e.g. leagues/<id>/draft/<gw>/picks) round-trip.
// Because we iterate every doc in `leagues`, this covers BOTH leagues
// (lg_mock_draft and lg_pre_draft) with no league-specific handling.

// Subcollection layout (Web SDK can't list these). {} = no further nesting.
const _LEAGUE_SUBCOLLECTIONS = {
  members: {},
  squads: {},
  lineups: {},
  scores: {},
  schedule: {},
  knockout: {},
  standings: {},
  transfer_windows: {},
  transactions: {},
  trades: {},
  waivers: {},
  draft: { picks: {} }, // draft docs hold a nested `picks` subcollection
};

const _ROOT_COLLECTIONS = {
  wc_config: {},
  wc_teams: {},
  wc_players: {},
  wc_fixtures: { playerScores: {} },
  leagues: _LEAGUE_SUBCOLLECTIONS,
};

async function _exportSubcollections(docRef, spec) {
  const out = {};
  for (const [name, childSpec] of Object.entries(spec)) {
    const snap = await docRef.collection(name).get();
    if (snap.empty) continue;
    out[name] = {};
    for (const sdoc of snap.docs) {
      out[name][sdoc.id] = {
        _data: sdoc.data(),
        _subcollections: await _exportSubcollections(sdoc.ref, childSpec),
      };
    }
  }
  return out;
}

async function exportFirestore() {
  alert("Exporting database... this may take a few seconds.");
  try {
    const data = {};
    for (const [colName, spec] of Object.entries(_ROOT_COLLECTIONS)) {
      console.log(`Exporting collection: ${colName}`);
      const snap = await _db.collection(colName).get();
      data[colName] = {};
      for (const doc of snap.docs) {
        data[colName][doc.id] = {
          _data: doc.data(),
          _subcollections: await _exportSubcollections(doc.ref, spec),
        };
      }
    }

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `firestore_export_${new Date().toISOString().slice(0, 10)}.json`;
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

// Flatten the recursive export tree into a flat list of { ref, data } writes.
function _collectWrites(ref, node, writes) {
  writes.push({ ref, data: node._data || {} });
  const subs = node._subcollections || {};
  for (const [name, sdocs] of Object.entries(subs)) {
    for (const [sdocId, childNode] of Object.entries(sdocs)) {
      _collectWrites(ref.collection(name).doc(sdocId), childNode, writes);
    }
  }
}

async function importFirestore(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async (e) => {
    try {
      const data = JSON.parse(e.target.result);
      alert("Importing database... please wait.");

      // Flatten every doc (including nested subcollections), then commit in
      // batches of 500 (Firestore's per-batch write cap) rather than one
      // awaited write per doc.
      const writes = [];
      for (const [colName, docs] of Object.entries(data)) {
        for (const [docId, node] of Object.entries(docs)) {
          _collectWrites(_db.collection(colName).doc(docId), node, writes);
        }
      }

      const BATCH = 500;
      for (let i = 0; i < writes.length; i += BATCH) {
        const batch = _db.batch();
        for (const w of writes.slice(i, i + BATCH)) batch.set(w.ref, w.data);
        await batch.commit();
        console.log(`Imported ${Math.min(i + BATCH, writes.length)} / ${writes.length} docs`);
      }

      alert(`Import completed (${writes.length} docs). Reloading...`);
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
