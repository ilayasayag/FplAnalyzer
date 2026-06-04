// =====================================================================
// WC26 — Screens: Status, Points, Pick Team
// =====================================================================

// ---------- ADMIN: Transfer Window switcher ----------
// Admin-only control (gated on backend `IS_ADMIN`, NOT on localhost) that lets
// an admin force the transfer-window phase of the shared MOCK DRAFT test league
// for testing. The four phases cycle none -> trade -> free_agents ->
// next_gw_bid; "Auto" clears the override and returns to the fixture-clock
// logic. It always targets `lg_mock_draft` (the designated test sandbox) so
// every admin account controls the same windows regardless of which league
// they happen to be viewing.
const WINDOW_TEST_LID = "lg_mock_draft";
function AdminWindowSwitcher() {
  const isAdmin = !!window.IS_ADMIN;
  const [phase, setPhase] = React.useState(null); // "auto" | "none" | "trade" | "free_agents" | "next_gw_bid"
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState("");

  // Derive the displayed phase from a transfer-window response: when an
  // override is active show the forced phase; otherwise "auto". A closed
  // window with no override means the real clock says nothing is open.
  const phaseFromWin = (win) => {
    if (!win) return "auto";
    if (win.overridden) return win.window ? win.window.phase : "none";
    return "auto";
  };

  const refresh = React.useCallback(async () => {
    if (!isAdmin) return;
    try {
      const win = await apiCall("GET", `/leagues/${WINDOW_TEST_LID}/transfer-window`);
      setPhase(phaseFromWin(win));
    } catch (e) {
      console.warn("AdminWindowSwitcher: failed to read window", e);
    }
  }, [isAdmin]);

  React.useEffect(() => { refresh(); }, [refresh]);

  if (!isAdmin) return null;

  const OPTIONS = [
    { key: "auto", label: "Auto" },
    { key: "trade", label: "Trade" },
    { key: "free_agents", label: "Free Agents" },
    { key: "next_gw_bid", label: "Next GW Bid" },
  ];
  const LABELS = { auto: "Auto", none: "Closed", trade: "Trade", free_agents: "Free Agents", next_gw_bid: "Next GW Bid" };

  const setWindow = async (key) => {
    if (busy) return;
    setBusy(true);
    setMsg("");
    try {
      const res = await apiCall("POST", `/leagues/${WINDOW_TEST_LID}/admin/window-override`, { phase: key });
      const eff = phaseFromWin(res);
      setPhase(eff);
      setMsg(`Window set to ${LABELS[eff] || eff}`);
    } catch (e) {
      console.warn("AdminWindowSwitcher: failed to set window", e);
      setMsg(`Failed: ${(e && (e.error || e.message)) || "error"}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card-dark">
      <div className="card-dark__title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <span>Transfer Window (admin · mock draft)</span>
        {msg && <span style={{ fontSize: 12, fontWeight: 600, color: "var(--green-400)" }}>{msg}</span>}
      </div>
      <div style={{ padding: 18, display: "flex", flexWrap: "wrap", gap: 8 }}>
        {OPTIONS.map(opt => {
          const active = phase === opt.key;
          return (
            <button
              key={opt.key}
              disabled={busy}
              onClick={() => setWindow(opt.key)}
              className="btn"
              style={{
                background: active ? "var(--green-400)" : "rgba(255,255,255,0.08)",
                color: active ? "var(--navy-900)" : "white",
                border: "1px solid " + (active ? "var(--green-400)" : "rgba(255,255,255,0.18)"),
                fontWeight: 700,
                cursor: busy ? "wait" : "pointer",
                opacity: busy ? 0.7 : 1,
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ---------- STATUS / Dashboard ----------
function StatusScreen({ onTab }) {
  const myStanding = STANDINGS.find(s => s.uid === ME) || { rank: "—", fpts: "—", hpts: "—" };
  const top5 = STANDINGS.slice(0, 8);

  const rounds = BRACKET.rounds || BRACKET || {};
  const qfArray = Array.isArray(rounds.qf) ? rounds.qf : [];
  const sfArray = Array.isArray(rounds.sf) ? rounds.sf : [];
  const finalArray = Array.isArray(rounds.final) 
    ? rounds.final 
    : (rounds.final && typeof rounds.final === 'object' ? [rounds.final] : []);

  const myMatch = qfArray.find(m => m.home === ME || m.away === ME) ||
                  sfArray.find(m => m.home === ME || m.away === ME) ||
                  finalArray.find(m => m.home === ME || m.away === ME);
  
  const myOpponent = myMatch ? (myMatch.home === ME ? (myMatch.away ? managerById(myMatch.away) : null) : (myMatch.home ? managerById(myMatch.home) : null)) : null;
  const mySeedObj = (BRACKET.seeds || []).find(s => s.uid === ME);
  const mySeed = mySeedObj ? mySeedObj.seed : (myStanding ? myStanding.rank : "?");

  const getRoundName = (matchId) => {
    if (!matchId) return "";
    if (matchId.startsWith("qf_")) return "Quarter-Final";
    if (matchId.startsWith("sf_")) return "Semi-Final";
    if (matchId.startsWith("final_")) return "Final";
    return "Knockout Match";
  };

  const getRoundPhase = (matchId) => {
    if (!matchId) return "";
    if (matchId.startsWith("qf_")) return "Quarter-Finals phase";
    if (matchId.startsWith("sf_")) return "Semi-Finals phase";
    if (matchId.startsWith("final_")) return "Final phase";
    return "Knockout phase";
  };

  const currentGw = TOURNAMENT.currentGw;
  const viewingGw = window.VIEWING_GW || currentGw;
  const setViewingGw = window.setViewingGw;
  const gwPoints = window.GW3_TOTALS && window.GW3_TOTALS[ME] !== undefined ? window.GW3_TOTALS[ME] : "—";
  
  const getOrdinal = n => {
    const num = Number(n);
    if (isNaN(num)) return "";
    const s = ["th", "st", "nd", "rd"], v = num % 100;
    return s[(v - 20) % 10] || s[v] || s[0];
  };

  const hasLeague = LEAGUE && LEAGUE.inviteCode;

  return (
    <div className="col" style={{ gap: 20 }}>
      {/* Admin-only transfer-window switcher (gated on backend IS_ADMIN) */}
      <AdminWindowSwitcher />

      {/* Phase transition banner */}
      {LEAGUE.status === "knockout" && myMatch && (
        <div className="card-dark" style={{ padding: 0, position: "relative", overflow: "hidden" }}>
          <div style={{
            background: "linear-gradient(94deg, #14104a 0%, #2a2080 50%, #1be8d4 130%)",
            padding: "22px 28px",
            display: "grid", gridTemplateColumns: "1fr auto", alignItems: "center", gap: 24,
          }}>
            <div>
              <div className="pill pill--green" style={{ marginBottom: 10 }}>● Group Stage Complete</div>
              <div className="h-display" style={{ fontSize: 26, color: "white", marginBottom: 6 }}>
                Knockout Phase Active
              </div>
              <div style={{ color: "rgba(255,255,255,0.78)", fontSize: 14 }}>
                You qualified <strong style={{ color: "var(--gold-500)" }}>Seed #{mySeed}</strong>. Your {getRoundName(myMatch.id)} vs <strong>{myOpponent ? myOpponent.team : "TBD"}</strong> kicks off soon.
              </div>
            </div>
            <button className="btn btn--primary" onClick={() => onTab("bracket")}>View Bracket →</button>
          </div>
        </div>
      )}

      {/* GW summary card */}
      <div className="card-dark">
        <div className="card-dark__title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <div className="row" style={{ gap: 8, alignItems: "center" }}>
            <span>Gameweek {viewingGw} · {hasLeague ? (LEAGUE.knockoutStartGw <= viewingGw ? "Knockout Phase" : "Group Stage Phase") : "Fantasy League"}</span>
          </div>
          
          <div className="row" style={{ gap: 12, alignItems: "center" }}>
            {/* Time Machine Selector */}
            <div className="row" style={{
              gap: 8, alignItems: "center",
              background: "rgba(255, 255, 255, 0.08)", padding: "4px 10px",
              borderRadius: 8, border: "1px solid rgba(255, 255, 255, 0.1)"
            }}>
              <button
                disabled={viewingGw <= 1}
                onClick={() => setViewingGw(viewingGw - 1)}
                style={{
                  background: "transparent", border: "none", color: viewingGw <= 1 ? "rgba(255,255,255,0.2)" : "white",
                  cursor: viewingGw <= 1 ? "not-allowed" : "pointer", padding: "2px 6px", fontWeight: 700
                }}
              >
                ◀
              </button>
              <span className="mono" style={{ fontSize: 12, fontWeight: 800, minWidth: 44, textAlign: "center" }}>
                GW {viewingGw}
              </span>
              <button
                disabled={viewingGw >= currentGw}
                onClick={() => setViewingGw(viewingGw + 1)}
                style={{
                  background: "transparent", border: "none", color: viewingGw >= currentGw ? "rgba(255,255,255,0.2)" : "white",
                  cursor: viewingGw >= currentGw ? "not-allowed" : "pointer", padding: "2px 6px", fontWeight: 700
                }}
              >
                ▶
              </button>
            </div>

            <span className={`pill ${viewingGw === currentGw ? "pill--green" : "pill--dark"}`} style={{ padding: "4px 8px", fontSize: 10, fontWeight: 700 }}>
              {viewingGw === currentGw ? "LIVE" : "PAST"}
            </span>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", borderTop: "1px solid var(--border-dark)" }}>
          <div style={{ padding: "22px 24px", borderRight: "1px solid var(--border-dark)" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>GW{viewingGw} Points</div>
            <div className="h-display" style={{ fontSize: 56, color: "var(--green-400)", lineHeight: 1.1, marginTop: 4 }}>{String(gwPoints)}</div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)", marginTop: 4 }}>Live performance points</div>
          </div>
          <div style={{ padding: "22px 24px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>League Rank</div>
            <div className="h-display" style={{ fontSize: 56, color: "var(--gold-500)", lineHeight: 1.1, marginTop: 4 }}>
              {myStanding.rank}{myStanding.rank !== "—" && <span style={{ fontSize: 22, color: "rgba(255,255,255,0.5)", verticalAlign: "super" }}>{getOrdinal(myStanding.rank)}</span>}
            </div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)", marginTop: 4 }}>
              {myStanding.hpts !== "—" ? `${myStanding.hpts} H2H pts` : "—"} · {myStanding.fpts !== "—" ? `${myStanding.fpts} total fpts` : "—"}
            </div>
          </div>
        </div>
      </div>

      {/* Your KO preview */}
      {LEAGUE.status === "knockout" && myMatch && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div style={{ background: "var(--navy-900)", color: "white", padding: "12px 20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 700, letterSpacing: "-0.01em" }}>Your {getRoundName(myMatch.id)} · GW{myMatch.gw}</span>
            <span className="pill pill--gold">{getRoundPhase(myMatch.id)}</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", padding: "24px 28px", alignItems: "center", gap: 24 }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 11, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Seed #{mySeed}</div>
              <div className="h-display" style={{ fontSize: 22 }}>{myStanding ? myStanding.team : "My Team"}</div>
              <div className="muted" style={{ fontSize: 13 }}>{myStanding ? myStanding.displayName || myStanding.name : "Manager"} · {myStanding ? myStanding.fpts : 0} fpts</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div className="h-display" style={{ fontSize: 32, color: "var(--ink-500)" }}>vs.</div>
              <div className="muted" style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>{getRoundName(myMatch.id)}</div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>GW {myMatch.gw}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                Seed #{myMatch.home === ME ? (myMatch.seedAway ?? myMatch.awaySeed ?? "?") : (myMatch.seedHome ?? myMatch.homeSeed ?? "?")}
              </div>
              <div className="h-display" style={{ fontSize: 22 }}>{myOpponent ? myOpponent.team : "TBD"}</div>
              <div className="muted" style={{ fontSize: 13 }}>{myOpponent ? myOpponent.name : "Awaiting Seeding"}</div>
            </div>
          </div>
        </div>
      )}

      {/* Top performer of GW3 */}
      <div className="card-dark">
        <div className="card-dark__title">GW{currentGw} Standout XI</div>
        <div style={{ padding: 18, display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
          {[...(window.PLAYERS || PLAYERS || [])]
            .sort((a, b) => b.pts - a.pts)
            .slice(0, 5).length > 0 ? (
              [...(window.PLAYERS || PLAYERS || [])]
                .sort((a, b) => b.pts - a.pts)
                .slice(0, 5).map(p => (
                  <div key={p.id} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                    <PlayerSlot playerId={p.id} points={p.pts} mode="points" />
                  </div>
                ))
            ) : (
              <div style={{ gridColumn: "span 5", textAlign: "center", padding: 10, color: "rgba(255,255,255,0.45)" }}>
                No performance data yet.
              </div>
            )}
        </div>
      </div>
    </div>
  );
}


// ---------- POINTS (finished GW pitch) ----------
function PointsScreen({ onTab }) {
  const [view, setView] = React.useState("pitch");
  const lineup = MY_LINEUP_GW3;

  // Calculate total points dynamically without captain doubling
  let totalPts = 0;
  if (lineup && lineup.starting) {
    lineup.starting.forEach(id => {
      totalPts += GW3_POINTS[id] ?? 0;
    });
  } else {
    totalPts = 65; // fallback
  }

  // Get current user's team name dynamically
  const myTeamName = (window.MANAGERS || MANAGERS).find(m => m.uid === (window.ME || ME))?.team || "My Squad";

  return (
    <div className="col" style={{ gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>
          Points · <span className="muted" style={{ fontWeight: 500 }}>{myTeamName}</span>
        </h2>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn btn--ghost-dark" style={{ padding: "8px 14px", fontSize: 12 }}>← GW2</button>
          <button className="btn btn--ghost-dark" disabled style={{ padding: "8px 14px", fontSize: 12 }}>GW4 →</button>
        </div>
      </div>

      <div className="card-dark" style={{ padding: 22 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18, gap: 16 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.6)", letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap" }}>Gameweek 3 · Group Stage MD3</div>
            <div className="h-display" style={{ fontSize: 22, marginTop: 2 }}>Final Points</div>
          </div>
          <div style={{ background: "var(--gold-500)", color: "var(--navy-900)", borderRadius: 12, padding: "12px 22px", textAlign: "center", flexShrink: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", whiteSpace: "nowrap" }}>FINAL POINTS</div>
            <div className="mono" style={{ fontSize: 38, fontWeight: 800, lineHeight: 1 }}>{totalPts}</div>
          </div>
        </div>

        <div style={{ display: "inline-flex", padding: 4, background: "rgba(0,0,0,0.25)", borderRadius: 999, marginBottom: 14 }}>
          <button className={"btn " + (view === "pitch" ? "btn--primary" : "")} style={{ padding: "6px 18px", fontSize: 12, background: view === "pitch" ? undefined : "transparent", color: view === "pitch" ? undefined : "white" }} onClick={() => setView("pitch")}>Pitch View</button>
          <button className={"btn " + (view === "list" ? "btn--primary" : "")} style={{ padding: "6px 18px", fontSize: 12, background: view === "list" ? undefined : "transparent", color: view === "list" ? undefined : "white" }} onClick={() => setView("list")}>List View</button>
        </div>

        {view === "pitch" ? (
          <Pitch lineup={lineup} mode="points" />
        ) : (
          <PointsListView lineup={lineup} />
        )}

        {/* Auto-subs */}
        <div style={{ marginTop: 22, paddingTop: 18, borderTop: "1px solid var(--border-dark)" }}>
          <div className="h-display" style={{ fontSize: 16, marginBottom: 10 }}>Automatic Substitutions</div>
          <table style={{ width: "100%", color: "white", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "rgba(255,255,255,0.55)", fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                <th style={{ textAlign: "left", padding: "8px 0" }}>In</th>
                <th style={{ textAlign: "left", padding: "8px 0" }}>Out</th>
                <th style={{ textAlign: "left", padding: "8px 0" }}>Reason</th>
              </tr>
            </thead>
            <tbody>
              {lineup.autoSubs.map((sub, i) => (
                <tr key={i} style={{ borderTop: "1px solid var(--border-dark)" }}>
                  <td style={{ padding: "10px 0", display: "flex", alignItems: "center", gap: 8 }}>
                    <Flag team={teamById(playerById(sub.in).team)} />
                    <strong>{playerById(sub.in).name}</strong>
                  </td>
                  <td style={{ padding: "10px 0" }}>{playerById(sub.out).name}</td>
                  <td style={{ padding: "10px 0", color: "rgba(255,255,255,0.65)" }}>{playerById(sub.out).name} played 0 minutes</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function PointsListView({ lineup }) {
  const all = [...lineup.starting, ...lineup.bench];
  return (
    <table className="table-clean table-dark">
      <thead>
        <tr>
          <th>Player</th>
          <th>Team</th>
          <th>Pos</th>
          <th style={{ textAlign: "right" }}>MIN</th>
          <th style={{ textAlign: "right" }}>G</th>
          <th style={{ textAlign: "right" }}>A</th>
          <th style={{ textAlign: "right" }}>CS</th>
          <th style={{ textAlign: "right" }}>PTS</th>
        </tr>
      </thead>
      <tbody>
        {all.map(id => {
          const p = playerById(id);
          const t = teamById(p.team);
          const inLineup = lineup.starting.includes(id);
          const pts = GW3_POINTS[id] ?? 0;
          // synth stats
          const mins = pts === 0 ? 0 : 90;
          const g = pts > 8 ? 1 : 0;
          const a = pts > 5 ? 1 : 0;
          return (
            <tr key={id} style={{ opacity: inLineup ? 1 : 0.5 }}>
              <td><strong>{p.name}</strong></td>
              <td><span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Flag team={t} /> {t.id}</span></td>
              <td>{POS_NAMES[p.pos]}</td>
              <td className="num" style={{ textAlign: "right" }}>{mins}</td>
              <td className="num" style={{ textAlign: "right" }}>{g}</td>
              <td className="num" style={{ textAlign: "right" }}>{a}</td>
              <td className="num" style={{ textAlign: "right" }}>{p.pos === 1 ? (mins ? "✓" : "—") : "—"}</td>
              <td className="num" style={{ textAlign: "right", fontWeight: 800, color: pts > 0 ? "var(--green-400)" : "rgba(255,255,255,0.4)" }}>{pts}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}


// ---------- PICK TEAM ----------
function PickTeamScreen({ onTab, squadLoading }) {
  const [view, setView] = React.useState("pitch");
  const [lineup, setLineup] = React.useState(MY_LINEUP_GW3);
  const [selected, setSelected] = React.useState(null);

  React.useEffect(() => {
    if (MY_LINEUP_GW3) {
      setLineup(MY_LINEUP_GW3);
    }
  }, [MY_LINEUP_GW3]);

  const handleSaveLineup = async () => {
    try {
      const lid = LEAGUE.id;
      const gw = TOURNAMENT.currentGw;
      const parseId = id => isNaN(Number(id)) ? Number(String(id).replace("p_", "")) : Number(id);
      
      const payload = {
        starting: lineup.starting.map(parseId),
        bench: lineup.bench.map(parseId),
        formation: lineup.formation,
      };
      
      await apiCall("PUT", `/leagues/${lid}/lineup/${gw}`, payload);
      alert("Lineup saved successfully!");
    } catch(err) {
      alert("Failed to save lineup: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  const handlePlayerClick = id => {
    if (!selected) {
      setSelected(id);
      return;
    }
    if (selected === id) { setSelected(null); return; }

    const isStartingA = lineup.starting.includes(selected);
    const isStartingB = lineup.starting.includes(id);

    // Hypothetically perform swap
    let newStarting = [...lineup.starting];
    let newBench = [...lineup.bench];

    const idxA = (isStartingA ? newStarting : newBench).indexOf(selected);
    const idxB = (isStartingB ? newStarting : newBench).indexOf(id);

    if (isStartingA && isStartingB) {
      [newStarting[idxA], newStarting[idxB]] = [newStarting[idxB], newStarting[idxA]];
    } else if (!isStartingA && !isStartingB) {
      [newBench[idxA], newBench[idxB]] = [newBench[idxB], newBench[idxA]];
    } else {
      const aArr = isStartingA ? newStarting : newBench;
      const bArr = isStartingB ? newStarting : newBench;
      aArr[idxA] = id;
      bArr[idxB] = selected;
    }

    // Dynamic formation validation
    const countPos = { 1: 0, 2: 0, 3: 0, 4: 0 };
    newStarting.forEach(pId => {
      const p = playerById(pId);
      if (p) {
        countPos[p.pos] = (countPos[p.pos] || 0) + 1;
      }
    });

    const gk = countPos[1];
    const def = countPos[2];
    const mid = countPos[3];
    const fwd = countPos[4];

    const formationKey = `${gk}-${def}-${mid}-${fwd}`;
    const VALID_FORMATIONS = [
      "1-3-5-2", "1-3-4-3", "1-4-5-1", "1-4-4-2", "1-4-3-3", "1-5-4-1", "1-5-3-2"
    ];

    if (!VALID_FORMATIONS.includes(formationKey)) {
      alert(`Invalid Formation: Swapping would result in a ${def}-${mid}-${fwd} formation. Legal formations must have 1 Goalkeeper, between 3 and 5 Defenders, between 2 and 5 Midfielders, and between 1 and 3 Forwards.`);
      setSelected(null);
      return;
    }

    // Sort starters so the Pitch component places players in their correct rows
    newStarting.sort((a, b) => {
      const posA = playerById(a)?.pos ?? 3;
      const posB = playerById(b)?.pos ?? 3;
      return posA - posB;
    });

    setLineup({
      ...lineup,
      starting: newStarting,
      bench: newBench,
      formation: [gk, def, mid, fwd]
    });
    setSelected(null);
  };

  // While an authenticated user's real squad is still loading, show a
  // lightweight skeleton instead of the data.jsx demo squad (which would
  // otherwise flash before /squads/me resolves and overwrites the globals).
  if (squadLoading) {
    return (
      <div className="col" style={{ gap: 16 }}>
        <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>My Team</h2>
        <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--ink-500)", fontSize: 14 }}>
          Loading your squad…
        </div>
      </div>
    );
  }

  // count eliminated in starting
  const elimStarting = lineup.starting.filter(id => {
    const p = playerById(id);
    return p && (p.elim || teamById(p.team)?.elim);
  });

  return (
    <div className="col" style={{ gap: 16 }}>
      <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>My Team</h2>

      {elimStarting.length > 0 && (
        <div className="alert alert--danger">
          <div className="alert__icon" style={{ background: "var(--red-500)", color: "white" }}>!</div>
          <div>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>
              {elimStarting.length} eliminated player{elimStarting.length > 1 ? "s" : ""} in your starting XI
            </div>
            <div style={{ fontSize: 12 }}>
              {elimStarting.map(id => playerById(id).name).join(", ")} — their nation is out of the tournament. They will score 0 in GW4.
            </div>
          </div>
        </div>
      )}

      <div className="card-dark" style={{ padding: 18 }}>
        {/* tabs */}
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
          <div style={{ display: "inline-flex", padding: 4, background: "rgba(0,0,0,0.25)", borderRadius: 999 }}>
            <button className={"btn " + (view === "pitch" ? "btn--primary" : "")} style={{ padding: "6px 18px", fontSize: 12, background: view === "pitch" ? undefined : "transparent", color: view === "pitch" ? undefined : "white" }} onClick={() => setView("pitch")}>Pitch View</button>
            <button className={"btn " + (view === "list" ? "btn--primary" : "")} style={{ padding: "6px 18px", fontSize: 12, background: view === "list" ? undefined : "transparent", color: view === "list" ? undefined : "white" }} onClick={() => setView("list")}>List View</button>
          </div>
        </div>

        {selected && (
          <div className="alert alert--info" style={{ marginBottom: 12, background: "rgba(91,61,242,0.18)", color: "white", border: "1px solid rgba(255,255,255,0.18)" }}>
            <div className="alert__icon" style={{ background: "var(--teal-400)", color: "var(--navy-900)" }}>↔</div>
            <div style={{ fontSize: 13 }}>
              <strong>{playerById(selected).name}</strong> selected. Click another player to swap, or click again to cancel.
            </div>
          </div>
        )}

        <Pitch lineup={lineup} mode="pick" onPlayerClick={handlePlayerClick} />

        <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 16 }}>
          <button className="btn btn--ghost" onClick={() => { setLineup(MY_LINEUP_GW3); setSelected(null); }}>Reset</button>
          <button onClick={handleSaveLineup} className="btn btn--primary" style={{ minWidth: 200 }}>Save Lineup for GW{TOURNAMENT.currentGw}</button>
        </div>
        <div style={{ textAlign: "center", marginTop: 10, fontSize: 12, color: "rgba(255,255,255,0.7)" }}>
          Locks {TOURNAMENT.gwDates[4].lockAt} · {WINDOW.hoursLeft}h remaining
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { StatusScreen, PointsScreen, PickTeamScreen });
