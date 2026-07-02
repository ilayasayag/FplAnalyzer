// =====================================================================
// WC26 — Screens: Draft Room (live snake draft) + Create/Join League

// Real group-stage fixtures (3 rounds × 24). Used to show each squad player's
// upcoming opponents (GW1→GW3) instead of mock points in the Draft Room.
const GROUP_FIXTURES = {
  1: [["MEX","RSA"],["KOR","CZE"],["CAN","BOS"],["USA","PAR"],["QAT","SWI"],["BRA","MOR"],
      ["HAI","SCO"],["AUS","TUR"],["GER","CUW"],["NED","JAP"],["CIV","ECU"],["SWE","TUN"],
      ["SPA","CPV"],["BEL","EGY"],["SAU","URU"],["IRA","NZL"],["FRA","SEN"],["IRQ","NOR"],
      ["ARG","ALG"],["AUT","JOR"],["POR","COD"],["ENG","CRO"],["GHA","PAN"],["UZB","COL"]],
  2: [["CZE","RSA"],["SWI","BOS"],["CAN","QAT"],["MEX","KOR"],["USA","AUS"],["SCO","MOR"],
      ["BRA","HAI"],["TUR","PAR"],["NED","SWE"],["GER","CIV"],["ECU","CUW"],["TUN","JAP"],
      ["SPA","SAU"],["BEL","IRA"],["URU","CPV"],["NZL","EGY"],["ARG","AUT"],["FRA","IRQ"],
      ["NOR","SEN"],["JOR","ALG"],["POR","UZB"],["ENG","GHA"],["PAN","CRO"],["COL","COD"]],
  3: [["SWI","CAN"],["BOS","QAT"],["MOR","HAI"],["SCO","BRA"],["RSA","KOR"],["CZE","MEX"],
      ["ECU","GER"],["CUW","CIV"],["TUN","NED"],["JAP","SWE"],["TUR","USA"],["PAR","AUS"],
      ["NOR","FRA"],["SEN","IRQ"],["URU","SPA"],["CPV","SAU"],["NZL","BEL"],["EGY","IRA"],
      ["CRO","GHA"],["PAN","ENG"],["COD","UZB"],["COL","POR"],["JOR","ARG"],["ALG","AUT"]],
};
const GROUP_OPPONENTS = (() => {
  const m = {};
  [1, 2, 3].forEach(gw => GROUP_FIXTURES[gw].forEach(([h, a]) => {
    (m[h] = m[h] || [])[gw - 1] = a;
    (m[a] = m[a] || [])[gw - 1] = h;
  }));
  return m;
})();
// =====================================================================

const getNormalizedPlayerId = (id) => {
  if (id === null || id === undefined) return "";
  if (typeof id === "number") return id;
  const num = Number(id);
  if (!isNaN(num)) return num;
  const cleaned = String(id).replace("p_", "");
  const numCleaned = Number(cleaned);
  if (!isNaN(numCleaned)) return numCleaned;
  return id;
};

