// =====================================================================
// WC26 — App orchestrator (router + tweaks)
// =====================================================================

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "leagueSize": 7,
  "gwPhase": "knockout",
  "themeAccent": "wc",
  "showElimToast": true,
  "compactMode": false
}/*EDITMODE-END*/;

const ACCENT_THEMES = {
  wc:    { grad: "linear-gradient(94deg, #4a1ba8 0%, #4329c4 30%, #1f6dd1 60%, #1ad2c4 100%)", pill: "linear-gradient(94deg, #2bf094 0%, #1be8d4 100%)" },
  fpl:   { grad: "linear-gradient(94deg, #2d0b6e 0%, #3b1aa9 25%, #2c8acd 60%, #1bd6c8 100%)", pill: "linear-gradient(94deg, #00ff87 0%, #02efff 100%)" },
  fire:  { grad: "linear-gradient(94deg, #4a0d6e 0%, #c41262 35%, #ec582a 70%, #ffc844 100%)", pill: "linear-gradient(94deg, #ffd56b 0%, #ff6388 100%)" },
  forest:{ grad: "linear-gradient(94deg, #0d2818 0%, #1f6b3e 35%, #2eb05c 65%, #ffc844 100%)", pill: "linear-gradient(94deg, #00e87b 0%, #ffd56b 100%)" },
};

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [tab, setTab] = React.useState("status");
  const [toastDismissed, setToastDismissed] = React.useState(false);

  // Auth States
  const [user, setUser] = React.useState(null);
  const [authLoading, setAuthLoading] = React.useState(true);
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [displayName, setDisplayName] = React.useState("");
  const [authError, setAuthError] = React.useState("");
  const [isSignUp, setIsSignUp] = React.useState(false);
  const [activeLid, setActiveLid] = React.useState("lg_mock_draft");

  // Expose global league switch/refresh handlers
  React.useEffect(() => {
    window.setActiveLeagueId = setActiveLid;
    window.refreshActiveLeague = async () => {
      try {
        const list = await apiCall("GET", "/leagues/my");
        if (list && list.length > 0) {
          if (list.some(l => l.leagueId === "lg_mock_draft")) {
            setActiveLid("lg_mock_draft");
          } else {
            setActiveLid(list[0].leagueId);
          }
        }
      } catch (e) {
        console.warn("Failed to refresh active league", e);
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

          // Fetch my leagues to determine the active league ID
          const list = await apiCall("GET", "/leagues/my");
          if (list && list.length > 0) {
            if (list.some(l => l.leagueId === "lg_mock_draft")) {
              setActiveLid("lg_mock_draft");
            } else if (list.some(l => l.leagueId === "lg_pre_draft")) {
              setActiveLid("lg_pre_draft");
            } else {
              setActiveLid(list[0].leagueId);
            }
          }
        } catch (e) {
          console.warn("Failed to fetch leagues in auth sync", e);
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

    // Update ME global variable to logged-in user's UID
    window.ME = user.uid;
    try { ME = user.uid; } catch(e) {}

    const lid = activeLid; // active league ID

    // 1. Sync Standings live
    const unsubStandings = _db.collection("leagues").doc(lid)
      .collection("standings").doc("current")
      .onSnapshot((doc) => {
        if (doc.exists) {
          const data = doc.data();
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
            forceUpdate();
          }
        }
      }, (err) => console.error("Standings listen error:", err));

    // 2. Sync Live Scores / GW Totals live
    const curGw = window.TOURNAMENT.currentGw;
    const unsubScores = _db.collection("leagues").doc(lid)
      .collection("scores").doc(String(curGw))
      .onSnapshot((doc) => {
        if (doc.exists) {
          const data = doc.data();
          if (data && data.results) {
            window.GW3_TOTALS = {};
            Object.entries(data.results).forEach(([uid, res]) => {
              window.GW3_TOTALS[uid] = res.points || 0;
            });
            forceUpdate();
          }
        }
      }, (err) => console.error("Scores listen error:", err));

    // 3. Sync Draft State live
    const unsubDraft = _db.collection("leagues").doc(lid)
      .collection("draft").doc("state")
      .onSnapshot((doc) => {
        if (doc.exists) {
          const data = doc.data();
          const numMembers = data.order ? data.order.length : 10;
          window.DRAFT_STATE = {
            round: data.currentPick ? Math.floor(data.currentPick / numMembers) + 1 : 1,
            pickOverall: (data.currentPick || 0) + 1,
            pickInRound: ((data.currentPick || 0) % numMembers) + 1,
            onTheClock: data.currentDrafter || "",
            totalRounds: 15,
            totalPicks: data.totalPicks || 150,
            pickTimer: data.pickTimer || 60,
            secondsLeft: Math.max(0, Math.round((data.pickDeadline || 0) - Date.now() / 1000)),
            isMyTurn: data.currentDrafter === user.uid,
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

    // 5. Initial HTTP fetches (Bracket, Schedule, Squad, Lineup, Players)
    const loadInitialData = async () => {
      try {
        // Fetch active league details
        try {
          const leagueDetails = await apiCall("GET", `/leagues/${lid}`);
          if (leagueDetails) {
            window.LEAGUE = {
              id: leagueDetails.leagueId,
              name: leagueDetails.name,
              inviteCode: leagueDetails.inviteCode,
              size: leagueDetails.maxMembers,
              knockoutStartGw: leagueDetails.knockoutStartGw,
              leaguePhaseGws: leagueDetails.leaguePhaseGws,
              knockoutQualifiers: leagueDetails.knockoutQualifiers,
              pickTimer: leagueDetails.pickTimer,
              tradeApproval: leagueDetails.tradeApproval,
              admin: leagueDetails.adminUid,
            };

            if (leagueDetails.members) {
              window.MANAGERS = leagueDetails.members.map(m => ({
                uid: m.uid,
                name: m.displayName || m.uid.substring(0, 8),
                team: m.teamName || "Unnamed Team",
                flag: m.flag || "GER",
                draftPos: m.draftPosition || 99,
                waiverPri: m.waiverPriority || 99,
              }));
            }
          }
        } catch (e) {
          console.warn("Failed to fetch league details, using mock defaults", e);
        }

        // Fetch players list
        const players = await apiCall("GET", "/players");
        if (players && players.length > 0) {
          window.PLAYERS = players.map(p => ({
            id: String(p.id),
            name: p.name,
            pos: p.position,
            team: p.teamIso || p.teamShort || String(p.teamId),
            pts: p.totalPoints || 0,
            dr: p.draftRank || 999,
          }));
          window.PLAYER_MAP = Object.fromEntries(window.PLAYERS.map(p => [p.id, p]));

          // Dynamically populate GW3_POINTS from players total points in mock database!
          window.GW3_POINTS = {};
          window.PLAYERS.forEach(p => {
            window.GW3_POINTS[p.id] = p.pts;
          });
        }

        // Fetch bracket
        try {
          const bracket = await apiCall("GET", `/leagues/${lid}/knockout`);
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

            if (parsedSf.length > 0 || parsedFinal.length > 0) {
              window.BRACKET = {
                sf: parsedSf,
                final: parsedFinal,
              };
            }
          }
        } catch(e) {
          console.warn("Knockout bracket not seeded yet, using mock placeholder", e);
        }

        // Fetch Schedule
        try {
          const schedule = await apiCall("GET", `/leagues/${lid}/schedule`);
          if (schedule && schedule.schedule && schedule.schedule.length > 0) {
            window.SCHEDULE = {};
            schedule.schedule.forEach(g => {
              window.SCHEDULE[g.gw] = (g.matches || []).map(m => [m.home, m.away]);
            });
          }
        } catch (e) {
          console.warn("Failed to fetch schedule", e);
        }

        // Fetch my Squad
        try {
          const squad = await apiCall("GET", `/leagues/${lid}/squads/me`);
          if (squad && squad.players && squad.players.length > 0) {
            window.MY_SQUAD_IDS = squad.players.map(p => String(p.playerId));
          }
        } catch (e) {
          console.warn("Failed to fetch my squad", e);
        }

        // Fetch my Lineup
        try {
          const lineup = await apiCall("GET", `/leagues/${lid}/lineup/${curGw}`);
          if (lineup && lineup.starting && lineup.starting.length > 0) {
            window.MY_LINEUP_GW3 = {
              starting: (lineup.starting || []).map(String),
              bench: (lineup.bench || []).map(String),
              formation: lineup.formation || [1, 4, 4, 2],
              autoSubs: lineup.autoSubsMade || [],
            };
          }
        } catch (e) {
          console.warn("Failed to fetch my lineup", e);
        }

        // Fetch transfer window
        try {
          const winData = await apiCall("GET", `/leagues/${lid}/transfer-window`);
          if (winData) {
            window.WINDOW = {
              hoursLeft: winData.status === "open" ? 36 : 0,
              freeTransfers: 2,
              used: 0,
              state: winData.status,
              windowNumber: winData.window ? winData.window.windowNumber : 1
            };
          }
        } catch (e) {
          console.warn("Failed to fetch transfer window", e);
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
              pts: p.totalPoints || 0,
              dr: p.draftRank || 999,
            }));
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
          console.warn("Failed to fetch waivers", e);
        }

        forceUpdate();
      } catch (err) {
        console.error("Failed to load initial live data:", err);
      }
    };

    loadInitialData();

    return () => {
      unsubStandings();
      unsubScores();
      unsubDraft();
      unsubDraftPicks();
    };
  }, [user, activeLid]);

  // Apply theme accent via CSS custom props
  React.useEffect(() => {
    const theme = ACCENT_THEMES[t.themeAccent] || ACCENT_THEMES.wc;
    document.documentElement.style.setProperty("--grad-hero", theme.grad);
    document.documentElement.style.setProperty("--grad-pill-active", theme.pill);
  }, [t.themeAccent]);

  // Mock notification banner
  const showElim = t.showElimToast && !toastDismissed && (tab === "status" || tab === "pickteam");

  const renderScreen = () => {
    switch (tab) {
      case "status":    return <StatusScreen onTab={setTab} />;
      case "points":    return <PointsScreen onTab={setTab} />;
      case "pickteam":  return <PickTeamScreen onTab={setTab} />;
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

  return (
    <div data-screen-label={`WC26 · ${TABS.find(x => x.id === tab)?.label || tab}`}>
      <TopBar tweak={t} />
      <Hero tab={tab} />
      <SubNav tab={tab} onTab={setTab} />

      {showElim && (
        <div style={{ background: "linear-gradient(94deg, #c52836, #ff3e6c)", color: "white", padding: "10px 32px", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13, fontWeight: 600 }}>
          <span><strong>⚠ Group stage final:</strong> Italy, Morocco, Poland & 13 others eliminated. 3 of your players are dead. Open the transfer window before GW4 lock.</span>
          <div className="row" style={{ gap: 10 }}>
            <button className="btn btn--primary" style={{ padding: "6px 14px", fontSize: 11 }} onClick={() => setTab("transfers")}>Open transfers</button>
            <button onClick={() => setToastDismissed(true)} style={{ color: "white", padding: "2px 8px", fontSize: 18, opacity: 0.7 }}>×</button>
          </div>
        </div>
      )}

      <div className={"page " + (isWide ? "page--wide" : "")}>
        <main key={updateKey}>{renderScreen()}</main>
        {!isWide && <Sidebar onTab={setTab} />}
      </div>

      <PlayerStatsModal />

      <TweaksPanel>
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
        <TweakToggle label="Show elim banner" value={t.showElimToast}
          onChange={v => { setTweak('showElimToast', v); setToastDismissed(false); }} />
      </TweaksPanel>
    </div>
  );
}

// Boot
const root = ReactDOM.createRoot(document.getElementById("app"));
root.render(<App />);
