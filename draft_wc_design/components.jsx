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

function getNextFixtureOpponent(teamIso) {
  // Team-vs-team fixtures for the viewing GW. Primary source is the live
  // window.WC_FIXTURES_BY_TEAM map (built in app.jsx from GET /fixtures?gw=N,
  // keyed by the same iso the players use; backend resolves isoCode from the
  // team map). Falls back to the static WC_FIXTURES_GW4 round only when the
  // live map isn't loaded yet. Teams not playing this GW (eliminated / bye)
  // resolve to "—". window.SCHEDULE is the H2H *manager* schedule, not team
  // fixtures, so it is never used here.
  if (!teamIso) return "—";
  const iso = String(teamIso).toUpperCase();
  const byTeam = window.WC_FIXTURES_BY_TEAM;
  if (byTeam && typeof byTeam === "object" && Object.keys(byTeam).length > 0) {
    const entry = byTeam[iso];
    return entry && entry.opp ? `v ${entry.opp}` : "—";
  }
  // Fallback: static single-round set (pre-load / fixtures fetch failed).
  const fixtures = (window.WC_FIXTURES_GW4 || []);
  if (!Array.isArray(fixtures)) return "—";
  const fix = fixtures.find(f => f && (f.home === iso || f.away === iso));
  if (!fix) return "—";
  return fix.home === iso ? `v ${fix.away}` : `v ${fix.home}`;
}

// ---------- Player Slot (used on pitch) ----------
function PlayerSlot({ playerId, points, mode = "points", disabled = false, selected = false, onBench = false, benchOrder = null, onClick }) {
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

  const opp = getNextFixtureOpponent(p.team);
  const displayInfo = mode === "points" 
    ? `${points != null ? points : (GW3_POINTS[playerId] ?? 0)} PTS` 
    : opp;

  return (
    <div
      className={`player-slot ${isElim ? "player-slot--eliminated" : ""} ${disabled ? "player-slot--disabled" : ""} ${selected ? "player-slot--selected" : ""}`}
      onClick={onClick}
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
  // gw_history snapshot). When provided, this overrides the GW3_POINTS
  // (season-total) fallback inside PlayerSlot.
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

// ---------- Expose globally ----------
Object.assign(window, { Flag, GroupChip, Jersey, PlayerSlot, Pitch, TrophyIcon, Logo, Stat });
