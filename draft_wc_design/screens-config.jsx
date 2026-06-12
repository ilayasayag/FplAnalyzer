// =====================================================================
// WC26 — Screens: Rules & Config Page (Ultra Configurable Rules)
// =====================================================================

function ConfigScreen({ onTab }) {
  const isMobile = useIsMobile();
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState(null); // { type: 'success'|'error', text: '' }
  
  // Scoring points state
  const [scoring, setScoring] = React.useState({
    appearUnder60: 1,
    appear60Plus: 2,
    goalGk: 10,
    goalDef: 6,
    goalMid: 5,
    goalFwd: 4,
    assistPoints: 3,
    csGk: 4,
    csDef: 4,
    csMid: 1,
    csFwd: 0,
    gcPenGk: -1,
    gcPenDef: -1,
    gcPenMid: 0,
    gcPenFwd: 0,
    yellowCardPoints: -1,
    redCardPoints: -3,
    ownGoalPoints: -2,
    penaltyMissPoints: -2,
    penaltySavePoints: 5,
    savesPerPointGk: 3
  });

  // Squad size limitations state
  const [squadLimit, setSquadLimit] = React.useState({
    totalPlayers: 15,
    gk: 2,
    def: 5,
    mid: 5,
    fwd: 3
  });

  // League manager boundaries state
  const [leagueSize, setLeagueSize] = React.useState({
    minManagers: 6,
    maxManagers: 10,
    optimalMin: 6,
    optimalMax: 10
  });

  // Standing bonus points state
  const [bonus, setBonus] = React.useState({
    gwTopScorerH2HBonus: 1
  });

  // Knockout promotions & slots criteria state
  const [knockout, setKnockout] = React.useState({
    qualifiersCount: 4,
    h2hSlots: 2,
    fptsSlots: 2,
    structure: "sf"
  });

  // League phase settings
  const [leaguePhase, setLeaguePhase] = React.useState({
    format: "h2h",
    customGameWeeksCount: ""
  });

  // Load tournament config rules on mount
  React.useEffect(() => {
    const fetchConfig = async () => {
      try {
        const data = await apiCall("GET", "/config");
        if (data && data.rules) {
          const r = data.rules;
          
          // Map scoring rules
          const sc = r.scoring || {};
          const goal = sc.goalPoints || {};
          const cs = sc.csPoints || {};
          const gc = sc.gcPointsPer2 || {};
          
          setScoring({
            appearUnder60: sc.appearUnder60 ?? 1,
            appear60Plus: sc.appear60Plus ?? 2,
            goalGk: goal["1"] ?? 10,
            goalDef: goal["2"] ?? 6,
            goalMid: goal["3"] ?? 5,
            goalFwd: goal["4"] ?? 4,
            assistPoints: sc.assistPoints ?? 3,
            csGk: cs["1"] ?? 4,
            csDef: cs["2"] ?? 4,
            csMid: cs["3"] ?? 1,
            csFwd: cs["4"] ?? 0,
            gcPenGk: gc["1"] ?? -1,
            gcPenDef: gc["2"] ?? -1,
            gcPenMid: gc["3"] ?? 0,
            gcPenFwd: gc["4"] ?? 0,
            yellowCardPoints: sc.yellowCardPoints ?? -1,
            redCardPoints: sc.redCardPoints ?? -3,
            ownGoalPoints: sc.ownGoalPoints ?? -2,
            penaltyMissPoints: sc.penaltyMissPoints ?? -2,
            penaltySavePoints: sc.penaltySavePoints ?? 5,
            savesPerPointGk: sc.savesPerPointGk ?? 3
          });

          // Map squad limit
          const sq = r.squadLimit || {};
          setSquadLimit({
            totalPlayers: sq.totalPlayers ?? 15,
            gk: sq.gk ?? 2,
            def: sq.def ?? 5,
            mid: sq.mid ?? 5,
            fwd: sq.fwd ?? 3
          });

          // Map league manager boundaries
          const lz = r.leagueSize || {};
          setLeagueSize({
            minManagers: lz.minManagers ?? 6,
            maxManagers: Math.min(lz.maxManagers ?? 10, 10),
            optimalMin: lz.optimalMin ?? 6,
            optimalMax: lz.optimalMax ?? 10
          });

          // Map standing bonus points
          const bn = r.bonus || {};
          setBonus({
            gwTopScorerH2HBonus: bn.gwTopScorerH2HBonus ?? 1
          });

          // Map knockout promotions & slots criteria
          const ko = r.knockout || {};
          const qCrit = ko.qualificationCriteria || {};
          setKnockout({
            qualifiersCount: ko.qualifiersCount ?? 4,
            h2hSlots: qCrit.h2hSlots ?? 2,
            fptsSlots: qCrit.fptsSlots ?? 2,
            structure: ko.structure ?? "sf"
          });

          // Map league phase format
          const lp = r.leaguePhase || {};
          setLeaguePhase({
            format: lp.format ?? "h2h",
            customGameWeeksCount: lp.customGameWeeksCount ?? ""
          });
        }
      } catch (err) {
        console.error("Failed to load rules config:", err);
        setMessage({ type: "error", text: "Failed to retrieve configuration from backend" });
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);

    // Build the rules structure exactly matching our proposed plan
    const updatedRules = {
      scoring: {
        appearUnder60: Number(scoring.appearUnder60),
        appear60Plus: Number(scoring.appear60Plus),
        goalPoints: {
          "1": Number(scoring.goalGk),
          "2": Number(scoring.goalDef),
          "3": Number(scoring.goalMid),
          "4": Number(scoring.goalFwd)
        },
        assistPoints: Number(scoring.assistPoints),
        csPoints: {
          "1": Number(scoring.csGk),
          "2": Number(scoring.csDef),
          "3": Number(scoring.csMid),
          "4": Number(scoring.csFwd)
        },
        gcPointsPer2: {
          "1": Number(scoring.gcPenGk),
          "2": Number(scoring.gcPenDef),
          "3": Number(scoring.gcPenMid),
          "4": Number(scoring.gcPenFwd)
        },
        yellowCardPoints: Number(scoring.yellowCardPoints),
        redCardPoints: Number(scoring.redCardPoints),
        ownGoalPoints: Number(scoring.ownGoalPoints),
        penaltyMissPoints: Number(scoring.penaltyMissPoints),
        penaltySavePoints: Number(scoring.penaltySavePoints),
        savesPerPointGk: Number(scoring.savesPerPointGk)
      },
      squadLimit: {
        totalPlayers: Number(squadLimit.totalPlayers),
        gk: Number(squadLimit.gk),
        def: Number(squadLimit.def),
        mid: Number(squadLimit.mid),
        fwd: Number(squadLimit.fwd)
      },
      leagueSize: {
        minManagers: Number(leagueSize.minManagers),
        maxManagers: Number(leagueSize.maxManagers),
        optimalMin: Number(leagueSize.optimalMin),
        optimalMax: Number(leagueSize.optimalMax)
      },
      bonus: {
        gwTopScorerH2HBonus: Number(bonus.gwTopScorerH2HBonus)
      },
      leaguePhase: {
        format: leaguePhase.format,
        customGameWeeksCount: leaguePhase.customGameWeeksCount ? Number(leaguePhase.customGameWeeksCount) : null
      },
      knockout: {
        qualifiersCount: Number(knockout.qualifiersCount),
        qualificationCriteria: {
          h2hSlots: Number(knockout.h2hSlots),
          fptsSlots: Number(knockout.fptsSlots)
        },
        structure: knockout.structure
      },
      leagueSizeRules: {
        "6": { "knockoutStartGw": 7, "leaguePhaseGws": [1,2,3,4,5,6], "knockoutQualifiers": 4, "knockoutStructure": "sf" },
        "7": { "knockoutStartGw": 7, "leaguePhaseGws": [1,2,3,4,5,6], "knockoutQualifiers": 4, "knockoutStructure": "sf" },
        "8": { "knockoutStartGw": 7, "leaguePhaseGws": [1,2,3,4,5,6], "knockoutQualifiers": 4, "knockoutStructure": "sf" },
        "9": { "knockoutStartGw": 4, "leaguePhaseGws": [1,2,3], "knockoutQualifiers": 8, "knockoutStructure": "qf" },
        "10": { "knockoutStartGw": 4, "leaguePhaseGws": [1,2,3], "knockoutQualifiers": 8, "knockoutStructure": "qf" }
      }
    };

    try {
      const response = await apiCall("POST", "/config", { rules: updatedRules });
      if (response && response.status === "ok") {
        setMessage({ type: "success", text: "Tournament rules saved and propagated successfully!" });
        
        // Refresh local tournament context variables
        TOURNAMENT.rules = updatedRules;
        try {
          window.location.reload(); // Refresh the app to pull all values instantly
        } catch(e) {}
      } else {
        setMessage({ type: "error", text: "Failed to persist configuration rules" });
      }
    } catch (err) {
      console.error("Save config rules exception:", err);
      setMessage({ type: "error", text: err.message || "An exception occurred during save operations" });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="card-dark" style={{ padding: 40, textAlign: "center" }}>
        <div className="mono" style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Loading dynamic config rules...</div>
        <div style={{ width: 30, height: 30, border: "3px solid rgba(255,255,255,0.1)", borderTop: "3px solid var(--green-400)", borderRadius: "50%", margin: "0 auto", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  return (
    <div className="cfg-screen" style={{ maxWidth: 1080, margin: "0 auto", padding: isMobile ? "0 0 40px" : "0 20px 40px" }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 28, ...(isMobile ? { flexWrap: "wrap", gap: 12 } : {}) }}>
        <div>
          <h2 className="h-display" style={{ fontSize: isMobile ? 24 : 32, margin: 0 }}>System Rules Config</h2>
          <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>Configure scoring tables, positional quotas, dynamic promotion criteria, and hybrid layouts.</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn btn--primary"
          style={{ padding: "14px 28px", fontSize: 13, fontWeight: 700, borderRadius: 10, boxShadow: "0 8px 24px rgba(43,240,148,0.25)" }}
        >
          {saving ? "Saving Rules..." : "Save Configuration"}
        </button>
      </div>

      {message && (
        <div
          className="alert"
          style={{
            background: message.type === "success" ? "rgba(43,240,148,0.08)" : "rgba(230,57,70,0.08)",
            color: message.type === "success" ? "#2bf094" : "#ff6b8b",
            border: `1px solid ${message.type === "success" ? "rgba(43,240,148,0.2)" : "rgba(230,57,70,0.2)"}`,
            padding: "16px 20px",
            borderRadius: 12,
            marginBottom: 24,
            fontWeight: 600,
            fontSize: 14,
            display: "flex",
            alignItems: "center",
            gap: 12
          }}
        >
          <span>{message.type === "success" ? "✓" : "⚠"}</span>
          <span>{message.text}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="col" style={{ gap: 24 }}>
        
        {/* Section 1: Points Scoring System */}
        <div className="card-dark" style={{ padding: 24, borderRadius: 16 }}>
          <div style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 20 }}>
            <h3 style={{ fontSize: 18, margin: 0, fontWeight: 700, color: "white" }}>1. Points Scoring Coefficient Matrix</h3>
            <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>Control dynamic points allocations computed per player position inside match score sheets.</p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 20 }}>
            
            <div className="col" style={{ gap: 12 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "var(--gold-500)", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: 4 }}>Goal Points</div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Goalkeeper Goal</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.goalGk} onChange={e => setScoring({ ...scoring, goalGk: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Defender Goal</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.goalDef} onChange={e => setScoring({ ...scoring, goalDef: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Midfielder Goal</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.goalMid} onChange={e => setScoring({ ...scoring, goalMid: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Forward Goal</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.goalFwd} onChange={e => setScoring({ ...scoring, goalFwd: e.target.value })} />
              </div>
            </div>

            <div className="col" style={{ gap: 12 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "var(--gold-500)", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: 4 }}>Clean Sheets</div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Goalkeeper CS</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.csGk} onChange={e => setScoring({ ...scoring, csGk: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Defender CS</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.csDef} onChange={e => setScoring({ ...scoring, csDef: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Midfielder CS</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.csMid} onChange={e => setScoring({ ...scoring, csMid: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Forward CS</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.csFwd} onChange={e => setScoring({ ...scoring, csFwd: e.target.value })} />
              </div>
            </div>

            <div className="col" style={{ gap: 12 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "var(--gold-500)", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: 4 }}>General Stats</div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Play &lt; 60 min</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.appearUnder60} onChange={e => setScoring({ ...scoring, appearUnder60: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Play &ge; 60 min</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.appear60Plus} onChange={e => setScoring({ ...scoring, appear60Plus: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Assist points</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.assistPoints} onChange={e => setScoring({ ...scoring, assistPoints: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>GK Saves (per 1pt)</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.savesPerPointGk} onChange={e => setScoring({ ...scoring, savesPerPointGk: e.target.value })} />
              </div>
            </div>

            <div className="col" style={{ gap: 12 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "var(--gold-500)", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: 4 }}>Cards & Penalties</div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Yellow Card</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.yellowCardPoints} onChange={e => setScoring({ ...scoring, yellowCardPoints: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Red Card</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.redCardPoints} onChange={e => setScoring({ ...scoring, redCardPoints: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Own Goal</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.ownGoalPoints} onChange={e => setScoring({ ...scoring, ownGoalPoints: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>Penalty Save GK</span>
                <input type="number" className="input-field" style={{ width: 70, textAlign: "center", padding: 6 }} value={scoring.penaltySavePoints} onChange={e => setScoring({ ...scoring, penaltySavePoints: e.target.value })} />
              </div>
            </div>

          </div>
        </div>

        {/* Section 2: Squad Positional Limits & optimal sizes */}
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 24 }}>
          
          <div className="card-dark" style={{ padding: 24, borderRadius: 16 }}>
            <div style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 20 }}>
              <h3 style={{ fontSize: 18, margin: 0, fontWeight: 700, color: "white" }}>2. Positional Squad Sizes</h3>
              <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>Control how many players at each position are required in drafted squad rosters.</p>
            </div>
            
            <div className="col" style={{ gap: 14 }}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Goalkeepers (GK)</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 8 }} value={squadLimit.gk} onChange={e => setSquadLimit({ ...squadLimit, gk: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Defenders (DEF)</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 8 }} value={squadLimit.def} onChange={e => setSquadLimit({ ...squadLimit, def: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Midfielders (MID)</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 8 }} value={squadLimit.mid} onChange={e => setSquadLimit({ ...squadLimit, mid: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Forwards (FWD)</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 8 }} value={squadLimit.fwd} onChange={e => setSquadLimit({ ...squadLimit, fwd: e.target.value })} />
              </div>
              <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: 10, marginTop: 6 }} className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontWeight: 700, fontSize: 13, color: "var(--gold-500)" }}>Total Squad Players</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 8, fontWeight: 700, border: "1px solid var(--gold-500)" }} value={squadLimit.totalPlayers} onChange={e => setSquadLimit({ ...squadLimit, totalPlayers: e.target.value })} />
              </div>
            </div>
          </div>

          <div className="card-dark" style={{ padding: 24, borderRadius: 16 }}>
            <div style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 20 }}>
              <h3 style={{ fontSize: 18, margin: 0, fontWeight: 700, color: "white" }}>3. Dynamic League Limits</h3>
              <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>Control the valid manager limits. Optimal size range is 6 to 10 managers.</p>
            </div>

            <div className="col" style={{ gap: 14 }}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Minimum League Managers</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 8 }} value={leagueSize.minManagers} onChange={e => setLeagueSize({ ...leagueSize, minManagers: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Maximum League Managers</span>
                <input type="number" min="6" max="10" className="input-field" style={{ width: 80, padding: 8 }} value={leagueSize.maxManagers} onChange={e => setLeagueSize({ ...leagueSize, maxManagers: Math.min(10, Math.max(6, parseInt(e.target.value) || 10)) })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Optimal size range minimum</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 8 }} value={leagueSize.optimalMin} onChange={e => setLeagueSize({ ...leagueSize, optimalMin: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Optimal size range maximum</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 8 }} value={leagueSize.optimalMax} onChange={e => setLeagueSize({ ...leagueSize, optimalMax: e.target.value })} />
              </div>
              <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: 10, marginTop: 6 }} className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontWeight: 700, fontSize: 13, color: "var(--gold-500)" }}>Top-Scorer Standing Bonus</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 8, fontWeight: 700, border: "1px solid var(--gold-500)" }} value={bonus.gwTopScorerH2HBonus} onChange={e => setBonus({ ...bonus, gwTopScorerH2HBonus: e.target.value })} />
              </div>
            </div>
          </div>

        </div>

        {/* Section 3: Group Phase & Promotion Rules */}
        <div className="card-dark" style={{ padding: 24, borderRadius: 16 }}>
          <div style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 20 }}>
            <h3 style={{ fontSize: 18, margin: 0, fontWeight: 700, color: "white" }}>4. Standings, Hybrid Promotions, & Bracket Rules</h3>
            <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>Control standing formats (H2H, Total points) and dynamic promotion splits to knockout rounds.</p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 24 }}>
            
            <div className="col" style={{ gap: 14 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "var(--gold-500)", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: 4 }}>League Format</div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Standing Structure</span>
                <select className="input-field" style={{ width: 140, padding: 6, background: "rgba(0,0,0,0.4)" }} value={leaguePhase.format} onChange={e => setLeaguePhase({ ...leaguePhase, format: e.target.value })}>
                  <option value="h2h">Head-to-Head</option>
                  <option value="total_points">Total Points</option>
                  <option value="hybrid">Hybrid H2H + FPTS</option>
                </select>
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Custom Group Stage GWs</span>
                <input type="number" placeholder="Default size rules" className="input-field" style={{ width: 140, padding: 6 }} value={leaguePhase.customGameWeeksCount} onChange={e => setLeaguePhase({ ...leaguePhase, customGameWeeksCount: e.target.value })} />
              </div>
            </div>

            <div className="col" style={{ gap: 14 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "var(--gold-500)", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: 4 }}>Promotion Slots</div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>H2H Promotion Slots</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 6 }} value={knockout.h2hSlots} onChange={e => setKnockout({ ...knockout, h2hSlots: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>FPTS Promotion Slots</span>
                <input type="number" className="input-field" style={{ width: 80, padding: 6 }} value={knockout.fptsSlots} onChange={e => setKnockout({ ...knockout, fptsSlots: e.target.value })} />
              </div>
            </div>

            <div className="col" style={{ gap: 14 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "var(--gold-500)", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: 4 }}>Knockout Layout</div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Total Qualifiers Count</span>
                <input type="number" className="input-field" style={{ width: 100, padding: 6 }} value={knockout.qualifiersCount} onChange={e => setKnockout({ ...knockout, qualifiersCount: e.target.value })} />
              </div>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 13 }}>Bracket Structure</span>
                <select className="input-field" style={{ width: 100, padding: 6, background: "rgba(0,0,0,0.4)" }} value={knockout.structure} onChange={e => setKnockout({ ...knockout, structure: e.target.value })}>
                  <option value="sf">Semi-Finals</option>
                  <option value="qf">Quarter-Finals</option>
                </select>
              </div>
            </div>

          </div>
        </div>

      </form>
    </div>
  );
}

// Bind to window context
Object.assign(window, { ConfigScreen });
