// =====================================================================
// WC26 — Screens: Status, Points, Pick Team
// =====================================================================

// ---------- STATUS / Dashboard ----------
function StatusScreen({ onTab }) {
  const myStanding = STANDINGS.find(s => s.uid === ME);
  const top5 = STANDINGS.slice(0, 8);

  const rounds = BRACKET.rounds || BRACKET;
  const myMatch = (rounds.qf || []).find(m => m.home === ME || m.away === ME) ||
                  (rounds.sf || []).find(m => m.home === ME || m.away === ME) ||
                  (rounds.final || []).find(m => m.home === ME || m.away === ME);
  
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

  return (
    <div className="col" style={{ gap: 20 }}>
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
        <div className="card-dark__title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>Gameweek 3 · Group Stage Round 3</span>
          <span className="pill pill--dark" style={{ background: "rgba(0,0,0,0.18)" }}>FINAL</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", borderTop: "1px solid var(--border-dark)" }}>
          <div style={{ padding: "22px 24px", borderRight: "1px solid var(--border-dark)" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>GW3 Points</div>
            <div className="h-display" style={{ fontSize: 56, color: "var(--green-400)", lineHeight: 1.1, marginTop: 4 }}>65</div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)" }}>vs. avg <strong style={{ color: "white" }}>63.1</strong> · <span style={{ color: "var(--green-400)" }}>+1.9</span></div>
          </div>
          <div style={{ padding: "22px 24px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>League Rank</div>
            <div className="h-display" style={{ fontSize: 56, color: "var(--gold-500)", lineHeight: 1.1, marginTop: 4 }}>7<span style={{ fontSize: 22, color: "rgba(255,255,255,0.5)" }}>th</span></div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)" }}>3 H2H pts · 179 fantasy pts · qualified</div>
          </div>
        </div>

        {/* day-by-day mini timeline */}
        <div style={{ display: "grid", gridTemplateColumns: "120px 1fr 120px", padding: "14px 24px", borderTop: "1px solid var(--border-dark)", color: "rgba(255,255,255,0.75)", fontSize: 12 }}>
          <span style={{ fontWeight: 600 }}>Day</span>
          <span style={{ fontWeight: 600, textAlign: "center" }}>Match Points</span>
          <span style={{ fontWeight: 600, textAlign: "right" }}>Bonus</span>
        </div>
        {[
          { day: "Wed 22 Jun", res: "CONFIRMED", bonus: "ADDED" },
          { day: "Thu 23 Jun", res: "CONFIRMED", bonus: "ADDED" },
          { day: "Fri 24 Jun", res: "CONFIRMED", bonus: "ADDED" },
          { day: "Sat 25 Jun", res: "CONFIRMED", bonus: "ADDED" },
        ].map((d, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "120px 1fr 120px", padding: "10px 24px", borderTop: "1px solid var(--border-dark)", alignItems: "center", fontSize: 12 }}>
            <span>{d.day}</span>
            <span style={{ display: "flex", justifyContent: "center" }}>
              <span className="pill pill--green">{d.res}</span>
            </span>
            <span style={{ textAlign: "right", color: "var(--green-400)", fontWeight: 700, letterSpacing: "0.04em" }}>{d.bonus}</span>
          </div>
        ))}
        <div style={{ padding: "10px 24px", borderTop: "1px solid var(--border-dark)", fontSize: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>Final standings</span>
          <span className="pill pill--teal">UPDATED</span>
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
        <div className="card-dark__title">GW3 Standout XI</div>
        <div style={{ padding: 18, display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
          {[
            { id: "p_yamal", pts: 14 },
            { id: "p_bellingham", pts: 12 },
            { id: "p_ronaldo", pts: 11 },
            { id: "p_musiala", pts: 8 },
            { id: "p_mbappe", pts: 7 },
          ].map(({ id, pts }) => (
            <div key={id} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <PlayerSlot playerId={id} points={pts} mode="points" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}


// ---------- POINTS (finished GW pitch) ----------
function PointsScreen({ onTab }) {
  const [view, setView] = React.useState("pitch");
  const lineup = MY_LINEUP_GW3;

  return (
    <div className="col" style={{ gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>
          Points · <span className="muted" style={{ fontWeight: 500 }}>Hapoel Eliyahu</span>
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
            <div className="mono" style={{ fontSize: 38, fontWeight: 800, lineHeight: 1 }}>65</div>
          </div>
        </div>

        <div style={{ display: "inline-flex", padding: 4, background: "rgba(0,0,0,0.25)", borderRadius: 999, marginBottom: 14 }}>
          <button className={"btn " + (view === "pitch" ? "btn--primary" : "")} style={{ padding: "6px 18px", fontSize: 12, background: view === "pitch" ? undefined : "transparent", color: view === "pitch" ? undefined : "white" }} onClick={() => setView("pitch")}>Pitch View</button>
          <button className={"btn " + (view === "list" ? "btn--primary" : "")} style={{ padding: "6px 18px", fontSize: 12, background: view === "list" ? undefined : "transparent", color: view === "list" ? undefined : "white" }} onClick={() => setView("list")}>List View</button>
        </div>

        {view === "pitch" ? (
          <Pitch lineup={lineup} mode="points" captain="p_kane" />
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
function PickTeamScreen({ onTab }) {
  const [view, setView] = React.useState("pitch");
  const [lineup, setLineup] = React.useState(MY_LINEUP_GW3);
  const [captain, setCaptain] = React.useState("p_kane");
  const [selected, setSelected] = React.useState(null);

  const handleSaveLineup = async () => {
    try {
      const lid = LEAGUE.id;
      const gw = TOURNAMENT.currentGw;
      const parseId = id => isNaN(Number(id)) ? Number(String(id).replace("p_", "")) : Number(id);
      
      const payload = {
        starting: lineup.starting.map(parseId),
        bench: lineup.bench.map(parseId),
        formation: lineup.formation,
        captain: parseId(captain),
        viceCaptain: lineup.starting.find(id => id !== captain) ? parseId(lineup.starting.find(id => id !== captain)) : parseId(captain)
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
    // swap selected with clicked
    const isStartingA = lineup.starting.includes(selected);
    const isStartingB = lineup.starting.includes(id);
    const next = { ...lineup, starting: [...lineup.starting], bench: [...lineup.bench] };
    const idxA = (isStartingA ? next.starting : next.bench).indexOf(selected);
    const idxB = (isStartingB ? next.starting : next.bench).indexOf(id);
    if (isStartingA && isStartingB) {
      [next.starting[idxA], next.starting[idxB]] = [next.starting[idxB], next.starting[idxA]];
    } else if (!isStartingA && !isStartingB) {
      [next.bench[idxA], next.bench[idxB]] = [next.bench[idxB], next.bench[idxA]];
    } else {
      const aArr = isStartingA ? next.starting : next.bench;
      const bArr = isStartingB ? next.starting : next.bench;
      aArr[idxA] = id;
      bArr[idxB] = selected;
    }
    setLineup(next);
    setSelected(null);
  };

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

        <Pitch lineup={lineup} mode="pick" captain={captain} onPlayerClick={handlePlayerClick} />

        <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 16 }}>
          <button className="btn btn--ghost" onClick={() => { setLineup(MY_LINEUP_GW3); setSelected(null); }}>Reset</button>
          <button onClick={handleSaveLineup} className="btn btn--primary" style={{ minWidth: 200 }}>Save Lineup for GW{TOURNAMENT.currentGw}</button>
        </div>
        <div style={{ textAlign: "center", marginTop: 10, fontSize: 12, color: "rgba(255,255,255,0.7)" }}>
          Locks {TOURNAMENT.gwDates[4].lockAt} · {WINDOW.hoursLeft}h remaining
        </div>
      </div>

      {/* Fixtures preview */}
      <div className="card">
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: 14, letterSpacing: "-0.01em" }}>Your players GW4 fixtures</strong>
          <span className="muted" style={{ fontSize: 12 }}>R32 · Jul 1–4</span>
        </div>
        <div style={{ padding: "12px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
          {[
            { player: "p_kane",      vs: "URU", home: true },
            { player: "p_mbappe",    vs: "POR2", home: true },
            { player: "p_bellingham",vs: "URU", home: true },
            { player: "p_yamal",     vs: "JPN", home: true },
            { player: "p_musiala",   vs: "MEX2", home: true },
            { player: "p_ronaldo",   vs: "FRA", home: false },
            { player: "p_bruno",     vs: "FRA", home: false },
            { player: "p_dias",      vs: "FRA", home: false },
          ].map(f => {
            const p = playerById(f.player);
            const t = teamById(p.team);
            const opp = teamById(f.vs);
            return (
              <div key={f.player} style={{ display: "grid", gridTemplateColumns: "180px 1fr 80px", alignItems: "center", gap: 12, padding: "6px 0", fontSize: 13 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Flag team={t} /> <strong>{p.name}</strong>
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="muted">{f.home ? "vs" : "@"}</span>
                  <Flag team={opp} /> {opp.name}
                </span>
                <span className="pill pill--teal" style={{ justifySelf: "end", fontSize: 10 }}>R32</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { StatusScreen, PointsScreen, PickTeamScreen });
