// =====================================================================
// WC26 — Screens: Player Browser, Fixtures, League standings + Schedule, Trades
// =====================================================================

// ---------- PLAYER BROWSER ----------
function PlayerBrowserScreen() {
  const [search, setSearch] = React.useState("");
  const [pos, setPos] = React.useState("all");
  const [grp, setGrp] = React.useState("all");
  const [owned, setOwned] = React.useState("all");
  const [sort, setSort] = React.useState("pts");

  // squad ownership map
  const owners = {};
  MANAGERS.forEach(m => {
    if (m.uid === ME) MY_SQUAD_IDS.forEach(id => owners[id] = m.uid);
  });

  const activePlayers = window.PLAYERS || PLAYERS;
  const filtered = activePlayers.filter(p => {
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (pos !== "all" && p.pos !== Number(pos)) return false;
    const t = teamById(p.team);
    if (grp !== "all" && t.grp !== grp) return false;
    if (owned === "free" && owners[p.id]) return false;
    if (owned === "mine" && owners[p.id] !== ME) return false;
    if (owned === "elim" && !(p.elim || t.elim)) return false;
    return true;
  });
  filtered.sort((a, b) => {
    if (sort === "pts") return b.pts - a.pts;
    if (sort === "dr") return a.dr - b.dr;
    if (sort === "name") return a.name.localeCompare(b.name);
    return 0;
  });

  return (
    <div className="col" style={{ gap: 16 }}>
      <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Player Browser</h2>

      {/* Filters */}
      <div className="card-dark" style={{ padding: 18 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 160px 160px 200px 140px", gap: 12 }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, opacity: 0.7, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>Search</div>
            <input
              type="text"
              placeholder="Player name…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ width: "100%", padding: "10px 14px", borderRadius: 8, border: "1px solid var(--border-dark-strong)", background: "rgba(255,255,255,0.05)", color: "white" }}
            />
          </div>
          <FilterSelect label="Position" value={pos} onChange={setPos} options={[
            ["all", "All"], ["1", "GK"], ["2", "DEF"], ["3", "MID"], ["4", "FWD"]
          ]} />
          <FilterSelect label="Group" value={grp} onChange={setGrp} options={[
            ["all", "All groups"], ...["A","B","C","D","E","F","G","H","I","J","K","L"].map(g => [g, `Group ${g}`])
          ]} />
          <FilterSelect label="View" value={owned} onChange={setOwned} options={[
            ["all", "All players"], ["free", "Free agents"], ["mine", "My squad"], ["elim", "Eliminated"]
          ]} />
          <FilterSelect label="Sort" value={sort} onChange={setSort} options={[
            ["pts", "Points"], ["dr", "Draft rank"], ["name", "Name A→Z"]
          ]} />
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 14, fontSize: 12, color: "rgba(255,255,255,0.7)" }}>
          <span><span className="mono" style={{ fontWeight: 800, color: "var(--green-400)" }}>{filtered.length}</span> players shown</span>
          <div className="row" style={{ gap: 12 }}>
            <span className="row" style={{ gap: 6 }}><span className="dot dot--gray" /> Owned</span>
            <span className="row" style={{ gap: 6 }}><span className="dot dot--green" /> Free agent</span>
            <span className="row" style={{ gap: 6 }}><span className="dot dot--red" /> Eliminated</span>
          </div>
        </div>
      </div>

      {/* Group flag bands */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 4, marginBottom: 4 }}>
        {["A","B","C","D","E","F","G","H","I","J","K","L"].map(g => (
          <button key={g}
            onClick={() => setGrp(grp === g ? "all" : g)}
            style={{
              padding: "8px 0", borderRadius: 6, fontSize: 11, fontWeight: 800,
              background: `var(--grp-${g})`,
              color: ["B","C","D","E","F"].includes(g) ? "var(--navy-900)" : "white",
              opacity: grp === "all" || grp === g ? 1 : 0.35,
              transition: "opacity 0.12s",
            }}>
            {g}
          </button>
        ))}
      </div>

      <div className="card" style={{ overflow: "hidden" }}>
        <table className="table-clean">
          <thead>
            <tr>
              <th>Player</th>
              <th>Team</th>
              <th>Grp</th>
              <th>Pos</th>
              <th style={{ textAlign: "right" }}>DR</th>
              <th style={{ textAlign: "right" }}>Pts</th>
              <th>Owner</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 30).map(p => {
              const t = teamById(p.team);
              const isElim = p.elim || t?.elim;
              const owner = owners[p.id];
              return (
                <tr key={p.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                      <div style={{ width: 36, height: 36, flexShrink: 0 }}>
                        <Jersey team={t} pos={p.pos} />
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 700, opacity: isElim ? 0.5 : 1, whiteSpace: "nowrap" }}>{p.name}</div>
                        {isElim && <div style={{ fontSize: 10, color: "var(--red-500)", fontWeight: 700, letterSpacing: "0.06em", whiteSpace: "nowrap" }}>OUT · ELIMINATED</div>}
                      </div>
                    </div>
                  </td>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <Flag team={t} /> <span style={{ fontSize: 13 }}>{t.name}</span>
                    </span>
                  </td>
                  <td><GroupChip group={t.grp} /></td>
                  <td><span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.08)", color: "var(--navy-900)", fontSize: 10 }}>{POS_NAMES[p.pos]}</span></td>
                  <td className="num" style={{ textAlign: "right" }}>{p.dr}</td>
                  <td className="num" style={{ textAlign: "right", fontWeight: 700 }}>{p.pts}</td>
                  <td style={{ fontSize: 12 }}>
                    {owner ? (
                      <span className="row" style={{ gap: 6 }}>
                        <span className="dot" style={{ background: owner === ME ? "var(--gold-500)" : "var(--ink-300)" }} />
                        {managerById(owner).team}
                      </span>
                    ) : (
                      <span className="row" style={{ gap: 6, color: "var(--green-500)", fontWeight: 700 }}>
                        <span className="dot dot--green" /> Free agent
                      </span>
                    )}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {!owner && <button className="btn btn--draft" style={{ padding: "6px 14px", fontSize: 11 }}>Claim</button>}
                    {owner === ME && <button className="btn btn--ghost-dark" style={{ padding: "6px 14px", fontSize: 11 }}>Drop</button>}
                    {owner && owner !== ME && <button className="btn btn--ghost-dark" style={{ padding: "6px 14px", fontSize: 11 }}>Trade</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length > 30 && (
          <div style={{ textAlign: "center", padding: 14, borderTop: "1px solid var(--border)" }}>
            <button className="btn btn--ghost-dark">Load more ({filtered.length - 30} more)</button>
          </div>
        )}
      </div>
    </div>
  );
}

