// =====================================================================
// WC26 — Shell: TopBar, Hero, SubNav, Sidebar
// =====================================================================

const TABS = [
  { id: "status",     label: "Status" },
  { id: "points",     label: "Points" },
  { id: "pickteam",   label: "Pick Team" },
  { id: "transfers",  label: "Transfers" },
  { id: "league",     label: "League" },
  { id: "bracket",    label: "Knockout" },
  { id: "fixtures",   label: "Fixtures" },
  { id: "draft",      label: "Draft Room" },
  { id: "players",    label: "Players" },
  { id: "trades",     label: "Trades" },
  { id: "create",     label: "Leagues" },
];

function TopBar({ tweak }) {
  return (
    <div className="topbar">
      <Logo />
      <nav className="topbar__nav" style={{ marginLeft: 8 }}>
        <a href="#" className="is-active">Fantasy WC</a>
        <a href="#" style={{ opacity: 0.55 }}>Matches</a>
        <a href="#" style={{ opacity: 0.55 }}>Groups</a>
        <a href="#" style={{ opacity: 0.55 }}>Players</a>
        <a href="#" style={{ opacity: 0.55 }}>News</a>
      </nav>
      <div className="topbar__right">
        <div className="row">
          <span className="dot dot--green" />
          <span><strong>GW{TOURNAMENT.currentGw}</strong> · {TOURNAMENT.gwDates[TOURNAMENT.currentGw].wcRound}</span>
        </div>
        <span style={{ width: 1, height: 14, background: "var(--border)" }} />
        <span>Ilay Asayag</span>
        <span style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--grad-hero)", display: "inline-flex", alignItems: "center", justifyContent: "center", color: "white", fontWeight: 700, fontSize: 12 }}>IA</span>
      </div>
    </div>
  );
}

function Hero({ tab, manager }) {
  return (
    <div className="hero">
      <div className="hero__wordmark">
        <span className="trophy">
          <svg width="58" height="58" viewBox="0 0 60 60" fill="none">
            <path d="M14 10h32v8a16 16 0 0 1-32 0V10Z" fill="#ffc844" />
            <path d="M6 12h8v6a4 4 0 0 1-4-4 2 2 0 0 1-2-2Zm40 0h8a2 2 0 0 1-2 2 4 4 0 0 1-4 4v-6Z" fill="#ffd56b" />
            <path d="M22 34h16v8H22z" fill="#ffc844" />
            <path d="M16 42h28v6H16z" fill="#ffc844" />
            <path d="M12 48h36v4H12z" fill="#ffd56b" />
            <circle cx="30" cy="16" r="6" fill="#0c0a3e" opacity="0.18" />
            <text x="30" y="20" textAnchor="middle" fill="#fff" fontFamily="Bricolage Grotesque,Inter,sans-serif" fontWeight="800" fontSize="9">26</text>
          </svg>
        </span>
        <span>Fantasy <span className="sub">World Cup</span></span>
      </div>
    </div>
  );
}

function SubNav({ tab, onTab }) {
  return (
    <div className="subnav">
      {TABS.map(t => (
        <button
          key={t.id}
          className={"subnav__tab " + (tab === t.id ? "is-active" : "")}
          onClick={() => onTab(t.id)}
        >
          {t.label}
        </button>
      ))}
      <div style={{ flex: 1 }} />
      <button className="subnav__tab" style={{ color: "rgba(255,255,255,0.78)" }}>Sign Out</button>
    </div>
  );
}

// ---------- Sidebar (right) ----------
function Sidebar({ onTab }) {
  const me = managerById(ME);
  const myTeam = teamById(me.flag);
  const myStanding = STANDINGS.find(s => s.uid === ME);

  // count eliminated players in squad
  const elimCount = MY_SQUAD_IDS.filter(id => {
    const p = playerById(id);
    return p && (p.elim || teamById(p.team)?.elim);
  }).length;

  return (
    <aside className="col" style={{ gap: 16 }}>
      {/* Identity card */}
      <div className="card-dark">
        <div style={{ padding: "16px 18px", display: "flex", alignItems: "center", gap: 12 }}>
          <Flag team={myTeam} size="lg" />
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>{me.name.replace(" (you)", "")}</div>
            <div className="muted" style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>{me.team}</div>
          </div>
        </div>
        <div style={{ background: "var(--gold-500)", color: "var(--navy-900)", padding: "6px 18px", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          Seed #7 · Quarter-Finals
        </div>
        <div className="card-section">
          <Stat label="GW3 Points" value="65" />
          <Stat label="Total Points" value="179" />
          <Stat label="League Rank" value={`#${myStanding.rank} / 10`} accent="var(--gold-500)" />
        </div>
      </div>

      {/* Favourite nation */}
      <div className="card" style={{ padding: "14px 16px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-500)" }}>Favourite Nation</div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
          <Flag team={teamById("POR")} size="lg" />
          <div>
            <div style={{ fontWeight: 700 }}>Portugal</div>
            <div className="muted" style={{ fontSize: 12 }}>Group C · Advanced 2nd</div>
          </div>
        </div>
      </div>

      {/* Window status */}
      <div className="card-dark">
        <div className="card-dark__title">Transfer Window</div>
        <div className="card-section">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span className="pill pill--gold">W{WINDOW.number} · The Big One</span>
          </div>
          <div style={{ fontSize: 12, opacity: 0.85, lineHeight: 1.4 }}>
            Closes {WINDOW.closesAt}<br />
            <strong>{WINDOW.hoursLeft}h remaining</strong>
          </div>
          <div style={{ marginTop: 10 }}>
            <Stat label="Free transfers" value={`${WINDOW.freeTransfers - WINDOW.used}/${WINDOW.freeTransfers}`} accent="var(--green-400)" />
            <Stat label="Waiver priority" value={`#${me.waiverPri}`} />
          </div>
        </div>
        <div className="card-section">
          <button className="btn btn--primary" style={{ width: "100%" }} onClick={() => onTab("transfers")}>
            Manage Transfers →
          </button>
        </div>
      </div>

      {/* Elimination alert */}
      {elimCount > 0 && (
        <div className="alert alert--danger">
          <div className="alert__icon" style={{ background: "var(--red-500)", color: "white" }}>!</div>
          <div>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>{elimCount} dead players in squad</div>
            <div style={{ fontSize: 12 }}>Italy and Morocco are out. Drop them before GW4 lock.</div>
          </div>
        </div>
      )}

      {/* Admin */}
      <div className="card" style={{ padding: "14px 16px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-500)", marginBottom: 8 }}>League Admin</div>
        <button className="muted" style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 0", fontSize: 13 }}>Team Details →</button>
        <button className="muted" style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 0", fontSize: 13 }}>Edit League →</button>
        <button className="muted" style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 0", fontSize: 13 }}>Invite Code · WC26-Q7XN</button>
      </div>
    </aside>
  );
}

Object.assign(window, { TABS, TopBar, Hero, SubNav, Sidebar });
