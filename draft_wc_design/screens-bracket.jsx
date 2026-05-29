// =====================================================================
// WC26 — Screens: Knockout Bracket, Transfers/Waivers
// =====================================================================

// ---------- KNOCKOUT BRACKET ----------
function BracketScreen({ onTab }) {
  const rounds = BRACKET.rounds || BRACKET;
  const hasQf = LEAGUE.knockoutQualifiers === 8 || (rounds.qf && rounds.qf.length > 0);
  const gridColumns = hasQf ? "1fr 1fr 1fr 220px" : "1fr 1fr 220px";

  // QF results: fallback statuses. Currently SF/F empty.
  const qfResults = {
    qf1: { status: "scheduled" },
    qf2: { status: "live", liveLabel: "Lock in 36h" },
    qf3: { status: "scheduled" },
    qf4: { status: "scheduled" },
  };

  const sfResults = {
    sf1: { status: hasQf ? "scheduled" : "live", liveLabel: hasQf ? "Scheduled" : "Lock in 36h" },
    sf2: { status: "scheduled" },
  };

  return (
    <div className="col" style={{ gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Knockout Bracket</h2>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{LEAGUE.name} · {LEAGUE.knockoutQualifiers} qualifiers · {hasQf ? "QF → SF → Final" : "SF → Final"}</div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <span className="pill pill--gold">GW{LEAGUE.knockoutStartGw} · {hasQf ? "Quarter-Finals" : "Semi-Finals"}</span>
        </div>
      </div>

      {/* Seeding explainer */}
      <div className="alert alert--info">
        <div className="alert__icon" style={{ background: "var(--violet-500)", color: "white" }}>i</div>
        <div style={{ fontSize: 13 }}>
          <strong>Bracket seeded after GW{LEAGUE.knockoutStartGw - 1}.</strong> {hasQf ? "Seeds 1–4 are top H2H records; seeds 5–8 are the next best by fantasy points." : "Seeds 1–2 are top H2H records; seeds 3–4 are the next best by fantasy points."} Higher seeds host the lower seeds. Tiebreakers: total fantasy points, then coin flip.
        </div>
      </div>

      <div className="bracket" style={{ gridTemplateColumns: gridColumns }}>
        {/* QF column */}
        {hasQf && (
          <div className="bracket__col">
            <div className="bracket__col-head">Quarter-Finals · GW4</div>
            {rounds.qf && rounds.qf.map((m, i) => <BracketMatch key={m.id} match={m} result={qfResults[m.id]} round="qf" />)}
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
                return <BracketMatch key={m.id} match={m} result={sfResults[m.id]} round="sf" />;
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

      {/* Path to glory */}
      <div className="card" style={{ padding: 20 }}>
        <div className="h-display" style={{ fontSize: 16, marginBottom: 12 }}>Your Path to Glory</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(" + (hasQf ? 3 : 2) + ", 1fr)", gap: 12 }}>
          {hasQf ? [
            { round: "QF", opp: "Tiki-Taka FC", flag: "ARG", gw: 4, dates: "Jul 1–4" },
            { round: "SF", opp: "Winner QF1/3", flag: null, gw: 5, dates: "Jul 5–8" },
            { round: "Final", opp: "TBD", flag: null, gw: 6, dates: "Jul 10–12" },
          ].map((r, i) => (
            <div key={i} style={{ padding: "14px 16px", border: "1px solid var(--border)", borderRadius: 8, background: i === 0 ? "rgba(255,200,68,0.10)" : "var(--cream)", borderColor: i === 0 ? "var(--gold-500)" : "var(--border)" }}>
              <div className="muted" style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>{r.round} · GW{r.gw}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {r.flag && <Flag team={teamById(r.flag)} />}
                <strong style={{ fontSize: 14 }}>{r.opp}</strong>
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{r.dates}</div>
            </div>
          )) : [
            { round: "SF", opp: "Tiki-Taka FC", flag: "ARG", gw: 7, dates: "Jul 14–15" },
            { round: "Final", opp: "TBD", flag: null, gw: 8, dates: "Jul 18–19" },
          ].map((r, i) => (
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
  const meSide = match.home === ME ? "home" : (match.away === ME ? "away" : null);

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


// ---------- TRANSFERS / WAIVERS / FREE AGENTS ----------
function TransfersScreen() {
  const [tab, setTab] = React.useState("free");

  return (
    <div className="col" style={{ gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Transfers</h2>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>Manage your squad between gameweeks</div>
        </div>
      </div>

      {/* Big window banner */}
      <div className="card-dark" style={{ position: "relative", overflow: "hidden" }}>
        <div style={{
          background: "linear-gradient(94deg, #1d1864 0%, #4a1ba8 50%, #ff3e6c 100%)",
          padding: "20px 24px",
        }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", alignItems: "center", gap: 20 }}>
            <div>
              <div className="pill pill--gold" style={{ marginBottom: 8 }}>⏳ WINDOW 3 · THE BIG ONE</div>
              <div className="h-display" style={{ fontSize: 22, color: "white", marginBottom: 4 }}>
                16 nations eliminated. Time to rebuild.
              </div>
              <div style={{ color: "rgba(255,255,255,0.85)", fontSize: 13 }}>
                Window closes <strong>Wed 1 Jul 16:00</strong> · {WINDOW.hoursLeft}h remaining · Waivers process at T+24h (in 12h)
              </div>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <StatBlock label="Free transfers" value="2/2" />
              <StatBlock label="Waiver priority" value="#4" accent="var(--gold-500)" />
            </div>
          </div>
        </div>
        <div style={{ padding: "8px 24px 12px", display: "flex", gap: 16, alignItems: "center", fontSize: 12, color: "rgba(255,255,255,0.7)", borderTop: "1px solid var(--border-dark)" }}>
          <span><span className="dot dot--gold" style={{ marginRight: 6 }} /> Waivers process Mon 27 Jun · 10:00</span>
          <span><span className="dot dot--green" style={{ marginRight: 6 }} /> Free agents available after</span>
          <span><span className="dot dot--red" style={{ marginRight: 6 }} /> Window closes Wed 1 Jul · 16:00</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="card" style={{ padding: "4px 14px", display: "flex", gap: 4 }}>
        {[
          ["free",    "Free Agents"],
          ["waivers", `My Waivers (${MY_WAIVERS.length})`],
          ["squad",   "My Squad"],
          ["history", "History"],
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
      {tab === "waivers" && <WaiversTab />}
      {tab === "squad" && <MySquadTab />}
      {tab === "history" && <TransferHistoryTab />}
    </div>
  );
}

function StatBlock({ label, value, accent }) {
  return (
    <div style={{ background: "rgba(0,0,0,0.25)", padding: "10px 18px", borderRadius: 10, textAlign: "center", minWidth: 110 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: "rgba(255,255,255,0.6)", letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{label}</div>
      <div className="mono" style={{ fontSize: 22, fontWeight: 800, color: accent || "white", lineHeight: 1.1, whiteSpace: "nowrap" }}>{value}</div>
    </div>
  );
}

function FreeAgentsTab() {
  const [posFilter, setPosFilter] = React.useState("all");
  const [activePickup, setActivePickup] = React.useState(null);
  const [playerToDrop, setPlayerToDrop] = React.useState("");

  const list = (window.FREE_AGENTS || []).filter(p => posFilter === "all" || p.pos === Number(posFilter));
  const mySquad = (window.MY_SQUAD_IDS || []).map(id => window.PLAYER_MAP[id]).filter(Boolean);

  const handlePickup = async (p) => {
    if (!playerToDrop) {
      alert("Please select a player to drop.");
      return;
    }
    try {
      const lid = window.LEAGUE.id;
      const winNum = window.WINDOW.windowNumber || 1;
      const pIn = isNaN(Number(p.id)) ? Number(p.id.replace("p_", "")) : Number(p.id);
      const pOut = isNaN(Number(playerToDrop)) ? Number(playerToDrop.replace("p_", "")) : Number(playerToDrop);
      
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

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <strong>Top Free Agents</strong>
          <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>· players not owned by any league manager</span>
        </div>
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
      </div>
      <table className="table-clean">
        <thead>
          <tr>
            <th>Player</th>
            <th>Team</th>
            <th>Pos</th>
            <th>GW4 fixture</th>
            <th style={{ textAlign: "right" }}>Pts</th>
            <th style={{ textAlign: "right" }}>Form</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {list.map(p => {
            const t = teamById(p.team);
            const oppMap = { ARG: "ECU", ENG: "URU", NED: "EGY", USA: "BRA", BEL: "AUS", FRA: "POR2", CRO: "POL", BRA: "USA", JPN: "ESP", KOR: "COL", URU: "ENG", COL: "KOR" };
            const opp = oppMap[p.team] ? teamById(oppMap[p.team]) : null;
            const eligibleDrops = mySquad.filter(s => s.pos === p.pos);
            const isPicking = activePickup?.id === p.id;

            return (
              <tr key={p.id}>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                    <div style={{ width: 36, height: 36, flexShrink: 0 }}><Jersey team={t} pos={p.pos} /></div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 700, whiteSpace: "nowrap" }}>{p.name}</div>
                      <div className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>DR {p.dr}</div>
                    </div>
                  </div>
                </td>
                <td><span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Flag team={t} /> {t.name}</span></td>
                <td><span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.08)", color: "var(--navy-900)", fontSize: 10 }}>{POS_NAMES[p.pos]}</span></td>
                <td>
                  {opp ? (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                      vs <Flag team={opp} /> {opp.id}
                    </span>
                  ) : <span className="muted">—</span>}
                </td>
                <td className="num" style={{ textAlign: "right", fontWeight: 700 }}>{p.pts}</td>
                <td style={{ textAlign: "right" }}>
                  <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700, background: p.pts > 30 ? "rgba(0,217,107,0.18)" : p.pts > 20 ? "rgba(255,200,68,0.18)" : "rgba(0,0,0,0.06)", color: p.pts > 30 ? "#006b35" : p.pts > 20 ? "#7a5a00" : "var(--ink-500)" }}>
                    {p.pts > 30 ? "Hot" : p.pts > 20 ? "Form" : "Cold"}
                  </span>
                </td>
                <td style={{ textAlign: "right" }}>
                  {isPicking ? (
                    <div className="row" style={{ gap: 6, alignItems: "center", justifyContent: "flex-end" }}>
                      <select className="input-field" style={{ width: 140, padding: "4px 8px", fontSize: 12, background: "rgba(255,255,255,0.8)", color: "black" }} value={playerToDrop} onChange={e => setPlayerToDrop(e.target.value)}>
                        <option value="">-- Drop player --</option>
                        {eligibleDrops.map(s => (
                          <option key={s.id} value={s.id}>{s.name} ({s.teamName || s.team})</option>
                        ))}
                      </select>
                      <button className="btn btn--solid-dark" style={{ padding: "4px 8px", fontSize: 11, background: "var(--green-500)", color: "white" }} onClick={() => handlePickup(p)}>✔</button>
                      <button className="btn btn--ghost-dark" style={{ padding: "4px 8px", fontSize: 11, background: "var(--red-500)", color: "white" }} onClick={() => setActivePickup(null)}>✖</button>
                    </div>
                  ) : (
                    <button className="btn btn--draft" style={{ padding: "6px 14px", fontSize: 11 }} onClick={() => { setActivePickup(p); setPlayerToDrop(eligibleDrops[0]?.id || ""); }}>Pick up</button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function WaiversTab() {
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [waiverIn, setWaiverIn] = React.useState("");
  const [waiverOut, setWaiverOut] = React.useState("");

  const list = window.MY_WAIVERS || [];
  const mySquad = (window.MY_SQUAD_IDS || []).map(id => window.PLAYER_MAP[id]).filter(Boolean);

  const eligibleWaiverIn = (window.FREE_AGENTS || []).filter(p => {
    if (!waiverOut) return true;
    const sOut = window.PLAYER_MAP[waiverOut];
    return sOut ? p.pos === sOut.pos : true;
  });

  const handleCancelWaiver = async (waiverId) => {
    try {
      const lid = window.LEAGUE.id;
      await apiCall("DELETE", `/leagues/${lid}/waivers/${waiverId}`);
      alert("Waiver claim cancelled successfully!");
      window.location.reload();
    } catch (err) {
      alert("Failed to cancel waiver: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  const handleSubmitWaiver = async () => {
    if (!waiverIn || !waiverOut) {
      alert("Please select both players.");
      return;
    }
    try {
      const lid = window.LEAGUE.id;
      const winNum = window.WINDOW.windowNumber || 1;
      const pIn = isNaN(Number(waiverIn)) ? Number(waiverIn.replace("p_", "")) : Number(waiverIn);
      const pOut = isNaN(Number(waiverOut)) ? Number(waiverOut.replace("p_", "")) : Number(waiverOut);
      
      await apiCall("POST", `/leagues/${lid}/waivers`, {
        playerIn: pIn,
        playerOut: pOut,
        windowNumber: winNum
      });
      alert("Waiver claim submitted successfully!");
      setIsSubmitting(false);
      window.location.reload();
    } catch (err) {
      alert("Failed to submit waiver: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  return (
    <div className="col" style={{ gap: 12 }}>
      <div className="alert alert--gold">
        <div className="alert__icon" style={{ background: "var(--gold-500)" }}>⏳</div>
        <div>
          <strong>Waivers processing window is open</strong> · Priority-based snake queue.
          Higher-priority managers claim first; after one successful claim, you drop to the back.
        </div>
      </div>

      <div className="card">
        <table className="table-clean">
          <thead>
            <tr>
              <th style={{ width: 50 }}>#</th>
              <th>Claim (in / out)</th>
              <th>Priority</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((w, i) => {
              const pIn = window.PLAYER_MAP[w.playerIn] || { name: w.playerIn, team: "", pos: 1 };
              const pOut = window.PLAYER_MAP[w.playerOut] || { name: w.playerOut, team: "", pos: 1 };
              const tIn = teamById(pIn.team);
              const tOut = teamById(pOut.team);
              return (
                <tr key={w.id}>
                  <td className="num" style={{ fontWeight: 700 }}>{i + 1}</td>
                  <td>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 24px 1fr", gap: 10, alignItems: "center", maxWidth: 500 }}>
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
                  <td className="num">#{w.priority}</td>
                  <td><span className="pill pill--gold" style={{ fontSize: 10 }}>{w.status}</span></td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn btn--ghost-dark" style={{ padding: "6px 14px", fontSize: 11, background: "var(--red-500)", color: "white" }} onClick={() => handleCancelWaiver(w.id)}>Cancel</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {isSubmitting ? (
          <div className="col" style={{ padding: 18, gap: 12, borderTop: "1px solid var(--border)", background: "rgba(0,0,0,0.02)" }}>
            <div style={{ display: "flex", gap: 12, justifyContent: "center", alignItems: "center" }}>
              <div className="col">
                <span style={{ fontSize: 11, fontWeight: 700, marginBottom: 4 }}>DROP PLAYER</span>
                <select className="input-field" style={{ width: 180, padding: 8, background: "white", color: "black" }} value={waiverOut} onChange={e => { setWaiverOut(e.target.value); setWaiverIn(""); }}>
                  <option value="">-- Drop player --</option>
                  {mySquad.map(s => (
                    <option key={s.id} value={s.id}>{s.name} ({POS_NAMES[s.pos]})</option>
                  ))}
                </select>
              </div>
              <span className="h-display" style={{ fontSize: 20, color: "var(--ink-400)", marginTop: 16 }}>↔</span>
              <div className="col">
                <span style={{ fontSize: 11, fontWeight: 700, marginBottom: 4 }}>CLAIM PLAYER</span>
                <select className="input-field" style={{ width: 180, padding: 8, background: "white", color: "black" }} value={waiverIn} onChange={e => setWaiverIn(e.target.value)} disabled={!waiverOut}>
                  <option value="">-- Claim player --</option>
                  {eligibleWaiverIn.map(s => (
                    <option key={s.id} value={s.id}>{s.name} (DR {s.dr})</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="row" style={{ gap: 8, justifyContent: "center" }}>
              <button className="btn btn--ghost-dark" onClick={() => setIsSubmitting(false)}>Cancel</button>
              <button className="btn btn--primary" onClick={handleSubmitWaiver} disabled={!waiverIn || !waiverOut}>Submit Waiver Claim</button>
            </div>
          </div>
        ) : (
          <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border)", textAlign: "center" }}>
            <button className="btn btn--primary" onClick={() => setIsSubmitting(true)}>+ Submit New Waiver Claim</button>
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 18 }}>
        <div className="h-display" style={{ fontSize: 14, marginBottom: 10 }}>Waiver Queue · League-wide priority</div>
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
              <div key={p.id} style={{ display: "grid", gridTemplateColumns: "auto 1fr 100px 100px 100px 100px", padding: "10px 18px", borderTop: "1px solid var(--border)", alignItems: "center", gap: 12, opacity: isElim ? 0.7 : 1 }}>
                <div style={{ width: 32, height: 32 }}><Jersey team={t} pos={p.pos} /></div>
                <div>
                  <div style={{ fontWeight: 700 }}>{p.name} {isElim && <span className="pill pill--red" style={{ marginLeft: 8, fontSize: 9 }}>OUT</span>}</div>
                  <div className="muted" style={{ fontSize: 12 }}>{t.name} · Group {t.grp}</div>
                </div>
                <div className="num" style={{ textAlign: "right" }}><span className="muted" style={{ fontSize: 11 }}>Pts</span> <strong>{p.pts}</strong></div>
                <div className="num" style={{ textAlign: "right" }}><span className="muted" style={{ fontSize: 11 }}>DR</span> {p.dr}</div>
                <button className="btn btn--ghost-dark" style={{ padding: "6px 12px", fontSize: 11 }}>Drop</button>
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
  const history = [
    { type: "auto", date: "Sat 25 Jun", desc: "Italy eliminated — Donnarumma & Barella moved to waivers", state: "Pending claim" },
    { type: "trade", date: "Fri 24 Jun", desc: "Acquired Bruno Fernandes from Tel Aviv United for Foden", state: "Completed" },
    { type: "waiver", date: "Wed 22 Jun", desc: "Claimed L. Yamal off waivers (priority #4)", state: "Completed" },
    { type: "drop", date: "Mon 20 Jun", desc: "Dropped Lewandowski → waiver pool", state: "Completed" },
    { type: "draft", date: "Wed 8 Jun", desc: "Drafted 15-player squad (Snake · pick #7)", state: "Completed" },
  ];
  return (
    <div className="card">
      {history.map((h, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "auto 100px 1fr 120px", padding: "14px 18px", borderTop: i ? "1px solid var(--border)" : "none", alignItems: "center", gap: 14 }}>
          <span style={{ width: 8, height: 8, borderRadius: 4, background: h.type === "auto" ? "var(--red-500)" : h.type === "trade" ? "var(--violet-500)" : h.type === "waiver" ? "var(--gold-500)" : h.type === "drop" ? "var(--ink-500)" : "var(--green-500)" }} />
          <span className="muted" style={{ fontSize: 12 }}>{h.date}</span>
          <span style={{ fontSize: 13 }}>{h.desc}</span>
          <span className="pill" style={{ background: "rgba(0,0,0,0.06)", color: "var(--ink-700)", fontSize: 10, justifySelf: "end" }}>{h.state}</span>
        </div>
      ))}
    </div>
  );
}

Object.assign(window, { BracketScreen, TransfersScreen });
