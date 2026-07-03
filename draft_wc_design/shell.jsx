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
  { id: "audit",      label: "Scoring Audit" },
  { id: "create",     label: "Leagues" },
  { id: "config",     label: "Rules Config" },
];

function useTopBar() {
  const displayName = window._auth?.currentUser?.displayName || "Me";
  const initials = displayName.split(" ").map(w => w[0]).join("").substring(0, 2).toUpperCase();
  // 4-state banner — reactive: re-reads window.__DATA_SOURCE__ whenever the app
  // updates it (fires a "wc-datasource" event). Cold start is "loading", a
  // NEUTRAL state: the old default was "down", which accused the backend of
  // being unreachable before the first request had even been sent — every
  // page load flashed a red "DEMO DATA" chip at the users. "down" now renders
  // only when the bootstrap EXPLICITLY concludes the backend failed.
  const [dataSource, setDataSourceState] = React.useState(window.__DATA_SOURCE__ || "loading");
  React.useEffect(() => {
    const sync = () => setDataSourceState(window.__DATA_SOURCE__ || "loading");
    window.addEventListener("wc-datasource", sync);
    sync(); // catch a value set before this listener attached
    return () => window.removeEventListener("wc-datasource", sync);
  }, []);
  let bannerBg = "#c52836"; // dark red
  let bannerText = "⚠️ DEMO DATA — backend not reached";
  if (dataSource === "loading") {
    bannerBg = "rgba(255,255,255,0.16)";
    bannerText = "⏳ Loading live data…";
  } else if (dataSource === "simulated") {
    bannerBg = "#4a1ba8"; // deep purple
    bannerText = "📊 Simulated Data Mode";
  } else if (dataSource === "live") {
    bannerBg = "#10b981"; // emerald green
    bannerText = "🟢 Live Production Data";
  }
  return { displayName, initials, bannerBg, bannerText };
}

function TopBar({ tweak }) {
  const { displayName, initials, bannerBg, bannerText } = useTopBar();
  return (
    <div className="topbar">
      <Logo />
      <div style={{ marginLeft: 16, padding: "4px 10px", borderRadius: 4, background: bannerBg, color: "white", fontSize: 11, fontWeight: 700 }}>
        {bannerText}
      </div>
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
          <span><strong>GW{TOURNAMENT.currentGw}</strong> · {(TOURNAMENT.gwDates && TOURNAMENT.gwDates[TOURNAMENT.currentGw]) ? TOURNAMENT.gwDates[TOURNAMENT.currentGw].wcRound : "GW"}</span>
        </div>
        <span style={{ width: 1, height: 14, background: "var(--border)" }} />
        <span>{displayName}</span>
        <span style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--grad-hero)", display: "inline-flex", alignItems: "center", justifyContent: "center", color: "white", fontWeight: 700, fontSize: 12 }}>{initials || "ME"}</span>
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

const CHANGE_PW_STYLES = {
  overlay: { position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 },
  card: { background: "var(--surface, #1a1738)", color: "white", padding: 24, borderRadius: 12, width: 360, boxShadow: "0 12px 40px rgba(0,0,0,0.4)" },
  input: { width: "100%", padding: "8px 10px", marginTop: 6, borderRadius: 6, border: "1px solid rgba(255,255,255,0.18)", background: "rgba(255,255,255,0.06)", color: "white", fontSize: 13, boxSizing: "border-box" },
  label: { display: "block", marginTop: 12, fontSize: 12, color: "rgba(255,255,255,0.7)" },
  btnSecondary: { padding: "8px 14px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.2)", background: "transparent", color: "white", cursor: "pointer" },
};

function useChangePasswordModal({ onClose }) {
  const [currentPw, setCurrentPw] = React.useState("");
  const [newPw, setNewPw] = React.useState("");
  const [confirmPw, setConfirmPw] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const [done, setDone] = React.useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (newPw.length < 6) { setErr("New password must be at least 6 characters."); return; }
    if (newPw !== confirmPw) { setErr("New passwords don't match."); return; }
    const user = window._auth?.currentUser;
    if (!user) { setErr("Not signed in."); return; }
    setBusy(true);
    try {
      const cred = firebase.auth.EmailAuthProvider.credential(user.email, currentPw);
      await user.reauthenticateWithCredential(cred);
      await user.updatePassword(newPw);
      setDone(true);
    } catch (e) {
      setErr(e.message || "Failed to change password.");
    } finally {
      setBusy(false);
    }
  };

  const btnPrimary = { padding: "8px 14px", borderRadius: 6, border: "none", background: "var(--grad-hero, #4c1d95)", color: "white", fontWeight: 700, cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.6 : 1 };

  return { currentPw, setCurrentPw, newPw, setNewPw, confirmPw, setConfirmPw, busy, err, done, submit, btnPrimary };
}

