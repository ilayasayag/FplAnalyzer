// =====================================================================
// WC26 — App orchestrator (router + tweaks)
// =====================================================================

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "leagueSize": 10,
  "gwPhase": "knockout",
  "themeAccent": "wc",
  "showElimToast": true,
  "compactMode": false
}/*EDITMODE-END*/;

const ACCENT_THEMES = {
  wc:    { grad: "linear-gradient(94deg, #4a1ba8 0%, #4329c4 30%, #1f6dd1 60%, #1ad2c4 100%)", pill: "linear-gradient(94deg, #2bf094 0%, #1be8d4 100%)" },
  fpl:   { grad: "linear-gradient(94deg, #2d0b6e 0%, #3b1aa9 25%, #2c8acd 60%, #1bd6c8 100%)", pill: "linear-gradient(94deg, #00ff87 0%, #02efff 100%)" },
  fire:  { grad: "linear-gradient(94deg, #4a0d6e 0%, #c41262 35%, #ec582a 70%, #ffc844 100%)", pill: "linear-gradient(94deg, #ffd56b 0%, #ff6388 100%)" },
  forest:{ grad: "linear-gradient(94deg, #0d2818 0%, #1f6b3e 35%, #2eb05c 65%, #ffc844 100%)", pill: "linear-gradient(94deg, #00e87b 0%, #ffd56b 100%)" },
};

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [tab, setTab] = React.useState("status");
  const [toastDismissed, setToastDismissed] = React.useState(false);

  // Apply theme accent via CSS custom props
  React.useEffect(() => {
    const theme = ACCENT_THEMES[t.themeAccent] || ACCENT_THEMES.wc;
    document.documentElement.style.setProperty("--grad-hero", theme.grad);
    document.documentElement.style.setProperty("--grad-pill-active", theme.pill);
  }, [t.themeAccent]);

  // Mock notification banner
  const showElim = t.showElimToast && !toastDismissed && (tab === "status" || tab === "pickteam");

  const renderScreen = () => {
    switch (tab) {
      case "status":    return <StatusScreen onTab={setTab} />;
      case "points":    return <PointsScreen onTab={setTab} />;
      case "pickteam":  return <PickTeamScreen onTab={setTab} />;
      case "transfers": return <TransfersScreen onTab={setTab} />;
      case "league":    return <LeagueScreen onTab={setTab} />;
      case "bracket":   return <BracketScreen onTab={setTab} />;
      case "fixtures":  return <FixturesScreen onTab={setTab} />;
      case "draft":     return <DraftRoomScreen onTab={setTab} />;
      case "players":   return <PlayerBrowserScreen onTab={setTab} />;
      case "trades":    return <TradesScreen onTab={setTab} />;
      case "create":    return <CreateLeagueScreen onTab={setTab} />;
      default:          return <StatusScreen onTab={setTab} />;
    }
  };

  // Use wide layout (no sidebar) on Draft, Bracket, Create, Fixtures pages
  const wideTabs = ["draft", "bracket", "create", "fixtures"];
  const isWide = wideTabs.includes(tab);

  return (
    <div data-screen-label={`WC26 · ${TABS.find(x => x.id === tab)?.label || tab}`}>
      <TopBar tweak={t} />
      <Hero tab={tab} />
      <SubNav tab={tab} onTab={setTab} />

      {showElim && (
        <div style={{ background: "linear-gradient(94deg, #c52836, #ff3e6c)", color: "white", padding: "10px 32px", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13, fontWeight: 600 }}>
          <span><strong>⚠ Group stage final:</strong> Italy, Morocco, Poland & 13 others eliminated. 3 of your players are dead. Open the transfer window before GW4 lock.</span>
          <div className="row" style={{ gap: 10 }}>
            <button className="btn btn--primary" style={{ padding: "6px 14px", fontSize: 11 }} onClick={() => setTab("transfers")}>Open transfers</button>
            <button onClick={() => setToastDismissed(true)} style={{ color: "white", padding: "2px 8px", fontSize: 18, opacity: 0.7 }}>×</button>
          </div>
        </div>
      )}

      <div className={"page " + (isWide ? "page--wide" : "")}>
        <main>{renderScreen()}</main>
        {!isWide && <Sidebar onTab={setTab} />}
      </div>

      <PlayerStatsModal />

      <TweaksPanel>
        <TweakSection label="League" />
        <TweakRadio label="League size" value={String(t.leagueSize)}
          options={["6", "10", "12"]}
          onChange={v => setTweak('leagueSize', Number(v))} />
        <div style={{ fontSize: 10, color: "rgba(41,38,27,0.55)", lineHeight: 1.4, marginTop: -4 }}>
          {t.leagueSize > 8 ? "→ Top 8 → QF/SF/Final (KO from GW4)" : "→ Top 4 → SF/Final (extended H2H until GW5)"}
        </div>

        <TweakSection label="Tournament phase" />
        <TweakRadio label="Current GW" value={t.gwPhase}
          options={["group", "knockout"]}
          onChange={v => setTweak('gwPhase', v)} />

        <TweakSection label="Visual" />
        <TweakColor label="Brand accent" value={t.themeAccent}
          options={["wc", "fpl", "fire", "forest"]}
          onChange={v => setTweak('themeAccent', v)} />

        <TweakSection label="Behaviour" />
        <TweakToggle label="Show elim banner" value={t.showElimToast}
          onChange={v => { setTweak('showElimToast', v); setToastDismissed(false); }} />
      </TweaksPanel>
    </div>
  );
}

// Boot
const root = ReactDOM.createRoot(document.getElementById("app"));
root.render(<App />);
