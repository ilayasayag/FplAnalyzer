// =====================================================================
// WC26 — App orchestrator (router + tweaks)
// =====================================================================

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "leagueSize": 7,
  "gwPhase": "knockout",
  "themeAccent": "wc",
  "compactMode": false
}/*EDITMODE-END*/;

const ACCENT_THEMES = {
  wc:    { grad: "linear-gradient(94deg, #4a1ba8 0%, #4329c4 30%, #1f6dd1 60%, #1ad2c4 100%)", pill: "linear-gradient(94deg, #2bf094 0%, #1be8d4 100%)" },
  fpl:   { grad: "linear-gradient(94deg, #2d0b6e 0%, #3b1aa9 25%, #2c8acd 60%, #1bd6c8 100%)", pill: "linear-gradient(94deg, #00ff87 0%, #02efff 100%)" },
  fire:  { grad: "linear-gradient(94deg, #4a0d6e 0%, #c41262 35%, #ec582a 70%, #ffc844 100%)", pill: "linear-gradient(94deg, #ffd56b 0%, #ff6388 100%)" },
  forest:{ grad: "linear-gradient(94deg, #0d2818 0%, #1f6b3e 35%, #2eb05c 65%, #ffc844 100%)", pill: "linear-gradient(94deg, #00e87b 0%, #ffd56b 100%)" },
};

// Set the data-source banner state AND notify the TopBar chip so it always
// reflects the latest value (it reads a window global, so without an event it
// can latch a stale cold-start "down" after the real data resolves).
function setDataSource(v) {
  window.__DATA_SOURCE__ = v;
  try { window.dispatchEvent(new CustomEvent("wc-datasource", { detail: v })); } catch (e) {}
}

// Per-GW cache of team→opponent maps built from GET /fixtures?gw=N, keyed by
// the same isoCode the players use: { [gw]: { ISO: { opp, home } } }. Screens
// that need a GW other than the viewed one (Pick Team edits the NEXT gw) call
// fetchFixturesByTeamForGw on demand; in-flight requests are deduped and only
// non-empty rounds are cached, so a not-yet-scheduled GW is retried next time
// instead of latching an empty map.
window.WC_FIXTURES_BY_GW = window.WC_FIXTURES_BY_GW || {};
const _fixturesByGwInflight = {};
function buildFixturesByTeam(fixtures) {
  const byTeam = {};
  (fixtures || []).forEach(fx => {
    const h = ((fx.homeTeam || {}).isoCode || "").toUpperCase();
    const a = ((fx.awayTeam || {}).isoCode || "").toUpperCase();
    if (h && a) {
      byTeam[h] = { opp: a, home: true };
      byTeam[a] = { opp: h, home: false };
    }
  });
  return byTeam;
}
function fetchFixturesByTeamForGw(gw) {
  const cached = window.WC_FIXTURES_BY_GW[gw];
  if (cached && Object.keys(cached).length > 0) return Promise.resolve(cached);
  if (_fixturesByGwInflight[gw]) return _fixturesByGwInflight[gw];
  const p = apiCall("GET", `/fixtures?gw=${gw}`)
    .then(fixtures => {
      const byTeam = buildFixturesByTeam(fixtures);
      if (Object.keys(byTeam).length > 0) window.WC_FIXTURES_BY_GW[gw] = byTeam;
      return byTeam;
    })
    .finally(() => { delete _fixturesByGwInflight[gw]; });
  _fixturesByGwInflight[gw] = p;
  return p;
}
window.fetchFixturesByTeamForGw = fetchFixturesByTeamForGw;

