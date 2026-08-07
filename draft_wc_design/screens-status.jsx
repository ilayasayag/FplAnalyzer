// =====================================================================
// WC26 — Screens: Status, Points, Pick Team
// =====================================================================

// ---------- ADMIN: Transfer Window run-actions ----------
// Admin-only control (gated on backend `IS_ADMIN`, NOT on localhost) that lets
// an admin RUN the window machinery of the shared MOCK DRAFT test league: the
// wishlist auction for a GW, or the full trade-window-open orchestrator.
// Rendered on the TRANSFERS screen under the window switcher (the phase
// switching itself — Auto/Trade/Free agents/Gameweek — lives in
// TransfersScreen's inline switcher so there is exactly one switcher). It
// always targets `lg_mock_draft` (the designated test sandbox) so every admin
// account controls the same windows regardless of which league they happen to
// be viewing.
const WINDOW_TEST_LID = "lg_mock_draft";
function useAdminWindowSwitcher() {
  const isAdmin = !!window.IS_ADMIN;
  const [msg, setMsg] = React.useState("");
  const [gw, setGw] = React.useState((window.TOURNAMENT && window.TOURNAMENT.currentGw) || 1); // upcoming gw the auction/orchestrator run for
  const [running, setRunning] = React.useState(false);

  // Prefill the GW input from the mock league's live window when one is open.
  const refresh = React.useCallback(async () => {
    if (!isAdmin) return;
    try {
      const win = await apiCall("GET", `/leagues/${WINDOW_TEST_LID}/transfer-window`);
      if (win && win.window && win.window.gw) setGw(win.window.gw);
    } catch (e) {
      console.warn("AdminWindowSwitcher: failed to read window", e);
    }
  }, [isAdmin]);

  React.useEffect(() => { refresh(); }, [refresh]);

  // Run a backend action for the mock league and report a short summary.
  // `kind` is "auction" (PR-4 wishlist-only) or "orchestrator" (PR-5: deferred
  // trades FIRST, then the wishlist auction — the §6 trade-window-open sequence).
  const runAction = async (kind) => {
    if (running) return;
    setRunning(true);
    setMsg("");
    try {
      const path = kind === "orchestrator"
        ? `/admin/leagues/${WINDOW_TEST_LID}/open-trade-window/${gw}`
        : `/admin/leagues/${WINDOW_TEST_LID}/process-wishlist-auction/${gw}`;
      const res = await apiCall("POST", path);
      if (kind === "orchestrator") {
        const dt = (res.deferredTrades || {});
        const wa = (res.wishlistAuction || {});
        const ndt = (dt.executed || []).length;
        const nca = (dt.cancelled || []).length;
        const nwa = (wa.executed || []).length;
        setMsg(`GW${gw}: ${ndt} trade(s) executed, ${nca} cancelled · ${nwa} wishlist claim(s)`);
      } else {
        const n = (res.executed || []).length;
        const ns = (res.skipped || []).length;
        setMsg(`GW${gw} auction: ${n} claim(s), ${ns} skipped`);
      }
    } catch (e) {
      console.warn("AdminWindowSwitcher: action failed", e);
      setMsg(`Failed: ${(e && (e.error || e.message)) || "error"}`);
    } finally {
      setRunning(false);
    }
  };

  return { isAdmin, msg, gw, setGw, running, runAction };
}

