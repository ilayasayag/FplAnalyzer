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
// Ilay-only editor for the league's TIMED window schedule. Each row is a phase
// that takes effect at a given Israel-time instant; the backend applies them
// lazily as the clock passes each one. Times are entered in Israel time (IDT,
// UTC+3 — correct for the summer-2026 tournament) and converted to UTC on save.
function WindowScheduleAdmin() {
  if (!window.IS_SUPER_ADMIN) return null;
  const lid = window.LEAGUE && window.LEAGUE.id;
  const IL_OFFSET_MIN = 180; // Israel Daylight Time = UTC+3 (all WC26 dates)

  const utcToIsraelLocal = (iso) => {
    const ms = Date.parse(iso);
    if (isNaN(ms)) return "";
    return new Date(ms + IL_OFFSET_MIN * 60000).toISOString().slice(0, 16);
  };
  const israelLocalToUtc = (local) => {
    if (!local) return null;
    const [d, t] = local.split("T");
    const [Y, Mo, Da] = d.split("-").map(Number);
    const [H, Mi] = (t || "00:00").split(":").map(Number);
    const ms = Date.UTC(Y, Mo - 1, Da, H, Mi) - IL_OFFSET_MIN * 60000;
    return new Date(ms).toISOString();
  };

  const defaultGw = (window.WINDOW && window.WINDOW.gw) || (window.TOURNAMENT && window.TOURNAMENT.currentGw) || null;
  const initial = ((window.WINDOW && window.WINDOW.scheduledOverrides) || []).map(e => ({
    phase: e.phase, local: utcToIsraelLocal(e.effectiveAt), gw: e.gw != null ? e.gw : defaultGw,
  }));
  // Per-GW squad-lock overrides ({gwStr: IL-local}) — a SEPARATE mechanism from
  // the phase transitions (is_lineup_locked reads lineupLockOverride, not the
  // windowSchedule), surfaced here so every window change for a GW is editable
  // in one place.
  const initialLocks = Object.fromEntries(
    Object.entries((window.WINDOW && window.WINDOW.lineupLockOverride) || {})
      .map(([gw, iso]) => [String(gw), utcToIsraelLocal(iso)])
  );
  const [rows, setRows] = React.useState(initial);
  const [locks, setLocks] = React.useState(initialLocks);
  const [saving, setSaving] = React.useState(false);
  const [msg, setMsg] = React.useState("");
  // Paginate the editor one GW at a time (← / →) so the admin focuses on a
  // single gameweek's windows instead of a long stacked list.
  const [gwCursor, setGwCursor] = React.useState(0);
  const setLock = (gw, local) => setLocks(ls => ({ ...ls, [String(gw)]: local }));

  const PHASES = [["trade", "Trade"], ["free_agents", "Free agents"], ["next_gw_bid", "Gameweek"], ["none", "Closed"]];
  const inputStyle = { padding: "7px 10px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.08)", color: "white", fontSize: 13 };

  const setRow = (i, patch) => setRows(rs => rs.map((r, k) => k === i ? { ...r, ...patch } : r));
  const addRowForGw = (gw) => setRows(rs => [...rs, { phase: "free_agents", local: "", gw }]);
  const removeRow = (i) => setRows(rs => rs.filter((_, k) => k !== i));
  const addGameweek = () => {
    const gws = rows.map(r => r.gw).filter(g => g != null);
    const suggested = gws.length ? Math.max(...gws) + 1 : (defaultGw || 1);
    const input = window.prompt("Add a windows group for which gameweek?", String(suggested));
    if (input == null) return;
    const gw = Number(input);
    if (!Number.isFinite(gw)) return;
    addRowForGw(gw);
    // Jump the pager to the new GW (predict its sorted index: numeric GWs asc).
    const numeric = groupKeys.filter(k => k !== "—").map(Number);
    const withNew = [...new Set([...numeric, gw])].sort((a, b) => a - b);
    setGwCursor(withNew.indexOf(gw));
  };

  const persist = async (body, okMsg) => {
    setSaving(true); setMsg("");
    try {
      const res = await apiCall("POST", `/leagues/${lid}/admin/window-schedule`, body);
      // A schedule already resolving to Free agents auto-runs the wishlist
      // auction server-side — report what happened instead of a silent reload.
      const ar = res && res.wishlistAutoRun;
      if (ar && ar.status === "done") {
        setMsg(`Saved — wishlist auction ran for GW${ar.gw} (${ar.claims} claims). Reloading…`);
        setTimeout(() => window.location.reload(), 2200);
      } else if (ar && (ar.status === "blocked" || ar.status === "failed")) {
        setMsg(`Saved, but wishlist auto-run ${ar.status}: ${ar.reason || ar.error || ""}`);
        setTimeout(() => window.location.reload(), 3500);
      } else {
        setMsg(okMsg);
        setTimeout(() => window.location.reload(), 900);
      }
    } catch (e) {
      setMsg("Failed: " + (e.error || e.detail || JSON.stringify(e)));
      setSaving(false);
    }
  };
  const save = () => {
    if (saving) return;
    if (rows.some(r => !r.local)) { setMsg("Every transition needs a date/time."); return; }
    const schedule = rows
      .map(r => ({ phase: r.phase, effectiveAt: israelLocalToUtc(r.local), gw: r.gw != null ? Number(r.gw) : undefined }))
      .filter(e => e.effectiveAt)
      .sort((a, b) => a.effectiveAt.localeCompare(b.effectiveAt));
    // Per-GW lock overrides: present blank fields are dropped (revert to fixture
    // clock); the backend replaces the whole map with what we send.
    const lineupLockOverride = {};
    Object.entries(locks).forEach(([gw, local]) => {
      if (local) { const iso = israelLocalToUtc(local); if (iso) lineupLockOverride[gw] = iso; }
    });
    persist({ schedule, lineupLockOverride }, "Saved. Reloading…");
  };
  const clearAll = () => {
    if (saving) return;
    if (!window.confirm("Clear all phase transitions? Lineup-lock overrides are kept; the window phase reverts to the manual override / fixture clock.")) return;
    persist({ schedule: [] }, "Cleared. Reloading…");
  };

  // Group transitions by GW (keeping each row's index for edits), sorted by GW
  // then time — the admin sees each gameweek's windows + dates together.
  const groups = {};
  rows.forEach((r, i) => {
    const key = r.gw == null ? "—" : String(r.gw);
    (groups[key] = groups[key] || []).push({ r, i });
  });
  const groupKeys = Object.keys(groups).sort(
    (a, b) => (a === "—" ? 1 : b === "—" ? -1 : Number(a) - Number(b))
  );
  const gwIdx = Math.min(Math.max(gwCursor, 0), Math.max(groupKeys.length - 1, 0));
  const curKey = groupKeys[gwIdx];

  return (
    <div className="card-dark" style={{ padding: 0, overflow: "hidden" }}>
      <div style={{ padding: "14px 20px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 800, color: "white" }}>⏱ Window schedule · Ilay only</div>
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.6)", marginTop: 2, maxWidth: 540 }}>
            Timed phase changes — times in <strong>Israel (IDT, UTC+3)</strong>, grouped by gameweek. The phase flips the next time the window is read after each time. A <strong>Free agents</strong> entry also AUTO-RUNS the wishlist auction (cron tick, ~5 min granularity; snapshot saved first, once per GW). Each GW's <strong>🔒 Lineup lock</strong> (when squads freeze) is editable here too — blank reverts to the fixture clock.
          </div>
        </div>
        {msg && <span style={{ fontSize: 12, fontWeight: 700, color: msg.startsWith("Failed") ? "#ff9a9a" : "var(--green-400, #5dCAA5)" }}>{msg}</span>}
      </div>

      <div style={{ padding: "0 20px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
        {rows.length === 0 && (
          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", padding: "6px 0" }}>No scheduled transitions. Add a gameweek below.</div>
        )}
        {groupKeys.length > 1 && (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <button onClick={() => setGwCursor(i => Math.max(0, i - 1))} disabled={gwIdx === 0}
              style={{ padding: "6px 14px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.2)", background: "transparent", color: gwIdx === 0 ? "rgba(255,255,255,0.3)" : "white", cursor: gwIdx === 0 ? "default" : "pointer", fontSize: 15, fontWeight: 800 }}>←</button>
            <div style={{ fontSize: 12, fontWeight: 700, color: "rgba(255,255,255,0.75)" }}>
              {curKey === "—" ? "Unassigned" : `Gameweek ${curKey}`} · {gwIdx + 1} of {groupKeys.length}
            </div>
            <button onClick={() => setGwCursor(i => Math.min(groupKeys.length - 1, i + 1))} disabled={gwIdx === groupKeys.length - 1}
              style={{ padding: "6px 14px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.2)", background: "transparent", color: gwIdx === groupKeys.length - 1 ? "rgba(255,255,255,0.3)" : "white", cursor: gwIdx === groupKeys.length - 1 ? "default" : "pointer", fontSize: 15, fontWeight: 800 }}>→</button>
          </div>
        )}
        {[curKey].filter(Boolean).map(key => {
          const items = groups[key].slice().sort((a, b) => (a.r.local || "").localeCompare(b.r.local || ""));
          const dated = items.filter(x => x.r.local);
          return (
            <div key={key} style={{ border: "1px solid rgba(255,255,255,0.12)", borderRadius: 10, padding: "10px 12px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, gap: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 800, color: "white" }}>{key === "—" ? "Unassigned" : `Gameweek ${key}`}</div>
                <button onClick={() => addRowForGw(key === "—" ? null : Number(key))} disabled={saving}
                  style={{ padding: "5px 10px", borderRadius: 7, border: "1px dashed rgba(255,255,255,0.3)", background: "transparent", color: "white", cursor: "pointer", fontSize: 11, fontWeight: 700 }}>+ Add transition</button>
              </div>
              {items.map(({ r, i }) => (
                <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
                  <select value={r.phase} onChange={e => setRow(i, { phase: e.target.value })}
                    style={{ ...inputStyle, fontWeight: 700 }}>
                    {PHASES.map(([v, l]) => <option key={v} value={v} style={{ color: "black" }}>{l}</option>)}
                  </select>
                  <span style={{ color: "rgba(255,255,255,0.6)", fontSize: 12 }}>at</span>
                  <input type="datetime-local" value={r.local} onChange={e => setRow(i, { local: e.target.value })} style={inputStyle} />
                  <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 11, fontWeight: 700 }}>IL</span>
                  <button onClick={() => removeRow(i)} title="Remove"
                    style={{ marginLeft: "auto", padding: "6px 10px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.2)", background: "transparent", color: "rgba(255,255,255,0.8)", cursor: "pointer", fontSize: 12 }}>✕</button>
                </div>
              ))}
              {key !== "—" && (
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 8, paddingTop: 8, borderTop: "1px dashed rgba(255,255,255,0.12)" }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "rgba(255,255,255,0.85)" }}>🔒 Lineup lock</span>
                  <span style={{ color: "rgba(255,255,255,0.6)", fontSize: 12 }}>at</span>
                  <input type="datetime-local" value={locks[key] || ""} onChange={e => setLock(key, e.target.value)} style={inputStyle} />
                  <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 11, fontWeight: 700 }}>IL</span>
                  {locks[key]
                    ? <button onClick={() => setLock(key, "")} title="Clear this GW's lock override (revert to fixture clock)"
                        style={{ marginLeft: "auto", padding: "6px 10px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.2)", background: "transparent", color: "rgba(255,255,255,0.8)", cursor: "pointer", fontSize: 11 }}>Clear lock</button>
                    : <span style={{ marginLeft: "auto", fontSize: 10, color: "rgba(255,255,255,0.4)" }}>no override · fixture clock</span>}
                </div>
              )}
              {dated.length > 0 && (
                <div style={{ marginTop: 4, fontSize: 11, color: "rgba(255,255,255,0.6)" }}>
                  {dated.map((x, k) => {
                    const lbl = (PHASES.find(p => p[0] === x.r.phase) || [null, x.r.phase])[1];
                    return <span key={k}>{k ? " → " : ""}<strong style={{ color: "white" }}>{lbl}</strong> {x.r.local.replace("T", " ")}</span>;
                  })}
                </div>
              )}
            </div>
          );
        })}

        <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
          <button onClick={addGameweek} disabled={saving}
            style={{ padding: "8px 14px", borderRadius: 8, border: "1px dashed rgba(255,255,255,0.3)", background: "transparent", color: "white", cursor: "pointer", fontSize: 12, fontWeight: 700 }}>+ Add gameweek</button>
          <button onClick={save} disabled={saving || rows.length === 0}
            style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "var(--green-500)", color: "var(--navy-900)", cursor: (saving || rows.length === 0) ? "default" : "pointer", fontSize: 12, fontWeight: 800, opacity: (saving || rows.length === 0) ? 0.6 : 1 }}>
            {saving ? "Saving…" : "Save schedule"}</button>
          <button onClick={clearAll} disabled={saving}
            style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.2)", background: "transparent", color: "rgba(255,255,255,0.8)", cursor: "pointer", fontSize: 12, fontWeight: 700 }}>Clear all</button>
        </div>
      </div>
    </div>
  );
}

