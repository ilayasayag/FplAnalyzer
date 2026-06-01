// =====================================================================
// WC26 — Player Stats Modal
// Opens on dispatchEvent('show-player-stats', { detail: { id }})
// =====================================================================

function PlayerStatsModal() {
  const [playerId, setPlayerId] = React.useState(null);
  const [tab, setTab] = React.useState("history");

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

  if (!playerId) return null;
  const p = playerById(playerId);
  if (!p) return null;
  const t = teamById(p.team);
  const isElim = p.elim || t?.elim;

  // Synthesized GW history (3 group games + scheduled R32)
  const history = synthHistory(p);
  const fixtures = synthFixtures(p, t);
  const ict = synthICT(p);

  // Form = avg of last 2 GWs
  const form = ((p.pts > 0) ? ((history[2].pts + history[1].pts) / 2).toFixed(1) : "0.0");

  // Owner
  const owner = MY_SQUAD_IDS.includes(p.id) ? "Hapoel Eliyahu (you)" : null;

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
          <StatCard label="GW3" value={p.pts > 0 ? `${history[2].pts}pts` : "0pts"} sub={history[2].opp} />
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
          {tab === "history" && <HistoryTab history={history} />}
          {tab === "fixtures" && <FixturesTab fixtures={fixtures} />}
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

function HistoryTab({ history }) {
  return (
    <div style={{ padding: "30px 16px", textAlign: "center", background: "var(--cream)", borderRadius: 8 }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>📊</div>
      <div style={{ fontWeight: 700, color: "var(--navy-900)" }}>Detailed Stats Coming Soon</div>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Live and historical performance data will populate once World Cup matches begin.</div>
    </div>
  );
}

function FixturesTab({ fixtures }) {
  return (
    <div style={{ padding: "30px 16px", textAlign: "center", background: "var(--cream)", borderRadius: 8 }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>📅</div>
      <div style={{ fontWeight: 700, color: "var(--navy-900)" }}>Fixtures Coming Soon</div>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Detailed match schedules will be populated once they are confirmed.</div>
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


// ---------- Synthesizers (deterministic) ----------
function synthHistory(p) {
  const isElim = p.elim || teamById(p.team)?.elim;
  const isGK = p.pos === 1;
  const isDef = p.pos === 2;
  const isMid = p.pos === 3;
  const isFwd = p.pos === 4;

  // Pseudo-rand by player id
  const seed = p.id.split("").reduce((s, c) => s + c.charCodeAt(0), 0);
  const r = (i, mod) => (seed * (i + 1) * 13) % mod;

  const oppMap = {
    BRA: ["AUS", "GHA", "POR"], ARG: ["ITA", "JPN", "EGY"], FRA: ["KSA", "NGA", "CRO"],
    ENG: ["IRN", "ALG", "ECU"],  ESP: ["POL", "TUN", "SEN"], GER: ["JOR", "USA", "BEL"],
    NED: ["CRC", "QAT", "URU"],  POR: ["GHA", "AUS", "BRA"], BEL: ["JOR", "USA", "GER"],
    CRO: ["KSA", "NGA", "FRA"],  USA: ["JOR", "GER", "BEL"], MEX: ["CAN", "MAR", "UZB"],
    ITA: ["EGY", "JPN", "ARG"],  MAR: ["UZB", "CAN", "MEX"], POL: ["TUN", "SEN", "ESP"],
    SEN: ["TUN", "POL", "ESP"],  JPN: ["EGY", "ARG", "ITA"], URU: ["QAT", "CRC", "NED"],
    COL: ["OMA", "CHI", "KOR"],  KOR: ["CHI", "OMA", "COL"], SUI: ["PAR", "CUR", "CMR"],
    DEN: ["NZL", "SCO", "CIV"],  EGY: ["JPN", "ARG", "ITA"],
  };
  const opps = oppMap[p.team] || ["TBD", "TBD", "TBD"];

  return [1, 2, 3].map((gw, i) => {
    const baseScore = isElim && gw === 3 ? 0 : Math.max(0, p.pts / 3 + (r(i, 9) - 4));
    const mp = baseScore > 1 ? (r(i, 4) === 0 ? 60 + r(i, 30) : 90) : 0;
    const gs = isFwd ? r(i, 5) === 0 ? 1 : 0 : (isMid ? r(i, 7) === 0 ? 1 : 0 : 0);
    const a = (isMid || isFwd) ? (r(i, 4) === 0 ? 1 : 0) : 0;
    const cs = (isGK || isDef) && r(i, 3) === 0 && mp >= 60;
    const gc = (isGK || isDef) && !cs ? r(i, 3) : 0;
    const yc = r(i, 6) === 0 ? 1 : 0;
    const s = isGK ? r(i, 8) : 0;
    const pts = Math.round(baseScore);
    const b = pts > 10 ? 3 : pts > 7 ? 2 : pts > 5 ? 1 : 0;
    const bps = pts * 3 + r(i, 8);
    return {
      gw, opp: `${opps[i] || "TBD"} ${i % 2 ? "(A)" : "(H)"}`,
      round: `Group ${["A","B","C","D","E","F","G","H","I","J","K","L"][i] || "·"}`,
      pts, mp, gs, a, cs, gc, og: 0, ps: 0, pm: 0, yc, rc: 0, s, b, bps,
    };
  });
}

function synthFixtures(p, t) {
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

function synthICT(p) {
  // Synthesize ranks: higher pts → better rank
  const activePlayers = window.PLAYERS || PLAYERS;
  const posPeers = activePlayers.filter(x => x.pos === p.pos);
  const allRanked = [...posPeers].sort((a, b) => b.pts - a.pts);
  const rank = allRanked.findIndex(x => x.id === p.id) + 1;
  const totalPos = posPeers.length;
  const overallSorted = [...activePlayers].sort((a, b) => b.pts - a.pts);
  const overall = overallSorted.findIndex(x => x.id === p.id) + 1;

  // Slight scatter for individual ICT components
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