function ChangePasswordModal({ onClose }) {
  const { currentPw, setCurrentPw, newPw, setNewPw, confirmPw, setConfirmPw, busy, err, done, submit, btnPrimary } = useChangePasswordModal({ onClose });
  const { overlay: overlayStyle, card: cardStyle, input: inputStyle, label: labelStyle, btnSecondary } = CHANGE_PW_STYLES;

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={cardStyle} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Change password</h3>
        {done ? (
          <div>
            <p style={{ marginTop: 14, fontSize: 13 }}>✅ Password updated. You'll use the new one next sign-in.</p>
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
              <button style={btnPrimary} onClick={onClose}>Close</button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit}>
            <label style={labelStyle}>Current password
              <input type="password" autoFocus value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} style={inputStyle} disabled={busy} />
            </label>
            <label style={labelStyle}>New password
              <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} style={inputStyle} disabled={busy} />
            </label>
            <label style={labelStyle}>Confirm new password
              <input type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} style={inputStyle} disabled={busy} />
            </label>
            {err && <div style={{ marginTop: 12, fontSize: 12, color: "#ff8a8a" }}>{err}</div>}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
              <button type="button" style={btnSecondary} onClick={onClose} disabled={busy}>Cancel</button>
              <button type="submit" style={btnPrimary} disabled={busy}>{busy ? "Saving…" : "Update"}</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function useSubNav() {
  const [pwOpen, setPwOpen] = React.useState(false);
  return { pwOpen, setPwOpen };
}

function SubNav({ tab, onTab }) {
  const { pwOpen, setPwOpen } = useSubNav();
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
      <button
        className="subnav__tab"
        style={{ color: "rgba(255,255,255,0.78)" }}
        onClick={() => setPwOpen(true)}
      >
        Change Password
      </button>
      <button
        className="subnav__tab"
        style={{ color: "rgba(255,255,255,0.78)" }}
        onClick={() => window._auth && window._auth.signOut()}
      >
        Sign Out
      </button>
      {pwOpen && <ChangePasswordModal onClose={() => setPwOpen(false)} />}
    </div>
  );
}

// ---------- MobileNav (bottom tab bar, mobile only) ----------
const MOBILE_PRIMARY_TABS = [
  { id: "status",    icon: "⚡" },
  { id: "points",    icon: "📊" },
  { id: "pickteam",  icon: "⚽" },
  { id: "transfers", icon: "🔁" },
  { id: "league",    icon: "🏆" },
];

function useMobileNav({ tab, onTab }) {
  const isMobile = useIsMobile();
  const [moreOpen, setMoreOpen] = React.useState(false);
  const primaryIds = MOBILE_PRIMARY_TABS.map(t => t.id);
  const moreTabs = TABS.filter(t =>
    !primaryIds.includes(t.id) && (t.id !== "config" || window.IS_ADMIN)
  );
  const moreActive = moreTabs.some(t => t.id === tab);
  const pick = (id) => { onTab(id); setMoreOpen(false); };
  return { isMobile, moreOpen, setMoreOpen, moreTabs, moreActive, pick };
}

