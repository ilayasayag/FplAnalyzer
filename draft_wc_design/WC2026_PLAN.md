# World Cup 2026 Fantasy Draft — System Plan

---

## 1. Tournament Structure

WC 2026: **48 teams, 12 groups of 4**. Each team plays 3 group stage matches. Total 104 matches.

### Fantasy Gameweek Calendar (8 GWs)

| GW | WC Round | Approx Dates | Phase |
|---|---|---|---|
| GW1 | Group Stage Round 1 | Jun 11–15 | Group |
| GW2 | Group Stage Round 2 | Jun 16–21 | Group |
| GW3 | Group Stage Round 3 | Jun 22–26 | Group |
| GW4 | Round of 32 | Jul 1–4 | Knockout |
| GW5 | Round of 16 | Jul 5–8 | Knockout |
| GW6 | Quarter-finals | Jul 10–12 | Knockout |
| GW7 | Semi-finals | Jul 14–15 | Knockout |
| GW8 | Final + 3rd Place | Jul 18–19 | Knockout |

Transfer windows open **between** GWs. Lineup locks at **kickoff of first match** of each GW.

---

## 2. League Format & Knockout Rules

### Group Phase (always GWs 1–3)
All managers play a **round-robin H2H league** during the WC group stage (GWs 1–3), regardless of league size. Every manager plays one H2H match per GW.

### Knockout Phase — Size-Dependent Start

| League Size | Qualifiers | Knockout Starts | Bracket |
|---|---|---|---|
| **> 8 managers** | Top 8 | GW4 (Round of 32) | QF → SF → Final |
| **6–8 managers** | Top 4 | GW6 (Quarter-finals) | SF → Final |
| **< 6 managers** | Top 4 | GW6 (Quarter-finals) | SF → Final |

> **Key rule**: For 6–8 managers, the league plays full H2H for GWs 1–5 (group stage + Rounds of 32, 16, and QF as additional league rounds), then the top 4 enter a Semi-Final at GW6. For > 8 managers, knockout starts immediately at GW4 with the top 8.

### Qualification Seeding

**When N > 8 (top 8 qualify → QF):**
- Seed 1–4: 4 managers with best H2H record (sorted by H2H points, then total fantasy points)
- Seed 5–8: 4 managers with highest total fantasy points from the remaining managers
- Bracket: Seed 1 vs Seed 8, Seed 2 vs Seed 7, Seed 3 vs Seed 6, Seed 4 vs Seed 5

**When N ≤ 8 (top 4 qualify → SF):**
- Seed 1–2: 2 managers with best H2H record
- Seed 3–4: 2 managers with highest total fantasy points from the remaining managers
- Bracket: Seed 1 vs Seed 4, Seed 2 vs Seed 3

### Extended League Phase (6–8 managers only)
GWs 4–5 (Round of 32 and Round of 16) are **additional H2H league rounds** — managers continue earning H2H results and fantasy points that count toward the final standings used for SF seeding. The transfer windows also remain open between these GWs.

---

## 3. Firestore Database Schema

### Global Collections (shared across all leagues)

```
wc_config/
  tournament:
    currentGw: int
    status: "pre_draft" | "drafting" | "group_phase" | "knockout" | "complete"
    season: 2026
    gwDates:
      gw1: { start, end, wcRound: "Group Stage - 1", lockAt }
      gw2: { start, end, wcRound: "Group Stage - 2", lockAt }
      gw3: { start, end, wcRound: "Group Stage - 3", lockAt }
      gw4: { start, end, wcRound: "Round of 32",     lockAt }
      gw5: { start, end, wcRound: "Round of 16",     lockAt }
      gw6: { start, end, wcRound: "Quarter-Finals",  lockAt }
      gw7: { start, end, wcRound: "Semi-Finals",     lockAt }
      gw8: { start, end, wcRound: "Final",           lockAt }

wc_teams/{team_id}:
  id: int                     # api-sports team ID
  name: str                   # "Brazil"
  logo: str                   # URL
  group: str                  # "Group A"
  eliminated: bool
  eliminatedAfterGw: int | null

wc_players/{player_id}:       # ~1,248 players, synced from api-sports
  id: int
  name: str
  photo: str
  position: int               # 1=GK 2=DEF 3=MID 4=FWD
  positionName: str           # "GK"|"DEF"|"MID"|"FWD"
  teamId: int
  teamName: str
  eliminated: bool            # mirrors parent team's status

wc_fixtures/{fixture_id}:     # all 104 WC matches
  id: int
  gw: int
  wcRound: str
  homeTeam: { id, name }
  awayTeam: { id, name }
  kickoff: timestamp
  status: "scheduled" | "live" | "finished"
  score: { home: int, away: int }
  processedForFantasy: bool

  playerScores/{player_id}:   # subcollection, written after match ends
    fantasyPoints: int
    stats:
      minutes: int
      goals: int
      assists: int
      saves: int
      cleanSheet: bool
      goalsConceded: int
      yellowCards: int
      redCards: int
      penaltyMissed: int
      penaltySaved: int
      ownGoal: int
```