// ---------- DRAFT ROOM ----------
function useDraftRoom() {
  const isMobile = useIsMobile();
  // Mobile-only: which stacked panel is visible (watchlist | pool | squad).
  const [mobilePanel, setMobilePanel] = React.useState("pool");
  // The clock reflects the REAL server deadline (DRAFT_STATE.secondsLeft), not a
  // hardcoded countdown. 0 when no draft is running for the active league.
  const serverSeconds = (typeof DRAFT_STATE !== "undefined" && DRAFT_STATE.secondsLeft) ? DRAFT_STATE.secondsLeft : 0;
  const isPaused = (typeof DRAFT_STATE !== "undefined") ? DRAFT_STATE.paused : false;
  const [secondsLeft, setSecondsLeft] = React.useState(serverSeconds);
  const [search, setSearch] = React.useState("");
  const [posFilter, setPosFilter] = React.useState("all");
  // Watchlist: ordered array of player IDs (numbers) — order is the auto-pick priority.
  // Derived Set used for O(1) membership checks in the pool render.
  const [watchlistIds, setWatchlistIds] = React.useState([]);
  const [loadingWatchlist, setLoadingWatchlist] = React.useState(false);
  const [draggedIdx, setDraggedIdx] = React.useState(null);
  const watchlistSet = React.useMemo(() => new Set(watchlistIds.map(getNormalizedPlayerId)), [watchlistIds]);
  const [nationFilter, setNationFilter] = React.useState("all");
  const [page, setPage] = React.useState(0);
  const PAGE_SIZE = 30;
  // Watchlist panel display filters (display-only; saved order unchanged)
  const [wlPos, setWlPos] = React.useState("all");
  const [wlNation, setWlNation] = React.useState("all");
  const [wlStatus, setWlStatus] = React.useState("all"); // all | available | picked

  const handleDraftPick = async (playerId) => {
    try {
      const lid = LEAGUE.id;
      const idKey = Math.random().toString(36).substring(2) + Date.now().toString(36);
      const numericId = isNaN(Number(playerId)) ? Number(String(playerId).replace("p_", "")) : Number(playerId);
      await apiCall("POST", `/leagues/${lid}/draft/pick`, { playerId: numericId, idempotencyKey: idKey });
    } catch(err) {
      alert("Draft pick failed: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  // Save watchlist order to server.
  const saveWatchlist = async (ids) => {
    const lid = (typeof LEAGUE !== "undefined") ? LEAGUE.id : null;
    if (!lid) return;
    try {
      await apiCall("PUT", `/leagues/${lid}/draft/watchlist`, { playerIds: ids });
    } catch(err) {
      console.error("Failed to save watchlist:", err);
    }
  };

  // Toggle a player in/out of the watchlist, then persist.
  const handleToggleWatchlist = async (playerId) => {
    const id = getNormalizedPlayerId(playerId);
    const newIds = watchlistSet.has(id)
      ? watchlistIds.map(getNormalizedPlayerId).filter(x => x !== id)
      : [...watchlistIds.map(getNormalizedPlayerId), id];
    setWatchlistIds(newIds);
    await saveWatchlist(newIds);
  };

  // Load this manager's watchlist from the server on mount.
  React.useEffect(() => {
    const lid = (typeof LEAGUE !== "undefined") ? LEAGUE.id : null;
    if (!lid) return;
    setLoadingWatchlist(true);
    apiCall("GET", `/leagues/${lid}/draft/watchlist`)
      .then(res => { if (res && res.playerIds) setWatchlistIds(res.playerIds.map(Number)); })
      .catch(err => console.warn("Failed to load watchlist:", err))
      .finally(() => setLoadingWatchlist(false));
  }, []);

  // Emergency pause / resume — any manager may fire it; the server freezes all
  // picks and stores the seconds left so resume continues exactly where it was.
  const [pauseBusy, setPauseBusy] = React.useState(false);
  const handlePauseResume = async () => {
    const lid = (typeof LEAGUE !== "undefined") ? LEAGUE.id : null;
    if (!lid || pauseBusy) return;
    setPauseBusy(true);
    try {
      await apiCall("POST", `/leagues/${lid}/draft/${isPaused ? "resume" : "pause"}`);
    } catch (err) {
      alert("Failed to " + (isPaused ? "resume" : "pause") + ": " + (err.error || err.detail || JSON.stringify(err)));
    } finally {
      setPauseBusy(false);
    }
  };

  // Start the draft (league admin only — server enforces adminUid).
  const [startBusy, setStartBusy] = React.useState(false);
  const handleStartDraft = async () => {
    const lid = (typeof LEAGUE !== "undefined") ? LEAGUE.id : null;
    if (!lid || startBusy) return;
    if (!window.confirm("Start the draft now for everyone? The first pick clock begins immediately.")) return;
    setStartBusy(true);
    try {
      await apiCall("POST", `/leagues/${lid}/draft/start`);
    } catch (err) {
      alert("Failed to start draft: " + (err.error || err.detail || JSON.stringify(err)));
    } finally {
      setStartBusy(false);
    }
  };
  const isLeagueAdmin = (typeof LEAGUE !== "undefined") && LEAGUE.admin
    ? LEAGUE.admin === window.ME : true;

  // ← Undo last pick (admin): one press = one pick back. Handles the whole
  // pause -> rollback -> resume cycle itself, so pressing it 3 times rewinds
  // 3 picks. The server rebuilds pickedPlayerIds deduped on every rollback.
  const [rollbackBusy, setRollbackBusy] = React.useState(false);
  const handleUndoLastPick = async () => {
    const lid = (typeof LEAGUE !== "undefined") ? LEAGUE.id : null;
    if (!lid || rollbackBusy) return;
    const last = DRAFT_HISTORY[DRAFT_HISTORY.length - 1];
    if (!last) return;
    const mgr = managerById(last.uid) || { name: last.uid };
    const pl = playerById(last.playerId) || { name: last.playerId };
    if (!window.confirm(`Undo the last pick?\n\n#${last.overall} ${mgr.name}: ${pl.name} is removed and ${mgr.name} picks again with a fresh clock.`)) return;
    setRollbackBusy(true);
    try {
      const wasPaused = isPaused;
      if (!wasPaused) await apiCall("POST", `/leagues/${lid}/draft/pause`);
      await apiCall("POST", `/leagues/${lid}/draft/rollback`, { toPick: last.overall - 1 });
      await apiCall("POST", `/leagues/${lid}/draft/resume`);
      // Optimistic local trim so an immediate second press targets the
      // PREVIOUS pick (the 2.5s poll re-syncs the truth right after).
      window.DRAFT_HISTORY = DRAFT_HISTORY.slice(0, -1);
    } catch (err) {
      alert("Undo failed: " + (err.error || err.detail || JSON.stringify(err)));
    } finally {
      setRollbackBusy(false);
    }
  };

  const lastPickRef = React.useRef(DRAFT_STATE.pickOverall);
  const lastPausedRef = React.useRef(isPaused);

  React.useEffect(() => {
    if (draftNotStarted) {
      setSecondsLeft(0);
      return;
    }
    const timerVal = (typeof DRAFT_STATE !== "undefined" && DRAFT_STATE.pickTimer) ? DRAFT_STATE.pickTimer : 30;
    
    if (DRAFT_STATE.pickOverall !== lastPickRef.current) {
      setSecondsLeft(timerVal);
    } else if (lastPausedRef.current && !isPaused) {
      // Resume continues with the seconds saved at pause — sync from the
      // server-computed remaining instead of resetting to a full clock.
      setSecondsLeft(Math.max(0, DRAFT_STATE.secondsLeft != null ? DRAFT_STATE.secondsLeft : timerVal));
    }
    
    lastPickRef.current = DRAFT_STATE.pickOverall;
    lastPausedRef.current = isPaused;
  }, [DRAFT_STATE.pickOverall, isPaused]);

  React.useEffect(() => {
    const t = setInterval(() => {
      setSecondsLeft(s => {
        if (isPaused) return s;
        return Math.max(0, s - 1);
      });
    }, 1000);
    return () => clearInterval(t);
  }, [isPaused]);

  // Auto-pick watchdog: when the on-screen timer hits 0 AND a draft is active,
  // fire /draft/auto-pick. Any client in the room can fire this — the engine
  // gates on time.time() >= pickDeadline and on currentPick (it advances after
  // the first successful call, so racing clients just get a harmless 400).
  // Once per deadline epoch: keyed off the server pickDeadline so we don't
  // re-fire after the pick advances.
  const lastFiredFor = React.useRef(null);
  React.useEffect(() => {
    const deadline = (typeof DRAFT_STATE !== "undefined") ? DRAFT_STATE.pickDeadline : null;
    const status = (typeof DRAFT_STATE !== "undefined") ? DRAFT_STATE.status : null;
    if (isPaused) return;
    if (secondsLeft === 0 && status === "active" && deadline && lastFiredFor.current !== deadline) {
      lastFiredFor.current = deadline;
      const lid = (typeof LEAGUE !== "undefined") ? LEAGUE.id : null;
      if (!lid) return;
      apiCall("POST", `/leagues/${lid}/draft/auto-pick`).catch((err) => {
        // Expected: another client already fired it, or the deadline hasn't
        // actually elapsed on the server clock. Swallow silently — but RE-ARM
        // after a short delay so a transient conflict can't stall the draft
        // (the old once-per-deadline latch never retried).
        console.debug("auto-pick declined:", err && (err.error || err.detail));
        setTimeout(() => {
          if (lastFiredFor.current === deadline) lastFiredFor.current = null;
        }, 3000);
      });
    }
  }, [secondsLeft, isPaused]);

  const onClock = managerById(DRAFT_STATE.onTheClock) || { name: "TBD", team: "Draft Pending", flag: "GER" };

  // Players already picked
  const taken = new Set(DRAFT_HISTORY.map(p => getNormalizedPlayerId(p.playerId)));
  // Get unique nations list
  const activePlayers = window.PLAYERS || PLAYERS;
  const nationsList = React.useMemo(() => {
    const list = [];
    const seen = new Set();
    activePlayers.forEach(p => {
      const code = p.team;
      if (code && !seen.has(code)) {
        seen.add(code);
        const t = teamById(code) || { name: code };
        list.push({ code, name: t.name || code });
      }
    });
    return list.sort((a, b) => a.name.localeCompare(b.name));
  }, [activePlayers]);

  const pool = activePlayers.filter(p => {
    if (taken.has(getNormalizedPlayerId(p.id))) return false;
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (posFilter !== "all" && p.pos !== Number(posFilter)) return false;
    if (nationFilter !== "all" && p.team !== nationFilter) return false;
    return true;
  }).sort((a, b) => a.dr - b.dr);

  const totalPool = pool.length;
  const startIdx = page * PAGE_SIZE;
  const visiblePool = pool.slice(startIdx, startIdx + PAGE_SIZE);

  const sidebarOrder = (DRAFT_STATE.order && DRAFT_STATE.order.length > 0)
    ? DRAFT_STATE.order.map(uid => managerById(uid)).filter(Boolean)
    : MANAGERS;

  // Snake order projection for next ~10 picks
  const upcoming = [];
  let pickN = DRAFT_STATE.pickOverall || 1;
  let round = DRAFT_STATE.round || 1;
  let inRound = DRAFT_STATE.pickInRound || 1;
  const numManagers = sidebarOrder.length || 10;
  while (upcoming.length < 8 && pickN <= (numManagers * 15)) {
    const order = round % 2 === 1 ? sidebarOrder : [...sidebarOrder].reverse();
    const uid = order[inRound - 1]?.uid;
    upcoming.push({ overall: pickN, round, uid });
    pickN++;
    inRound++;
    if (inRound > numManagers) { round++; inRound = 1; }
  }

  // Project all draft picks to find when ME picks next
  let picksUntilMyTurn = null;
  let roundsUntilMyTurn = null;
  if (typeof DRAFT_STATE !== "undefined" && typeof ME !== "undefined") {
    const currentPick = DRAFT_STATE.pickOverall || 1;
    const onClockUid = DRAFT_STATE.onTheClock;
    const isMeOnClock = onClockUid === ME;
    const searchStart = isMeOnClock ? currentPick + 1 : currentPick;
    const numM = sidebarOrder.length || 10;
    
    let nextMyPickOverall = null;
    let nextMyPickRound = null;
    
    let pN = 1;
    let r = 1;
    let iR = 1;
    while (pN <= (numM * 15)) {
      const order = r % 2 === 1 ? sidebarOrder : [...sidebarOrder].reverse();
      const uid = order[iR - 1]?.uid;
      
      if (pN >= searchStart && uid === ME) {
        nextMyPickOverall = pN;
        nextMyPickRound = r;
        break;
      }
      
      pN++;
      iR++;
      if (iR > numM) { r++; iR = 1; }
    }
    
    if (nextMyPickOverall !== null) {
      picksUntilMyTurn = nextMyPickOverall - currentPick;
      roundsUntilMyTurn = nextMyPickRound - (DRAFT_STATE.round || 1);
    }
  }

  // My squad so far
  const myPicks = DRAFT_HISTORY.filter(p => p.uid === window.ME);
  const mySquadByPos = { 1: 0, 2: 0, 3: 0, 4: 0 };
  const myNationCounts = {};
  myPicks.forEach(p => {
    const pl = playerById(p.playerId);
    if (!pl) return;
    mySquadByPos[pl.pos]++;
    if (pl.team) myNationCounts[pl.team] = (myNationCounts[pl.team] || 0) + 1;
  });

  // Why can't I pick this player? null = eligible. Mirrors the server rules
  // (position quota 2/5/5/3 + max 3 per nation) so the UI greys/blocks instead
  // of letting a click bounce off a 400.
  const POS_QUOTA = { 1: 2, 2: 5, 3: 5, 4: 3 };
  const NATION_MAX = 3;
  const ineligibleReason = (p) => {
    if (!p) return null;
    if (taken.has(getNormalizedPlayerId(p.id))) return "TAKEN";
    if (mySquadByPos[p.pos] >= POS_QUOTA[p.pos]) return "POS FULL";
    if ((myNationCounts[p.team] || 0) >= NATION_MAX) return "NATION MAX";
    return null;
  };

  const formatTime = s => `0:${String(s).padStart(2, "0")}`;

  // A league whose draft doc is absent/empty (e.g. a pre_draft league) has no
  // live draft. Show a clear notice instead of a misleading "running" board.
  const draftNotStarted = (typeof DRAFT_STATE !== "undefined") && (DRAFT_STATE.notStarted || !DRAFT_STATE.round) && DRAFT_HISTORY.length === 0;

  // Full watchlist with eligibility status. Ineligible entries stay visible
  // (greyed + reason tag) so the ranked order is preserved; filters below are
  // display-only. availableCount drives the header badge.
  const watchlistRows = watchlistIds.map((id, idx) => {
    const p = playerById(id);
    return { id, idx, p, reason: p ? ineligibleReason(p) : "TAKEN" };
  }).filter(r => r.p);
  const availableCount = watchlistRows.filter(r => !r.reason).length;
  const visibleWatchlist = watchlistRows.filter(r => {
    if (wlPos !== "all" && r.p.pos !== Number(wlPos)) return false;
    if (wlNation !== "all" && r.p.team !== wlNation) return false;
    if (wlStatus === "available" && r.reason) return false;
    if (wlStatus === "picked" && r.reason !== "TAKEN") return false;
    return true;
  });
  const wlNations = [...new Set(watchlistRows.map(r => r.p.team).filter(Boolean))].sort();

  const onClockName = draftNotStarted ? "—" : (onClock.name || "—");

  // Duplicate-pick detector: the same player on two squads means corrupted
  // state — surface it loudly so the admin pauses + rolls back.
  const duplicatePicks = (() => {
    const seen = {}; const dups = [];
    DRAFT_HISTORY.forEach(p => {
      if (seen[p.playerId]) dups.push(p); else seen[p.playerId] = p;
    });
    return dups;
  })();

  return {
    isMobile, mobilePanel, setMobilePanel,
    isPaused, secondsLeft, draftNotStarted,
    search, setSearch, posFilter, setPosFilter,
    watchlistIds, setWatchlistIds, loadingWatchlist, draggedIdx, setDraggedIdx,
    watchlistSet, nationFilter, setNationFilter,
    page, setPage, PAGE_SIZE,
    wlPos, setWlPos, wlNation, setWlNation, wlStatus, setWlStatus,
    handleDraftPick, saveWatchlist, handleToggleWatchlist,
    handlePauseResume, pauseBusy, handleStartDraft, startBusy,
    handleUndoLastPick, rollbackBusy, isLeagueAdmin,
    onClock, onClockName, taken, nationsList, pool, visiblePool,
    totalPool, startIdx, sidebarOrder, upcoming,
    picksUntilMyTurn, myPicks, mySquadByPos, myNationCounts,
    POS_QUOTA, NATION_MAX, ineligibleReason, formatTime,
    watchlistRows, availableCount, visibleWatchlist, wlNations,
    duplicatePicks,
  };
}

function DraftRoomScreen({ onTab }) {
  const {
    isMobile, mobilePanel, setMobilePanel,
    isPaused, secondsLeft, draftNotStarted,
    search, setSearch, posFilter, setPosFilter,
    watchlistIds, setWatchlistIds, loadingWatchlist, draggedIdx, setDraggedIdx,
    watchlistSet, nationFilter, setNationFilter,
    page, setPage, PAGE_SIZE,
    wlPos, setWlPos, wlNation, setWlNation, wlStatus, setWlStatus,
    handleDraftPick, saveWatchlist, handleToggleWatchlist,
    handlePauseResume, pauseBusy, handleStartDraft, startBusy,
    handleUndoLastPick, rollbackBusy, isLeagueAdmin,
    onClock, onClockName, taken, nationsList, pool, visiblePool,
    totalPool, startIdx, sidebarOrder, upcoming,
    picksUntilMyTurn, myPicks, mySquadByPos, myNationCounts,
    POS_QUOTA, NATION_MAX, ineligibleReason, formatTime,
    watchlistRows, availableCount, visibleWatchlist, wlNations,
    duplicatePicks,
  } = useDraftRoom();

  // ---- Shared panel JSX. Rendered into the desktop 3-column grid (unchanged
  // ---- output) or the mobile stacked view with chip-switched panels.
  const notStartedBanner = draftNotStarted && (
    <div style={{ gridColumn: "1 / -1", background: "rgba(74,27,168,0.22)", border: "1px solid rgba(167,139,250,0.45)", borderRadius: 10, padding: "12px 16px", color: "#d9ccff", fontSize: 13, fontWeight: 600 }}>
      ⏳ This league's draft hasn't started yet. The order below is a preview — live picks begin when the draft opens.
    </div>
  );

  const dupBanner = duplicatePicks.length > 0 && (
    <div style={{ gridColumn: "1 / -1", background: "var(--red-500)", borderRadius: 10, padding: "12px 16px", color: "white", fontSize: 13, fontWeight: 700 }}>
      🚨 Duplicate pick detected: {duplicatePicks.map(p => `${(playerById(p.playerId)||{}).name||p.playerId} (pick #${p.overall})`).join(", ")} — the same player is on two squads.
      {isLeagueAdmin ? " Use ← Undo last pick (repeat until past the duplicate)." : " Ask the league admin to undo."}
    </div>
  );

  /* LEFT COLUMN — Watchlist */
  const watchlistPanel = (
      <div className="col" style={{ gap: 12, height: "100%" }}>
        {/* Watchlist */}
        <div className="card-dark" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
          <div className="card-dark__title">
            ★ Watchlist ({availableCount}/{watchlistRows.length})
            {loadingWatchlist && <span style={{ fontSize: 10, fontWeight: 400, marginLeft: 6, opacity: 0.6 }}>loading…</span>}
          </div>
          {/* Display-only filters: position / nation / availability */}
          <div style={{ display: "flex", gap: 5, padding: "8px 10px", flexWrap: "wrap", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
            {["all", "1", "2", "3", "4"].map(p => (
              <button key={p}
                style={{ padding: isMobile ? "10px 12px" : "3px 8px", fontSize: isMobile ? 11 : 10, fontWeight: 700, borderRadius: 999, border: "none", cursor: "pointer",
                  background: wlPos === p ? "var(--green-400)" : "rgba(255,255,255,0.08)",
                  color: wlPos === p ? "var(--navy-900)" : "white" }}
                onClick={() => setWlPos(p)}>
                {p === "all" ? "ALL" : POS_NAMES[Number(p)]}
              </button>
            ))}
            <select value={wlNation} onChange={e => setWlNation(e.target.value)}
              style={{ padding: isMobile ? "9px 8px" : "2px 6px", fontSize: isMobile ? 11 : 10, fontWeight: 700, borderRadius: 999, border: "1px solid rgba(255,255,255,0.15)", background: "rgba(255,255,255,0.08)", color: "white" }}>
              <option value="all" style={{ background: "var(--navy-900)" }}>All nations</option>
              {wlNations.map(n => <option key={n} value={n} style={{ background: "var(--navy-900)" }}>{n}</option>)}
            </select>
            <select value={wlStatus} onChange={e => setWlStatus(e.target.value)}
              style={{ padding: isMobile ? "9px 8px" : "2px 6px", fontSize: isMobile ? 11 : 10, fontWeight: 700, borderRadius: 999, border: "1px solid rgba(255,255,255,0.15)", background: "rgba(255,255,255,0.08)", color: "white" }}>
              <option value="all" style={{ background: "var(--navy-900)" }}>All</option>
              <option value="available" style={{ background: "var(--navy-900)" }}>Available</option>
              <option value="picked" style={{ background: "var(--navy-900)" }}>Picked</option>
            </select>
          </div>
          {visibleWatchlist.length === 0 ? (
            <div className="card-section" style={{ textAlign: "center", color: "rgba(255,255,255,0.5)", fontSize: 12, padding: "14px 16px", lineHeight: 1.5 }}>
              {watchlistRows.length === 0
                ? <span>Star players (☆) to queue them.<br />Auto-pick uses this order.</span>
                : <span>No watchlist players match these filters.</span>}
            </div>
          ) : (
            <div style={{ overflowY: "auto", flex: 1 }}>
              {visibleWatchlist.map(({ id, idx, p, reason }) => {
                const t = teamById(p.team);
                const grey = !!reason;
                const tagColor = reason === "TAKEN" ? "#f87171" : "#f5c518";
                return (
                  <div
                    key={id}
                    draggable={true}
                    onDragStart={() => setDraggedIdx(idx)}
                    onDragOver={e => e.preventDefault()}
                    onDrop={async () => {
                      if (draggedIdx === null || draggedIdx === idx) { setDraggedIdx(null); return; }
                      const reordered = [...watchlistIds];
                      const [moved] = reordered.splice(draggedIdx, 1);
                      reordered.splice(idx, 0, moved);
                      setWatchlistIds(reordered);
                      setDraggedIdx(null);
                      await saveWatchlist(reordered);
                    }}
                    className="card-section"
                    style={{ display: "flex", alignItems: "center", gap: 7, padding: "12px 14px", cursor: "grab", opacity: grey ? 0.45 : 1 }}
                  >
                    <span style={{ color: "rgba(255,255,255,0.25)", fontSize: 13, userSelect: "none", flexShrink: 0 }}>⣿</span>
                    <span className="mono" style={{ color: "rgba(255,255,255,0.65)", fontSize: 12, minWidth: 16, flexShrink: 0 }}>{idx + 1}</span>
                    <div
                      style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 7, cursor: "pointer" }}
                      onClick={() => window.dispatchEvent(new CustomEvent('show-player-stats', { detail: { id: p.id } }))}
                    >
                      <div style={{ width: 24, height: 24, flexShrink: 0 }}><Jersey team={t} pos={p.pos} /></div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 700, fontSize: 14, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "white", textDecoration: grey && reason === "TAKEN" ? "line-through" : "underline", decorationColor: "rgba(255,255,255,0.15)" }}>{p.name}</div>
                        <div style={{ color: "#cbd5e1", fontSize: 12, fontWeight: 700 }}>
                          {t.id} · {POS_NAMES[p.pos]}
                          {reason && <span style={{ marginLeft: 6, fontSize: isMobile ? 11 : 9, fontWeight: 800, padding: "1px 5px", borderRadius: 4, background: "rgba(0,0,0,0.35)", color: tagColor }}>{reason}</span>}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDraftPick(id)}
                      className="btn btn--draft"
                      style={{ padding: isMobile ? "10px 12px" : "3px 8px", fontSize: isMobile ? 11 : 10, flexShrink: 0 }}
                      disabled={!DRAFT_STATE.isMyTurn || grey}
                      title={reason || ""}
                    >Pick</button>
                    <button
                      onClick={() => handleToggleWatchlist(id)}
                      style={{ padding: isMobile ? "10px 10px" : "3px 5px", fontSize: isMobile ? 14 : 11, background: "transparent", color: "rgba(255,255,255,0.35)", flexShrink: 0 }}
                      title="Remove from watchlist"
                    >✕</button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
  );

  /* CENTER — Clock card (always rendered on top in the mobile view) */
  const clockCard = (
        <div className="card-dark" style={{ padding: isMobile ? "14px 16px" : "20px 24px", display: "grid", gridTemplateColumns: isMobile ? "1fr auto" : "1fr auto 1fr", alignItems: "center", gap: isMobile ? 12 : 20 }}>
          <div>
            <div style={{
              fontSize: isMobile ? 12 : 16,
              fontWeight: 900,
              color: "white",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              background: "linear-gradient(90deg, #10b981, #059669)",
              padding: "6px 12px",
              borderRadius: 6,
              display: "inline-block",
              boxShadow: "0 2px 4px rgba(0,0,0,0.15)"
            }}>
              {draftNotStarted ? "PRE-DRAFT" : `ROUND ${DRAFT_STATE.round} · PICK ${DRAFT_STATE.pickOverall}`}
            </div>
            <div style={{ fontSize: 11, fontWeight: 800, color: "var(--green-400)", letterSpacing: "0.08em", textTransform: "uppercase", marginTop: 14 }}>
              On The Clock
            </div>
            <div className="h-display" style={{
              fontSize: isMobile ? 26 : 48,
              color: "#ffffff",
              marginTop: 4, 
              fontWeight: 900, 
              letterSpacing: "-0.03em",
              textTransform: "uppercase",
              textShadow: "0 0 12px rgba(255,255,255,0.2)"
            }}>
              {onClockName}
            </div>
          </div>
          <div style={{
            width: isMobile ? 92 : 130, height: isMobile ? 92 : 130,
            border: "5px solid " + (isPaused ? "var(--gold-500)" : (secondsLeft <= 15 ? "var(--red-500)" : (draftNotStarted ? "#334155" : "var(--green-400)"))),
            borderRadius: "50%",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexDirection: "column",
            position: "relative",
          }}>
            <div className="mono" style={{ fontSize: isPaused ? (isMobile ? 15 : 24) : (isMobile ? 26 : 36), fontWeight: 800, color: (draftNotStarted && !isPaused) ? "#475569" : "white", lineHeight: 1 }}>
              {isPaused ? "PAUSED" : (draftNotStarted ? "0:00" : formatTime(secondsLeft))}
            </div>
            <div style={{ fontSize: 9, fontWeight: 800, color: "rgba(255,255,255,0.6)", letterSpacing: "0.1em", marginTop: 2 }}>
              {isPaused ? `(${formatTime(secondsLeft)})` : "SECONDS"}
            </div>
          </div>
          <div style={{ textAlign: "right", ...(isMobile ? { gridColumn: "1 / -1" } : {}) }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: "rgba(255,255,255,0.4)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Next Up</div>
            <div style={{ 
              fontSize: 16, 
              color: "rgba(255,255,255,0.45)", 
              marginTop: 6, 
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.05em"
            }}>
              {draftNotStarted ? "—" : (upcoming[1] ? managerById(upcoming[1].uid).name : "—")}
            </div>
            {!draftNotStarted && !DRAFT_STATE.complete && (
              <button
                onClick={handlePauseResume}
                disabled={pauseBusy}
                title={isPaused ? "Resume the draft with the same clock" : "Emergency pause — freezes picks for everyone"}
                style={{
                  marginTop: 10, padding: isMobile ? "11px 16px" : "7px 14px", fontSize: 12, fontWeight: 800,
                  borderRadius: 8, border: "none", cursor: "pointer", letterSpacing: "0.04em",
                  background: isPaused ? "var(--green-400)" : "rgba(255,170,0,0.18)",
                  color: isPaused ? "var(--navy-900)" : "var(--gold-500)",
                  outline: isPaused ? "none" : "1px solid rgba(255,170,0,0.5)",
                }}>
                {pauseBusy ? "…" : (isPaused ? "▶ Resume draft" : "⏸ Pause draft")}
              </button>
            )}
            {!draftNotStarted && isLeagueAdmin && DRAFT_HISTORY.length > 0 && (
              <button
                onClick={handleUndoLastPick}
                disabled={rollbackBusy}
                title={(() => { const l = DRAFT_HISTORY[DRAFT_HISTORY.length - 1]; if (!l) return ""; const m = managerById(l.uid) || { name: l.uid }; const p = playerById(l.playerId) || { name: l.playerId }; return `Undo #${l.overall} ${m.name}: ${p.name}`; })()}
                style={{
                  marginTop: 8, padding: isMobile ? "11px 16px" : "7px 14px", fontSize: 12, fontWeight: 800,
                  borderRadius: 8, border: "1px solid rgba(255,255,255,0.25)", cursor: "pointer",
                  background: "rgba(255,255,255,0.10)", color: "white", letterSpacing: "0.04em",
                  display: "block",
                }}>
                {rollbackBusy ? "…" : "← Undo last pick"}
              </button>
            )}
          </div>
          {draftNotStarted ? (
            <div style={{
              gridColumn: "1 / -1",
              marginTop: 12,
              padding: "14px 20px",
              background: "rgba(255, 255, 255, 0.05)",
              border: "2px solid rgba(255, 255, 255, 0.15)",
              borderRadius: 8,
              color: "rgba(255, 255, 255, 0.6)",
              fontSize: "18px",
              fontWeight: "900",
              textAlign: "center",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              ...(isMobile ? { flexWrap: "wrap" } : {}),
              boxShadow: "0 4px 12px rgba(0,0,0,0.2)"
            }}>
              <span>⏳ Draft has not opened yet</span>
              {isLeagueAdmin && (
                <button
                  onClick={handleStartDraft}
                  disabled={startBusy}
                  style={{
                    marginLeft: 14, padding: "9px 22px", fontSize: 14, fontWeight: 900,
                    borderRadius: 8, border: "none", cursor: "pointer",
                    background: "var(--green-400)", color: "var(--navy-900)",
                    letterSpacing: "0.04em", boxShadow: "0 2px 8px rgba(0,217,107,0.35)",
                  }}>
                  {startBusy ? "Starting…" : "▶ START DRAFT"}
                </button>
              )}
            </div>
          ) : (
            picksUntilMyTurn !== null && (
              <div style={{
                gridColumn: "1 / -1",
                marginTop: 12,
                padding: "14px 20px",
                background: DRAFT_STATE.isMyTurn ? "rgba(0, 217, 107, 0.15)" : "rgba(255, 170, 0, 0.15)",
                border: DRAFT_STATE.isMyTurn ? "2px solid var(--green-400)" : "2px solid var(--gold-500)",
                borderRadius: 8,
                color: DRAFT_STATE.isMyTurn ? "var(--green-400)" : "var(--gold-500)",
                fontSize: "18px",
                fontWeight: "900",
                textAlign: "center",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                boxShadow: "0 4px 12px rgba(0,0,0,0.2)"
              }}>
                {DRAFT_STATE.isMyTurn ? (
                  <span>⚡ It's your turn to pick!</span>
                ) : (
                  <span>⏳ You pick in {picksUntilMyTurn} {picksUntilMyTurn === 1 ? "pick" : "picks"}</span>
                )}
              </div>
            )
          )}
        </div>
  );

  /* CENTER — Filters + player pool */
  const poolCard = (
        <div className="card-dark" style={{ padding: isMobile ? 14 : 18, display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1.5fr 1fr auto", gap: isMobile ? 8 : 12, marginBottom: 14 }}>
            <input
              type="text"
              placeholder="Search players…"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(0); }}
              style={{ padding: "10px 14px", borderRadius: 999, border: "1px solid var(--border-dark-strong)", background: "rgba(255,255,255,0.08)", color: "white" }}
            />
            <select
              value={nationFilter}
              onChange={e => { setNationFilter(e.target.value); setPage(0); }}
              style={{
                padding: "10px 18px", borderRadius: 999,
                border: "1px solid var(--border-dark-strong)",
                background: "rgba(255,255,255,0.08)", color: "white",
                cursor: "pointer", outline: "none",
                fontSize: 12, fontWeight: 700
              }}
            >
              <option value="all" style={{ background: "var(--navy-900)" }}>All Nations</option>
              {nationsList.map(n => (
                <option key={n.code} value={n.code} style={{ background: "var(--navy-900)" }}>
                  {n.name} ({n.code})
                </option>
              ))}
            </select>
            <div style={{ display: isMobile ? "flex" : "inline-flex", padding: 3, background: "rgba(0,0,0,0.25)", borderRadius: 999 }}>
              {["all", "1", "2", "3", "4"].map(p => (
                <button key={p}
                  style={{
                    padding: isMobile ? "11px 0" : "6px 14px", fontSize: 11, fontWeight: 700, borderRadius: 999,
                    ...(isMobile ? { flex: 1 } : {}),
                    background: posFilter === p ? "var(--green-400)" : "transparent",
                    color: posFilter === p ? "var(--navy-900)" : "white",
                  }}
                  onClick={() => { setPosFilter(p); setPage(0); }}>
                  {p === "all" ? "ALL" : POS_NAMES[Number(p)]}
                </button>
              ))}
            </div>
          </div>

          <div style={{ background: "rgba(0,0,0,0.18)", padding: "8px 12px", borderRadius: 6, fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", color: "rgba(255,255,255,0.6)", display: "grid", gridTemplateColumns: isMobile ? "minmax(0, 1fr) 52px 104px" : "1fr 120px 80px 120px", gap: 8 }}>
            <span>PLAYER</span>
            {!isMobile && <span>TEAM</span>}
            <span style={{ textAlign: "center" }}>POS</span>
            <span></span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", marginTop: 4 }}>
            {visiblePool.map(p => {
              const t = teamById(p.team);
              const isWatched = watchlistSet.has(getNormalizedPlayerId(p.id));
              return (
                <div key={p.id} style={{ display: "grid", gridTemplateColumns: isMobile ? "minmax(0, 1fr) 52px 104px" : "1fr 120px 80px 120px", gap: 8, padding: "10px 12px", borderTop: "1px solid var(--border-dark)", alignItems: "center", color: "white" }}>
                  <div
                    style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", ...(isMobile ? { minWidth: 0 } : {}) }}
                    onClick={() => window.dispatchEvent(new CustomEvent('show-player-stats', { detail: { id: p.id } }))}
                  >
                    <div style={{ width: 30, height: 30, ...(isMobile ? { flexShrink: 0 } : {}) }}><Jersey team={t} pos={p.pos} /></div>
                    <div style={isMobile ? { flex: 1, minWidth: 0 } : undefined}>
                      <div style={{ fontWeight: 700, textDecoration: "underline", decorationColor: "rgba(255,255,255,0.15)", ...(isMobile ? { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } : {}) }}>{p.name}</div>
                      <div style={{ fontSize: 11, color: "rgba(255,255,255,0.8)" }}>{isMobile ? `${t.id} · Group ${t.grp}` : `Group ${t.grp}`}</div>
                    </div>
                  </div>
                  {!isMobile && (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                      <Flag team={t} /> {t.id}
                    </span>
                  )}
                  <span style={{ textAlign: "center" }}>
                    <span className="pill" style={{ background: "rgba(255,255,255,0.10)", color: "white", fontSize: isMobile ? 11 : 10 }}>{POS_NAMES[p.pos]}</span>
                  </span>
                  <div className="row" style={{ gap: 4, justifyContent: "flex-end" }}>
                    <button
                      onClick={() => handleToggleWatchlist(p.id)}
                      style={{
                        padding: "4px 8px",
                        fontSize: 24,
                        background: "transparent",
                        color: isWatched ? "#ffd700" : "rgba(255,255,255,0.4)",
                        border: "none",
                        cursor: "pointer",
                        textShadow: isWatched ? "0 0 8px rgba(255, 215, 0, 0.6)" : "none"
                      }}
                      title={isWatched ? "Remove from watchlist" : "Add to watchlist"}>
                      {isWatched ? "★" : "☆"}
                    </button>
                    {(() => {
                      const reason = ineligibleReason(p);
                      return (
                        <button onClick={() => handleDraftPick(p.id)} className="btn btn--draft"
                          style={{ padding: isMobile ? "10px 10px" : "5px 12px", fontSize: 11, opacity: reason ? 0.4 : 1 }}
                          disabled={!DRAFT_STATE.isMyTurn || !!reason}
                          title={reason || ""}>
                          {reason && reason !== "TAKEN" ? (reason === "POS FULL" ? "Full" : "Max 3") : "Draft"}
                        </button>
                      );
                    })()}
                  </div>
                </div>
              );
            })}
            {visiblePool.length === 0 && (
              <div style={{ padding: "24px 12px", textAlign: "center", color: "rgba(255,255,255,0.5)", fontSize: 13 }}>No players match these filters.</div>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border-dark)" }}>
            <span style={{ fontSize: 12, color: "rgba(255,255,255,0.6)" }}>
              Showing {totalPool > 0 ? startIdx + 1 : 0}–{Math.min(startIdx + PAGE_SIZE, totalPool)} of {totalPool}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                disabled={page === 0}
                onClick={() => setPage(p => Math.max(0, p - 1))}
                style={{ padding: isMobile ? "11px 14px" : "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700, border: "none",
                  background: page === 0 ? "rgba(255,255,255,0.05)" : "rgba(255,255,255,0.14)",
                  color: page === 0 ? "rgba(255,255,255,0.3)" : "white", cursor: page === 0 ? "default" : "pointer" }}>
                ← Prev
              </button>
              <button
                disabled={startIdx + PAGE_SIZE >= totalPool}
                onClick={() => setPage(p => p + 1)}
                style={{ padding: isMobile ? "11px 14px" : "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700, border: "none",
                  background: (startIdx + PAGE_SIZE >= totalPool) ? "rgba(255,255,255,0.05)" : "rgba(255,255,255,0.14)",
                  color: (startIdx + PAGE_SIZE >= totalPool) ? "rgba(255,255,255,0.3)" : "white",
                  cursor: (startIdx + PAGE_SIZE >= totalPool) ? "default" : "pointer" }}>
                Next →
              </button>
            </div>
          </div>
        </div>
  );

  /* RIGHT COLUMN — My Squad & Draft Order */
  const squadPanel = (
      <div className="col" style={{ gap: 12, height: "100%" }}>
        {/* My Squad */}
        <div className="card-dark" style={{ flexShrink: 0 }}>
          <div className="card-dark__title">My Squad ({myPicks.length}/15)</div>
          <div className="card-section" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, padding: 14 }}>
            <SquadCount label="GK" cur={mySquadByPos[1]} max={2} />
            <SquadCount label="DEF" cur={mySquadByPos[2]} max={5} />
            <SquadCount label="MID" cur={mySquadByPos[3]} max={5} />
            <SquadCount label="FWD" cur={mySquadByPos[4]} max={3} />
          </div>
          {Object.keys(myNationCounts).length > 0 && (
            <div className="card-section" style={{ display: "flex", flexWrap: "wrap", gap: 5, padding: "8px 14px" }}>
              {Object.entries(myNationCounts).sort((a, b) => b[1] - a[1]).map(([iso, c]) => (
                <span key={iso} style={{ fontSize: 10, fontWeight: 800, padding: "2px 7px", borderRadius: 999,
                  background: c >= NATION_MAX ? "rgba(245,197,24,0.18)" : "rgba(255,255,255,0.08)",
                  color: c >= NATION_MAX ? "#f5c518" : "rgba(255,255,255,0.75)",
                  border: c >= NATION_MAX ? "1px solid rgba(245,197,24,0.5)" : "1px solid transparent" }}
                  title={c >= NATION_MAX ? "Nation cap reached (3)" : ""}>
                  {iso} {c}/3
                </span>
              ))}
            </div>
          )}
          {myPicks.length === 0 ? (
            <div className="card-section" style={{ textAlign: "center", color: "rgba(255,255,255,0.55)", fontSize: 13 }}>
              Your picks will appear here.
            </div>
          ) : (
            myPicks.map((p, i) => {
              const pl = playerById(p.playerId);
              const plT = teamById(pl.team);
              return (
                <div key={i} className="card-section" style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px" }}>
                  <span className="mono" style={{ color: "rgba(255,255,255,0.4)", fontSize: 11 }}>R{p.round}</span>
                  <div 
                    style={{ flex: 1, display: "flex", alignItems: "center", gap: 10, cursor: "pointer", minWidth: 0 }}
                    onClick={() => window.dispatchEvent(new CustomEvent('show-player-stats', { detail: { id: pl.id } }))}
                  >
                    <div style={{ width: 28, height: 28, flexShrink: 0 }}><Jersey team={plT} pos={pl.pos} /></div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 700, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textDecoration: "underline", decorationColor: "rgba(255,255,255,0.15)" }}>{pl.name}</div>
                      <div style={{ color: "#cbd5e1", fontSize: 11, fontWeight: 600 }}>{POS_NAMES[pl.pos]} · {plT.id}</div>
                    </div>
                  </div>
                  {/* Group-stage opponents GW1→GW3 (small flags), not mock points */}
                  <span style={{ display: "inline-flex", gap: 4, flexShrink: 0, alignItems: "center" }}
                    title={`Faces: ${(GROUP_OPPONENTS[pl.team] || []).join(" → ")} (GW1→GW3)`}>
                    {(GROUP_OPPONENTS[pl.team] || []).map((iso, k) => (
                      <span key={k} style={{ transform: "scale(0.85)" }}><Flag team={teamById(iso)} /></span>
                    ))}
                  </span>
                </div>
              );
            })
          )}
        </div>

        {/* Draft Order */}
        <div className="card-dark" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
          <div className="card-dark__title" style={{ fontSize: 14 }}>Draft Order</div>
          <div style={{ overflowY: "auto", flex: 1 }}>
            {sidebarOrder.map((m, idx) => {
              const picks = DRAFT_HISTORY.filter(p => p.uid === m.uid);
              const lastPick = picks.length > 0 ? picks[picks.length - 1] : null;
              const isCurrent = DRAFT_STATE.onTheClock === m.uid;

              return (
                <div key={idx} style={{ 
                  padding: "12px 14px", 
                  borderBottom: "1px solid var(--border-dark)", 
                  background: isCurrent ? "rgba(0, 217, 107, 0.15)" : undefined,
                  borderLeft: isCurrent ? "4px solid var(--green-400)" : "4px solid transparent",
                  opacity: isCurrent ? 1 : 0.85,
                  boxShadow: isCurrent ? "inset 0 0 10px rgba(0, 217, 107, 0.1)" : undefined
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span style={{ 
                      color: isCurrent ? "var(--green-400)" : "rgba(255,255,255,0.7)", 
                      fontWeight: isCurrent ? 900 : 700, 
                      fontSize: 13
                    }}>
                      {m.name} {isCurrent && "💬"}
                    </span>
                    {lastPick && (
                      <span className="mono" style={{ color: "rgba(255,255,255,0.45)", fontSize: 10 }}>
                        R{lastPick.round}·{lastPick.overall}
                      </span>
                    )}
                  </div>
                  {lastPick ? (
                    <div style={{ 
                      color: "white", 
                      fontWeight: 800, 
                      fontSize: 16, 
                      marginTop: 6,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      cursor: "pointer",
                      textDecoration: "underline",
                      decorationColor: "rgba(255,255,255,0.15)"
                    }}
                    onClick={() => window.dispatchEvent(new CustomEvent('show-player-stats', { detail: { id: lastPick.playerId } }))}
                    >
                      {playerById(lastPick.playerId).name}
                    </div>
                  ) : (
                    <div style={{ color: "rgba(255,255,255,0.35)", fontSize: 13, marginTop: 6, fontStyle: "italic" }}>
                      No picks yet
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
  );

  // ---- Mobile: clock always on top, then chip-tabs switching the stacked panels.
  if (isMobile) {
    return (
      <div className="col" style={{ gap: 12 }}>
        {notStartedBanner}
        {dupBanner}
        {clockCard}
        <div className="draft-mobile-tabs">
          <button className={mobilePanel === "watchlist" ? "is-active" : ""} onClick={() => setMobilePanel("watchlist")}>
            ★ Watchlist ({availableCount}/{watchlistRows.length})
          </button>
          <button className={mobilePanel === "pool" ? "is-active" : ""} onClick={() => setMobilePanel("pool")}>
            Pool ({totalPool})
          </button>
          <button className={mobilePanel === "squad" ? "is-active" : ""} onClick={() => setMobilePanel("squad")}>
            Squad ({myPicks.length}/15)
          </button>
        </div>
        {mobilePanel === "watchlist" && watchlistPanel}
        {mobilePanel === "pool" && poolCard}
        {mobilePanel === "squad" && squadPanel}
      </div>
    );
  }

  // ---- Desktop: the original 3-column grid, unchanged.
  return (
    <div style={{ display: "grid", gridTemplateColumns: "320px 1fr 260px", gap: 16, height: 480 }}>
      {notStartedBanner}
      {dupBanner}
      {watchlistPanel}

      {/* CENTER COLUMN — main draft area */}
      <div className="col" style={{ gap: 14, height: "100%" }}>
        {clockCard}
        {poolCard}
      </div>

      {squadPanel}
    </div>
  );
}

function SquadCount({ label, cur, max }) {
  const isMobile = useIsMobile();
  const full = cur >= max;
  return (
    <div style={{ textAlign: "center", padding: "8px 0", background: "rgba(0,0,0,0.2)", borderRadius: 6, border: full ? "1px solid var(--green-400)" : "1px solid transparent" }}>
      <div style={{ fontSize: isMobile ? 11 : 10, fontWeight: 800, color: "rgba(255,255,255,0.6)", letterSpacing: "0.08em" }}>{label}</div>
      <div className="mono" style={{ fontSize: 16, fontWeight: 800, color: full ? "var(--green-400)" : "white" }}>{cur}/{max}</div>
    </div>
  );
}


// ---------- CREATE / JOIN LEAGUE ----------
function useCreateLeague() {
  const isMobile = useIsMobile();
  const [mode, setMode] = React.useState("home"); // home | create | join
  const me = managerById(window.ME) || { name: "Manager", team: "My Team", flag: "GER", waiverPri: 99 };
  const myStanding = (window.STANDINGS || STANDINGS).find(s => s.uid === window.ME) || { rank: "—", fpts: "—", hpts: "—" };
  const currentGw = TOURNAMENT.currentGw;
  const gwPoints = window.GW_TOTALS && window.GW_TOTALS[window.ME] !== undefined ? window.GW_TOTALS[window.ME] : "—";
  const hasLeague = LEAGUE && LEAGUE.inviteCode;

  const [leaguesList, setLeaguesList] = React.useState([]);
  const [loadingLeagues, setLoadingLeagues] = React.useState(false);

  React.useEffect(() => {
    const fetchLeagues = async () => {
      setLoadingLeagues(true);
      try {
        const res = await apiCall("GET", "/leagues/my");
        if (res) {
          setLeaguesList(res);
        }
      } catch (err) {
        console.warn("Failed to fetch my leagues list", err);
      } finally {
        setLoadingLeagues(false);
      }
    };
    fetchLeagues();
  }, []);

  return { isMobile, mode, setMode, me, myStanding, currentGw, gwPoints, hasLeague, leaguesList, loadingLeagues };
}

function CreateLeagueScreen({ onTab }) {
  const { isMobile, mode, setMode, me, myStanding, currentGw, gwPoints, hasLeague, leaguesList, loadingLeagues } = useCreateLeague();
  const { setActiveLid } = useAppCtx();

  if (mode === "create") return <CreateForm onBack={() => setMode("home")} onTab={onTab} />;
  if (mode === "join") return <JoinForm onBack={() => setMode("home")} onTab={onTab} />;

  return (
    <div className="col" style={{ gap: 20 }}>
      <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Leagues</h2>

      {/* Switch Platforms Section */}
      {leaguesList.length > 1 && (
        <div className="col" style={{ gap: 12, marginTop: 10 }}>
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 16 }}>
            {leaguesList.map(l => {
              const isActive = l.leagueId === LEAGUE.id;
              const isSim = l.leagueId.includes("mock") || l.leagueId.includes("sim");
              return (
                <div 
                  key={l.leagueId} 
                  className="card-dark" 
                  style={{ 
                    padding: 20, 
                    border: isActive ? "2px solid var(--green-400)" : "1px solid var(--border-dark)",
                    background: isActive ? "rgba(26, 210, 196, 0.08)" : "rgba(255,255,255,0.02)",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    gap: 16,
                    borderRadius: 12,
                    position: "relative"
                  }}
                >
                  {isActive && (
                    <span 
                      style={{ 
                        position: "absolute", top: 12, right: 12, 
                        background: "var(--green-400)", color: "var(--navy-900)", 
                        fontSize: 9, fontWeight: 800, padding: "3px 8px", borderRadius: 4,
                        letterSpacing: "0.05em"
                      }}
                    >
                      ACTIVE
                    </span>
                  )}
                  <div>
                    <div style={{ fontSize: 11, color: isSim ? "#a78bfa" : "var(--gold-500)", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                      {isSim ? "Platform A · Simulation Time-Machine" : "Platform B · 7-Manager Live Draft"}
                    </div>
                    <div className="h-display" style={{ fontSize: 20, marginTop: 6, color: "white" }}>{l.name}</div>
                    <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", marginTop: 6 }}>
                      Status: <strong style={{ color: "white", textTransform: "capitalize" }}>{l.status.replace("_", " ")}</strong> · {l.memberCount}/{l.maxMembers} Managers
                    </div>
                  </div>
                  {!isActive ? (
                    <button 
                      className="btn btn--primary" 
                      style={{ alignSelf: "flex-start", padding: "6px 14px", fontSize: 11 }}
                      onClick={() => {
                        setActiveLid(l.leagueId);
                      }}
                    >
                      Switch to this Platform →
                    </button>
                  ) : (
                    <div style={{ fontSize: 11, color: "var(--green-400)", fontWeight: 600 }}>Currently viewing this environment</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* My league */}
      <div className="card-dark" style={{ padding: 0, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", top: 0, right: 0, padding: "6px 14px", background: "var(--green-400)", color: "var(--navy-900)", fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", borderRadius: "0 0 0 10px", whiteSpace: "nowrap" }}>ACTIVE LEAGUE</div>
        <div style={{ padding: 22, marginRight: isMobile ? 0 : 140 }}>
          <div className="h-display" style={{ fontSize: 24, marginBottom: 4, paddingRight: isMobile ? 96 : 0 }}>{LEAGUE.name}</div>
          <div style={{ color: "rgba(255,255,255,0.75)", fontSize: 13, marginBottom: 14 }}>
            {hasLeague ? `${LEAGUE.size} managers · Snake draft · H2H league with knockout` : "—"}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "repeat(4, 1fr)", gap: 12 }}>
            <MetricChip label="Your rank" value={hasLeague ? `#${myStanding.rank} / ${LEAGUE.size}` : "—"} accent="var(--gold-500)" />
            <MetricChip label="Total points" value={String(myStanding.fpts)} />
            <MetricChip label="GW Points" value={String(gwPoints)} accent="var(--green-400)" />
            <MetricChip label="Status" value={hasLeague ? (LEAGUE.knockoutStartGw <= currentGw ? "Knockout" : "Group Stage") : "—"} accent="var(--gold-500)" />
          </div>
          <div style={{ marginTop: 16, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <button className="btn btn--primary" onClick={() => onTab("status")}>Open League →</button>
            <span style={{ marginLeft: 8, fontSize: 12, color: "rgba(255,255,255,0.6)" }}>Invite code:</span>
            <span className="pill pill--ghost" style={{ background: "rgba(255,255,255,0.10)", border: "1px solid rgba(255,255,255,0.18)", fontFamily: "var(--font-num)" }}>{LEAGUE.inviteCode || "—"}</span>
          </div>
        </div>
      </div>

      {/* Create / Join cards */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 16 }}>
        <div className="card" style={{ padding: 24, cursor: "pointer", transition: "transform 0.12s, box-shadow 0.12s" }}
          onClick={() => setMode("create")}
          onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 8px 24px rgba(12,10,62,0.10)"; }}
          onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: "var(--grad-hero)", display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontSize: 24, fontWeight: 800, marginBottom: 16 }}>+</div>
          <div className="h-display" style={{ fontSize: 20, marginBottom: 4 }}>Create New League</div>
          <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
            Spin up a draft league with friends. Choose size, draft date, and house rules.
            We'll generate an invite code and schedule the H2H matchups.
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.06)", color: "var(--navy-800)" }}>4–16 managers</span>
            <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.06)", color: "var(--navy-800)" }}>Snake draft</span>
            <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.06)", color: "var(--navy-800)" }}>H2H + KO</span>
          </div>
        </div>

        <div className="card" style={{ padding: 24, cursor: "pointer", transition: "transform 0.12s, box-shadow 0.12s" }}
          onClick={() => setMode("join")}
          onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 8px 24px rgba(12,10,62,0.10)"; }}
          onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: "var(--gold-500)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--navy-900)", fontSize: 22, fontWeight: 800, marginBottom: 16 }}>→</div>
          <div className="h-display" style={{ fontSize: 20, marginBottom: 4 }}>Join with Code</div>
          <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
            Got a friend's invite code? Enter it here to join their league.
            Drafts must open before you can join — talk to the league admin.
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.06)", color: "var(--navy-800)" }}>Public + private</span>
            <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.06)", color: "var(--navy-800)" }}>Spectate available</span>
          </div>
        </div>
      </div>

    </div>
  );
}

function MetricChip({ label, value, accent }) {
  return (
    <div style={{ background: "rgba(0,0,0,0.20)", padding: "10px 14px", borderRadius: 8 }}>
      <div style={{ fontSize: 10, fontWeight: 800, color: "rgba(255,255,255,0.6)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{label}</div>
      <div className="mono" style={{ fontSize: 18, fontWeight: 800, color: accent || "white", marginTop: 2 }}>{value}</div>
    </div>
  );
}

function useCreateForm({ onBack }) {
  const isMobile = useIsMobile();
  const [name, setName] = React.useState("");
  const [size, setSize] = React.useState(10);
  const [timer, setTimer] = React.useState(30);
  const [tradeRule, setTradeRule] = React.useState("vote");
  const [draftDate, setDraftDate] = React.useState("2026-06-08T18:00");

  const koStartGw = size > 8 ? 4 : 7;
  const qualifiers = size > 8 ? 8 : 4;
  const leaguePhase = size > 8 ? [1, 2, 3] : [1, 2, 3, 4, 5, 6];

  const handleCreate = async () => {
    try {
      const res = await apiCall("POST", "/leagues", {
        name,
        displayName: _auth.currentUser?.displayName || _auth.currentUser?.email.split("@")[0] || "Admin",
        maxMembers: size,
        pickTimer: timer,
        tradeApproval: tradeRule,
        draftAt: draftDate ? new Date(draftDate).toISOString() : undefined
      });
      alert(`League "${res.name}" created successfully!\nInvite Code: ${res.inviteCode}`);
      if (window.refreshActiveLeague) {
        await window.refreshActiveLeague();
      }
      onBack();
    } catch (err) {
      alert("Failed to create league: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  return { isMobile, name, setName, size, setSize, timer, setTimer, tradeRule, setTradeRule, draftDate, setDraftDate, koStartGw, qualifiers, leaguePhase, handleCreate };
}

function CreateForm({ onBack, onTab }) {
  const { isMobile, name, setName, size, setSize, timer, setTimer, tradeRule, setTradeRule, draftDate, setDraftDate, koStartGw, qualifiers, leaguePhase, handleCreate } = useCreateForm({ onBack });

  return (
    <div className="col" style={{ gap: 16 }}>
      <button onClick={onBack} className="muted" style={{ alignSelf: "flex-start", fontSize: 13 }}>← Back</button>
      <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Create New League</h2>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 320px", gap: 16 }}>
        <div className="card" style={{ padding: isMobile ? 18 : 28 }}>
          <Field label="League name" hint="What you'll call it in chat">
            <input
              type="text" value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. World Cup Bros 2026"
              style={{ width: "100%", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border-strong)", fontSize: 15 }}
            />
          </Field>

          <Field label="League size" hint={`${size} managers · ${koStartGw === 4 ? "Standard format" : "Extended H2H format"}`}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 4 }}>
              {[6,7,8,9,10].map(n => (
                <button key={n}
                  className={"btn " + (size === n ? "btn--solid-dark" : "btn--ghost-dark")}
                  style={{ padding: "10px 0", fontSize: 13 }}
                  onClick={() => setSize(n)}>{n}</button>
              ))}
            </div>
            <div style={{ marginTop: 10, padding: "10px 12px", background: "rgba(91,61,242,0.06)", borderRadius: 6, fontSize: 12, color: "var(--navy-800)" }}>
              <strong>Structure:</strong> Group stage = H2H rounds GW{leaguePhase.join(", GW")}. Top {qualifiers} qualify for knockout starting GW{koStartGw} ({size > 8 ? "QF → SF → Final" : "SF → Final"}).
            </div>
          </Field>

          <Field label="Draft date" hint="When the snake draft begins">
            <input
              type="datetime-local" value={draftDate} onChange={e => setDraftDate(e.target.value)}
              style={{ padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border-strong)", fontSize: 15, maxWidth: "100%" }}
            />
          </Field>

          <Field label="Pick timer" hint="Seconds per draft pick">
            <div style={{ display: "flex", gap: 6, ...(isMobile ? { flexWrap: "wrap" } : {}) }}>
              {[30, 60, 90, 120].map(n => (
                <button key={n}
                  className={"btn " + (timer === n ? "btn--solid-dark" : "btn--ghost-dark")}
                  style={{ padding: "10px 18px", fontSize: 13 }}
                  onClick={() => setTimer(n)}>{n}s</button>
              ))}
            </div>
          </Field>

          <Field label="Trade approval" hint="How trades are vetted before going through">
            <div style={{ display: "flex", gap: 6, ...(isMobile ? { flexWrap: "wrap" } : {}) }}>
              {[
                ["instant", "Instant"],
                ["vote", "League vote"],
                ["admin", "Admin only"],
                ["none", "Disabled"],
              ].map(([v, l]) => (
                <button key={v}
                  className={"btn " + (tradeRule === v ? "btn--solid-dark" : "btn--ghost-dark")}
                  style={{ padding: "10px 16px", fontSize: 12 }}
                  onClick={() => setTradeRule(v)}>{l}</button>
              ))}
            </div>
          </Field>

          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", paddingTop: 14, borderTop: "1px solid var(--border)" }}>
            <button onClick={onBack} className="btn btn--ghost-dark">Cancel</button>
            <button onClick={handleCreate} className="btn btn--primary" disabled={!name}>Create League</button>
          </div>
        </div>

        {/* Preview */}
        <div className="card-dark" style={{ padding: 0, position: "sticky", top: 16, alignSelf: "start" }}>
          <div className="card-dark__title">Preview</div>
          <div className="card-section">
            <div style={{ fontSize: 11, opacity: 0.6, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>League name</div>
            <div className="h-display" style={{ fontSize: 18, marginTop: 4 }}>{name || "Untitled League"}</div>
          </div>
          <div className="card-section">
            <Stat label="Managers" value={`${size}`} />
            <Stat label="Squad size" value="15 (2/5/5/3)" />
            <Stat label="League phase" value={`GW1–${leaguePhase[leaguePhase.length - 1]}`} />
            <Stat label="Knockout starts" value={`GW${koStartGw}`} accent="var(--gold-500)" />
            <Stat label="Qualifiers" value={`Top ${qualifiers}`} />
            <Stat label="Pick timer" value={`${timer}s`} />
            <Stat label="Trade approval" value={tradeRule} />
          </div>
          <div className="card-section" style={{ fontSize: 12, opacity: 0.8 }}>
            Free transfers · 2 per window. Five windows between GW1–GW6.
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.04em", marginBottom: 4 }}>{label}</div>
      {hint && <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{hint}</div>}
      {children}
    </div>
  );
}

function useJoinForm({ onBack }) {
  const [code, setCode] = React.useState("");
  const [displayName, setDisplayName] = React.useState(_auth.currentUser?.displayName || "");
  const [teamName, setTeamName] = React.useState("");

  const handleJoin = async () => {
    try {
      await apiCall("POST", "/leagues/join", {
        inviteCode: code,
        teamName: teamName || "Unnamed Team",
        displayName: displayName || _auth.currentUser?.email.split("@")[0] || "Manager"
      });
      alert("Joined league successfully!");
      if (window.refreshActiveLeague) {
        await window.refreshActiveLeague();
      }
      onBack();
    } catch (err) {
      alert("Failed to join league: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  return { code, setCode, displayName, setDisplayName, teamName, setTeamName, handleJoin };
}

function JoinForm({ onBack }) {
  const { code, setCode, displayName, setDisplayName, teamName, setTeamName, handleJoin } = useJoinForm({ onBack });

  return (
    <div className="col" style={{ gap: 16, maxWidth: 520 }}>
      <button onClick={onBack} className="muted" style={{ alignSelf: "flex-start", fontSize: 13 }}>← Back</button>
      <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Join a League</h2>
      <div className="card" style={{ padding: 28 }}>
        <Field label="Invite code" hint="Ask the league admin for the 8-character code">
          <input
            type="text" value={code} onChange={e => setCode(e.target.value.toUpperCase())}
            placeholder="WC26-XXXX"
            style={{ width: "100%", padding: "16px", borderRadius: 8, border: "1px solid var(--border-strong)", fontSize: 18, fontFamily: "var(--font-num)", letterSpacing: "0.06em", textAlign: "center" }}
          />
        </Field>
        <Field label="Display name" hint="What your friends will see in this league">
          <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)} style={{ width: "100%", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border-strong)", fontSize: 15 }} />
        </Field>
        <Field label="Team name" hint="Pick something memorable. You can change it later.">
          <input type="text" value={teamName} onChange={e => setTeamName(e.target.value)} placeholder="e.g. Hapoel Eliyahu" style={{ width: "100%", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border-strong)", fontSize: 15 }} />
        </Field>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onBack} className="btn btn--ghost-dark">Cancel</button>
          <button onClick={handleJoin} className="btn btn--primary" disabled={!code}>Join League</button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { DraftRoomScreen, CreateLeagueScreen, GROUP_FIXTURES, GROUP_OPPONENTS });
