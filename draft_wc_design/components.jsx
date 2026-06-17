// =====================================================================
// WC26 — Shared components: Flag, Jersey, PlayerSlot, Pitch, GroupChip
// =====================================================================

// ---------- Flag ----------
// Uses flagcdn.com for real national flag images.
// Falls back to coloured bands if no ISO mapping (e.g. for subnational fictional teams).
const FLAG_ISO = {
  MEX: "mx", CAN: "ca", MAR: "ma", UZB: "uz",
  ARG: "ar", JPN: "jp", ITA: "it", EGY: "eg",
  BRA: "br", POR: "pt", GHA: "gh", AUS: "au",
  FRA: "fr", CRO: "hr", NGA: "ng", KSA: "sa",
  ENG: "gb-eng", ECU: "ec", IRN: "ir", ALG: "dz",
  GER: "de", BEL: "be", USA: "us", JOR: "jo",
  ESP: "es", SEN: "sn", POL: "pl", TUN: "tn",
  NED: "nl", URU: "uy", CRC: "cr", QAT: "qa",
  COL: "co", KOR: "kr", CHI: "cl", OMA: "om",
  DEN: "dk", CIV: "ci", SCO: "gb-sct", NZL: "nz",
  SUI: "ch", CMR: "cm", PAR: "py", CUR: "cw",
  POR2: "tr",   // Türkiye (was reused id in mock data)
  MEX2: "pe",   // Peru   (was reused id in mock data)
  VEN: "ve", HAI: "ht",
  // Backend (api-sports) raw ISO codes that differ from the FIFA-style codes
  // above. With the backend-driven team map, team.id is now the raw code, so
  // these map every live nation to a clean flag-icons SVG.
  SPA: "es", JAP: "jp", MOR: "ma", SWI: "ch", IRA: "ir", TUR: "tr",
  AUT: "at", BOS: "ba", COD: "cd", CPV: "cv", CZE: "cz", IRQ: "iq",
  NOR: "no", PAN: "pa", RSA: "za", SAU: "sa", SWE: "se",
};

// ISO codes for which a real kit image exists under kits/<iso>.png.
// Generated from the FIFA WC fantasy squad kits; keyed by the same ISO codes
// that FLAG_ISO maps team.id to, so coverage matches the flags exactly.
const KIT_ISO = new Set([
  "ar", "at", "au", "ba", "be", "br", "ca", "cd", "ch", "ci", "co", "cv",
  "cw", "cz", "de", "dz", "ec", "eg", "es", "fr", "gb-eng", "gb-sct", "gh",
  "hr", "ht", "iq", "ir", "jo", "jp", "kr", "ma", "mx", "nl", "no", "nz",
  "pa", "pt", "py", "qa", "sa", "se", "sn", "tn", "tr", "us", "uy", "uz", "za",
]);

function Flag({ team, size = "sm" }) {
  if (!team) return null;
  const iso = FLAG_ISO[team.id];
  const isLg = size === "lg";
  const cls = "flag" + (isLg ? " flag--lg" : "");
  if (iso) {
    return (
      <span className={cls} title={team.name}>
        <img
          src={`https://cdn.jsdelivr.net/gh/lipis/flag-icons@7.2.3/flags/4x3/${iso}.svg`}
          alt={team.name}
        />
      </span>
    );
  }
  // Backend-provided crest/flag (api-sports) for any nation without a static
  // flag-icons mapping — keeps every one of the 48 teams showing a real flag.
  if (team.logo) {
    return (
      <span className={cls} title={team.name}>
        <img src={team.logo} alt={team.name} style={{ objectFit: "cover" }} />
      </span>
    );
  }
  // Fallback: coloured bands
  if (team.vert) {
    return (
      <span className={cls} style={{ display: "flex" }}>
        {team.vert.map((c, i) => <span key={i} style={{ flex: 1, background: c }} />)}
      </span>
    );
  }
  const colors = team.flag || ["#888", "#888", "#888"];
  return (
    <span className={cls} style={{ display: "flex", flexDirection: "column", position: "relative" }}>
      {colors.map((c, i) => <span key={i} style={{ flex: 1, background: c }} />)}
      {team.dot && (
        <span style={{
          position: "absolute", left: "50%", top: "50%",
          transform: "translate(-50%, -50%)",
          width: "30%", aspectRatio: 1, borderRadius: "50%",
          background: team.dot,
        }} />
      )}
    </span>
  );
}