function MobileNav({ tab, onTab }) {
  const { isMobile, moreOpen, setMoreOpen, moreTabs, moreActive, pick } = useMobileNav({ tab, onTab });
  if (!isMobile) return null;
  return (
    <React.Fragment>
      {moreOpen && <div className="mobilenav-backdrop" onClick={() => setMoreOpen(false)} />}
      {moreOpen && (
        <div className="mobilenav-sheet">
          {moreTabs.map(t => (
            <button
              key={t.id}
              className={"mobilenav-sheet__item " + (tab === t.id ? "is-active" : "")}
              onClick={() => pick(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}
      <nav className="mobilenav">
        {MOBILE_PRIMARY_TABS.map(t => {
          const meta = TABS.find(x => x.id === t.id) || { label: t.id };
          return (
            <button
              key={t.id}
              className={"mobilenav__slot " + (tab === t.id && !moreOpen ? "is-active" : "")}
              onClick={() => pick(t.id)}
            >
              <span className="mobilenav__icon">{t.icon}</span>
              <span className="mobilenav__label">{meta.label}</span>
            </button>
          );
        })}
        <button
          className={"mobilenav__slot " + (moreOpen || moreActive ? "is-active" : "")}
          onClick={() => setMoreOpen(o => !o)}
        >
          <span className="mobilenav__icon">☰</span>
          <span className="mobilenav__label">More</span>
        </button>
      </nav>
    </React.Fragment>
  );
}

// ---------- Sidebar (right) ----------
function Sidebar({ onTab }) {
  const me = managerById(window.ME) || { name: "Manager", team: "My Team", flag: "GER", waiverPri: 99 };
  const myTeam = teamById(me.flag) || teamById("GER");
  const myStanding = (window.STANDINGS || STANDINGS).find(s => s.uid === window.ME) || { rank: "—", fpts: "—", hpts: "—" };

  // count eliminated players in squad
  const elimCount = MY_SQUAD_IDS.filter(id => {
    const p = playerById(id);
    return p && (p.elim || teamById(p.team)?.elim);
  }).length;

  const currentGw = TOURNAMENT.currentGw;
  const gwPoints = window.GW_TOTALS && window.GW_TOTALS[window.ME] !== undefined ? window.GW_TOTALS[window.ME] : "—";
  
  const activeWindow = window.WINDOW || WINDOW;
  const favTeam = teamById(me.flag) || teamById("GER");
  const hasLeague = LEAGUE && LEAGUE.inviteCode;

  return (
    <aside className="col" style={{ gap: 16 }}>
      {/* Identity card */}
      <div className="card-dark">
        <div style={{ padding: "16px 18px", display: "flex", alignItems: "center", gap: 12 }}>
          <ManagerFlag uid={window.ME} size="xl" fallback={myTeam} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>{me.name.replace(" (you)", "")}</div>
            <div className="muted" style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>{me.team}</div>
          </div>
        </div>
        <div style={{ background: "var(--gold-500)", color: "var(--navy-900)", padding: "6px 18px", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          {hasLeague ? `Seed #${me.draftPos || "—"} · ${LEAGUE.knockoutStartGw <= currentGw ? "Knockout" : "Group Phase"}` : "—"}
        </div>
        <div className="card-section">
          <Stat label={`GW${currentGw} Points`} value={String(gwPoints)} />
          <Stat label="Total Points" value={String(myStanding.fpts)} />
          <Stat label="League Rank" value={hasLeague ? `#${myStanding.rank} / ${LEAGUE.size}` : "—"} accent="var(--gold-500)" />
        </div>
      </div>

      {/* Favourite nation */}
      <div className="card" style={{ padding: "14px 16px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-500)" }}>Favourite Nation</div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
          <Flag team={favTeam} size="lg" />
          <div>
            <div style={{ fontWeight: 700 }}>{favTeam.name}</div>
            <div className="muted" style={{ fontSize: 12 }}>Group {favTeam.grp || "—"} · {favTeam.elim ? "Eliminated" : "Active"}</div>
          </div>
        </div>
      </div>

      {/* Window status */}
      <div className="card-dark">
        <div className="card-dark__title">Transfer Window</div>
        <div className="card-section">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span className="pill pill--gold">{windowPhaseMeta(activeWindow.phase).label}</span>
          </div>
          <div style={{ fontSize: 12, opacity: 0.85, lineHeight: 1.5 }}>
            {activeWindow.phaseEndsAt ? (
              <>
                Closes {fmtWindowTime(activeWindow.phaseEndsAt)}<br />
                <strong><Countdown to={activeWindow.phaseEndsAt} suffix=" remaining" /></strong>
              </>
            ) : (
              <>{windowPhaseMeta(activeWindow.phase).hint}</>
            )}
            {activeWindow.nextPhase && activeWindow.nextPhaseStartsAt && (
              <div style={{ marginTop: 6, opacity: 0.75 }}>
                Next: {windowPhaseMeta(activeWindow.nextPhase).label} · {fmtWindowTime(activeWindow.nextPhaseStartsAt)}
              </div>
            )}
          </div>
          <div style={{ marginTop: 10 }}>
            <Stat label="Free transfers" value="∞" accent="var(--green-400)" />
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
            <div style={{ fontSize: 12 }}>Drop them before GW4 lock.</div>
          </div>
        </div>
      )}

      {/* Admin */}
      <div className="card" style={{ padding: "14px 16px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-500)", marginBottom: 8 }}>League Admin</div>
        <button className="muted" style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 0", fontSize: 13 }}>Team Details →</button>
        <button className="muted" style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 0", fontSize: 13 }}>Edit League →</button>
        <button className="muted" style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 0", fontSize: 13 }}>Invite Code · {LEAGUE?.inviteCode || "—"}</button>
      </div>
    </aside>
  );
}

Object.assign(window, { TABS, TopBar, Hero, SubNav, Sidebar, MobileNav });
