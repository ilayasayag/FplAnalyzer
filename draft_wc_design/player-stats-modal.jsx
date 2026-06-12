// =====================================================================
// WC26 — Player Stats Modal
// Opens on dispatchEvent('show-player-stats', { detail: { id }})
// =====================================================================

function PlayerStatsModal() {
  const [playerId, setPlayerId] = React.useState(null);
  const [tab, setTab] = React.useState("history");
  // Real per-GW breakdown fetched from GET /players/{id}/scores.
  // history === null while loading, [] when there are no scored rows yet.
  const [history, setHistory] = React.useState(null);
  const [historyErr, setHistoryErr] = React.useState(false);

  React.useEffect(() => {
    const handler = e => {
      setPlayerId(e.detail.id);
      setTab("history");
    };
    window.addEventListener("show-player-stats", handler);
    return () => window.removeEventListener("show-player-stats", handler);
  }, []);

  // Close on ESC
  React.useEffect(() => {
    if (!playerId) return;
    const k = e => { if (e.key === "Escape") setPlayerId(null); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [playerId]);

  // Fetch the REAL per-GW scoring breakdown for the open player. Every rendered
  // row's stats AND its PTS come from the SAME backend row — the engine output
  // (fantasyPoints already includes bonus), never an independent fabrication.
  React.useEffect(() => {
    if (!playerId) { setHistory(null); setHistoryErr(false); return; }
    let cancelled = false;
    setHistory(null);
    setHistoryErr(false);
    apiCall("GET", `/players/${playerId}/scores`)
      .then(rows => {
        if (cancelled) return;
        const mapped = (rows || []).map(row => {
          const s = row.stats || {};
          return {
            gw: row.gw,
            opp: s.opponent || row.opponent || "—",
            round: s.round || row.round || `GW${row.gw}`,
            mp: s.minutes || 0,
            gs: s.goals || 0,
            a: s.assists || 0,
            cs: !!s.cleanSheet,
            gc: s.goalsConceded || 0,
            yc: s.yellowCards || 0,
            s: s.saves || 0,
            b: row.bonusPoints != null ? row.bonusPoints : (s.bonusPoints || 0),
            pts: row.fantasyPoints != null ? row.fantasyPoints : 0,
            // Defensive contribution actions (tackles+int+clear+blocks) + the
            // itemized scoring breakdown for the "every point explained" panel.
            defc: (s.defCon != null) ? s.defCon : (((s.tackles || {}).total || 0) + ((s.tackles || {}).interceptions || 0) + ((s.tackles || {}).blocks || 0) + (s.clearances || 0)),
            breakdown: Array.isArray(row.breakdown) ? row.breakdown : [],
            fifaPoints: row.fifaPoints,
          };
        }).sort((x, y) => x.gw - y.gw);
        setHistory(mapped);
      })
      .catch(err => {
        if (cancelled) return;
        console.error("Failed to fetch player scores:", err);
        setHistory([]);
        setHistoryErr(true);
      });
    return () => { cancelled = true; };
  }, [playerId]);

  if (!playerId) return null;
  const p = playerById(playerId);
  if (!p) return null;
  const t = teamById(p.team);
  const isElim = p.elim || t?.elim;

  const ict = posRankFor(p);

  // Latest scored GW row (for the quick-stat card) + 2-GW form, derived from
  // the SAME real rows the History table shows. Falls back to dashes/0 until
  // the fetch resolves or when no rows exist.
  const scored = (history || []).filter(h => h.mp > 0 || h.pts !== 0);
  const lastRow = scored.length ? scored[scored.length - 1] : null;
  const last2 = scored.slice(-2);
  const form = last2.length
    ? (last2.reduce((sum, h) => sum + (h.pts || 0), 0) / last2.length).toFixed(1)
    : "0.0";

  // Owner: resolve from the all-manager squad map (window.SQUADS_BY_UID,
  // populated by app.jsx) and the real manager team names. The bare lexical
  // MY_SQUAD_IDS / hardcoded team name are static demo data — prefer the
  // window-loaded values so real ownership shows for every manager, not just ME.
  const managers = window.MANAGERS || MANAGERS;
  const squadsByUid = window.SQUADS_BY_UID || {};
  const mySquadIds = window.MY_SQUAD_IDS || MY_SQUAD_IDS;
  let owner = null;
  const ownerUid = Object.keys(squadsByUid).find(
    uid => (squadsByUid[uid] || []).map(String).includes(String(p.id))
  );
  if (ownerUid) {
    const m = managers.find(mm => mm.uid === ownerUid);
    const teamName = (m && (m.team || m.displayName)) || "a manager";
    owner = ownerUid === window.ME ? `${teamName} (you)` : teamName;
  } else if ((mySquadIds || []).map(String).includes(String(p.id))) {
    const me = managers.find(mm => mm.uid === window.ME);
    owner = `${(me && (me.team || me.displayName)) || "your squad"} (you)`;
  }

  return (
    <div className="modal-backdrop" onClick={() => setPlayerId(null)}>
      <div className="modal player-modal" onClick={e => e.stopPropagation()}>
        <button className="modal__close" onClick={() => setPlayerId(null)}>×</button>

        {/* Header — gradient with player ID */}
        <div className="player-modal__head">
          <div className="player-modal__photo">
            <div style={{ width: 96, height: 96, background: "var(--cream)", borderRadius: 8, padding: 4 }}>
              <Jersey team={t} pos={p.pos} />
            </div>
          </div>
          <div className="player-modal__id">
            <span className={`pill pill--dark ${isElim ? "pill--red" : ""}`} style={{ background: isElim ? "var(--red-500)" : "var(--navy-900)" }}>
              {POS_NAMES[p.pos] === "GK" ? "Goalkeeper" : POS_NAMES[p.pos] === "DEF" ? "Defender" : POS_NAMES[p.pos] === "MID" ? "Midfielder" : "Forward"}
            </span>
            <div className="player-modal__name">{p.name}</div>
            <div className="player-modal__team">
              <Flag team={t} size="lg" /> <span>{t.name}</span>
              <span style={{ marginLeft: 8, color: "rgba(255,255,255,0.55)", fontSize: 13 }}>· Group {t.grp}</span>
              {isElim && <span className="pill pill--red" style={{ marginLeft: 8 }}>Nation eliminated</span>}
            </div>
            {owner && (
              <div style={{ marginTop: 8, fontSize: 12, color: "rgba(255,255,255,0.65)" }}>
                <span className="dot dot--gold" style={{ marginRight: 6 }} /> Owned by {owner}
              </div>
            )}
          </div>
        </div>

        {/* Quick stats row */}
        <div className="player-modal__stats">
          <StatCard label="Form" value={form} sub="(2 GW avg)" />
          <StatCard label={lastRow ? `GW${lastRow.gw}` : "Latest"} value={lastRow ? `${lastRow.pts}pts` : "0pts"} sub={lastRow ? lastRow.opp : "—"} />
          <StatCard label="Total" value={`${p.pts}pts`} sub="all season" />
          <StatCard label="Draft rank" value={`#${p.dr}`} sub={`of ${(window.PLAYERS || PLAYERS).length}`} />
          <StatCard label="Status" value={owner ? "Owned" : "Free agent"} sub={owner ? "in this league" : "available"} />
        </div>

        {/* Points rank — real fantasy-points ranking (no fabricated ICT) */}
        <div className="player-modal__ict">
          <div className="player-modal__ict-section">
            <div className="player-modal__ict-title">Points Rank for {POS_NAMES[p.pos] === "GK" ? "Goalkeepers" : POS_NAMES[p.pos] === "DEF" ? "Defenders" : POS_NAMES[p.pos] === "MID" ? "Midfielders" : "Forwards"}</div>
            <div className="player-modal__ict-row">
              <ICTCell label="By position" rank={ict.posRank} total={ict.totalPos} large />
            </div>
          </div>
          <div className="player-modal__ict-section">
            <div className="player-modal__ict-title">Overall Points Rank</div>
            <div className="player-modal__ict-row">
              <ICTCell label="All players" rank={ict.overallRank} total={(window.PLAYERS || PLAYERS).length} large />
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="player-modal__tabs">
          <button className={tab === "history" ? "is-active" : ""} onClick={() => setTab("history")}>History</button>
          <button className={tab === "fixtures" ? "is-active" : ""} onClick={() => setTab("fixtures")}>Fixtures</button>
          <button className={tab === "compare" ? "is-active" : ""} onClick={() => setTab("compare")}>Compare</button>
        </div>

        <div className="player-modal__body">
          {tab === "history" && <HistoryTab history={history} error={historyErr} />}
          {tab === "fixtures" && <FixturesTab fixtures={fixturesFor(p, t)} />}
          {tab === "compare" && <CompareTab player={p} />}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub }) {
  return (
    <div className="player-modal__stat">
      <div className="player-modal__stat-label">{label}</div>
      <div className="player-modal__stat-value">{value}</div>
      <div className="player-modal__stat-sub">{sub}</div>
    </div>
  );
}

function ICTCell({ label, rank, total, large }) {
  return (
    <div className="player-modal__ict-cell">
      <div className="player-modal__ict-label">{label}</div>
      <div className="player-modal__ict-value" style={{ fontSize: large ? 22 : 17 }}>
        <strong>{rank}</strong> <span>of {total}</span>
      </div>
    </div>
  );
}

function HistoryTab({ history, error }) {
  // Loading: fetch in flight (history === null).
  if (history == null) {
    return (
      <div style={{ padding: "30px 16px", textAlign: "center", background: "var(--cream)", borderRadius: 8, color: "var(--ink-500)", fontSize: 13 }}>
        Loading match history…
      </div>
    );
  }
  // No scored rows yet (empty season) or a failed fetch: show the informational
  // message rather than fabricating rows.
  if (!history.length) {
    return (
      <div style={{ padding: "30px 16px", textAlign: "center", background: "var(--cream)", borderRadius: 8 }}>
        <div style={{ fontWeight: 700, color: "var(--navy-900)" }}>No match data yet</div>
        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          {error ? "Couldn't load this player's match history. Try again shortly." : "Live per-match breakdown available once the World Cup begins."}
        </div>
      </div>
    );
  }
  return (
    <div className="table-scroll">
      <table className="table-clean" style={{ fontSize: 13, width: "100%" }}>
        <thead>
          <tr style={{ background: "var(--cream)" }}>
            <th style={{ padding: "8px 10px", textAlign: "left" }}>GW</th>
            <th style={{ padding: "8px 10px", textAlign: "left" }}>Opponent</th>
            <th style={{ padding: "8px 10px", textAlign: "left" }}>Round</th>
            <th style={{ padding: "8px 8px", textAlign: "right" }}>MIN</th>
            <th style={{ padding: "8px 8px", textAlign: "right" }}>GS</th>
            <th style={{ padding: "8px 8px", textAlign: "right" }}>A</th>
            <th style={{ padding: "8px 8px", textAlign: "right" }}>CS</th>
            <th style={{ padding: "8px 8px", textAlign: "right" }}>GC</th>
            <th style={{ padding: "8px 8px", textAlign: "right" }}>YC</th>
            <th style={{ padding: "8px 8px", textAlign: "right" }}>S</th>
            <th style={{ padding: "8px 8px", textAlign: "right" }} title="Defensive contribution: tackles + interceptions + clearances + blocks">DEF</th>
            <th style={{ padding: "8px 8px", textAlign: "right", fontWeight: 800 }}>PTS</th>
          </tr>
        </thead>
        <tbody>
          {history.map(h => (
            <tr key={h.gw} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ padding: "10px 10px", fontWeight: 700 }}>GW{h.gw}</td>
              <td style={{ padding: "10px 10px" }}>{h.opp}</td>
              <td style={{ padding: "10px 10px" }}><span className="pill pill--dark" style={{ fontSize: 10 }}>{h.round}</span></td>
              <td className="num" style={{ padding: "10px 8px", textAlign: "right" }}>{h.mp || "—"}</td>
              <td className="num" style={{ padding: "10px 8px", textAlign: "right" }}>{h.gs}</td>
              <td className="num" style={{ padding: "10px 8px", textAlign: "right" }}>{h.a}</td>
              <td className="num" style={{ padding: "10px 8px", textAlign: "right" }}>{h.cs ? "✓" : "—"}</td>
              <td className="num" style={{ padding: "10px 8px", textAlign: "right", color: h.gc > 0 ? "var(--red-500)" : undefined }}>{h.gc || "—"}</td>
              <td className="num" style={{ padding: "10px 8px", textAlign: "right", color: h.yc ? "var(--gold-500)" : undefined }}>{h.yc ? "1" : "—"}</td>
              <td className="num" style={{ padding: "10px 8px", textAlign: "right" }}>{h.s || "—"}</td>
              <td className="num" style={{ padding: "10px 8px", textAlign: "right", fontWeight: 700 }}>{h.defc || "—"}</td>
              <td className="num" style={{ padding: "10px 8px", textAlign: "right", fontWeight: 800, color: h.pts > 0 ? "var(--navy-900)" : "var(--ink-300)", fontSize: 15 }}>{h.pts}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ padding: "10px 14px", background: "var(--cream)", borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--ink-500)" }}>
        DEF = defensive contribution (tackles + interceptions + clearances + blocks). PTS = FIFA match points + your league's DefCon bonus.
      </div>
      {history.filter(h => (h.breakdown || []).length).map(h => (
        <div key={`bd${h.gw}`} style={{ marginTop: 14, border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
          <div style={{ background: "var(--navy-900)", color: "white", padding: "10px 14px", fontWeight: 700, fontSize: 13, display: "flex", justifyContent: "space-between" }}>
            <span>GW{h.gw} · how the {h.pts} points were scored</span>
            <span>vs {h.opp}</span>
          </div>
          {h.breakdown.map((ln, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "9px 14px", borderTop: i ? "1px solid var(--border)" : "none", fontSize: 13 }}>
              <span style={{ color: "var(--ink-700)" }}>{ln.label}{ln.value != null ? <span className="muted" style={{ marginLeft: 6 }}>({ln.value})</span> : null}</span>
              <span className="num" style={{ fontWeight: 800, color: ln.pts > 0 ? "var(--green-600, #1a9d5a)" : (ln.pts < 0 ? "var(--red-500)" : "var(--ink-300)") }}>{ln.pts > 0 ? `+${ln.pts}` : ln.pts}</span>
            </div>
          ))}
          <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 14px", borderTop: "2px solid var(--navy-900)", fontWeight: 800, background: "var(--cream)" }}>
            <span>Total</span><span className="num">{h.pts}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function FixturesTab({ fixtures }) {
  const diffColor = d => d >= 5 ? "var(--red-500)" : d >= 4 ? "var(--hot-500)" : d >= 3 ? "var(--gold-500)" : "var(--green-500)";
  const diffLabel = d => d >= 5 ? "Very Hard" : d >= 4 ? "Hard" : d >= 3 ? "Medium" : "Easy";
  return (
    <div className="table-scroll">
      <table className="table-clean" style={{ fontSize: 13, width: "100%" }}>
        <thead>
          <tr style={{ background: "var(--cream)" }}>
            <th style={{ padding: "8px 10px" }}>GW</th>
            <th style={{ padding: "8px 10px" }}>Date</th>
            <th style={{ padding: "8px 10px" }}>Round</th>
            <th style={{ padding: "8px 10px" }}>Opponent</th>
            <th style={{ padding: "8px 10px" }}>Venue</th>
            <th style={{ padding: "8px 10px", textAlign: "right" }}>FDR</th>
          </tr>
        </thead>
        <tbody>
          {fixtures.map((f, i) => (
            <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ padding: "10px 10px", fontWeight: 700 }}>{f.gw !== "—" ? `GW${f.gw}` : "—"}</td>
              <td style={{ padding: "10px 10px", color: "var(--ink-500)", fontSize: 12 }}>{f.date}</td>
              <td style={{ padding: "10px 10px" }}><span className="pill pill--dark" style={{ fontSize: 10 }}>{f.round}</span></td>
              <td style={{ padding: "10px 10px", fontWeight: 600 }}>{f.opp}</td>
              <td style={{ padding: "10px 10px", fontSize: 12, color: "var(--ink-500)" }}>{f.venue}</td>
              <td style={{ padding: "10px 10px", textAlign: "right" }}>
                <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700, background: diffColor(f.diff) + "22", color: diffColor(f.diff) }}>
                  {f.diff} · {diffLabel(f.diff)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ padding: "10px 14px", background: "var(--cream)", borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--ink-500)" }}>
        FDR = Fixture Difficulty Rating (1 easy → 5 very hard). Knockout opponents confirmed as the bracket fills.
      </div>
    </div>
  );
}

function CompareTab({ player }) {
  return (
    <div style={{ padding: "30px 16px", textAlign: "center", background: "var(--cream)", borderRadius: 8 }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>⚔️</div>
      <div style={{ fontWeight: 700, color: "var(--navy-900)" }}>Comparison Coming Soon</div>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Player comparison tool will be activated when live scoring starts.</div>
    </div>
  );
}


// ---------- Upcoming-fixture schedule (tournament calendar, not stats) ----------
// GW1–3 come from the REAL group-stage schedule (GROUP_OPPONENTS, built in
// screens-draft.jsx from the 72-fixture calendar). Knockout rows are the real
// WC26 calendar with TBD opponents until the bracket fills. Group GWs the
// league has already played are dropped — the History tab covers those.
function fixturesFor(p, t) {
  if (!t || t.elim) return [
    { gw: "—", date: "—", round: "OUT", opp: "—", home: true, venue: "—", diff: 5 },
  ];
  const GW_DATES = { 1: "11–17 Jun", 2: "18–23 Jun", 3: "24–27 Jun" };
  // FDR by opponent tier (no per-team strength feed yet): contenders 4, solid 3, rest 2.
  const TIER1 = new Set(["FRA", "BRA", "ARG", "ENG", "SPA", "GER", "POR", "NED"]);
  const TIER2 = new Set(["URU", "CRO", "COL", "BEL", "MEX", "USA", "SWI", "MOR", "JAP", "KOR", "SEN", "ECU", "AUT", "TUR"]);
  const diffFor = iso => TIER1.has(iso) ? 4 : TIER2.has(iso) ? 3 : 2;
  const groupOpps =
    (typeof GROUP_OPPONENTS !== "undefined" && GROUP_OPPONENTS[p.team]) ||
    (window.GROUP_OPPONENTS && window.GROUP_OPPONENTS[p.team]) || [];
  const currentGw = (window.TOURNAMENT && window.TOURNAMENT.currentGw) || 1;
  const rows = [];
  [1, 2, 3].forEach(gw => {
    if (gw < currentGw) return;
    const opp = groupOpps[gw - 1] || "TBD";
    rows.push({ gw, date: GW_DATES[gw], round: `Group ${t.grp}`, opp, home: true, venue: "Group stage", diff: diffFor(opp) });
  });
  rows.push(
    { gw: 4, date: "28 Jun – 3 Jul", round: "R32",   opp: "TBD", home: true,  venue: "TBD",    diff: 3 },
    { gw: 5, date: "4–7 Jul",        round: "R16",   opp: "TBD", home: true,  venue: "TBD",    diff: 3 },
    { gw: 6, date: "9–11 Jul",       round: "QF",    opp: "TBD", home: false, venue: "TBD",    diff: 4 },
    { gw: 7, date: "14–15 Jul",      round: "SF",    opp: "TBD", home: true,  venue: "TBD",    diff: 4 },
    { gw: 8, date: "Sun 19 Jul",     round: "FINAL", opp: "TBD", home: true,  venue: "NJ/NYC", diff: 5 },
  );
  return rows;
}

// Position/overall RANK derived from REAL season points (p.pts). This computes
// ordinal ranks from the loaded player totals — it does not fabricate stats.
function posRankFor(p) {
  // Rank: higher pts → better rank
  const activePlayers = window.PLAYERS || PLAYERS;
  const posPeers = activePlayers.filter(x => x.pos === p.pos);
  const allRanked = [...posPeers].sort((a, b) => b.pts - a.pts);
  const rank = allRanked.findIndex(x => x.id === p.id) + 1;
  const totalPos = posPeers.length;
  const overallSorted = [...activePlayers].sort((a, b) => b.pts - a.pts);
  const overall = overallSorted.findIndex(x => x.id === p.id) + 1;

  // The backend exposes no per-component ICT data, so we only return the REAL
  // fantasy-points rank (within position and overall). The modal renders these
  // as "Points Rank" rather than fabricating influence/creativity/threat.
  return {
    posRank: rank,
    overallRank: overall,
    totalPos,
  };
}

Object.assign(window, { PlayerStatsModal });
