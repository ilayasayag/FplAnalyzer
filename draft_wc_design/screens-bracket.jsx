// =====================================================================
// WC26 — Screens: Knockout Bracket, Transfers/Waivers
// =====================================================================

// ---------- KNOCKOUT BRACKET ----------
function BracketScreen({ onTab }) {
  const rounds = BRACKET.rounds || BRACKET;
  const hasQf = LEAGUE.knockoutQualifiers === 8 || (rounds.qf && rounds.qf.length > 0);
  const gridColumns = hasQf ? "1fr 1fr 1fr 220px" : "1fr 1fr 220px";

  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="screen-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Knockout Bracket</h2>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{LEAGUE.name} · {LEAGUE.inviteCode ? `${LEAGUE.knockoutQualifiers} qualifiers` : "—"} · {hasQf ? "QF → SF → Final" : "SF → Final"}</div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <span className="pill pill--gold">GW{LEAGUE.knockoutStartGw || "—"} · {hasQf ? "Quarter-Finals" : "Semi-Finals"}</span>
        </div>
      </div>

      {/* Seeding explainer */}
      <div className="alert alert--info">
        <div className="alert__icon" style={{ background: "var(--violet-500)", color: "white" }}>i</div>
        <div style={{ fontSize: 13 }}>
          <strong>Bracket seeded after GW{LEAGUE.knockoutStartGw ? (LEAGUE.knockoutStartGw - 1) : "—"}.</strong> {hasQf ? "Seeds 1–4 are top H2H records; seeds 5–8 are the next best by fantasy points." : "Seeds 1–2 are top H2H records; seeds 3–4 are the next best by fantasy points."} Higher seeds host the lower seeds. Tiebreakers: total fantasy points, then coin flip.
        </div>
      </div>

      <div className="bracket-scroll">
      <div className="bracket" style={{ gridTemplateColumns: gridColumns }}>
        {/* QF column */}
        {hasQf && (
          <div className="bracket__col">
            <div className="bracket__col-head">Quarter-Finals · GW4</div>
            {rounds.qf && rounds.qf.map((m, i) => <BracketMatch key={m.id} match={m} result={null} round="qf" />)}
          </div>
        )}

        {/* SF column */}
        <div className="bracket__col" style={{ paddingTop: hasQf ? 28 : 0 }}>
          <div className="bracket__col-head">Semi-Finals · GW{hasQf ? 5 : 7}</div>
          {rounds.sf && rounds.sf.length > 0 ? (
            rounds.sf.map((m, i) => {
              if (hasQf && (!m.home || !m.away)) {
                return (
                  <div key={m.id} className="bracket__match" style={{ opacity: 0.55 }}>
                    <div className="bracket__side"><div className="bracket__seed">—</div><div><div className="bracket__team">Winner QF{i*2+1}</div><div className="bracket__team-sub">to be decided</div></div><div className="bracket__pts">–</div></div>
                    <div className="bracket__side"><div className="bracket__seed">—</div><div><div className="bracket__team">Winner QF{i*2+2}</div><div className="bracket__team-sub">to be decided</div></div><div className="bracket__pts">–</div></div>
                  </div>
                );
              } else {
                return <BracketMatch key={m.id} match={m} result={null} round="sf" />;
              }
            })
          ) : hasQf ? (
            // Render 2 empty placeholder matches for SFs if QFs are not yet finished
            [1, 2].map((_, i) => (
              <div key={i} className="bracket__match" style={{ opacity: 0.55, marginTop: i === 0 ? 0 : 20 }}>
                <div className="bracket__side"><div className="bracket__seed">—</div><div><div className="bracket__team">Winner QF{i*2+1}</div><div className="bracket__team-sub">to be decided</div></div><div className="bracket__pts">–</div></div>
                <div className="bracket__side"><div className="bracket__seed">—</div><div><div className="bracket__team">Winner QF{i*2+2}</div><div className="bracket__team-sub">to be decided</div></div><div className="bracket__pts">–</div></div>
              </div>
            ))
          ) : null}
        </div>

        {/* Final column */}
        <div className="bracket__col" style={{ justifyContent: "center" }}>
          <div className="bracket__col-head">Final · GW{hasQf ? 6 : 8}</div>
          {rounds.final && rounds.final.length > 0 ? (
            rounds.final.map(m => <BracketMatch key={m.id} match={m} result={{ status: "scheduled" }} round="final" />)
          ) : (
            <div className="bracket__match" style={{ opacity: 0.55 }}>
              <div className="bracket__side"><div className="bracket__seed">—</div><div><div className="bracket__team">Winner SF1</div><div className="bracket__team-sub">awaiting</div></div><div className="bracket__pts">–</div></div>
              <div className="bracket__side"><div className="bracket__seed">—</div><div><div className="bracket__team">Winner SF2</div><div className="bracket__team-sub">awaiting</div></div><div className="bracket__pts">–</div></div>
            </div>
          )}
        </div>

        {/* Trophy column */}
        <div className="bracket__col" style={{ justifyContent: "center", alignItems: "center" }}>
          <div className="bracket__col-head">Champion</div>
          <div style={{ background: "linear-gradient(160deg, #ffc844 0%, #ff8200 100%)", borderRadius: 14, padding: "26px 18px", textAlign: "center", color: "var(--navy-900)" }}>
            <svg width="80" height="80" viewBox="0 0 60 60" fill="none" style={{ margin: "0 auto" }}>
              <path d="M14 10h32v8a16 16 0 0 1-32 0V10Z" fill="#0c0a3e" />
              <path d="M6 12h8v6a4 4 0 0 1-4-4 2 2 0 0 1-2-2Zm40 0h8a2 2 0 0 1-2 2 4 4 0 0 1-4 4v-6Z" fill="#0c0a3e" opacity="0.85"/>
              <path d="M22 34h16v8H22z" fill="#0c0a3e" />
              <path d="M16 42h28v6H16z" fill="#0c0a3e" />
              <path d="M12 48h36v4H12z" fill="#0c0a3e" opacity="0.85"/>
            </svg>
            <div className="h-display" style={{ fontSize: 14, marginTop: 6, letterSpacing: "0.05em" }}>WC26 DRAFT</div>
            <div className="h-display" style={{ fontSize: 22, fontWeight: 800 }}>Champion</div>
            <div style={{ fontSize: 11, marginTop: 6, opacity: 0.75 }}>Decided Jul 18–19</div>
          </div>
        </div>
      </div>
      </div>

      {/* Path to glory */}
      <div className="card" style={{ padding: 20 }}>
        <div className="h-display" style={{ fontSize: 16, marginBottom: 12 }}>Your Path to Glory</div>
        {(() => {
          const isBracketSeeded = (rounds.qf && rounds.qf.length > 0) || (rounds.sf && rounds.sf.length > 0);
          if (!isBracketSeeded) {
            return (
              <div className="muted" style={{ padding: "16px 0", textAlign: "center", fontSize: 13, background: "var(--cream)", borderRadius: 8 }}>
                Awaiting group phase completion. Knockout bracket will be seeded after GW{LEAGUE.knockoutStartGw ? (LEAGUE.knockoutStartGw - 1) : 3}.
              </div>
            );
          }

          const myQfMatch = rounds.qf ? rounds.qf.find(m => m.home === window.ME || m.away === window.ME) : null;
          const mySfMatch = rounds.sf ? rounds.sf.find(m => m.home === window.ME || m.away === window.ME) : null;
          const myFinalMatch = rounds.final ? rounds.final.find(m => m.home === window.ME || m.away === window.ME) : null;

          const pathItems = [];
          if (hasQf) {
            // QF
            if (myQfMatch) {
              const oppUid = myQfMatch.home === window.ME ? myQfMatch.away : myQfMatch.home;
              const opp = oppUid ? managerById(oppUid) : null;
              pathItems.push({
                round: "QF", opp: opp ? opp.team : "TBD", flag: opp ? opp.flag : null, gw: LEAGUE.knockoutStartGw || 4, dates: "Jul 1–4"
              });
            } else {
              pathItems.push({ round: "QF", opp: "Did not qualify", flag: null, gw: LEAGUE.knockoutStartGw || 4, dates: "Jul 1–4" });
            }
            // SF
            if (mySfMatch) {
              const oppUid = mySfMatch.home === window.ME ? mySfMatch.away : mySfMatch.home;
              const opp = oppUid ? managerById(oppUid) : null;
              pathItems.push({
                round: "SF", opp: opp ? opp.team : "TBD", flag: opp ? opp.flag : null, gw: (LEAGUE.knockoutStartGw || 4) + 1, dates: "Jul 5–8"
              });
            } else {
              pathItems.push({ round: "SF", opp: myQfMatch ? "Winner QF Match" : "—", flag: null, gw: (LEAGUE.knockoutStartGw || 4) + 1, dates: "Jul 5–8" });
            }
            // Final
            if (myFinalMatch) {
              const oppUid = myFinalMatch.home === window.ME ? myFinalMatch.away : myFinalMatch.home;
              const opp = oppUid ? managerById(oppUid) : null;
              pathItems.push({
                round: "Final", opp: opp ? opp.team : "TBD", flag: opp ? opp.flag : null, gw: (LEAGUE.knockoutStartGw || 4) + 2, dates: "Jul 10–12"
              });
            } else {
              pathItems.push({ round: "Final", opp: "TBD", flag: null, gw: (LEAGUE.knockoutStartGw || 4) + 2, dates: "Jul 10–12" });
            }
          } else {
            // SF only
            if (mySfMatch) {
              const oppUid = mySfMatch.home === window.ME ? mySfMatch.away : mySfMatch.home;
              const opp = oppUid ? managerById(oppUid) : null;
              pathItems.push({
                round: "SF", opp: opp ? opp.team : "TBD", flag: opp ? opp.flag : null, gw: LEAGUE.knockoutStartGw || 7, dates: "Jul 14–15"
              });
            } else {
              pathItems.push({ round: "SF", opp: "Did not qualify", flag: null, gw: LEAGUE.knockoutStartGw || 7, dates: "Jul 14–15" });
            }
            // Final
            if (myFinalMatch) {
              const oppUid = myFinalMatch.home === window.ME ? myFinalMatch.away : myFinalMatch.home;
              const opp = oppUid ? managerById(oppUid) : null;
              pathItems.push({
                round: "Final", opp: opp ? opp.team : "TBD", flag: opp ? opp.flag : null, gw: (LEAGUE.knockoutStartGw || 7) + 1, dates: "Jul 18–19"
              });
            } else {
              pathItems.push({ round: "Final", opp: "TBD", flag: null, gw: (LEAGUE.knockoutStartGw || 7) + 1, dates: "Jul 18–19" });
            }
          }

          return (
            <div className="path-grid" style={{ display: "grid", gridTemplateColumns: "repeat(" + pathItems.length + ", 1fr)", gap: 12 }}>
              {pathItems.map((r, i) => (
                <div key={i} style={{ padding: "14px 16px", border: "1px solid var(--border)", borderRadius: 8, background: i === 0 ? "rgba(255,200,68,0.10)" : "var(--cream)", borderColor: i === 0 ? "var(--gold-500)" : "var(--border)" }}>
                  <div className="muted" style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>{r.round} · GW{r.gw}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {r.flag && <Flag team={teamById(r.flag)} />}
                    <strong style={{ fontSize: 14 }}>{r.opp}</strong>
                  </div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{r.dates}</div>
                </div>
              ))}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

function BracketMatch({ match, result, round }) {
  const h = match.home ? managerById(match.home) : null;
  const a = match.away ? managerById(match.away) : null;
  const hT = h ? teamById(h.flag) : null;
  const aT = a ? teamById(a.flag) : null;
  const isLive = result?.status === "live";
  const meSide = match.home === window.ME ? "home" : (match.away === window.ME ? "away" : null);

  const homeSeed = match.seedHome ?? match.homeSeed ?? "—";
  const awaySeed = match.seedAway ?? match.awaySeed ?? "—";
  
  const homePts = match.homePoints ?? result?.homePts ?? "–";
  const awayPts = match.awayPoints ?? result?.awayPts ?? "–";

  return (
    <div className={"bracket__match " + (isLive ? "is-live" : "")}>
      {isLive && (
        <div style={{ position: "absolute", top: -10, left: "50%", transform: "translateX(-50%)", background: "var(--green-400)", color: "var(--navy-900)", fontSize: 9, fontWeight: 800, letterSpacing: "0.08em", padding: "2px 10px", borderRadius: 999, textTransform: "uppercase", whiteSpace: "nowrap", zIndex: 2 }}>{result.liveLabel || "Live"}</div>
      )}
      <div className={"bracket__side " + (meSide === "home" ? "is-me" : "")} style={{ background: meSide === "home" ? "rgba(255,200,68,0.12)" : undefined, opacity: h ? 1 : 0.6 }}>
        <div className="bracket__seed">#{homeSeed}</div>
        <div>
          <div className="bracket__team" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {hT && <Flag team={hT} />} {h ? h.team : "TBD"}
          </div>
          <div className="bracket__team-sub">{h ? h.name : "Awaiting Seeding"}</div>
        </div>
        <div className="bracket__pts">{homePts}</div>
      </div>
      <div className={"bracket__side " + (meSide === "away" ? "is-me" : "")} style={{ background: meSide === "away" ? "rgba(255,200,68,0.12)" : undefined, opacity: a ? 1 : 0.6 }}>
        <div className="bracket__seed">#{awaySeed}</div>
        <div>
          <div className="bracket__team" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {aT && <Flag team={aT} />} {a ? a.team : "TBD"}
          </div>
          <div className="bracket__team-sub">{a ? a.name : "Awaiting Seeding"}</div>
        </div>
        <div className="bracket__pts">{awayPts}</div>
      </div>
    </div>
  );
}


// Animated replay of a wishlist auction — reveals each executed claim one-by-one
// in resolution order (waiver priority), showing the manager + player IN/OUT.
function AuctionViz({ result, onClose }) {
  // Reveal events in the EXACT order the auction resolved them — claims (↔) and
  // cancels (↓) interleaved — so a cancelled bid appears the moment it lost,
  // next to the claim that beat it. Falls back to executed-then-failed for an
  // older payload with no ordered event log.
  const items = React.useMemo(() => {
    const ev = (result && result.events) || [];
    if (ev.length) return ev.map(e => ({ ...e, ok: e.type === "claim" }));
    return [
      ...((result && result.executed) || []).map(e => ({ ...e, ok: true })),
      ...((result && result.failed) || []).map(f => ({ ...f, ok: false })),
    ];
  }, [result]);
  const nClaimed = items.filter(it => it.ok).length;
  const nFailed = items.length - nClaimed;
  const [revealed, setRevealed] = React.useState(0);
  React.useEffect(() => {
    if (revealed >= items.length) return;
    const t = setTimeout(() => setRevealed(r => r + 1), 600);
    return () => clearTimeout(t);
  }, [revealed, items.length]);
  const done = revealed >= items.length;

  const mgrName = (uid) => { const m = managerById(uid); return m ? (m.team || m.name || uid) : uid; };
  const pl = (id) => (window.PLAYER_MAP || {})[String(id)] || { name: id, pos: 3, team: null };
  const chip = (p, kind) => {
    const isIn = kind === "in";
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 9px", borderRadius: 7,
        background: isIn ? "rgba(0,217,107,0.18)" : "rgba(230,57,70,0.16)", color: isIn ? "#5ef0a8" : "#ff9aa3", fontSize: 13, fontWeight: 700 }}>
        <Flag team={teamById(p.team)} /> {p.name}
        <span style={{ fontSize: 10, opacity: 0.85, fontWeight: 800 }}>{isIn ? `IN · ${POS_NAMES[p.pos]}` : "OUT"}</span>
      </span>
    );
  };

  return (
    <div onClick={done ? onClose : undefined}
      style={{ position: "fixed", inset: 0, background: "rgba(8,6,40,0.80)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div onClick={e => e.stopPropagation()} className="card-dark"
        style={{ width: "min(580px, 95vw)", maxHeight: "88vh", overflow: "auto", padding: 26, borderRadius: 16, boxShadow: "0 24px 80px rgba(0,0,0,0.5)" }}>
        <div className="h-display" style={{ fontSize: 22, color: "white", marginBottom: 4 }}>⚡ Wishlist auction · GW{result.gw}</div>
        <div style={{ color: "rgba(255,255,255,0.72)", fontSize: 13, marginBottom: 18 }}>
          {done
            ? `${nClaimed} claimed · ${nFailed} cancelled — resolved by waiver priority.`
            : `Resolving by waiver priority… (${revealed}/${items.length})`}
        </div>
        <div className="col" style={{ gap: 10 }}>
          {items.length === 0 && (
            <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 13 }}>No bids were submitted this round.</div>
          )}
          {items.slice(0, revealed).map((it, i) => (
            <div key={i} className="auction-row" style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 12, alignItems: "center",
              padding: "11px 13px", borderRadius: 10,
              background: it.ok ? "rgba(255,255,255,0.06)" : "rgba(230,57,70,0.08)",
              border: "1px solid " + (it.ok ? "rgba(255,255,255,0.08)" : "rgba(230,57,70,0.25)"),
              opacity: it.ok ? 1 : 0.85 }}>
              <div style={{ fontWeight: 800, color: "white", fontSize: 13, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{mgrName(it.uid)}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {it.ok ? (
                  <React.Fragment>
                    {chip(pl(it.playerIn), "in")}
                    <span style={{ color: "rgba(255,255,255,0.4)" }}>↔</span>
                    {chip(pl(it.playerOut), "out")}
                  </React.Fragment>
                ) : (
                  <React.Fragment>
                    {chip(pl(it.playerIn), "in")}
                    <span style={{ color: "rgba(255,255,255,0.4)" }}>↔</span>
                    {chip(pl(it.playerOut), "out")}
                    <span title="bid cancelled — player went to another manager" style={{ color: "#ff9aa3", fontWeight: 900, fontSize: 16 }}>↓</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#ff9aa3" }}>
                      {it.wonByUid ? `cancelled · won by ${mgrName(it.wonByUid)}` : "cancelled · unavailable"}
                    </span>
                  </React.Fragment>
                )}
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 22, textAlign: "right" }}>
          <button className="btn btn--primary" disabled={!done} onClick={onClose}
            style={{ padding: "10px 18px", fontSize: 13, opacity: done ? 1 : 0.5, cursor: done ? "pointer" : "default" }}>
            {done ? "Done — refresh" : "Resolving…"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- TRANSFERS / WAIVERS / FREE AGENTS ----------
function TransfersScreen() {
  const [tab, setTab] = React.useState("free");
  const [runningMock, setRunningMock] = React.useState(false);
  const [auctionViz, setAuctionViz] = React.useState(null);  // {gw, executed, skipped}
  const [switching, setSwitching] = React.useState(false);
  const activeWindow = window.WINDOW || WINDOW;
  const me = managerById(window.ME) || { name: "Manager", team: "My Team", flag: "GER", waiverPri: 99 };
  const isMock = !!(window.LEAGUE && window.LEAGUE.simulated);
  // Window switching + the wishlist runner are LEAGUE-ADMIN powers (Ilay).
  // Everyone still SEES the buttons (current window highlighted) but they are
  // greyed/disabled for non-admins. Server-side gates match.
  const amLeagueAdmin = !!(window.LEAGUE && window.LEAGUE.admin && window.LEAGUE.admin === window.ME);
  const curPhase = (window.WINDOW && window.WINDOW.phase) || "none";
  const overridden = !!(window.WINDOW && window.WINDOW.overridden);

  // MOCK: flip the league's transfer-window phase so the page renders that
  // window. Trade = manager trades + wishlist; Free agents = instant pickups +
  // wishlist; Gameweek = wishlist only (no manager trades, picks go to wishlist);
  // Auto = clear the override and hand control back to the fixture clock.
  const switchWindow = async (phase) => {
    if (switching) return;
    if (phase === "auto" ? !overridden : phase === curPhase) return;
    setSwitching(true);
    try {
      const lid = window.LEAGUE.id;
      const gw = (window.WINDOW && window.WINDOW.gw) || (window.TOURNAMENT && window.TOURNAMENT.currentGw);
      // "auto" sends no gw — same call shape the old Status-screen admin
      // switcher used to clear the override.
      await apiCall("POST", `/leagues/${lid}/admin/window-override`, phase === "auto" ? { phase } : { phase, gw });
      window.location.reload();
    } catch (err) {
      alert("Failed to switch window: " + (err.error || err.detail || JSON.stringify(err)));
      setSwitching(false);
    }
  };

  // MOCK: open the free-agents window + run the wishlist auction in one click.
  // Auto-fills 1-3 bids for every OTHER manager (top free agents in, their worst
  // players out); the viewed manager's own wishlist is kept. Resolves the
  // auction so squads actually change, then reloads into the FA-window view.
  const runMockWishlist = async () => {
    if (runningMock) return;
    if (!window.confirm("Mock: close the trade window, open the FREE-AGENTS window and run the wishlist auction now?\n\nEvery other manager gets 1–3 auto bids (top free agents in, worst players out). Your own wishlist is kept.")) return;
    setRunningMock(true);
    try {
      const lid = window.LEAGUE.id;
      const gw = (window.WINDOW && window.WINDOW.gw) || (window.TOURNAMENT && window.TOURNAMENT.currentGw);
      const res = await apiCall("POST", `/admin/leagues/${lid}/run-mock-wishlist`, { gw, excludeUid: window.ME });
      const a = (res && res.wishlistAuction) || {};
      // Replay the auction in the UI (claims revealed one-by-one in resolution
      // order) instead of a bare alert. Closing the modal reloads into the new
      // FA-window state with the updated squads.
      setAuctionViz({ gw: res.gw, executed: a.executed || [], failed: a.failed || [], events: a.events || [] });
    } catch (err) {
      alert("Failed to run mock wishlist: " + (err.error || err.detail || JSON.stringify(err)));
      setRunningMock(false);
    }
  };

  return (
    <div className="col" style={{ gap: 16 }}>
      {auctionViz && <AuctionViz result={auctionViz} onClose={() => window.location.reload()} />}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Transfers</h2>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>Manage your squad between gameweeks</div>
        </div>
        {/* Any user can pull fresh live scores on demand */}
        <SyncDataButton />
      </div>

      {/* Big window banner */}
      <div className="card-dark" style={{ position: "relative", overflow: "hidden" }}>
        <div style={{
          background: "linear-gradient(94deg, #1d1864 0%, #4a1ba8 50%, #ff3e6c 100%)",
          padding: "20px 24px",
        }}>
          <div className="transfers-banner__grid" style={{ display: "grid", gridTemplateColumns: "1fr auto", alignItems: "center", gap: 20 }}>
            <div>
              <div className="pill pill--gold" style={{ marginBottom: 8 }}>⏳ {windowPhaseMeta(activeWindow.phase).label.toUpperCase()}</div>
              <div className="h-display" style={{ fontSize: 22, color: "white", marginBottom: 4 }}>
                {activeWindow.state === "open" ? `${windowPhaseMeta(activeWindow.phase).label} is active.` : "Transfer window is closed."}
              </div>
              <div style={{ color: "rgba(255,255,255,0.85)", fontSize: 13 }}>
                {activeWindow.phaseEndsAt
                  ? <>Closes <strong>{fmtWindowTime(activeWindow.phaseEndsAt)}</strong> · <Countdown to={activeWindow.phaseEndsAt} suffix=" remaining" /></>
                  : windowPhaseMeta(activeWindow.phase).hint}
              </div>
              {activeWindow.nextPhase && activeWindow.nextPhaseStartsAt && (
                <div style={{ color: "rgba(255,255,255,0.7)", fontSize: 12, marginTop: 6 }}>
                  Next: <strong>{windowPhaseMeta(activeWindow.nextPhase).label}</strong> opens {fmtWindowTime(activeWindow.nextPhaseStartsAt)} · <Countdown to={activeWindow.nextPhaseStartsAt} />
                </div>
              )}
            </div>
            <div className="transfers-banner__stats" style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <StatBlock label="Free transfers" value="∞" />
              <StatBlock label="Waiver priority" value={`#${me.waiverPri}`} accent="var(--gold-500)" />
              <button className="btn" disabled={runningMock || !amLeagueAdmin} onClick={runMockWishlist}
                title={amLeagueAdmin ? "Open the free-agents window and resolve the wishlist auction" : "Only the league admin can run the wishlist"}
                style={{ padding: "12px 16px", fontSize: 13, fontWeight: 800, borderRadius: 10, whiteSpace: "nowrap",
                  background: (runningMock || !amLeagueAdmin) ? "rgba(255,255,255,0.25)" : "var(--gold-500)",
                  color: (runningMock || !amLeagueAdmin) ? "rgba(255,255,255,0.55)" : "var(--navy-900)",
                  border: "none", cursor: (runningMock || !amLeagueAdmin) ? "default" : "pointer",
                  opacity: !amLeagueAdmin ? 0.6 : 1 }}>
                {runningMock ? "Running…" : "▶ Run wishlist"}
              </button>
            </div>
          </div>
        </div>
        <div style={{ padding: "10px 24px 14px", borderTop: "1px solid var(--border-dark)" }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "rgba(255,255,255,0.55)", marginBottom: 8 }}>
            {amLeagueAdmin ? "Switch window (league admin)" : "Current window"}
          </div>
          <div className="transfers-window-switch" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[
              ["auto", "Auto", "fixture clock decides"],
              ["trade", "Trade", "manager trades + wishlist"],
              ["free_agents", "Free agents", "instant pickups + wishlist"],
              ["next_gw_bid", "Gameweek", "wishlist only · no trades"],
            ].map(([key, label, hint]) => {
              const active = key === "auto" ? !overridden : curPhase === key;
              const locked = switching || !amLeagueAdmin;
              return (
                <button key={key} disabled={locked} onClick={() => switchWindow(key)}
                  title={amLeagueAdmin ? hint : "Only the league admin can switch windows"}
                  style={{ padding: "8px 14px", fontSize: 12, fontWeight: 700, borderRadius: 8,
                    cursor: locked ? "default" : "pointer",
                    background: active ? "var(--green-500)" : "rgba(255,255,255,0.10)",
                    color: active ? "var(--navy-900)" : (amLeagueAdmin ? "white" : "rgba(255,255,255,0.45)"),
                    opacity: (!amLeagueAdmin && !active) ? 0.55 : 1,
                    border: "1px solid " + (active ? "var(--green-500)" : "rgba(255,255,255,0.20)") }}>
                  {label}
                  <span style={{ display: "block", fontSize: 10, fontWeight: 600, opacity: 0.8 }}>{hint}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Admin-only run-actions for the mock league (wishlist auction / trade-
          window orchestrator). Self-gates on IS_ADMIN — renders null otherwise. */}
      <AdminWindowSwitcher />

      {/* Tabs */}
      <div className="card transfers-tabs" style={{ padding: "4px 14px", display: "flex", gap: 4 }}>
        {[
          ["free",    "Free Agents"],
          ["wishlist", `Wishlist (${(window.MY_WISHLIST_BIDS || []).length})`],
          ["squad",   "My Squad"],
          ["history", "History"],
          // ("draft" sub-tab removed — the top-nav Draft Room is the only one)
        ].map(([id, label]) => (
          <button key={id}
            className={"btn " + (tab === id ? "btn--solid-dark" : "")}
            style={{ padding: "10px 18px", fontSize: 13, background: tab === id ? undefined : "transparent", color: tab === id ? undefined : "var(--ink-700)" }}
            onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "free" && <FreeAgentsTab />}
      {tab === "wishlist" && <WishlistTab />}
      {tab === "squad" && <MySquadTab />}
      {tab === "history" && <TransferHistoryTab />}
    </div>
  );
}

function StatBlock({ label, value, accent }) {
  return (
    <div style={{ background: "rgba(0,0,0,0.25)", padding: "10px 18px", borderRadius: 10, textAlign: "center", minWidth: 110 }}>
      <div className="stat-block__label" style={{ fontSize: 10, fontWeight: 700, color: "rgba(255,255,255,0.6)", letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{label}</div>
      <div className="mono" style={{ fontSize: 22, fontWeight: 800, color: accent || "white", lineHeight: 1.1, whiteSpace: "nowrap" }}>{value}</div>
    </div>
  );
}

// Free-agents / pool sort options (Segment 6). [key, label]; "pts" is default.
// Season-stat keys read p.season.<key>; pts/dr/selPct read top-level fields.
const FA_SORT_OPTIONS = [
  ["pts", "Total points"],
  ["goals", "Goals"],
  ["assists", "Assists"],
  ["shotsOnTarget", "Shots on target"],
  ["cleanSheets", "Clean sheets"],
  ["minutes", "Minutes"],
  ["defconActions", "DefCon actions"],
  ["dr", "FIFA draft rank"],
  ["selPct", "% Selected"],
];
// Only FIFA draft rank sorts ascending (lower = better).
const SORT_ASC = new Set(["dr"]);
function faSortVal(p, key) {
  if (key === "pts") return p.pts || 0;
  if (key === "dr") return p.dr || 9999;
  if (key === "selPct") return p.selPct || 0;
  return (p.season && p.season[key]) || 0;  // season aggregates
}
// Short header + cell renderer for the DYNAMIC sorted-stat column. Keys already
// shown as fixed columns (pts, selPct) map to null → no extra column. Everything
// else surfaces the value you sorted by so it's visible in the table.
const FA_DYNAMIC_COL = {
  goals:         ["Goals",  p => (p.season && p.season.goals) || 0],
  assists:       ["Asts",   p => (p.season && p.season.assists) || 0],
  shotsOnTarget: ["SoT",    p => (p.season && p.season.shotsOnTarget) || 0],
  cleanSheets:   ["CS",     p => (p.season && p.season.cleanSheets) || 0],
  minutes:       ["Mins",   p => (p.season && p.season.minutes) || 0],
  defconActions: ["DefCon", p => (p.season && p.season.defconActions) || 0],
  dr:            ["Draft",  p => `#${p.dr || "—"}`],
};

function FreeAgentsTab() {
  const [posFilter, setPosFilter] = React.useState("all");
  const [nationFilter, setNationFilter] = React.useState("all");
  const [ownerFilter, setOwnerFilter] = React.useState("all"); // "all" | "__free" | manager name
  const [search, setSearch] = React.useState("");
  const [mode, setMode] = React.useState("free"); // "free" = unowned only, "all" = whole pool
  const [activePickup, setActivePickup] = React.useState(null);
  const [playerToDrop, setPlayerToDrop] = React.useState("");
  const [sortBy, setSortBy] = React.useState("pts"); // default: total points
  // Sort direction. Each key has a sensible default (FIFA draft rank ascends,
  // everything else descends); clicking the active column header flips it.
  const [sortDir, setSortDir] = React.useState("desc");
  const defaultDirFor = key => (SORT_ASC.has(key) ? "asc" : "desc");
  // Pick a sort column (dropdown or header click). Re-selecting the active
  // column toggles asc<->desc; a new column resets to its default direction.
  const applySort = key => {
    if (key === sortBy) setSortDir(d => (d === "asc" ? "desc" : "asc"));
    else { setSortBy(key); setSortDir(defaultDirFor(key)); }
  };
  const sortCaret = key => (sortBy === key ? (sortDir === "asc" ? " ▲" : " ▼") : "");

  // playerId -> owning manager's name. Computed EVERY render (not useMemo[]) so it
  // reflects window.SQUADS_BY_UID as soon as the per-manager squads finish loading —
  // a memo captured on mount could be empty if Transfers opens before that async
  // load resolves, which made every owned player look like a free agent.
  const ownerByPid = {};
  {
    const sbu = window.SQUADS_BY_UID || {}, mgrs = window.MANAGERS || [];
    const nameOf = uid => { const m = mgrs.find(x => x.uid === uid); return m ? (m.team || m.name || uid) : uid; };
    Object.entries(sbu).forEach(([uid, ids]) => (ids || []).forEach(pid => { ownerByPid[String(pid)] = nameOf(uid); }));
  }
  const ownerNames = [...new Set(Object.values(ownerByPid))].sort();

  // Derive BOTH views from the full pool (window.PLAYERS), which carries club +
  // real points. "All players" = the whole pool (owned shown with their manager,
  // not pickable); "Free agents" = players not owned by any manager. We don't use
  // the /free-agents endpoint here — it returns a projected, 50-capped subset with
  // no club/points.
  const source = (window.PLAYERS || []).filter(p => mode === "all" || !ownerByPid[String(p.id)]);
  const nations = [...new Set(source.map(p => p.teamName).filter(Boolean))].sort();
  const q = search.trim().toLowerCase();
  const filtered = source
    .filter(p => posFilter === "all" || p.pos === Number(posFilter))
    .filter(p => nationFilter === "all" || p.teamName === nationFilter)
    .filter(p => {
      if (ownerFilter === "all") return true;
      const o = ownerByPid[String(p.id)];
      return ownerFilter === "__free" ? !o : o === ownerFilter;
    })
    .filter(p => !q || (p.name || "").toLowerCase().includes(q) || (p.club || "").toLowerCase().includes(q))
    // Primary sort = chosen key in the chosen direction (header click toggles
    // asc/desc). SECONDARY is ALWAYS total points (desc), then draft rank — so
    // ties, and any column that's still all-zero pre-data, stay best-first.
    .sort((a, b) => {
      const av = faSortVal(a, sortBy), bv = faSortVal(b, sortBy);
      const primary = sortDir === "asc" ? av - bv : bv - av;
      return primary || (b.pts || 0) - (a.pts || 0) || (a.dr || 9999) - (b.dr || 9999);
    });
  const CAP = 120;
  const shown = filtered.slice(0, CAP);
  // Dynamic column reflecting the active sort (null when sorting by an
  // already-shown column like Pts / % Sel). Lets the user SEE the stat they
  // sorted by — e.g. Sort: Goals adds a Goals column.
  const dynCol = FA_DYNAMIC_COL[sortBy] || null;
  const mySquad = (window.MY_SQUAD_IDS || []).map(id => window.PLAYER_MAP[id]).filter(Boolean);
  const selStyle = { padding: "7px 10px", fontSize: 12, borderRadius: 8, border: "1px solid var(--border)", background: "white", color: "var(--ink-900)" };

  // Free-agent pickups are only INSTANT during the FREE_AGENTS window. At any
  // other time the squad is locked, so the same drop-selection instead queues
  // the player onto your bid-wishlist (resolved by the auction when the window
  // opens). Target GW = the open window's GW, else the next GW to be played.
  const faOpen = (window.WINDOW && window.WINDOW.phase) === "free_agents";
  const bidGw = (window.WINDOW && window.WINDOW.gw) ||
                (window.TOURNAMENT && window.TOURNAMENT.currentGw);
  const _pid = (v) => (isNaN(Number(v)) ? Number(String(v).replace("p_", "")) : Number(v));

  const handlePickup = async (p) => {
    if (!playerToDrop) {
      alert("Please select a player to drop.");
      return;
    }
    try {
      const lid = window.LEAGUE.id;
      const winNum = window.WINDOW.windowNumber || 1;
      const pIn = _pid(p.id);
      const pOut = _pid(playerToDrop);

      await apiCall("POST", `/leagues/${lid}/free-agent`, {
        playerIn: pIn,
        playerOut: pOut,
        windowNumber: winNum
      });
      alert(`Successfully picked up ${p.name} and dropped ${window.PLAYER_MAP[playerToDrop]?.name || playerToDrop}!`);
      setActivePickup(null);
      window.location.reload();
    } catch (err) {
      alert("Failed to pick up player: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  // Window closed → add this free agent to the bid-wishlist (same in/out swap
  // the pickup would do), appending to the manager's ordered bids for bidGw.
  const handleAddWishlist = async (p) => {
    if (!playerToDrop) { alert("Please select a player to drop."); return; }
    if (!bidGw) { alert("No upcoming gameweek to bid for yet."); return; }
    const pIn = _pid(p.id), pOut = _pid(playerToDrop);
    const existing = (window.MY_WISHLIST_BIDS || []).map(b => ({
      playerIn: Number(b.playerIn), playerOut: Number(b.playerOut), position: b.position,
    }));
    // Allow the same incoming player with a DIFFERENT player out (ordered
    // fallbacks); only block an exact duplicate of the (in, out) pair.
    if (existing.some(b => b.playerIn === pIn && b.playerOut === pOut)) {
      alert(`That exact swap (${p.name} in / ${window.PLAYER_MAP[String(playerToDrop)]?.name || "player"} out) is already on your wishlist.`); setActivePickup(null); return;
    }
    try {
      const lid = window.LEAGUE.id;
      const cp = window.PLAYER_MAP[String(p.id)];
      const next = [...existing, { playerIn: pIn, playerOut: pOut, position: cp ? POS_NAMES[cp.pos] : "?" }];
      const res = await apiCall("POST", `/leagues/${lid}/wishlist-bids`, { gw: bidGw, bids: next });
      window.MY_WISHLIST_BIDS = (res && Array.isArray(res.bids)) ? res.bids : next;
      alert(`Added ${p.name} to your wishlist (GW${bidGw}). It'll be claimed by the auction when the free-agents window opens.`);
      setActivePickup(null);
    } catch (err) {
      alert("Failed to add to wishlist: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div>
            <strong>{mode === "all" ? "All Players" : "Top Free Agents"}</strong>
            <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>
              · {mode === "all" ? "every player in the pool" : "players not owned by any league manager"}
              {" · "}{filtered.length} match{filtered.length === 1 ? "" : "es"}{filtered.length > CAP ? ` (top ${CAP} shown)` : ""}
            </span>
          </div>
          <div style={{ display: "inline-flex", padding: 3, background: "rgba(0,0,0,0.06)", borderRadius: 999 }}>
            {[["free", "Free agents"], ["all", "All players"]].map(([m, label]) => (
              <button key={m} className="btn" style={{ padding: "6px 14px", fontSize: 12, borderRadius: 999, background: mode === m ? "var(--navy-900)" : "transparent", color: mode === m ? "white" : "var(--ink-700)" }} onClick={() => { setMode(m); setOwnerFilter("all"); }}>{label}</button>
            ))}
          </div>
        </div>
        <div className="fa-filters" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12, alignItems: "center" }}>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name or club…"
            style={{ flex: "1 1 200px", minWidth: 160, padding: "8px 12px", fontSize: 13, borderRadius: 8, border: "1px solid var(--border)", background: "white", color: "var(--ink-900)" }} />
          <select value={nationFilter} onChange={e => setNationFilter(e.target.value)} style={selStyle}>
            <option value="all">All nations</option>
            {nations.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          <select value={sortBy} onChange={e => { setSortBy(e.target.value); setSortDir(defaultDirFor(e.target.value)); }} style={selStyle} title="Sort players by (or click a column header)">
            {FA_SORT_OPTIONS.map(([k, label]) => <option key={k} value={k}>Sort: {label}</option>)}
          </select>
          {mode === "all" && (
            <select value={ownerFilter} onChange={e => setOwnerFilter(e.target.value)} style={selStyle}>
              <option value="all">Any owner</option>
              <option value="__free">Free agents</option>
              {ownerNames.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          )}
          <div className="row" style={{ gap: 4 }}>
            {["all", "1", "2", "3", "4"].map(p => (
              <button key={p}
                className={"btn " + (posFilter === p ? "btn--solid-dark" : "")}
                style={{ padding: "6px 12px", fontSize: 12, background: posFilter === p ? undefined : "transparent", color: posFilter === p ? undefined : "var(--ink-700)" }}
                onClick={() => setPosFilter(p)}>
                {p === "all" ? "All" : POS_NAMES[Number(p)]}
              </button>
            ))}
          </div>
          {(search || nationFilter !== "all" || ownerFilter !== "all" || posFilter !== "all") && (
            <button className="btn btn--ghost-dark" style={{ padding: "6px 10px", fontSize: 11 }}
              onClick={() => { setSearch(""); setNationFilter("all"); setOwnerFilter("all"); setPosFilter("all"); }}>Clear</button>
          )}
        </div>
      </div>
      <div className="table-scroll">
      <table className="table-clean">
        <thead>
          <tr>
            <th>Player</th>
            <th>Team</th>
            <th>Pos</th>
            <th>Owner</th>
            {dynCol && <th onClick={() => applySort(sortBy)} style={{ textAlign: "right", color: "var(--navy-900)", cursor: "pointer", userSelect: "none" }} title="Click to flip sort direction">{dynCol[0]}{sortCaret(sortBy)}</th>}
            <th onClick={() => applySort("pts")} style={{ textAlign: "right", cursor: "pointer", userSelect: "none", color: sortBy === "pts" ? "var(--navy-900)" : undefined }} title="Sort by total points">Pts{sortCaret("pts")}</th>
            <th onClick={() => applySort("selPct")} style={{ textAlign: "right", cursor: "pointer", userSelect: "none", color: sortBy === "selPct" ? "var(--navy-900)" : undefined }} title="Sort by FIFA fantasy ownership %">% Sel{sortCaret("selPct")}</th>
            <th style={{ textAlign: "right" }}>Form</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {shown.length === 0 && (
            <tr><td colSpan={dynCol ? "9" : "8"} style={{ padding: 28, textAlign: "center", color: "var(--ink-500)" }}>No players match your filters.</td></tr>
          )}
          {shown.map(p => {
            const t = teamById(p.team);
            const owner = ownerByPid[String(p.id)];
            const eligibleDrops = mySquad.filter(s => s.pos === p.pos);
            const isPicking = activePickup?.id === p.id;

            return (
              <tr key={p.id}>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                    <div style={{ width: 36, height: 36, flexShrink: 0 }}><Jersey team={t} pos={p.pos} /></div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 700, whiteSpace: "nowrap", cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted" }}
                        onClick={() => window.dispatchEvent(new CustomEvent("show-player-stats", { detail: { id: p.id } }))}>{p.name}</div>
                      <div className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>{p.club || POS_NAMES[p.pos]}</div>
                    </div>
                  </div>
                </td>
                <td><span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Flag team={t} /> {p.teamName || (t && t.name) || p.team}</span></td>
                <td><span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.08)", color: "var(--navy-900)", fontSize: 10 }}>{POS_NAMES[p.pos]}</span></td>
                <td>
                  {owner
                    ? <span style={{ fontSize: 12, fontWeight: 600 }}>{owner}</span>
                    : <span style={{ fontSize: 12, color: "#0a8043", fontWeight: 600 }}>Free agent</span>}
                </td>
                {dynCol && <td className="num" style={{ textAlign: "right", fontWeight: 800, color: "var(--navy-900)" }}>{dynCol[1](p)}</td>}
                <td className="num" style={{ textAlign: "right", fontWeight: 700 }}>{p.pts}</td>
                <td className="num" style={{ textAlign: "right", color: p.selPct != null ? "var(--ink-700)" : "var(--ink-300)" }}>
                  {p.selPct != null ? `${Number(p.selPct).toFixed(1)}%` : "—"}
                </td>
                <td style={{ textAlign: "right" }}>
                  <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700, background: p.pts > 30 ? "rgba(0,217,107,0.18)" : p.pts > 20 ? "rgba(255,200,68,0.18)" : "rgba(0,0,0,0.06)", color: p.pts > 30 ? "#006b35" : p.pts > 20 ? "#7a5a00" : "var(--ink-500)" }}>
                    {p.pts > 30 ? "Hot" : p.pts > 20 ? "Form" : "Cold"}
                  </span>
                </td>
                <td style={{ textAlign: "right" }}>
                  {owner ? (
                    <span className="muted" style={{ fontSize: 11 }}>Owned</span>
                  ) : isPicking ? (
                    <div className="row fa-pickup" style={{ gap: 6, alignItems: "center", justifyContent: "flex-end" }}>
                      <select className="input-field" style={{ width: 140, padding: "4px 8px", fontSize: 12, background: "rgba(255,255,255,0.8)", color: "black" }} value={playerToDrop} onChange={e => setPlayerToDrop(e.target.value)}>
                        <option value="">{faOpen ? "-- Drop player --" : "-- Swap out --"}</option>
                        {eligibleDrops.map(s => (
                          <option key={s.id} value={s.id}>{s.name} ({s.teamName || s.team})</option>
                        ))}
                      </select>
                      <button className="btn btn--solid-dark" style={{ padding: "4px 8px", fontSize: 11, background: "var(--green-500)", color: "white" }} onClick={() => faOpen ? handlePickup(p) : handleAddWishlist(p)}>✔</button>
                      <button className="btn btn--ghost-dark" style={{ padding: "4px 8px", fontSize: 11, background: "var(--red-500)", color: "white" }} onClick={() => setActivePickup(null)}>✖</button>
                    </div>
                  ) : faOpen ? (
                    <button className="btn btn--draft" style={{ padding: "6px 14px", fontSize: 11 }} onClick={() => { setActivePickup(p); setPlayerToDrop(eligibleDrops[0]?.id || ""); }}>Pick up</button>
                  ) : (
                    <button className="btn btn--draft" style={{ padding: "6px 14px", fontSize: 11, background: "var(--gold-500)", color: "var(--navy-900)" }} onClick={() => { setActivePickup(p); setPlayerToDrop(eligibleDrops[0]?.id || ""); }}>+ Wishlist</button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
    </div>
  );
}

function WishlistTab() {
  const [bids, setBids] = React.useState(() => (window.MY_WISHLIST_BIDS || []).map(b => ({
    playerIn: Number(b.playerIn),
    playerOut: Number(b.playerOut),
    position: b.position,
  })));
  const [adding, setAdding] = React.useState(false);
  const [dropId, setDropId] = React.useState("");
  const [claimId, setClaimId] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  const win = window.WINDOW || {};
  const upcomingGw = win.gw || (window.TOURNAMENT && window.TOURNAMENT.currentGw);
  const phase = win.phase || "none";
  const isFaWindow = phase === "free_agents";
  const mySquad = (window.MY_SQUAD_IDS || []).map(id => window.PLAYER_MAP[id]).filter(Boolean);

  // Free agents eligible to claim, filtered to the chosen drop's position and
  // excluding players already on this manager's wishlist.
  const dropPlayer = dropId ? window.PLAYER_MAP[String(dropId)] : null;
  const eligibleClaims = (window.FREE_AGENTS || []).filter(p => {
    // The same incoming player MAY appear in multiple bids paired with different
    // players OUT (ordered fallbacks). Only block the EXACT (in, out) pair that
    // is already on the list for the currently-chosen drop.
    if (dropId && bids.some(b => b.playerIn === Number(p.id) && b.playerOut === Number(dropId))) return false;
    if (!dropPlayer) return true;
    return p.pos === dropPlayer.pos;
  });

  // Persist the given bids list to the backend NOW (an empty list clears the
  // wishlist doc). Used so the "X" remove and reorder are durable immediately —
  // not just local state that a refresh would revert.
  const persistBids = async (nextBids) => {
    if (!upcomingGw) return;
    const lid = window.LEAGUE.id;
    await apiCall("POST", `/leagues/${lid}/wishlist-bids`, {
      gw: upcomingGw,
      bids: nextBids.map(b => ({ playerIn: b.playerIn, playerOut: b.playerOut, position: b.position })),
    });
    window.MY_WISHLIST_BIDS = nextBids.slice();
  };

  const move = async (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= bids.length) return;
    const next = bids.slice();
    [next[i], next[j]] = [next[j], next[i]];
    const prev = bids;
    setBids(next);
    try { await persistBids(next); }
    catch (err) { setBids(prev); alert("Failed to reorder: " + (err.error || err.detail || JSON.stringify(err))); }
  };
  const removeBid = async (i) => {
    const next = bids.filter((_, k) => k !== i);
    const prev = bids;
    setBids(next);  // optimistic
    try { await persistBids(next); }
    catch (err) { setBids(prev); alert("Failed to remove bid: " + (err.error || err.detail || JSON.stringify(err))); }
  };

  const addBid = () => {
    if (!dropId || !claimId) { alert("Pick a player to drop and a free agent to claim."); return; }
    const dp = window.PLAYER_MAP[String(dropId)];
    const cp = window.PLAYER_MAP[String(claimId)];
    if (dp && cp && dp.pos !== cp.pos) { alert("Drop and claim must be the same position."); return; }
    if (bids.some(b => b.playerIn === Number(claimId) && b.playerOut === Number(dropId))) {
      alert("That exact swap is already on your wishlist. Pick a different player to drop to add it as a fallback."); return;
    }
    setBids([...bids, { playerIn: Number(claimId), playerOut: Number(dropId), position: cp ? POS_NAMES[cp.pos] : "?" }]);
    setAdding(false); setDropId(""); setClaimId("");
  };

  const save = async () => {
    if (!upcomingGw) { alert("No upcoming gameweek — the transfer window is closed."); return; }
    if (!bids.length) { alert("Add at least one bid first."); return; }
    setSaving(true);
    try {
      const lid = window.LEAGUE.id;
      await apiCall("POST", `/leagues/${lid}/wishlist-bids`, {
        gw: upcomingGw,
        bids: bids.map(b => ({ playerIn: b.playerIn, playerOut: b.playerOut, position: b.position })),
      });
      window.MY_WISHLIST_BIDS = bids.slice();
      alert(`Wishlist saved — ${bids.length} bid(s) for GW${upcomingGw}. They'll be resolved by the auction when the window closes.`);
    } catch (err) {
      alert("Failed to save wishlist: " + (err.error || err.detail || JSON.stringify(err)));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="col" style={{ gap: 12 }}>
      <div className={"alert " + (isFaWindow ? "alert--green" : "alert--gold")}>
        <div className="alert__icon" style={{ background: isFaWindow ? "var(--green-500)" : "var(--gold-500)" }}>{isFaWindow ? "✓" : "⏳"}</div>
        <div>
          <strong>Wishlist auction{upcomingGw ? ` · GW${upcomingGw}` : ""}</strong> · Build an ORDERED list of same-position
          swaps. When the free-agents window closes, a single batch auction resolves all managers' lists by waiver priority —
          higher priority claims first, one pick per round, cycling until no claims remain. Your <strong>order = your preference</strong> (top tried first).
          {" "}You can list the <strong>same player IN with different players OUT</strong> as fallbacks — if the first pairing can't resolve, the next is tried.
          {!isFaWindow && <span className="muted"> Bids can be edited any time; they only resolve during the free-agents window.</span>}
        </div>
      </div>

      <div className="card">
        <div className="table-scroll">
        <table className="table-clean">
          <thead>
            <tr>
              <th style={{ width: 60 }}>Pref</th>
              <th>Claim (in / out)</th>
              <th style={{ width: 120, textAlign: "right" }}>Reorder</th>
            </tr>
          </thead>
          <tbody>
            {bids.length === 0 && (
              <tr><td colSpan={3} className="muted" style={{ textAlign: "center", padding: 18 }}>No wishlist bids yet — add one below.</td></tr>
            )}
            {bids.map((b, i) => {
              const pIn = window.PLAYER_MAP[String(b.playerIn)] || { name: b.playerIn, team: "", pos: 1 };
              const pOut = window.PLAYER_MAP[String(b.playerOut)] || { name: b.playerOut, team: "", pos: 1 };
              const tIn = teamById(pIn.team);
              const tOut = teamById(pOut.team);
              return (
                <tr key={`${b.playerIn}_${b.playerOut}`}>
                  <td className="num" style={{ fontWeight: 800, fontSize: 16 }}>#{i + 1}</td>
                  <td>
                    <div className="wishlist-swap" style={{ display: "grid", gridTemplateColumns: "1fr 24px 1fr", gap: 10, alignItems: "center", maxWidth: 500 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "rgba(0,217,107,0.08)", borderRadius: 6, border: "1px solid rgba(0,217,107,0.25)" }}>
                        <Flag team={tIn} />
                        <div>
                          <div style={{ fontWeight: 700, fontSize: 13 }}>{pIn.name}</div>
                          <div className="muted" style={{ fontSize: 11 }}>IN · {POS_NAMES[pIn.pos]}</div>
                        </div>
                      </div>
                      <span className="h-display" style={{ color: "var(--ink-300)", textAlign: "center" }}>↔</span>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "rgba(230,57,70,0.08)", borderRadius: 6, border: "1px solid rgba(230,57,70,0.20)" }}>
                        <Flag team={tOut} />
                        <div>
                          <div style={{ fontWeight: 700, fontSize: 13, textDecoration: pOut.elim ? "line-through" : "none" }}>{pOut.name}</div>
                          <div className="muted" style={{ fontSize: 11 }}>OUT · {pOut.elim || tOut?.elim ? "ELIMINATED" : POS_NAMES[pOut.pos]}</div>
                        </div>
                      </div>
                    </div>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <div className="row" style={{ gap: 4, justifyContent: "flex-end" }}>
                      <button className="btn btn--ghost-dark" style={{ padding: "4px 8px", fontSize: 12 }} disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
                      <button className="btn btn--ghost-dark" style={{ padding: "4px 8px", fontSize: 12 }} disabled={i === bids.length - 1} onClick={() => move(i, 1)}>↓</button>
                      <button className="btn btn--ghost-dark" style={{ padding: "4px 8px", fontSize: 11, background: "var(--red-500)", color: "white" }} onClick={() => removeBid(i)}>✕</button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>

        {adding ? (
          <div className="col" style={{ padding: 18, gap: 12, borderTop: "1px solid var(--border)", background: "rgba(0,0,0,0.02)" }}>
            <div className="wishlist-add" style={{ display: "flex", gap: 12, justifyContent: "center", alignItems: "center" }}>
              <div className="col">
                <span style={{ fontSize: 11, fontWeight: 700, marginBottom: 4 }}>DROP PLAYER</span>
                <select className="input-field" style={{ width: 180, padding: 8, background: "white", color: "black" }} value={dropId} onChange={e => { setDropId(e.target.value); setClaimId(""); }}>
                  <option value="">-- Drop player --</option>
                  {mySquad.map(s => (
                    <option key={s.id} value={s.id}>{s.name} ({POS_NAMES[s.pos]})</option>
                  ))}
                </select>
              </div>
              <span className="h-display" style={{ fontSize: 20, color: "var(--ink-400)", marginTop: 16 }}>↔</span>
              <div className="col">
                <span style={{ fontSize: 11, fontWeight: 700, marginBottom: 4 }}>CLAIM FREE AGENT</span>
                <select className="input-field" style={{ width: 180, padding: 8, background: "white", color: "black" }} value={claimId} onChange={e => setClaimId(e.target.value)} disabled={!dropId}>
                  <option value="">-- Claim player --</option>
                  {eligibleClaims.map(s => (
                    <option key={s.id} value={s.id}>{s.name} ({POS_NAMES[s.pos]})</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="row" style={{ gap: 8, justifyContent: "center" }}>
              <button className="btn btn--ghost-dark" onClick={() => { setAdding(false); setDropId(""); setClaimId(""); }}>Cancel</button>
              <button className="btn btn--primary" onClick={addBid} disabled={!dropId || !claimId}>Add to wishlist</button>
            </div>
          </div>
        ) : (
          <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border)", display: "flex", gap: 10, justifyContent: "center" }}>
            <button className="btn btn--ghost-dark" onClick={() => setAdding(true)}>+ Add bid</button>
            <button className="btn btn--primary" onClick={save} disabled={saving || !bids.length}>{saving ? "Saving…" : `Save wishlist (${bids.length})`}</button>
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 18 }}>
        <div className="h-display" style={{ fontSize: 14, marginBottom: 10 }}>Auction order · League-wide waiver priority</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(80px, 1fr))", gap: 6 }}>
          {(window.MANAGERS || []).sort((a, b) => a.waiverPri - b.waiverPri).map((m, i) => (
            <div key={m.uid} style={{
              padding: "10px 8px", borderRadius: 6,
              background: m.uid === window.ME ? "var(--gold-500)" : "var(--cream)",
              border: "1px solid " + (m.uid === window.ME ? "var(--gold-500)" : "var(--border)"),
              textAlign: "center",
            }}>
              <div className="mono" style={{ fontSize: 10, fontWeight: 700, color: "var(--ink-500)" }}>#{i + 1}</div>
              <div style={{ fontSize: 11, fontWeight: 700, marginTop: 2 }}>{m.name.replace(" (you)", "")}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MySquadTab() {
  const grouped = { 1: [], 2: [], 3: [], 4: [] };
  MY_SQUAD_IDS.forEach(id => {
    const p = playerById(id);
    if (p) grouped[p.pos].push(p);
  });

  return (
    <div className="col" style={{ gap: 12 }}>
      {[1, 2, 3, 4].map(pos => (
        <div key={pos} className="card">
          <div style={{ padding: "12px 18px", background: "var(--cream)", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <strong>{POS_NAMES[pos]}s ({grouped[pos].length})</strong>
            <span className="muted" style={{ fontSize: 12 }}>Quota: {pos === 1 ? 2 : pos === 4 ? 3 : 5}</span>
          </div>
          {grouped[pos].map(p => {
            const t = teamById(p.team);
            const isElim = p.elim || t?.elim;
            return (
              <div key={p.id} className="squad-row" style={{ display: "grid", gridTemplateColumns: "auto 1fr 100px 100px", padding: "10px 18px", borderTop: "1px solid var(--border)", alignItems: "center", gap: 12, opacity: isElim ? 0.7 : 1 }}>
                <div style={{ width: 32, height: 32 }}><Jersey team={t} pos={p.pos} /></div>
                <div>
                  <div style={{ fontWeight: 700, cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted", display: "inline" }}
                    onClick={() => window.dispatchEvent(new CustomEvent("show-player-stats", { detail: { id: p.id } }))}>{p.name}</div>
                  {isElim && <span className="pill pill--red" style={{ marginLeft: 8, fontSize: 9 }}>OUT</span>}
                  <div className="muted" style={{ fontSize: 12 }}>{t.name} · {POS_NAMES[p.pos]}</div>
                </div>
                <div className="num" style={{ textAlign: "right" }}><span className="muted" style={{ fontSize: 11 }}>Pts</span> <strong>{p.pts}</strong></div>
                {/* Drop removed — squad exits go through Trade / the FA swap flow */}
                <button className="btn btn--ghost-dark" style={{ padding: "6px 12px", fontSize: 11 }}>Trade</button>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function TransferHistoryTab() {
  // League-wide transfer history grouped per gameweek (newest first). Each GW
  // shows BOTH:
  //   • manager↔manager trades that resolved that GW (transactions, type="trade")
  //   • the wishlist auction — EVERY manager's bids in resolution order, each
  //     claimed (✓) or cancelled (↓ with the manager who won the player).
  // Sources: GET /wishlist-results (durable ordered events) + GET /transactions.
  const [wl, setWl] = React.useState(null);
  const [txns, setTxns] = React.useState(null);
  React.useEffect(() => {
    const lid = window.LEAGUE && window.LEAGUE.id;
    if (!lid) { setWl([]); setTxns([]); return; }
    let cancelled = false;
    apiCall("GET", `/leagues/${lid}/wishlist-results`)
      .then(res => { if (!cancelled) setWl((res && res.results) || []); })
      .catch(() => { if (!cancelled) setWl([]); });
    apiCall("GET", `/leagues/${lid}/transactions?limit=500`)
      .then(res => { if (!cancelled) setTxns(Array.isArray(res) ? res : ((res && res.transactions) || [])); })
      .catch(() => { if (!cancelled) setTxns([]); });
    return () => { cancelled = true; };
  }, []);

  const pl = (id) => (window.PLAYER_MAP || {})[String(id)] || { name: id, pos: 3, team: null };
  const mgr = (uid) => { const m = managerById(uid); return m ? (m.team || m.name || uid) : uid; };

  // Flatten one auction doc into an ordered list of {uid, playerIn, playerOut,
  // claimed, wonByUid}. Prefer the chronological `events`; fall back to the
  // per-manager `results` for older payloads with no event log.
  const auctionItems = (auction) => {
    if (!auction) return [];
    if ((auction.events || []).length) {
      return auction.events.map(e => ({
        uid: e.uid, playerIn: e.playerIn, playerOut: e.playerOut,
        claimed: e.type === "claim", wonByUid: e.wonByUid,
      }));
    }
    const out = [];
    (auction.results || []).forEach(r => (r.bids || []).forEach(b => out.push({
      uid: r.uid, playerIn: b.playerIn, playerOut: b.playerOut,
      claimed: b.status === "claimed", wonByUid: b.wonByUid,
    })));
    return out;
  };

  const chip = (p, kind) => {
    const isIn = kind === "in";
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 9px", borderRadius: 7,
        background: isIn ? "rgba(0,168,67,0.12)" : "rgba(230,57,70,0.10)", color: isIn ? "#0a7d3c" : "#b3303a", fontWeight: 700, fontSize: 13 }}>
        <Flag team={teamById(p.team)} /> {p.name} <span style={{ fontSize: 10, opacity: 0.8 }}>{isIn ? "IN" : "OUT"}</span>
      </span>
    );
  };

  if (wl === null || txns === null) {
    return <div className="card" style={{ padding: "24px 18px", textAlign: "center", color: "var(--ink-500)" }}>Loading transfer history…</div>;
  }

  // Trade transactions store players as objects ({playerId, name, ...}); resolve
  // to ids so the chip helper can look them up in PLAYER_MAP like everything else.
  const tradePids = (arr) => (arr || []).map(p => (p && typeof p === "object") ? p.playerId : p);
  const trades = (txns || []).filter(t => t && t.type === "trade_accepted");
  // Free-agent pickups (playerIn + playerOut) and pure drops (playerOut only).
  const moves = (txns || []).filter(t => t && (t.type === "free_agent" || t.type === "drop"));
  const gws = [...new Set([
    ...(wl || []).map(r => r.gw),
    ...trades.map(t => t.gw),
    ...moves.map(t => t.gw),
  ].filter(g => g != null))].sort((a, b) => b - a);

  if (!gws.length) {
    return (
      <div className="card" style={{ padding: "24px 18px", textAlign: "center", color: "var(--ink-500)" }}>
        No transfer history yet — manager trades and wishlist auctions across the league will appear here per gameweek.
      </div>
    );
  }

  return (
    <div className="col" style={{ gap: 16 }}>
      {gws.map(gw => {
        const items = auctionItems((wl || []).find(r => r.gw === gw));
        const gwTrades = trades.filter(t => t.gw === gw);
        const gwMoves = moves.filter(m => m.gw === gw);
        const nClaimed = items.filter(i => i.claimed).length;
        return (
          <div key={gw} className="card" style={{ overflow: "hidden" }}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>Gameweek {gw}</strong>
              <span className="muted" style={{ fontSize: 12 }}>
                {gwTrades.length} trade{gwTrades.length === 1 ? "" : "s"} · {gwMoves.length} free agent{gwMoves.length === 1 ? "" : "s"} · {nClaimed} claimed · {items.length - nClaimed} cancelled
              </span>
            </div>

            {/* Manager↔manager trades */}
            {gwTrades.map((t, i) => (
              <div key={`t${i}`} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "10px 16px", borderTop: "1px solid var(--border)", background: "rgba(46,91,255,0.04)" }}>
                <span className="history-badge" style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.06em", color: "#2e5bff", background: "rgba(46,91,255,0.12)", padding: "3px 7px", borderRadius: 6 }}>TRADE</span>
                <strong style={{ fontSize: 13 }}>{mgr(t.proposerUid)}</strong>
                {tradePids(t.proposerPlayers).map((id, k) => <span key={`p${k}`}>{chip(pl(id), "out")}</span>)}
                <span style={{ color: "var(--ink-400)" }}>↔</span>
                {tradePids(t.targetPlayers).map((id, k) => <span key={`g${k}`}>{chip(pl(id), "in")}</span>)}
                <strong style={{ fontSize: 13 }}>{mgr(t.targetUid)}</strong>
              </div>
            ))}

            {/* Wishlist auction — every manager, in resolution order */}
            {items.map((it, i) => {
              const pIn = pl(it.playerIn), pOut = pl(it.playerOut);
              return (
                <div key={`w${i}`} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "10px 16px", borderTop: "1px solid var(--border)" }}>
                  <strong style={{ fontSize: 13, minWidth: 90 }}>{mgr(it.uid)}</strong>
                  {chip(pIn, "in")}
                  <span style={{ color: "var(--ink-400)" }}>↔</span>
                  {chip(pOut, "out")}
                  <span style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 800,
                    color: it.claimed ? "#0a8043" : "#c0392b" }}>
                    {it.claimed
                      ? "✓ Claimed"
                      : <span title="cancelled — player went to another manager">↓ {it.wonByUid ? `won by ${mgr(it.wonByUid)}` : "Cancelled"}</span>}
                  </span>
                </div>
              );
            })}

            {/* Free-agent pickups / drops (instant moves outside the auction) */}
            {gwMoves.map((m, i) => {
              const pIn = m.playerIn != null ? pl(m.playerIn) : null;
              const pOut = m.playerOut != null ? pl(m.playerOut) : null;
              return (
                <div key={`fa${i}`} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "10px 16px", borderTop: "1px solid var(--border)", background: "rgba(0,168,67,0.04)" }}>
                  <span className="history-badge" style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.06em", color: "#0a7d3c", background: "rgba(0,168,67,0.12)", padding: "3px 7px", borderRadius: 6 }}>FREE AGENT</span>
                  <strong style={{ fontSize: 13, minWidth: 90 }}>{mgr(m.uid)}</strong>
                  {pIn && chip(pIn, "in")}
                  {pIn && pOut && <span style={{ color: "var(--ink-400)" }}>↔</span>}
                  {pOut && chip(pOut, "out")}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

function DraftTab() {
  const [watchlist, setWatchlist] = React.useState(new Set());
  const [loadingWatchlist, setLoadingWatchlist] = React.useState(false);
  const [search, setSearch] = React.useState("");
  const [posFilter, setPosFilter] = React.useState("all");
  const [nationFilter, setNationFilter] = React.useState("all");
  const [ownerFilter, setOwnerFilter] = React.useState("all");
  const [page, setPage] = React.useState(0);
  const [pageSize, setPageSize] = React.useState(25);
  const [draggedIndex, setDraggedIndex] = React.useState(null);

  const activePlayers = window.PLAYERS || [];
  const draftHistory = window.DRAFT_HISTORY || [];
  const managers = window.MANAGERS || [];
  const league = window.LEAGUE || {};
  const isMyTurn = window.DRAFT_STATE && window.DRAFT_STATE.isMyTurn;
  const PLAYER_MAP = window.PLAYER_MAP || {};
  const ME = window.ME;

  const POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"};

  React.useEffect(() => {
    const fetchWatchlist = async () => {
      setLoadingWatchlist(true);
      try {
        const lid = window.LEAGUE.id;
        const res = await apiCall("GET", `/leagues/${lid}/draft/watchlist`);
        if (res && res.playerIds) {
          setWatchlist(new Set(res.playerIds.map(String)));
        }
      } catch (err) {
        console.warn("Failed to fetch watchlist:", err);
      } finally {
        setLoadingWatchlist(false);
      }
    };
    if (window.LEAGUE && window.LEAGUE.id) {
      fetchWatchlist();
    }
  }, []);

  const handleToggleWatchlist = async (player) => {
    const pId = String(player.id);
    const updated = new Set(watchlist);
    if (updated.has(pId)) {
      updated.delete(pId);
    } else {
      updated.add(pId);
    }
    setWatchlist(updated);
    
    // Save to server
    try {
      const lid = window.LEAGUE.id;
      const ids = Array.from(updated).map(Number);
      await apiCall("PUT", `/leagues/${lid}/draft/watchlist`, { playerIds: ids });
    } catch (err) {
      console.error("Failed to update watchlist on server:", err);
    }
  };

  const handleDragStart = (e, index) => {
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e, index) => {
    e.preventDefault();
  };

  const handleDrop = async (e, targetIndex) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === targetIndex) return;

    const watchlistArray = Array.from(watchlist);
    const [removed] = watchlistArray.splice(draggedIndex, 1);
    watchlistArray.splice(targetIndex, 0, removed);

    setWatchlist(new Set(watchlistArray));
    setDraggedIndex(null);

    // Save to server
    try {
      const lid = window.LEAGUE.id;
      const ids = watchlistArray.map(Number);
      await apiCall("PUT", `/leagues/${lid}/draft/watchlist`, { playerIds: ids });
    } catch (err) {
      console.error("Failed to save reordered watchlist:", err);
    }
  };

  const handleDraftPick = async (playerId) => {
    try {
      const lid = window.LEAGUE.id;
      const idKey = Math.random().toString(36).substring(2) + Date.now().toString(36);
      const numericId = isNaN(Number(playerId)) ? Number(String(playerId).replace("p_", "")) : Number(playerId);
      await apiCall("POST", `/leagues/${lid}/draft/pick`, { playerId: numericId, idempotencyKey: idKey });
      alert("Draft pick successful!");
      window.location.reload();
    } catch (err) {
      alert("Draft pick failed: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  // Taken player IDs
  const taken = new Set(draftHistory.map(p => String(p.playerId)));

  // Map player ID to owner info
  const ownerMap = {};
  draftHistory.forEach(p => {
    const manager = managers.find(m => m.uid === p.uid);
    ownerMap[String(p.playerId)] = manager ? (manager.team || manager.name) : "Drafted";
  });

  // Calculate nations list
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

  // Filter player pool
  const pool = React.useMemo(() => {
    return activePlayers.filter(p => {
      const pIdStr = String(p.id);

      // Search
      if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;

      // Position
      if (posFilter !== "all" && String(p.pos) !== posFilter) return false;

      // Nation
      if (nationFilter !== "all" && p.team !== nationFilter) return false;

      // Owner
      const ownerName = ownerMap[pIdStr];
      if (ownerFilter === "unowned" && ownerName) return false;
      if (ownerFilter === "my") {
        const pPick = draftHistory.find(dh => String(dh.playerId) === pIdStr);
        if (!pPick || pPick.uid !== window.ME) return false;
      }
      if (ownerFilter !== "all" && ownerFilter !== "unowned" && ownerFilter !== "my") {
        const pPick = draftHistory.find(dh => String(dh.playerId) === pIdStr);
        if (!pPick || pPick.uid !== ownerFilter) return false;
      }

      return true;
    }).sort((a, b) => a.dr - b.dr);
  }, [activePlayers, draftHistory, search, posFilter, nationFilter, ownerFilter]);

  // Helper to derive statistics based on points & position (for realism)
  const getDerivedStats = (p) => {
    const pts = p.pts || 0;
    const rating = Math.max(72, Math.min(99, 98 - Math.floor(p.dr / 4) + (pts % 3)));
    const ppg = pts > 0 ? (pts / 3).toFixed(1) : "0.0";
    const mp = pts > 0 ? 3 : 0;
    let g = 0, a = 0, cs = 0;
    if (p.pos === 1) { // GK
      cs = Math.floor(pts / 4);
    } else if (p.pos === 2) { // DEF
      cs = Math.floor(pts / 4);
      g = Math.floor(pts / 12);
      a = Math.floor((pts % 12) / 6);
    } else if (p.pos === 3) { // MID
      g = Math.floor(pts / 8);
      a = Math.floor((pts % 8) / 4);
    } else if (p.pos === 4) { // FWD
      g = Math.floor(pts / 6);
      a = Math.floor((pts % 6) / 4);
    }
    return { rating, ppg, mp, g, a, cs };
  };

  // Pagination calculations
  const totalPlayers = pool.length;
  const startIdx = page * pageSize;
  const visiblePlayers = pool.slice(startIdx, startIdx + pageSize);

  // Watchlist array in order of selection (matching watchlist Set)
  // watchlist stores string IDs; PLAYER_MAP is keyed by numbers — convert before lookup
  const watchlistArray = Array.from(watchlist).map(id => PLAYER_MAP[Number(id)]).filter(Boolean);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, alignItems: "start" }}>
      {/* LEFT COLUMN: Players Pool */}
      <div className="card" style={{ padding: 18, minWidth: 0, overflow: "hidden" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h3 className="h-display" style={{ fontSize: 20, margin: 0 }}>Players</h3>
          <div style={{ color: "var(--ink-500)", fontSize: 13, fontWeight: 600 }}>{totalPlayers} Players found</div>
        </div>

        {/* Filters */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
          <input
            type="text"
            placeholder="Search players..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0); }}
            style={{
              padding: "8px 14px", borderRadius: 999, border: "1px solid var(--border-strong)",
              background: "white", color: "var(--navy-900)", fontSize: 12, minWidth: 160, outline: "none"
            }}
          />

          <select
            value={nationFilter}
            onChange={e => { setNationFilter(e.target.value); setPage(0); }}
            className="input-field"
            style={{
              padding: "6px 12px", borderRadius: 999, border: "1px solid var(--border-strong)",
              background: "white", color: "var(--navy-900)", fontSize: 12, fontWeight: 700, outline: "none", cursor: "pointer"
            }}
          >
            <option value="all">All Nations</option>
            {nationsList.map(n => (
              <option key={n.code} value={n.code}>{n.name}</option>
            ))}
          </select>

          <select
            value={ownerFilter}
            onChange={e => { setOwnerFilter(e.target.value); setPage(0); }}
            className="input-field"
            style={{
              padding: "6px 12px", borderRadius: 999, border: "1px solid var(--border-strong)",
              background: "white", color: "var(--navy-900)", fontSize: 12, fontWeight: 700, outline: "none", cursor: "pointer"
            }}
          >
            <option value="all">All Owners</option>
            <option value="unowned">Unowned</option>
            <option value="my">My Team</option>
            {managers.filter(m => m.uid !== window.ME).map(m => (
              <option key={m.uid} value={m.uid}>{m.team}</option>
            ))}
          </select>

          <div style={{ display: "inline-flex", padding: 3, background: "rgba(0,0,0,0.06)", borderRadius: 999 }}>
            {["all", "1", "2", "3", "4"].map(p => (
              <button
                key={p}
                style={{
                  padding: "6px 12px", fontSize: 11, fontWeight: 700, borderRadius: 999,
                  background: posFilter === p ? "var(--navy-900)" : "transparent",
                  color: posFilter === p ? "white" : "var(--ink-700)",
                }}
                onClick={() => { setPosFilter(p); setPage(0); }}
              >
                {p === "all" ? "ALL" : POS_NAMES[Number(p)]}
              </button>
            ))}
          </div>
        </div>

        {/* Players Table */}
        <div style={{ overflowX: "auto" }}>
          <table className="table-clean" style={{ fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border-strong)" }}>
                <th style={{ padding: "10px 6px" }}>Name</th>
                <th style={{ padding: "10px 4px", textAlign: "center" }}>Rating</th>
                <th style={{ padding: "10px 4px", textAlign: "center" }}>Pts</th>
                <th style={{ padding: "10px 4px", textAlign: "center" }}>PPG</th>
                <th style={{ padding: "10px 4px", textAlign: "center" }}>MP</th>
                <th style={{ padding: "10px 4px", textAlign: "center" }}>G</th>
                <th style={{ padding: "10px 4px", textAlign: "center" }}>A</th>
                <th style={{ padding: "10px 4px", textAlign: "center" }}>CS</th>
                <th style={{ padding: "10px 6px" }}>Owner</th>
                <th style={{ padding: "10px 4px", textAlign: "center" }}>Pick</th>
                <th style={{ padding: "10px 4px", textAlign: "center" }}>Auto Pick</th>
              </tr>
            </thead>
            <tbody>
              {visiblePlayers.map(p => {
                const t = teamById(p.team);
                const isWatched = watchlist.has(String(p.id));
                const isDrafted = taken.has(String(p.id));
                const ownerName = ownerMap[String(p.id)] || "-";
                const { rating, ppg, mp, g, a, cs } = getDerivedStats(p);

                return (
                  <tr key={p.id} className={isDrafted ? "muted" : ""}>
                    <td style={{ padding: "10px 6px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Flag team={t} />
                        <div style={{ display: "flex", flexDirection: "column" }}>
                          <span style={{ fontWeight: 700, whiteSpace: "nowrap", cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted" }}
                            onClick={() => window.dispatchEvent(new CustomEvent("show-player-stats", { detail: { id: p.id } }))}>{p.name}</span>
                          <span style={{ fontSize: 11, color: "var(--ink-500)", whiteSpace: "nowrap" }}>{t?.name || p.team}</span>
                        </div>
                        <span className="pill pill--dark" style={{ fontSize: 9, padding: "2px 4px" }}>{POS_NAMES[p.pos]}</span>
                      </div>
                    </td>
                    <td style={{ padding: "10px 4px", textAlign: "center", fontWeight: 700 }} className="num">{rating}</td>
                    <td style={{ padding: "10px 4px", textAlign: "center", fontWeight: 700 }} className="num">{p.pts || 0}</td>
                    <td style={{ padding: "10px 4px", textAlign: "center" }} className="num">{ppg}</td>
                    <td style={{ padding: "10px 4px", textAlign: "center" }} className="num">{mp}</td>
                    <td style={{ padding: "10px 4px", textAlign: "center" }} className="num">{g || 0}</td>
                    <td style={{ padding: "10px 4px", textAlign: "center" }} className="num">{a || 0}</td>
                    <td style={{ padding: "10px 4px", textAlign: "center" }} className="num">{cs || 0}</td>
                    <td style={{ padding: "10px 6px", maxWidth: 90, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {isDrafted ? <span className="pill pill--gold" style={{ fontSize: 10 }}>{ownerName}</span> : "-"}
                    </td>
                    <td style={{ padding: "10px 4px", textAlign: "center" }}>
                      <button
                        className="btn btn--draft"
                        style={{ padding: "4px 8px", fontSize: 11 }}
                        disabled={isDrafted || !isMyTurn}
                        onClick={() => handleDraftPick(p.id)}
                      >
                        Pick
                      </button>
                    </td>
                    <td style={{ padding: "10px 4px", textAlign: "center" }}>
                      <button
                        className={isWatched ? "btn btn--ghost-dark" : "btn btn--primary"}
                        style={{ padding: "4px 8px", fontSize: 11 }}
                        disabled={isDrafted}
                        onClick={() => handleToggleWatchlist(p)}
                      >
                        {isWatched ? "Remove" : "Add"}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {visiblePlayers.length === 0 && (
                <tr>
                  <td colSpan="11" style={{ textAlign: "center", padding: 24, color: "var(--ink-500)" }}>
                    No players match the filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination controls */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
          <div style={{ color: "var(--ink-500)", fontSize: 12 }}>
            Showing {totalPlayers > 0 ? startIdx + 1 : 0}–{Math.min(startIdx + pageSize, totalPlayers)} of {totalPlayers}
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "var(--ink-500)" }}>Per page:</span>
            <select
              value={pageSize}
              onChange={e => { setPageSize(Number(e.target.value)); setPage(0); }}
              className="input-field"
              style={{ padding: "4px 8px", fontSize: 12 }}
            >
              {[10, 25, 50, 100].map(sz => (
                <option key={sz} value={sz}>{sz}</option>
              ))}
            </select>
            <button
              className="btn btn--ghost-dark"
              style={{ padding: "5px 12px", fontSize: 11 }}
              disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
            >
              Previous
            </button>
            <button
              className="btn btn--ghost-dark"
              style={{ padding: "5px 12px", fontSize: 11 }}
              disabled={startIdx + pageSize >= totalPlayers}
              onClick={() => setPage(p => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* RIGHT COLUMN: Auto Pick List */}
      <div className="card" style={{ padding: 18, minWidth: 0, overflow: "hidden" }}>
        <h3 className="h-display" style={{ fontSize: 20, margin: 0, marginBottom: 16 }}>Auto Pick List</h3>
        <div style={{ background: "rgba(91,61,242,0.06)", padding: "10px 12px", borderRadius: 8, fontSize: 12, color: "var(--navy-800)", marginBottom: 14 }}>
          💡 Drag handles <strong>⣿</strong> to reorder. If you go on-clock and miss your turn, the server drafts your highest-ranked available player.
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="table-clean" style={{ fontSize: 13, width: "100%" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border-strong)" }}>
                <th style={{ width: 50, padding: "10px 6px" }}>Order</th>
                <th style={{ padding: "10px 6px" }}>Name</th>
                <th style={{ textAlign: "right", padding: "10px 6px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {watchlistArray.map((p, idx) => {
                const t = teamById(p.team);
                const isDrafted = taken.has(String(p.id));

                return (
                  <tr
                    key={p.id}
                    draggable={!isDrafted}
                    onDragStart={(e) => handleDragStart(e, idx)}
                    onDragOver={(e) => handleDragOver(e, idx)}
                    onDrop={(e) => handleDrop(e, idx)}
                    className={isDrafted ? "muted" : ""}
                    style={{ cursor: isDrafted ? "default" : "grab" }}
                  >
                    <td style={{ padding: "10px 6px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        {!isDrafted ? (
                          <span style={{ cursor: "grab", color: "var(--ink-300)", fontWeight: "bold" }} title="Drag to reorder">
                            ⣿
                          </span>
                        ) : (
                          <span style={{ width: 10 }} />
                        )}
                        <span className="mono" style={{ fontWeight: 700 }}>{idx + 1}</span>
                      </div>
                    </td>
                    <td style={{ padding: "10px 6px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <Flag team={t} />
                        <div>
                          <strong style={{ whiteSpace: "nowrap" }}>{p.name}</strong>
                          <div style={{ fontSize: 11, color: "var(--ink-500)", whiteSpace: "nowrap" }}>{POS_NAMES[p.pos]} · {t?.id || p.team}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: "10px 6px" }}>
                      <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                        <button
                          className="btn btn--ghost-dark"
                          style={{ padding: "4px 6px", fontSize: 11 }}
                          onClick={() => handleToggleWatchlist(p)}
                        >
                          Remove
                        </button>
                        <button
                          className="btn btn--draft"
                          style={{ padding: "4px 6px", fontSize: 11 }}
                          disabled={isDrafted || !isMyTurn}
                          onClick={() => handleDraftPick(p.id)}
                        >
                          Pick
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {watchlistArray.length === 0 && (
                <tr>
                  <td colSpan="3" style={{ textAlign: "center", padding: 24, color: "var(--ink-500)" }}>
                    Your auto pick list is empty. Add players from the left panel.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { BracketScreen, TransfersScreen });
