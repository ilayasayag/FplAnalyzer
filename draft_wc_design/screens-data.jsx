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
  const isMobile = useIsMobile();

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
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr 110px 130px 150px 150px 120px", gap: 12 }}>
          <div style={isMobile ? { gridColumn: "1 / -1" } : undefined}>
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
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 14, fontSize: 12, color: "rgba(255,255,255,0.7)", flexWrap: isMobile ? "wrap" : undefined, gap: isMobile ? 8 : undefined }}>
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
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(6, 1fr)" : "repeat(12, 1fr)", gap: 4, marginBottom: 4 }}>
        {["A","B","C","D","E","F","G","H","I","J","K","L"].map(g => (
          <button key={g}
            onClick={() => setGrp(grp === g ? "all" : g)}
            style={{
              padding: isMobile ? "12px 0" : "8px 0", borderRadius: 6, fontSize: 11, fontWeight: 800,
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
        <div className="table-scroll">
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
                        {isElim && <div style={{ fontSize: isMobile ? 11 : 10, color: "var(--red-500)", fontWeight: 700, letterSpacing: "0.06em", whiteSpace: "nowrap" }}>OUT · ELIMINATED</div>}
                      </div>
                    </div>
                  </td>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <Flag team={t} /> <span style={{ fontSize: 13 }}>{t.name}</span>
                    </span>
                  </td>
                  <td><GroupChip group={t.grp} /></td>
                  <td><span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.08)", color: "var(--navy-900)", fontSize: isMobile ? 11 : 10 }}>{POS_NAMES[p.pos]}</span></td>
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
        </div>
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
// Normalize a backend fixture ({homeTeam,awayTeam,kickoff,status,score,wcRound})
// into the row shape the renderer expects ({day,time,home,away,venue,...}).
// `home`/`away` are isoCodes so teamById resolves flag/name/group for both the
// live map and the static bracket.
function normalizeFixtureRow(fx) {
  const homeIso = ((fx.homeTeam || {}).isoCode || "").toUpperCase();
  const awayIso = ((fx.awayTeam || {}).isoCode || "").toUpperCase();
  let day = "", time = "";
  if (fx.kickoff) {
    const d = new Date(fx.kickoff);
    if (!isNaN(d.getTime())) {
      day = d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
      time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    }
  }
  const sc = fx.score || {};
  const hasScore = sc.home != null && sc.away != null;
  return {
    home: homeIso || (fx.homeTeam || {}).name || "?",
    away: awayIso || (fx.awayTeam || {}).name || "?",
    homeName: (fx.homeTeam || {}).name,
    awayName: (fx.awayTeam || {}).name,
    day: day || "Scheduled",
    time: time || (fx.status || ""),
    venue: hasScore ? `${sc.home}–${sc.away}` : "",
    status: fx.status,
  };
}

// ---------- WC tournament knockout bracket (national teams) ----------
// Renders wc_config/wc_bracket (served by GET /wc-bracket), self-updated by the
// daily scan. Round columns R32 → Final; winners highlighted; TBD slots show the
// ESPN placeholder ("Round of 32 1 Winner") until the team is decided.
const WC_BRACKET_ROUND_ORDER = ["Round of 32", "Round of 16", "Quarter-Final", "Semi-Final", "Final"];

// Canonical Round-of-32 bracket order (official FIFA bracket, per the
// confirmed QF venues/pairings — Boston/Miami feed SF1, LA/KC feed SF2). Our
// ESPN scan stores matches in DATE order, which scrambles the tree — we
// re-seat them here in groups of 4 so each QF block feeds the right SF.
const WC_CANON_R32 = [
  ["GER", "PAR"], ["FRA", "SWE"], ["RSA", "CAN"], ["NED", "MOR"],  // Boston QF
  ["POR", "CRO"], ["SPA", "AUT"], ["USA", "BOS"], ["BEL", "SEN"],  // Miami QF
  ["BRA", "JAP"], ["CIV", "NOR"], ["MEX", "ECU"], ["ENG", "COD"],  // LA QF
  ["ARG", "CPV"], ["AUS", "EGY"], ["SWI", "ALG"], ["COL", "GHA"],  // KC QF
];

// Re-seat every round into FIXED canonical bracket slots. Each round is an
// array of exactly its bracket size (R32=16, R16=8, QF=4, SF=2, Final=1); a
// match is placed at the slot dictated by the canonical R32 table above (later
// rounds inherit their slot from whichever R32 slot their real team came from).
// Slots with no data yet become "Winner of …" placeholders.
//
// The slots are FIXED (not a variable-length sorted list): a match briefly
// missing from the feed leaves ONE empty slot on its correct side rather than
// shifting every later match up a position — which is what scrambled the tree
// (e.g. Brazil/Norway jumping to the wrong half) when South Africa/Canada
// dropped out of the ESPN scan window. The left/right split downstream keys off
// the slot index, so the tree shape is stable regardless of feed gaps.
function wcCanonicalize(rounds) {
  const r32src = rounds["Round of 32"] || [];
  if (!r32src.length) return rounds;
  const idxOf = m => {
    const a = m.home, b = m.away;
    for (let i = 0; i < WC_CANON_R32.length; i++) {
      const [x, y] = WC_CANON_R32[i];
      if ((a === x && b === y) || (a === y && b === x)) return i;
    }
    return -1; // unknown matchup → cannot be positioned in the tree
  };
  // Seat R32 into its 16 fixed slots. slotOf maps each real team → its slot so
  // later rounds can be positioned by the team that advanced.
  const r32slots = new Array(16).fill(null);
  r32src.forEach(m => { const i = idxOf(m); if (i >= 0 && !r32slots[i]) r32slots[i] = m; });
  const slotOf = {};
  r32slots.forEach((m, i) => {
    if (!m) return;
    if (m.home) slotOf[m.home] = i;
    if (m.away) slotOf[m.away] = i;
  });
  const placeholder = (id, s, prev) => ({
    id, home: null, away: null, winner: null, status: "NS",
    homeName: prev ? prev + " " + (2 * s + 1) + " Winner" : "TBD",
    awayName: prev ? prev + " " + (2 * s + 2) + " Winner" : "TBD",
  });
  const out = {
    "Round of 32": r32slots.map((m, s) => m || placeholder("R32-canon-" + s, s, null)),
  };
  for (let ri = 1; ri < WC_BRACKET_ROUND_ORDER.length; ri++) {
    const rname = WC_BRACKET_ROUND_ORDER[ri];
    if (!(rounds[rname] && rounds[rname].length)) continue; // round not scheduled yet
    const prev = WC_BRACKET_ROUND_ORDER[ri - 1];
    const size = 16 >> ri;
    const bySlot = {};
    (rounds[rname] || []).forEach(m => {
      const t = m.home || m.away;
      if (t && slotOf[t] != null) bySlot[slotOf[t] >> ri] = m;
    });
    const arr = [];
    for (let s = 0; s < size; s++) {
      arr.push(bySlot[s] || placeholder(rname + "-canon-" + s, s, prev));
    }
    out[rname] = arr;
  }
  return out;
}

// Compact an ESPN placeholder label ("Round of 32 1 Winner") to a tiny slot tag
// ("R32 W1") so undecided boxes stay one short line instead of two long ones.
function wcShortSlot(name) {
  if (!name) return "TBD";
  let s = String(name)
    .replace(/Round of 32/i, "R32").replace(/Round of 16/i, "R16")
    .replace(/Quarter-?final/i, "QF").replace(/Semi-?final/i, "SF")
    .replace(/\s*Winner\s*/i, " W").trim();
  // "R32 1 W" -> "R32 W1"
  s = s.replace(/^(R32|R16|QF|SF)\s+(\d+)\s*W$/i, "$1 W$2");
  return s || "TBD";
}

function WCBracketSide({ iso, name, score, winner, played }) {
  const isWinner = !!(winner && iso && winner === iso);
  return (
    <div className="bracket__side" style={{ opacity: iso ? 1 : 0.55 }}>
      {iso ? <Flag team={{ id: iso, name: name || iso }} size="lg" /> : <div className="bracket__seed">—</div>}
      <div className="bracket__team" style={{ fontWeight: isWinner ? 800 : 600 }}>{iso || wcShortSlot(name)}</div>
      {/* Only show a score once the tie is actually being/been played — an
          unplayed match has score 0 which read as clutter. */}
      {played && (
        <div className="bracket__pts" style={{ color: isWinner ? "var(--green-400)" : undefined }}>
          {score == null ? "–" : score}
        </div>
      )}
    </div>
  );
}

function WCBracketMatch({ m }) {
  const played = m.status === "FT" || m.status === "LIVE";
  const tag = m.status === "LIVE" ? "LIVE"
    : m.status === "FT" ? (m.decidedBy === "penalties" ? "FT · pens" : "FT") : null;
  return (
    <div className="bracket__match" style={{ borderColor: m.status === "LIVE" ? "var(--green-400)" : undefined }}>
      <WCBracketSide iso={m.home} name={m.homeName} score={m.homeScore} winner={m.winner} played={played} />
      <WCBracketSide iso={m.away} name={m.awayName} score={m.awayScore} winner={m.winner} played={played} />
      {tag && <div style={{ textAlign: "center", fontSize: 9, fontWeight: 800, letterSpacing: "0.06em", color: m.status === "LIVE" ? "var(--green-400)" : "rgba(255,255,255,0.45)", paddingTop: 2 }}>{tag}</div>}
    </div>
  );
}

function WCBracketView() {
  const [data, setData] = React.useState(null);
  const [err, setErr] = React.useState(false);
  React.useEffect(() => {
    let cancelled = false;
    apiCall("GET", "/wc-bracket")
      .then(d => { if (!cancelled) setData(d || {}); })
      .catch(() => { if (!cancelled) setErr(true); });
    return () => { cancelled = true; };
  }, []);
  if (err) return <div className="muted" style={{ padding: "12px 0", color: "rgba(255,255,255,0.6)" }}>Bracket unavailable right now.</div>;
  if (!data) return <div className="muted" style={{ padding: "12px 0", color: "rgba(255,255,255,0.6)" }}>Loading bracket…</div>;
  const rounds = wcCanonicalize(data.rounds || {});
  const present = WC_BRACKET_ROUND_ORDER.filter(r => (rounds[r] || []).length > 0);
  if (present.length === 0) return <div className="muted" style={{ padding: "12px 0", color: "rgba(255,255,255,0.6)" }}>The bracket will populate as the Round of 32 begins.</div>;
  // Two-sided bracket: every round except the Final splits in half — the first
  // half is the LEFT side, the second half the RIGHT side (ESPN orders matches
  // in bracket sequence). Columns run R32-L → SF-L → FINAL → SF-R → R32-R, so
  // the Final sits in the middle and both halves read inward.
  const sideRounds = present.filter(r => r !== "Final");
  const hasFinal = (rounds["Final"] || []).length > 0;
  const half = ms => Math.ceil(ms.length / 2);
  const columns = [];
  sideRounds.forEach(r => {
    const ms = rounds[r] || [];
    columns.push({ key: r + "-L", head: r, matches: ms.slice(0, half(ms)) });
  });
  if (hasFinal) columns.push({ key: "Final", head: "Final", matches: rounds["Final"], center: true });
  [...sideRounds].reverse().forEach(r => {
    const ms = rounds[r] || [];
    columns.push({ key: r + "-R", head: r, matches: ms.slice(half(ms)) });
  });
  return (
    <div className="bracket-scroll">
      <div className="bracket" style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(112px, 1fr))` }}>
        {columns.map(col => (
          <div className="bracket__col" key={col.key} style={col.center ? { justifyContent: "center" } : undefined}>
            <div className="bracket__col-head">{col.head}</div>
            {(col.matches || []).map(m => <WCBracketMatch key={m.id} m={m} />)}
          </div>
        ))}
      </div>
    </div>
  );
}

function FixturesScreen() {
  // Default to the tournament's REAL current GW (mock-era code hardcoded 4).
  const [gw, setGw] = React.useState((window.TOURNAMENT && window.TOURNAMENT.currentGw) || 1);
  const isKnockout = ((window.TOURNAMENT && window.TOURNAMENT.currentGw) || 1) >= 4;
  const [view, setView] = React.useState(isKnockout ? "bracket" : "list");
  const [fetched, setFetched] = React.useState(null); // null = not loaded yet
  const [loading, setLoading] = React.useState(false);
  const isMobile = useIsMobile();
  const round = TOURNAMENT.gwDates[gw];

  // Secret: single-click the GW-bar dot opens the score-pool EV picks.
  // Self-contained; no league data touched.
  const [picksOpen, setPicksOpen] = React.useState(false);
  const openPicks = (e) => { if (e) { e.preventDefault(); e.stopPropagation(); } setPicksOpen(true); };

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiCall("GET", `/fixtures?gw=${gw}`)
      .then(list => {
        if (cancelled) return;
        const rows = (Array.isArray(list) ? list : []).map(normalizeFixtureRow);
        setFetched(rows);
        setLoading(false);
      })
      .catch(e => {
        if (cancelled) return;
        console.warn("Fixtures fetch failed for gw", gw, e);
        setFetched(null); // fall back to static
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [gw]);

  // Use live fixtures once loaded; otherwise the static GW4 round as a
  // placeholder (only meaningful for GW4, but harmless elsewhere while loading).
  const fixtures = fetched != null ? fetched : WC_FIXTURES_GW4;

  const byDay = {};
  fixtures.forEach(f => { (byDay[f.day] ||= []).push(f); });

  return (
    <div className="col" style={{ gap: 16 }}>
      <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Fixtures</h2>

      <div className="card-dark" style={{ overflow: "hidden" }}>
        <div style={{ background: "var(--grad-pill-active)", padding: isMobile ? "10px 12px" : "12px 20px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: isMobile ? 8 : undefined }}>
          <button className="btn btn--ghost-dark" style={{ padding: isMobile ? "6px 8px" : "6px 12px", fontSize: isMobile ? 11 : 12, background: "rgba(0,0,0,0.10)", border: "1px solid rgba(0,0,0,0.15)", flexShrink: isMobile ? 0 : undefined }} onClick={() => setGw(g => Math.max(1, g - 1))}>← GW{gw - 1}</button>
          <div className="m-min0" style={{ textAlign: "center", color: "var(--navy-900)" }}>
            <div className="h-display" style={{ fontSize: isMobile ? 15 : 18 }}>Gameweek {gw}</div>
            <div style={{ fontSize: isMobile ? 11 : 12, fontWeight: 600 }}>{round.wcRound} · {round.start} – {round.end}</div>
          </div>
          <button className="btn btn--ghost-dark" style={{ padding: isMobile ? "6px 8px" : "6px 12px", fontSize: isMobile ? 11 : 12, background: "rgba(0,0,0,0.10)", border: "1px solid rgba(0,0,0,0.15)", flexShrink: isMobile ? 0 : undefined }} onClick={() => setGw(g => Math.min(8, g + 1))} disabled={gw >= 8}>GW{gw + 1} →</button>
        </div>

        <div style={{ padding: isMobile ? "14px 12px" : "20px 28px", color: "white" }}>
          {isKnockout && (
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              {["bracket", "list"].map(v => (
                <button key={v} onClick={() => setView(v)}
                  className={"btn " + (view === v ? "btn--solid-dark" : "btn--ghost-dark")}
                  style={{ padding: "6px 16px", fontSize: 12 }}>
                  {v === "bracket" ? "Bracket" : "List"}
                </button>
              ))}
            </div>
          )}
          {view === "bracket" ? <WCBracketView /> : (
          <React.Fragment>
          {loading && fetched == null && (
            <div className="muted" style={{ padding: "12px 0", color: "rgba(255,255,255,0.6)" }}>Loading fixtures…</div>
          )}
          {!loading && fetched != null && fixtures.length === 0 && (
            <div className="muted" style={{ padding: "12px 0", color: "rgba(255,255,255,0.6)" }}>No fixtures scheduled for GW{gw}.</div>
          )}
          {Object.entries(byDay).map(([day, ms]) => (
            <div key={day} style={{ marginBottom: 18 }}>
              <div style={{ display: "inline-block", background: "var(--green-400)", color: "var(--navy-900)", padding: "4px 12px", borderRadius: 4, fontWeight: 800, fontSize: 11, letterSpacing: "0.06em", marginBottom: 8 }}>{day.toUpperCase()}</div>
              {ms.map((m, i) => {
                const h = teamById(m.home);
                const a = teamById(m.away);
                const hName = (h && h.name && h.grp !== "?") ? h.name : (m.homeName || (h && h.name) || m.home);
                const aName = (a && a.name && a.grp !== "?") ? a.name : (m.awayName || (a && a.name) || m.away);
                const grpLabel = round.wcRound.includes("Group")
                  ? (h && h.grp && h.grp !== "?" ? `Grp ${h.grp}` : "Group")
                  : round.wcRound;
                if (isMobile) {
                  return (
                    <div key={i} style={{ padding: "10px 0", borderBottom: "1px solid var(--border-dark)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, fontSize: 11, marginBottom: 6 }}>
                        <span className="muted">{m.time} <span style={{ opacity: 0.5 }}>local</span></span>
                        <span className="muted" style={{ color: "rgba(255,255,255,0.6)" }}>{m.venue}</span>
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto minmax(0,1fr)", gap: 6, alignItems: "center", fontSize: 12 }}>
                        <span className="m-min0" style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 6, fontWeight: 700 }}>
                          <span className="m-truncate">{hName}</span> <Flag team={h} />
                        </span>
                        <span style={{ textAlign: "center" }}>
                          <span className="pill pill--dark" style={{ background: "rgba(255,255,255,0.08)", fontSize: 11, color: "white" }}>
                            {grpLabel}
                          </span>
                        </span>
                        <span className="m-min0" style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700 }}>
                          <Flag team={a} /> <span className="m-truncate">{aName}</span>
                        </span>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={i} style={{ display: "grid", gridTemplateColumns: "120px 1fr 1fr 1fr 140px", padding: "12px 0", alignItems: "center", borderBottom: "1px solid var(--border-dark)", fontSize: 14 }}>
                    <span className="muted" style={{ fontSize: 12 }}>{m.time} <span style={{ opacity: 0.5 }}>local</span></span>
                    <span style={{ textAlign: "right", display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, fontWeight: 700 }}>
                      {hName} <Flag team={h} size="lg" />
                    </span>
                    <span style={{ textAlign: "center" }}>
                      <span className="pill pill--dark" style={{ background: "rgba(255,255,255,0.08)", fontSize: 11, color: "white" }}>
                        {grpLabel}
                      </span>
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 700 }}>
                      <Flag team={a} size="lg" /> {aName}
                    </span>
                    <span className="muted" style={{ fontSize: 11, textAlign: "right", color: "rgba(255,255,255,0.6)" }}>{m.venue}</span>
                  </div>
                );
              })}
            </div>
          ))}
          </React.Fragment>
          )}
        </div>
      </div>

      {/* Transfer-window timeline for this GW (what's open when, local times).
          Renders only for GWs the WINDOW schedule covers (current + next). */}
      <WindowTimeline gw={gw} title="Transfer windows" />

      {/* GW bar (jump) */}
      <div className="card" style={{ padding: "12px 16px", display: "flex", alignItems: "center", gap: 6, flexWrap: isMobile ? "wrap" : undefined }}>
        {[1,2,3,4,5,6,7,8].map(n => (
          <button key={n} onClick={() => setGw(n)}
            className={"btn " + (gw === n ? "btn--solid-dark" : "btn--ghost-dark")}
            style={{ flex: isMobile ? "1 1 22%" : 1, padding: "10px 0", fontSize: 12 }}>
            GW{n}
            <span style={{ display: "block", fontSize: isMobile ? 11 : 9, opacity: 0.7, fontWeight: 500, marginTop: 2 }}>{TOURNAMENT.gwDates[n].wcRound.replace("Group Stage · ", "")}</span>
          </button>
        ))}
        {/* secret: single-click → score-pool EV picks */}
        <span onClick={openPicks} aria-hidden="true"
          style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", width: 32, height: 32, marginLeft: 2, borderRadius: "50%", opacity: 0.35, cursor: "pointer", userSelect: "none", WebkitTapHighlightColor: "transparent", color: "var(--ink-500)", fontSize: 22 }}>•</span>
      </div>

      {window.BettingPicksModal
        ? React.createElement(window.BettingPicksModal, { open: picksOpen, onClose: () => setPicksOpen(false) })
        : null}
    </div>
  );
}


// ---------- LEAGUE STANDINGS ----------
function LeagueScreen({ onTab }) {
  const [tab, setTab] = React.useState("standings");
  const isMobile = useIsMobile();
  // Phase pill derives from the league config, not a hardcoded "Knockout
  // Phase" (same derivation as the shell identity card).
  const league = window.LEAGUE || LEAGUE;
  const curGw = (window.TOURNAMENT && window.TOURNAMENT.currentGw) || 1;
  const inKnockout = league.knockoutStartGw != null && league.knockoutStartGw <= curGw;
  return (
    <div className="col" style={{ gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: isMobile ? 10 : 16, flexWrap: isMobile ? "wrap" : undefined }}>
        <h2 className="h-display" style={{ fontSize: isMobile ? 22 : 26, margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{LEAGUE.name}</h2>
        <div className="row" style={{ gap: 8, flexShrink: 0 }}>
          <span className="pill pill--gold">{inKnockout ? "Knockout Phase" : "Group Phase"}</span>
          <span className="pill pill--dark" style={{ background: "var(--navy-900)", color: "white" }}>{LEAGUE.size} managers</span>
        </div>
      </div>

      <div className="card" style={{ padding: isMobile ? "4px 8px" : "4px 14px", display: "flex", gap: 4 }}>
        {[
          ["standings", "Standings"],
          ["schedule",  "Group Schedule"],
          ["results",   "Results"],
        ].map(([id, label]) => (
          <button key={id}
            className={"btn " + (tab === id ? "btn--solid-dark" : "")}
            style={{ padding: isMobile ? "10px 6px" : "10px 18px", fontSize: isMobile ? 12 : 13, flex: isMobile ? 1 : undefined, background: tab === id ? undefined : "transparent", color: tab === id ? undefined : "var(--ink-700)" }}
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
  // Live standings: the backend composes a LIVE overlay mid-GW (live:true +
  // updatedAt) so the table is never empty for an active league. Poll every
  // 60s while the tab is mounted; window.STANDINGS (app.jsx's one-shot fetch)
  // remains the instant first paint until our own fetch lands.
  const [liveData, setLiveData] = React.useState(null);
  const [sortBy, setSortBy] = React.useState("fpts"); // "fpts" (default) | "hpts" — client-side only
  const [squadModal, setSquadModal] = React.useState(null); // { uid, gw }
  // Read the league id at render time so the effect (re)starts once app.jsx's
  // league fetch lands (it force-updates the tree; [] deps would never rerun).
  const lid = window.LEAGUE && window.LEAGUE.id;
  React.useEffect(() => {
    if (!lid) return;
    let cancelled = false;
    const load = () => {
      apiCall("GET", `/leagues/${lid}/standings`)
        .then(d => { if (!cancelled && d && Array.isArray(d.managers)) setLiveData(d); })
        .catch(() => { /* keep the last good table on a transient blip */ });
    };
    load();
    const timer = setInterval(load, 60000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [lid]);
  // Store-backed fallback (always-live-data rule): while neither the live
  // per-GW feed nor the standings row has resolved, render skeleton rows —
  // never the data.jsx demo table.
  const standingsRow = useStoreRow("standings");
  const baseRows = (liveData && liveData.managers && liveData.managers.length)
    ? liveData.managers
    : (standingsRow.status === "ready" ? (standingsRow.value || []) : null);
  const standingsPending = baseRows === null;
  const isLive = !!(liveData && liveData.live);
  let updatedLabel = null;
  if (isLive && liveData.updatedAt) {
    const d = new Date(liveData.updatedAt);
    if (!isNaN(d)) updatedLabel = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  const rows = React.useMemo(() => {
    const arr = [...(baseRows || [])];
    arr.sort(sortBy === "hpts"
      ? (a, b) => ((b.hpts || 0) - (a.hpts || 0)) || ((b.fpts || 0) - (a.fpts || 0))
      : (a, b) => ((b.fpts || 0) - (a.fpts || 0)) || ((b.hpts || 0) - (a.hpts || 0)));
    return arr;
  }, [baseRows, sortBy]);
  // "This GW" = the league's current gameweek. The modal shows real per-player
  // points if that GW is finalised, otherwise the manager's current squad with
  // dashes (mid-GW / not yet played).
  const viewGw = (window.TOURNAMENT && window.TOURNAMENT.currentGw) || 1;
  // The qualification cut + round name come from the league config, not a
  // hardcoded "Top 8 / Quarter-Finals" (#48): a league can qualify any N.
  const qualifiers = (window.LEAGUE && window.LEAGUE.knockoutQualifiers) || 8;
  const ROUND_BY_QUALS = { 32: "Round of 32", 16: "Round of 16", 8: "Quarter-Finals", 4: "Semi-Finals", 2: "Final" };
  const roundName = ROUND_BY_QUALS[qualifiers] || "the Knockouts";
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      {squadModal && <ManagerSquadModal uid={squadModal.uid} gw={squadModal.gw} onClose={() => setSquadModal(null)} />}
      <div style={{ padding: "10px 18px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div className="row" style={{ gap: 8, minHeight: 26 }}>
          {isLive && (
            <span className="pill" style={{ background: "var(--hot-500)", color: "white", fontWeight: 800, letterSpacing: "0.06em" }}>● LIVE</span>
          )}
          {isLive && updatedLabel && (
            <span className="muted" style={{ fontSize: 11 }}>GW{liveData.gw || viewGw} points update live · {updatedLabel}</span>
          )}
        </div>
        <div className="row" style={{ gap: 4 }}>
          <span className="muted" style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Sort</span>
          {[["fpts", "Total FPts"], ["hpts", "H2H Pts"]].map(([id, label]) => (
            <button key={id}
              className={"btn " + (sortBy === id ? "btn--solid-dark" : "btn--ghost-dark")}
              style={{ padding: "6px 12px", fontSize: 11 }}
              onClick={() => setSortBy(id)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="table-scroll">
      <table className="table-clean table-clean--compact table-clean--standings">
        <thead>
          <tr>
            <th>#</th>
            <th>Manager</th>
            <th style={{ textAlign: "right" }}>W</th>
            <th style={{ textAlign: "right" }}>D</th>
            <th style={{ textAlign: "right" }}>L</th>
            <th style={{ textAlign: "right" }}>H2H Pts</th>
            <th style={{ textAlign: "right" }}>FPts</th>
            <th className="c-status"></th>
          </tr>
        </thead>
        <tbody>
          {standingsPending && Array.from({ length: 6 }).map((_, i) => (
            <tr key={`skel-${i}`}>
              <td className="num" style={{ width: 50 }}><Skel w={18} h={14} /></td>
              <td><Skel w={140} h={14} /></td>
              <td style={{ textAlign: "right" }}><Skel w={16} h={14} /></td>
              <td style={{ textAlign: "right" }}><Skel w={16} h={14} /></td>
              <td style={{ textAlign: "right" }}><Skel w={16} h={14} /></td>
              <td style={{ textAlign: "right" }}><Skel w={28} h={14} /></td>
              <td style={{ textAlign: "right" }}><Skel w={36} h={14} /></td>
              <td className="c-status"></td>
            </tr>
          ))}
          {rows.map((s, i) => {
            const m = managerById(s.uid);
            const t = teamById(m.flag);
            const isMe = s.uid === window.ME;
            const qualified = !s.knockedOut;
            // Draw the cut line right below the last qualifying place (only if
            // some teams actually miss out, and only when the displayed order
            // is the seeding order — the H2H sort; an FPts sort interleaves
            // qualified/eliminated rows so a positional line would mislead).
            const showQualLine = sortBy === "hpts" && i === qualifiers - 1 && qualifiers < rows.length;
            return (
              <React.Fragment key={s.uid}>
                <tr className={(isMe ? "is-me " : "") + (qualified ? "is-qualified" : "is-eliminated")}>
                  <td className="num c-rank" style={{ width: 50 }}>
                    <div className="row" style={{ gap: 6 }}>
                      <strong style={{ fontSize: 15 }}>{s.rank}</strong>
                      {s.mv > 0 && <span style={{ color: "var(--green-500)" }}>▲</span>}
                      {s.mv < 0 && <span style={{ color: "var(--hot-500)" }}>▼</span>}
                    </div>
                  </td>
                  <td className="c-mgr">
                    <div className="row" style={{ gap: 10, minWidth: 0 }}>
                      <ManagerFlag uid={s.uid} size="xl" fallback={t} />
                      <div style={{ minWidth: 0, flex: 1, cursor: "pointer" }}
                        onClick={() => setSquadModal({ uid: s.uid, gw: viewGw })}
                        title={`View ${m.team}'s squad & GW${viewGw} points`}>
                        <div style={{ fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textDecoration: "underline", textDecorationStyle: "dotted" }}>{m.team}</div>
                        <div className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>{m.name}</div>
                      </div>
                      {qualified && !s.ptsSeed && <span className="pill pill--gold" style={{ marginLeft: 4, flexShrink: 0 }}>H2H Seed</span>}
                      {qualified && s.ptsSeed && <span className="pill pill--teal" style={{ marginLeft: 4, flexShrink: 0 }}>Pts Seed</span>}
                    </div>
                  </td>
                  <td className="num c-chip" data-label="W" style={{ textAlign: "right" }}>{s.hw}</td>
                  <td className="num c-chip" data-label="D" style={{ textAlign: "right" }}>{s.hd}</td>
                  <td className="num c-chip" data-label="L" style={{ textAlign: "right" }}>{s.hl}</td>
                  <td className="num c-chip" data-label="H2H" style={{ textAlign: "right", fontWeight: 700 }}>{s.hpts}</td>
                  <td className="num c-chip" data-label="FPts" style={{ textAlign: "right" }}>{s.fpts}</td>
                  <td className="c-chip c-status" style={{ textAlign: "right", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    {qualified ? <span style={{ color: "var(--green-500)" }}>Qualified</span> : <span style={{ color: "var(--red-500)" }}>Eliminated</span>}
                  </td>
                </tr>
                {showQualLine && (
                  <tr className="c-fullrow">
                    <td colSpan="8" style={{ padding: 0 }}>
                      <div style={{ borderTop: "2px dashed var(--hot-500)", padding: "6px 14px", background: "rgba(255,62,108,0.05)", fontSize: 11, fontWeight: 700, color: "var(--hot-500)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                        ↑ Qualification Line · Top {qualifiers} enter {roundName}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
      </div>
      <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border)", fontSize: 12, color: "var(--ink-500)" }}>
        Top {qualifiers} qualify for {roundName}. H2H Seeds qualify on head-to-head record; Pts Seeds are the best remaining by fantasy points.
      </div>
    </div>
  );
}

function ScheduleTable() {
  const gws = window.LEAGUE?.leaguePhaseGws || [1, 2, 3, 4, 5, 6];
  const [squadModal, setSquadModal] = React.useState(null); // { uid, gw }
  const isMobile = useIsMobile();
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
              const ap = gwScores && gwScores[a] !== undefined ? gwScores[a] : (gw === window.TOURNAMENT.currentGw ? (window.GW_TOTALS[a] || 0) : "—");
              const bp = gwScores && gwScores[b] !== undefined ? gwScores[b] : (gw === window.TOURNAMENT.currentGw ? (window.GW_TOTALS[b] || 0) : "—");
              const hasScore = ap !== "—" && bp !== "—";
              const aWin = hasScore && Number(ap) > Number(bp);
              const isMe = a === window.ME || b === window.ME;
              const nameStyle = { cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted" };
              return (
                <div key={i} style={{ display: "grid", gridTemplateColumns: isMobile ? "minmax(0,1fr) auto minmax(0,1fr)" : "1fr 90px 1fr", gap: isMobile ? 6 : undefined, padding: isMobile ? "10px 12px" : "10px 18px", borderTop: "1px solid var(--border)", alignItems: "center", background: isMe ? "rgba(91,61,242,0.05)" : "transparent" }}>
                  <div className="m-min0" style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: isMobile ? 6 : 10, fontWeight: hasScore && aWin ? 700 : 500, fontSize: isMobile ? 13 : undefined }}>
                    <span className="m-truncate" style={nameStyle} onClick={() => setSquadModal({ uid: a, gw })}>{A.team}</span>
                    <ManagerFlag uid={a} size="lg" fallback={aT} />
                  </div>
                  <div style={{ textAlign: "center", fontFamily: "var(--font-num)", fontWeight: 800, fontSize: isMobile ? 14 : 16 }}>
                    <span style={{ color: hasScore && aWin ? "var(--navy-900)" : "var(--ink-500)" }}>{ap}</span>
                    <span style={{ color: "var(--ink-300)", margin: isMobile ? "0 4px" : "0 8px" }}>–</span>
                    <span style={{ color: hasScore && !aWin ? "var(--navy-900)" : "var(--ink-500)" }}>{bp}</span>
                  </div>
                  <div className="m-min0" style={{ display: "flex", alignItems: "center", gap: isMobile ? 6 : 10, fontWeight: !aWin ? 700 : 500, fontSize: isMobile ? 13 : undefined }}>
                    <ManagerFlag uid={b} size="lg" fallback={bT} />
                    <span className="m-truncate" style={nameStyle} onClick={() => setSquadModal({ uid: b, gw })}>{B.team}</span>
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
  const isMobile = useIsMobile();
  return (
    <div className="card" style={{ padding: 20 }}>
      {squadModal && <ManagerSquadModal uid={squadModal.uid} gw={squadModal.gw} onClose={() => setSquadModal(null)} />}
      <div className="h-display" style={{ fontSize: 16, marginBottom: 8 }}>Latest Results · GW3</div>
      <div className="muted" style={{ fontSize: 13 }}>Final H2H results from group stage MD3. Click a name to see their squad breakdown.</div>
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 12 }}>
        {(SCHEDULE[3] || []).map(([a, b], i) => {
          const A = managerById(a), B = managerById(b);
          const ap = GW_TOTALS[a], bp = GW_TOTALS[b];
          const nameStyle = { cursor: "pointer", textDecoration: "underline", textDecorationStyle: "dotted" };
          return (
            <div key={i} style={{ padding: "12px 14px", border: "1px solid var(--border)", borderRadius: 8, display: "grid", gridTemplateColumns: isMobile ? "minmax(0,1fr) auto minmax(0,1fr)" : "1fr auto 1fr", gap: isMobile ? 8 : 10, alignItems: "center" }}>
              <div className="m-min0" style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
                <span className="m-truncate" style={{ fontSize: 13, fontWeight: ap > bp ? 700 : 500, ...nameStyle }} onClick={() => setSquadModal({ uid: a, gw: 3 })}>{A.team}</span>
                <ManagerFlag uid={a} size="lg" fallback={teamById(A.flag)} />
              </div>
              <div className="mono" style={{ fontWeight: 800, fontSize: isMobile ? 16 : 18 }}>{ap}–{bp}</div>
              <div className="m-min0" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <ManagerFlag uid={b} size="lg" fallback={teamById(B.flag)} />
                <span className="m-truncate" style={{ fontSize: 13, fontWeight: bp > ap ? 700 : 500, ...nameStyle }} onClick={() => setSquadModal({ uid: b, gw: 3 })}>{B.team}</span>
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
  // Seed set when the user clicks "Trade" on a player in the Transfers table:
  // { targetUid, receiveId } pre-targets that manager + pre-ticks the player.
  const [seed, setSeed] = React.useState(null);
  React.useEffect(() => {
    const s = window.__TRADE_SEED;
    if (s) { window.__TRADE_SEED = null; setSeed(s); setShowPropose(true); }
  }, []);
  const isMobile = useIsMobile();
  const inbox = window.TRADES_INBOX || TRADES_INBOX;
  const outbox = window.TRADES_OUTBOX || TRADES_OUTBOX;
  // Manager↔manager trades open in the TRADE window AND the gameweek
  // (NEXT_GW_BID) window. In the gameweek window a proposal is a BID — it queues
  // up and, when the trade window opens, becomes a pending offer the other
  // manager must accept. It never executes on its own.
  const phase = (window.WINDOW && window.WINDOW.phase) || "none";
  const isBidWindow = phase === "next_gw_bid";
  const tradesOpen = phase === "trade" || isBidWindow;
  const phaseLabel = { free_agents: "free-agents window", none: "closed window" }[phase] || "this window";
  return (
    <div className="col" style={{ gap: 16 }}>
      {showPropose && tradesOpen && <ProposeTradeModal isBid={isBidWindow} initialTargetUid={seed?.targetUid} initialReceiveId={seed?.receiveId} onClose={() => { setShowPropose(false); setSeed(null); }} />}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: isMobile ? 10 : undefined, flexWrap: isMobile ? "wrap" : undefined }}>
        <h2 className="h-display" style={{ fontSize: isMobile ? 22 : 26, margin: 0 }}>Trades</h2>
        <button className="btn btn--primary" disabled={!tradesOpen}
          title={tradesOpen ? "" : `Manager trades are closed during the ${phaseLabel}`}
          style={{ opacity: tradesOpen ? 1 : 0.45, cursor: tradesOpen ? "pointer" : "not-allowed" }}
          onClick={() => tradesOpen && setShowPropose(true)}>{isBidWindow ? "+ Place Bid" : "+ Propose Trade"}</button>
      </div>
      {isBidWindow && (
        <div className="alert alert--green">
          <div className="alert__icon" style={{ background: "var(--green-500)" }}>⚡</div>
          <div>It's the <strong>gameweek window</strong> — place a <strong>bid</strong> now and it queues up. When the trade window opens it becomes a pending offer the other manager must <strong>accept</strong> (it never goes through on its own). You can cancel a bid any time before then.</div>
        </div>
      )}
      {!tradesOpen && (
        <div className="alert alert--gold">
          <div className="alert__icon" style={{ background: "var(--gold-500)" }}>⏳</div>
          <div>Manager trades are open during the <strong>trade window</strong> and as bids during the <strong>gameweek window</strong>. You're in the <strong>{phaseLabel}</strong> — you can still respond to existing offers and build your wishlist.</div>
        </div>
      )}

      <div className="card" style={{ padding: isMobile ? "4px 8px" : "4px 14px", display: "flex", gap: 4 }}>
        {[
          ["inbox", `Inbox (${inbox.length})`],
          ["outbox", `Sent (${outbox.length})`],
          ["history", "History"],
        ].map(([id, label]) => (
          <button key={id}
            className={"btn " + (tab === id ? "btn--solid-dark" : "")}
            style={{ padding: isMobile ? "10px 6px" : "10px 18px", fontSize: isMobile ? 12 : 13, flex: isMobile ? 1 : undefined, background: tab === id ? undefined : "transparent", color: tab === id ? undefined : "var(--ink-700)" }}
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
  const isMobile = useIsMobile();

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
        <span className="m-truncate" style={{ fontSize: 13, fontWeight: 700, whiteSpace: "nowrap" }}>
          {isIncoming ? `${proposer.team} offers a trade` : `Sent to ${target.team}`}
        </span>
        <span className="muted" style={{ color: "rgba(255,255,255,0.6)", fontSize: 12, whiteSpace: "nowrap" }}>{trade.createdAt}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr auto 1fr", padding: isMobile ? 14 : 20, gap: isMobile ? 10 : 16, alignItems: "center" }}>
        <div>
          <div className="muted" style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
            {isIncoming ? "You give" : "You give"}
          </div>
          {(isIncoming ? trade.targetPlayers : trade.proposerPlayers).map(id => {
            const p = playerById(id);
            const t = teamById(p.team);
            return (
              <div key={id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "var(--cream)", borderRadius: 8 }}>
                <div style={{ width: 36, height: 36, flexShrink: 0 }}><Jersey team={t} pos={p.pos} /></div>
                <div className="m-min0">
                  <div style={{ fontWeight: 700 }}>{p.name}</div>
                  <div className="muted m-truncate" style={{ fontSize: 12 }}>{POS_NAMES[p.pos]} · {t.name} · {p.pts} pts</div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="h-display" style={{ fontSize: isMobile ? 20 : 26, color: "var(--ink-300)", ...(isMobile ? { justifySelf: "center", transform: "rotate(90deg)" } : {}) }}>↔</div>
        <div>
          <div className="muted" style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
            {isIncoming ? "You get" : "You get"}
          </div>
          {(isIncoming ? trade.proposerPlayers : trade.targetPlayers).map(id => {
            const p = playerById(id);
            const t = teamById(p.team);
            return (
              <div key={id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "var(--cream)", borderRadius: 8 }}>
                <div style={{ width: 36, height: 36, flexShrink: 0 }}><Jersey team={t} pos={p.pos} /></div>
                <div className="m-min0">
                  <div style={{ fontWeight: 700 }}>{p.name}</div>
                  <div className="muted m-truncate" style={{ fontSize: 12 }}>{POS_NAMES[p.pos]} · {t.name} · {p.pts} pts</div>
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
      <div style={{ padding: isMobile ? "12px 14px" : "12px 20px", borderTop: "1px solid var(--border)", display: "flex", gap: 8, justifyContent: "space-between", alignItems: "center", flexWrap: isMobile ? "wrap" : undefined }}>
        {trade.status === "deferred_pending" ? (
          <>
            <span style={{ fontSize: 12, fontWeight: 700, color: "var(--green-600, #1a9d5a)" }}>
              ⚡ Gameweek bid · becomes a pending offer to accept when the trade window opens
            </span>
            {/* Not yet consented — either party may cancel before the window opens. */}
            <button className="btn btn--ghost-dark" disabled={busy} onClick={() => act("cancel")}>{busy ? "…" : (isIncoming ? "Reject bid" : "Cancel bid")}</button>
          </>
        ) : (
          <>
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
          </>
        )}
      </div>
    </div>
  );
}

// ---------- MANAGER SQUAD MODAL ----------
function ManagerSquadModal({ uid, gw, onClose }) {
  const m = managerById(uid);
  const isMobile = useIsMobile();
  // Per-GW breakdown from the immutable gw_history snapshot — the SAME source the
  // Points panel uses. It carries the frozen squad that was actually fielded for
  // this GW, each player's points FOR THIS GW, and the authoritative total. This
  // replaces the old GW3-only / season-total (GW_POINTS) logic, so the league
  // modal now shows real per-player points for any finished GW (#53), never a
  // season total (#52-class), and never the post-transfer squad (#50-class).
  const [snap, setSnap] = React.useState(undefined);       // undefined=loading, null=no snapshot
  const [fallbackIds, setFallbackIds] = React.useState(null);
  const [lineupsHidden, setLineupsHidden] = React.useState(false); // 403: pre-lock, not my squad

  React.useEffect(() => {
    let cancelled = false;
    setSnap(undefined);
    setFallbackIds(null);
    setLineupsHidden(false);
    const lid = window.LEAGUE && window.LEAGUE.id;
    if (!lid) { setSnap(null); return; }
    const loadCurrentSquad = () => {
      apiCall("GET", `/leagues/${lid}/squads/${uid}`)
        .then(res => { if (!cancelled) setFallbackIds((res.players || []).map(p => String(p.playerId))); })
        .catch(() => { if (!cancelled) setFallbackIds(uid === window.ME ? (window.MY_SQUAD_IDS || []) : []); });
    };
    apiCall("GET", `/leagues/${lid}/gw-history/${uid}?gw=${gw}`)
      .then(s => {
        if (cancelled) return;
        if (s && Array.isArray(s.players) && s.players.length) { setSnap(s); }
        else { setSnap(null); loadCurrentSquad(); }   // GW not finalized yet → show current squad, dashes
      })
      .catch(err => {
        if (cancelled) return;
        setSnap(null);
        // Pre-lock privacy: another manager's lineup is hidden until it locks
        // (backend 403) — show the notice instead of falling back to a list.
        if (err && err.status === 403) { setLineupsHidden(true); return; }
        loadCurrentSquad();
      });
    return () => { cancelled = true; };
  }, [uid, gw]);

  React.useEffect(() => {
    const k = e => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  // Resolve the player-id list + points map: prefer the frozen snapshot, else the
  // live squad (current/unplayed GW). `players === null` means still loading.
  const hasSnap = !!snap;
  const pointsMap = {};
  let players = null;
  let managerTotal = "—";
  if (hasSnap) {
    snap.players.forEach(pl => { pointsMap[String(pl.id)] = pl.points || 0; });
    players = [...(snap.starting || []), ...(snap.bench || [])].map(String);
    if (!players.length) players = snap.players.map(pl => String(pl.id));
    managerTotal = snap.totalPoints != null ? snap.totalPoints : "—";
  } else if (snap === null) {
    players = lineupsHidden ? [] : fallbackIds; // null while the fallback squad loads
  }

  // Pitch lineup for a snapshot (finalized or live-locked GW): order the
  // starting XI GK→DEF→MID→FWD and derive the formation from the players' real
  // positions — the same transform PointsScreen applies to its snapshot.
  const pitchLineup = React.useMemo(() => {
    if (!snap) return null;
    const ids = (snap.players || []).map(pl => pl.id);
    const starting = (Array.isArray(snap.starting) && snap.starting.length) ? snap.starting : ids.slice(0, 11);
    const bench = Array.isArray(snap.bench) ? snap.bench : ids.slice(11);
    const posOf = (rawId) => {
      const id = typeof rawId === "number" ? rawId : (isNaN(Number(rawId)) ? rawId : Number(rawId));
      const p = playerById(id);
      return p ? p.pos : 3;
    };
    const byPosRow = { 1: [], 2: [], 3: [], 4: [] };
    starting.forEach(id => { (byPosRow[posOf(id)] || byPosRow[3]).push(id); });
    const ordered = [...byPosRow[1], ...byPosRow[2], ...byPosRow[3], ...byPosRow[4]];
    const formation = [Math.max(1, byPosRow[1].length), byPosRow[2].length, byPosRow[3].length, byPosRow[4].length];
    return { starting: ordered, bench, formation };
  }, [snap]);

  // Group by position
  const byPos = { 1: [], 2: [], 3: [], 4: [] };
  if (players) {
    players.forEach(rawId => {
      const id = typeof rawId === "number" ? rawId : (isNaN(Number(rawId)) ? rawId : Number(rawId));
      const p = playerById(id);
      if (p && byPos[p.pos]) byPos[p.pos].push(p);
    });
  }

  // Snapshot present → real per-GW points (0 if the player didn't feature);
  // no snapshot (unplayed GW) → dash.
  const getGwPts = (p) => hasSnap ? (pointsMap[String(p.id)] ?? 0) : "—";

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 640, maxHeight: isMobile ? undefined : "88vh", overflowY: "auto" }} onClick={e => e.stopPropagation()}>
        <button className="modal__close" onClick={onClose}>×</button>
        <div style={{ padding: isMobile ? "20px 16px 12px" : "24px 24px 12px", borderBottom: "1px solid var(--border)", position: "relative" }}>
          <ManagerFlag uid={uid} size="hero"
            style={{ position: "absolute", top: isMobile ? 16 : 20, right: isMobile ? 48 : 56, width: isMobile ? 96 : 144, height: isMobile ? 64 : 96 }} />
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            Squad Breakdown · GW{gw}
            {hasSnap && snap.live && (
              <span className="pill" style={{ marginLeft: 8, background: "var(--hot-500)", color: "white", fontWeight: 800 }}>● LIVE</span>
            )}
          </div>
          <div className="h-display" style={{ fontSize: 24, marginTop: 4, paddingRight: isMobile ? 110 : 170 }}>{m?.team || "Squad"}</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{m?.name}</div>
          <div style={{ marginTop: 12, display: "inline-flex", alignItems: "center", gap: 10, background: "var(--navy-900)", color: "white", padding: "10px 16px", borderRadius: 10 }}>
            <span style={{ fontSize: 12, opacity: 0.7 }}>GW{gw} {hasSnap && snap.live ? "Live" : "Total"}</span>
            <span className="mono" style={{ fontSize: 26, fontWeight: 800, color: "var(--gold-500)" }}>{managerTotal}</span>
            <span style={{ fontSize: 12, opacity: 0.5 }}>pts</span>
          </div>
        </div>

        {hasSnap && pitchLineup ? (
          /* Finalized or live-locked GW → pitch view with per-player GW points
             (same renderer as the Points screen; bench rendered below). */
          <div className="squad-modal-pitch" style={{ padding: isMobile ? "12px 10px 20px" : "16px 20px 24px" }}>
            <Pitch lineup={pitchLineup} mode="points" pointsById={pointsMap} />
          </div>
        ) : lineupsHidden ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--ink-500)" }}>
            Lineups are hidden until they lock for GW{gw}. Check back at kickoff.
          </div>
        ) : players === null ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--ink-500)" }}>Loading squad…</div>
        ) : players.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--ink-500)" }}>No squad data available.</div>
        ) : (
          <div style={{ padding: isMobile ? "12px 16px 24px" : "12px 24px 24px" }}>
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
                      <div key={p.id} style={{ display: "grid", gridTemplateColumns: isMobile ? "36px minmax(0,1fr) auto" : "36px 1fr auto", gap: 10, padding: "8px 0", borderBottom: "1px solid var(--border)", alignItems: "center" }}>
                        <div style={{ width: 36, height: 36 }}><Jersey team={t} pos={p.pos} /></div>
                        <div className="m-min0">
                          <div style={{ fontWeight: 700 }}>{p.name} {isElim && <span className="pill pill--red" style={{ fontSize: isMobile ? 11 : 9, marginLeft: 4 }}>OUT</span>}</div>
                          <div className="muted m-truncate" style={{ fontSize: 12 }}>{t?.name} · {POS_NAMES[p.pos]}</div>
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
function ProposeTradeModal({ onClose, isBid, initialTargetUid, initialReceiveId }) {
  const [step, setStep] = React.useState(1);
  const [targetUid, setTargetUid] = React.useState(null);
  const [theirPlayers, setTheirPlayers] = React.useState(null);
  const [mySelected, setMySelected] = React.useState(new Set());
  // Pre-tick the player the user clicked "Trade" on (the one they want to
  // receive). Seed the player object's OWN id (single canonical form) — the same
  // value toggleTheir/countByPos use. Seeding two forms double-counts the player
  // in countByPos and breaks position validation.
  const [theirSelected, setTheirSelected] = React.useState(() => {
    if (initialReceiveId == null) return new Set();
    const p = playerById(Number(initialReceiveId)) || playerById(String(initialReceiveId));
    return new Set([p && p.id != null ? p.id : Number(initialReceiveId)]);
  });
  const [submitting, setSubmitting] = React.useState(false);
  const isMobile = useIsMobile();

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
      alert(isBid
        ? "Bid placed! When the trade window opens it becomes a pending offer the other manager must accept — it won't go through without their OK. You can cancel it any time before then."
        : "Trade proposal sent! Awaiting their response.");
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

  // Seeded from the Transfers "Trade" button: jump straight to step 2 with the
  // chosen manager's squad loaded (the player is already ticked via state init).
  React.useEffect(() => {
    if (initialTargetUid) handleSelectManager(initialTargetUid);
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
          display: "grid", gridTemplateColumns: isMobile ? "28px minmax(0,1fr) auto" : "28px 1fr auto", gap: 8,
          padding: "8px 10px", cursor: "pointer", borderRadius: 6, marginBottom: 2,
          background: isSel ? "rgba(91,61,242,0.12)" : "transparent",
          border: isSel ? "1px solid rgba(91,61,242,0.35)" : "1px solid transparent",
          opacity: isElim ? 0.55 : 1,
        }}>
        <div style={{ width: 28, height: 28 }}><Jersey team={t} pos={p.pos} /></div>
        <div className="m-min0">
          <div style={{ fontWeight: 700, fontSize: 13 }}>{p.name}</div>
          <div className="m-truncate" style={{ fontSize: 11, color: "var(--ink-500)" }}>{POS_NAMES[p.pos]} · {t?.name}</div>
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
      <div className="modal" style={{ maxWidth: step === 2 ? 760 : 500, maxHeight: isMobile ? undefined : "90vh", overflowY: "auto" }} onClick={e => e.stopPropagation()}>
        <button className="modal__close" onClick={onClose}>×</button>

        {/* Step 1 — pick manager */}
        {step === 1 && (
          <div style={{ padding: 24 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{isBid ? "Place Bid" : "Propose Trade"} · Step 1 of 2</div>
            <div className="h-display" style={{ fontSize: 22, margin: "6px 0 16px" }}>Who do you want to trade with?</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
              {managers.map(m => {
                const t = teamById(m.flag);
                return (
                  <button key={m.uid} onClick={() => handleSelectManager(m.uid)}
                    style={{ padding: "14px 16px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--cream)", textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", gap: 10, transition: "box-shadow 0.1s" }}
                    onMouseOver={e => e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.10)"}
                    onMouseOut={e => e.currentTarget.style.boxShadow = "none"}>
                    <ManagerFlag uid={m.uid} size="lg" fallback={t} />
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
            <div style={{ padding: isMobile ? "14px 16px" : "18px 24px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12 }}>
              <button className="btn btn--ghost-dark" style={{ padding: "6px 12px", fontSize: 12, flexShrink: isMobile ? 0 : undefined }} onClick={() => { setStep(1); setMySelected(new Set()); setTheirSelected(new Set()); }}>← Back</button>
              <div className="m-min0">
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{isBid ? "Place Bid" : "Propose Trade"} · Step 2 of 2</div>
                <div className="h-display" style={{ fontSize: isMobile ? 15 : 18, marginTop: 2 }}>Select players to swap with {targetMgr?.team}</div>
              </div>
            </div>

            {/* Squads side by side */}
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 0 }}>
              {/* My squad */}
              <div style={{ padding: isMobile ? 14 : 18, borderRight: isMobile ? undefined : "1px solid var(--border)", borderBottom: isMobile ? "1px solid var(--border)" : undefined }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
                  Your Squad — you give
                  {mySelected.size > 0 && <span className="pill pill--dark" style={{ marginLeft: 8, fontSize: isMobile ? 11 : 10 }}>{mySelected.size} selected</span>}
                </div>
                {[1, 2, 3, 4].map(pos => {
                  const list = mySquad.filter(p => p.pos === pos);
                  if (!list.length) return null;
                  return (
                    <div key={pos} style={{ marginBottom: 10 }}>
                      <div style={{ fontSize: isMobile ? 11 : 10, fontWeight: 700, color: "var(--ink-400)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 4 }}>
                        {POS_NAMES[pos]}s
                      </div>
                      {list.map(p => renderPlayerRow(p, mySelected, toggleMy, "my"))}
                    </div>
                  );
                })}
              </div>

              {/* Their squad */}
              <div style={{ padding: isMobile ? 14 : 18 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-500)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
                  {targetMgr?.team} — you receive
                  {theirSelected.size > 0 && <span className="pill pill--dark" style={{ marginLeft: 8, fontSize: isMobile ? 11 : 10 }}>{theirSelected.size} selected</span>}
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
                        <div style={{ fontSize: isMobile ? 11 : 10, fontWeight: 700, color: "var(--ink-400)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 4 }}>
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
            <div style={{ padding: isMobile ? "14px 16px" : "14px 24px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, background: "var(--cream)", flexWrap: isMobile ? "wrap" : undefined }}>
              <div style={{ fontSize: 13, color: posValid ? "var(--green-600)" : "var(--ink-500)" }}>
                {validationMsg() || "✓ Trade looks good — positions match!"}
              </div>
              <button className="btn btn--primary" style={{ flexShrink: 0 }}
                disabled={!posValid || submitting}
                onClick={handleSubmit}>
                {submitting ? "Sending…" : (isBid ? "Place Bid →" : "Send Trade Proposal →")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


// ---------- Scoring Audit (read-only, everyone) ----------
// Live reconciliation of the league scoring model: for every scored player we
// compare FIFA's live round total − the (capped) scouting bonus + our DefCon to
// the total we actually stored. Pure transparency — nothing here is editable.
function ScoreAuditScreen() {
  // Lazy: nothing is fetched until the user picks a scope and hits Run, so the
  // heavy whole-pool scan only happens on demand.
  const [mode, setMode] = React.useState("player");   // "player" | "nation" | "all"
  const [view, setView] = React.useState("players");  // table tab (players|nations)
  const [nationIso, setNationIso] = React.useState("");
  const [pquery, setPquery] = React.useState("");
  const [picked, setPicked] = React.useState(null);   // {id, name} for player mode
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState(false);

  // Nation list from the loaded teams (fallback: derive from the player pool).
  const nations = React.useMemo(() => {
    const teams = window.TEAMS || [];
    if (teams.length) return [...teams].map(t => ({ iso: t.id, name: t.name })).sort((a, b) => a.name.localeCompare(b.name));
    const seen = {};
    (window.PLAYERS || []).forEach(p => { if (p.team) seen[p.team] = p.teamName || p.team; });
    return Object.entries(seen).map(([iso, name]) => ({ iso, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, []);
  const q = pquery.trim().toLowerCase();
  const pmatches = !q ? [] : (window.PLAYERS || [])
    .filter(p => (p.name || "").toLowerCase().includes(q) || (p.club || "").toLowerCase().includes(q))
    .slice(0, 8);

  const run = React.useCallback((qs) => {
    setLoading(true); setErr(false);
    apiCall("GET", "/score-audit" + qs)
      .then(d => { setData(d); setView(d && d.scope === "nation" ? "players" : "players"); setLoading(false); })
      .catch(e => { console.warn("score-audit failed", e); setErr(true); setLoading(false); });
  }, []);

  const canRun = mode === "all" || (mode === "nation" && nationIso) || (mode === "player" && picked);
  const doRun = () => {
    if (mode === "player" && picked) run(`?player=${picked.id}`);
    else if (mode === "nation" && nationIso) run(`?nation=${encodeURIComponent(nationIso)}`);
    else if (mode === "all") run("?scope=all");
  };
  const openPlayer = (pid) => window.dispatchEvent(new CustomEvent("show-player-stats", { detail: { id: String(pid) } }));

  const num = { textAlign: "right", fontFamily: "var(--font-num)" };
  const th = { padding: "8px 10px", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--ink-500)" };
  const selStyle = { padding: "8px 12px", fontSize: 13, borderRadius: 8, border: "1px solid var(--border)", background: "white", color: "var(--ink-900)" };
  const Cell = ({ children, style }) => <td style={{ padding: "9px 10px", ...style }}>{children}</td>;
  const rows = data ? (view === "players" ? data.players : data.byNation) : [];

  return (
    <div className="col" style={{ gap: 16 }}>
      <div>
        <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Scoring Audit</h2>
        <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
          Live check · <strong>FIFA total − scouting bonus + DefCon</strong> vs the points we store. Read-only.
        </div>
      </div>

      {/* Scope picker — pick what to check, then Run (no auto-scan). */}
      <div className="card" style={{ padding: 14 }}>
        <div style={{ display: "inline-flex", padding: 3, background: "rgba(0,0,0,0.06)", borderRadius: 999, marginBottom: 12 }}>
          {[["player", "By player"], ["nation", "By nation"], ["all", "All players"]].map(([m, label]) => (
            <button key={m} className="btn" style={{ padding: "6px 16px", fontSize: 12, borderRadius: 999, background: mode === m ? "var(--navy-900)" : "transparent", color: mode === m ? "white" : "var(--ink-700)" }}
              onClick={() => { setMode(m); setData(null); }}>{label}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {mode === "player" && (
            <div style={{ position: "relative", flex: "1 1 280px", minWidth: 220 }}>
              <input value={picked ? picked.name : pquery} onChange={e => { setPicked(null); setPquery(e.target.value); }}
                placeholder="Search a player…" style={{ ...selStyle, width: "100%" }} />
              {!picked && pmatches.length > 0 && (
                <div style={{ position: "absolute", zIndex: 5, left: 0, right: 0, marginTop: 4, border: "1px solid var(--border)", borderRadius: 8, background: "white", overflow: "hidden", boxShadow: "var(--shadow, 0 4px 16px rgba(0,0,0,0.12))" }}>
                  {pmatches.map(p => (
                    <div key={p.id} onClick={() => { setPicked({ id: p.id, name: p.name }); setPquery(""); }}
                      style={{ padding: "8px 12px", cursor: "pointer", fontSize: 13, borderTop: "1px solid var(--border)" }}>
                      <strong>{p.name}</strong> <span className="muted" style={{ fontSize: 11 }}>· {p.teamName || p.team} · {POS_NAMES[p.pos]}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {mode === "nation" && (
            <select value={nationIso} onChange={e => setNationIso(e.target.value)} style={selStyle}>
              <option value="">Pick a nation…</option>
              {nations.map(n => <option key={n.iso} value={n.iso}>{n.name}</option>)}
            </select>
          )}
          {mode === "all" && <span className="muted" style={{ fontSize: 12 }}>Scans the whole pool — heavier, runs only when you click.</span>}
          <button className="btn btn--primary" style={{ padding: "8px 18px", fontSize: 13 }} onClick={doRun} disabled={!canRun || loading}>
            {loading ? "Checking…" : "Run check"}
          </button>
          {data && (
            <span className="pill" style={{ fontSize: 12, fontWeight: 800, padding: "5px 12px",
              background: data.mismatches ? "var(--red-500)" : "var(--green-500)", color: "white" }}>
              {data.mismatches ? `${data.mismatches} mismatch${data.mismatches === 1 ? "" : "es"}` : "All matched ✓"}
            </span>
          )}
          {/* Softer, separate condition: totals reconcile but some points still
              aren't itemized to a reason. Amber, not red — nothing's WRONG. */}
          {data && data.unexplainedPlayers > 0 && (
            <span className="pill" style={{ fontSize: 12, fontWeight: 800, padding: "5px 12px",
              background: "var(--amber-500, #f5a623)", color: "white" }}
              title="Totals match, but these players have FIFA points we couldn't itemize to a specific reason yet.">
              {data.unexplainedPlayers} with un-itemized points
            </span>
          )}
        </div>
      </div>

      {err && <div className="card" style={{ padding: 20, color: "var(--red-500)" }}>Couldn't run the check. Try again.</div>}

      {data && (
        <div className="card" style={{ overflow: "hidden" }}>
          {!data.fifaLive && (
            <div style={{ padding: "8px 14px", background: "rgba(255,200,68,0.18)", fontSize: 12, color: "#7a5a00" }}>
              FIFA live feed unreachable right now — comparing against the last stored FIFA points.
            </div>
          )}
          {/* Players/Nations table tabs only meaningful when there's >1 nation. */}
          {data.byNation && data.byNation.length > 1 && (
            <div style={{ display: "inline-flex", padding: 3, margin: 12, background: "rgba(0,0,0,0.06)", borderRadius: 999 }}>
              {[["players", "By player"], ["nations", "By nation"]].map(([m, label]) => (
                <button key={m} className="btn" style={{ padding: "5px 14px", fontSize: 12, borderRadius: 999, background: view === m ? "var(--navy-900)" : "transparent", color: view === m ? "white" : "var(--ink-700)" }} onClick={() => setView(m)}>{label}</button>
              ))}
            </div>
          )}
          <div className="table-scroll">
            <table className="table-clean" style={{ width: "100%", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "var(--cream)" }}>
                  <th style={{ ...th, textAlign: "left" }}>{view === "players" ? "Player" : "Nation"}</th>
                  {view === "players" && <th style={{ ...th, textAlign: "left" }}>Nation</th>}
                  {view === "nations" && <th style={{ ...th, textAlign: "right" }}>Players</th>}
                  <th style={{ ...th, textAlign: "right" }} title="FIFA live round total">FIFA</th>
                  <th style={{ ...th, textAlign: "right" }} title="Scouting bonus (excluded)">− Scout</th>
                  <th style={{ ...th, textAlign: "right" }} title="Our DefCon bonus (added)">+ DefCon</th>
                  <th style={{ ...th, textAlign: "right" }}>Expected</th>
                  <th style={{ ...th, textAlign: "right" }}>Ours</th>
                  <th style={{ ...th, textAlign: "right" }} title="FIFA points we still can't itemize to a specific reason (0 = every point is explained)">Unexpl.</th>
                  <th style={{ ...th, textAlign: "center" }}>✓</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan="9" style={{ padding: 24, textAlign: "center", color: "var(--ink-500)" }}>No scored players in this scope yet.</td></tr>
                )}
                {rows.map((a, i) => {
                  const clickable = view === "players";
                  return (
                    <tr key={i} style={{ borderTop: "1px solid var(--border)", background: a.match ? undefined : "rgba(231,76,60,0.07)", cursor: clickable ? "pointer" : undefined }}
                      onClick={clickable ? () => openPlayer(a.pid) : undefined}>
                      <Cell style={{ fontWeight: 700, color: clickable ? "var(--navy-900)" : undefined, textDecoration: clickable ? "underline" : undefined, textDecorationStyle: "dotted" }}>{view === "players" ? a.name : (a.team || a.iso || "—")}</Cell>
                      {view === "players" && <Cell style={{ color: "var(--ink-500)" }}>{a.team || a.iso}</Cell>}
                      {view === "nations" && <Cell style={num}>{a.players}</Cell>}
                      <Cell style={{ ...num, fontWeight: 700 }}>{a.fifaLive}</Cell>
                      <Cell style={{ ...num, color: a.scouting ? "var(--red-500)" : "var(--ink-300)" }}>{a.scouting ? `−${a.scouting}` : "0"}</Cell>
                      <Cell style={{ ...num, color: a.defcon ? "var(--green-600, #1a9d5a)" : "var(--ink-300)" }}>{a.defcon ? `+${a.defcon}` : "0"}</Cell>
                      <Cell style={{ ...num, fontWeight: 700 }}>{a.expected}</Cell>
                      <Cell style={{ ...num, fontWeight: 800, color: a.match ? "var(--navy-900)" : "var(--red-500)" }}>{a.stored}</Cell>
                      <Cell style={{ ...num, fontWeight: a.unexplainedAbs ? 800 : 400,
                        color: a.unexplainedAbs ? "var(--amber-600, #c77700)" : "var(--ink-300)" }}
                        title={a.unexplainedAbs ? "FIFA awarded points here we can't yet itemize to a specific reason" : "Every point is itemized with a reason"}>
                        {a.unexplainedAbs || "0"}</Cell>
                      <Cell style={{ textAlign: "center", fontWeight: 800, color: a.match ? "var(--green-600, #1a9d5a)" : "var(--red-500)" }}>{a.match ? "✓" : "✗"}</Cell>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div style={{ padding: "10px 14px", background: "var(--cream)", borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--ink-500)" }}>
            Expected = FIFA live total − scouting bonus (the part FIFA gives that we don't count) + your league's DefCon bonus. {view === "players" ? "Click a player to open their card. " : ""}A ✗ means our stored points are out of sync — a "Sync data" run heals it. <strong>Unexpl.</strong> is FIFA-awarded points we couldn't itemize to a specific reason yet; 0 means every point is explained — the total still reconciles either way.
          </div>
        </div>
      )}
    </div>
  );
}

Object.assign(window, { PlayerBrowserScreen, FixturesScreen, LeagueScreen, TradesScreen, ScoreAuditScreen });