function AdminWindowSwitcher() {
  const { isAdmin, msg, gw, setGw, running, runAction } = useAdminWindowSwitcher();

  // Visible to the global admin (Ilay) on ANY league — he keeps window
  // control after go-live; nobody else ever sees this panel.
  if (!isAdmin) return null;

  return (
    <div className="card-dark">
      <div className="card-dark__title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <span>Transfer Window Actions (admin · mock draft)</span>
        {msg && <span style={{ fontSize: 12, fontWeight: 600, color: "var(--green-400)" }}>{msg}</span>}
      </div>
      <div style={{ padding: 18, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <span style={{ fontSize: 12, opacity: 0.7, marginRight: 4 }}>
          Run for GW
        </span>
        <input
          type="number"
          min="1"
          value={gw}
          disabled={running}
          onChange={(e) => setGw(parseInt(e.target.value, 10) || 1)}
          style={{ width: 56, padding: "6px 8px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.18)", background: "rgba(255,255,255,0.08)", color: "white", fontWeight: 700 }}
        />
        <button
          disabled={running}
          onClick={() => runAction("auction")}
          className="btn"
          style={{ background: "rgba(255,255,255,0.08)", color: "white", border: "1px solid rgba(255,255,255,0.18)", fontWeight: 700, cursor: running ? "wait" : "pointer", opacity: running ? 0.7 : 1 }}
        >
          Run Wishlist Auction
        </button>
        <button
          disabled={running}
          onClick={() => runAction("orchestrator")}
          className="btn"
          style={{ background: "var(--teal-400)", color: "var(--navy-900)", border: "1px solid var(--teal-400)", fontWeight: 700, cursor: running ? "wait" : "pointer", opacity: running ? 0.7 : 1 }}
        >
          Open Trade Window (deferred + auction)
        </button>
      </div>
    </div>
  );
}

// ---------- STATUS / Dashboard ----------
function useStatusScreen() {
  const isMobile = useIsMobile();
  // Store-backed (#51): the hero numbers subscribe to WCStore rows instead of
  // reading raw globals. While a row is loading we render a skeleton — NEVER
  // the data.jsx demo standings and never a stale gw's numbers (the store
  // drops mis-stamped responses, so populate-then-blank can't happen).
  const standingsRow = useStoreRow("standings");
  const gwTotalsRow = useStoreRow("gwTotals");
  const standingsLoading = standingsRow.status !== "ready";
  const _standings = standingsRow.status === "ready" ? (standingsRow.value || []) : [];
  const myStanding = _standings.find(s => s.uid === window.ME) || { rank: "—", fpts: "—", hpts: "—" };

  const rounds = BRACKET.rounds || BRACKET || {};
  const qfArray = Array.isArray(rounds.qf) ? rounds.qf : [];
  const sfArray = Array.isArray(rounds.sf) ? rounds.sf : [];
  const finalArray = Array.isArray(rounds.final)
    ? rounds.final
    : (rounds.final && typeof rounds.final === 'object' ? [rounds.final] : []);

  const myMatch = qfArray.find(m => m.home === window.ME || m.away === window.ME) ||
                  sfArray.find(m => m.home === window.ME || m.away === window.ME) ||
                  finalArray.find(m => m.home === window.ME || m.away === window.ME);

  const myOpponent = myMatch ? (myMatch.home === window.ME ? (myMatch.away ? managerById(myMatch.away) : null) : (myMatch.home ? managerById(myMatch.home) : null)) : null;
  const mySeedObj = (BRACKET.seeds || []).find(s => s.uid === window.ME);
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
  const { viewingGw, setViewingGw } = useAppCtx();
  // null = still loading (render a skeleton); "—" = loaded, genuinely absent.
  const gwPoints = gwTotalsRow.status !== "ready" ? null
    : (gwTotalsRow.value && gwTotalsRow.value[window.ME] !== undefined ? gwTotalsRow.value[window.ME] : "—");

  const getOrdinal = n => {
    const num = Number(n);
    if (isNaN(num)) return "";
    const s = ["th", "st", "nd", "rd"], v = num % 100;
    return s[(v - 20) % 10] || s[v] || s[0];
  };

  const hasLeague = LEAGUE && LEAGUE.inviteCode;

  return { isMobile, standingsLoading, myStanding, myMatch, myOpponent, mySeed, getRoundName, getRoundPhase, currentGw, viewingGw, setViewingGw, gwPoints, getOrdinal, hasLeague };
}

function StatusScreen({ onTab }) {
  const { isMobile, standingsLoading, myStanding, myMatch, myOpponent, mySeed, getRoundName, getRoundPhase, currentGw, viewingGw, setViewingGw, gwPoints, getOrdinal, hasLeague } = useStatusScreen();

  return (
    <div className="col" style={{ gap: 20 }}>
      {/* Any user can pull fresh live scores on demand */}
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <SyncDataButton />
      </div>

      {/* Phase transition banner */}
      {LEAGUE.status === "knockout" && myMatch && (
        <div className="card-dark" style={{ padding: 0, position: "relative", overflow: "hidden" }}>
          <div style={{
            background: "linear-gradient(94deg, #14104a 0%, #2a2080 50%, #1be8d4 130%)",
            padding: isMobile ? "18px 16px" : "22px 28px",
            display: "grid",
            gridTemplateColumns: isMobile ? "minmax(0, 1fr)" : "1fr auto",
            alignItems: "center",
            gap: isMobile ? 14 : 24,
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
                  cursor: viewingGw <= 1 ? "not-allowed" : "pointer",
                  padding: isMobile ? "10px 12px" : "2px 6px",
                  minHeight: isMobile ? 40 : undefined,
                  fontWeight: 700
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
                  cursor: viewingGw >= currentGw ? "not-allowed" : "pointer",
                  padding: isMobile ? "10px 12px" : "2px 6px",
                  minHeight: isMobile ? 40 : undefined,
                  fontWeight: 700
                }}
              >
                ▶
              </button>
            </div>

            <span className={`pill ${viewingGw === currentGw ? "pill--green" : "pill--dark"}`} style={{ padding: "4px 8px", fontSize: isMobile ? 11 : 10, fontWeight: 700 }}>
              {viewingGw === currentGw ? "LIVE" : "PAST"}
            </span>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "minmax(0, 1fr) minmax(0, 1fr)" : "1fr 1fr", borderTop: "1px solid var(--border-dark)" }}>
          <div style={{ padding: isMobile ? "16px 14px" : "22px 24px", borderRight: "1px solid var(--border-dark)", minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>GW{viewingGw} Points</div>
            <div className="h-display" style={{ fontSize: isMobile ? 42 : 56, color: "var(--green-400)", lineHeight: 1.1, marginTop: 4 }}>
              {gwPoints === null ? <Skel w={isMobile ? 64 : 88} h={isMobile ? 38 : 50} /> : String(gwPoints)}
            </div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)", marginTop: 4 }}>Live performance points</div>
          </div>
          <div style={{ padding: isMobile ? "16px 14px" : "22px 24px", minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>League Rank</div>
            <div className="h-display" style={{ fontSize: isMobile ? 42 : 56, color: "var(--gold-500)", lineHeight: 1.1, marginTop: 4 }}>
              {standingsLoading ? <Skel w={isMobile ? 48 : 64} h={isMobile ? 38 : 50} /> : (
                <React.Fragment>
                  {myStanding.rank}{myStanding.rank !== "—" && <span style={{ fontSize: isMobile ? 17 : 22, color: "rgba(255,255,255,0.5)", verticalAlign: "super" }}>{getOrdinal(myStanding.rank)}</span>}
                </React.Fragment>
              )}
            </div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)", marginTop: 4 }}>
              {standingsLoading ? <Skel w={140} h={12} /> : (
                <React.Fragment>
                  {myStanding.hpts !== "—" ? `${myStanding.hpts} H2H pts` : "—"} · {myStanding.fpts !== "—" ? `${myStanding.fpts} total fpts` : "—"}
                </React.Fragment>
              )}
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
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "minmax(0, 1fr)" : "1fr auto 1fr", padding: isMobile ? "18px 16px" : "24px 28px", alignItems: "center", gap: isMobile ? 12 : 24 }}>
            <div style={{ textAlign: isMobile ? "center" : "right", minWidth: isMobile ? 0 : undefined }}>
              <div style={{ fontSize: 11, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Seed #{mySeed}</div>
              <div className="h-display" style={{ fontSize: 22, display: "flex", alignItems: "center", gap: 8, justifyContent: isMobile ? "center" : "flex-end" }}>{myStanding ? myStanding.team : "My Team"} <ManagerFlag uid={window.ME} size="lg" /></div>
              <div className="muted" style={{ fontSize: 13 }}>{myStanding ? myStanding.displayName || myStanding.name : "Manager"} · {myStanding ? myStanding.fpts : 0} fpts</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div className="h-display" style={{ fontSize: 32, color: "var(--ink-500)" }}>vs.</div>
              <div className="muted" style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>{getRoundName(myMatch.id)}</div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>GW {myMatch.gw}</div>
            </div>
            <div style={{ textAlign: isMobile ? "center" : undefined, minWidth: isMobile ? 0 : undefined }}>
              <div style={{ fontSize: 11, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                Seed #{myMatch.home === window.ME ? (myMatch.seedAway ?? myMatch.awaySeed ?? "?") : (myMatch.seedHome ?? myMatch.homeSeed ?? "?")}
              </div>
              <div className="h-display" style={{ fontSize: 22, display: "flex", alignItems: "center", gap: 8, justifyContent: isMobile ? "center" : "flex-start" }}>{myOpponent && myOpponent.uid && <ManagerFlag uid={myOpponent.uid} size="lg" />}{myOpponent ? myOpponent.team : "TBD"}</div>
              <div className="muted" style={{ fontSize: 13 }}>{myOpponent ? myOpponent.name : "Awaiting Seeding"}</div>
            </div>
          </div>
        </div>
      )}

      {/* Top performer of GW3 */}
      <div className="card-dark">
        <div className="card-dark__title">GW{currentGw} Standout XI</div>
        <div style={isMobile
          ? { padding: 14, display: "flex", overflowX: "auto", WebkitOverflowScrolling: "touch", gap: 12 }
          : { padding: 18, display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
          {[...(window.PLAYERS || PLAYERS || [])]
            .sort((a, b) => b.pts - a.pts)
            .slice(0, 5).length > 0 ? (
              [...(window.PLAYERS || PLAYERS || [])]
                .sort((a, b) => b.pts - a.pts)
                .slice(0, 5).map(p => (
                  <div key={p.id} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, flex: isMobile ? "0 0 auto" : undefined }}>
                    <PlayerSlot playerId={p.id} points={p.pts} mode="points" />
                  </div>
                ))
            ) : (
              <div style={{ gridColumn: "span 5", textAlign: "center", padding: 10, color: "rgba(255,255,255,0.45)", flex: isMobile ? "1 0 100%" : undefined }}>
                No performance data yet.
              </div>
            )}
        </div>
      </div>
    </div>
  );
}


// ---------- POINTS (finished GW pitch) ----------
function usePointsScreen() {
  const isMobile = useIsMobile();
  const [view, setView] = React.useState("pitch");
  // The live lineup for the viewed GW — via the STORE row, never the data.jsx
  // demo roster and never a stale gw's lineup (the row drops to loading on
  // every gw/league change and stale responses are stamped out). For a
  // FINISHED gw we instead render the immutable gw_history snapshot (see
  // snapLineup below) so the pitch shows exactly the squad that was locked
  // for that GW — not whatever the squad became after later moves.
  const lineupRow = useStoreRow("myLineup");
  const liveLineup = lineupRow.status === "ready" ? lineupRow.value : null;
  const lineupLoading = lineupRow.status !== "ready";

  const currentGw = TOURNAMENT.currentGw;
  const { viewingGw, setViewingGw } = useAppCtx();
  const me = window.ME;

  // Per-player breakdown for the VIEWED gw from the manager's gw_history
  // snapshot (post-autosub starters+bench). statsById[id] = { points, stats }
  // where points IS the engine output. Empty {} until the fetch lands.
  const [statsById, setStatsById] = React.useState({});
  // Locked lineup rebuilt from the gw_history snapshot for a finished GW.
  const [snapLineup, setSnapLineup] = React.useState(null);
  const lid = window.LEAGUE && window.LEAGUE.id;

  React.useEffect(() => {
    setStatsById({});
    setSnapLineup(null);
    if (!lid || !me) return;
    let cancelled = false;
    apiCall("GET", `/leagues/${lid}/gw-history/${me}?gw=${viewingGw}`)
      .then(snap => {
        if (cancelled || !snap || !Array.isArray(snap.players)) return;
        const map = {};
        snap.players.forEach(pl => { map[String(pl.id)] = { points: pl.points || 0, stats: pl.stats || {} }; });
        setStatsById(map);
        // Prefer the snapshot's frozen starting/bench; older snapshots that
        // predate those fields fall back to the players order (starting first).
        const ids = snap.players.map(pl => pl.id);
        const starting = (Array.isArray(snap.starting) && snap.starting.length) ? snap.starting : ids.slice(0, 11);
        const bench = Array.isArray(snap.bench) ? snap.bench : ids.slice(11);
        setSnapLineup({ starting, bench, autoSubs: snap.autoSubs || [] });
      })
      .catch(err => { if (!cancelled) console.error("Failed to fetch gw-history snapshot:", err); });
    return () => { cancelled = true; };
  }, [lid, me, viewingGw]);

  // For a finished GW, render the immutable snapshot lineup; for the live GW,
  // the editable lineup doc. The Pitch lays starters out by formation, so order
  // the snapshot's starting XI GK→DEF→MID→FWD and derive the formation from the
  // players' real positions (resolved via window.PLAYER_MAP).
  const EMPTY_LINEUP = { starting: [], bench: [], formation: [1, 4, 4, 2], autoSubs: [] };
  const lineup = React.useMemo(() => {
    // A FINISHED gw must ONLY ever render its frozen gw_history snapshot — never
    // the live squad, which may include free-agents/trades acquired AFTER that
    // GW (that bug showed a just-signed player in a past, already-scored GW).
    // While the snapshot is still loading, show an empty pitch, not the live one.
    if (viewingGw < currentGw) {
      if (!snapLineup) return EMPTY_LINEUP;
    } else {
      return liveLineup || EMPTY_LINEUP;
    }
    const pmap = window.PLAYER_MAP || {};
    const posOf = (id) => (pmap[String(id)] ? pmap[String(id)].pos : 3);
    const byPos = { 1: [], 2: [], 3: [], 4: [] };
    (snapLineup.starting || []).forEach(id => { (byPos[posOf(id)] || byPos[3]).push(id); });
    const ordered = [...byPos[1], ...byPos[2], ...byPos[3], ...byPos[4]];
    const formation = [Math.max(1, byPos[1].length), byPos[2].length, byPos[3].length, byPos[4].length];
    return { starting: ordered, bench: snapLineup.bench || [], formation, autoSubs: snapLineup.autoSubs || [] };
  }, [viewingGw, currentGw, snapLineup, liveLineup]);

  // Points-only map for the pitch slots.
  const gwPointsById = React.useMemo(() => {
    const m = {};
    Object.entries(statsById).forEach(([id, v]) => { m[id] = v.points; });
    return m;
  }, [statsById]);

  // Authoritative squad total for the viewed gw = backend results.{uid}.points
  // (Σ starter points post-autosub + captain bonus). null = still loading
  // (render a skeleton); "—" = loaded, gw not scored for this manager.
  const gwTotalsRow = useStoreRow("gwTotals");
  const totalPts = gwTotalsRow.status !== "ready" ? null
    : ((gwTotalsRow.value && gwTotalsRow.value[me] != null) ? gwTotalsRow.value[me] : "—");

  // Get current user's team name dynamically (no demo-roster fallback).
  const myTeamName = (window.MANAGERS || []).find(m => m.uid === me)?.team || "My Squad";

  return { isMobile, view, setView, lineup, lineupLoading, statsById, gwPointsById, totalPts, myTeamName, currentGw, viewingGw, setViewingGw };
}

function PointsScreen({ onTab }) {
  const { isMobile, view, setView, lineup, lineupLoading, statsById, gwPointsById, totalPts, myTeamName, currentGw, viewingGw, setViewingGw } = usePointsScreen();

  return (
    <div className="col" style={{ gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: isMobile ? "wrap" : undefined, gap: isMobile ? 10 : undefined }}>
        <h2 className="h-display" style={{ fontSize: isMobile ? 22 : 26, margin: 0, minWidth: isMobile ? 0 : undefined, display: "flex", alignItems: "center", gap: 10 }}>
          <ManagerFlag uid={window.ME} size="xl" /> Points · <span className="muted" style={{ fontWeight: 500 }}>{myTeamName}</span>
        </h2>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn btn--ghost-dark" style={{ padding: isMobile ? "11px 14px" : "8px 14px", fontSize: 12, minHeight: isMobile ? 40 : undefined }} disabled={viewingGw <= 1 || !setViewingGw} onClick={() => setViewingGw && setViewingGw(viewingGw - 1)}>← GW{viewingGw - 1}</button>
          <button className="btn btn--ghost-dark" disabled={viewingGw >= currentGw || !setViewingGw} style={{ padding: isMobile ? "11px 14px" : "8px 14px", fontSize: 12, minHeight: isMobile ? 40 : undefined }} onClick={() => setViewingGw && setViewingGw(viewingGw + 1)}>GW{viewingGw + 1} →</button>
        </div>
      </div>

      <div className="card-dark" style={{ padding: isMobile ? 14 : 22 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18, gap: isMobile ? 12 : 16 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.6)", letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap" }}>Gameweek {viewingGw}</div>
            <div className="h-display" style={{ fontSize: isMobile ? 19 : 22, marginTop: 2 }}>{viewingGw < currentGw ? "Final Points" : "Live Points"}</div>
          </div>
          <div style={{ background: "var(--gold-500)", color: "var(--navy-900)", borderRadius: 12, padding: isMobile ? "10px 16px" : "12px 22px", textAlign: "center", flexShrink: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", whiteSpace: "nowrap" }}>{viewingGw < currentGw ? "FINAL POINTS" : "POINTS"}</div>
            <div className="mono" style={{ fontSize: isMobile ? 32 : 38, fontWeight: 800, lineHeight: 1 }}>{totalPts === null ? <Skel w={44} h={30} /> : totalPts}</div>
          </div>
        </div>

        <div style={{ display: "inline-flex", padding: 4, background: "rgba(0,0,0,0.25)", borderRadius: 999, marginBottom: 14 }}>
          <button className={"btn " + (view === "pitch" ? "btn--primary" : "")} style={{ padding: isMobile ? "11px 18px" : "6px 18px", fontSize: 12, minHeight: isMobile ? 40 : undefined, background: view === "pitch" ? undefined : "transparent", color: view === "pitch" ? undefined : "white" }} onClick={() => setView("pitch")}>Pitch View</button>
          <button className={"btn " + (view === "list" ? "btn--primary" : "")} style={{ padding: isMobile ? "11px 18px" : "6px 18px", fontSize: 12, minHeight: isMobile ? 40 : undefined, background: view === "list" ? undefined : "transparent", color: view === "list" ? undefined : "white" }} onClick={() => setView("list")}>List View</button>
        </div>

        {view === "pitch" ? (
          <Pitch lineup={lineup} mode="points" pointsById={gwPointsById} />
        ) : (
          <PointsListView lineup={lineup} statsById={statsById} />
        )}

        {/* Auto-subs */}
        <div style={{ marginTop: 22, paddingTop: 18, borderTop: "1px solid var(--border-dark)" }}>
          <div className="h-display" style={{ fontSize: 16, marginBottom: 10 }}>Automatic Substitutions</div>
          <div className="table-scroll">
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
    </div>
  );
}

function PointsListView({ lineup, statsById = {} }) {
  const all = [...lineup.starting, ...lineup.bench];
  return (
    <div className="table-scroll">
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
          // Real per-gw stats + points come from the SAME gw_history snapshot
          // row (engine output). No fabrication: dashes when no data.
          const row = statsById[String(id)];
          const s = row ? (row.stats || {}) : {};
          const pts = row ? row.points : 0;
          const mins = s.minutes || 0;
          const g = s.goals || 0;
          const a = s.assists || 0;
          const cs = !!s.cleanSheet;
          return (
            <tr key={id} style={{ opacity: inLineup ? 1 : 0.5 }}>
              <td><strong>{p.name}</strong></td>
              <td><span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Flag team={t} /> {t.id}</span></td>
              <td>{POS_NAMES[p.pos]}</td>
              <td className="num" style={{ textAlign: "right" }}>{mins}</td>
              <td className="num" style={{ textAlign: "right" }}>{g}</td>
              <td className="num" style={{ textAlign: "right" }}>{a}</td>
              <td className="num" style={{ textAlign: "right" }}>{(p.pos === 1 || p.pos === 2) ? (cs ? "✓" : "—") : "—"}</td>
              <td className="num" style={{ textAlign: "right", fontWeight: 800, color: pts > 0 ? "var(--green-400)" : "rgba(255,255,255,0.4)" }}>{pts}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
    </div>
  );
}


// ---------- PICK TEAM ----------
function usePickTeamScreen() {
  const isMobile = useIsMobile();
  const [view, setView] = React.useState("pitch");
  const squadRow = useStoreRow("mySquad");
  // Cached edit-GW resolution ({ gw, lineup|null }) — filled by the app
  // bootstrap's prefetch and revalidated in the background on each mount.
  // Re-entering the tab renders INSTANTLY from this cache instead of holding
  // the skeleton gate through /edit-gw + /lineup round-trips every visit
  // (the "grey squares every time I press Pick Team" report). Pick Team's
  // lineup still has exactly ONE source — this edit-GW row — never the
  // viewed (Points) lineup.
  const editRow = useStoreRow("editLineup");
  // True once the manager has unsaved local edits: a background revalidate
  // (or a late prefetch) must never wipe in-progress changes.
  const dirtyRef = React.useRef(false);

  const _fromSquad = (ids) => {
    const byPos = { 1: [], 2: [], 3: [], 4: [] };
    (ids || []).forEach(pid => {
      const p = playerById(pid);
      if (p && byPos[p.pos]) byPos[p.pos].push(String(pid));
    });
    const nd = Math.min(byPos[2].length, 4), nm = Math.min(byPos[3].length, 4), nf = Math.min(byPos[4].length, 2);
    return {
      starting: [...byPos[1].slice(0, 1), ...byPos[2].slice(0, nd), ...byPos[3].slice(0, nm), ...byPos[4].slice(0, nf)],
      bench: [...byPos[1].slice(1), ...byPos[2].slice(nd), ...byPos[3].slice(nm), ...byPos[4].slice(nf)],
      formation: [1, nd, nm, nf],
      autoSubs: [],
    };
  };
  // A ready row with lineup:null means "edit GW has no saved lineup yet" —
  // genuinely carry the CURRENT squad forward (needs the squad row).
  const _rowToLineup = (row, sqRow) => {
    if (row.status !== "ready" || !row.value) return null;
    if (row.value.lineup) return row.value.lineup;
    return sqRow.status === "ready" ? _fromSquad(sqRow.value) : null;
  };

  // Instant render on cached visits: initialize straight from the store so
  // the skeleton gate never shows when the edit lineup is already known.
  const [lineup, setLineup] = React.useState(() => _rowToLineup(WCStore.row("editLineup"), WCStore.row("mySquad")));
  const [selected, setSelected] = React.useState(null);
  const [toast, setToast] = React.useState(null);
  // The GW we EDIT = the earliest unlocked GW (GW2 while GW1 is live/locked),
  // resolved from the backend so we never edit a frozen, already-scored GW.
  const [editGw, setEditGw] = React.useState(() => {
    const r = WCStore.row("editLineup");
    return (r.status === "ready" && r.value && r.value.gw) || (window.TOURNAMENT && window.TOURNAMENT.currentGw) || 1;
  });

  // Route cache/revalidation updates into local state — never over unsaved
  // edits (dirty guard). Runs whenever the row (or the squad readiness the
  // carry-forward depends on) changes.
  React.useEffect(() => {
    if (editRow.status !== "ready" || !editRow.value) return;
    setEditGw(editRow.value.gw);
    if (dirtyRef.current) return;
    const lu = _rowToLineup(editRow, squadRow);
    if (lu) setLineup(lu);
  }, [editRow, squadRow.status]);

  // Background revalidate (once per mount, after the squad is known): fetch
  // the edit GW + its own lineup and refresh the CACHE ROW; the effect above
  // routes it to the screen unless there are unsaved edits. Doubles as the
  // initial filler when the bootstrap prefetch didn't run or failed. Uses
  // the same stamped tag as the prefetch so stale-league responses drop.
  React.useEffect(() => {
    const lid = window.LEAGUE && window.LEAGUE.id;
    if (!lid || squadRow.status !== "ready") return;
    let cancelled = false;
    const _tag = `${lid}|${window.ME}`;
    (async () => {
      let gw = (window.TOURNAMENT && window.TOURNAMENT.currentGw) || 1;
      try {
        const eg = await apiCall("GET", `/leagues/${lid}/edit-gw`);
        gw = (eg && eg.editGw) || gw;
      } catch (e) {
        console.warn("edit-gw resolve failed; editing current GW", e);
      }
      if (cancelled) return;
      try {
        const lu = await apiCall("GET", `/leagues/${lid}/lineup/${gw}`);
        if (cancelled) return;
        WCStore.set("editLineup", {
          gw,
          lineup: (lu && Array.isArray(lu.starting) && lu.starting.length) ? {
            starting: lu.starting.map(String),
            bench: (lu.bench || []).map(String),
            formation: lu.formation || [1, 4, 4, 2],
            autoSubs: lu.autoSubsMade || [],
          } : null,
        }, _tag);
      } catch (e) {
        console.warn(`lineup fetch failed for edit GW${gw}`, e);
        // Nothing cached at all → publish the carry-forward marker so the
        // screen isn't stuck on the gate.
        if (!cancelled && WCStore.status("editLineup") !== "ready") {
          WCStore.set("editLineup", { gw, lineup: null }, _tag);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [squadRow.status]);

  // Player cards must show opponents for the GW being EDITED (the one in
  // "Save Lineup for GWX"), not the viewed GW. Fetch that round's per-team
  // map into the window.WC_FIXTURES_BY_GW cache, then bump state so the pitch
  // re-renders from "—" to real opponents once it lands.
  const [, setFixturesGwLoaded] = React.useState(0);
  React.useEffect(() => {
    if (typeof window.fetchFixturesByTeamForGw !== "function") return;
    if (window.WC_FIXTURES_BY_GW && window.WC_FIXTURES_BY_GW[editGw]) return;
    let cancelled = false;
    window.fetchFixturesByTeamForGw(editGw)
      .then(() => { if (!cancelled) setFixturesGwLoaded(editGw); })
      .catch(e => console.warn(`Pick Team: fixtures fetch failed for GW${editGw}`, e));
    return () => { cancelled = true; };
  }, [editGw]);

  React.useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const handleSaveLineup = async () => {
    try {
      const lid = LEAGUE.id;
      const gw = editGw;
      const parseId = id => isNaN(Number(id)) ? Number(String(id).replace("p_", "")) : Number(id);

      const payload = {
        starting: lineup.starting.map(parseId),
        bench: lineup.bench.map(parseId),
        formation: lineup.formation,
      };

      await apiCall("PUT", `/leagues/${lid}/lineup/${gw}`, payload);
      // Keep the Points "My Team" pitch in sync immediately. That pitch reads
      // window.MY_LINEUP for the live/upcoming GW; without this it stays on
      // the pre-save (or a fabricated squad-default) lineup until a full reload
      // — exactly the "I saved but Points shows my old squad" bug.
      window.MY_LINEUP = {
        starting: lineup.starting.map(String),
        bench: lineup.bench.map(String),
        formation: lineup.formation,
        autoSubs: [],
      };
      // The save IS the new truth: refresh the edit-lineup cache so the next
      // tab visit renders this instantly, and clear the unsaved-edits flag so
      // background revalidations may flow again.
      dirtyRef.current = false;
      WCStore.set("editLineup", {
        gw,
        lineup: {
          starting: lineup.starting.map(String),
          bench: lineup.bench.map(String),
          formation: lineup.formation,
          autoSubs: [],
        },
      }, `${lid}|${window.ME}`);
      setToast({ type: "success", message: `Lineup saved for GW${gw}!` });
    } catch(err) {
      setToast({
        type: "error",
        message: "Failed to save lineup: " + (err.error || err.detail || JSON.stringify(err))
      });
    }
  };

  const handlePlayerClick = id => {
    if (!selected) {
      setSelected(id);
      return;
    }
    if (selected === id) { setSelected(null); return; }

    // Check swap legality to prevent clicking disabled/unclickable options
    if (typeof isSwapLegal === "function" && !isSwapLegal(lineup, selected, id)) {
      return;
    }

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

    // A manual swap = unsaved local edits: block background revalidations
    // from overwriting until saved or reset.
    dirtyRef.current = true;
    setLineup({
      ...lineup,
      starting: newStarting,
      bench: newBench,
      formation: [gk, def, mid, fwd]
    });
    setSelected(null);
  };

  // Reset = discard unsaved edits and restore the SAVED edit-GW lineup (from
  // the cache row; squad carry-forward when none saved) — NOT the viewed
  // (Points) lineup the old button restored.
  const handleResetLineup = () => {
    dirtyRef.current = false;
    const lu = _rowToLineup(editRow, squadRow);
    if (lu) setLineup(lu);
    setSelected(null);
  };

  return { isMobile, view, setView, lineup, setLineup, selected, toast, setToast, editGw, handleSaveLineup, handlePlayerClick, handleResetLineup };
}

function PickTeamScreen({ onTab, squadLoading }) {
  const { isMobile, view, setView, lineup, setLineup, selected, toast, setToast, editGw, handleSaveLineup, handlePlayerClick, handleResetLineup } = usePickTeamScreen();

  // While an authenticated user's real squad is still loading — or the edit
  // GW's own lineup hasn't resolved yet (lineup === null) — show a skeleton.
  // Nothing but the edit-GW lineup itself may ever render on this screen.
  if (squadLoading || !lineup) {
    return (
      <div className="col" style={{ gap: 16 }}>
        <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>My Team</h2>
        <div className="card" style={{ padding: 28, display: "flex", flexDirection: "column", gap: 12, alignItems: "center" }}>
          <div style={{ color: "var(--ink-500)", fontSize: 13, fontWeight: 700 }}>Loading your squad…</div>
          {[0, 1, 2, 3].map(i => (
            <div key={i} style={{ display: "flex", gap: 10, justifyContent: "center", width: "100%" }}>
              {Array.from({ length: 4 - (i === 0 ? 3 : 0) }).map((_, k) => (
                <Skel key={k} w={64} h={54} style={{ borderRadius: 10, opacity: 0.18 }} />
              ))}
            </div>
          ))}
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
      <h2 className="h-display" style={{ fontSize: 26, margin: 0, display: "flex", alignItems: "center", gap: 12 }}><ManagerFlag uid={window.ME} size="xl" /> My Team <span className="muted" style={{ fontSize: 15, fontWeight: 500 }}>· Setting GW{editGw}</span></h2>

      {/* Prominent lineup-deadline countdown (lock = T0 - 1h of the EDIT GW). */}
      {(() => {
        const lockAt = lineupLockForGw(editGw);
        const locked = lockAt && Date.parse(lockAt) <= Date.now();
        return (
          <div className="card" style={{ padding: "14px 18px", display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, borderLeft: `4px solid ${locked ? "var(--red-500)" : "var(--green-500)"}` }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-500)" }}>GW{editGw} lineup deadline</div>
              <div style={{ fontSize: 14, marginTop: 2 }}>
                {lockAt ? <>Locks {fmtWindowTime(lockAt)}</> : "Deadline not set yet"}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              {locked
                ? <span style={{ fontWeight: 800, color: "var(--red-500)", fontSize: 18 }}>Locked</span>
                : <span style={{ fontFamily: "var(--font-num)", fontWeight: 800, fontSize: 24, color: "var(--navy-900)" }}><Countdown to={lockAt} placeholder="—" /></span>}
            </div>
          </div>
        );
      })()}

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

      <div className="card-dark" style={{ padding: isMobile ? 12 : 18 }}>
        {/* tabs */}
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
          <div style={{ display: "inline-flex", padding: 4, background: "rgba(0,0,0,0.25)", borderRadius: 999 }}>
            <button className={"btn " + (view === "pitch" ? "btn--primary" : "")} style={{ padding: isMobile ? "11px 18px" : "6px 18px", fontSize: 12, minHeight: isMobile ? 40 : undefined, background: view === "pitch" ? undefined : "transparent", color: view === "pitch" ? undefined : "white" }} onClick={() => setView("pitch")}>Pitch View</button>
            <button className={"btn " + (view === "list" ? "btn--primary" : "")} style={{ padding: isMobile ? "11px 18px" : "6px 18px", fontSize: 12, minHeight: isMobile ? 40 : undefined, background: view === "list" ? undefined : "transparent", color: view === "list" ? undefined : "white" }} onClick={() => setView("list")}>List View</button>
          </div>
        </div>


        {/* Cards show the EDIT gw's opponents (matches the Save button). */}
        <FixtureGwContext.Provider value={editGw}>
          <Pitch lineup={lineup} mode="pick" selected={selected} onPlayerClick={handlePlayerClick} />
        </FixtureGwContext.Provider>

        <div className="pickteam-savebar" style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 16 }}>
          <button className="btn btn--ghost" onClick={handleResetLineup}>Reset</button>
          <button onClick={handleSaveLineup} className="btn btn--primary" style={{ minWidth: isMobile ? 0 : 200, flex: isMobile ? 1 : undefined }}>Save Lineup for GW{editGw}</button>
        </div>
        <div style={{ textAlign: "center", marginTop: 10, fontSize: 12, color: "rgba(255,255,255,0.7)" }}>
          {(() => {
            const lockAt = lineupLockForGw(editGw);
            if (!lockAt) return "Deadline set once GW fixtures are scheduled";
            return Date.parse(lockAt) <= Date.now()
              ? <>GW{editGw} lineup is locked</>
              : <>Locks {fmtWindowTime(lockAt)} · <Countdown to={lockAt} suffix=" remaining" /></>;
          })()}
        </div>
      </div>

      {toast && (
        <div className={`toast-message toast-message--${toast.type}`} onClick={() => setToast(null)}>
          <span className="toast-message__icon">
            {toast.type === "success" ? "✓" : "✕"}
          </span>
          <span className="toast-message__text">{toast.message}</span>
          <button className="toast-message__close">×</button>
        </div>
      )}
    </div>
  );
}

Object.assign(window, { StatusScreen, PointsScreen, PickTeamScreen, AdminWindowSwitcher });