### Per-League Collections

```
leagues/{lid}:
  name, inviteCode, adminUid, status, maxMembers
  format: "h2h"
  pickTimer: int
  tradeApproval: "instant" | "vote" | "admin" | "none"
  currentGw: int
  groupPhaseGws: [1, 2, 3]
  knockoutStartGw: int           # computed at creation: 4 (N>8) or 6 (N≤8)
  leaguePhaseGws: [1,2,3] or [1,2,3,4,5]  # all GWs where H2H league plays
  knockoutQualifiers: 8 | 4

leagues/{lid}/members/{uid}:
  displayName, teamName
  draftPosition: int
  waiverPriority: int

leagues/{lid}/squads/{uid}:
  players: [{ playerId, name, position, positionName, teamId, teamName }]

leagues/{lid}/lineups/{uid}_{gw}:
  starting: [playerId × 11]
  bench: [playerId × 4]          # bench order matters for auto-subs
  formation: [1, def, mid, fwd]
  locked: bool
  autoSubsMade: [{ out, in }]

leagues/{lid}/scores/{gw}:
  results:
    {uid}: { points, playerScores: [{playerId, points, stats}], autoSubs }
  h2hResults:
    {uid}: { opponent: uid, result: "W"|"D"|"L", pointsFor, pointsAgainst }
  processed: bool

leagues/{lid}/schedule/{gw}:    # for ALL league-phase GWs (1-3 or 1-5)
  gw: int
  matches: [{ home: uid, away: uid, homePoints, awayPoints, finished }]

leagues/{lid}/standings:
  managers: [{
    uid, displayName, teamName,
    hw, hd, hl, hpts,            # H2H wins/draws/losses/points (W=3 D=1 L=0)
    fpts,                         # total fantasy points scored all season
    gwPoints: { "1": 45, "2": 60, ... }
  }]

leagues/{lid}/knockout/bracket:
  type: "qf_start" | "sf_start"
  rounds:
    qf: [{ home, away, homePoints, awayPoints, winner, gw }]  # only if N>8
    sf: [{ home, away, homePoints, awayPoints, winner, gw }]
    final: [{ home, away, homePoints, awayPoints, winner, gw }]
  champion: uid | null

leagues/{lid}/waivers/{waiver_id}:
  uid, playerIn, playerOut, priority, gw
  status: "pending" | "approved" | "rejected"
  createdAt

leagues/{lid}/trades/{trade_id}:
  proposerUid, targetUid
  proposerPlayers: [{ playerId, position, webName }]
  targetPlayers:   [{ playerId, position, webName }]
  status: "pending" | "awaiting_admin" | "awaiting_vote" | "accepted" | "declined" | "vetoed"
  vetoVotes: [uid]
  createdAt, resolvedAt

leagues/{lid}/transfer_windows/{window_id}:
  windowNumber: int              # 1–5
  openAt: timestamp
  closeAt: timestamp             # = first match kickoff of next GW
  status: "open" | "closed"
  transfersUsed: { uid: int }
  freeTransfers: 2
```

---

## 4. WC2026Client (`fpl_predictor/data/wc_api.py`)

Replaces `FPLClient` entirely. All data comes from `https://v3.football.api-sports.io` using key from `secrets.json`.

```python
class WC2026Client:
    API_BASE  = "https://v3.football.api-sports.io"
    WC_LEAGUE = 1
    WC_SEASON = 2026
    POSITION_MAP = {"G": 1, "D": 2, "M": 3, "F": 4}

    # Sync (run once pre-tournament, ~48 API calls)
    def sync_all_squads(self, db)               # populate wc_players + wc_teams
    def sync_fixtures(self, db)                  # populate wc_fixtures for all GWs

    # Player data (reads from Firestore cache)
    def get_player(self, player_id) -> dict
    def get_player_map(self) -> dict             # {id: player_dict}
    def get_players_by_position(self, pos) -> list
    def get_players_by_team(self, team_id) -> list
    def get_free_agents(self, lid, position=None) -> list

    # Live data (hits api-sports, with TTL caching)
    def get_live_fixtures(self) -> list          # currently in-progress
    def get_fixture_events(self, fid) -> list    # goals / cards / assists
    def get_fixture_player_stats(self, fid) -> dict  # per-player full stats

    # Team data
    def get_wc_teams(self) -> list
    def get_eliminated_teams(self) -> list
```

