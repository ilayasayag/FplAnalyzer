// =====================================================================
// WC26 — Screens: Draft Room (live snake draft) + Create/Join League
// =====================================================================

// ---------- DRAFT ROOM ----------
function DraftRoomScreen({ onTab }) {
  const [secondsLeft, setSecondsLeft] = React.useState(38);
  const [search, setSearch] = React.useState("");
  const [posFilter, setPosFilter] = React.useState("all");
  const [watchlist, setWatchlist] = React.useState(new Set(["p_alvarez", "p_modric", "p_courtois"]));

  const handleDraftPick = async (playerId) => {
    try {
      const lid = LEAGUE.id;
      const idKey = Math.random().toString(36).substring(2) + Date.now().toString(36);
      const numericId = isNaN(Number(playerId)) ? Number(String(playerId).replace("p_", "")) : Number(playerId);
      await apiCall("POST", `/leagues/${lid}/draft/pick`, { playerId: numericId, idempotencyKey: idKey });
    } catch(err) {
      alert("Draft pick failed: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  React.useEffect(() => {
    const t = setInterval(() => setSecondsLeft(s => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  const onClock = managerById(DRAFT_STATE.onTheClock) || { name: "TBD", team: "Draft Pending", flag: "GER" };
  const onClockTeam = teamById(onClock.flag) || teamById("GER");

  // Players already picked
  const taken = new Set(DRAFT_HISTORY.map(p => p.playerId));
  const pool = PLAYERS.filter(p => {
    if (taken.has(p.id)) return false;
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (posFilter !== "all" && p.pos !== Number(posFilter)) return false;
    return true;
  }).sort((a, b) => a.dr - b.dr);

  // Snake order projection for next ~10 picks
  const upcoming = [];
  let pickN = DRAFT_STATE.pickOverall || 1;
  let round = DRAFT_STATE.round || 1;
  let inRound = DRAFT_STATE.pickInRound || 1;
  const numManagers = MANAGERS.length || 10;
  while (upcoming.length < 8 && pickN <= (numManagers * 15)) {
    const order = round % 2 === 1 ? MANAGERS : [...MANAGERS].reverse();
    const uid = order[inRound - 1]?.uid;
    upcoming.push({ overall: pickN, round, uid });
    pickN++;
    inRound++;
    if (inRound > numManagers) { round++; inRound = 1; }
  }

  // My squad so far
  const myPicks = DRAFT_HISTORY.filter(p => p.uid === ME);
  const mySquadByPos = { 1: 0, 2: 0, 3: 0, 4: 0 };
  myPicks.forEach(p => { mySquadByPos[playerById(p.playerId).pos]++; });

  const formatTime = s => `0:${String(s).padStart(2, "0")}`;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 320px", gap: 16, minHeight: 700 }}>
      {/* LEFT — Draft order */}
      <div className="card-dark" style={{ overflow: "hidden", maxHeight: 700 }}>
        <div className="card-dark__title" style={{ fontSize: 14 }}>Draft Order</div>
        <div style={{ overflowY: "auto", maxHeight: 640 }}>
          {DRAFT_HISTORY.map((p, i) => {
            const m = managerById(p.uid);
            const t = teamById(m.flag);
            const pl = playerById(p.playerId);
            const plT = teamById(pl.team);
            return (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "36px 1fr 6px", gap: 8, padding: "8px 12px", borderBottom: "1px solid var(--border-dark)", alignItems: "center", fontSize: 12, opacity: 0.85 }}>
                <span className="mono" style={{ color: "rgba(255,255,255,0.5)", fontSize: 10, whiteSpace: "nowrap" }}>R{p.round}·{String(p.overall).padStart(2,"0")}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                  <Flag team={t} />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ color: "rgba(255,255,255,0.55)", fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.team}</div>
                    <div style={{ color: "white", fontWeight: 700, fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pl.name}</div>
                  </div>
                </div>
                <span style={{ width: 6, height: 22, background: plT.flag?.[0] || "#888", borderRadius: 1 }} />
              </div>
            );
          })}
          {/* On the clock */}
          <div style={{ padding: "12px 12px", borderBottom: "1px solid var(--border-dark)", background: "rgba(0,217,107,0.10)" }}>
            <div className="row" style={{ gap: 6, fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--green-400)", marginBottom: 6 }}>
              <span className="dot dot--green" /> On the clock · R{DRAFT_STATE.round}·{DRAFT_STATE.pickOverall}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Flag team={onClockTeam} size="lg" />
              <div>
                <div style={{ color: "white", fontWeight: 700 }}>{onClock.team}</div>
                <div style={{ color: "rgba(255,255,255,0.55)", fontSize: 11 }}>{onClock.name}</div>
              </div>
            </div>
          </div>
          {/* Upcoming */}
          {upcoming.slice(1).map((p, i) => {
            const m = managerById(p.uid);
            const t = teamById(m.flag);
            const isMe = p.uid === ME;
            return (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "36px 1fr", gap: 8, padding: "7px 12px", borderBottom: "1px solid var(--border-dark)", alignItems: "center", fontSize: 12, background: isMe ? "rgba(255,200,68,0.10)" : undefined }}>
                <span className="mono" style={{ color: "rgba(255,255,255,0.45)", fontSize: 10, whiteSpace: "nowrap" }}>R{p.round}·{String(p.overall).padStart(2,"0")}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6, color: isMe ? "var(--gold-500)" : "rgba(255,255,255,0.65)", minWidth: 0 }}>
                  <Flag team={t} /> <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{isMe ? <strong>You're up</strong> : m.team}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* CENTER — main draft area */}
      <div className="col" style={{ gap: 14 }}>
        {/* Clock */}
        <div className="card-dark" style={{ padding: "20px 24px", display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", gap: 20 }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 800, color: "rgba(255,255,255,0.6)", letterSpacing: "0.08em", textTransform: "uppercase" }}>On the clock · Round {DRAFT_STATE.round}</div>
            <div className="h-display" style={{ fontSize: 24, color: "white", marginTop: 2, display: "flex", alignItems: "center", gap: 10 }}>
              <Flag team={onClockTeam} size="lg" />
              {onClock.team}
            </div>
            <div className="muted" style={{ fontSize: 12, color: "rgba(255,255,255,0.55)" }}>Pick {DRAFT_STATE.pickOverall} of {DRAFT_STATE.totalPicks}</div>
          </div>
          <div style={{
            width: 130, height: 130,
            border: "5px solid " + (secondsLeft <= 15 ? "var(--red-500)" : "var(--green-400)"),
            borderRadius: "50%",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexDirection: "column",
            position: "relative",
          }}>
            <div className="mono" style={{ fontSize: 36, fontWeight: 800, color: "white", lineHeight: 1 }}>{formatTime(secondsLeft)}</div>
            <div style={{ fontSize: 9, fontWeight: 800, color: "rgba(255,255,255,0.6)", letterSpacing: "0.1em", marginTop: 2 }}>SECONDS</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: "rgba(255,255,255,0.6)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Next up</div>
            <div className="h-display" style={{ fontSize: 18, color: "white", marginTop: 2 }}>{managerById(upcoming[1].uid).team}</div>
            <div className="muted" style={{ fontSize: 12, color: "rgba(255,255,255,0.55)" }}>then {managerById(upcoming[2].uid).team}, {managerById(upcoming[3].uid).team}…</div>
          </div>
        </div>

        {/* Filters + player pool */}
        <div className="card-dark" style={{ padding: 18 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 12, marginBottom: 14 }}>
            <input
              type="text"
              placeholder="Search players…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ padding: "10px 14px", borderRadius: 999, border: "1px solid var(--border-dark-strong)", background: "rgba(255,255,255,0.08)", color: "white" }}
            />
            <div style={{ display: "inline-flex", padding: 3, background: "rgba(0,0,0,0.25)", borderRadius: 999 }}>
              {["all", "1", "2", "3", "4"].map(p => (
                <button key={p}
                  style={{
                    padding: "6px 14px", fontSize: 11, fontWeight: 700, borderRadius: 999,
                    background: posFilter === p ? "var(--green-400)" : "transparent",
                    color: posFilter === p ? "var(--navy-900)" : "white",
                  }}
                  onClick={() => setPosFilter(p)}>
                  {p === "all" ? "ALL" : POS_NAMES[Number(p)]}
                </button>
              ))}
            </div>
            <div style={{ display: "inline-flex", padding: 3, background: "rgba(0,0,0,0.25)", borderRadius: 999, color: "white", alignItems: "center", padding: "6px 12px", fontSize: 12 }}>
              <span style={{ opacity: 0.6 }}>Sort:</span>&nbsp;<strong>Draft rank</strong>
            </div>
          </div>

          <div style={{ background: "rgba(0,0,0,0.18)", padding: "8px 12px", borderRadius: 6, fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", color: "rgba(255,255,255,0.6)", display: "grid", gridTemplateColumns: "40px 1fr 100px 80px 80px 100px", gap: 8 }}>
            <span>DR</span>
            <span>PLAYER</span>
            <span>TEAM</span>
            <span style={{ textAlign: "center" }}>POS</span>
            <span style={{ textAlign: "right" }}>PROJ</span>
            <span></span>
          </div>
          <div style={{ maxHeight: 420, overflowY: "auto", marginTop: 4 }}>
            {pool.slice(0, 30).map(p => {
              const t = teamById(p.team);
              const isWatched = watchlist.has(p.id);
              return (
                <div key={p.id} style={{ display: "grid", gridTemplateColumns: "40px 1fr 100px 80px 80px 100px", gap: 8, padding: "10px 12px", borderTop: "1px solid var(--border-dark)", alignItems: "center", color: "white" }}>
                  <span className="mono" style={{ color: "rgba(255,255,255,0.6)" }}>{p.dr}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 30, height: 30 }}><Jersey team={t} pos={p.pos} /></div>
                    <div>
                      <div style={{ fontWeight: 700 }}>{p.name}</div>
                      <div style={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}>Group {t.grp}</div>
                    </div>
                  </div>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                    <Flag team={t} /> {t.id}
                  </span>
                  <span style={{ textAlign: "center" }}>
                    <span className="pill" style={{ background: "rgba(255,255,255,0.10)", color: "white", fontSize: 10 }}>{POS_NAMES[p.pos]}</span>
                  </span>
                  <span className="mono" style={{ textAlign: "right", fontWeight: 700 }}>{p.pts}</span>
                  <div className="row" style={{ gap: 4, justifyContent: "flex-end" }}>
                    <button
                      onClick={() => setWatchlist(prev => { const n = new Set(prev); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n; })}
                      style={{ padding: "4px 8px", fontSize: 14, background: "transparent", color: isWatched ? "var(--gold-500)" : "rgba(255,255,255,0.4)" }}>
                      {isWatched ? "★" : "☆"}
                    </button>
                    <button onClick={() => handleDraftPick(p.id)} className="btn btn--draft" style={{ padding: "5px 12px", fontSize: 11 }} disabled={!DRAFT_STATE.isMyTurn}>Draft</button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* RIGHT — my roster */}
      <div className="col" style={{ gap: 12 }}>
        <div className="card-dark">
          <div className="card-dark__title">My Squad ({myPicks.length}/15)</div>
          <div className="card-section" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, padding: 14 }}>
            <SquadCount label="GK" cur={mySquadByPos[1]} max={2} />
            <SquadCount label="DEF" cur={mySquadByPos[2]} max={5} />
            <SquadCount label="MID" cur={mySquadByPos[3]} max={5} />
            <SquadCount label="FWD" cur={mySquadByPos[4]} max={3} />
          </div>
          {myPicks.length === 0 ? (
            <div className="card-section" style={{ textAlign: "center", color: "rgba(255,255,255,0.55)", fontSize: 13 }}>
              Your picks will appear here.
            </div>
          ) : (
            myPicks.map((p, i) => {
              const pl = playerById(p.playerId);
              const plT = teamById(pl.team);
              return (
                <div key={i} className="card-section" style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px" }}>
                  <span className="mono" style={{ color: "rgba(255,255,255,0.4)", fontSize: 11 }}>R{p.round}</span>
                  <div style={{ width: 28, height: 28 }}><Jersey team={plT} pos={pl.pos} /></div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: 13 }}>{pl.name}</div>
                    <div style={{ color: "rgba(255,255,255,0.55)", fontSize: 11 }}>{POS_NAMES[pl.pos]} · {plT.id}</div>
                  </div>
                  <span className="mono" style={{ color: "var(--green-400)", fontWeight: 700, fontSize: 13 }}>{pl.pts}</span>
                </div>
              );
            })
          )}
        </div>

        <div className="card-dark">
          <div className="card-dark__title">★ Watchlist ({watchlist.size})</div>
          {[...watchlist].map(id => {
            const p = playerById(id);
            if (!p) return null;
            const t = teamById(p.team);
            return (
              <div key={id} className="card-section" style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px" }}>
                <div style={{ width: 24, height: 24 }}><Jersey team={t} pos={p.pos} /></div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: 13 }}>{p.name}</div>
                  <div style={{ color: "rgba(255,255,255,0.55)", fontSize: 11 }}>{t.id} · DR {p.dr}</div>
                </div>
                <button onClick={() => handleDraftPick(id)} className="btn btn--draft" style={{ padding: "4px 10px", fontSize: 10 }} disabled={!DRAFT_STATE.isMyTurn}>Draft</button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function SquadCount({ label, cur, max }) {
  const full = cur >= max;
  return (
    <div style={{ textAlign: "center", padding: "8px 0", background: "rgba(0,0,0,0.2)", borderRadius: 6, border: full ? "1px solid var(--green-400)" : "1px solid transparent" }}>
      <div style={{ fontSize: 10, fontWeight: 800, color: "rgba(255,255,255,0.6)", letterSpacing: "0.08em" }}>{label}</div>
      <div className="mono" style={{ fontSize: 16, fontWeight: 800, color: full ? "var(--green-400)" : "white" }}>{cur}/{max}</div>
    </div>
  );
}


// ---------- CREATE / JOIN LEAGUE ----------
function CreateLeagueScreen({ onTab }) {
  const [mode, setMode] = React.useState("home"); // home | create | join

  if (mode === "create") return <CreateForm onBack={() => setMode("home")} onTab={onTab} />;
  if (mode === "join") return <JoinForm onBack={() => setMode("home")} onTab={onTab} />;

  return (
    <div className="col" style={{ gap: 20 }}>
      <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Leagues</h2>

      {/* My league */}
      <div className="card-dark" style={{ padding: 0, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", top: 0, right: 0, padding: "6px 14px", background: "var(--green-400)", color: "var(--navy-900)", fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", borderRadius: "0 0 0 10px", whiteSpace: "nowrap" }}>ACTIVE LEAGUE</div>
        <div style={{ padding: 22, marginRight: 140 }}>
          <div className="h-display" style={{ fontSize: 24, marginBottom: 4 }}>{LEAGUE.name}</div>
          <div style={{ color: "rgba(255,255,255,0.75)", fontSize: 13, marginBottom: 14 }}>
            10 managers · Snake draft · H2H league with Round of 32 knockout
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            <MetricChip label="Your rank" value="#7 / 10" accent="var(--gold-500)" />
            <MetricChip label="Total points" value="179" />
            <MetricChip label="GW3 points" value="65" accent="var(--green-400)" />
            <MetricChip label="Status" value="QF Qualified" accent="var(--gold-500)" />
          </div>
          <div style={{ marginTop: 16, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <button className="btn btn--primary" onClick={() => onTab("status")}>Open League →</button>
            <span style={{ marginLeft: 8, fontSize: 12, color: "rgba(255,255,255,0.6)" }}>Invite code:</span>
            <span className="pill pill--ghost" style={{ background: "rgba(255,255,255,0.10)", border: "1px solid rgba(255,255,255,0.18)", fontFamily: "var(--font-num)" }}>{LEAGUE.inviteCode}</span>
          </div>
        </div>
      </div>

      {/* Create / Join cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card" style={{ padding: 24, cursor: "pointer", transition: "transform 0.12s, box-shadow 0.12s" }}
          onClick={() => setMode("create")}
          onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 8px 24px rgba(12,10,62,0.10)"; }}
          onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: "var(--grad-hero)", display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontSize: 24, fontWeight: 800, marginBottom: 16 }}>+</div>
          <div className="h-display" style={{ fontSize: 20, marginBottom: 4 }}>Create New League</div>
          <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
            Spin up a draft league with friends. Choose size, draft date, and house rules.
            We'll generate an invite code and schedule the H2H matchups.
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.06)", color: "var(--navy-800)" }}>4–16 managers</span>
            <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.06)", color: "var(--navy-800)" }}>Snake draft</span>
            <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.06)", color: "var(--navy-800)" }}>H2H + KO</span>
          </div>
        </div>

        <div className="card" style={{ padding: 24, cursor: "pointer", transition: "transform 0.12s, box-shadow 0.12s" }}
          onClick={() => setMode("join")}
          onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 8px 24px rgba(12,10,62,0.10)"; }}
          onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: "var(--gold-500)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--navy-900)", fontSize: 22, fontWeight: 800, marginBottom: 16 }}>→</div>
          <div className="h-display" style={{ fontSize: 20, marginBottom: 4 }}>Join with Code</div>
          <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
            Got a friend's invite code? Enter it here to join their league.
            Drafts must open before you can join — talk to the league admin.
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.06)", color: "var(--navy-800)" }}>Public + private</span>
            <span className="pill pill--dark" style={{ background: "rgba(12,10,62,0.06)", color: "var(--navy-800)" }}>Spectate available</span>
          </div>
        </div>
      </div>

      {/* Friends activity */}
      <div className="card" style={{ padding: 0 }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong>Friends are playing</strong>
          <span className="muted" style={{ fontSize: 12 }}>Public leagues with open spots</span>
        </div>
        {[
          { name: "Telegram Group Cup", size: "8/10", admin: "Yonatan", state: "Drafting Mon" },
          { name: "Office Pool 2026", size: "12/12", admin: "Roy", state: "Full" },
          { name: "Random Internet Strangers", size: "4/8", admin: "—", state: "Pre-draft" },
        ].map((l, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 100px 120px 100px", padding: "12px 18px", borderTop: "1px solid var(--border)", alignItems: "center", gap: 12 }}>
            <strong style={{ fontSize: 14 }}>{l.name}</strong>
            <span className="mono" style={{ fontSize: 13 }}>{l.size}</span>
            <span className="muted" style={{ fontSize: 12 }}>Admin · {l.admin}</span>
            <button className="btn btn--ghost-dark" style={{ padding: "6px 14px", fontSize: 11 }} disabled={l.state === "Full"}>
              {l.state === "Full" ? "Full" : "Join"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function MetricChip({ label, value, accent }) {
  return (
    <div style={{ background: "rgba(0,0,0,0.20)", padding: "10px 14px", borderRadius: 8 }}>
      <div style={{ fontSize: 10, fontWeight: 800, color: "rgba(255,255,255,0.6)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{label}</div>
      <div className="mono" style={{ fontSize: 18, fontWeight: 800, color: accent || "white", marginTop: 2 }}>{value}</div>
    </div>
  );
}

function CreateForm({ onBack, onTab }) {
  const [name, setName] = React.useState("");
  const [size, setSize] = React.useState(10);
  const [timer, setTimer] = React.useState(60);
  const [tradeRule, setTradeRule] = React.useState("vote");
  const [draftDate, setDraftDate] = React.useState("2026-06-08T18:00");

  const koStartGw = size > 8 ? 4 : 7;
  const qualifiers = size > 8 ? 8 : 4;
  const leaguePhase = size > 8 ? [1, 2, 3] : [1, 2, 3, 4, 5, 6];

  const handleCreate = async () => {
    try {
      const res = await apiCall("POST", "/leagues", {
        name,
        displayName: _auth.currentUser?.displayName || _auth.currentUser?.email.split("@")[0] || "Admin",
        maxMembers: size,
        pickTimer: timer,
        tradeApproval: tradeRule,
        draftAt: draftDate ? new Date(draftDate).toISOString() : undefined
      });
      alert(`League "${res.name}" created successfully!\nInvite Code: ${res.inviteCode}`);
      if (window.refreshActiveLeague) {
        await window.refreshActiveLeague();
      }
      onBack();
    } catch (err) {
      alert("Failed to create league: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  return (
    <div className="col" style={{ gap: 16 }}>
      <button onClick={onBack} className="muted" style={{ alignSelf: "flex-start", fontSize: 13 }}>← Back</button>
      <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Create New League</h2>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 16 }}>
        <div className="card" style={{ padding: 28 }}>
          <Field label="League name" hint="What you'll call it in chat">
            <input
              type="text" value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. World Cup Bros 2026"
              style={{ width: "100%", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border-strong)", fontSize: 15 }}
            />
          </Field>

          <Field label="League size" hint={`${size} managers · ${koStartGw === 4 ? "Standard format" : "Extended H2H format"}`}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 4 }}>
              {[6,7,8,9,10].map(n => (
                <button key={n}
                  className={"btn " + (size === n ? "btn--solid-dark" : "btn--ghost-dark")}
                  style={{ padding: "10px 0", fontSize: 13 }}
                  onClick={() => setSize(n)}>{n}</button>
              ))}
            </div>
            <div style={{ marginTop: 10, padding: "10px 12px", background: "rgba(91,61,242,0.06)", borderRadius: 6, fontSize: 12, color: "var(--navy-800)" }}>
              <strong>Structure:</strong> Group stage = H2H rounds GW{leaguePhase.join(", GW")}. Top {qualifiers} qualify for knockout starting GW{koStartGw} ({size > 8 ? "QF → SF → Final" : "SF → Final"}).
            </div>
          </Field>

          <Field label="Draft date" hint="When the snake draft begins">
            <input
              type="datetime-local" value={draftDate} onChange={e => setDraftDate(e.target.value)}
              style={{ padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border-strong)", fontSize: 15 }}
            />
          </Field>

          <Field label="Pick timer" hint="Seconds per draft pick">
            <div style={{ display: "flex", gap: 6 }}>
              {[30, 60, 90, 120].map(n => (
                <button key={n}
                  className={"btn " + (timer === n ? "btn--solid-dark" : "btn--ghost-dark")}
                  style={{ padding: "10px 18px", fontSize: 13 }}
                  onClick={() => setTimer(n)}>{n}s</button>
              ))}
            </div>
          </Field>

          <Field label="Trade approval" hint="How trades are vetted before going through">
            <div style={{ display: "flex", gap: 6 }}>
              {[
                ["instant", "Instant"],
                ["vote", "League vote"],
                ["admin", "Admin only"],
                ["none", "Disabled"],
              ].map(([v, l]) => (
                <button key={v}
                  className={"btn " + (tradeRule === v ? "btn--solid-dark" : "btn--ghost-dark")}
                  style={{ padding: "10px 16px", fontSize: 12 }}
                  onClick={() => setTradeRule(v)}>{l}</button>
              ))}
            </div>
          </Field>

          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", paddingTop: 14, borderTop: "1px solid var(--border)" }}>
            <button onClick={onBack} className="btn btn--ghost-dark">Cancel</button>
            <button onClick={handleCreate} className="btn btn--primary" disabled={!name}>Create League</button>
          </div>
        </div>

        {/* Preview */}
        <div className="card-dark" style={{ padding: 0, position: "sticky", top: 16, alignSelf: "start" }}>
          <div className="card-dark__title">Preview</div>
          <div className="card-section">
            <div style={{ fontSize: 11, opacity: 0.6, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>League name</div>
            <div className="h-display" style={{ fontSize: 18, marginTop: 4 }}>{name || "Untitled League"}</div>
          </div>
          <div className="card-section">
            <Stat label="Managers" value={`${size}`} />
            <Stat label="Squad size" value="15 (2/5/5/3)" />
            <Stat label="League phase" value={`GW1–${leaguePhase[leaguePhase.length - 1]}`} />
            <Stat label="Knockout starts" value={`GW${koStartGw}`} accent="var(--gold-500)" />
            <Stat label="Qualifiers" value={`Top ${qualifiers}`} />
            <Stat label="Pick timer" value={`${timer}s`} />
            <Stat label="Trade approval" value={tradeRule} />
          </div>
          <div className="card-section" style={{ fontSize: 12, opacity: 0.8 }}>
            Free transfers · 2 per window. Five windows between GW1–GW6.
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.04em", marginBottom: 4 }}>{label}</div>
      {hint && <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{hint}</div>}
      {children}
    </div>
  );
}

function JoinForm({ onBack }) {
  const [code, setCode] = React.useState("");
  const [displayName, setDisplayName] = React.useState(_auth.currentUser?.displayName || "");
  const [teamName, setTeamName] = React.useState("");

  const handleJoin = async () => {
    try {
      await apiCall("POST", "/leagues/join", {
        inviteCode: code,
        teamName: teamName || "Unnamed Team",
        displayName: displayName || _auth.currentUser?.email.split("@")[0] || "Manager"
      });
      alert("Joined league successfully!");
      if (window.refreshActiveLeague) {
        await window.refreshActiveLeague();
      }
      onBack();
    } catch (err) {
      alert("Failed to join league: " + (err.error || err.detail || JSON.stringify(err)));
    }
  };

  return (
    <div className="col" style={{ gap: 16, maxWidth: 520 }}>
      <button onClick={onBack} className="muted" style={{ alignSelf: "flex-start", fontSize: 13 }}>← Back</button>
      <h2 className="h-display" style={{ fontSize: 26, margin: 0 }}>Join a League</h2>
      <div className="card" style={{ padding: 28 }}>
        <Field label="Invite code" hint="Ask the league admin for the 8-character code">
          <input
            type="text" value={code} onChange={e => setCode(e.target.value.toUpperCase())}
            placeholder="WC26-XXXX"
            style={{ width: "100%", padding: "16px", borderRadius: 8, border: "1px solid var(--border-strong)", fontSize: 18, fontFamily: "var(--font-num)", letterSpacing: "0.06em", textAlign: "center" }}
          />
        </Field>
        <Field label="Display name" hint="What your friends will see in this league">
          <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)} style={{ width: "100%", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border-strong)", fontSize: 15 }} />
        </Field>
        <Field label="Team name" hint="Pick something memorable. You can change it later.">
          <input type="text" value={teamName} onChange={e => setTeamName(e.target.value)} placeholder="e.g. Hapoel Eliyahu" style={{ width: "100%", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border-strong)", fontSize: 15 }} />
        </Field>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onBack} className="btn btn--ghost-dark">Cancel</button>
          <button onClick={handleJoin} className="btn btn--primary" disabled={!code}>Join League</button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { DraftRoomScreen, CreateLeagueScreen });