// =====================================================================
// Platform-selector LOBBY — the home page after sign-in.
// The user explicitly chooses which league/platform to enter; no league is
// auto-selected, so the simulated showcase never overrides their real league.
// =====================================================================
function LobbyScreen({ leagues, loading, onEnter, onSignOut }) {
  const [mode, setMode] = React.useState("home"); // home | create | join

  const wrap = (inner) => (
    <div style={{
      minHeight: "100vh",
      background: "radial-gradient(circle at top left, #2a2080, #0c0a3e 70%)",
      color: "white", padding: "48px 20px"
    }}>
      <div style={{ maxWidth: 880, margin: "0 auto" }}>{inner}</div>
    </div>
  );

  if (mode === "create") {
    return wrap(
      <div className="col" style={{ gap: 16 }}>
        <button onClick={() => setMode("home")} style={{ background: "transparent", border: "none", color: "var(--green-400)", fontWeight: 700, cursor: "pointer", padding: 0, alignSelf: "flex-start" }}>← Back to platforms</button>
        <CreateForm onBack={() => setMode("home")} onTab={() => setMode("home")} />
      </div>
    );
  }
  if (mode === "join") {
    return wrap(
      <div className="col" style={{ gap: 16 }}>
        <button onClick={() => setMode("home")} style={{ background: "transparent", border: "none", color: "var(--green-400)", fontWeight: 700, cursor: "pointer", padding: 0, alignSelf: "flex-start" }}>← Back to platforms</button>
        <JoinForm onBack={() => setMode("home")} onTab={() => setMode("home")} />
      </div>
    );
  }

  const platformMeta = (l) => {
    const isSim = (l.simulated === true) || l.leagueId.includes("mock") || l.leagueId.includes("sim");
    if (isSim) return { tag: "Platform A · Simulated Showcase", color: "#a78bfa", note: "A finished demo season to explore the UI" };
    if (l.leagueId === "lg_pre_draft") return { tag: "Platform B · Live 7-Manager Draft", color: "var(--green-400)", note: "The real league with your friends" };
    return { tag: "Your League", color: "var(--gold-500)", note: "A league you created or joined" };
  };

  return wrap(
    <div className="col" style={{ gap: 28 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 className="h-display" style={{ fontSize: 32, margin: 0, letterSpacing: "-0.02em" }}>Choose your platform</h1>
          <p className="muted" style={{ fontSize: 14, marginTop: 6, color: "rgba(255,255,255,0.6)" }}>
            Each league is fully separate. Pick which one to manage — you can switch any time.
          </p>
        </div>
        {onSignOut && (
          <button onClick={onSignOut} style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "rgba(255,255,255,0.8)", fontWeight: 600, fontSize: 12, padding: "8px 14px", borderRadius: 8, cursor: "pointer" }}>Sign Out</button>
        )}
      </div>

      {loading ? (
        <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 14 }}>Loading your leagues…</div>
      ) : leagues.length === 0 ? (
        <div className="card-dark" style={{ padding: 28, borderRadius: 14, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}>
          <div className="h-display" style={{ fontSize: 20, marginBottom: 6 }}>No leagues yet</div>
          <div style={{ fontSize: 13, color: "rgba(255,255,255,0.65)" }}>Create a new league or join one with an invite code to get started.</div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 18 }}>
          {leagues.map(l => {
            const meta = platformMeta(l);
            return (
              <div key={l.leagueId} className="card-dark" style={{
                padding: 22, borderRadius: 14,
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderLeft: `4px solid ${meta.color}`,
                display: "flex", flexDirection: "column", gap: 14
              }}>
                <div>
                  <div style={{ fontSize: 11, color: meta.color, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>{meta.tag}</div>
                  <div className="h-display" style={{ fontSize: 22, marginTop: 6, color: "white" }}>{l.name}</div>
                  <div style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", marginTop: 4 }}>{meta.note}</div>
                  <div style={{ fontSize: 12, color: "rgba(255,255,255,0.7)", marginTop: 10 }}>
                    Status: <strong style={{ color: "white", textTransform: "capitalize" }}>{String(l.status || "").replace(/_/g, " ") || "—"}</strong>
                    {(l.memberCount != null || l.maxMembers != null) && <> · {l.memberCount ?? "?"}/{l.maxMembers ?? "?"} managers</>}
                  </div>
                </div>
                <button className="btn btn--primary" style={{ alignSelf: "flex-start", padding: "8px 18px", fontSize: 12, fontWeight: 700 }} onClick={() => onEnter(l.leagueId)}>
                  Enter platform →
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, maxWidth: 560 }}>
        <button className="card-dark" style={{ padding: 20, borderRadius: 12, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", color: "white", cursor: "pointer", textAlign: "left" }} onClick={() => setMode("create")}>
          <div className="h-display" style={{ fontSize: 16 }}>+ Create a league</div>
          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", marginTop: 4 }}>Start a new draft and invite friends</div>
        </button>
        <button className="card-dark" style={{ padding: 20, borderRadius: 12, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", color: "white", cursor: "pointer", textAlign: "left" }} onClick={() => setMode("join")}>
          <div className="h-display" style={{ fontSize: 16 }}>→ Join with code</div>
          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", marginTop: 4 }}>Enter an invite code to join</div>
        </button>
      </div>
    </div>
  );
}

function TweakDraftSimulator({ lid }) {
  const [active, setActive] = React.useState(false);
  const [status, setStatus] = React.useState("idle");
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!lid) return;
    let interval = null;
    const fetchState = async () => {
      try {
        const res = await apiCall("GET", `/leagues/${lid}/draft/sim/state`);
        if (res) {
          setActive(res.active);
          setStatus(res.status);
        }
      } catch (e) {
        console.warn("Failed to fetch simulator state:", e);
      }
    };

    fetchState();
    interval = setInterval(fetchState, 3000);
    return () => clearInterval(interval);
  }, [lid]);

  const handleToggle = async () => {
    if (!lid) return;
    setLoading(true);
    try {
      const nextActive = !active;
      const res = await apiCall("POST", `/leagues/${lid}/draft/sim/toggle`, { active: nextActive });
      if (res) {
        setActive(res.active);
        setStatus(res.status);
      }
    } catch (e) {
      alert("Error toggling simulator: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    if (!lid) return;
    if (!window.confirm("Are you sure you want to reset the draft state? This will wipe all picks and squads.")) return;
    setLoading(true);
    try {
      const res = await apiCall("POST", `/leagues/${lid}/draft/sim/reset`);
      if (res) {
        setActive(false);
        setStatus("idle");
        alert("Draft state has been reset successfully!");
      }
    } catch (e) {
      alert("Error resetting draft: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!lid) {
    return <div style={{ fontSize: 10, color: "rgba(41,38,27,0.5)" }}>Please enter a league first to access the simulator.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontWeight: 600 }}>Status:</span>
        <span style={{
          padding: "2px 6px",
          borderRadius: 4,
          fontSize: 9,
          fontWeight: 700,
          textTransform: "uppercase",
          background: active ? "rgba(43,240,148,0.15)" : "rgba(0,0,0,0.15)",
          color: active ? "#2bf094" : "inherit"
        }}>{active ? "Running" : status}</span>
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <button
          type="button"
          onClick={handleToggle}
          disabled={loading}
          className="twk-btn"
          style={{ flex: 1, height: 26, fontSize: 10, padding: 0 }}
        >
          {active ? "Pause Sim" : "Start Sim"}
        </button>
        <button
          type="button"
          onClick={handleReset}
          disabled={loading}
          className="twk-btn secondary"
          style={{ flex: 1, height: 26, fontSize: 10, padding: 0 }}
        >
          Reset Draft
        </button>
      </div>
    </div>
  );
}


function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [tab, setTab] = React.useState("status");

  // Auth States
  const [user, setUser] = React.useState(null);
  const [authLoading, setAuthLoading] = React.useState(true);
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [displayName, setDisplayName] = React.useState("");
  const [authError, setAuthError] = React.useState("");
  const [isSignUp, setIsSignUp] = React.useState(false);
  // The app boots straight into the single league — the mock-data showcase
  // (lg_mock_draft), which "transforms" into the real league once its data is
  // updated. There is no platform-chooser lobby any more: lg_mock_draft IS the
  // home/default. (No data syncs until `user` resolves — see the sync effect.)
  // ?lid=<leagueId> opens another league (e.g. lg_draft_test, the draft
  // rehearsal sandbox) without changing the default single-league experience.
  const [activeLid, setActiveLid] = React.useState(
    new URLSearchParams(window.location.search).get("lid") || "lg_mock_draft");
  const [myLeagues, setMyLeagues] = React.useState([]);
  const [leaguesLoading, setLeaguesLoading] = React.useState(true);
  const [viewingGw, setViewingGw] = React.useState(1);
  // Mock-simulator (admin Tweaks panel) busy flag — disables the buttons + shows
  // progress while a GW is generated server-side.
  const [simBusy, setSimBusy] = React.useState("");
  // False until the real /squads/me + lineup fetch resolves (success OR a
  // definitive "no squad" result). Gates the Pick Team render so an
  // authenticated user never sees the data.jsx demo squad flash before the
  // real one loads.
  const [squadLoaded, setSquadLoaded] = React.useState(false);

  React.useEffect(() => {
    window.VIEWING_GW = viewingGw;
    window.setViewingGw = setViewingGw;
  }, [viewingGw]);


  // Expose global league switch/refresh handlers
  React.useEffect(() => {
    window.setActiveLeagueId = setActiveLid;
    // The lobby is gone — there is only the one league. Any stray call just
    // keeps the user on the mock-data league rather than showing a chooser.
    window.goToLobby = () => setActiveLid("lg_mock_draft");
    // Re-fetch the user's league list WITHOUT auto-selecting one. Callers that
    // want to enter a specific league (create/join) call setActiveLeagueId themselves.
    window.refreshActiveLeague = async () => {
      try {
        const list = await apiCall("GET", "/leagues/my");
        setMyLeagues(list || []);
      } catch (e) {
        console.warn("Failed to refresh leagues", e);
      }
    };
  }, []);

  // Monitor Auth state changes
  React.useEffect(() => {
    return _auth.onAuthStateChanged(async (u) => {
      if (u) {
        setUser(u);
        try {
          // Sync profile
          try {
            await apiCall("POST", "/auth/me", {
              displayName: u.displayName || u.email.split("@")[0],
              photoUrl: ""
            });
          } catch (e) {
            console.warn("POST /auth/me profile sync failed, continuing", e);
          }

          // Fetch my leagues for the platform-selector lobby. We do NOT
          // auto-select a league: the user picks which platform to enter from
          // the home page, so the simulated showcase never silently overrides
          // their real league.
          const list = await apiCall("GET", "/leagues/my");
          setMyLeagues(list || []);
        } catch (e) {
          console.warn("Failed to fetch leagues in auth sync", e);
        } finally {
          setLeaguesLoading(false);
        }
      } else {
        setUser(null);
      }
      setAuthLoading(false);
    });
  }, []);

  const handleSignIn = async (e) => {
    e.preventDefault();
    setAuthError("");
    try {
      await _auth.signInWithEmailAndPassword(email, password);
    } catch (err) {
      setAuthError(err.message || "Failed to sign in");
    }
  };

  const handleSignUp = async (e) => {
    e.preventDefault();
    setAuthError("");
    try {
      const cred = await _auth.createUserWithEmailAndPassword(email, password);
      if (cred.user && displayName) {
        await cred.user.updateProfile({ displayName });
        setUser({ ...cred.user, displayName });
      }
    } catch (err) {
      setAuthError(err.message || "Failed to sign up");
    }
  };

  const [updateKey, setUpdateKey] = React.useState(0);
  const forceUpdate = () => setUpdateKey(k => k + 1);

  // Firestore & API dynamic synchronization
  React.useEffect(() => {
    if (!user) return;
    // No league selected yet → we're on the platform-selector lobby. Don't sync
    // any per-league data (this is what keeps the two platforms isolated).
    if (!activeLid) return;

    // Update ME global variable to logged-in user's UID
    window.__AUTH_UID = user.uid;
    window.ME = user.uid;
    // Mock-only "view as manager" override (admin demo tool): view the showcase
    // league as any member without separate logins. Reverted below if the saved
    // override isn't a member of the loaded league; cleared via the Tweaks panel.
    try { const _m = localStorage.getItem("wc_mock_me"); if (_m) window.ME = _m; } catch (e) { /* ignore */ }
    try { ME = window.ME; } catch(e) {}

    // New league / GW: hide the squad until the real fetch resolves so we never
    // flash the demo squad seeded by data.jsx.
    setSquadLoaded(false);

    const lid = activeLid; // active league ID

    // 1. Standings — fetched via the API (→ gamedb), NOT a direct client
    // onSnapshot. The compat Firestore SDK can't select the named "gamedb"
    // database (it silently reads an empty "(default)"), which left the table
    // empty/falling back to demo data. The API targets gamedb for both the live
    // GW (/standings → current doc) and a past GW (?gw=N → that snapshot).
    let stdCancelled = false;
    const unsubStandings = () => { stdCancelled = true; };
    const curGw = window.TOURNAMENT.currentGw || 1;
    const _stdPath = (viewingGw === curGw)
      ? `/leagues/${lid}/standings`
      : `/leagues/${lid}/standings?gw=${viewingGw}`;
    apiCall("GET", _stdPath)
      .then(data => {
        if (stdCancelled) return;
        if (data && data.managers) {
          window.STANDINGS = data.managers.map(m => ({
            uid: m.uid,
            rank: m.rank || 1,
            hw: m.hw || 0,
            hd: m.hd || 0,
            hl: m.hl || 0,
            hpts: m.hpts || 0,
            fpts: m.fpts || 0,
            mv: m.mv || 0,
            bonusPoints: m.bonusPoints || 0,
            knockedOut: m.knockedOut || false,
            ptsSeed: m.ptsSeed || false,
          })).sort((a, b) => a.rank - b.rank);
        } else {
          window.STANDINGS = [];
        }
        forceUpdate();
      })
      .catch(err => { if (!stdCancelled) console.error("Standings fetch error:", err); });

    // 2. Scores / GW totals — via the API (→ gamedb), same reason as standings.
    // One endpoint serves both the live and past GW; an unfinalized/empty GW
    // returns no results, which clears GW3_TOTALS (so a previous league's totals
    // never persist after a switch).
    let scoresCancelled = false;
    const unsubScores = () => { scoresCancelled = true; };
    apiCall("GET", `/leagues/${lid}/scores/${viewingGw}`)
      .then(data => {
        if (scoresCancelled) return;
        window.GW3_TOTALS = {};
        if (data && data.results) {
          Object.entries(data.results).forEach(([uid, res]) => {
            window.GW3_TOTALS[uid] = res.points || 0;
          });
        }
        forceUpdate();
      })
      .catch(err => { if (!scoresCancelled) { window.GW3_TOTALS = {}; console.error("Scores fetch error:", err); } });

    // 3. Sync Draft State live
    const unsubDraft = _db.collection("leagues").doc(lid)
      .collection("draft").doc("state")
      .onSnapshot((doc) => {
        if (doc.exists) {
          const data = doc.data();
          const numMembers = data.order ? data.order.length : 10;
          let currentDrafter = data.currentDrafter;
          if (!currentDrafter && data.order && typeof data.currentPick === 'number') {
            const pick = data.currentPick;
            const rnd = Math.floor(pick / numMembers);
            const pos = pick % numMembers;
            currentDrafter = (rnd % 2 === 0) ? data.order[pos] : data.order[numMembers - 1 - pos];
          }
          window.DRAFT_STATE = {
            round: data.currentPick ? Math.floor(data.currentPick / numMembers) + 1 : 1,
            pickOverall: (data.currentPick || 0) + 1,
            pickInRound: ((data.currentPick || 0) % numMembers) + 1,
            onTheClock: currentDrafter || "",
            totalRounds: 15,
            totalPicks: data.totalPicks || 150,
            pickTimer: data.pickTimer || 30,
            secondsLeft: Math.max(0, Math.round((data.pickDeadline || 0) - Date.now() / 1000)),
            isMyTurn: currentDrafter === user.uid,
            order: data.order || [],
            paused: !!data.paused,
          };
          forceUpdate();
        } else {
          // No draft has been created for this league (e.g. a pre_draft league).
          // Clear DRAFT_STATE so we never render a stale/other league's draft.
          window.DRAFT_STATE = {
            round: 0, pickOverall: 0, pickInRound: 0, onTheClock: "",
            totalRounds: 15, totalPicks: 0, pickTimer: 0, secondsLeft: 0,
            isMyTurn: false, notStarted: true,
            order: [],
            paused: false,
          };
          forceUpdate();
        }
      }, (err) => console.error("Draft state listen error:", err));

    // 4. Sync Draft Picks history live
    const unsubDraftPicks = _db.collection("leagues").doc(lid)
      .collection("draft").doc("state")
      .collection("picks").orderBy("pickNumber")
      .onSnapshot((snap) => {
        window.DRAFT_HISTORY = snap.docs.map(doc => {
          const d = doc.data();
          return {
            round: d.round,
            overall: d.pickNumber + 1,
            uid: d.uid,
            playerId: String(d.playerId),
          };
        });
        forceUpdate();
      }, (err) => console.error("Draft picks listen error:", err));

    // 4b. Draft state POLL (REST). The compat SDK silently ignores the named-
    // database arg (firestore("gamedb") -> "(default)"), so the two listeners
    // above receive NOTHING in production. This poll is the real live-update
    // path for the draft: one GET returns state + picks; it also nudges bot
    // picks forward via /draft/sim/advance when a bot is on the clock (only
    // the first human does the nudging so concurrent clients don't race).
    let draftPollBusy = false, advanceBusy = false, lastDraftSig = "";
    const draftPoll = setInterval(async () => {
      if (draftPollBusy || !user) return;
      draftPollBusy = true;
      try {
        const s = await apiCall("GET", `/leagues/${lid}/draft/state`);
        if (!s || s.status === "pending" || !s.order || !s.order.length) return;
        const numMembers = s.order.length;
        const sig = `${s.currentPick}|${s.status}|${s.paused}|${Math.round(s.pickDeadline || 0)}`;
        window.DRAFT_STATE = {
          round: Math.floor((s.currentPick || 0) / numMembers) + 1,
          pickOverall: (s.currentPick || 0) + 1,
          pickInRound: ((s.currentPick || 0) % numMembers) + 1,
          onTheClock: s.currentDrafter || "",
          totalRounds: 15,
          totalPicks: s.totalPicks || 0,
          pickTimer: s.pickTimer || 30,
          secondsLeft: Math.max(0, Math.round((s.pickDeadline || 0) - Date.now() / 1000)),
          isMyTurn: s.currentDrafter === user.uid,
          order: s.order,
          paused: !!s.paused,
          humanUids: s.humanUids || [],
          complete: s.status === "complete",
          // The auto-pick watchdog gates on these two — without them the
          // timeout pick can never fire.
          status: s.status,
          pickDeadline: s.pickDeadline,
        };
        window.DRAFT_HISTORY = (s.picks || []).map(d => ({
          round: d.round, overall: (d.pickNumber || 0) + 1,
          uid: d.uid, playerId: String(d.playerId),
        }));
        if (sig !== lastDraftSig) { lastDraftSig = sig; forceUpdate(); }
        else forceUpdate(); // clock re-sync is cheap; keep the countdown honest
        // Bot nudge: first human in humanUids drives the bots forward.
        const humans = s.humanUids || [];
        if (s.status === "active" && !s.paused && humans.length &&
            user.uid === humans[0] && s.currentDrafter &&
            !humans.includes(s.currentDrafter) && !advanceBusy) {
          advanceBusy = true;
          try { await apiCall("POST", `/leagues/${lid}/draft/sim/advance`, { count: 1 }); }
          catch (e) { /* not a sim league / race — fine */ }
          finally { advanceBusy = false; }
        }
      } catch (e) {
        // 404 = no draft yet; network blips are retried next tick.
      } finally {
        draftPollBusy = false;
      }
    }, 2500);

    // 5. Initial HTTP fetches (Bracket, Schedule, Squad, Lineup, Players)
    const loadInitialData = async () => {
      let criticalFailed = false;
      // Declared at function scope (not inside the league-details block) so the
      // players / free-agents / scores fetches below can read them. The backend
      // (api-sports) is the source of truth for country codes: players' teamIso,
      // manager flags and the /teams isoCode all use the SAME raw codes (e.g.
      // SPA, JAP, MOR, AUT, TUR). Pass them through unchanged — window.TEAM_MAP
      // resolves name/group/flag/elimination for every nation.
      let leagueDetails = null;
      const normalizeIso = iso => (iso ? String(iso).toUpperCase() : "GER");
      try {
        // Fetch gameweeks — tournament-global, so load once per session. A
        // league switch or GW change must not re-pull (and risk a transient
        // failure on) data that never changes between leagues.
        if (!window.__GW_LOADED__)
        try {
          const gws = await apiCall("GET", "/gameweeks");
          if (gws && gws.length > 0) {
            window.__GW_LOADED__ = true;
            window.TOURNAMENT.gwDates = {};
            const formatIso = (isoStr) => {
              if (!isoStr) return "";
              const d = new Date(isoStr);
              const months = ["Jun", "Jul"];
              const m = months[d.getUTCMonth() - 5] || "Jun";
              const date = d.getUTCDate();
              const hrs = String(d.getUTCHours()).padStart(2, '0');
              const mins = String(d.getUTCMinutes()).padStart(2, '0');
              return `${m} ${date} ${hrs}:${mins}`;
            };
            const formatDateOnly = (isoStr) => {
              if (!isoStr) return "";
              const d = new Date(isoStr);
              const months = ["Jun", "Jul"];
              const m = months[d.getUTCMonth() - 5] || "Jun";
              const date = d.getUTCDate();
              return `${m} ${date}`;
            };
            gws.forEach(g => {
              window.TOURNAMENT.gwDates[g.gw] = {
                wcRound: g.wcRound || g.label,
                start: formatDateOnly(g.start),
                end: formatDateOnly(g.end),
                lockAt: formatIso(g.lockAt)
              };
            });
          }
        } catch (e) {
          console.warn("Failed to fetch gameweeks", e);
        }

        // Fetch active league details
        try {
          leagueDetails = await apiCall("GET", `/leagues/${lid}`);
          if (leagueDetails) {
            window.TOURNAMENT.currentGw = leagueDetails.currentGw || 1;
            window.TOURNAMENT.status = leagueDetails.status || "pre_draft";

            if (window.LAST_ACTIVE_LID !== lid) {
              window.LAST_ACTIVE_LID = lid;
              // Default to the latest GW. After a mock "Simulate next GW" we pin
              // the just-played GW so the reload lands on the result you just
              // generated, not the next (empty) GW.
              let initGw = leagueDetails.currentGw || 1;
              try {
                const pinned = localStorage.getItem("wc_view_gw_after_reload");
                if (pinned) { initGw = Number(pinned); localStorage.removeItem("wc_view_gw_after_reload"); }
              } catch (e) { /* ignore */ }
              setViewingGw(initGw);
            }

            window.LEAGUE = {
              id: leagueDetails.leagueId,
              name: leagueDetails.name,
              inviteCode: leagueDetails.inviteCode,
              // Rank denominator = actual managers in the league, not the max
              // capacity (#48: "Rank #N / 8" while 10 are enrolled).
              size: leagueDetails.memberCount || leagueDetails.maxMembers,
              knockoutStartGw: leagueDetails.knockoutStartGw,
              leaguePhaseGws: leagueDetails.leaguePhaseGws,
              knockoutQualifiers: leagueDetails.knockoutQualifiers,
              pickTimer: leagueDetails.pickTimer,
              tradeApproval: leagueDetails.tradeApproval,
              admin: leagueDetails.adminUid,
              simulated: !!leagueDetails.simulated,
            };

            if (leagueDetails.members) {
              window.MANAGERS = leagueDetails.members.map(m => ({
                uid: m.uid,
                name: m.displayName || m.uid.substring(0, 8),
                team: m.teamName || "Unnamed Team",
                flag: normalizeIso(m.flag),
                draftPos: m.draftPosition || 99,
                waiverPri: m.waiverPriority || 99,
              }));
              // Revert a stale "view as manager" override if it isn't a member
              // of this league (e.g. after switching leagues).
              if (window.ME !== window.__AUTH_UID && !window.MANAGERS.some(mm => mm.uid === window.ME)) {
                window.ME = window.__AUTH_UID;
                try { ME = window.__AUTH_UID; } catch (e) {}
              }
            } else {
              // No members returned → clear so a previous league's managers
              // (or the data.jsx demo roster) can never bleed through.
              window.MANAGERS = [];
            }
          } else {
            criticalFailed = true;
          }
        } catch (e) {
          console.warn("Failed to fetch league details, using mock defaults", e);
          // A dead ?lid (e.g. a bookmarked sandbox league that was deleted)
          // must not strand the app on demo data — strip the param and fall
          // back to the home league.
          if (lid !== "lg_mock_draft" &&
              new URLSearchParams(window.location.search).get("lid") === lid) {
            console.warn(`League ${lid} unavailable — falling back to lg_mock_draft`);
            window.history.replaceState({}, "", window.location.pathname);
            setActiveLid("lg_mock_draft");
            return;
          }
          // Only flag the app as "down" if we have no previously-loaded league
          // for this id. A transient blip on a re-run must not wipe the league
          // the user is already viewing.
          if (!window.LEAGUE || window.LAST_ACTIVE_LID !== lid) criticalFailed = true;
        }

        // Fetch the authoritative team list (names, groups, elimination,
        // crests) keyed by the backend's raw ISO codes — the same codes used by
        // players and manager flags. This replaces the hardcoded placeholder
        // bracket so all 48 nations resolve correctly. A failure here is
        // non-critical: teamById falls back to the static map.
        if (!window.__TEAMS_LOADED__)
        try {
          const teams = await apiCall("GET", "/teams");
          if (teams && teams.length > 0) {
            window.__TEAMS_LOADED__ = true;
            const staticMap = (typeof TEAM_MAP !== "undefined") ? TEAM_MAP : {};
            const merged = {};
            teams.forEach(t => {
              const iso = (t.isoCode || t.short_name || "").toUpperCase();
              if (!iso) return;
              const base = staticMap[iso] || {};
              merged[iso] = {
                ...base,
                id: iso,
                name: t.name || base.name || iso,
                grp: t.group || base.grp || "?",
                elim: (t.eliminated !== undefined ? t.eliminated : base.elim) || false,
                logo: t.logo || base.logo,
              };
            });
            window.TEAM_MAP = merged;
            window.TEAMS = Object.values(merged);
          }
        } catch (e) {
          console.warn("Failed to fetch teams; falling back to static team map", e);
        }

        // Fetch players list — global pool, load once per session.
        if (!window.__PLAYERS_LOADED__)
        try {
          const players = await apiCall("GET", "/players");
          if (players && players.length > 0) {
            window.__PLAYERS_LOADED__ = true;
            window.PLAYERS = players
              // Defensive: drop any malformed pool entry (no real id or no
              // position). The backend already filters these, but this guards
              // against junk wc_players docs ever reaching the draft pool, where
              // they'd render as "UNDEFINED / Group ?" rows with a duplicate
              // String(undefined) React key.
              .filter(p => p && p.id != null && String(p.id) !== "undefined" && p.position != null)
              .map(p => ({
              id: String(p.id),
              name: p.name,
              pos: p.position,
              team: normalizeIso(p.teamIso || p.teamShort || String(p.teamId)),
              teamName: p.teamName || "",
              club: p.club || "",
              pts: p.totalPoints || 0,
              dr: p.draftRank || 999,
            }));
            window.PLAYER_MAP = Object.fromEntries(window.PLAYERS.map(p => [p.id, p]));

            // Dynamically populate GW3_POINTS from players total points in mock database!
            window.GW3_POINTS = {};
            window.PLAYERS.forEach(p => {
              window.GW3_POINTS[p.id] = p.pts;
            });
          } else if (!window.PLAYERS || !window.PLAYERS.length) {
            // Server gave us nothing AND we have no prior pool → genuinely down.
            criticalFailed = true;
          }
        } catch (e) {
          console.warn("Failed to fetch players", e);
          // Transient network failure: only fatal if we never loaded a pool.
          // A blip on a re-run must not blank an app that already has players.
          if (!window.PLAYERS || !window.PLAYERS.length) criticalFailed = true;
        }

        // Fetch bracket matching viewingGw
        try {
          const bracket = await apiCall("GET", `/leagues/${lid}/knockout?gw=${viewingGw}`);
          if (bracket) {
            const roundsSource = bracket.rounds || bracket;
            const parsedSf = (roundsSource.sf || []).map(m => ({
              id: m.id,
              home: m.home,
              away: m.away,
              homeSeed: m.homeSeed,
              awaySeed: m.awaySeed,
              gw: m.gw,
            }));

            let parsedFinal = [];
            if (roundsSource.final) {
              const finalItems = Array.isArray(roundsSource.final) ? roundsSource.final : [roundsSource.final];
              parsedFinal = finalItems.filter(Boolean).map(m => ({
                id: m.id,
                home: m.home,
                away: m.away,
                homeSrc: m.homeSrc,
                awaySrc: m.awaySrc,
                gw: m.gw,
              }));
            }

            window.BRACKET = {
              sf: parsedSf,
              final: parsedFinal,
            };
          } else {
            window.BRACKET = { sf: [], final: [] };
          }
        } catch(e) {
          console.warn("Knockout bracket not seeded yet", e);
          window.BRACKET = { sf: [], final: [] };
        }

        // Fetch Schedule
        try {
          const schedule = await apiCall("GET", `/leagues/${lid}/schedule`);
          if (schedule && schedule.schedule && schedule.schedule.length > 0) {
            window.SCHEDULE = {};
            schedule.schedule.forEach(g => {
              window.SCHEDULE[g.gw] = (g.matches || []).map(m => [m.home, m.away]);
            });
          } else {
            // No schedule yet (pre-draft / pre-season). Don't fall back to mock.
            window.SCHEDULE = {};
          }
        } catch (e) {
          console.warn("Failed to fetch schedule", e);
        }

        // Fetch real per-team fixtures for the viewing GW so Pick Team can show
        // each player's "v OPP" from live data instead of the static
        // WC_FIXTURES_GW4 round. Keyed by the same iso the players use
        // (backend resolves homeTeam/awayTeam isoCode from the team map).
        try {
          // Build the by-team map for the viewed GW. If that GW has no fixtures
          // yet (e.g. the mock sits at currentGw=4/knockout but only GW1-3 are
          // scheduled), walk back to the most recent GW that DOES have fixtures
          // so every active player still shows a real opponent instead of "—".
          // There is no static fallback any more — an empty map just yields "—".
          // Each fetched round also lands in the per-GW cache
          // (window.WC_FIXTURES_BY_GW) that Pick Team uses for its edit GW.
          let byTeam = {};
          for (let g = viewingGw; g >= 1; g--) {
            byTeam = await fetchFixturesByTeamForGw(g);
            if (Object.keys(byTeam).length > 0) break;
          }
          window.WC_FIXTURES_BY_TEAM = byTeam;
        } catch (e) {
          console.warn("Failed to fetch per-team fixtures", e);
          // Keep any previously-loaded map; an empty map just renders "—".
          if (!window.WC_FIXTURES_BY_TEAM) window.WC_FIXTURES_BY_TEAM = {};
        }

        // Fetch my Squad
        try {
          const squad = await apiCall("GET", `/leagues/${lid}/squads/${window.ME}`);
          if (squad && squad.players && squad.players.length > 0) {
            window.MY_SQUAD_IDS = squad.players.map(p => String(p.playerId));
          } else {
            // No squad yet (draft not complete). Don't show the mock squad.
            window.MY_SQUAD_IDS = [];
          }
        } catch (e) {
          console.warn("Failed to fetch my squad", e);
        }

        // Fetch every manager's squad so ownership can be resolved across the
        // whole league (Player Browser "Owned by", Transfers free-agent gating).
        // Without this, only ME's squad is known and every other manager's
        // players render as "Free agent". Reuses the same per-uid squad
        // endpoint the Manager Squad modal already calls. Failures per-manager
        // are non-fatal; we keep whatever resolved.
        try {
          const squadsByUid = {};
          await Promise.all((window.MANAGERS || []).map(async (m) => {
            if (!m || !m.uid) return;
            try {
              const res = m.uid === window.ME
                ? { players: (window.MY_SQUAD_IDS || []).map(playerId => ({ playerId })) }
                : await apiCall("GET", `/leagues/${lid}/squads/${m.uid}`);
              squadsByUid[m.uid] = (res.players || []).map(p => String(p.playerId));
            } catch (e) {
              // Leave this manager's squad unknown rather than failing the batch.
              squadsByUid[m.uid] = squadsByUid[m.uid] || [];
            }
          }));
          window.SQUADS_BY_UID = squadsByUid;
        } catch (e) {
          console.warn("Failed to fetch all-manager squads", e);
          if (!window.SQUADS_BY_UID) window.SQUADS_BY_UID = {};
        }

        // Fetch the lineup for the VIEWED manager matching viewingGw.
        // IMPORTANT: your OWN team must use the auth endpoint (/lineup/<gw>).
        // The /lineup/<uid>/<gw> form treats ANY uid as an opponent and 403s an
        // unlocked GW — even for yourself — so using it for your own team blanks
        // the pitch (and falls back to the data.jsx demo roster). Only the
        // "view as another manager" override uses the target form; when that's
        // blocked (live GW) or empty, derive a shape from THEIR squad instead of
        // showing the demo roster.
        const _ownLineup = window.ME === window.__AUTH_UID;
        const _lineupFromSquad = () => {
          const byPos = { 1: [], 2: [], 3: [], 4: [] };
          (window.MY_SQUAD_IDS || []).forEach(id => {
            const p = playerById(isNaN(Number(id)) ? id : Number(id));
            if (p && byPos[p.pos]) byPos[p.pos].push(String(id));
          });
          const nd = Math.min(byPos[2].length, 4), nm = Math.min(byPos[3].length, 4), nf = Math.min(byPos[4].length, 2);
          const starting = [...byPos[1].slice(0, 1), ...byPos[2].slice(0, nd), ...byPos[3].slice(0, nm), ...byPos[4].slice(0, nf)];
          const bench = [...byPos[1].slice(1), ...byPos[2].slice(nd), ...byPos[3].slice(nm), ...byPos[4].slice(nf)];
          return { starting, bench, formation: [1, nd, nm, nf], autoSubs: [] };
        };
        try {
          const lineup = await apiCall("GET", _ownLineup
            ? `/leagues/${lid}/lineup/${viewingGw}`
            : `/leagues/${lid}/lineup/${window.ME}/${viewingGw}`);
          if (lineup && lineup.starting && lineup.starting.length > 0) {
            window.MY_LINEUP_GW3 = {
              starting: (lineup.starting || []).map(String),
              bench: (lineup.bench || []).map(String),
              formation: lineup.formation || [1, 4, 4, 2],
              autoSubs: lineup.autoSubsMade || [],
            };
          } else {
            window.MY_LINEUP_GW3 = _lineupFromSquad();
          }
        } catch (e) {
          console.warn("Failed to fetch my lineup", e);
          if (e && e.status === 403) {
            // Viewing another manager's pre-lock lineup is blocked → show their
            // squad in a default shape, never the demo roster.
            window.MY_LINEUP_GW3 = _lineupFromSquad();
          } else if (!(window.MY_LINEUP_GW3 && window.MY_LINEUP_GW3.starting && window.MY_LINEUP_GW3.starting.length)) {
            // Transient failure with nothing cached yet → derive from the squad.
            window.MY_LINEUP_GW3 = _lineupFromSquad();
          }
          // else: keep last-known-good (transient-network resilience).
        }

        // Real squad + lineup have now resolved (success OR a definitive
        // "no squad" result). Reveal the Pick Team squad area.
        setSquadLoaded(true);

        // Fetch transfer window
        try {
          const winData = await apiCall("GET", `/leagues/${lid}/transfer-window`);
          if (winData) {
            window.WINDOW = {
              hoursLeft: winData.status === "open" ? 36 : 0,
              freeTransfers: 2,
              used: 0,
              state: winData.status,
              phase: winData.window ? winData.window.phase : "none",
              gw: winData.window ? winData.window.gw : null,
              overridden: !!winData.overridden,
              windowNumber: winData.window ? winData.window.windowNumber : 1
            };
          }
        } catch (e) {
          console.warn("Failed to fetch transfer window", e);
        }

        // Fetch admin flag (UI gating only — backend still enforces).
        try {
          const adminRes = await apiCall("GET", "/me/admin");
          window.IS_ADMIN = !!(adminRes && adminRes.isAdmin);
        } catch (e) {
          window.IS_ADMIN = false;
          console.warn("Failed to fetch admin flag", e);
        }

        // Fetch free agents
        try {
          const fa = await apiCall("GET", `/leagues/${lid}/free-agents`);
          if (fa && fa.length > 0) {
            window.FREE_AGENTS = fa.map(p => ({
              id: String(p.id),
              name: p.name,
              pos: p.position,
              team: p.teamIso || p.teamShort || String(p.teamId),
              teamName: p.teamName || "",
              club: p.club || "",
              pts: p.totalPoints || 0,
              dr: p.draftRank || 999,
            }));
          } else {
            window.FREE_AGENTS = [];
          }
        } catch (e) {
          console.warn("Failed to fetch free agents", e);
        }

        // Fetch active waivers
        try {
          const wav = await apiCall("GET", `/leagues/${lid}/waivers`);
          if (wav && wav.length > 0) {
            window.MY_WAIVERS = wav.map(w => ({
              id: w.waiverId || w.id,
              playerIn: String(w.playerIn),
              playerOut: String(w.playerOut),
              priority: w.priority || 4,
              gw: w.gw || curGw,
              status: w.status || "pending"
            }));
          }
        } catch (e) {
          console.warn("Failed to fetch active waivers", e);
        }

        // Fetch my wishlist bids for the upcoming GW (drives the Wishlist tab /
        // the batch auction). The upcoming GW comes from the transfer window.
        window.MY_WISHLIST_BIDS = [];
        try {
          // The bid GW is the open window's GW when one is open, else the next
          // GW to be played — so the wishlist loads/persists even while the
          // window is closed (you queue free agents ahead of the next window).
          const wgw = (window.WINDOW && window.WINDOW.gw) ||
                      (window.TOURNAMENT && window.TOURNAMENT.currentGw);
          if (wgw) {
            const wl = await apiCall("GET", `/leagues/${lid}/wishlist-bids/me?gw=${wgw}`);
            if (wl && Array.isArray(wl.bids)) {
              window.MY_WISHLIST_BIDS = wl.bids;
            }
          }
        } catch (e) {
          console.warn("Failed to fetch wishlist bids", e);
        }

        // Fetch trades — split into inbox (offers TO me) and sent (offers FROM
        // me). Without this the Trades screen rendered the data.jsx demo consts
        // (TRADES_INBOX/TRADES_OUTBOX), i.e. the "Player zielinski / messi"
        // placeholder cards.
        try {
          const trades = await apiCall("GET", `/leagues/${lid}/trades`);
          const fmtAgo = (ts) => {
            if (!ts) return "";
            const d = new Date(ts);
            if (isNaN(d.getTime())) return "";
            const mins = Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
            if (mins < 60) return mins + "m ago";
            const hrs = Math.floor(mins / 60);
            if (hrs < 24) return hrs + "h ago";
            return Math.floor(hrs / 24) + "d ago";
          };
          const mapTrade = (t) => ({
            id: t.tradeId || t.id,
            proposer: t.proposerUid,
            target: t.targetUid,
            proposerPlayers: (t.proposerPlayers || []).map(p => String(p.playerId)),
            targetPlayers: (t.targetPlayers || []).map(p => String(p.playerId)),
            status: t.status,
            createdAt: fmtAgo(t.createdAt),
            message: t.message || "",
          });
          const pending = (trades || []).filter(t => t.status === "pending").map(mapTrade);
          window.TRADES_INBOX = pending.filter(t => t.target === window.ME);
          window.TRADES_OUTBOX = pending.filter(t => t.proposer === window.ME);
        } catch (e) {
          console.warn("Failed to fetch trades", e);
          window.TRADES_INBOX = [];
          window.TRADES_OUTBOX = [];
        }

        // Fetch all gameweek scores
        window.ALL_GW_SCORES = {};
        try {
          const gws = leagueDetails?.leaguePhaseGws || [1, 2, 3, 4, 5, 6];
          await Promise.all(gws.map(async (gw) => {
            try {
              const scoreData = await apiCall("GET", `/leagues/${lid}/scores/${gw}`);
              if (scoreData && scoreData.results) {
                window.ALL_GW_SCORES[gw] = {};
                Object.entries(scoreData.results).forEach(([uid, res]) => {
                  window.ALL_GW_SCORES[gw][uid] = res.points || 0;
                });
              }
            } catch (e) {
              // ignore unplayed GWs
            }
          }));
        } catch (e) {
          console.warn("Failed to fetch all gameweek scores", e);
        }

        if (criticalFailed) {
          setDataSource("down");
        } else if (leagueDetails && leagueDetails.simulated === true) {
          // The backend marks each league explicitly: Platform A (mock) carries
          // simulated:true, the real 7-player draft carries simulated:false.
          setDataSource("simulated");
        } else {
          setDataSource("live");
        }
        forceUpdate();
      } catch (err) {
        console.error("Failed to load initial live data:", err);
        setDataSource("down");
        // Don't strand the Pick Team screen on the skeleton forever if the
        // bootstrap threw before the squad fetch ran.
        setSquadLoaded(true);
        forceUpdate();
      }
    };

    loadInitialData();

    return () => {
      unsubStandings();
      unsubScores();
      unsubDraft();
      unsubDraftPicks();
      clearInterval(draftPoll);
    };
  }, [user, activeLid, viewingGw]);

  // Apply theme accent via CSS custom props
  React.useEffect(() => {
    const theme = ACCENT_THEMES[t.themeAccent] || ACCENT_THEMES.wc;
    document.documentElement.style.setProperty("--grad-hero", theme.grad);
    document.documentElement.style.setProperty("--grad-pill-active", theme.pill);
  }, [t.themeAccent]);


  const renderScreen = () => {
    switch (tab) {
      case "status":    return <StatusScreen onTab={setTab} />;
      case "points":    return <PointsScreen onTab={setTab} />;
      case "pickteam":  return <PickTeamScreen onTab={setTab} squadLoading={!!user && !squadLoaded} />;
      case "transfers": return <TransfersScreen onTab={setTab} />;
      case "league":    return <LeagueScreen onTab={setTab} />;
      case "bracket":   return <BracketScreen onTab={setTab} />;
      case "fixtures":  return <FixturesScreen onTab={setTab} />;
      case "draft":     return <DraftRoomScreen onTab={setTab} />;
      case "players":   return <PlayerBrowserScreen onTab={setTab} />;
      case "trades":    return <TradesScreen onTab={setTab} />;
      case "create":    return <CreateLeagueScreen onTab={setTab} />;
      case "config":    return <ConfigScreen onTab={setTab} />;
      default:          return <StatusScreen onTab={setTab} />;
    }
  };

  // Use wide layout (no sidebar) on Draft, Bracket, Create, Fixtures pages
  const wideTabs = ["draft", "bracket", "create", "fixtures"];
  const isWide = wideTabs.includes(tab);

  if (authLoading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", background: "#0c0a3e", color: "white" }}>
        <div style={{ textAlign: "center" }}>
          <div className="mono" style={{ fontSize: 20, fontWeight: 800, marginBottom: 12 }}>Loading WC26...</div>
          <div style={{ width: 40, height: 40, border: "4px solid rgba(255,255,255,0.1)", borderTop: "4px solid var(--green-400)", borderRadius: "50%", margin: "0 auto", animation: "spin 1s linear infinite" }} />
          <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div style={{
        display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh",
        background: "radial-gradient(circle at top left, #2a2080, #0c0a3e 70%)",
        color: "white", padding: 20
      }}>
        <div className="card-dark" style={{
          width: "100%", maxWidth: 440, padding: 36, borderRadius: 20,
          background: "rgba(255, 255, 255, 0.03)",
          backdropFilter: "blur(20px)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          boxShadow: "0 24px 64px rgba(0,0,0,0.4)"
        }}>
          <div style={{ textAlign: "center", marginBottom: 28 }}>
            <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" style={{ width: 80, height: 80, margin: "0 auto 12px" }}>
              <defs>
                <linearGradient id="logo-bg" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stop-color="#4a1ba8"/>
                  <stop offset="0.5" stop-color="#3a2db8"/>
                  <stop offset="1" stop-color="#1be8d4"/>
                </linearGradient>
              </defs>
              <rect width="200" height="200" rx="44" fill="url(#logo-bg)"/>
              <path d="M70 60h60v18a30 30 0 0 1-60 0V60Z" fill="#ffc844"/>
              <text x="100" y="83" text-anchor="middle" fill="#fff" font-family="Bricolage Grotesque" font-weight="800" font-size="18">26</text>
            </svg>
            <h1 className="h-display" style={{ fontSize: 28, margin: 0, letterSpacing: "-0.02em" }}>WC26 Fantasy Draft</h1>
            <p className="muted" style={{ fontSize: 13, marginTop: 4, color: "rgba(255,255,255,0.6)" }}>
              {isSignUp ? "Create a new manager profile" : "Sign in to manage your squad"}
            </p>
          </div>

          <form onSubmit={isSignUp ? handleSignUp : handleSignIn} className="col" style={{ gap: 16 }}>
            {authError && (
              <div style={{ background: "rgba(230,57,70,0.18)", color: "#ff6b8b", padding: "10px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600, border: "1px solid rgba(230,57,70,0.3)" }}>
                ⚠ {authError}
              </div>
            )}

            {isSignUp && (
              <div>
                <label style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "rgba(255,255,255,0.6)", display: "block", marginBottom: 6 }}>Display Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Roy Koopa"
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  className="input-field"
                  style={{ width: "100%", padding: "12px 14px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.06)", color: "white" }}
                />
              </div>
            )}

            <div>
              <label style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "rgba(255,255,255,0.6)", display: "block", marginBottom: 6 }}>Email Address</label>
              <input
                type="email"
                required
                placeholder="you@domain.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="input-field"
                style={{ width: "100%", padding: "12px 14px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.06)", color: "white" }}
              />
            </div>

            <div>
              <label style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "rgba(255,255,255,0.6)", display: "block", marginBottom: 6 }}>Password</label>
              <input
                type="password"
                required
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="input-field"
                style={{ width: "100%", padding: "12px 14px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.06)", color: "white" }}
              />
            </div>

            <button type="submit" className="btn btn--primary" style={{ padding: 14, fontSize: 13, fontWeight: 700, width: "100%", marginTop: 8 }}>
              {isSignUp ? "Sign Up as Manager" : "Sign In to Office Pool"}
            </button>
          </form>

          <div style={{ textAlign: "center", marginTop: 20, fontSize: 12 }}>
            <span style={{ color: "rgba(255,255,255,0.5)" }}>
              {isSignUp ? "Already have an account?" : "Don't have an account yet?"}
            </span>{" "}
            <button
              onClick={() => { setIsSignUp(!isSignUp); setAuthError(""); }}
              style={{ background: "transparent", border: "none", color: "var(--green-400)", fontWeight: 700, cursor: "pointer", padding: 0 }}
            >
              {isSignUp ? "Sign In" : "Register"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Signed in but no platform selected → show the lobby / platform selector.
  if (!activeLid) {
    return (
      <LobbyScreen
        leagues={myLeagues}
        loading={leaguesLoading}
        onEnter={(lid) => setActiveLid(lid)}
        onSignOut={() => _auth.signOut()}
      />
    );
  }

  return (
    <div data-screen-label={`WC26 · ${TABS.find(x => x.id === tab)?.label || tab}`}>
      <TopBar tweak={t} />
      <Hero tab={tab} />
      <SubNav tab={tab} onTab={setTab} />


      <div className={"page " + (isWide ? "page--wide" : "")}>
        <main>{renderScreen()}</main>
        {!isWide && <Sidebar onTab={setTab} />}
      </div>

      <MobileNav tab={tab} onTab={setTab} />

      <PlayerStatsModal />

      <TweaksPanel>
        <TweakSection label="Draft Simulator" />
        <TweakDraftSimulator lid={activeLid} />

        <TweakSection label="League" />
        <TweakRadio label="League size" value={String(t.leagueSize)}
          options={["6", "7", "8", "9", "10"]}
          onChange={v => setTweak('leagueSize', Number(v))} />
        <div style={{ fontSize: 10, color: "rgba(41,38,27,0.55)", lineHeight: 1.4, marginTop: -4 }}>
          {t.leagueSize > 8 ? "→ Top 8 → QF/SF/Final (KO from GW4)" : "→ Top 4 → SF/Final (extended H2H until GW6)"}
        </div>

        <TweakSection label="Tournament phase" />
        <TweakRadio label="Current GW" value={t.gwPhase}
          options={["group", "knockout"]}
          onChange={v => setTweak('gwPhase', v)} />

        <TweakSection label="Visual" />
        <TweakColor label="Brand accent" value={t.themeAccent}
          options={["wc", "fpl", "fire", "forest"]}
          onChange={v => setTweak('themeAccent', v)} />

        <TweakSection label="Behaviour" />

        <TweakSection label="Database Sync" />
        <TweakToggle label="Connect to Prod DB" value={localStorage.getItem("firebase_use_prod") === "true"}
          onChange={v => {
            localStorage.setItem("firebase_use_prod", v ? "true" : "false");
            window.location.reload();
          }} />
        {localStorage.getItem("firebase_use_prod") === "true" ? (
          <TweakButton label="Export Prod DB to File" onClick={window.exportFirestore} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
            <label style={{ fontSize: 10, color: "rgba(41,38,27,0.6)" }}>Import database file into local emulator:</label>
            <input type="file" accept=".json" onChange={e => {
              const file = e.target.files[0];
              if (file && window.confirm("Are you sure you want to overwrite your local emulator database with this file's data?")) {
                window.importFirestore(file);
              }
            }} style={{ fontSize: 10, color: "inherit", width: "100%" }} />
          </div>
        )}

        {window.IS_ADMIN && activeLid && (
          <>
            <TweakSection label="Mock Simulator (admin)" />
            <div style={{ fontSize: 10, color: "rgba(41,38,27,0.55)", lineHeight: 1.4, marginTop: -4 }}>
              {simBusy ? simBusy : `Generate the mock World Cup for "${activeLid}" — step one GW at a time, or reset to a fresh GW1.`}
            </div>
            <TweakButton
              label={simBusy ? "Working…" : "▶ Simulate next GW"}
              onClick={async () => {
                if (simBusy) return;
                try {
                  setSimBusy("Simulating next gameweek… (~30-50s, please wait)");
                  const res = await apiCall("POST", `/admin/leagues/${activeLid}/simulate-gw`, {}, { timeoutMs: 120000 });
                  if (res && res.done) {
                    alert("Tournament already complete — reset to GW1 to replay.");
                    setSimBusy("");
                    return;
                  }
                  // Land on the GW we just generated (not the next empty one).
                  try { if (res && res.gw) localStorage.setItem("wc_view_gw_after_reload", String(res.gw)); } catch (e) { /* ignore */ }
                  window.location.reload();
                } catch (e) {
                  // Firebase Hosting caps proxied requests at ~60s; a slow GW can
                  // surface as a timeout/504 even though it finished server-side.
                  // Reload to reflect the real state instead of a false failure.
                  const timedOut = !e || e.name === "AbortError" || e.status === 504 || e.status === undefined;
                  if (timedOut) {
                    window.location.reload();
                  } else {
                    alert("Simulate GW failed: " + (e.error || e.message || JSON.stringify(e)));
                    setSimBusy("");
                  }
                }
              }} />
            <TweakButton
              label="⟳ Reset mock to GW1"
              secondary
              onClick={async () => {
                if (simBusy) return;
                if (!window.confirm(`Reset "${activeLid}" back to a fresh GW1? This wipes all generated fixtures, scores and standings (squads + members are kept).`)) return;
                try {
                  setSimBusy("Resetting to GW1…");
                  await apiCall("POST", `/admin/leagues/${activeLid}/sim-reset`, {}, { timeoutMs: 120000 });
                  window.location.reload();
                } catch (e) {
                  alert("Reset failed: " + (e && e.message ? e.message : e));
                  setSimBusy("");
                }
              }} />

            <TweakSection label="View as Manager (mock)" />
            <div style={{ fontSize: 10, color: "rgba(41,38,27,0.55)", lineHeight: 1.4, marginTop: -4 }}>
              Switch whose squad / points / rank you're viewing — no separate login needed. Reloads as that manager; your real account is unchanged.
            </div>
            {(window.MANAGERS || []).map(mgr => (
              <TweakButton
                key={mgr.uid}
                label={(mgr.uid === window.ME ? "● " : "○ ") + (mgr.team || mgr.name || mgr.uid)}
                secondary={mgr.uid !== window.ME}
                onClick={() => {
                  try { localStorage.setItem("wc_mock_me", mgr.uid); } catch (e) { /* ignore */ }
                  window.location.reload();
                }} />
            ))}
            <TweakButton
              label="↺ Back to my real account"
              secondary
              onClick={() => {
                try { localStorage.removeItem("wc_mock_me"); } catch (e) { /* ignore */ }
                window.location.reload();
              }} />
          </>
        )}
      </TweaksPanel>
    </div>
  );
}

// Boot
const root = ReactDOM.createRoot(document.getElementById("app"));
root.render(<App />);