function TransfersScreen() {
  const [tab, setTab] = React.useState("free");
  const [runningMock, setRunningMock] = React.useState(false);
  const [auctionViz, setAuctionViz] = React.useState(null);  // {gw, executed, skipped}
  const [switching, setSwitching] = React.useState(false);
  const [toast, setToast] = React.useState(null);

  React.useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const activeWindow = window.WINDOW || WINDOW;
  const me = managerById(window.ME) || { name: "Manager", team: "My Team", flag: "GER", waiverPri: 99 };
  const isMock = !!(window.LEAGUE && window.LEAGUE.simulated);
  // Window switching + the wishlist runner are LEAGUE-ADMIN powers (Ilay).
  // Everyone still SEES the buttons (current window highlighted) but they are
  // greyed/disabled for non-admins. Server-side gates match.
  const amLeagueAdmin = !!(window.LEAGUE && window.LEAGUE.admin && window.LEAGUE.admin === window.ME);
  // Window control (phase switch + timed schedule) is Ilay-only. Backend matches.
  const amSuperAdmin = !!window.IS_SUPER_ADMIN;
  const curPhase = (window.WINDOW && window.WINDOW.phase) || "none";
  const overridden = !!(window.WINDOW && window.WINDOW.overridden);

  // MOCK: flip the league's transfer-window phase so the page renders that
  // window. Trade = manager trades + wishlist; Free agents = instant pickups +
  // wishlist; Gameweek = wishlist only (no manager trades, picks go to wishlist);
  // Auto = clear the override and hand control back to the fixture clock.
  const switchWindow = async (phase) => {
    if (switching) return;
    if (phase === "auto" ? !overridden : phase === curPhase) return;
    // Entering Free agents AUTO-RUNS the wishlist auction on real leagues
    // (server-side, once per GW, snapshot saved first) — make that explicit.
    if (phase === "free_agents" && !isMock &&
        !window.confirm("Opening the Free agents window AUTO-RUNS the wishlist auction on everyone's pending bids (once per GW; a bid+squad snapshot is saved first).\n\nContinue?")) return;
    setSwitching(true);
    try {
      const lid = window.LEAGUE.id;
      const gw = (window.WINDOW && window.WINDOW.gw) || (window.TOURNAMENT && window.TOURNAMENT.currentGw);
      // "auto" sends no gw — same call shape the old Status-screen admin
      // switcher used to clear the override.
      const res = await apiCall("POST", `/leagues/${lid}/admin/window-override`, phase === "auto" ? { phase } : { phase, gw });
      const ar = res && res.wishlistAutoRun;
      if (ar && (ar.status === "done" || ar.status === "blocked" || ar.status === "failed")) {
        setToast({
          type: ar.status === "done" ? "success" : "error",
          message: ar.status === "done"
            ? `Wishlist auction ran for GW${ar.gw}: ${ar.claims} claim${ar.claims === 1 ? "" : "s"} (snapshot saved).`
            : `Window switched, but the wishlist auto-run was ${ar.status}: ${ar.reason || ar.error || "see wishlist_runs"}`,
        });
        setTimeout(() => window.location.reload(), 2600);
      } else {
        window.location.reload();
      }
    } catch (err) {
      setToast({
        type: "error",
        message: "Failed to switch window: " + (err.error || err.detail || JSON.stringify(err))
      });
      setSwitching(false);
    }
  };

  // REAL wishlist auction on the managers' actual bids (NO auto-filled mock
  // bids). Idempotent server-side: a second run is refused (409) until the GW
  // is rolled back — so a stray double-click can't re-run it.
  const runWishlistAuction = async () => {
    if (runningMock) return;
    const gw = (window.WINDOW && window.WINDOW.gw) || (window.TOURNAMENT && window.TOURNAMENT.currentGw);
    if (!window.confirm(`Run the wishlist auction for GW${gw} on the managers' REAL bids?\n\nThis resolves all bids by waiver priority and updates squads. It can only run once per GW (roll back first to re-run).`)) return;
    setRunningMock(true);
    try {
      const lid = window.LEAGUE.id;
      const res = await apiCall("POST", `/admin/leagues/${lid}/process-wishlist-auction/${gw}`, {});
      setAuctionViz({ gw: res.gw, executed: res.executed || [], failed: res.failed || [], events: res.events || [] });
    } catch (err) {
      const already = (err && (err.status === 409)) || /ALREADY_RESOLVED/.test(JSON.stringify(err || ""));
      setToast({
        type: "error",
        message: already
          ? `GW${gw} already resolved — roll it back before re-running.`
          : "Failed to run wishlist: " + (err.error || err.detail || JSON.stringify(err))
      });
      setRunningMock(false);
    }
  };

  // Ilay-only: undo a GW's wishlist auction (reverse swaps, reopen bids, clear
  // the result) so it can be cleanly re-run.
  const rollbackWishlist = async () => {
    if (runningMock) return;
    const gw = (window.WINDOW && window.WINDOW.gw) || (window.TOURNAMENT && window.TOURNAMENT.currentGw);
    if (!window.confirm(`Roll back the GW${gw} wishlist auction?\n\nReverses every claim (squads return to pre-auction), reopens all bids, and clears the result. Use this to fix a bad run, then re-run.`)) return;
    setRunningMock(true);
    try {
      const lid = window.LEAGUE.id;
      const res = await apiCall("POST", `/admin/leagues/${lid}/rollback-wishlist/${gw}`, {});
      setToast({ type: "success", message: `Rolled back GW${gw}: ${res.reversedSwaps} swaps reversed, ${res.bidDocsReopened} bid lists reopened.` });
      setTimeout(() => window.location.reload(), 1200);
    } catch (err) {
      setToast({ type: "error", message: "Rollback failed: " + (err.error || err.detail || JSON.stringify(err)) });
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
              {amSuperAdmin && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <button className="btn" disabled={runningMock} onClick={runWishlistAuction}
                    title="Resolve the wishlist auction on the managers' REAL bids (once per GW)"
                    style={{ padding: "12px 16px", fontSize: 13, fontWeight: 800, borderRadius: 10, whiteSpace: "nowrap",
                      background: runningMock ? "rgba(255,255,255,0.25)" : "var(--gold-500)",
                      color: runningMock ? "rgba(255,255,255,0.55)" : "var(--navy-900)",
                      border: "none", cursor: runningMock ? "default" : "pointer" }}>
                    {runningMock ? "Working…" : "▶ Run wishlist"}
                  </button>
                  <button className="btn" disabled={runningMock} onClick={rollbackWishlist}
                    title="Undo this GW's wishlist auction so it can be re-run"
                    style={{ padding: "6px 10px", fontSize: 11, fontWeight: 700, borderRadius: 8, whiteSpace: "nowrap",
                      background: "transparent", color: "rgba(255,255,255,0.8)",
                      border: "1px solid rgba(255,255,255,0.25)", cursor: runningMock ? "default" : "pointer" }}>
                    ↺ Roll back wishlist
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
        <div style={{ padding: "10px 24px 14px", borderTop: "1px solid var(--border-dark)" }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "rgba(255,255,255,0.55)", marginBottom: 8 }}>
            {amSuperAdmin ? "Switch window (Ilay)" : "Current window"}
          </div>
          <div className="transfers-window-switch" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[
              ["auto", "Auto", "fixture clock decides"],
              ["trade", "Trade", "manager trades + wishlist"],
              ["free_agents", "Free agents", "instant pickups + wishlist"],
              ["next_gw_bid", "Gameweek", "wishlist only · no trades"],
            ].map(([key, label, hint]) => {
              const active = key === "auto" ? !overridden : curPhase === key;
              const locked = switching || !amSuperAdmin;
              return (
                <button key={key} disabled={locked} onClick={() => switchWindow(key)}
                  title={amSuperAdmin ? hint : "Only Ilay can switch windows"}
                  style={{ padding: "8px 14px", fontSize: 12, fontWeight: 700, borderRadius: 8,
                    cursor: locked ? "default" : "pointer",
                    background: active ? "var(--green-500)" : "rgba(255,255,255,0.10)",
                    color: active ? "var(--navy-900)" : (amSuperAdmin ? "white" : "rgba(255,255,255,0.45)"),
                    opacity: (!amSuperAdmin && !active) ? 0.55 : 1,
                    border: "1px solid " + (active ? "var(--green-500)" : "rgba(255,255,255,0.20)") }}>
                  {label}
                  <span style={{ display: "block", fontSize: 10, fontWeight: 600, opacity: 0.8 }}>{hint}</span>
                </button>
              );
            })}
          </div>
        </div>
        {/* Ilay-only: a blocked/failed wishlist auto-run must not go unnoticed —
            the cron tick retries, but the CAUSE (unfinalized GW, failed lease)
            needs a human. Written by the server on every auto-run attempt. */}
        {amSuperAdmin && activeWindow.wishlistAutoRun &&
          (activeWindow.wishlistAutoRun.status === "blocked" || activeWindow.wishlistAutoRun.status === "failed") && (
          <div style={{ padding: "10px 24px", borderTop: "1px solid var(--border-dark)",
            background: "rgba(255,90,110,0.10)", fontSize: 12, fontWeight: 700, color: "#ff9aa3" }}>
            ⚠ Wishlist auto-run {activeWindow.wishlistAutoRun.status}
            {activeWindow.wishlistAutoRun.gw ? ` (GW${activeWindow.wishlistAutoRun.gw})` : ""}:{" "}
            {activeWindow.wishlistAutoRun.reason || activeWindow.wishlistAutoRun.error || "see wishlist_runs"}
          </div>
        )}
      </div>

      {/* Ilay-only: schedule timed window transitions (e.g. Free agents @ 16:00,
          Gameweek @ 18:00 Israel). Self-gates on IS_SUPER_ADMIN. */}
      <WindowScheduleAdmin />

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

      {tab === "free" && <FreeAgentsTab setToast={setToast} />}
      {tab === "wishlist" && <WishlistTab setToast={setToast} />}
      {tab === "squad" && <MySquadTab />}
      {tab === "history" && <TransferHistoryTab />}

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
  ["sixtyPlusGames", "60+ min games"],
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
  sixtyPlusGames:["60+ Gms", p => (p.season && p.season.sixtyPlusGames) || 0],
  defconActions: ["DefCon", p => (p.season && p.season.defconActions) || 0],
  dr:            ["Draft",  p => `#${p.dr || "—"}`],
};

// Side-by-side season-stat + upcoming-fixture comparison for the swap modal:
// the player coming IN vs the squad player going OUT. Reuses the global compare
// helpers (cmpVal, upcomingFixturesFor) and team widgets so this stays in lock-
// step with the player-stats-modal Compare tab. Stats come straight off
// p.season (no fetch) so it renders instantly when a drop is picked.
function PickupCompare({ incoming, outgoing }) {
  if (!incoming || !outgoing) return null;
  const tIn = teamById(incoming.team), tOut = teamById(outgoing.team);
  const win = "var(--green-600, #1a9d5a)";

  const metrics = [
    ["Minutes", "minutes"],
    ["Goals", "goals"],
    ["Assists", "assists"],
    ["Shots on target", "shotsOnTarget"],
    ["Clean sheets", "cleanSheets"],
    ["DefCon actions", "defconActions"],
    ["Total points", "pts"],
  ];

  // Real upcoming fixtures only (known group opponents) — TBD knockout rows are
  // dropped. This list shrinks naturally as GWs are played (2 now → 1 in GW2).
  const realFx = pl => upcomingFixturesFor(pl, teamById(pl.team), null)
    .filter(f => f.gw !== "—" && f.opp && f.opp !== "TBD");

  const FdrBadge = ({ d }) => {
    const c = d >= 5 ? "var(--red-500)" : d >= 4 ? "var(--hot-500)" : d >= 3 ? "var(--gold-500)" : "var(--green-500)";
    return <span style={{ display: "inline-block", minWidth: 18, textAlign: "center", padding: "1px 6px", borderRadius: 4, fontSize: 10, fontWeight: 700, background: c + "22", color: c }}>{d}</span>;
  };

  const FxCol = ({ pl, fx, align }) => (
    <div style={{ flex: 1, background: "white", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
      <div style={{ background: "var(--cream)", padding: "5px 10px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-500)", textAlign: align }}>
        {pl.name.split(" ").slice(-1)[0]} · next
      </div>
      {fx.length === 0 ? (
        <div className="muted" style={{ padding: "8px 10px", fontSize: 11, textAlign: "center" }}>No upcoming fixtures</div>
      ) : fx.map((f, i) => {
        const ot = teamById(f.opp);
        return (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, padding: "6px 10px", borderTop: "1px solid var(--border)", fontSize: 12 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 5, minWidth: 0 }}>
              <span className="muted" style={{ fontSize: 10, fontWeight: 700 }}>GW{f.gw}</span>
              {ot ? <Flag team={ot} /> : null}
              <span style={{ fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{(ot && ot.name) || f.opp}</span>
            </span>
            <FdrBadge d={f.diff} />
          </div>
        );
      })}
    </div>
  );

  return (
    <div style={{ background: "var(--cream)", borderRadius: 10, padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.05em", color: "var(--ink-500)", textTransform: "uppercase", textAlign: "center" }}>
        Stat comparison · this season
      </div>

      {/* Heads — IN on the left, OUT on the right */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 30, height: 30, flexShrink: 0 }}><Jersey team={tIn} pos={incoming.pos} /></div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 12, color: "var(--navy-900)", lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{incoming.name}</div>
            <div style={{ fontSize: 9, fontWeight: 700, color: "#006b35", letterSpacing: "0.05em" }}>IN</div>
          </div>
        </div>
        <div style={{ fontWeight: 800, color: "var(--ink-500)", fontSize: 11 }}>vs</div>
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
          <div style={{ minWidth: 0, textAlign: "right" }}>
            <div style={{ fontWeight: 800, fontSize: 12, color: "var(--navy-900)", lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{outgoing.name}</div>
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--red-500)", letterSpacing: "0.05em" }}>OUT</div>
          </div>
          <div style={{ width: 30, height: 30, flexShrink: 0 }}><Jersey team={tOut} pos={outgoing.pos} /></div>
        </div>
      </div>

      {/* Metric rows — the better value is greener/bolder */}
      <div style={{ background: "white", borderRadius: 8, overflow: "hidden", border: "1px solid var(--border)" }}>
        {metrics.map(([label, key], i) => {
          const av = cmpVal(incoming, key), bv = cmpVal(outgoing, key);
          const aWin = av > bv, bWin = bv > av;
          return (
            <div key={key} style={{ display: "flex", alignItems: "center", borderTop: i ? "1px solid var(--border)" : "none" }}>
              <div className="num" style={{ flex: 1, textAlign: "center", padding: "7px 8px", fontWeight: aWin ? 800 : 600, color: aWin ? win : "var(--ink-700)" }}>{av}</div>
              <div style={{ width: 120, textAlign: "center", fontSize: 10, color: "var(--ink-500)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</div>
              <div className="num" style={{ flex: 1, textAlign: "center", padding: "7px 8px", fontWeight: bWin ? 800 : 600, color: bWin ? win : "var(--ink-700)" }}>{bv}</div>
            </div>
          );
        })}
      </div>

      {/* Upcoming fixtures, side by side */}
      <div style={{ display: "flex", gap: 8 }}>
        <FxCol pl={incoming} fx={realFx(incoming)} align="left" />
        <FxCol pl={outgoing} fx={realFx(outgoing)} align="right" />
      </div>

      <div className="muted" style={{ fontSize: 10, textAlign: "center" }}>
        Greener / bolder = the better value. FDR 1 easy → 5 hard.
      </div>
    </div>
  );
}

function FreeAgentsTab({ setToast }) {
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

  // The "Next" column shows each player's opponent in the GW you're transferring
  // FOR — the next editable round (GW3 while GW2 is live), NOT the current/viewed
  // GW. Resolve it from the same backend endpoint Pick Team uses ("Save Lineup
  // for GWX"), then load that round's per-team fixtures into WC_FIXTURES_BY_GW.
  // Until it resolves (or if that round isn't scheduled) the column stays blank.
  const [nextGw, setNextGw] = React.useState(null);
  const [, setFixturesLoaded] = React.useState(0);
  // Knockout bracket (national teams) — used to optionally hide free agents whose
  // nation is already OUT of the tournament. Same doc the Fixtures bracket renders.
  const [wcBracket, setWcBracket] = React.useState(null);
  // "In tournament" defaults ON — knocked-out players are what everyone is
  // trying to get RID of; no reason to offer them back (toggle stays for the
  // rare deliberate look). "Played minutes" is opt-in: hides the deep bench
  // (0 minutes so far) that realistically no manager would pick.
  const [activeOnly, setActiveOnly] = React.useState(true);
  const [minutesOnly, setMinutesOnly] = React.useState(false);
  React.useEffect(() => {
    let cancelled = false;
    apiCall("GET", "/wc-bracket")
      .then(d => { if (!cancelled) setWcBracket(d || {}); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);
  // Teams still alive = reached the knockouts (have a Round-of-32 tie) AND have
  // not lost a completed knockout match. A nation with NO R32 tie (group-stage
  // exit, e.g. Iran / New Zealand) is out; a nation whose R32 tie hasn't been
  // played yet stays in (we only drop CONFIRMED exits — losers of a finished
  // match or teams that never qualified).
  const { aliveReady, isNationAlive, eliminatedCount } = (() => {
    const rounds = (wcBracket && wcBracket.rounds) || {};
    const knockout = new Set(), eliminated = new Set();
    (rounds["Round of 32"] || []).forEach(m => {
      if (m.home) knockout.add(m.home);
      if (m.away) knockout.add(m.away);
    });
    Object.values(rounds).forEach(ms => (ms || []).forEach(m => {
      if (m.status === "FT" && m.winner) {
        if (m.home && m.home !== m.winner) eliminated.add(m.home);
        if (m.away && m.away !== m.winner) eliminated.add(m.away);
      }
    }));
    const ready = knockout.size > 0;
    const alive = iso => !ready ? true : (knockout.has(iso) && !eliminated.has(iso));
    return { aliveReady: ready, isNationAlive: alive,
             // how many of the current pool's nations are out (display hint)
             eliminatedCount: ready
               ? [...new Set((window.PLAYERS || []).map(p => (p.team || "").toUpperCase()))].filter(t => t && !alive(t)).length
               : 0 };
  })();
  React.useEffect(() => {
    const lid = window.LEAGUE && window.LEAGUE.id;
    if (!lid) return;
    let cancelled = false;
    (async () => {
      let gw = null;
      try {
        const eg = await apiCall("GET", `/leagues/${lid}/edit-gw`);
        gw = (eg && eg.editGw) || null;
      } catch (e) {
        console.warn("FreeAgents: edit-gw resolve failed", e);
      }
      if (!gw) gw = (window.TOURNAMENT && window.TOURNAMENT.currentGw) || null;
      if (cancelled || !gw) return;
      setNextGw(gw);
      try {
        if (typeof window.fetchFixturesByTeamForGw === "function" &&
            !(window.WC_FIXTURES_BY_GW && window.WC_FIXTURES_BY_GW[gw])) {
          await window.fetchFixturesByTeamForGw(gw);
        }
        if (!cancelled) setFixturesLoaded(gw);
      } catch (e) {
        console.warn(`FreeAgents: fixtures fetch failed for GW${gw}`, e);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // playerId -> owning manager's name. Computed EVERY render (not useMemo[]) so it
  // reflects window.SQUADS_BY_UID as soon as the per-manager squads finish loading —
  // a memo captured on mount could be empty if Transfers opens before that async
  // load resolves, which made every owned player look like a free agent.
  const ownerByPid = {};
  const ownerUidByPid = {};
  {
    const sbu = window.SQUADS_BY_UID || {}, mgrs = window.MANAGERS || [];
    const nameOf = uid => { const m = mgrs.find(x => x.uid === uid); return m ? (m.team || m.name || uid) : uid; };
    Object.entries(sbu).forEach(([uid, ids]) => (ids || []).forEach(pid => {
      ownerByPid[String(pid)] = nameOf(uid);
      ownerUidByPid[String(pid)] = uid;
    }));
  }
  const ownerNames = [...new Set(Object.values(ownerByPid))].sort();

  // Manager↔manager trades/bids are allowed in the TRADE and gameweek
  // (NEXT_GW_BID) windows. When open, a player owned by ANOTHER manager shows a
  // "Trade" button that jumps to the Trades tab with a proposal pre-seeded
  // (their squad selected, that player already ticked as the one you receive).
  const tradePhase = (window.WINDOW && window.WINDOW.phase) || "none";
  const canTrade = tradePhase === "trade" || tradePhase === "next_gw_bid";

  // Derive BOTH views from the full pool (window.PLAYERS), which carries club +
  // real points. "All players" = the whole pool (owned shown with their manager,
  // not pickable); "Free agents" = players not owned by any manager. We don't use
  // the /free-agents endpoint here — it returns a projected, 50-capped subset with
  // no club/points.
  const source = (window.PLAYERS || []).filter(p => mode === "all" || !ownerByPid[String(p.id)]);
  // When "In tournament" is on, the nations dropdown lists ONLY nations still
  // alive in the WC — eliminated teams drop out of the picker, not just the rows.
  const nationPool = activeOnly ? source.filter(p => isNationAlive((p.team || "").toUpperCase())) : source;
  const nations = [...new Set(nationPool.map(p => p.teamName).filter(Boolean))].sort();
  // If the currently-selected nation just left the list (e.g. eliminated while
  // In-tournament is on), fall back to "all" so the table never goes blank.
  const effNation = nations.includes(nationFilter) ? nationFilter : "all";
  const q = search.trim().toLowerCase();
  const filtered = source
    .filter(p => posFilter === "all" || p.pos === Number(posFilter))
    .filter(p => effNation === "all" || p.teamName === effNation)
    .filter(p => {
      if (ownerFilter === "all") return true;
      const o = ownerByPid[String(p.id)];
      return ownerFilter === "__free" ? !o : o === ownerFilter;
    })
    .filter(p => !q || (p.name || "").toLowerCase().includes(q) || (p.club || "").toLowerCase().includes(q))
    // Optional: drop players whose nation is already out of the tournament.
    .filter(p => !activeOnly || isNationAlive((p.team || "").toUpperCase()))
    // Free-agent rows carry `min` (from /free-agents); all-players rows carry
    // season.minutes — read whichever exists so the filter works in both modes.
    .filter(p => !minutesOnly || ((p.min != null ? p.min : (p.season && p.season.minutes) || 0) > 0))
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
  // First UNRESOLVED gw (computed at bootstrap) — bids never target a GW whose
  // auction already ran. Falls back to the window/current GW pre-bootstrap.
  const bidGw = window.WISHLIST_BID_GW ||
                (window.WINDOW && window.WINDOW.gw) ||
                (window.TOURNAMENT && window.TOURNAMENT.currentGw);
  const _pid = (v) => (isNaN(Number(v)) ? Number(String(v).replace("p_", "")) : Number(v));

  const handlePickup = async (p) => {
    if (!playerToDrop) {
      setToast({ type: "error", message: "Please select a player to drop." });
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
      setToast({
        type: "success",
        message: `Successfully picked up ${p.name} and dropped ${window.PLAYER_MAP[playerToDrop]?.name || playerToDrop}!`
      });
      setActivePickup(null);
      setTimeout(() => window.location.reload(), 1500);
    } catch (err) {
      setToast({
        type: "error",
        message: "Failed to pick up player: " + (err.error || err.detail || JSON.stringify(err))
      });
    }
  };

  // Window closed → add this free agent to the bid-wishlist (same in/out swap
  // the pickup would do), appending to the manager's ordered bids for bidGw.
  const handleAddWishlist = async (p) => {
    if (!playerToDrop) { setToast({ type: "error", message: "Please select a player to drop." }); return; }
    if (!bidGw) { setToast({ type: "error", message: "No upcoming gameweek to bid for yet." }); return; }
    const pIn = _pid(p.id), pOut = _pid(playerToDrop);
    const existing = (window.MY_WISHLIST_BIDS || []).map(b => ({
      playerIn: Number(b.playerIn), playerOut: Number(b.playerOut), position: b.position,
    }));
    // Allow the same incoming player with a DIFFERENT player out (ordered
    // fallbacks); only block an exact duplicate of the (in, out) pair.
    if (existing.some(b => b.playerIn === pIn && b.playerOut === pOut)) {
      setToast({
        type: "error",
        message: `That exact swap (${p.name} in / ${window.PLAYER_MAP[String(playerToDrop)]?.name || "player"} out) is already on your wishlist.`
      });
      setActivePickup(null);
      return;
    }
    try {
      const lid = window.LEAGUE.id;
      const cp = window.PLAYER_MAP[String(p.id)];
      const next = [...existing, { playerIn: pIn, playerOut: pOut, position: cp ? POS_NAMES[cp.pos] : "?" }];
      const res = await apiCall("POST", `/leagues/${lid}/wishlist-bids`, { gw: bidGw, bids: next });
      window.MY_WISHLIST_BIDS = (res && Array.isArray(res.bids)) ? res.bids : next;
      setToast({
        type: "success",
        message: `Added ${p.name} to your wishlist (GW${bidGw}). It'll be claimed by the auction when the free-agents window opens.`
      });
      setActivePickup(null);
    } catch (err) {
      setToast({
        type: "error",
        message: "Failed to add to wishlist: " + (err.error || err.detail || JSON.stringify(err))
      });
    }
  };

  // Add the incoming free agent to an EXISTING batch (same position, not
  // already an IN there) instead of creating a new standalone bid. No drop
  // selection needed — the batch's OUT side already says who leaves. The
  // player joins as the batch's LAST IN priority (reorder in the Wishlist
  // tab). Saves through the batched endpoint so the server round-trips the
  // stored flat list back.
  const handleAddToBatch = async (p, batchIdx) => {
    if (!bidGw) { setToast({ type: "error", message: "No upcoming gameweek to bid for yet." }); return; }
    const pIn = _pid(p.id);
    const flat = (window.MY_WISHLIST_BIDS || []).map(b => ({
      playerIn: Number(b.playerIn), playerOut: Number(b.playerOut), position: b.position,
    }));
    const next = batchBidsJs(flat).map(b => ({ position: b.position, outs: b.outs.slice(), ins: b.ins.slice() }));
    if (!next[batchIdx]) return;
    next[batchIdx].ins.push(pIn);
    try {
      const lid = window.LEAGUE.id;
      const res = await apiCall("POST", `/leagues/${lid}/wishlist-bids-batched`, { gw: bidGw, batches: next });
      window.MY_WISHLIST_BIDS = (res && Array.isArray(res.bids)) ? res.bids : unbatchBids(next);
      setToast({
        type: "success",
        message: `Added ${p.name} to batch #${batchIdx + 1} (GW${bidGw}) as its last IN priority.`
      });
      setActivePickup(null);
    } catch (err) {
      setToast({
        type: "error",
        message: "Failed to add to batch: " + (err.error || err.detail || JSON.stringify(err))
      });
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
          <select value={effNation} onChange={e => setNationFilter(e.target.value)} style={selStyle}>
            <option value="all">All nations{activeOnly && aliveReady ? ` (${nations.length} active)` : ""}</option>
            {nations.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          <select value={sortBy} onChange={e => { setSortBy(e.target.value); setSortDir(defaultDirFor(e.target.value)); }} style={selStyle} title="Sort players by (or click a column header)">
            {FA_SORT_OPTIONS.map(([k, label]) => <option key={k} value={k}>Sort: {label}</option>)}
          </select>
          {aliveReady && (
            <button onClick={() => setActiveOnly(v => !v)}
              title="Hide free agents whose nation is already out of the tournament (group-stage exits and knockout losers). Nations still to play their round are kept."
              className="btn"
              style={{ padding: "7px 12px", fontSize: 12, borderRadius: 8, whiteSpace: "nowrap",
                border: "1px solid " + (activeOnly ? "var(--navy-900)" : "var(--border)"),
                background: activeOnly ? "var(--navy-900)" : "white",
                color: activeOnly ? "white" : "var(--ink-700)" }}>
              {activeOnly ? "✓ " : ""}In tournament{activeOnly && eliminatedCount ? ` · −${eliminatedCount}` : ""}
            </button>
          )}
          <button onClick={() => setMinutesOnly(v => !v)}
            title="Hide players with 0 minutes played so far — the deep bench no manager realistically picks."
            className="btn"
            style={{ padding: "7px 12px", fontSize: 12, borderRadius: 8, whiteSpace: "nowrap",
              border: "1px solid " + (minutesOnly ? "var(--navy-900)" : "var(--border)"),
              background: minutesOnly ? "var(--navy-900)" : "white",
              color: minutesOnly ? "white" : "var(--ink-700)" }}>
            {minutesOnly ? "✓ " : ""}Played minutes
          </button>
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
      <table className="table-clean table-clean--compact table-clean--fa">
        <thead>
          <tr>
            <th>Player</th>
            <th>Team</th>
            <th>Pos</th>
            <th className="fa-owner-col">Owner</th>
            {dynCol && <th onClick={() => applySort(sortBy)} style={{ textAlign: "right", color: "var(--navy-900)", cursor: "pointer", userSelect: "none" }} title="Click to flip sort direction">{dynCol[0]}{sortCaret(sortBy)}</th>}
            <th onClick={() => applySort("pts")} style={{ textAlign: "right", cursor: "pointer", userSelect: "none", color: sortBy === "pts" ? "var(--navy-900)" : undefined }} title="Sort by total points">Pts{sortCaret("pts")}</th>
            <th onClick={() => applySort("selPct")} style={{ textAlign: "right", cursor: "pointer", userSelect: "none", color: sortBy === "selPct" ? "var(--navy-900)" : undefined }} title="Sort by FIFA fantasy ownership %">% Sel{sortCaret("selPct")}</th>
            <th className="c-form" style={{ textAlign: "right" }}>Form</th>
            <th className="c-next" style={{ textAlign: "center" }}>Next</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {shown.length === 0 && (
            <tr className="c-fullrow"><td colSpan={dynCol ? "10" : "9"} style={{ padding: 28, textAlign: "center", color: "var(--ink-500)" }}>No players match your filters.</td></tr>
          )}
          {shown.map(p => {
            const t = teamById(p.team);
            const owner = ownerByPid[String(p.id)];
            const eligibleDrops = mySquad.filter(s => s.pos === p.pos);

            return (
              <tr key={p.id}>
                <td className="c-ident">
                  <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                    <div className="fa-jersey" style={{ width: 36, height: 36, flexShrink: 0 }}><Jersey team={t} pos={p.pos} /></div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 700, whiteSpace: "nowrap", cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted" }}
                        onClick={() => window.dispatchEvent(new CustomEvent("show-player-stats", { detail: { id: p.id } }))}>{p.name}</div>
                      <div className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>{p.club || POS_NAMES[p.pos]}</div>
                    </div>
                  </div>
                </td>
                <td className="c-chip"><span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Flag team={t} /> <span className="c-team-name">{p.teamName || (t && t.name) || p.team}</span></span></td>
                <td className="c-chip"><span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.08)", color: "var(--navy-900)", fontSize: 10 }}>{POS_NAMES[p.pos]}</span></td>
                <td className="c-chip fa-owner-col" data-label="Owner">
                  {owner
                    ? <span style={{ fontSize: 12, fontWeight: 600 }}>{owner}</span>
                    : <span style={{ fontSize: 12, color: "#0a8043", fontWeight: 600 }}>Free agent</span>}
                </td>
                {dynCol && <td className="num c-chip" data-label={dynCol[0]} style={{ textAlign: "right", fontWeight: 800, color: "var(--navy-900)" }}>{dynCol[1](p)}</td>}
                <td className="num c-chip" data-label="Pts" style={{ textAlign: "right", fontWeight: 700 }}>{p.pts}</td>
                <td className="num c-chip" data-label="% Sel" style={{ textAlign: "right", color: p.selPct != null ? "var(--ink-700)" : "var(--ink-300)" }}>
                  {p.selPct != null ? `${Number(p.selPct).toFixed(1)}%` : "—"}
                </td>
                <td className="c-chip c-form" style={{ textAlign: "right" }}>
                  <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700, background: p.pts > 30 ? "rgba(0,217,107,0.18)" : p.pts > 20 ? "rgba(255,200,68,0.18)" : "rgba(0,0,0,0.06)", color: p.pts > 30 ? "#006b35" : p.pts > 20 ? "#7a5a00" : "var(--ink-500)" }}>
                    {p.pts > 30 ? "Hot" : p.pts > 20 ? "Form" : "Cold"}
                  </span>
                </td>
                <td className="c-chip c-next" style={{ textAlign: "center" }}>
                  {(() => {
                    const oppIso = nextGw ? getNextFixtureOpponentIso(p.team, nextGw) : null;
                    const oppT = oppIso ? teamById(oppIso) : null;
                    return oppT
                      ? <span title={`GW${nextGw}: v ${oppT.name || oppIso}`}><Flag team={oppT} /></span>
                      : <span className="c-next-blank" title={nextGw ? `GW${nextGw} fixture not set yet` : "Next fixture not set yet"} />;
                  })()}
                </td>
                <td className="c-action" style={{ textAlign: "right" }}>
                  {owner ? (
                    (() => {
                      const ownerUid = ownerUidByPid[String(p.id)];
                      const tradable = canTrade && ownerUid && ownerUid !== window.ME;
                      return tradable ? (
                        <button className="btn btn--draft" style={{ padding: "6px 14px", fontSize: 11, background: "var(--violet-500)", color: "white" }}
                          title={`Propose a trade with ${owner} for ${p.name}`}
                          onClick={() => window.dispatchEvent(new CustomEvent("wc:open-trade", { detail: { targetUid: ownerUid, receiveId: Number(p.id) } }))}>Trade</button>
                      ) : (
                        <span className="muted" style={{ fontSize: 11 }}>Owned</span>
                      );
                    })()
                  ) : faOpen ? (
                    <button className="btn btn--draft" title="Pick up" style={{ padding: "6px 14px", fontSize: 11 }} onClick={() => { setActivePickup(p); setPlayerToDrop(eligibleDrops[0]?.id || ""); }}><span className="lbl-full">Pick up</span><span className="lbl-short">+</span></button>
                  ) : (
                    <button className="btn btn--draft" title="Add to wishlist" style={{ padding: "6px 14px", fontSize: 11, background: "var(--gold-500)", color: "var(--navy-900)" }} onClick={() => { setActivePickup(p); setPlayerToDrop(eligibleDrops[0]?.id || ""); }}><span className="lbl-full">+ Wishlist</span><span className="lbl-short">+</span></button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>

      {activePickup && (() => {
        const p = activePickup;
        const eligibleDrops = mySquad.filter(s => s.pos === p.pos);
        const tClaim = teamById(p.team);
        return (
          <div className="modal-backdrop" onClick={() => setActivePickup(null)}>
            <div className="modal" style={{ maxWidth: 550, padding: 24, display: "flex", flexDirection: "column", gap: 16 }} onClick={e => e.stopPropagation()}>
              <button className="modal__close" onClick={() => setActivePickup(null)}>×</button>

              <div>
                <h3 className="h-display" style={{ margin: 0, fontSize: 20, color: "var(--navy-900)" }}>
                  {faOpen ? "Pick Up Free Agent" : "Add to Wishlist"}
                </h3>
                <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                  {faOpen 
                    ? `Swap a player from your squad to pick up ${p.name}.`
                    : `Configure a swap to add ${p.name} to your wishlist.`}
                </div>
              </div>

              {/* Free Agent Info (IN) */}
              <div style={{ 
                display: "flex", 
                alignItems: "center", 
                gap: 12, 
                padding: "12px 16px", 
                background: "rgba(0, 217, 107, 0.08)", 
                borderRadius: 8, 
                border: "1px solid rgba(0, 217, 107, 0.25)" 
              }}>
                <div style={{ width: 44, height: 44, flexShrink: 0 }}>
                  <Jersey team={tClaim} pos={p.pos} />
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15, color: "var(--navy-900)" }}>{p.name}</div>
                  <div className="muted" style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
                    <Flag team={tClaim} /> {p.teamName} · <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.08)", color: "var(--navy-900)", fontSize: 9, padding: "2px 6px" }}>{POS_NAMES[p.pos]}</span> · {p.pts} pts
                  </div>
                </div>
                <div style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, color: "#006b35", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  INCOMING
                </div>
              </div>

              {/* Arrow divider */}
              <div style={{ display: "flex", justifyContent: "center", color: "var(--ink-300)", fontSize: 18 }}>
                ⇅
              </div>

              {/* Drop options */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.05em", color: "var(--ink-500)", textTransform: "uppercase", marginBottom: 8 }}>
                  Select squad player to drop (Outgoing)
                </div>

                {eligibleDrops.length === 0 ? (
                  <div className="muted" style={{ padding: 12, border: "1px dashed var(--border)", borderRadius: 8, textAlign: "center", fontSize: 13 }}>
                    No players in your squad share the {POS_NAMES[p.pos]} position.
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {eligibleDrops.map(s => {
                      const tDrop = teamById(s.team);
                      const isSelected = playerToDrop === s.id;
                      const isAlreadyOut = (window.MY_WISHLIST_BIDS || []).some(b => Number(b.playerOut) === Number(s.id));
                      return (
                        <div 
                          key={s.id} 
                          onClick={() => setPlayerToDrop(s.id)}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 12,
                            padding: "10px 14px",
                            border: isSelected ? "2px solid var(--teal-400)" : "1px solid var(--border)",
                            background: isSelected ? "rgba(27, 232, 212, 0.05)" : "white",
                            borderRadius: 8,
                            cursor: "pointer",
                            transition: "all 0.15s ease",
                            boxShadow: isSelected ? "0 4px 12px rgba(27, 232, 212, 0.15)" : "none"
                          }}
                        >
                          <div style={{ width: 32, height: 32, flexShrink: 0 }}>
                            <Jersey team={tDrop} pos={s.pos} />
                          </div>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: 14, color: "var(--navy-900)", display: "flex", alignItems: "center" }}>
                              {s.name}
                              {isAlreadyOut && (
                                <span 
                                  style={{ 
                                    display: "inline-flex", 
                                    alignItems: "center", 
                                    justifyContent: "center", 
                                    width: 16, 
                                    height: 16, 
                                    borderRadius: "50%", 
                                    background: "var(--red-500)", 
                                    color: "white", 
                                    fontSize: 11, 
                                    fontWeight: "bold", 
                                    marginLeft: 8 
                                  }} 
                                  title="Already on your wishlist to be dropped"
                                >
                                  !
                                </span>
                              )}
                            </div>
                            <div className="muted" style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
                              <Flag team={tDrop} /> {s.teamName || s.team} · {s.club} · {s.pts} pts
                            </div>
                          </div>

                          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center" }}>
                            <input 
                              type="radio" 
                              name="playerToDrop" 
                              checked={isSelected} 
                              onChange={() => setPlayerToDrop(s.id)}
                              style={{ cursor: "pointer", accentColor: "var(--teal-400)", width: 16, height: 16 }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Stat + fixture comparison — appears once a drop is chosen */}
              {playerToDrop && (() => {
                const outg = eligibleDrops.find(s => String(s.id) === String(playerToDrop))
                  || window.PLAYER_MAP[String(playerToDrop)];
                return outg ? <PickupCompare incoming={p} outgoing={outg} /> : null;
              })()}

              {/* Shortcut: drop the player straight into one of your existing
                  same-position batches (he joins as its LAST IN priority) —
                  no drop selection needed, the batch's OUT side already says
                  who leaves. Only batches not already listing him qualify. */}
              {(() => {
                const flat = (window.MY_WISHLIST_BIDS || []).map(b => ({
                  playerIn: Number(b.playerIn), playerOut: Number(b.playerOut), position: b.position,
                }));
                const posName = POS_NAMES[p.pos];
                const eligible = batchBidsJs(flat).map((b, i) => ({ b, i }))
                  .filter(({ b }) => b.position === posName && b.ins.indexOf(_pid(p.id)) === -1);
                if (!eligible.length) return null;
                return (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--ink-500)", marginBottom: 6 }}>
                      Or add to an existing batch · no drop pick needed
                    </div>
                    <div className="col" style={{ gap: 6 }}>
                      {eligible.map(({ b, i }) => (
                        <div key={i} onClick={() => handleAddToBatch(p, i)}
                          style={{ display: "flex", alignItems: "center", gap: 8, width: "100%",
                            padding: "8px 12px", borderRadius: 8, border: "1px solid var(--border)",
                            background: "white", cursor: "pointer", fontSize: 12 }}>
                          <strong>Batch #{i + 1}</strong>
                          <span className="pill pill--navy" style={{ fontSize: 9 }}>{b.position}</span>
                          <span className="muted" style={{ fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            out: {b.outs.map(id => (window.PLAYER_MAP[String(id)] || {}).name || id).join(", ")}
                          </span>
                          <span className="muted" style={{ fontSize: 11, marginLeft: "auto", whiteSpace: "nowrap" }}>
                            {b.ins.length} in · joins last
                          </span>
                          <button onClick={(e) => { e.stopPropagation(); handleAddToBatch(p, i); }}
                            style={{ padding: "7px 16px", fontSize: 12, fontWeight: 700, borderRadius: 8,
                              border: "none", background: "var(--navy-900)", color: "white",
                              cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}>
                            Add
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Actions */}
              <div className="pickup-modal__actions" style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 8 }}>
                <button className="btn btn--ghost-dark" style={{ padding: "10px 20px" }} onClick={() => setActivePickup(null)}>
                  Cancel
                </button>
                <button 
                  className="btn btn--primary" 
                  style={{ 
                    padding: "10px 20px",
                    background: "var(--navy-900)",
                    color: "white"
                  }} 
                  disabled={!playerToDrop} 
                  onClick={() => faOpen ? handlePickup(p) : handleAddWishlist(p)}
                >
                  {faOpen ? "Confirm Swap" : "Add to Wishlist"}
                </button>
              </div>

            </div>
          </div>
        );
      })()}
    </div>
  );
}

// ---------- Batched wishlist view ----------
// The FLAT ordered bid list stays the stored source of truth; batches are a
// DERIVED view. These two functions mirror the server's canonical transform
// (fpl_predictor/game/wc_wishlist_batches.py) — expansion is OUT-major (for
// each OUT in order, every IN in order), and grouping only happens when a run
// of bids IS exactly a batch's expansion, so batch→unbatch always returns the
// identical flat list. Every batched save round-trips through the server,
// which re-derives the grouping from what it stored — the client never trusts
// its own mirror for persistence.
const POS_NUM = { GK: 1, DEF: 2, MID: 3, FWD: 4 };

function unbatchBids(batches) {
  const flat = [];
  (batches || []).forEach(b => {
    (b.outs || []).forEach(out => {
      (b.ins || []).forEach(inn => {
        flat.push({ playerIn: Number(inn), playerOut: Number(out), position: b.position });
      });
    });
  });
  return flat;
}

function batchBidsJs(flat) {
  flat = flat || [];
  const batches = [];
  let i = 0;
  const n = flat.length;
  while (i < n) {
    const pos = flat[i].position || "";
    const out1 = Number(flat[i].playerOut);
    const ins = [];
    let j = i;
    while (j < n && (flat[j].position || "") === pos && Number(flat[j].playerOut) === out1
           && ins.indexOf(Number(flat[j].playerIn)) === -1) {
      ins.push(Number(flat[j].playerIn));
      j++;
    }
    const outs = [out1];
    const m = ins.length;
    while (j + m <= n) {
      const nxt = flat.slice(j, j + m);
      const outNext = Number(nxt[0].playerOut);
      if (outs.indexOf(outNext) !== -1) break;
      let ok = true;
      for (let k = 0; k < m; k++) {
        if ((nxt[k].position || "") !== pos || Number(nxt[k].playerOut) !== outNext
            || Number(nxt[k].playerIn) !== ins[k]) { ok = false; break; }
      }
      if (!ok) break;
      outs.push(outNext);
      j += m;
    }
    batches.push({ position: pos, outs: outs, ins: ins });
    i = j;
  }
  return batches;
}

const showPlayerStats = (id) =>
  window.dispatchEvent(new CustomEvent("show-player-stats", { detail: { id: String(id) } }));

// Shared "is this nation still in the tournament" resolver — same rule as the
// Free Agents tab's activeOnly filter (reached the R32 bracket AND not the
// loser of a finished knockout match; before the bracket exists, everyone is
// alive). The bracket doc is fetched once and cached module-wide. Needed
// because the pool's per-player `eliminated` flag is only set for GROUP-stage
// exits, so knocked-out nations' players would otherwise look signable.
let _wcBracketCache = null;
function useNationAlive() {
  const [bracket, setBracket] = React.useState(_wcBracketCache);
  React.useEffect(() => {
    if (_wcBracketCache) return undefined;
    let cancelled = false;
    apiCall("GET", "/wc-bracket")
      .then(d => { _wcBracketCache = d || {}; if (!cancelled) setBracket(_wcBracketCache); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);
  return React.useMemo(() => {
    const rounds = (bracket && bracket.rounds) || {};
    const knockout = new Set(), eliminated = new Set();
    (rounds["Round of 32"] || []).forEach(m => {
      if (m.home) knockout.add(m.home);
      if (m.away) knockout.add(m.away);
    });
    Object.values(rounds).forEach(ms => (ms || []).forEach(m => {
      if (m.status === "FT" && m.winner) {
        if (m.home && m.home !== m.winner) eliminated.add(m.home);
        if (m.away && m.away !== m.winner) eliminated.add(m.away);
      }
    }));
    const ready = knockout.size > 0;
    return (iso) => {
      if (!ready) return true;
      const t = (iso || "").toUpperCase();
      return knockout.has(t) && !eliminated.has(t);
    };
  }, [bracket]);
}

// One player row inside a batch side — a numbered LIST row (not a chip): drag
// handle, rank, flag, clickable name, elimination badge, remove. BOTH reorder
// affordances are always present: drag anywhere the browser supports it, and
// ↑/↓ arrows as the universal fallback (touch, keyboard, narrow windows —
// useIsMobile is width-based, so a squeezed desktop is "mobile" too).
function BatchPlayerRow({ pid, idx, side, onRemove, onMove, canUp, canDown, drag }) {
  const p = window.PLAYER_MAP[String(pid)] || { name: String(pid), team: "", pos: 1, pts: 0 };
  const t = teamById(p.team);
  const isElim = p.elim || (t && t.elim);
  const inSide = side === "ins";
  return (
    <div draggable onDragStart={drag.start} onDragOver={drag.over} onDrop={drag.drop}
      style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", borderRadius: 8,
        background: inSide ? "rgba(0,217,107,0.08)" : "rgba(230,57,70,0.08)",
        border: "1px solid " + (inSide ? "rgba(0,217,107,0.25)" : "rgba(230,57,70,0.20)"),
        cursor: "grab" }}>
      <span style={{ color: "var(--ink-300)", fontSize: 12, fontWeight: 800 }}>⠿</span>
      <span className="mono" style={{ fontSize: 12, fontWeight: 800, width: 16, color: "var(--ink-500)" }}>{idx + 1}</span>
      {t && <Flag team={t} />}
      <span style={{ fontWeight: 700, fontSize: 13, cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
        onClick={() => showPlayerStats(pid)}>{p.name}</span>
      {isElim && <span className="pill pill--red" style={{ fontSize: 9, flexShrink: 0 }}>OUT OF WC</span>}
      <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
        {inSide && <span className="muted" style={{ fontSize: 11, marginRight: 4 }}>{p.pts || 0} pts</span>}
        <button className="btn btn--ghost-dark" disabled={!canUp} style={{ padding: "2px 8px", fontSize: 12 }} onClick={() => onMove(-1)}>↑</button>
        <button className="btn btn--ghost-dark" disabled={!canDown} style={{ padding: "2px 8px", fontSize: 12 }} onClick={() => onMove(1)}>↓</button>
        <button className="btn btn--ghost-dark" title="Remove" style={{ padding: "2px 8px", fontSize: 12, color: "var(--red-500)" }} onClick={onRemove}>✕</button>
      </span>
    </div>
  );
}

// The batched wishlist editor. Renders the DERIVED batches of the current
// flat list + local "draft" batches (new batches still missing an IN side —
// those live only in memory: a batch with an empty side is not persistable,
// and deleting the last player of either side deletes the whole batch).
function BatchedWishlistEditor({ bids, gw, onPersisted, setToast }) {
  const isMobile = useIsMobile();
  const nationAlive = useNationAlive();
  const batches = React.useMemo(() => batchBidsJs(bids), [bids]);
  const [drafts, setDrafts] = React.useState([]);
  const [busy, setBusy] = React.useState(false);
  // {b: batchIdx | "d0", side: "outs"|"ins"|"new"} — which adder popover is open.
  const [adder, setAdder] = React.useState(null);
  const [query, setQuery] = React.useState("");
  const dragRef = React.useRef(null);

  const persist = async (nextBatches) => {
    if (busy) return;
    const expanded = unbatchBids(nextBatches);
    if (expanded.length > 60) {
      setToast({ type: "error", message: `This expands to ${expanded.length} bids — the maximum is 60. Trim a batch.` });
      return;
    }
    setBusy(true);
    try {
      const lid = window.LEAGUE.id;
      const res = await apiCall("POST", `/leagues/${lid}/wishlist-bids-batched`, { gw, batches: nextBatches });
      onPersisted((res && Array.isArray(res.bids)) ? res.bids : expanded);
    } catch (err) {
      setToast({ type: "error", message: "Failed to save: " + (err.error || err.detail || JSON.stringify(err)) });
    } finally {
      setBusy(false);
    }
  };

  const clone = () => batches.map(b => ({ position: b.position, outs: b.outs.slice(), ins: b.ins.slice() }));

  const moveBatch = (i, to) => {
    if (to < 0 || to >= batches.length || to === i) return;
    const next = clone();
    const [b] = next.splice(i, 1);
    next.splice(to, 0, b);
    persist(next);
  };
  const removeBatch = (i) => {
    const next = clone();
    next.splice(i, 1);
    persist(next);
  };
  const moveRow = (bi, side, i, to) => {
    const next = clone();
    const arr = next[bi][side];
    if (to < 0 || to >= arr.length || to === i) return;
    const [pid] = arr.splice(i, 1);
    arr.splice(to, 0, pid);
    persist(next);
  };
  const removeRow = (bi, side, i) => {
    const next = clone();
    next[bi][side].splice(i, 1);
    // A batch can't exist with an empty side — removing the last player on
    // EITHER side removes the whole batch (you can't sign players in without
    // signing players out, and vice versa).
    if (next[bi][side].length === 0) next.splice(bi, 1);
    persist(next);
  };
  const addPid = (bi, side, pid) => {
    setAdder(null); setQuery("");
    const next = clone();
    next[bi][side].push(Number(pid));
    persist(next);
  };

  // Draft (unsaved new batch) handling — local state only until both sides
  // have a player, then it persists as a real batch and leaves the drafts.
  const startDraft = (p) => {
    setAdder(null); setQuery("");
    setDrafts(ds => [...ds, { position: POS_NAMES[p.pos], outs: [Number(p.id)], ins: [] }]);
  };
  const draftAdd = (di, side, pid) => {
    setAdder(null); setQuery("");
    const d = drafts[di];
    const nd = { position: d.position, outs: d.outs.slice(), ins: d.ins.slice() };
    nd[side].push(Number(pid));
    if (nd.outs.length && nd.ins.length) {
      setDrafts(ds => ds.filter((_, k) => k !== di));
      persist([...clone(), nd]);
    } else {
      setDrafts(ds => ds.map((x, k) => k === di ? nd : x));
    }
  };
  const draftRemove = (di, side, i) => {
    const d = drafts[di];
    const nd = { position: d.position, outs: d.outs.slice(), ins: d.ins.slice() };
    nd[side].splice(i, 1);
    setDrafts(ds => (nd.outs.length || nd.ins.length)
      ? ds.map((x, k) => k === di ? nd : x)
      : ds.filter((_, k) => k !== di));
  };
  const draftMove = (di, side, i, to) => {
    const d = drafts[di];
    const arr = d[side];
    if (to < 0 || to >= arr.length || to === i) return;
    const nd = { position: d.position, outs: d.outs.slice(), ins: d.ins.slice() };
    const [pid] = nd[side].splice(i, 1);
    nd[side].splice(to, 0, pid);
    setDrafts(ds => ds.map((x, k) => k === di ? nd : x));
  };

  // Drag plumbing: batches drag among batches; rows drag within their own
  // batch + side. dataTransfer stays empty — dragRef carries the source.
  // Row handlers MUST stopPropagation: the batch card is itself draggable,
  // so without it a row's dragstart bubbles up and the card handler
  // overwrites the source as kind:"batch" — the row's own dragover then
  // never matches and the drop is refused (the "drag does nothing" bug).
  const rowDrag = (bi, side, i) => ({
    start: (e) => {
      e.stopPropagation();
      dragRef.current = { kind: "row", b: bi, side, i };
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
    },
    over: (e) => {
      const d = dragRef.current;
      if (d && d.kind === "row" && d.b === bi && d.side === side) e.preventDefault();
    },
    drop: (e) => {
      e.preventDefault();
      e.stopPropagation();
      const d = dragRef.current;
      dragRef.current = null;
      if (d && d.kind === "row" && d.b === bi && d.side === side && d.i !== i) moveRow(bi, side, d.i, i);
    },
  });
  const batchDrag = (i) => ({
    onDragStart: (e) => {
      dragRef.current = { kind: "batch", i };
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
    },
    onDragOver: (e) => { const d = dragRef.current; if (d && d.kind === "batch") e.preventDefault(); },
    onDrop: (e) => {
      e.preventDefault();
      const d = dragRef.current;
      dragRef.current = null;
      if (d && d.kind === "batch" && d.i !== i) moveBatch(d.i, i);
    },
  });

  // Adder option lists. OUT side: my squad, same position, not already used
  // in this batch — knocked-out players first (they're who you're clearing).
  // IN side: free agents, same position, name search, best points first.
  const squadOptions = (batch) => {
    const posN = POS_NUM[batch.position];
    return (window.MY_SQUAD_IDS || [])
      .map(id => window.PLAYER_MAP[id]).filter(Boolean)
      .filter(p => (!posN || p.pos === posN) && batch.outs.indexOf(Number(p.id)) === -1)
      .sort((a, b) => {
        const ea = (a.elim || (teamById(a.team) || {}).elim) ? 0 : 1;
        const eb = (b.elim || (teamById(b.team) || {}).elim) ? 0 : 1;
        return ea - eb || (a.pts || 0) - (b.pts || 0);
      });
  };
  const faOptions = (batch) => {
    const posN = POS_NUM[batch.position];
    const q = query.trim().toLowerCase();
    // ONLY active nations are signable-worthy — the whole point of the
    // wishlist is replacing knocked-out players, so suggesting more of them
    // is noise. Search spans the FULL free-agent pool (the bootstrap no
    // longer truncates at 50); a blank query surfaces the best available by
    // points, then minutes played.
    return (window.FREE_AGENTS || [])
      .filter(p => p.pos === posN && batch.ins.indexOf(Number(p.id)) === -1)
      .filter(p => nationAlive(p.team))
      .filter(p => !q || (p.name || "").toLowerCase().includes(q))
      .sort((a, b) => (b.pts || 0) - (a.pts || 0) || (b.min || 0) - (a.min || 0))
      .slice(0, 10);
  };

  const adderPopover = (options, onPick, withSearch, placeholder) => (
    <div style={{ position: "relative" }}>
      <div style={{ position: "absolute", zIndex: 6, left: 0, right: 0, marginTop: 4, border: "1px solid var(--border)", borderRadius: 8, background: "white", overflow: "hidden", boxShadow: "0 6px 20px rgba(0,0,0,0.15)" }}>
        {withSearch && (
          <input autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder={placeholder}
            style={{ width: "100%", padding: "8px 12px", border: "none", borderBottom: "1px solid var(--border)", fontSize: 13, outline: "none", boxSizing: "border-box" }} />
        )}
        {options.length === 0 && <div className="muted" style={{ padding: "8px 12px", fontSize: 12 }}>No eligible players.</div>}
        {options.map(p => {
          const t = teamById(p.team);
          const isElim = p.elim || (t && t.elim);
          return (
            <div key={p.id} onClick={() => onPick(p)}
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 12px", cursor: "pointer", fontSize: 13, borderTop: "1px solid var(--border)" }}>
              {t && <Flag team={t} />}
              <strong>{p.name}</strong>
              {isElim && <span className="pill pill--red" style={{ fontSize: 9 }}>OUT OF WC</span>}
              {/* Comparison stats: minutes · DefCon bonus · total points.
                  Free-agent rows carry min/defcon from the API; squad rows
                  (PLAYER_MAP) may not — show what exists. */}
              <span className="muted mono" style={{ marginLeft: "auto", fontSize: 11, whiteSpace: "nowrap" }}>
                {p.min != null ? `${p.min}′ · DC ${p.defcon || 0} · ` : ""}{p.pts || 0} pts
              </span>
            </div>
          );
        })}
        <div onClick={() => { setAdder(null); setQuery(""); }} className="muted"
          style={{ padding: "6px 12px", cursor: "pointer", fontSize: 11, textAlign: "center", borderTop: "1px solid var(--border)" }}>Cancel</div>
      </div>
    </div>
  );

  const addRowBtn = (label, onClick) => (
    <button onClick={onClick} disabled={busy}
      style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "7px 10px", borderRadius: 8, border: "1px dashed var(--ink-300)", background: "transparent", color: "var(--ink-500)", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
      + {label}
    </button>
  );

  const sideCol = (batch, bi, side, isDraft, di) => {
    const arr = batch[side];
    const key = isDraft ? `d${di}` : bi;
    const open = adder && adder.b === key && adder.side === side;
    return (
      <div>
        <div className="muted" style={{ fontSize: 11, fontWeight: 700, marginBottom: 6 }}>
          {side === "outs" ? "Take out · #1 leaves first" : "Take in · #1 claimed first"}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {arr.map((pid, i) => (
            <BatchPlayerRow key={pid} pid={pid} idx={i} side={side}
              canUp={i > 0} canDown={i < arr.length - 1}
              onMove={(dir) => isDraft ? draftMove(di, side, i, i + dir) : moveRow(bi, side, i, i + dir)}
              onRemove={() => isDraft ? draftRemove(di, side, i) : removeRow(bi, side, i)}
              drag={isDraft ? { start: () => {}, over: () => {}, drop: () => {} } : rowDrag(bi, side, i)} />
          ))}
          {addRowBtn(side === "outs" ? `Add from squad (${batch.position})` : `Search free ${batch.position}…`,
            () => { setAdder(open ? null : { b: key, side }); setQuery(""); })}
          {open && (side === "outs"
            ? adderPopover(squadOptions(batch), p => isDraft ? draftAdd(di, "outs", p.id) : addPid(bi, "outs", p.id), false)
            : adderPopover(faOptions(batch), p => isDraft ? draftAdd(di, "ins", p.id) : addPid(bi, "ins", p.id), true, `Type a free ${batch.position}'s name…`))}
        </div>
      </div>
    );
  };

  const batchCard = (batch, bi, isDraft, di) => (
    <div key={isDraft ? `draft-${di}` : `b-${bi}`} className="card"
      draggable={!isDraft} {...(isDraft ? {} : batchDrag(bi))}
      style={{ padding: "12px 16px", opacity: busy ? 0.7 : 1 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        {!isDraft && <span style={{ color: "var(--ink-300)", fontSize: 13, fontWeight: 800, cursor: "grab" }}>⠿</span>}
        <strong style={{ fontSize: 14 }}>{isDraft ? "New batch" : `Batch #${bi + 1}`}</strong>
        <span className="pill pill--navy" style={{ fontSize: 10 }}>{batch.position}</span>
        <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>
          {isDraft
            ? "pick both sides to save"
            : `${batch.outs.length * batch.ins.length} bid${batch.outs.length * batch.ins.length === 1 ? "" : "s"} · up to ${Math.min(batch.outs.length, batch.ins.length)} swap${Math.min(batch.outs.length, batch.ins.length) === 1 ? "" : "s"}`}
        </span>
        {!isDraft && (
          <React.Fragment>
            <button className="btn btn--ghost-dark" disabled={bi === 0} style={{ padding: "2px 8px", fontSize: 12 }} onClick={() => moveBatch(bi, bi - 1)}>↑</button>
            <button className="btn btn--ghost-dark" disabled={bi === batches.length - 1} style={{ padding: "2px 8px", fontSize: 12 }} onClick={() => moveBatch(bi, bi + 1)}>↓</button>
          </React.Fragment>
        )}
        <button className="btn btn--ghost-dark" title="Delete batch" style={{ padding: "2px 8px", fontSize: 12, color: "var(--red-500)" }}
          onClick={() => isDraft ? setDrafts(ds => ds.filter((_, k) => k !== di)) : removeBatch(bi)}>✕</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "minmax(0,1fr) minmax(0,1fr)", gap: 14, alignItems: "start" }}>
        {sideCol(batch, bi, "outs", isDraft, di)}
        {sideCol(batch, bi, "ins", isDraft, di)}
      </div>
    </div>
  );

  const newBatchOpen = adder && adder.b === "new";
  const allSquad = (window.MY_SQUAD_IDS || []).map(id => window.PLAYER_MAP[id]).filter(Boolean)
    .filter(p => !(query.trim()) || (p.name || "").toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => {
      const ea = (a.elim || (teamById(a.team) || {}).elim) ? 0 : 1;
      const eb = (b.elim || (teamById(b.team) || {}).elim) ? 0 : 1;
      return ea - eb || (a.pts || 0) - (b.pts || 0);
    });

  return (
    <div className="col" style={{ gap: 10 }}>
      {batches.length === 0 && drafts.length === 0 && (
        <div className="card muted" style={{ padding: 18, textAlign: "center" }}>
          No wishlist bids yet — start a batch below, or add players from the Free Agents tab.
        </div>
      )}
      {batches.map((b, bi) => batchCard(b, bi, false))}
      {drafts.map((d, di) => batchCard(d, null, true, di))}
      <div>
        {addRowBtn("New batch — pick a player to take out", () => { setAdder(newBatchOpen ? null : { b: "new", side: "new" }); setQuery(""); })}
        {newBatchOpen && adderPopover(allSquad, startDraft, true, "Search your squad…")}
      </div>
    </div>
  );
}

function WishlistTab({ setToast }) {
  const isMobile = useIsMobile();
  const [bids, setBids] = React.useState(() => (window.MY_WISHLIST_BIDS || []).map(b => ({
    playerIn: Number(b.playerIn),
    playerOut: Number(b.playerOut),
    position: b.position,
  })));
  const [adding, setAdding] = React.useState(false);
  const [dropId, setDropId] = React.useState("");
  const [claimId, setClaimId] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  // Batched (grouped intents) vs flat (the stored source of truth, 1 row per
  // bid). Batched is the default editor; the flat list stays fully editable
  // for late adopters and for validating the exact auction try-order.
  const [view, setView] = React.useState("batched");
  // Desktop flat-list drag reorder (arrows stay as the fallback).
  const flatDragRef = React.useRef(null);

  // Sync helper for the batched editor: it persists server-side and hands
  // back the authoritative stored flat list.
  const onBatchedPersisted = (newBids) => {
    const norm = (newBids || []).map(b => ({
      playerIn: Number(b.playerIn), playerOut: Number(b.playerOut), position: b.position,
    }));
    setBids(norm);
    window.MY_WISHLIST_BIDS = norm.slice();
  };

  const win = window.WINDOW || {};
  // First UNRESOLVED gw (bootstrap) so bids roll to the next GW once one resolves.
  const upcomingGw = window.WISHLIST_BID_GW || win.gw || (window.TOURNAMENT && window.TOURNAMENT.currentGw);
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
    catch (err) { setBids(prev); setToast({ type: "error", message: "Failed to reorder: " + (err.error || err.detail || JSON.stringify(err)) }); }
  };
  // Drag a flat-list row onto another row → move it there (arrows remain the
  // keyboard/mobile fallback).
  const reorderTo = async (from, to) => {
    if (to === from || from == null || to == null) return;
    const next = bids.slice();
    const [b] = next.splice(from, 1);
    next.splice(to, 0, b);
    const prev = bids;
    setBids(next);
    try { await persistBids(next); }
    catch (err) { setBids(prev); setToast({ type: "error", message: "Failed to reorder: " + (err.error || err.detail || JSON.stringify(err)) }); }
  };
  const removeBid = async (i) => {
    const next = bids.filter((_, k) => k !== i);
    const prev = bids;
    setBids(next);  // optimistic
    try { await persistBids(next); }
    catch (err) { setBids(prev); setToast({ type: "error", message: "Failed to remove bid: " + (err.error || err.detail || JSON.stringify(err)) }); }
  };

  const addBid = () => {
    if (!dropId || !claimId) { setToast({ type: "error", message: "Pick a player to drop and a free agent to claim." }); return; }
    const dp = window.PLAYER_MAP[String(dropId)];
    const cp = window.PLAYER_MAP[String(claimId)];
    if (dp && cp && dp.pos !== cp.pos) { setToast({ type: "error", message: "Drop and claim must be the same position." }); return; }
    if (bids.some(b => b.playerIn === Number(claimId) && b.playerOut === Number(dropId))) {
      setToast({ type: "error", message: "That exact swap is already on your wishlist. Pick a different player to drop to add it as a fallback." }); return;
    }
    setBids([...bids, { playerIn: Number(claimId), playerOut: Number(dropId), position: cp ? POS_NAMES[cp.pos] : "?" }]);
    setAdding(false); setDropId(""); setClaimId("");
  };

  const save = async () => {
    if (!upcomingGw) { setToast({ type: "error", message: "No upcoming gameweek — the transfer window is closed." }); return; }
    if (!bids.length) { setToast({ type: "error", message: "Add at least one bid first." }); return; }
    setSaving(true);
    try {
      const lid = window.LEAGUE.id;
      await apiCall("POST", `/leagues/${lid}/wishlist-bids`, {
        gw: upcomingGw,
        bids: bids.map(b => ({ playerIn: b.playerIn, playerOut: b.playerOut, position: b.position })),
      });
      window.MY_WISHLIST_BIDS = bids.slice();
      setToast({ type: "success", message: `Wishlist saved — ${bids.length} bid(s) for GW${upcomingGw}. They'll be resolved by the auction when the window closes.` });
    } catch (err) {
      setToast({ type: "error", message: "Failed to save wishlist: " + (err.error || err.detail || JSON.stringify(err)) });
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
          {" "}The <strong>Batched</strong> view groups one intent — players OUT (leave order) ↔ free agents IN (priority) — without hand-building every pairing; the <strong>Flat list</strong> is the exact order the auction tries and is what's stored.
          {!isFaWindow && <span className="muted"> Bids can be edited any time; they only resolve during the free-agents window.</span>}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ display: "inline-flex", padding: 3, background: "rgba(0,0,0,0.06)", borderRadius: 999 }}>
          {[["batched", "Batched"], ["flat", "Flat list · source of truth"]].map(([v, label]) => (
            <button key={v} className="btn" onClick={() => setView(v)}
              style={{ padding: "6px 16px", fontSize: 12, borderRadius: 999, fontWeight: 700,
                background: view === v ? "var(--navy-900)" : "transparent",
                color: view === v ? "white" : "var(--ink-700)" }}>{label}</button>
          ))}
        </div>
        <span className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>
          {bids.length} bid{bids.length === 1 ? "" : "s"}{upcomingGw ? ` · GW${upcomingGw}` : ""}
        </span>
      </div>

      {view === "batched" ? (
        <BatchedWishlistEditor bids={bids} gw={upcomingGw} onPersisted={onBatchedPersisted} setToast={setToast} />
      ) : (
      <div className="card">
        {isMobile ? (
          <div className="col" style={{ gap: 10, padding: 12 }}>
            {bids.length === 0 && (
              <div className="muted" style={{ textAlign: "center", padding: 18 }}>No wishlist bids yet — add one below.</div>
            )}
            {bids.map((b, i) => {
              const pIn = window.PLAYER_MAP[String(b.playerIn)] || { name: b.playerIn, team: "", pos: 1 };
              const pOut = window.PLAYER_MAP[String(b.playerOut)] || { name: b.playerOut, team: "", pos: 1 };
              const tIn = teamById(pIn.team);
              const tOut = teamById(pOut.team);
              return (
                <div key={`${b.playerIn}_${b.playerOut}`} className="card-section" draggable
                  onDragStart={(e) => { flatDragRef.current = i; if (e.dataTransfer) e.dataTransfer.effectAllowed = "move"; }}
                  onDragOver={(e) => { if (flatDragRef.current != null) e.preventDefault(); }}
                  onDrop={(e) => { e.preventDefault(); const from = flatDragRef.current; flatDragRef.current = null; reorderTo(from, i); }}
                  style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 10 }}>
                  <div style={{ fontWeight: 800, fontSize: 13, marginBottom: 6 }}><span style={{ color: "var(--ink-300)", marginRight: 6 }}>⠿</span>#{i + 1}</div>
                  <div className="wishlist-swap" style={{ display: "grid", gridTemplateColumns: "1fr 24px 1fr", gap: 10, alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "rgba(0,217,107,0.08)", borderRadius: 6, border: "1px solid rgba(0,217,107,0.25)" }}>
                      <Flag team={tIn} />
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 13, cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted" }}
                          onClick={() => showPlayerStats(b.playerIn)}>{pIn.name}</div>
                        <div className="muted" style={{ fontSize: 11 }}>IN · {POS_NAMES[pIn.pos]}</div>
                      </div>
                    </div>
                    <span className="h-display" style={{ color: "var(--ink-300)", textAlign: "center" }}>↔</span>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "rgba(230,57,70,0.08)", borderRadius: 6, border: "1px solid rgba(230,57,70,0.20)" }}>
                      <Flag team={tOut} />
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 13, cursor: "pointer", textDecoration: pOut.elim ? "line-through" : "underline", textDecorationStyle: pOut.elim ? "solid" : "dotted" }}
                          onClick={() => showPlayerStats(b.playerOut)}>{pOut.name}</div>
                        <div className="muted" style={{ fontSize: 11 }}>OUT · {pOut.elim || tOut?.elim ? "ELIMINATED" : POS_NAMES[pOut.pos]}</div>
                      </div>
                    </div>
                  </div>
                  <div className="row" style={{ gap: 6, marginTop: 8 }}>
                    <button className="btn btn--ghost-dark" style={{ flex: 1, minHeight: 40, fontSize: 13 }} disabled={i === 0} onClick={() => move(i, -1)}>↑ Up</button>
                    <button className="btn btn--ghost-dark" style={{ flex: 1, minHeight: 40, fontSize: 13 }} disabled={i === bids.length - 1} onClick={() => move(i, 1)}>↓ Down</button>
                    <button className="btn btn--ghost-dark" style={{ flex: 1, minHeight: 40, fontSize: 13, background: "var(--red-500)", color: "white" }} onClick={() => removeBid(i)}>✕ Remove</button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
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
                <tr key={`${b.playerIn}_${b.playerOut}`} draggable
                  onDragStart={(e) => { flatDragRef.current = i; if (e.dataTransfer) e.dataTransfer.effectAllowed = "move"; }}
                  onDragOver={(e) => { if (flatDragRef.current != null) e.preventDefault(); }}
                  onDrop={(e) => { e.preventDefault(); const from = flatDragRef.current; flatDragRef.current = null; reorderTo(from, i); }}
                  style={{ cursor: "grab" }}>
                  <td className="num" style={{ fontWeight: 800, fontSize: 16 }}><span style={{ color: "var(--ink-300)", marginRight: 6 }}>⠿</span>#{i + 1}</td>
                  <td>
                    <div className="wishlist-swap" style={{ display: "grid", gridTemplateColumns: "1fr 24px 1fr", gap: 10, alignItems: "center", maxWidth: 500 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "rgba(0,217,107,0.08)", borderRadius: 6, border: "1px solid rgba(0,217,107,0.25)" }}>
                        <Flag team={tIn} />
                        <div>
                          <div style={{ fontWeight: 700, fontSize: 13, cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted" }}
                            onClick={() => showPlayerStats(b.playerIn)}>{pIn.name}</div>
                          <div className="muted" style={{ fontSize: 11 }}>IN · {POS_NAMES[pIn.pos]}</div>
                        </div>
                      </div>
                      <span className="h-display" style={{ color: "var(--ink-300)", textAlign: "center" }}>↔</span>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "rgba(230,57,70,0.08)", borderRadius: 6, border: "1px solid rgba(230,57,70,0.20)" }}>
                        <Flag team={tOut} />
                        <div>
                          <div style={{ fontWeight: 700, fontSize: 13, cursor: "pointer", textDecoration: pOut.elim ? "line-through" : "underline", textDecorationStyle: pOut.elim ? "solid" : "dotted" }}
                            onClick={() => showPlayerStats(b.playerOut)}>{pOut.name}</div>
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
        )}

        {/* Save and Add Bid buttons removed as reordering/removing are auto-saved and adding goes through Free Agents tab */}
      </div>
      )}

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