### Caching TTLs
| Data | TTL |
|---|---|
| Player squads | 7 days |
| Completed fixture stats | Permanent (never refetch once `processedForFantasy=true`) |
| Live fixture | 5 minutes |
| Upcoming fixture | 1 hour |

### Request Budget (100/day free tier)
- Pre-tournament squad sync: 48 requests (one-time)
- Match day: only poll `live` fixtures (not all 104). At peak, 3–4 games overlap → ~6 req/5-min cycle → ~60 req/3-hour match window
- Post-GW stats: 1 req/fixture × max 24 fixtures = 24 req/day
- Total per day: well under 100 with proper caching

---

## 5. Scoring Engine (`fpl_predictor/game/wc_scoring.py`)

### Scoring Table

| Stat | GK | DEF | MID | FWD |
|---|---|---|---|---|
| < 60 min played | 1 | 1 | 1 | 1 |
| 60+ min played | 2 | 2 | 2 | 2 |
| Goal scored | 10 | 6 | 5 | 4 |
| Assist | 3 | 3 | 3 | 3 |
| Clean sheet | 4 | 4 | 1 | 0 |
| Goals conceded | -1 per 2 | -1 per 2 | 0 | 0 |
| Yellow card | -1 | -1 | -1 | -1 |
| Red card | -3 | -3 | -3 | -3 |
| Saves (per 3) | 1 | — | — | — |
| Own goal | -2 | -2 | -2 | -2 |
| Penalty missed | -2 | -2 | -2 | -2 |
| Penalty saved | 5 | — | — | — |

All stats come from `GET /fixtures/players?fixture={id}`. Own goals are inferred from `GET /fixtures/events?fixture={id}`.

### Score Processing Flow

```
process_fixture(fixture_id):
  1. Fetch /fixtures/players and /fixtures/events from api-sports
  2. For each player in both teams:
       pts = compute_points(player.stats, player.position)
       write → wc_fixtures/{fid}/playerScores/{player_id}
  3. Mark wc_fixtures/{fid}.processedForFantasy = true
  4. Call update_league_gw_scores(fixture_id) for all active leagues

update_league_gw_scores(fixture_id):
  For each active league:
    For each manager whose starting XI includes a player from this fixture:
      Add their points to leagues/{lid}/scores/{gw}.results[uid].points
    Recompute running H2H result for this GW
    Update leagues/{lid}/standings.fpts (running total)

finalize_gw(lid, gw):
  1. Ensure all fixtures in GW are processed
  2. Run process_auto_subs() for all managers
  3. Recompute final GW scores after auto-subs
  4. Set H2H final W/D/L for each match in schedule/{gw}
  5. Update standings (hw/hd/hl/hpts, fpts)
  6. Mark scores/{gw}.processed = true
  7. Open transfer window for this league
  8. Check eliminations for this WC round
  9. If gw == last league-phase GW: trigger seed_knockout(lid)
     - For N>8: last league GW = 3, knockoutStartGw = 4
     - For N≤8: last league GW = 5, knockoutStartGw = 6
 10. Advance league.currentGw += 1
```

---

## 6. Group / League Phase

### What Happens at League Start
1. Admin creates league, sets `maxMembers`, `pickTimer`, `tradeApproval`
2. System computes `knockoutStartGw` and `leaguePhaseGws` based on `maxMembers`
3. Members join via invite code
4. Admin starts snake draft (15 rounds, WC player pool)
5. After draft: schedule generated for **all league-phase GWs** at once

### H2H Schedule Generation
- For N > 8: generate schedule for GWs 1–3 only
- For N ≤ 8: generate schedule for GWs 1–5 (group stage + R32 + R16 as extra league rounds)
- Uses existing `ScheduleManager.generate_schedule()` with `start_gw=1, end_gw=knockoutStartGw-1`
- Round-robin; cycle repeats if GWs > N-1 rounds needed

### Standings
Sorted by: `hpts` (H2H points: W=3, D=1, L=0) → then `fpts` (total fantasy points) as tiebreaker.

