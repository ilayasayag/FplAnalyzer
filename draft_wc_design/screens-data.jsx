// =====================================================================
// WC26 — Screens: Player Browser, Fixtures, League standings + Schedule, Trades
// =====================================================================

// ---------- PLAYER BROWSER ----------
function PlayerBrowserScreen() {
  const [search, setSearch] = React.useState("");
  const [pos, setPos] = React.useState("all");
  const [grp, setGrp] = React.useState("all");
  const [nation, setNation] = React.useState("all");
  const [owned, setOwned] = React.useState("all");
  const [sort, setSort] = React.useState("pts");

  // Squad ownership map: playerId -> owning manager uid, across ALL managers.
  // app.jsx preloads window.SQUADS_BY_UID from the per-manager squad endpoint;
  // without it, only ME's squad would be known and every other manager's
  // players (e.g. Haaland) would wrongly render as free agents.
  const owners = {};
  const squadsByUid = window.SQUADS_BY_UID || {};
  const activeManagers = window.MANAGERS || MANAGERS;
  activeManagers.forEach(m => {
    const ids = squadsByUid[m.uid] || (m.uid === window.ME ? (window.MY_SQUAD_IDS || MY_SQUAD_IDS) : []);
    (ids || []).forEach(id => { owners[String(id)] = m.uid; });
  });

  const activePlayers = window.PLAYERS || PLAYERS;

  // Distinct nations actually present in the loaded dataset — drives the
  // Nation filter and doubles as a data-completeness check (48 = full DB).
  const nationCounts = {};
  activePlayers.forEach(p => { nationCounts[p.team] = (nationCounts[p.team] || 0) + 1; });
  const nationOptions = Object.keys(nationCounts)
    .map(id => [id, `${teamById(id)?.name || id} (${nationCounts[id]})`])
    .sort((a, b) => a[1].localeCompare(b[1]));
  const distinctNations = nationOptions.length;

  const filtered = activePlayers.filter(p => {
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (pos !== "all" && p.pos !== Number(pos)) return false;
    if (nation !== "all" && p.team !== nation) return false;
    const t = teamById(p.team);
    if (grp !== "all" && t.grp !== grp) return false;
    if (owned === "free" && owners[p.id]) return false;
    if (owned === "mine" && owners[p.id] !== window.ME) return false;
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
        <div style={{ display: "grid", gridTemplateColumns: "1fr 110px 130px 150px 150px 120px", gap: 12 }}>
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
          <FilterSelect label="Nation" value={nation} onChange={setNation} options={[
            ["all", `All nations (${distinctNations})`], ...nationOptions
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
          <span>
            <span className="mono" style={{ fontWeight: 800, color: "var(--green-400)" }}>{filtered.length}</span> players shown
            <span style={{ opacity: 0.6 }}> · </span>
            <span className="mono" style={{ fontWeight: 800, color: distinctNations >= 48 ? "var(--green-400)" : "var(--gold-500)" }}>{distinctNations}</span> nations in dataset
          </span>
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
                        <div style={{ fontWeight: 700, opacity: isElim ? 0.5 : 1, whiteSpace: "nowrap", cursor: "pointer", textDecoration: "underline" }}
                          onClick={() => window.dispatchEvent(new CustomEvent("show-player-stats", { detail: { id: p.id } }))}>{p.name}</div>
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
                  <td className="num" style={{ textAlign: "right", fontWeight: 700 }}>{p.pts}</td>
                  <td style={{ fontSize: 12 }}>
                    {owner ? (
                      <span className="row" style={{ gap: 6 }}>
                        <span className="dot" style={{ background: owner === window.ME ? "var(--gold-500)" : "var(--ink-300)" }} />
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
                    {owner === window.ME && <button className="btn btn--ghost-dark" style={{ padding: "6px 14px", fontSize: 11 }}>Drop</button>}
                    {owner && owner !== window.ME && <button className="btn btn--ghost-dark" style={{ padding: "6px 14px", fontSize: 11 }}>Trade</button>}
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
          {(window.STANDINGS || STANDINGS).map((s, i) => {
            const m = managerById(s.uid);
            const t = teamById(m.flag);
            const isMe = s.uid === window.ME;
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
  const [squadModal, setSquadModal] = React.useState(null); // { uid, gw }
  return (
    <div className="card">
      {squadModal && <ManagerSquadModal uid={squadModal.uid} gw={squadModal.gw} onClose={() => setSquadModal(null)} />}
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
              const isMe = a === window.ME || b === window.ME;
              const nameStyle = { cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted" };
              return (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 90px 1fr", padding: "10px 18px", borderTop: "1px solid var(--border)", alignItems: "center", background: isMe ? "rgba(91,61,242,0.05)" : "transparent" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, fontWeight: hasScore && aWin ? 700 : 500 }}>
                    <span style={nameStyle} onClick={() => setSquadModal({ uid: a, gw })}>{A.team}</span>
                    <Flag team={aT} />
                  </div>
                  <div style={{ textAlign: "center", fontFamily: "var(--font-num)", fontWeight: 800, fontSize: 16 }}>
                    <span style={{ color: hasScore && aWin ? "var(--navy-900)" : "var(--ink-500)" }}>{ap}</span>
                    <span style={{ color: "var(--ink-300)", margin: "0 8px" }}>–</span>
                    <span style={{ color: hasScore && !aWin ? "var(--navy-900)" : "var(--ink-500)" }}>{bp}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: !aWin ? 700 : 500 }}>
                    <Flag team={bT} />
                    <span style={nameStyle} onClick={() => setSquadModal({ uid: b, gw })}>{B.team}</span>
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
  const [squadModal, setSquadModal] = React.useState(null);
  return (
    <div className="card" style={{ padding: 20 }}>
      {squadModal && <ManagerSquadModal uid={squadModal.uid} gw={squadModal.gw} onClose={() => setSquadModal(null)} />}
      <div className="h-display" style={{ fontSize: 16, marginBottom: 8 }}>Latest Results · GW3</div>
      <div className="muted" style={{ fontSize: 13 }}>Final H2H results from group stage MD3. Click a name to see their squad breakdown.</div>
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {SCHEDULE[3].map(([a, b], i) => {
          const A = managerById(a), B = managerById(b);
          const ap = GW3_TOTALS[a], bp = GW3_TOTALS[b];
          const nameStyle = { cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted" };
          return (
            <div key={i} style={{ padding: "12px 14px", border: "1px solid var(--border)", borderRadius: 8, display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 10, alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
                <span style={{ fontSize: 13, fontWeight: ap > bp ? 700 : 500, ...nameStyle }} onClick={() => setSquadModal({ uid: a, gw: 3 })}>{A.team}</span>
                <Flag team={teamById(A.flag)} />
              </div>
              <div className="mono" style={{ fontWeight: 800, fontSize: 18 }}>{ap}–{bp}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Flag team={teamById(B.flag)} />
                <span style={{ fontSize: 13, fontWeight: bp > ap ? 700 : 500, ...nameStyle }} onClick={() => setSquadModal({ uid: b, gw: 3 })}>{B.team}</span>
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
  const [showPropose, setShowPropose] = React.useState(false);
  const inbox = window.TRADES_INBOX || TRADES_INBOX;
  const outbox = window.TRADES_OUTBOX || TRADES_OUTBOX;
  return (
    <div className="col" style={{ gap: 16 }}>
      {showPropose && <ProposeTradeModal onClose={() => setShowPropose(false)} />}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Trades</h2>
        <button className="btn btn--primary" onClick={() => setShowPropose(true)}>+ Propose Trade</button>
      </div>

      <div className="card" style={{ padding: "4px 14px", display: "flex", gap: 4 }}>
        {[
          ["inbox", `Inbox (${inbox.length})`],
          ["outbox", `Sent (${outbox.length})`],
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

      {tab === "inbox" && (inbox.length
        ? inbox.map(t => <TradeCard key={t.id} trade={t} direction="inbox" />)
        : <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--ink-500)" }}>No incoming trade offers.</div>)}
      {tab === "outbox" && (outbox.length
        ? outbox.map(t => <TradeCard key={t.id} trade={t} direction="outbox" />)
        : <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--ink-500)" }}>You haven't sent any trade offers.</div>)}
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
  const [busy, setBusy] = React.useState(false);

  const act = async (kind) => {
    if (busy) return;
    if (kind === "cancel" && !window.confirm("Cancel this trade offer?")) return;
    setBusy(true);
    try {
      const lid = window.LEAGUE.id;
      if (kind === "cancel") {
        await apiCall("POST", `/leagues/${lid}/trades/${trade.id}/cancel`, {});
      } else {
        await apiCall("POST", `/leagues/${lid}/trades/${trade.id}/respond`, { action: kind });
      }
      window.location.reload();
    } catch (err) {
      alert("Trade action failed: " + (err.error || err.detail || JSON.stringify(err)));
      setBusy(false);
    }
  };

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
            <button className="btn btn--ghost-dark" disabled={busy} onClick={() => act("decline")}>Decline</button>
            <button className="btn btn--primary" disabled={busy} onClick={() => act("accept")}>{busy ? "…" : "Accept"}</button>
          </div>
        ) : (
          <button className="btn btn--ghost-dark" disabled={busy} onClick={() => act("cancel")}>{busy ? "…" : "Cancel"}</button>
        )}
      </div>
    </div>
  );
}

// ---------- MANAGER SQUAD MODAL ----------
function ManagerSquadModal({ uid, gw, onClose }) {
  const [players, setPlayers] = React.useState(null); // null = loading
  const m = managerById(uid);
  const gwPoints = window.GW3_POINTS || {};
  const gwTotals = (window.ALL_GW_SCORES || {})[gw] || {};
  const managerTotal = gwTotals[uid] !== undefined ? gwTotals[uid]
    : (gw === 3 ? (window.GW3_TOTALS || {})[uid] : "—");

  React.useEffect(() => {
    const fetchSquad = async () => {
      try {
        const lid = window.LEAGUE.id;
        const res = await apiCall("GET", `/leagues/${lid}/squads/${uid}`);
        // API returns players as [{playerId, position, ...}] — normalize to string IDs
        setPlayers((res.players || []).map(p => String(p.playerId)));
      } catch (e) {
        // Fallback: if we're the manager, use MY_SQUAD_IDS
        setPlayers(uid === window.ME ? (window.MY_SQUAD_IDS || []) : []);
      }
    };
    fetchSquad();
  }, [uid]);

  React.useEffect(() => {
    const k = e => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  // Group by position
  const byPos = { 1: [], 2: [], 3: [], 4: [] };
  if (players) {
    players.forEach(rawId => {
      const id = typeof rawId === "number" ? rawId : (isNaN(Number(rawId)) ? rawId : Number(rawId));
      const p = playerById(id);
      if (p && byPos[p.pos]) byPos[p.pos].push(p);
    });
  }

  const getGwPts = (p) => {
    if (gw !== 3) return "—";
    const v = gwPoints[p.id] ?? gwPoints[Number(p.id)] ?? gwPoints[String(p.id)];
    return v !== undefined ? v : 0;
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 520, maxHeight: "88vh", overflowY: "auto" }} onClick={e => e.stopPropagation()}>
        <button className="modal__close" onClick={onClose}>×</button>
        <div style={{ padding: "24px 24px 12px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Squad Breakdown · GW{gw}</div>
          <div className="h-display" style={{ fontSize: 24, marginTop: 4 }}>{m?.team || "Squad"}</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{m?.name}</div>
          <div style={{ marginTop: 12, display: "inline-flex", alignItems: "center", gap: 10, background: "var(--navy-900)", color: "white", padding: "10px 16px", borderRadius: 10 }}>
            <span style={{ fontSize: 12, opacity: 0.7 }}>GW{gw} Total</span>
            <span className="mono" style={{ fontSize: 26, fontWeight: 800, color: "var(--gold-500)" }}>{managerTotal}</span>
            <span style={{ fontSize: 12, opacity: 0.5 }}>pts</span>
          </div>
        </div>

        {players === null ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--ink-500)" }}>Loading squad…</div>
        ) : players.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--ink-500)" }}>No squad data available.</div>
        ) : (
          <div style={{ padding: "12px 24px 24px" }}>
            {[1, 2, 3, 4].map(pos => {
              const list = byPos[pos];
              if (!list.length) return null;
              const posName = ["", "Goalkeepers", "Defenders", "Midfielders", "Forwards"][pos];
              return (
                <div key={pos} style={{ marginTop: 14 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
                    {posName} ({list.length})
                  </div>
                  {list.map(p => {
                    const t = teamById(p.team);
                    const pts = getGwPts(p);
                    const isElim = p.elim || t?.elim;
                    return (
                      <div key={p.id} style={{ display: "grid", gridTemplateColumns: "36px 1fr auto", gap: 10, padding: "8px 0", borderBottom: "1px solid var(--border)", alignItems: "center" }}>
                        <div style={{ width: 36, height: 36 }}><Jersey team={t} pos={p.pos} /></div>
                        <div>
                          <div style={{ fontWeight: 700 }}>{p.name} {isElim && <span className="pill pill--red" style={{ fontSize: 9, marginLeft: 4 }}>OUT</span>}</div>
                          <div className="muted" style={{ fontSize: 12 }}>{t?.name} · {POS_NAMES[p.pos]}</div>
                        </div>
                        <div className="mono" style={{ fontWeight: 800, fontSize: 20, color: pts > 0 ? "var(--navy-900)" : "var(--ink-300)", minWidth: 32, textAlign: "right" }}>
                          {pts}
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}


// ---------- PROPOSE TRADE MODAL ----------
function ProposeTradeModal({ onClose }) {
  const [step, setStep] = React.useState(1);
  const [targetUid, setTargetUid] = React.useState(null);
  const [theirPlayers, setTheirPlayers] = React.useState(null);
  const [mySelected, setMySelected] = React.useState(new Set());
  const [theirSelected, setTheirSelected] = React.useState(new Set());
  const [submitting, setSubmitting] = React.useState(false);

  const managers = (window.MANAGERS || []).filter(m => m.uid !== window.ME);
  const mySquad = (window.MY_SQUAD_IDS || []).map(rawId => {
    const id = typeof rawId === "number" ? rawId : (isNaN(Number(rawId)) ? rawId : Number(rawId));
    return playerById(id);
  }).filter(Boolean);

  const theirSquad = (theirPlayers || []).map(rawId => {
    const id = typeof rawId === "number" ? rawId : (isNaN(Number(rawId)) ? rawId : Number(rawId));
    return playerById(id);
  }).filter(Boolean);

  const countByPos = (set) => {
    const c = { 1: 0, 2: 0, 3: 0, 4: 0 };
    set.forEach(id => {
      const p = playerById(id) || playerById(Number(id));
      if (p) c[p.pos] = (c[p.pos] || 0) + 1;
    });
    return c;
  };

  const myPosCounts = countByPos(mySelected);
  const theirPosCounts = countByPos(theirSelected);
  const posValid = mySelected.size > 0 && theirSelected.size > 0 &&
    [1, 2, 3, 4].every(pos => myPosCounts[pos] === theirPosCounts[pos]);
  const validationMsg = () => {
    if (mySelected.size === 0 && theirSelected.size === 0) return "Select players from each squad to trade.";
    if (!posValid) {
      const diff = [1, 2, 3, 4].filter(pos => myPosCounts[pos] !== theirPosCounts[pos]);
      return `Position mismatch: ${diff.map(p => POS_NAMES[p]).join(", ")} counts differ between sides.`;
    }
    return null;
  };

  const handleSelectManager = async (uid) => {
    setTargetUid(uid);
    setTheirPlayers(null);
    setStep(2);
    try {
      const lid = window.LEAGUE.id;
      const res = await apiCall("GET", `/leagues/${lid}/squads/${uid}`);
      // API returns players as [{playerId, position, ...}] — normalize to string IDs
      setTheirPlayers((res.players || []).map(p => String(p.playerId)));
    } catch (e) {
      setTheirPlayers([]);
    }
  };

  const toggleMy = (id) => {
    const s = new Set(mySelected);
    s.has(id) ? s.delete(id) : s.add(id);
    setMySelected(s);
  };

  const toggleTheir = (id) => {
    const s = new Set(theirSelected);
    s.has(id) ? s.delete(id) : s.add(id);
    setTheirSelected(s);
  };

  const handleSubmit = async () => {
    if (!posValid) return;
    setSubmitting(true);
    try {
      const lid = window.LEAGUE.id;
      await apiCall("POST", `/leagues/${lid}/trades`, {
        targetUid,
        proposerPlayerIds: Array.from(mySelected).map(id => isNaN(Number(id)) ? Number(String(id).replace("p_", "")) : Number(id)),
        targetPlayerIds: Array.from(theirSelected).map(id => isNaN(Number(id)) ? Number(String(id).replace("p_", "")) : Number(id)),
      });
      alert("Trade proposal sent! Awaiting their response.");
      onClose();
      // Refetch so the new trade appears in the proposer's outbox (and the
      // target's inbox). Mirrors TradeCard.act — there's no standalone
      // trades-loader to call, so a reload is the reliable refresh here.
      window.location.reload();
    } catch (err) {
      alert("Trade failed: " + (err.error || err.detail || JSON.stringify(err)));
    } finally {
      setSubmitting(false);
    }
  };

  React.useEffect(() => {
    const k = e => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  const targetMgr = targetUid ? managerById(targetUid) : null;

  const renderPlayerRow = (p, selected, onToggle, side) => {
    const t = teamById(p.team);
    const isElim = p.elim || t?.elim;
    const isSel = selected.has(p.id) || selected.has(String(p.id));
    return (
      <div key={p.id}
        onClick={() => onToggle(p.id)}
        style={{
          display: "grid", gridTemplateColumns: "28px 1fr auto", gap: 8,
          padding: "8px 10px", cursor: "pointer", borderRadius: 6, marginBottom: 2,
          background: isSel ? "rgba(91,61,242,0.12)" : "transparent",
          border: isSel ? "1px solid rgba(91,61,242,0.35)" : "1px solid transparent",
          opacity: isElim ? 0.55 : 1,
        }}>
        <div style={{ width: 28, height: 28 }}><Jersey team={t} pos={p.pos} /></div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 13 }}>{p.name}</div>
          <div style={{ fontSize: 11, color: "var(--ink-500)" }}>{POS_NAMES[p.pos]} · {t?.name}</div>
        </div>
        <div style={{ alignSelf: "center" }}>
          <span style={{
            display: "inline-block", width: 18, height: 18, borderRadius: "50%",
            border: "2px solid " + (isSel ? "var(--violet-500)" : "var(--border-strong)"),
            background: isSel ? "var(--violet-500)" : "transparent",
          }} />
        </div>
      </div>
    );
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ maxWidth: step === 2 ? 760 : 500, maxHeight: "90vh", overflowY: "auto" }} onClick={e => e.stopPropagation()}>
        <button className="modal__close" onClick={onClose}>×</button>

        {/* Step 1 — pick manager */}
        {step === 1 && (
          <div style={{ padding: 24 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Propose Trade · Step 1 of 2</div>
            <div className="h-display" style={{ fontSize: 22, margin: "6px 0 16px" }}>Who do you want to trade with?</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
              {managers.map(m => {
                const t = teamById(m.flag);
                return (
                  <button key={m.uid} onClick={() => handleSelectManager(m.uid)}
                    style={{ padding: "14px 16px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--cream)", textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", gap: 10, transition: "box-shadow 0.1s" }}
                    onMouseOver={e => e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.10)"}
                    onMouseOut={e => e.currentTarget.style.boxShadow = "none"}>
                    {t && <Flag team={t} />}
                    <div>
                      <div style={{ fontWeight: 700 }}>{m.team}</div>
                      <div className="muted" style={{ fontSize: 12 }}>{m.name}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Step 2 — pick players */}
        {step === 2 && (
          <div style={{ padding: "0 0 0" }}>
            {/* Header */}
            <div style={{ padding: "18px 24px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12 }}>
              <button className="btn btn--ghost-dark" style={{ padding: "6px 12px", fontSize: 12 }} onClick={() => { setStep(1); setMySelected(new Set()); setTheirSelected(new Set()); }}>← Back</button>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Propose Trade · Step 2 of 2</div>
                <div className="h-display" style={{ fontSize: 18, marginTop: 2 }}>Select players to swap with {targetMgr?.team}</div>
              </div>
            </div>

            {/* Squads side by side */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
              {/* My squad */}
              <div style={{ padding: 18, borderRight: "1px solid var(--border)" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
                  Your Squad — you give
                  {mySelected.size > 0 && <span className="pill pill--dark" style={{ marginLeft: 8, fontSize: 10 }}>{mySelected.size} selected</span>}
                </div>
                {[1, 2, 3, 4].map(pos => {
                  const list = mySquad.filter(p => p.pos === pos);
                  if (!list.length) return null;
                  return (
                    <div key={pos} style={{ marginBottom: 10 }}>
                      <div style={{ fontSize: 10, fontWeight: 700, color: "var(--ink-400)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 4 }}>
                        {POS_NAMES[pos]}s
                      </div>
                      {list.map(p => renderPlayerRow(p, mySelected, toggleMy, "my"))}
                    </div>
                  );
                })}
              </div>

              {/* Their squad */}
              <div style={{ padding: 18 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
                  {targetMgr?.team} — you receive
                  {theirSelected.size > 0 && <span className="pill pill--dark" style={{ marginLeft: 8, fontSize: 10 }}>{theirSelected.size} selected</span>}
                </div>
                {theirPlayers === null ? (
                  <div style={{ padding: 24, textAlign: "center", color: "var(--ink-500)", fontSize: 13 }}>Loading their squad…</div>
                ) : theirSquad.length === 0 ? (
                  <div style={{ padding: 24, textAlign: "center", color: "var(--ink-500)", fontSize: 13 }}>No squad data.</div>
                ) : (
                  [1, 2, 3, 4].map(pos => {
                    const list = theirSquad.filter(p => p.pos === pos);
                    if (!list.length) return null;
                    return (
                      <div key={pos} style={{ marginBottom: 10 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--ink-400)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 4 }}>
                          {POS_NAMES[pos]}s
                        </div>
                        {list.map(p => renderPlayerRow(p, theirSelected, toggleTheir, "their"))}
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Validation + Submit */}
            <div style={{ padding: "14px 24px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, background: "var(--cream)" }}>
              <div style={{ fontSize: 13, color: posValid ? "var(--green-600)" : "var(--ink-500)" }}>
                {validationMsg() || "✓ Trade looks good — positions match!"}
              </div>
              <button className="btn btn--primary" style={{ flexShrink: 0 }}
                disabled={!posValid || submitting}
                onClick={handleSubmit}>
                {submitting ? "Sending…" : "Send Trade Proposal →"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


Object.assign(window, { PlayerBrowserScreen, FixturesScreen, LeagueScreen, TradesScreen });
