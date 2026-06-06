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
          <StatCard label="Owned in" value={owner ? "1/10" : "0/10"} sub="leagues" />
        </div>

        {/* ICT */}
        <div className="player-modal__ict">
          <div className="player-modal__ict-section">
            <div className="player-modal__ict-title">ICT Rank for {POS_NAMES[p.pos] === "GK" ? "Goalkeepers" : POS_NAMES[p.pos] === "DEF" ? "Defenders" : POS_NAMES[p.pos] === "MID" ? "Midfielders" : "Forwards"}</div>
            <div className="player-modal__ict-row">
              <ICTCell label="Influence" rank={ict.influence} total={ict.totalPos} />
              <ICTCell label="Creativity" rank={ict.creativity} total={ict.totalPos} />
              <ICTCell label="Threat" rank={ict.threat} total={ict.totalPos} />
              <ICTCell label="ICT Index" rank={ict.ictPos} total={ict.totalPos} />
            </div>
          </div>
          <div className="player-modal__ict-section">
            <div className="player-modal__ict-title">Overall ICT Rank</div>
            <div className="player-modal__ict-row">
              <ICTCell label="ICT Index" rank={ict.ictOverall} total={(window.PLAYERS || PLAYERS).length} large />
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
    <div style={{ overflowX: "auto" }}>
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
            <th style={{ padding: "8px 8px", textAlign: "right" }}>B</th>
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
              <td className="num" style={{ padding: "10px 8px", textAlign: "right", color: h.b > 0 ? "var(--green-500)" : undefined }}>{h.b || "—"}</td>
              <td className="num" style={{ padding: "10px 8px", textAlign: "right", fontWeight: 800, color: h.pts > 0 ? "var(--navy-900)" : "var(--ink-300)", fontSize: 15 }}>{h.pts}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ padding: "10px 14px", background: "var(--cream)", borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--ink-500)" }}>
        Per-match breakdown. PTS includes bonus and reflects the official scoring engine.
      </div>
    </div>
  );
}

function FixturesTab({ fixtures }) {
  const diffColor = d => d >= 5 ? "var(--red-500)" : d >= 4 ? "var(--hot-500)" : d >= 3 ? "var(--gold-500)" : "var(--green-500)";
  const diffLabel = d => d >= 5 ? "Very Hard" : d >= 4 ? "Hard" : d >= 3 ? "Medium" : "Easy";
  return (
    <div style={{ overflowX: "auto" }}>
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
        FDR = Fixture Difficulty Rating (1 easy → 5 very hard). Fixtures confirmed after group stage draw.
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
// NOTE: this is the static knockout-stage CALENDAR, not fabricated player stats.
// There is no per-player fixture endpoint loaded by the frontend yet; the
// History tab's per-match scoring is now fetched from /players/{id}/scores.
function fixturesFor(p, t) {
  if (!t || t.elim) return [
    { gw: "—", date: "—", round: "OUT", opp: "—", home: true, venue: "—", diff: 5 },
  ];
  const koOpponents = { BRA: "USA", ARG: "ECU", FRA: "POR2", ENG: "URU", ESP: "JPN", GER: "MEX2", NED: "EGY", POR: "FRA", BEL: "AUS", COL: "KOR", USA: "BRA", KOR: "COL" };
  const opp = koOpponents[p.team];
  if (!opp) return [{ gw: 4, date: "Jul 1–4", round: "R32", opp: "TBD", home: true, venue: "TBD", diff: 3 }];
  return [
    { gw: 4, date: "Wed 1 Jul", round: "R32", opp, home: true, venue: "Mexico City", diff: 2 },
    { gw: 5, date: "Sun 5 Jul", round: "R16", opp: "TBD", home: true, venue: "TBD",         diff: 3 },
    { gw: 6, date: "Sat 11 Jul", round: "QF",  opp: "TBD", home: false, venue: "TBD",       diff: 4 },
    { gw: 7, date: "Wed 15 Jul", round: "SF",  opp: "TBD", home: true, venue: "TBD",        diff: 4 },
    { gw: 8, date: "Sun 19 Jul", round: "FINAL", opp: "TBD", home: true, venue: "NJ/NYC",   diff: 5 },
  ];
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

  // ICT component cells are display-only ordinal offsets from the points rank
  // (the backend exposes no per-component ICT data); they are not scoring stats.
  return {
    influence: Math.max(1, rank - 2),
    creativity: rank + 1,
    threat: Math.max(1, rank - 1),
    ictPos: rank,
    ictOverall: overall,
    totalPos,
  };
}

Object.assign(window, { PlayerStatsModal });