---

## 7. Knockout Seeding & Bracket

Triggered automatically when `finalize_gw(lid, gw = knockoutStartGw - 1)` completes.

```python
def seed_knockout(lid):
    standings = get_final_league_standings(lid)   # after all league-phase GWs
    n = len(standings)

    if n > 8:
        # 4 best H2H + 4 best points → QF
        by_h2h  = standings[:4]
        rest    = sorted(standings[4:], key=lambda x: -x['fpts'])
        by_pts  = rest[:4]
        seeds   = by_h2h + by_pts   # 8 total, ordered 1–8
        bracket = build_qf_bracket(seeds)   # 1v8, 2v7, 3v6, 4v5
        start_gw = 4

    else:   # n ≤ 8
        # 2 best H2H + 2 best points → SF
        by_h2h  = standings[:2]
        rest    = sorted(standings[2:], key=lambda x: -x['fpts'])
        by_pts  = rest[:2]
        seeds   = by_h2h + by_pts   # 4 total, ordered 1–4
        bracket = build_sf_bracket(seeds)   # 1v4, 2v3
        start_gw = 6

    save_bracket(lid, bracket)
    league.knockoutStartGw = start_gw

def advance_knockout(lid, gw):
    # Fires after each knockout GW finalizes
    current_round = get_active_bracket_round(lid, gw)
    for match in current_round:
        if match.homePoints > match.awayPoints:
            match.winner = match.home
        elif match.awayPoints > match.homePoints:
            match.winner = match.away
        else:
            # Tiebreaker: season total fpts → coin flip
            match.winner = resolve_tiebreak(match.home, match.away)
    generate_next_round(lid, current_round)
```

---

## 8. Transfer Windows

### Window Schedule

| Window | Opens | Closes | Notes |
|---|---|---|---|
| Window 1 | After GW1 finalized | First match of GW2 | First swap opportunity |
| Window 2 | After GW2 finalized | First match of GW3 | Pre-final group stage |
| Window 3 | After GW3 finalized | First match of GW4 | **Big window** — 16 teams eliminated |
| Window 4 | After GW4 finalized | First match of GW5 | Only if applicable |
| Window 5 | After GW5 finalized | First match of GW6 | Only if applicable |

> Windows 4 and 5 only exist for leagues where GWs 4–5 are still league-phase (N ≤ 8). For N > 8, the knockout starts at GW4 and transfers are blocked during knockout.

### Rules
- **2 free transfers per window** (no penalty for more — friends app, keep it simple)
- Transfers blocked while a GW is active (window closed)
- Valid squad composition (2GK/5DEF/5MID/3FWD) must be maintained after every transfer

### Transfer Validation
```
validate_transfer(lid, uid, player_in, player_out):
  1. Check transfer window is currently open
  2. Check player_out is in manager's squad
  3. Check player_in is not owned in this league
  4. Check player_in is not on waivers (must use waiver claim instead)
  5. Check squad remains valid after swap
  6. Execute swap, increment transfersUsed[uid]
```

---

## 9. Waivers

### When Players Enter the Waiver Pool
- Manager drops a player → immediately on waivers (48h claim window)
- National team is eliminated → affected players auto-enter waivers at next window open
- Start of each transfer window: all previously dropped, unclaimed players enter the pool

### Waiver Priority
- **Rolling format**: successful claim → that manager drops to bottom of queue
- Initial order: reverse draft order (last pick in draft = first waiver priority)

### Waiver Processing (once per transfer window, T+24h after window opens)
```
T+0  → Window opens, dropped players enter waivers
T+24h → process_waivers():
  Sort all pending claims by waiverPriority ASC (lower = higher priority)
  For each claim:
    if player_in already claimed in this run: → reject
    if player_out no longer in manager's squad: → reject
    else: execute swap, drop manager to bottom of queue → approve
T+24h to window_close → Free agent phase: FCFS pickup (instant)
```

---

## 10. Free Agents

- Any WC player not owned by a manager and not on waivers
- Available during open transfer window only
- Immediate pickup (no waiting period)
- Must maintain valid squad composition
- Counts as 1 of the 2 free transfers for the window

API: `GET /api/leagues/{lid}/free-agents?position=2&sort=points`

---

## 11. National Team Elimination