// ---------- Group chip ----------
function GroupChip({ group }) {
  return (
    <span className="group-chip">
      <span className="group-chip__dot" style={{ background: `var(--grp-${group})` }} />
      Group {group}
    </span>
  );
}

// ---------- Jersey ----------
// A nation-colored shirt SVG, sized to fit a 56×56 box.
// Uses primary flag colour with secondary stripe.
function Jersey({ team, pos = 3, eliminated = false }) {
  if (!team) team = { flag: ["#888", "#888", "#888"] };

  // Real kit image (FIFA WC fantasy renders), keyed by the same ISO code the
  // flag uses. Falls back to the coloured SVG below for any team without a kit.
  const iso = FLAG_ISO[team.id];
  if (iso && KIT_ISO.has(iso)) {
    return (
      <img
        className="jersey-kit"
        src={`kits/${iso}.png`}
        alt={team.name ? `${team.name} kit` : "kit"}
        loading="lazy"
        draggable="false"
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.35))",
        }}
      />
    );
  }

  const colors = team.vert || team.flag || ["#888", "#888", "#888"];
  const primary = colors[0];
  const secondary = colors[1] !== primary ? colors[1] : colors[2];
  const isGK = pos === 1;
  const main = isGK ? "#1be8d4" : primary;
  const accent = isGK ? "#0c0a3e" : secondary;

  return (
    <svg viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`g-${team.id}-${pos}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={main} />
          <stop offset="1" stopColor={main} stopOpacity="0.85" />
        </linearGradient>
      </defs>
      {/* jersey body */}
      <path
        d="M 14 12 L 22 8 L 25 14 L 35 14 L 38 8 L 46 12 L 50 22 L 44 26 L 44 50 Q 44 54 40 54 L 20 54 Q 16 54 16 50 L 16 26 L 10 22 Z"
        fill={`url(#g-${team.id}-${pos})`}
        stroke="rgba(0,0,0,0.18)"
        strokeWidth="0.8"
      />
      {/* vertical accent stripe (mid) */}
      {team.vert ? (
        <rect x="27" y="14" width="6" height="40" fill={accent} opacity="0.85" />
      ) : (
        <rect x="14" y="32" width="32" height="3" fill={accent} opacity="0.6" />
      )}
      {/* collar */}
      <path d="M 25 14 L 30 18 L 35 14 Z" fill="rgba(0,0,0,0.25)" />
      {/* sleeve cuffs */}
      <rect x="10" y="20" width="6" height="3" fill={accent} opacity="0.5" />
      <rect x="44" y="20" width="6" height="3" fill={accent} opacity="0.5" />
    </svg>
  );
}

// ---------- Swap Constraints Helper ----------
function isSwapLegal(lineup, idA, idB) {
  if (idA === idB) return true;

  const isStartingA = lineup.starting.includes(idA);
  const isStartingB = lineup.starting.includes(idB);

  let newStarting = [...lineup.starting];
  let newBench = [...lineup.bench];

  const idxA = (isStartingA ? newStarting : newBench).indexOf(idA);
  const idxB = (isStartingB ? newStarting : newBench).indexOf(idB);

  if (idxA === -1 || idxB === -1) return false;

  // Perform hypothetical swap
  if (isStartingA && isStartingB) {
    [newStarting[idxA], newStarting[idxB]] = [newStarting[idxB], newStarting[idxA]];
  } else if (!isStartingA && !isStartingB) {
    [newBench[idxA], newBench[idxB]] = [newBench[idxB], newBench[idxA]];
  } else {
    const aArr = isStartingA ? newStarting : newBench;
    const bArr = isStartingB ? newStarting : newBench;
    aArr[idxA] = idB;
    bArr[idxB] = idA;
  }

  // 1. Bench[0] must be GK (pos 1)
  const benchGkId = newBench[0];
  const benchGk = playerById(benchGkId);
  if (!benchGk || benchGk.pos !== 1) return false;

  // 2. Starting formation validation
  const countPos = { 1: 0, 2: 0, 3: 0, 4: 0 };
  newStarting.forEach(pId => {
    const p = playerById(pId);
    if (p) {
      countPos[p.pos] = (countPos[p.pos] || 0) + 1;
    }
  });

  const gk = countPos[1];
  const def = countPos[2];
  const mid = countPos[3];
  const fwd = countPos[4];

  const formationKey = `${gk}-${def}-${mid}-${fwd}`;
  const VALID_FORMATIONS = [
    "1-3-5-2", "1-3-4-3", "1-4-5-1", "1-4-4-2", "1-4-3-3", "1-5-4-1", "1-5-3-2"
  ];

  return VALID_FORMATIONS.includes(formationKey);
}