function FilterSelect({ label, value, onChange, options }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 700, opacity: 0.7, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>{label}</div>
      <div style={{ position: "relative" }}>
        <select
          value={value}
          onChange={e => onChange(e.target.value)}
          style={{ width: "100%", padding: "10px 30px 10px 12px", borderRadius: 8, border: "1px solid var(--border-dark-strong)", background: "rgba(255,255,255,0.05)", color: "white", appearance: "none", cursor: "pointer" }}
        >
          {options.map(([v, l]) => <option key={v} value={v} style={{ color: "black" }}>{l}</option>)}
        </select>
        <span style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", color: "rgba(255,255,255,0.6)", pointerEvents: "none", fontSize: 10 }}>▼</span>
      </div>
    </div>
  );
}


// ---------- FIXTURES ----------
function FixturesScreen() {
  const [gw, setGw] = React.useState(4);
  const fixtures = WC_FIXTURES_GW4;
  const round = TOURNAMENT.gwDates[gw];

  const byDay = {};
  fixtures.forEach(f => { (byDay[f.day] ||= []).push(f); });

  return (
    <div className="col" style={{ gap: 16 }}>
      <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Fixtures</h2>

      <div className="card-dark" style={{ overflow: "hidden" }}>
        <div style={{ background: "var(--grad-pill-active)", padding: "12px 20px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button className="btn btn--ghost-dark" style={{ padding: "6px 12px", fontSize: 12, background: "rgba(0,0,0,0.10)", border: "1px solid rgba(0,0,0,0.15)" }} onClick={() => setGw(g => Math.max(1, g - 1))}>← GW{gw - 1}</button>
          <div style={{ textAlign: "center", color: "var(--navy-900)" }}>
            <div className="h-display" style={{ fontSize: 18 }}>Gameweek {gw}</div>
            <div style={{ fontSize: 12, fontWeight: 600 }}>{round.wcRound} · {round.start} – {round.end}</div>
          </div>
          <button className="btn btn--ghost-dark" style={{ padding: "6px 12px", fontSize: 12, background: "rgba(0,0,0,0.10)", border: "1px solid rgba(0,0,0,0.15)" }} onClick={() => setGw(g => Math.min(8, g + 1))} disabled={gw >= 8}>GW{gw + 1} →</button>
        </div>

        <div style={{ padding: "20px 28px", color: "white" }}>
          {Object.entries(byDay).map(([day, ms]) => (
            <div key={day} style={{ marginBottom: 18 }}>
              <div style={{ display: "inline-block", background: "var(--green-400)", color: "var(--navy-900)", padding: "4px 12px", borderRadius: 4, fontWeight: 800, fontSize: 11, letterSpacing: "0.06em", marginBottom: 8 }}>{day.toUpperCase()}</div>
              {ms.map((m, i) => {
                const h = teamById(m.home);
                const a = teamById(m.away);
                return (
                  <div key={i} style={{ display: "grid", gridTemplateColumns: "120px 1fr 1fr 1fr 140px", padding: "12px 0", alignItems: "center", borderBottom: "1px solid var(--border-dark)", fontSize: 14 }}>
                    <span className="muted" style={{ fontSize: 12 }}>{m.time} <span style={{ opacity: 0.5 }}>local</span></span>
                    <span style={{ textAlign: "right", display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, fontWeight: 700 }}>
                      {h.name} <Flag team={h} size="lg" />
                    </span>
                    <span style={{ textAlign: "center" }}>
                      <span className="pill pill--dark" style={{ background: "rgba(255,255,255,0.08)", fontSize: 11, color: "white" }}>
                        {round.wcRound.includes("Group") ? `Grp ${h.grp}` : round.wcRound}
                      </span>
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 700 }}>
                      <Flag team={a} size="lg" /> {a.name}
                    </span>
                    <span className="muted" style={{ fontSize: 11, textAlign: "right", color: "rgba(255,255,255,0.6)" }}>{m.venue}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* GW bar (jump) */}
      <div className="card" style={{ padding: "12px 16px", display: "flex", gap: 6 }}>
        {[1,2,3,4,5,6,7,8].map(n => (
          <button key={n} onClick={() => setGw(n)}
            className={"btn " + (gw === n ? "btn--solid-dark" : "btn--ghost-dark")}
            style={{ flex: 1, padding: "10px 0", fontSize: 12 }}>
            GW{n}
            <span style={{ display: "block", fontSize: 9, opacity: 0.7, fontWeight: 500, marginTop: 2 }}>{TOURNAMENT.gwDates[n].wcRound.replace("Group Stage · ", "")}</span>
          </button>
        ))}
      </div>
    </div>
  );
}


// ---------- LEAGUE STANDINGS ----------
function LeagueScreen({ onTab }) {
  const [tab, setTab] = React.useState("standings");
  return (
    <div className="col" style={{ gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
        <h2 className="h-display" style={{ fontSize: 26, margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{LEAGUE.name}</h2>
        <div className="row" style={{ gap: 8, flexShrink: 0 }}>
          <span className="pill pill--gold">Knockout Phase</span>
          <span className="pill pill--dark" style={{ background: "var(--navy-900)", color: "white" }}>{LEAGUE.size} managers</span>
        </div>
      </div>

      <div className="card" style={{ padding: "4px 14px", display: "flex", gap: 4 }}>
        {[
          ["standings", "Standings"],
          ["schedule",  "Group Schedule"],
          ["results",   "Results"],
        ].map(([id, label]) => (
          <button key={id}
            className={"btn " + (tab === id ? "btn--solid-dark" : "")}
            style={{ padding: "10px 18px", fontSize: 13, background: tab === id ? undefined : "transparent", color: tab === id ? undefined : "var(--ink-700)" }}
            onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "standings" && <StandingsTable onTab={onTab} />}
      {tab === "schedule" && <ScheduleTable />}
      {tab === "results" && <ResultsTable />}
    </div>
  );
}

function StandingsTable({ onTab }) {
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <table className="table-clean">
        <thead>
          <tr>
            <th>#</th>
            <th>Manager</th>
            <th style={{ textAlign: "right" }}>W</th>
            <th style={{ textAlign: "right" }}>D</th>
            <th style={{ textAlign: "right" }}>L</th>
            <th style={{ textAlign: "right" }}>H2H Pts</th>
            <th style={{ textAlign: "right" }}>FPts</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {STANDINGS.map((s, i) => {
            const m = managerById(s.uid);
            const t = teamById(m.flag);
            const isMe = s.uid === ME;
            const qualified = !s.knockedOut;
            const showQualLine = i === 7;
            return (
              <React.Fragment key={s.uid}>
                <tr className={(isMe ? "is-me " : "") + (qualified ? "is-qualified" : "")}>
                  <td className="num" style={{ width: 50 }}>
                    <div className="row" style={{ gap: 6 }}>
                      <strong style={{ fontSize: 15 }}>{s.rank}</strong>
                      {s.mv > 0 && <span style={{ color: "var(--green-500)" }}>▲</span>}
                      {s.mv < 0 && <span style={{ color: "var(--hot-500)" }}>▼</span>}
                    </div>
                  </td>
                  <td>
                    <div className="row" style={{ gap: 10, minWidth: 0 }}>
                      <Flag team={t} size="lg" />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.team}</div>
                        <div className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>{m.name}</div>
                      </div>
                      {qualified && i < 4 && <span className="pill pill--gold" style={{ marginLeft: 4, flexShrink: 0 }}>H2H Seed</span>}
                      {qualified && s.ptsSeed && <span className="pill pill--teal" style={{ marginLeft: 4, flexShrink: 0 }}>Pts Seed</span>}
                    </div>
                  </td>
                  <td className="num" style={{ textAlign: "right" }}>{s.hw}</td>
                  <td className="num" style={{ textAlign: "right" }}>{s.hd}</td>
                  <td className="num" style={{ textAlign: "right" }}>{s.hl}</td>
                  <td className="num" style={{ textAlign: "right", fontWeight: 700 }}>{s.hpts}</td>
                  <td className="num" style={{ textAlign: "right" }}>{s.fpts}</td>
                  <td style={{ textAlign: "right", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    {qualified ? <span style={{ color: "var(--green-500)" }}>Qualified</span> : <span style={{ color: "var(--red-500)" }}>Eliminated</span>}
                  </td>
                </tr>
                {showQualLine && (
                  <tr>
                    <td colSpan="8" style={{ padding: 0 }}>
                      <div style={{ borderTop: "2px dashed var(--hot-500)", padding: "6px 14px", background: "rgba(255,62,108,0.05)", fontSize: 11, fontWeight: 700, color: "var(--hot-500)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                        ↑ Qualification Line · Top 8 enter Quarter-Finals
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
      <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border)", fontSize: 12, color: "var(--ink-500)" }}>
        Seeds 1–4 are top H2H; seeds 5–8 are best remaining by fantasy points (Pts Seed).
      </div>
    </div>
  );
}

function ScheduleTable() {
  const gws = window.LEAGUE?.leaguePhaseGws || [1, 2, 3, 4, 5, 6];
  return (
    <div className="card">
      {gws.map(gw => {
        const matches = (window.SCHEDULE || {})[gw] || [];
        if (!matches || matches.length === 0) return null;
        return (
          <div key={gw} style={{ borderBottom: "1px solid var(--border)" }}>
            <div style={{ padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--cream)" }}>
              <strong>Gameweek {gw}</strong>
              <span className="muted" style={{ fontSize: 12 }}>{TOURNAMENT.gwDates[gw]?.wcRound || `Gameweek ${gw}`}</span>
            </div>
            {matches.map(([a, b], i) => {
              const A = managerById(a), B = managerById(b);
              if (!A || !B) return null;
              const aT = teamById(A.flag), bT = teamById(B.flag);
              const gwScores = (window.ALL_GW_SCORES || {})[gw];
              const ap = gwScores && gwScores[a] !== undefined ? gwScores[a] : (gw === window.TOURNAMENT.currentGw ? (window.GW3_TOTALS[a] || 0) : "—");
              const bp = gwScores && gwScores[b] !== undefined ? gwScores[b] : (gw === window.TOURNAMENT.currentGw ? (window.GW3_TOTALS[b] || 0) : "—");
              const hasScore = ap !== "—" && bp !== "—";
              const aWin = hasScore && Number(ap) > Number(bp);
              const isMe = a === ME || b === ME;
              return (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 90px 1fr", padding: "10px 18px", borderTop: "1px solid var(--border)", alignItems: "center", background: isMe ? "rgba(91,61,242,0.05)" : "transparent" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, fontWeight: hasScore && aWin ? 700 : 500 }}>
                    <span>{A.team}</span>
                    <Flag team={aT} />
                  </div>
                  <div style={{ textAlign: "center", fontFamily: "var(--font-num)", fontWeight: 800, fontSize: 16 }}>
                    <span style={{ color: hasScore && aWin ? "var(--navy-900)" : "var(--ink-500)" }}>{ap}</span>
                    <span style={{ color: "var(--ink-300)", margin: "0 8px" }}>–</span>
                    <span style={{ color: hasScore && !aWin ? "var(--navy-900)" : "var(--ink-500)" }}>{bp}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: !aWin ? 700 : 500 }}>
                    <Flag team={bT} />
                    <span>{B.team}</span>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

function ResultsTable() {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div className="h-display" style={{ fontSize: 16, marginBottom: 8 }}>Latest Results · GW3</div>
      <div className="muted" style={{ fontSize: 13 }}>Final H2H results from group stage MD3.</div>
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {SCHEDULE[3].map(([a, b], i) => {
          const A = managerById(a), B = managerById(b);
          const ap = GW3_TOTALS[a], bp = GW3_TOTALS[b];
          return (
            <div key={i} style={{ padding: "12px 14px", border: "1px solid var(--border)", borderRadius: 8, display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 10, alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
                <span style={{ fontSize: 13, fontWeight: ap > bp ? 700 : 500 }}>{A.team}</span>
                <Flag team={teamById(A.flag)} />
              </div>
              <div className="mono" style={{ fontWeight: 800, fontSize: 18 }}>{ap}–{bp}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Flag team={teamById(B.flag)} />
                <span style={{ fontSize: 13, fontWeight: bp > ap ? 700 : 500 }}>{B.team}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ---------- TRADES ----------
function TradesScreen() {
  const [tab, setTab] = React.useState("inbox");
  return (
    <div className="col" style={{ gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Trades</h2>
        <button className="btn btn--primary">+ Propose Trade</button>
      </div>

      <div className="card" style={{ padding: "4px 14px", display: "flex", gap: 4 }}>
        {[
          ["inbox", `Inbox (${TRADES_INBOX.length})`],
          ["outbox", `Sent (${TRADES_OUTBOX.length})`],
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

      {tab === "inbox" && TRADES_INBOX.map(t => <TradeCard key={t.id} trade={t} direction="inbox" />)}
      {tab === "outbox" && TRADES_OUTBOX.map(t => <TradeCard key={t.id} trade={t} direction="outbox" />)}
      {tab === "history" && (
        <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--ink-500)" }}>
          No completed trades yet this season.
        </div>
      )}
    </div>
  );
}

function TradeCard({ trade, direction }) {
  const proposer = managerById(trade.proposer);
  const target = managerById(trade.target);
  const isIncoming = direction === "inbox";

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div style={{ background: "var(--navy-900)", color: "white", padding: "10px 18px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: "nowrap" }}>
          {isIncoming ? `${proposer.team} offers a trade` : `Sent to ${target.team}`}
        </span>
        <span className="muted" style={{ color: "rgba(255,255,255,0.6)", fontSize: 12, whiteSpace: "nowrap" }}>{trade.createdAt}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", padding: 20, gap: 16, alignItems: "center" }}>
        <div>
          <div className="muted" style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
            {isIncoming ? "You give" : "You give"}
          </div>
          {(isIncoming ? trade.targetPlayers : trade.proposerPlayers).map(id => {
            const p = playerById(id);
            const t = teamById(p.team);
            return (
              <div key={id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "var(--cream)", borderRadius: 8 }}>
                <div style={{ width: 36, height: 36 }}><Jersey team={t} pos={p.pos} /></div>
                <div>
                  <div style={{ fontWeight: 700 }}>{p.name}</div>
                  <div className="muted" style={{ fontSize: 12 }}>{POS_NAMES[p.pos]} · {t.name} · {p.pts} pts</div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="h-display" style={{ fontSize: 26, color: "var(--ink-300)" }}>↔</div>
        <div>
          <div className="muted" style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
            {isIncoming ? "You get" : "You get"}
          </div>
          {(isIncoming ? trade.proposerPlayers : trade.targetPlayers).map(id => {
            const p = playerById(id);
            const t = teamById(p.team);
            return (
              <div key={id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "var(--cream)", borderRadius: 8 }}>
                <div style={{ width: 36, height: 36 }}><Jersey team={t} pos={p.pos} /></div>
                <div>
                  <div style={{ fontWeight: 700 }}>{p.name}</div>
                  <div className="muted" style={{ fontSize: 12 }}>{POS_NAMES[p.pos]} · {t.name} · {p.pts} pts</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {trade.message && (
        <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)", background: "var(--cream)", fontSize: 13, color: "var(--ink-700)", fontStyle: "italic" }}>
          "{trade.message}"
        </div>
      )}
      <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)", display: "flex", gap: 8, justifyContent: "space-between", alignItems: "center" }}>
        <span className="muted" style={{ fontSize: 12 }}>
          {trade.status === "pending" && (isIncoming ? "Awaiting your decision" : "Awaiting their decision")}
          {" · "}League approval: vote (3 vetoes needed)
        </span>
        {isIncoming ? (
          <div className="row" style={{ gap: 8 }}>
            <button className="btn btn--ghost-dark">Decline</button>
            <button className="btn btn--primary">Accept</button>
          </div>
        ) : (
          <button className="btn btn--ghost-dark">Cancel</button>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { PlayerBrowserScreen, FixturesScreen, LeagueScreen, TradesScreen });