### Detection
```
check_eliminations(gw):
  if gw == 3:
    eliminated = teams finishing 3rd in group that aren't best 3rd-place qualifiers
  else:
    eliminated = teams that lost their knockout match in this GW
  for team_id in eliminated:
    wc_teams/{team_id}.eliminated = true
    wc_teams/{team_id}.eliminatedAfterGw = gw
    all wc_players where teamId == team_id: eliminated = true
```

### Impact on Squads
- Eliminated players score **0 points** in all future GWs (no matches to play)
- They still occupy squad slots (2GK/5DEF/5MID/3FWD quota applies)
- Auto-added to waiver pool at next window open
- Frontend notifies managers whose squads contain eliminated players
- Managers with all eliminated GKs on bench cannot field a valid starting XI → they must transfer

---

## 12. Squad Constraints & Lineup Management

### Squad (15 players)
- 2 GK, 5 DEF, 5 MID, 3 FWD

### Starting XI (11 players)
- 1 GK (required)
- 3–5 DEF
- 2–5 MID
- 1–3 FWD

### Lineup Lock
- `lockAt` = kickoff timestamp of the **earliest match** in that GW
- API rejects lineup changes after `lockAt`
- Stored in `wc_config/tournament.gwDates.gw{n}.lockAt`

### Auto-Substitution (fires after ALL GW matches complete)
```
For each manager:
  For each starting player who played 0 minutes across ALL GW fixtures:
    Find first bench player (in bench order) who:
      - played > 0 minutes AND
      - swapping them in keeps a valid formation
    If found: swap, record auto-sub
```

---

## 13. GW Point Validation

### Background Job: `poll_live_scores` (every 5 min on match days)
```
1. Fetch live fixtures from api-sports (1 request)
2. For each fixture that just reached "FT" status:
     if not processedForFantasy: process_fixture(fixture_id)
3. Check if all fixtures in current GW are processedForFantasy
   If yes: finalize_gw() for all active leagues
```

### Audit Endpoint (for manager transparency)
`GET /api/leagues/{lid}/scores/{gw}/audit`
Returns: full per-player, per-fixture breakdown so any manager can verify every point

### Score Integrity Rules
- Points are never recomputed from scratch after `processedForFantasy = true`
- If api-sports corrects a stat (e.g. goal disallowed), admin can trigger `reprocess_fixture(fid)`
- Auto-subs are applied only at GW finalization, not during live scoring

---

## 14. Complete API Endpoints

### WC Data
| Method | Path | Description |
|---|---|---|
| GET | `/api/wc/players` | All WC players (filter: position, team, owned) |
| GET | `/api/wc/players/{id}` | Single player + fantasy point history |
| GET | `/api/wc/teams` | National teams + elimination status |
| GET | `/api/wc/fixtures` | All 104 WC fixtures |
| GET | `/api/wc/gw/{n}` | GW info (dates, WC round, lockAt, status) |

### League Management
| Method | Path | Description |
|---|---|---|
| POST | `/api/leagues` | Create league |
| POST | `/api/leagues/{lid}/join` | Join with invite code |
| GET | `/api/leagues/{lid}` | League info + config |
| GET | `/api/leagues/{lid}/standings` | Full standings |
| GET | `/api/leagues/{lid}/knockout` | Knockout bracket state |
| GET | `/api/leagues/{lid}/scores/{gw}` | GW scores for all managers |
| GET | `/api/leagues/{lid}/scores/{gw}/audit` | Per-player point breakdown |
| GET | `/api/leagues/{lid}/schedule` | Full H2H schedule |

### Squad & Lineup
| Method | Path | Description |
|---|---|---|
| GET | `/api/leagues/{lid}/squads/{uid}` | Manager's squad |
| PUT | `/api/leagues/{lid}/lineup/{gw}` | Set lineup |
| GET | `/api/leagues/{lid}/lineup/{gw}` | Get lineup |

### Transfers
| Method | Path | Description |
|---|---|---|
| GET | `/api/leagues/{lid}/transfer-window` | Current window status |
| GET | `/api/leagues/{lid}/free-agents` | Available free agents |
| POST | `/api/leagues/{lid}/free-agent` | Pick up free agent (drop another) |
| GET | `/api/leagues/{lid}/waivers` | Pending waiver claims |
| POST | `/api/leagues/{lid}/waivers` | Submit waiver claim |
| DELETE | `/api/leagues/{lid}/waivers/{wid}` | Cancel waiver claim |
| POST | `/api/leagues/{lid}/trades` | Propose trade |
| POST | `/api/leagues/{lid}/trades/{tid}/respond` | Accept / decline / veto |