// Which GW's fixtures a pitch shows on its player cards. Pick Team provides
// the EDIT gw (the one in "Save Lineup for GWX") so cards show that round's
// opponents; with no provider (Points/Status pitches) the value is null and
// the viewed-GW map built by app.jsx is used — the pre-existing behavior.
const FixtureGwContext = React.createContext(null);
window.FixtureGwContext = FixtureGwContext;

function getNextFixtureOpponent(teamIso, gw = null) {
  // Team-vs-team fixtures for the relevant GW. With an explicit `gw` the
  // source is the per-GW cache window.WC_FIXTURES_BY_GW[gw] (filled on demand
  // by window.fetchFixturesByTeamForGw in app.jsx) — "—" until that round's
  // fetch lands. Otherwise it is the live window.WC_FIXTURES_BY_TEAM map
  // (built in app.jsx from GET /fixtures for the VIEWED gw, keyed by the same
  // iso the players use; backend resolves isoCode from the team map). A team
  // with no entry — genuinely not playing the resolved round — shows "—". We
  // deliberately do NOT fall back to the static WC_FIXTURES_GW4 round: that
  // prototype set contains placeholder teams (e.g. POR2=Türkiye, MEX2=Peru)
  // that don't exist in the backend, so it fabricated wrong opponents
  // whenever the live map was empty. window.SCHEDULE is the H2H *manager*
  // schedule, not team fixtures, so it is never used here.
  if (!teamIso) return "—";
  const iso = String(teamIso).toUpperCase();
  const byTeam = (gw != null)
    ? (window.WC_FIXTURES_BY_GW || {})[gw]
    : window.WC_FIXTURES_BY_TEAM;
  if (byTeam && typeof byTeam === "object") {
    const entry = byTeam[iso];
    if (entry && entry.opp) return `v ${entry.opp}`;
  }
  return "—";
}

// ---------- Player Slot (used on pitch) ----------
function PlayerSlot({ playerId, points, mode = "points", disabled = false, selected = false, onBench = false, benchOrder = null, onClick }) {
  // null outside a FixtureGwContext provider → viewed-GW map (legacy behavior).
  // Read before the empty-slot return so the hook runs on every render.
  const fixtureGw = React.useContext(FixtureGwContext);
  const p = playerById(playerId);
  if (!p) {
    return (
      <div className="player-slot">
        <div className="player-slot__jersey" style={{ background: "rgba(0,0,0,0.2)", borderRadius: 8 }} />
        <div className="player-slot__name">Empty</div>
      </div>
    );
  }
  const t = teamById(p.team);
  const isElim = p.elim || (t && t.elim);

  const openStats = (e) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('show-player-stats', { detail: { id: playerId } }));
  };

  const opp = getNextFixtureOpponent(p.team, fixtureGw);
  // For a points view the per-GW points come from the gw_history snapshot map
  // (passed down via Pitch.pointsById). A player who didn't feature that GW has
  // NO snapshot entry — show 0, never the season-total fallback (VT-PointsNoStats
  // #52), which would leak a non-zero score onto a player with no GW stats.
  const displayInfo = mode === "points"
    ? `${points != null ? points : 0} PTS`
    : opp;

  return (
    <div
      className={`player-slot ${isElim ? "player-slot--eliminated" : ""} ${disabled ? "player-slot--disabled" : ""} ${selected ? "player-slot--selected" : ""}`}
      style={{ cursor: "pointer" }}
      onClick={(e) => {
        if (onClick) {
          onClick(e);
        } else {
          openStats(e);
        }
      }}
    >
      <button type="button" className="player-slot__info" onClick={openStats} title="Player stats">i</button>
      <div className="player-slot__jersey">
        <Jersey team={t} pos={p.pos} eliminated={isElim} />
        <span className={`player-slot__bench-role${onBench ? "" : " player-slot__bench-role--starter"}`}>
          {POS_NAMES[p.pos]}
        </span>
        {onBench && benchOrder > 0 && p.pos !== 1 && (
          <span className="player-slot__bench-order">
            {benchOrder}
          </span>
        )}
      </div>
      <div className="player-slot__name">{p.name}</div>
      <div className="player-slot__fixture">{displayInfo}</div>
    </div>
  );
}