### Draft
| Method | Path | Description |
|---|---|---|
| POST | `/api/leagues/{lid}/draft/start` | Admin starts draft |
| GET | `/api/leagues/{lid}/draft/state` | Current draft state |
| POST | `/api/leagues/{lid}/draft/pick` | Make a pick |

### Admin
| Method | Path | Description |
|---|---|---|
| POST | `/api/leagues/{lid}/gw/finalize` | Manually finalize GW |
| POST | `/api/leagues/{lid}/knockout/generate` | Manually trigger seeding |
| POST | `/api/leagues/{lid}/waivers/process` | Manually process waivers |
| POST | `/api/leagues/{lid}/fixtures/{fid}/reprocess` | Reprocess a fixture's scores |

---

## 15. Background Processing

### Cloud Functions / Cron Jobs

**`poll_live_scores`** — every 5 minutes on match days:
```
if no GW currently active: return early (saves API requests)
live = wc_client.get_live_fixtures()          # 1 API request
for f in live:
  if f.status == "FT" and not f.processedForFantasy:
    process_fixture(f.id)
check if all GW fixtures done → finalize_gw()
```

**`daily_sync`** — once per day:
```
sync any new WC fixtures added by api-sports
check elimination status of all 48 teams
refresh player data if squad changes detected
```

### Frontend Real-Time Updates
- Frontend uses Firestore `onSnapshot` on `leagues/{lid}/scores/{gw}` for live point updates
- No client-side polling needed — Firestore pushes changes as scores update
- Draft room already uses this pattern

---

## 16. What Gets Reused vs. Built New

### Reuse Unchanged
| File | Notes |
|---|---|
| `game/leagues.py` | Works as-is |
| `game/draft.py` | Change `POSITION_QUOTA` to WC values; change player source to `WC2026Client` |
| `game/schedule.py` | Works as-is; `end_gw` param controls league-phase length |
| `game/trades.py` | Swap `fpl_client` for `wc_client` |
| Firebase Auth + Firestore | Unchanged |
| Flask app skeleton | Unchanged |

### Rewrite / Adapt
| File | Change |
|---|---|
| `data/fpl_api.py` | Replace with `data/wc_api.py` (WC2026Client) |
| `game/scoring.py` | Replace with `game/wc_scoring.py` (new table, fixture-based) |
| `game/squads.py` | Add transfer window gate; use `wc_client` for player data |
| `game/waivers.py` | Replace `fpl_client` calls; adapt waiver processing timing |

### Build New
| File | Description |
|---|---|
| `game/knockout.py` | Bracket seeding, generation, advancement |
| `game/transfer_window.py` | Window open/close, budget tracking, elimination-triggered waivers |
| `game/wc_gameweeks.py` | GW calendar, lockAt timestamps, WC round → GW mapping |
| `game/elimination_tracker.py` | Detect eliminated teams, trigger squad notifications |
| Frontend: knockout bracket | Visual bracket tree with advancing managers |
| Frontend: WC player browser | Filter by nation, position, owned/free/waiver status |

---

## 17. Implementation Order

The tournament starts **June 11, 2026** (~15 days away). Critical path first.

| # | Task | Effort | Blocks |
|---|---|---|---|
| 1 | `WC2026Client` + squad sync | 1 day | Everything |
| 2 | `wc_gameweeks.py` (hardcoded GW dates + lockAt) | 0.5 day | Scoring, lineup lock |
| 3 | `WCScoringEngine` (scoring table + process_fixture) | 1 day | Live points |
| 4 | Firestore schema (new global collections) | 0.5 day | All data ops |
| 5 | Draft integration (WC player pool in DraftEngine) | 1 day | Draft |
| 6 | Squad/lineup adaptation (wc_client dependency) | 1 day | Lineup management |
| 7 | Transfer window manager | 1 day | Transfers |
| 8 | Waiver/free agent adaptation | 0.5 day | Transfers |
| 9 | `KnockoutEngine` (seeding + bracket + advancement) | 1.5 days | Knockout |
| 10 | Background scoring job (poll + finalize) | 1 day | Live scoring |
| 11 | Elimination tracker | 0.5 day | Waiver auto-trigger |
| 12 | Frontend: WC player browser + knockout bracket view | 2 days | UX |
| **Total** | | **~11 days** | |

> **Items 1–6** must be done before the first match on June 11.
> **Items 7–12** can be completed during the tournament — transfers only open after GW1 ends (~June 16), knockout isn't needed until GW4 (July 1) or GW6 (July 10).