// ---------- Pitch ----------
// formation: [GK, DEF, MID, FWD]
function Pitch({ lineup, mode = "points", selected = null, onPlayerClick, pointsById = null }) {
  if (!lineup) return null;
  const { starting, bench, formation } = lineup;
  const [_gk, nDef, nMid, nFwd] = formation;

  const gk = starting.slice(0, 1);
  const def = starting.slice(1, 1 + nDef);
  const mid = starting.slice(1 + nDef, 1 + nDef + nMid);
  const fwd = starting.slice(1 + nDef + nMid, 1 + nDef + nMid + nFwd);

  // Per-player points for the viewed gw (engine output from the manager's
  // gw_history snapshot). A player with no snapshot entry didn't feature that
  // GW → PlayerSlot renders 0 (no season-total fallback; see VT-PointsNoStats).
  const ptsOf = (id) => (pointsById && pointsById[String(id)] != null) ? pointsById[String(id)] : undefined;
  const isPlayerDisabled = (id) => {
    if (mode !== "pick" || selected === null) return false;
    return !isSwapLegal(lineup, selected, id);
  };

  return (
    <div className="pitch-wrap">
      <div className="pitch">
        <div className="pitch__stripes" />
        <div className="pitch__lines" />
        <div className="pitch__circle" />
        <div className="pitch__half" />
        <div className="pitch__pen-top" />
        <div className="pitch__pen-bot" />
        <div className="pitch__six-top" />
        <div className="pitch__six-bot" />

        <div className="pitch__rows">
          <div className="pitch__row">
            {gk.map(id => <PlayerSlot key={id} playerId={id} points={ptsOf(id)} mode={mode} disabled={isPlayerDisabled(id)} selected={selected === id} onClick={() => onPlayerClick?.(id)} />)}
          </div>
          <div className="pitch__row">
            {def.map(id => <PlayerSlot key={id} playerId={id} points={ptsOf(id)} mode={mode} disabled={isPlayerDisabled(id)} selected={selected === id} onClick={() => onPlayerClick?.(id)} />)}
          </div>
          <div className="pitch__row">
            {mid.map(id => <PlayerSlot key={id} playerId={id} points={ptsOf(id)} mode={mode} disabled={isPlayerDisabled(id)} selected={selected === id} onClick={() => onPlayerClick?.(id)} />)}
          </div>
          <div className="pitch__row">
            {fwd.map(id => <PlayerSlot key={id} playerId={id} points={ptsOf(id)} mode={mode} disabled={isPlayerDisabled(id)} selected={selected === id} onClick={() => onPlayerClick?.(id)} />)}
          </div>
        </div>
      </div>

      {/* Bench rendered BELOW the pitch — its own slot row so names always fit */}
      <div className="bench-row">
        <div className="bench-row__label">BENCH</div>
        <div className="bench-row__slots">
          {bench.map((id, i) => (
            <div key={id} className="bench-row__slot">
              <PlayerSlot playerId={id} points={ptsOf(id)} mode={mode} disabled={isPlayerDisabled(id)} selected={selected === id} onBench={true} benchOrder={i} onClick={() => onPlayerClick?.(id)} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------- Trophy icon ----------
function TrophyIcon({ size = 24, color = "currentColor" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 4h12v3a6 6 0 0 1-6 6 6 6 0 0 1-6-6V4Z" fill={color} />
      <path d="M3 5h3v3a2 2 0 0 1-2-2 1 1 0 0 1-1-1Zm15 0h3a1 1 0 0 1-1 1 2 2 0 0 1-2 2V5Z" fill={color} opacity="0.7" />
      <path d="M10 13h4v3h-4z" fill={color} opacity="0.85" />
      <path d="M8 16h8v3H8z" fill={color} />
      <path d="M7 19h10v2H7z" fill={color} />
    </svg>
  );
}

// ---------- Logo ----------
function Logo() {
  return (
    <span className="topbar__logo">
      <svg viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="logo-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#4a1ba8" />
            <stop offset="0.5" stopColor="#3a2db8" />
            <stop offset="1" stopColor="#1be8d4" />
          </linearGradient>
        </defs>
        <rect x="2" y="2" width="32" height="32" rx="9" fill="url(#logo-grad)" />
        {/* trophy */}
        <path d="M12 9h12v4a6 6 0 0 1-6 6 6 6 0 0 1-6-6V9Z" fill="#ffc844" />
        <path d="M14 19h8v3h-8z" fill="#ffc844" opacity="0.85" />
        <path d="M11 22h14v2.5H11z" fill="#ffc844" />
        {/* star */}
        <circle cx="28" cy="9" r="2.2" fill="#00e87b" />
      </svg>
      <span>
        <span style={{ background: "linear-gradient(94deg,#4a1ba8,#1be8d4)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
          WC26
        </span>
        <span style={{ marginLeft: 6, fontWeight: 400, color: "var(--ink-700)" }}>Draft</span>
      </span>
    </span>
  );
}

// ---------- Stat ----------
function Stat({ label, value, accent, big }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", gap: 12 }}>
      <span style={{ fontSize: 13, opacity: 0.85, whiteSpace: "nowrap", flexShrink: 0 }}>{label}</span>
      <span className="mono" style={{ fontWeight: 700, fontSize: big ? 18 : 14, color: accent || "inherit", whiteSpace: "nowrap" }}>{value}</span>
    </div>
  );
}

// ---------- useIsMobile (WP0 mobile layer) ----------
function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState(
    () => window.matchMedia("(max-width: 768px)").matches
  );
  React.useEffect(() => {
    const mq = window.matchMedia("(max-width: 768px)");
    const fn = e => setIsMobile(e.matches);
    mq.addEventListener ? mq.addEventListener("change", fn) : mq.addListener(fn);
    return () => { mq.removeEventListener ? mq.removeEventListener("change", fn) : mq.removeListener(fn); };
  }, []);
  return isMobile;
}

// ---------- Transfer-window timers (Segment 3 — windows & timers UX) ----------
// Shared helpers for the windows/timers UX. The backend's /transfer-window now
// returns the real fixture-clock boundaries (phaseEndsAt / nextPhase /
// nextPhaseStartsAt / schedule); these render them. components.jsx loads before
// shell/screens/app, so every consumer sees these globals.

// Display label + one-line hint + accent per transfer-window phase. Vocabulary
// kept aligned with the admin "Switch window" buttons (screens-bracket.jsx).
const WINDOW_PHASE_META = {
  trade:       { label: "Trade window",  hint: "Manager trades + wishlist bids", accent: "var(--green-400)" },
  free_agents: { label: "Free agents",   hint: "Instant pickups + wishlist",     accent: "var(--gold-500)" },
  next_gw_bid: { label: "Gameweek live", hint: "Offer trades · squads frozen",    accent: "var(--red-500)" },
  none:        { label: "Locked",        hint: "Squads + lineups frozen",         accent: "var(--ink-500)" },
};
function windowPhaseMeta(phase) {
  return WINDOW_PHASE_META[phase] || { label: phase || "—", hint: "", accent: "var(--ink-500)" };
}

// "Wed 18 Jun, 15:00" in the viewer's local timezone. "—" for missing/bad input.
function fmtWindowTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return d.toLocaleString(undefined, {
    weekday: "short", day: "numeric", month: "short",
    hour: "2-digit", minute: "2-digit",
  });
}

// Milliseconds → compact "1d 4h 12m" / "4h 12m" / "12m 30s" / "Now". Seconds
// show only under an hour so multi-day waits stay calm; "Now" once elapsed.
function fmtCountdown(ms) {
  if (ms == null || isNaN(ms) || ms <= 0) return "Now";
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}

// Ticking "now" hook — re-renders only the calling component every `intervalMs`
// (default 1s) so countdowns stay live without re-rendering the whole app.
function useNow(intervalMs = 1000) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

// Live countdown to an ISO instant. `to` null → renders `placeholder`. Shows
// "Now" once elapsed. `prefix`/`suffix` wrap the value.
function Countdown({ to, prefix = "", suffix = "", placeholder = "—", style, className }) {
  const now = useNow(1000);
  if (!to) return <span style={style} className={className}>{placeholder}</span>;
  const ms = Date.parse(to) - now;
  return <span style={style} className={className}>{prefix}{fmtCountdown(ms)}{suffix}</span>;
}

// The lineup-lock instant for a given GW (= T0 - squad_lock_before_h), pulled
// from the WINDOW schedule the backend returns. The locked ("none") band starts
// exactly at the lock; if the short-turnaround clamp dropped that band we fall
// back to the end of free-agents, then to T0 (the live band's start). Returns an
// ISO string, or null when the GW isn't in the two-GW schedule window yet.
function lineupLockForGw(gw) {
  const sched = (window.WINDOW && window.WINDOW.schedule) || [];
  const locked = sched.find(s => s.gw === gw && s.phase === "none");
  if (locked && locked.startsAt) return locked.startsAt;
  const fa = sched.find(s => s.gw === gw && s.phase === "free_agents");
  if (fa && fa.endsAt) return fa.endsAt;
  const bid = sched.find(s => s.gw === gw && s.phase === "next_gw_bid");
  return bid ? bid.startsAt : null;
}

// Window-timeline bands: the ordered transfer-window phases (with local start/
// end times + what each one allows) for the WINDOW schedule. `gw` filters to a
// single GW; null shows the whole two-GW window. The live band is flagged NOW
// and past bands dim. Renders nothing when no schedule covers the request — so
// it's safe to drop into any screen unconditionally.
function WindowTimeline({ gw = null, title = "Transfer windows" }) {
  const now = useNow(30000);  // bands turn over slowly; a 30s tick is ample
  const sched = (window.WINDOW && window.WINDOW.schedule) || [];
  const rows = gw == null ? sched : sched.filter(s => s.gw === gw);
  if (!rows.length) return null;
  return (
    <div className="card" style={{ padding: "14px 16px" }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-500)", marginBottom: 10 }}>
        {title}{gw != null ? ` · GW${gw}` : ""}
      </div>
      <div className="col" style={{ gap: 8 }}>
        {rows.map((s, i) => {
          const meta = windowPhaseMeta(s.phase);
          const startMs = s.startsAt ? Date.parse(s.startsAt) : -Infinity;
          const endMs = Date.parse(s.endsAt);
          const active = now >= startMs && now < endMs;
          const past = now >= endMs;
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, opacity: past ? 0.45 : 1 }}>
              <div style={{ width: 4, alignSelf: "stretch", borderRadius: 2, background: meta.accent }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>{meta.label}</span>
                  {active && <span className="pill" style={{ background: meta.accent, color: "var(--navy-900)", fontSize: 10, fontWeight: 800, padding: "1px 8px" }}>NOW</span>}
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-500)" }}>{meta.hint}</div>
              </div>
              <div style={{ textAlign: "right", fontSize: 12, color: "var(--ink-700)", whiteSpace: "nowrap" }}>
                <div>{s.startsAt ? fmtWindowTime(s.startsAt) : "open now"}</div>
                <div style={{ color: "var(--ink-300)" }}>→ {fmtWindowTime(s.endsAt)}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------- Custom per-manager team flags (fun league flags) ----------
// 600x400 normalized PNGs in /flags. Falls back to the member's nation flag
// for any uid without a custom one (future joiners).
const CUSTOM_TEAM_FLAGS = {
  u_ilay: "flags/u_ilay.png",
  u_netanel: "flags/u_netanel.png",
  u_yuval: "flags/u_yuval.png",
  u_roy: "flags/u_roy.png",
  u_nadav: "flags/u_nadav.png",
  u_shay: "flags/u_shay.png",
};
// size: sm 22x14 · lg 32x22 · xl 66x44 (page headers) · hero 144x96 (modals)
const MANAGER_FLAG_SIZES = {
  xl:   { width: 66,  height: 44, borderRadius: 6, boxShadow: "0 1px 4px rgba(0,0,0,0.18)" },
  hero: { width: 144, height: 96, borderRadius: 10, boxShadow: "0 3px 12px rgba(0,0,0,0.22)" },
};
function ManagerFlag({ uid, size = "sm", fallback = null, style = null }) {
  const src = CUSTOM_TEAM_FLAGS[uid];
  if (!src) return fallback ? <Flag team={fallback} size={MANAGER_FLAG_SIZES[size] ? "lg" : size} /> : null;
  const big = MANAGER_FLAG_SIZES[size];
  return (
    <span className={"flag" + (size !== "sm" ? " flag--lg" : "")}
          style={big ? { ...big, ...(style || {}) } : (style || undefined)}
          title="Team flag">
      <img src={src} alt="team flag" />
    </span>
  );
}

// ---------- Sync data (any user) ----------
// Pulls fresh live scores on demand (POST /sync-live-scores — the same
// self-healing scan the schedulers run, debounced 60s server-side), then
// reloads so every panel rerenders from the synced data. The scan walks
// multiple feeds, so allow it well past apiCall's 12s default.
function SyncDataButton({ style }) {
  const [busy, setBusy] = React.useState(false);
  const run = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await apiCall("POST", "/sync-live-scores?daysBack=1", null, { timeoutMs: 120000 });
      window.location.reload();
    } catch (e) {
      alert("Sync failed: " + ((e && (e.error || e.message)) || JSON.stringify(e)));
      setBusy(false);
    }
  };
  return (
    <button className="btn btn--ghost-dark" disabled={busy} onClick={run}
      style={{ whiteSpace: "nowrap", ...style }}>
      {busy ? "Syncing…" : "⟳ Sync data"}
    </button>
  );
}

// ---------- Secret betting picks (EV = P(dir)·base + 4·P(exact)) ----------
// Static snapshot of the score-prediction-pool EV model: Polymarket directions
// blended 0.6/0.4 with FIFA Match Predictor crowd picks on the exact score.
// Hand-computed (no live feed) — refresh by editing this table. Hidden behind a
// triple-tap on the Fixtures GW bar; nothing here touches league data.
const BETTING_PICKS = {
  GW1: { label: "GW1 · Round 1 (closing tonight)", rows: [
    ["Portugal – DR Congo", "Portugal 3-0", 2.10, false],
    ["England – Croatia",   "England 2-1",  2.02, false],
    ["Uzbekistan – Colombia","Colombia 2-0", 1.97, false],
    ["Ghana – Panama",      "Draw 1-1 (toss-up)", 1.60, true],
  ]},
  GW2: { label: "GW2 · Round 2", rows: [
    ["Canada – Qatar",        "Canada 2-0",      2.42, false],
    ["Ecuador – Curaçao",     "Ecuador 2-0",     2.30, false],
    ["Spain – Saudi Arabia",  "Spain 3-0",       2.19, false],
    ["Brazil – Haiti",        "Brazil 3-0",      2.16, false],
    ["France – Iraq",         "France 3-0",      2.16, false],
    ["Tunisia – Japan",       "Japan 2-0",       2.15, true],
    ["Portugal – Uzbekistan", "Portugal 3-0",    2.09, false],
    ["Switzerland – Bosnia",  "Switzerland 2-1", 2.01, false],
    ["Czech – South Africa",  "Czech 2-0",       1.94, false],
    ["USA – Australia",       "USA 2-1",         1.94, false],
    ["Netherlands – Sweden",  "Netherlands 2-1", 1.94, false],
    ["Uruguay – Cape Verde",  "Uruguay 2-0",     1.94, false],
    ["England – Ghana",       "England 2-0",     1.94, false],
    ["Jordan – Algeria",      "Algeria 2-0",     1.93, true],
    ["Turkey – Paraguay",     "Turkey 2-1",      1.92, false],
    ["Argentina – Austria",   "Argentina 2-1",   1.91, false],
    ["Colombia – DR Congo",   "Colombia 2-0",    1.91, false],
    ["New Zealand – Egypt",   "Egypt 2-0",       1.91, true],
    ["Belgium – Iran",        "Belgium 2-0",     1.86, false],
    ["Mexico – S.Korea",      "Draw 1-1",        1.86, true],
    ["Scotland – Morocco",    "Morocco 2-1",     1.84, true],
    ["Panama – Croatia",      "Croatia 2-0",     1.84, false],
    ["Norway – Senegal",      "Draw 1-1",        1.55, true],
    ["Germany – Ivory Coast", "Germany 2-1",     1.54, false],
  ]},
  GW3: { label: "GW3 · Round 3", rows: [
    ["South Africa – S.Korea","S.Korea 2-0",     2.28, true],
    ["Curaçao – Ivory Coast", "Ivory Coast 2-0", 2.16, false],
    ["Jordan – Argentina",    "Argentina 3-0",   2.12, false],
    ["Czech – Mexico",        "Mexico 2-1",      2.11, true],
    ["Senegal – Iraq",        "Senegal 2-0",     2.10, false],
    ["Bosnia – Qatar",        "Draw 1-1",        2.08, true],
    ["Morocco – Haiti",       "Morocco 3-0",     2.05, false],
    ["New Zealand – Belgium", "Belgium 2-0",     2.03, false],
    ["Croatia – Ghana",       "Croatia 2-1",     1.98, false],
    ["Tunisia – Netherlands", "Netherlands 2-0", 1.93, false],
    ["Panama – England",      "England 3-0",     1.91, false],
    ["Algeria – Austria",     "Draw 1-1",        1.90, true],
    ["Switzerland – Canada",  "Switzerland 2-1", 1.88, false],
    ["Egypt – Iran",          "Egypt 2-1",       1.86, false],
    ["DR Congo – Uzbekistan", "Draw 1-1",        1.84, true],
    ["Cape Verde – Saudi Arabia","Saudi 1-0",    1.74, true],
    ["Colombia – Portugal",   "Portugal 2-1",    1.74, false],
    ["Norway – France",       "France 2-1",      1.73, false],
    ["Paraguay – Australia",  "Paraguay 1-0",    1.70, false],
    ["Scotland – Brazil",     "Brazil 2-1",      1.64, false],
    ["Japan – Sweden",        "Japan 2-1",       1.63, false],
    ["Uruguay – Spain",       "Spain 2-1",       1.58, false],
    ["Ecuador – Germany",     "Germany 2-1",     1.56, false],
    ["Turkey – USA",          "Turkey 2-1",      1.42, false],
  ]},
};
function BettingPicksModal({ open, onClose }) {
  const [tab, setTab] = React.useState("GW1");
  if (!open) return null;
  const data = BETTING_PICKS[tab] || BETTING_PICKS.GW1;
  const maxEv = 2.42;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.62)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: "#0f1620", color: "#e8edf2", borderRadius: 14, maxWidth: 560, width: "100%", maxHeight: "86vh", overflow: "auto", boxShadow: "0 16px 56px rgba(0,0,0,0.55)", border: "1px solid rgba(255,255,255,0.10)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 18px 12px", position: "sticky", top: 0, background: "#0f1620", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>🎯 Score-pool EV picks</div>
            <div style={{ fontSize: 11, color: "#8aa0b4", marginTop: 2 }}>Polymarket × FIFA crowd blend · static snapshot</div>
          </div>
          <button onClick={onClose} style={{ background: "rgba(255,255,255,0.08)", border: "none", color: "#e8edf2", borderRadius: 8, width: 30, height: 30, fontSize: 16, cursor: "pointer" }}>✕</button>
        </div>
        <div style={{ display: "flex", gap: 6, padding: "10px 16px" }}>
          {["GW1", "GW2", "GW3"].map(k => (
            <button key={k} onClick={() => setTab(k)} style={{ flex: 1, padding: "8px 0", fontSize: 13, fontWeight: 700, cursor: "pointer", borderRadius: 8, border: "1px solid rgba(255,255,255,0.10)", background: tab === k ? "#1be8d4" : "transparent", color: tab === k ? "#06222b" : "#cdd9e4" }}>{k}</button>
          ))}
        </div>
        <div style={{ fontSize: 11, color: "#8aa0b4", padding: "0 18px 8px" }}>{data.label} — ranked by expected points. ★ = non-obvious (draw / underdog).</div>
        <div style={{ padding: "0 12px 16px" }}>
          {data.rows.map((r, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 6px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <span style={{ width: 18, fontSize: 11, color: "#6a8095", flexShrink: 0 }}>{i + 1}</span>
              <span style={{ flex: 1, minWidth: 0, fontSize: 12.5 }}>{r[0]}</span>
              <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 6, whiteSpace: "nowrap", background: r[3] ? "rgba(255,200,68,0.16)" : "rgba(27,232,212,0.14)", color: r[3] ? "#ffc844" : "#1be8d4" }}>{r[1]}{r[3] ? " ★" : ""}</span>
              <span style={{ display: "flex", alignItems: "center", gap: 6, width: 92, flexShrink: 0 }}>
                <span style={{ height: 7, borderRadius: 4, background: r[2] >= 2.0 ? "#1be8d4" : r[2] >= 1.7 ? "#7fd6c8" : "#9aa7b3", width: Math.max(2, Math.round((r[2] / maxEv) * 56)) }} />
                <span style={{ fontSize: 12, fontWeight: 700, color: "#e8edf2" }}>{r[2].toFixed(2)}</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------- Expose globally ----------
Object.assign(window, { Flag, GroupChip, Jersey, PlayerSlot, Pitch, TrophyIcon, Logo, Stat, useIsMobile, ManagerFlag, CUSTOM_TEAM_FLAGS, SyncDataButton, BettingPicksModal });
