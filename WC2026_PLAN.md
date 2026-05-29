# World Cup 2026 Fantasy Draft — Master Plan

> **Single source of truth.** This document supersedes all previous versions.
> Reconciled against `PRODUCT_SPEC.md` (UI design package), live API tests, and confirmed rules.
> Last updated: 2026-05-29.

---

## 1. Tournament Structure

WC 2026: **48 teams, 12 groups of 4.** Each team plays 3 group stage matches. Total **104 matches, 8 fantasy GWs.**

### Gameweek Calendar

| GW | WC Round | Approx Dates | Fantasy Phase |
|---|---|---|---|
| GW1 | Group Stage Round 1 | Jun 11–15 | H2H League |
| GW2 | Group Stage Round 2 | Jun 16–21 | H2H League |
| GW3 | Group Stage Round 3 | Jun 22–26 | H2H League |
| GW4 | Round of 32 | Jun 27–Jul 4 | H2H League |
| GW5 | Round of 16 | Jul 5–9 | H2H League |
| GW6 | Quarter-finals | Jul 10–12 | H2H League (AAA for 6-player leagues) |
| GW7 | Semi-finals | Jul 14–15 | **Knockout SF** |
| GW8 | Final + 3rd Place | Jul 18–19 | **Knockout Final** |

> **League size is always 6–8 players.** The knockout phase is always GW7 (SF) + GW8 (Final). No QF bracket.

---

## 2. League Format & Knockout Rules

### League Size
**Always 6–8 players.** `maxMembers` must be in this range when creating a league.

### League Phase (GWs 1–6)

All managers play a **round-robin H2H league** for GWs 1–6. Points system:

| Result | H2H Points |
|---|---|
| Win | 3 |
| Draw | 1 |
| Loss | 0 |
| **GW top-scorer bonus** | **+1 (additive)** |

**GW top-scorer bonus**: After each GW, the manager(s) with the highest fantasy score in the league earn +1 additional H2H point. This stacks on top of the W/D/L result (e.g., win + bonus = 4 pts, draw + bonus = 2 pts). All managers tied at the highest score each receive the bonus.

**7-player leagues — bye week**: The odd manager out each GW has no H2H opponent. Bye = 0 H2H points. Their fantasy score still counts toward season total (`fpts`). They are still eligible for the top-scorer bonus.

**6-player leagues — GW6 all-against-all**: GW6 uses a ranking-based system instead of pairwise H2H:

| Rank | H2H Points |
|---|---|
| 1st (highest fpts) | 6 |
| 2nd | 4 |
| 3rd | 3 |
| 4th | 2 |
| 5th | 1 |
| 6th (lowest fpts) | 0 |

Ties: both tied managers receive the higher rank's points. GW top-scorer bonus still applies (all tied managers at the top also get +1).

Stored per league: `knockoutStartGw: 7`, `leaguePhaseGws: [1,2,3,4,5,6]`, `knockoutQualifiers: 4`.

### Knockout Seeding (fires on finalize of GW6)

**Always top 4 qualify. Always SF bracket: 1v4, 2v3.**

Qualification algorithm (overlap-resolution):
1. Take the top-2 by H2H points (`hpts`) — call them **H2H qualifiers**
   - Tiebreak: total fantasy points → draft order
2. From the remaining managers, take the top-2 by total fantasy points (`fpts`) — **fpts qualifiers**
   - Tiebreak: H2H points → draft order
   - Skip any manager already in step 1

This handles all overlap scenarios naturally. Example: if the same manager leads both H2H and fpts lists, they get H2H slot 1, and the "fpts quota" is filled from the next-best fpts manager not already qualified.

**Seeding tiebreaker chain:**
1. H2H points (`hpts`)
2. Total season fantasy points (`fpts`)
3. Draft order (earlier pick = seed priority)

### Knockout Match Rules
- Manager with more GW fantasy points advances
- **Tie → higher seed (lower seed number) advances** — deterministic, no coin flip
- If seeds equal: total season fpts → draft order

### Predictions (virtual bonus players)

Each manager can submit two predictions before GW1 lockAt:
- `predictedWinner`: national team they think will win the WC
- `predictedTopScorer`: player they think will be the WC top scorer

These act as **two virtual bonus players** on each manager's profile. Bonuses applied at GW8 finalization:
- Correct winner: **+15 fpts** added to season total
- Correct top scorer: **+10 fpts** added to season total

Predictions lock at GW1 kickoff. Stored in `members/{uid}.predictions`.

---

## 3. Firestore Database Schema

### 3.1 Global Collections

```
wc_config/tournament:
  currentGw: int                 # 1–8
  status: "pre_draft" | "drafting" | "group_phase" | "knockout" | "complete"
  season: 2026
  gwDates:
    gw{n}:
      start: timestamp
      end: timestamp
      wcRound: str               # "Group Stage - 1", "Round of 32", etc.
      lockAt: timestamp          # = kickoff of earliest match in GW
      status: "upcoming" | "active" | "completed"

wc_api_usage/{date}:
  requests: int                  # daily counter, alert if > 80

wc_teams/{team_id}:
  id: int                        # api-sports numeric ID
  name: str                      # "Brazil"
  isoCode: str                   # ISO-3166 alpha-2, for flag CDN
  logo: str                      # api-sports logo URL
  group: str                     # "A"–"L"
  eliminated: bool
  eliminatedAfterGw: int | null
  groupFinished: bool            # true after all GW3 group matches

wc_players/{player_id}:
  id: int                        # api-sports player ID
  name: str
  photo: str
  position: int                  # 1=GK 2=DEF 3=MID 4=FWD
  positionName: str
  teamId: int
  teamName: str
  teamIso: str                   # for flag display
  eliminated: bool               # denormalised from team — update atomically
  draftRank: int                 # default ordering in draft room

wc_fixtures/{fixture_id}:
  id: int
  gw: int
  wcRound: str
  homeTeam: { id, name, isoCode }
  awayTeam: { id, name, isoCode }
  kickoff: timestamp
  status: "scheduled" | "live" | "HT" | "FT" | "postponed" | "cancelled"
  score: { home: int, away: int, homeET: int, awayET: int }
  processedForFantasy: bool
  # subcollection:
  playerScores/{player_id}:
    fantasyPoints: int
    captainBonus: int            # extra pts if this player was captain this GW
    stats:
      minutes: int
      goals: int
      assists: int
      saves: int                 # in-play saves only (NOT shootout)
      cleanSheet: bool           # 0 goals conceded by player's team
      goalsConceded: int         # for GK/DEF scoring
      yellowCards: int
      redCards: int
      penaltyMissed: int
      penaltySaved: int          # in-play only
      penaltySavedShootout: int  # NOT counted in fantasy (shootout is separate)
      ownGoal: int
      bps: int                   # raw BPS from api-sports
      bonusPoints: int           # 3/2/1 for top 3 BPS in fixture
```

### 3.2 Per-League Collections

```
leagues/{lid}:
  name: str
  inviteCode: str                # 8-char base32, server-generated, unique
  adminUid: str
  status: "pre_draft" | "drafting" | "group_phase" | "knockout" | "complete"
  maxMembers: int                # 6–8 (always)
  pickTimer: int                 # seconds: 30|60|90|120|180|300
  tradeApproval: "instant"|"vote"|"admin"|"none"
  currentGw: int
  knockoutStartGw: int           # always 7
  leaguePhaseGws: int[]          # always [1,2,3,4,5,6]
  knockoutQualifiers: int        # always 4
  draftAt: timestamp             # scheduled draft time
  seasonStartedAt: timestamp

leagues/{lid}/members/{uid}:
  displayName: str
  teamName: str
  draftPosition: int             # 1..N, set when draft starts
  waiverPriority: int            # lower = higher priority; starts = reverse(draftPosition)
  kickedAt: timestamp | null     # set if admin kicked; blocks re-join
  leftAt: timestamp | null       # set if manager voluntarily left
  squadFrozen: bool              # true if manager left mid-tournament
  predictions:
    predictedWinner: str | null         # national team id
    predictedTopScorer: int | null      # player id
    predictionsLockedAt: timestamp | null

leagues/{lid}/draft/state:
  status: "pending"|"active"|"paused"|"complete"
  order: [uid]                   # snake order
  currentPick: int               # 0-indexed
  totalPicks: int                # N × 15
  pickDeadline: timestamp        # when current turn expires
  pickTimer: int
  pickedPlayerIds: [int]
  pausedAt: timestamp | null
  startedAt: timestamp
  # subcollection:
  picks/{pick_id}:
    pickNumber: int
    uid: str
    playerId: int
    playerName: str
    position: int
    autoPicked: bool

leagues/{lid}/draft/watchlists/{uid}:
  playerIds: [int]               # private to owner

leagues/{lid}/squads/{uid}:
  players: [
    { playerId, name, position, positionName, teamId, teamName, teamIso, eliminated }
  ]
  # always 15 during normal play; can be 14 during drop grace period

leagues/{lid}/lineups/{uid}_{gw}:
  starting: [playerId × 11]
  bench: [playerId × 4]          # bench[0] MUST be the non-starting GK
  formation: [1, def, mid, fwd]
  captain: playerId              # doubles points if played; required
  viceCaptain: playerId          # becomes captain if captain played 0 min; required
  locked: bool                   # true after lockAt
  autoSubsMade: [{ out, in }]
  effectiveCaptain: playerId     # resolved after GW: captain if played, else VC, else null

leagues/{lid}/scores/{gw}:
  results:
    {uid}:
      points: int                # final GW score (after auto-subs + captain bonus)
      rawPoints: int             # before captain bonus
      captainBonus: int          # extra points from captain
      bonusPoint: bool           # true if this manager had highest GW fpts in league
      playerScores: [{ playerId, points, stats, autSubbedOut: bool }]
      autoSubs: [{ out, in }]
      captain: playerId
      viceCaptain: playerId
      effectiveCaptain: playerId
  h2hResults:
    {uid}: { opponent: uid, result: "W"|"D"|"L"|"AAA", pointsFor, pointsAgainst }
    # result "AAA" = all-against-all (GW6, 6-player leagues only)
    # AAA entries additionally have: h2hPoints: int (the rank-based points)
  gwType: "h2h" | "all_against_all"   # present only for GW6 6-player leagues
  processed: bool
  processedAt: timestamp
  auditLog: [{ changedAt, changedBy, reason, delta }]  # admin overrides only

leagues/{lid}/scores/predictions:   # special doc written at GW8 finalization
  results:
    {uid}: { points: int, isPredictionBonus: true }
  processedAt: timestamp

leagues/{lid}/schedule/{gw}:    # for all league-phase GWs (GW6 of 6-player leagues has no schedule doc)
  gw: int
  matches: [{ home: uid, away: uid, homePoints, awayPoints, finished }]

leagues/{lid}/standings:
  managers: [{
    uid, displayName, teamName,
    hw, hd, hl,                  # H2H wins / draws / losses
    hpts,                        # H2H points (W×3 + D×1 + bonus + AAA)
    fpts,                        # total fantasy points all season (incl. prediction bonuses)
    bonusPoints,                 # count of GW top-scorer bonuses received
    gwPoints: { "1": 45, "2": 60, ... }
  }]

leagues/{lid}/knockout/bracket:
  type: "sf_start"               # always (leagues are 6-8 players)
  seededAt: timestamp
  seeds: [{ seed, uid, displayName, teamName, hpts, fpts, qualifiedVia }]
    # qualifiedVia: "h2h" (top-2 H2H) | "fpts" (filled from fpts list)
  rounds:
    sf: [{ id, seedHome, seedAway, home, away, homePoints, awayPoints, winner, gw }]
    final: [{ id, home, away, homePoints, awayPoints, winner, gw }]
  champion: uid | null

leagues/{lid}/transfer_windows/{window_id}:
  windowNumber: int              # 1–6
  openAt: timestamp
  closeAt: timestamp             # = lockAt of next GW
  status: "open" | "closed"
  transfersUsed: { uid: int }
  freeTransfers: 2               # fixed; no carry-over between windows

leagues/{lid}/waivers/{waiver_id}:
  uid: str
  playerIn: int
  playerOut: int
  priority: int                  # snapshot of uid's waiverPriority at submission
  gw: int
  windowNumber: int
  status: "pending" | "approved" | "rejected"
  rejectionReason: str | null
  createdAt: timestamp

leagues/{lid}/trades/{trade_id}:
  proposerUid, targetUid
  proposerPlayers: [{ playerId, position, name }]
  targetPlayers:   [{ playerId, position, name }]
  message: str | null            # ≤ 280 chars
  status: "pending"|"awaiting_admin"|"awaiting_vote"|"accepted"|"declined"|"vetoed"|"cancelled"
  vetoVotes: [uid]               # who voted to veto
  approveVotes: [uid]
  vetoThreshold: int             # ceil(N/3) — computed at proposal time, frozen
  createdAt, resolvedAt, expiresAt   # auto-expire pending trades after 48h

leagues/{lid}/transactions:     # append-only log for realtime feed
  type: "waiver_approved"|"free_agent"|"trade_accepted"|"drop"
  uid, playerIn?, playerOut?
  timestamp

users/{uid}/notifications:      # user-level, not per-league
  {nid}:
    type: "draft.pick"|"draft.auto_picked"|"trade.proposed"|"trade.accepted"|
          "trade.vetoed"|"waiver.approved"|"waiver.rejected"|"score.adjusted"|
          "elim.player"|"elim.squad_all"|"scoring.delayed"|"knockout.seeded"
    leagueId: str | null
    data: {}                     # type-specific payload
    read: bool
    createdAt: timestamp

users/{uid}/profile:
  displayName, photoUrl, email
  favouriteNationId: int | null
  leagueIds: [str]              # max 5 active leagues
  notificationPrefs:
    draft: bool, eliminations: bool, trades: bool, scores: bool
```

---

## 4. WC2026Client (`data/wc_api.py`)

Replaces `FPLClient`. All data from `https://v3.football.api-sports.io`.

```python
API_KEY  = secrets["FOOTBALL_API_KEY"]   # from secrets.json
WC_LEAGUE = 1
WC_SEASON = 2026
POS_MAP   = {"G": 1, "D": 2, "M": 3, "F": 4}
```

### Methods

```python
# ── One-time setup ────────────────────────────────────────────────────
sync_all_squads(db)          # ~48 API calls; writes wc_players + wc_teams
sync_fixtures(db)            # writes wc_fixtures for all 8 GWs

# ── Player pool ───────────────────────────────────────────────────────
get_player(player_id)        # reads from Firestore cache
get_player_map()             # {id: player_dict}
get_all_players()            # full list for draft pool
get_players_by_team(team_id)

# ── Live data (hits api-sports, TTL-cached) ───────────────────────────
get_live_fixtures()          # status == "1H"|"2H"|"HT"|"ET"
get_fixture_events(fid)      # goals / assists / cards / own goals
get_fixture_player_stats(fid)  # per-player stats + BPS

# ── Elimination detection ─────────────────────────────────────────────
get_group_standings(group)   # for post-GW3 elimination check
check_team_eliminated(team_id)
```

### Caching TTLs

| Data | TTL | Notes |
|---|---|---|
| Player squads | 7 days | Stable; squads don't change mid-tournament |
| Completed fixture stats | Permanent | `processedForFantasy=true` → never re-hit API |
| Live fixture | 5 min | Only fetch if status is in-progress |
| Upcoming fixtures | 1 hour | Schedule is known in advance |
| Group standings | 30 min during GW3 | Needed for elimination detection |

### Request Budget (100/day free tier)

| Operation | Requests | When |
|---|---|---|
| Squad sync (one-time) | 48 | Pre-tournament |
| Live polling (match day peak: 4 games overlap) | ~6 req/5-min cycle × 3h = ~72 | Match days only |
| Post-fixture stats | 1 per finished fixture (max 24/day in groups) | Match days |
| Group standings check | 12 (one per group) | After GW3 only |
| **Worst day total** | ~96 | Peak group-stage day |

On the worst day, we are just under 100. Mitigation: only poll fixtures whose `status` is live (one call to `/fixtures/live` first; if empty, abort).

### WC 2026 Coverage Gap Fallback

api-sports WC 2026 currently shows `statistics_players: false`. **Tested WC 2022 and full per-player stats were available.** This will almost certainly be true for 2026 once it starts. However, build the fallback:

```python
def get_fixture_player_stats(fid):
    stats = api.get("/fixtures/players", fixture=fid)
    if not stats:
        # Fallback: reconstruct from events only (goals, assists, cards)
        events = api.get("/fixtures/events", fixture=fid)
        return _reconstruct_stats_from_events(events)
    return stats
```

Events endpoint gives: goals, assists, yellow/red cards, own goals, substitutions (→ minutes). This is enough for the main scoring categories even without the player-stats endpoint.

---

## 5. Scoring Engine (`game/wc_scoring.py`)

### 5.1 Scoring Table

| Stat | GK | DEF | MID | FWD |
|---|---|---|---|---|
| Played < 60 min | 1 | 1 | 1 | 1 |
| Played ≥ 60 min | 2 | 2 | 2 | 2 |
| Goal scored | 10 | 6 | 5 | 4 |
| Assist | 3 | 3 | 3 | 3 |
| Clean sheet | 4 | 4 | 1 | 0 |
| Goals conceded (per 2) | -1 | -1 | 0 | 0 |
| Yellow card | -1 | -1 | -1 | -1 |
| Red card | -3 | -3 | -3 | -3 |
| Saves (per 3, in-play only) | 1 | — | — | — |
| Own goal | -2 | -2 | -2 | -2 |
| Penalty missed | -2 | -2 | -2 | -2 |
| Penalty saved (in-play only) | 5 | — | — | — |
| Bonus (top 3 BPS in fixture) | 3/2/1 | 3/2/1 | 3/2/1 | 3/2/1 |

**Notes:**
- **Penalty shootout saves/misses** are NOT counted. Shootouts are part of the WC knockout format but don't add to individual fantasy scores — only in-play events count.
- **Extra time**: minutes played include ET. A player who plays 90+15 minutes gets the 60+ bonus.
- **Bonus points**: top 3 BPS in a fixture get 3/2/1 points. BPS ties resolved per FPL rules (both tied players receive the higher award). BPS values come directly from api-sports `bps` field.
- **Own goals** conceded by a player's team count against GK/DEF (goals conceded rule). Own goals *scored by the player* incur -2.
- **Goals conceded flooring**: fraction truncated, not rounded. -1 per 2 means: 1 conceded = 0, 2 = -1, 3 = -1, 4 = -2.

### 5.2 Captain Bonus

Applied AFTER regular point calculation:
- `effectiveCaptain` = captain if captain played ≥ 1 min, else viceCaptain if played ≥ 1 min, else null
- `captainBonus` = effectiveCaptain's raw GW points (i.e., points doubled in total)
- If both captain AND vice-captain played 0 minutes: `captainBonus = 0`
- Bonus applies in **both league phase and knockout phase**

### 5.5 GW Top-Scorer Bonus

After each league-phase GW finalizes, the manager(s) with the **highest fantasy score** in the league earn **+1 H2H point**. This bonus is additive with the W/D/L result.

- Stored as `results.{uid}.bonusPoint = true` in the scores doc
- Counted in `_update_standings()` when accumulating `hpts`
- If multiple managers are tied at the top score, **all tied managers** receive the +1 bonus
- Applies to bye-week managers (if they happen to have the highest score, they still earn +1)

### 5.6 Predictions Bonus (applied at GW8 finalization)

Managers who predicted correctly receive bonus fantasy points added to their season total:

| Prediction | Bonus |
|---|---|
| Correct WC winner (national team) | +15 fpts |
| Correct WC top scorer (player) | +10 fpts |

- Both bonuses can apply to the same manager (max +25)
- Stored as a special `leagues/{lid}/scores/predictions` document (counted in fpts standings)
- Set via `wc_config/tournament.winner` (team id) and `wc_config/tournament.topScorer` (player id) — admin sets these after Final
- Predictions lock at GW1 `lockAt`. Set via `PUT /leagues/{lid}/predictions`

### 5.3 process_fixture flow

```python
def process_fixture(fixture_id: int):
    stats   = wc_client.get_fixture_player_stats(fixture_id)  # or fallback
    events  = wc_client.get_fixture_events(fixture_id)        # for own goals

    player_points = {}
    for player in stats:
        pts = compute_base_points(player, SCORING_TABLE)
        pts += compute_bonus(player, stats)          # BPS → 3/2/1
        player_points[player.id] = pts
        write wc_fixtures/{fixture_id}/playerScores/{player.id}

    mark wc_fixtures/{fixture_id}.processedForFantasy = true
    propagate_to_leagues(fixture_id, player_points)

def propagate_to_leagues(fixture_id, player_points):
    # Find all active leagues with players from this fixture in their squads
    # For each such league, update running GW score
    active_leagues = query_leagues_with_gw_active()
    for lid in active_leagues:
        for uid, squad in get_all_squads(lid).items():
            lineup = get_lineup(lid, uid, current_gw)
            gw_delta = sum(
                player_points.get(pid, 0)
                for pid in lineup.starting
                if pid in players_from_this_fixture
            )
            if gw_delta:
                atomic_increment(leagues/{lid}/scores/{gw}/results/{uid}/points, gw_delta)
```

### 5.4 GW Finalization

```python
def finalize_gw(lid: str, gw: int):
    # 1. Verify all fixtures in GW are processedForFantasy
    unprocessed = [f for f in gw_fixtures if not f.processedForFantasy]
    if unprocessed:
        raise ValueError(f"Fixtures not yet processed: {unprocessed}")

    # 2. Process auto-substitutions for all managers
    all_minutes = aggregate_gw_minutes(gw)   # {player_id: minutes_played}
    for uid in league_members:
        apply_auto_subs(lid, uid, gw, all_minutes)
        recompute_score_with_captain_bonus(lid, uid, gw)

    # 3. Determine H2H results (if league-phase GW)
    if gw in league.leaguePhaseGws:
        for match in schedule[gw].matches:
            home_pts = scores[gw].results[match.home].points
            away_pts = scores[gw].results[match.away].points
            if home_pts > away_pts: result = ("W", "L")
            elif home_pts == away_pts: result = ("D", "D")
            else: result = ("L", "W")
            update H2H record for both managers

    # 4. Update standings
    update_standings(lid, gw)

    # 5. Mark complete
    scores[gw].processed = true

    # 6. Detect eliminations
    check_eliminations_after_gw(gw)

    # 7. Open transfer window
    open_transfer_window(lid, gw)

    # 8. If last league GW → seed knockout
    if gw == league.knockoutStartGw - 1:
        seed_knockout(lid)

    # 9. If knockout GW → advance bracket
    if gw >= league.knockoutStartGw:
        advance_knockout_bracket(lid, gw)

    # 10. Advance currentGw
    league.currentGw = gw + 1
```

---

## 6. Group / League Phase Operation

### Lineup Set Flow

```
Before lockAt:
  manager sets starting[11] + bench[4] + captain + viceCaptain
  Server validates: formation, position counts, captain in starting, VC ≠ captain
  Server WARNS (not errors) for eliminated players in starting XI

After lockAt:
  GET /lineup/{gw} returns opponent's lineup fully visible
  PUT /lineup/{gw} returns 409 LINEUP_LOCKED

Lineup for GW n copied forward from GW n-1 as default (manager can override)
```

### Auto-Substitution Rules

Fires after **all** GW fixtures complete (not per-fixture):

```
For each starting player who played 0 minutes across all GW fixtures:
  For each bench slot in order (bench[0] = GK, bench[1..3] = outfield):
    if bench player played ≥ 1 minute:
      if swapping preserves valid formation:
        do swap, record { out, in }
        break

Special rules:
  - bench[0] (GK) can only sub in for starting GK
  - formation must remain valid after sub (min 3 DEF, min 2 MID, min 1 FWD)
  - if no valid sub found: starter stays with 0 pts (bad luck)
  - captain/VC designation is NOT changed by auto-sub
    (if captain played 0 min and was auto-subbed: VC becomes effective captain)
```

### Lineup Block During Drop Grace Period

If manager's squad has < 15 players (during drop grace period), `PUT /lineup/{gw}` returns `409 SQUAD_INCOMPLETE` until they pick up a replacement.

---

## 7. Transfer Windows

### Window Schedule

| Window | Opens | Closes | Notes |
|---|---|---|---|
| 1 | After GW1 finalized | GW2 lockAt | ✅ |
| 2 | After GW2 finalized | GW3 lockAt | ✅ |
| 3 | After GW3 finalized | GW4 lockAt | ✅ **Big** (16 WC teams eliminated after Group Stage) |
| 4 | After GW4 finalized | GW5 lockAt | ✅ |
| 5 | After GW5 finalized | GW6 lockAt | ✅ |
| 6 | After GW6 finalized | GW7 lockAt | ✅ pre-SF (~48h) |

Transfer windows open after all league-phase GWs (1–6). No windows during knockout phase (GW7+).

### Transfer Rules

- **2 free transfers per window.** No carry-over between windows (use-it-or-lose-it).
- **No hard cap** on total transfers in a window (friends app), but free count tracked.
- Window is **closed** while a GW is active (between lockAt and GW finalization).
- Transfer executed atomically; if two managers claim the same free agent simultaneously → Firestore transaction; first one wins, second gets `409 PLAYER_ALREADY_OWNED`.

### 7.1 Free Agent Pickup

Immediate, FCFS, no queue. Validations:

| # | Rule | Code |
|---|---|---|
| 1 | Window open | `WINDOW_CLOSED` |
| 2 | playerOut in caller's squad | `PLAYER_OUT_NOT_OWNED` |
| 3 | playerIn exists | `PLAYER_NOT_FOUND` |
| 4 | playerIn not owned in this league | `PLAYER_ALREADY_OWNED` |
| 5 | playerIn not on waivers (use waiver claim instead) | `PLAYER_ON_WAIVERS` |
| 6 | playerIn not in pending waiver claim by another manager (race) | `PLAYER_ALREADY_CLAIMED` |
| 7 | playerIn.team not eliminated (no picking up dead-nation players) | `PLAYER_TEAM_ELIMINATED` |
| 8 | Resulting squad maintains 2GK/5DEF/5MID/3FWD | `POSITION_QUOTA_VIOLATED` |

### 7.2 Drop Without Pickup

`POST /leagues/{lid}/squad/drop` — player enters waivers immediately; squad goes to 14.

| # | Rule | Code |
|---|---|---|
| 1 | Window open | `WINDOW_CLOSED` |
| 2 | playerOut in squad | `PLAYER_OUT_NOT_OWNED` |
| 3 | Squad at 14 still has ≥ 1 player in every position | `POSITION_QUOTA_INCOMPLETABLE` |

After drop: manager has **24-hour grace period** to pick up replacement via free agent or waiver. Lineup set is blocked during this period. After 24h without pickup: still blocked; manager can still submit waiver claims. They have until the next GW lockAt to have a full squad.

---

## 8. Waivers

### 8.1 When Players Enter the Waiver Pool

- Manager explicitly drops a player → immediately on waivers
- National team is eliminated → affected players auto-enter waivers at next window open
- Previously dropped player with no claims → stays free agent (never returns to waivers)

### 8.2 Waiver Phases (within each transfer window)

```
Window opens (T+0):
  All dropped players enter waivers

T+0 → T+24h: WAIVER SUBMISSION PHASE
  Managers submit claims: { playerIn, playerOut }
  Multiple managers can claim the same playerIn (different playerOut)
  Same manager can claim up to 10 different players (anti-spam)
  Same manager CANNOT claim the same playerIn+playerOut twice (DUPLICATE_WAIVER_CLAIM)
  Same manager CAN claim playerIn=X for playerOut=A AND playerIn=Y for playerOut=A
    BUT only one of these can execute (can't drop A twice)
    → server resolves: first approved claim drops A; second auto-rejects

T+24h: WAIVER PROCESSING
  Sort all pending claims by (priority ASC, createdAt ASC)
  For each claim in order:
    if playerIn already claimed in this run → reject
    if playerOut no longer in squad → reject (already used by earlier claim)
    else → execute swap; drop uid to bottom of waiver queue

T+24h → window close: FREE AGENT PHASE
  Unclaimed free agents available FCFS (instant pickup)
  Players no longer on waivers after processing
```

### 8.3 Waiver Priority

- **Initial order**: reverse draft order (pick #15 → priority 1, pick #1 → priority N)
- **After successful claim**: manager drops to bottom (max priority number)
- **Managers who didn't claim**: their priority is unchanged (they move up relatively)
- **Reset option**: admin can reset to reverse-standings order between GWs (optional setting)

### 8.4 Waiver Conflict Detection

When manager submits claim `{playerIn: X, playerOut: Y}`:
- If manager already has another pending claim with `playerOut: Y`: server **warns** `WAIVER_DROP_CONFLICT` — both are stored but only the first-processed one will execute. Manager can cancel one.
- If manager already has a claim for `playerIn: X` (different playerOut): server rejects `DUPLICATE_WAIVER_CLAIM` for that playerIn.

---

## 9. Trades

### Validations

| # | Rule | Code |
|---|---|---|
| 1 | targetUid is member of league AND ≠ caller | `TRADE_TARGET_INVALID` |
| 2 | 1–5 players on each side | `TRADE_SIZE_INVALID` |
| 3 | Both sides have same player count | `TRADE_NOT_BALANCED` |
| 4 | All proposerPlayers owned by caller | `PROPOSER_PLAYERS_NOT_OWNED` |
| 5 | All targetPlayers owned by targetUid | `TARGET_PLAYERS_NOT_OWNED` |
| 6 | Position composition preserved on both sides (trade GK for GK, DEF for DEF, etc.) | `TRADE_POSITION_MISMATCH` |
| 7 | Transfer window open OR `tradesDuringGw = true` (not configurable in v1 — always window required) | `TRADES_BLOCKED_WINDOW_CLOSED` |
| 8 | Caller has < 5 pending outgoing trades | `TRADE_LIMIT_EXCEEDED` |
| 9 | targetUid has < 10 pending incoming trades | `TARGET_TRADE_LIMIT` |
| 10 | **None of the involved players' matches are currently in progress** | `PLAYER_MID_FIXTURE` |
| 11 | message ≤ 280 chars | `TRADE_MESSAGE_INVALID` |

**Mid-fixture check (rule 10)**: A player is "mid-fixture" if their national team's match has `status ∈ {"1H","2H","HT","ET"}`. Once status is `FT`, trade is permitted again.

### Veto Threshold

`tradeApproval == "vote"`: vetoed if `≥ ceil(N / 3)` league members vote to veto. (Not N/2 — lower bar gives trades a better chance of passing in small leagues.)

| N | ceil(N/3) vetoes needed to block |
|---|---|
| 6 | 2 |
| 8 | 3 |
| 10 | 4 |
| 12 | 4 |

Trade auto-expires after 48h if no response from target.

---

## 10. Squad & Lineup Constraints

### Squad (15 players, fixed composition)
2 GK · 5 DEF · 5 MID · 3 FWD

### Starting XI (11 players)
- Exactly 1 GK
- DEF: 3–5
- MID: 2–5
- FWD: 1–3

Valid formations: 1-3-4-3, 1-3-5-2, 1-4-3-3, 1-4-4-2, 1-4-5-1, 1-5-3-2, 1-5-4-1

### Bench (4 players)
- `bench[0]` = the non-starting GK (required; validated server-side)
- `bench[1..3]` = outfield players in auto-sub priority order

### Eliminated Players in Lineup
- **Allowed but warned** — manager may have no choice during closed window
- Server returns `warnings[]` array with `STARTING_HAS_ELIMINATED` per dead player
- Hard block ONLY if squad is incomplete (< 15 players due to pending drop)

---

## 11. National Team Elimination

### Group Stage (after all GW3 matches complete)

WC 2026: 12 groups of 4. Top 2 advance automatically. The **8 best 3rd-place teams** from 12 also advance. This means 16 teams are eliminated (24 automatic + 8 best 3rd = 32 advance; 16 go out).

**Critical**: All 12 groups' Round 3 matches must be complete before eliminations are confirmed. The 8 best 3rd-place teams are selected across all groups simultaneously. We cannot declare 3rd-place eliminations until ALL GW3 fixtures are `FT`.

```python
def detect_group_stage_eliminations():
    # Only run when ALL GW3 fixtures are processedForFantasy
    all_groups = get_all_12_groups()
    third_place_teams = []
    eliminated = []

    for group in all_groups:
        standings = compute_group_standings(group)
        eliminated.append(standings[3])         # 4th place: always out
        third_place_teams.append(standings[2])  # 3rd place: maybe out

    # Rank 3rd-place teams by: pts → goal_diff → goals_scored → FIFA ranking
    sorted_thirds = sort_by_wc_criteria(third_place_teams)
    advancing_thirds = sorted_thirds[:8]
    eliminated_thirds = sorted_thirds[8:]
    eliminated.extend(eliminated_thirds)

    for team in eliminated:
        mark_team_eliminated(team.id, gw=3)
```

### Knockout Eliminations

After each knockout GW: the loser of each bracket match is eliminated.

```python
def detect_knockout_eliminations(gw):
    for match in bracket.rounds[current_round]:
        if match.finished:
            loser_uid = match.away if match.winner == match.home else match.home
            # Find all WC teams whose players are owned by this uid
            # Mark them as eliminated? No — WC teams are eliminated based on WC results, not fantasy results
            pass
    # For WC team elimination tracking:
    losing_wc_teams = [match.loser_team for match in wc_knockout_fixtures[gw] if match.status == "FT"]
    for team in losing_wc_teams:
        mark_team_eliminated(team.id, gw=gw)
```

### Impact on Squads

1. `wc_teams/{id}.eliminated = true` and `wc_players/{id}.eliminated = true` (atomic batch write)
2. All managers in active leagues with these players get notification `elim.player`
3. If a manager's ENTIRE squad is eliminated: notification `elim.squad_all`
4. At next window open: eliminated players auto-enter waiver pool
5. Managers are NOT forced to drop them; they just score 0 forever

---

## 12. Knockout Engine (`game/knockout.py`)

### Seeding

```python
def seed_knockout(lid: str):
    standings = get_final_league_standings(lid)
    n = len(standings)

    if n > 8:
        # Sort all by H2H → fpts → head-to-head between tied → draft order
        sorted_all = sort_by_tiebreaker_chain(standings)
        seeds_1_4  = sorted_all[:4]
        remaining  = sorted_all[4:]
        seeds_5_8  = sorted(remaining, key=lambda x: (-x.fpts, x.draft_position))[:4]
        seeds = seeds_1_4 + seeds_5_8   # [seed1, seed2, ..., seed8]
        bracket = [
            { id: "QF1", home: seeds[0], away: seeds[7], gw: 4 },
            { id: "QF2", home: seeds[1], away: seeds[6], gw: 4 },
            { id: "QF3", home: seeds[2], away: seeds[5], gw: 4 },
            { id: "QF4", home: seeds[3], away: seeds[4], gw: 4 },
        ]

    else:  # n ≤ 8
        sorted_all = sort_by_tiebreaker_chain(standings)
        seeds_1_2  = sorted_all[:2]
        remaining  = sorted_all[2:]
        seeds_3_4  = sorted(remaining, key=lambda x: (-x.fpts, x.draft_position))[:2]
        seeds = seeds_1_2 + seeds_3_4   # [seed1, seed2, seed3, seed4]
        bracket = [
            { id: "SF1", home: seeds[0], away: seeds[3], gw: 7 },
            { id: "SF2", home: seeds[1], away: seeds[2], gw: 7 },
        ]

    save_bracket(lid, bracket)
```

### Bracket Advancement

```python
def advance_knockout_bracket(lid: str, gw: int):
    bracket = get_bracket(lid)
    current_matches = [m for m in bracket.all_matches if m.gw == gw]

    for match in current_matches:
        home_pts = scores[gw].results[match.home].points
        away_pts = scores[gw].results[match.away].points

        if home_pts > away_pts:
            match.winner = match.home
        elif away_pts > home_pts:
            match.winner = match.away
        else:
            # Tiebreaker 1: higher seed advances (lower seed number = better)
            if match.seed_home < match.seed_away:
                match.winner = match.home
            elif match.seed_away < match.seed_home:
                match.winner = match.away
            else:
                # Tiebreaker 2: total season fpts
                home_fpts = standings[match.home].fpts
                away_fpts = standings[match.away].fpts
                match.winner = match.home if home_fpts >= away_fpts else match.away

        match.loser_eliminated = True

    # Generate next round
    generate_next_round_matches(lid, bracket, current_matches)
```

### Edge Cases in Knockout

| Edge Case | Handling |
|---|---|
| Manager leaves mid-knockout | Their squad is frozen; they auto-score whatever their players score; bracket proceeds normally |
| Manager picks 0 players who play | Score = 0 + captain bonus (0 if both C/VC didn't play) = 0; higher seed advances on tie |
| Bracket regeneration (admin) | Creates new `bracket` document with `regeneratedAt`; all managers notified |

---

## 13. Background Processing

### Jobs

**`poll_live_scores`** — every 5 minutes on match days only:
```python
def poll_live_scores():
    live = wc_client.get_live_fixtures()     # 1 API request
    if not live:
        return                               # no-op, saves request budget

    for fixture in live:
        if fixture.status == "FT" and not fixture.processedForFantasy:
            process_fixture(fixture.id)      # ~1 API request

    # Check if all GW fixtures are done
    gw_fixtures = get_fixtures_for_gw(current_gw)
    if all(f.processedForFantasy for f in gw_fixtures):
        for lid in get_active_leagues():
            finalize_gw(lid, current_gw)
```

**`daily_sync`** — once per day (06:00 UTC):
```python
def daily_sync():
    sync_fixture_statuses()        # update postponed/rescheduled fixtures
    check_team_eliminations()      # in case api-sports updated group standings
    if wc_players_stale():
        sync_all_squads()          # only if > 7 days since last sync
    if daily_requests > 80:
        log_alert("API budget near limit")
```

**`process_waivers`** — T+24h after each window opens:
```python
def process_waivers(lid: str, window_number: int):
    claims = get_pending_waivers(lid, window_number)
    claims.sort(key=lambda c: (c.priority, c.createdAt))
    claimed = {}   # { playerIn: uid }
    dropped = {}   # { playerOut: uid }

    for claim in claims:
        if claim.playerIn in claimed:
            reject(claim, "PLAYER_ALREADY_CLAIMED")
            continue
        if dropped.get(claim.playerOut) == claim.uid:
            reject(claim, "PLAYER_ALREADY_DROPPED_THIS_WINDOW")
            continue
        execute_swap(lid, claim.uid, claim.playerIn, claim.playerOut)
        claimed[claim.playerIn] = claim.uid
        dropped[claim.playerOut] = claim.uid
        drop_to_bottom_of_queue(lid, claim.uid)
        approve(claim)
        notify(claim.uid, "waiver.approved", ...)
```

### Postponed Fixture Handling

If a WC fixture status becomes `postponed`:
1. Do NOT mark as `processedForFantasy`
2. The GW cannot finalize until rescheduled + played
3. If rescheduled into a different calendar GW: admin must update `wc_fixtures/{id}.gw` via admin endpoint
4. Notify active leagues: `scoring.delayed`

### api-sports Downtime

If the API returns non-200 on match day:
1. Cached `wc_fixtures` data still serves all reads
2. Scoring is **delayed**, not lost — will process when API recovers
3. Background job retries with exponential backoff (30s, 60s, 120s, max 300s)
4. If downtime > 2h: notify leagues `scoring.delayed`

---

## 14. Complete API Endpoints

Base URL: `/api/v1`. Auth: `Authorization: Bearer <firebase-id-token>` on all non-public endpoints.

### 14.1 Tournament & WC Data (public)

| Method | Path | Cache |
|---|---|---|
| GET | `/wc/tournament` | 5 min |
| GET | `/wc/teams` | 5 min |
| GET | `/wc/teams/{teamId}` | 1 hour |
| GET | `/wc/players?position=&team=&group=&search=&cursor=` | 5 min |
| GET | `/wc/players/{playerId}` | 1 min |
| GET | `/wc/players/{playerId}/history` | 30s when live |
| GET | `/wc/fixtures?gw=&team=&from=&to=` | 5 min (30s live) |
| GET | `/wc/fixtures/{fixtureId}` | 30s live |
| GET | `/wc/gw/{n}` | 5 min |

### 14.2 User Profile

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/me` | Create/update after Firebase sign-in |
| GET | `/auth/me` | Profile + league list |
| PATCH | `/auth/me` | Update displayName, favouriteNationId |
| PATCH | `/auth/me/notification-prefs` | Toggle per-category |

### 14.3 Leagues

| Method | Path | Notes |
|---|---|---|
| POST | `/leagues` | Create. Returns `{ leagueId, inviteCode }` |
| GET | `/leagues/{lid}` | Config + members (members only) |
| PATCH | `/leagues/{lid}` | Admin: name, tradeApproval (locked after draft except tradeApproval) |
| POST | `/leagues/join` | `{ inviteCode, teamName }` |
| POST | `/leagues/{lid}/leave` | Before draft only |
| POST | `/leagues/{lid}/kick` | Admin only, before draft only |
| POST | `/leagues/{lid}/invite-code/rotate` | Admin invalidates old code |
| GET | `/leagues/{lid}/standings` | Full standings |
| GET | `/leagues/{lid}/schedule?gw=` | H2H schedule |
| GET | `/leagues/{lid}/knockout` | Bracket. 404 before seeding |
| GET | `/leagues/{lid}/scores/{gw}` | All-manager GW scores |
| GET | `/leagues/{lid}/scores/{gw}/audit` | Per-fixture, per-player breakdown |

### 14.4 Draft

| Method | Path | Notes |
|---|---|---|
| POST | `/leagues/{lid}/draft/start` | Admin only |
| GET | `/leagues/{lid}/draft/state` | + Firestore `onSnapshot` for realtime |
| POST | `/leagues/{lid}/draft/pick` | `{ playerId }`. Idempotency-Key required |
| POST | `/leagues/{lid}/draft/watchlist` | `{ playerId, add: bool }`. Private |
| POST | `/leagues/{lid}/draft/autopick` | `{ enabled, rankedPlayerIds[] }` |
| POST | `/leagues/{lid}/draft/pause` | Admin only |
| POST | `/leagues/{lid}/draft/resume` | Admin only |

### 14.5 Squad & Lineup

| Method | Path | Notes |
|---|---|---|
| GET | `/leagues/{lid}/squads/{uid}` | Public to league members |
| GET | `/leagues/{lid}/lineup/{gw}` | Own lineup |
| GET | `/leagues/{lid}/lineup/{gw}/{uid}` | Opponent: hidden before lock, visible after |
| PUT | `/leagues/{lid}/lineup/{gw}` | Full replace: `{ starting, bench, captain, viceCaptain }` |
| PATCH | `/leagues/{lid}/lineup/{gw}` | Partial: swap players or change captain only |

### 14.6 Transfers / Waivers / Free Agents

| Method | Path | Notes |
|---|---|---|
| GET | `/leagues/{lid}/transfer-window` | `{ open, number, opensAt, closesAt, freeRemaining }` |
| GET | `/leagues/{lid}/free-agents?position=&group=&sort=&cursor=` | Not owned, not on waivers |
| POST | `/leagues/{lid}/free-agent` | `{ playerIn, playerOut }` |
| POST | `/leagues/{lid}/squad/drop` | `{ playerOut }`. No playerIn required |
| GET | `/leagues/{lid}/waivers` | My pending claims |
| GET | `/leagues/{lid}/waivers/queue` | League-wide priority order |
| POST | `/leagues/{lid}/waivers` | `{ playerIn, playerOut }` |
| DELETE | `/leagues/{lid}/waivers/{wid}` | Cancel pending claim |
| PATCH | `/leagues/{lid}/waivers/{wid}` | Reorder within MY claims |

### 14.7 Trades

| Method | Path | Notes |
|---|---|---|
| POST | `/leagues/{lid}/trades` | Propose |
| GET | `/leagues/{lid}/trades?status=&direction=` | My trades (inbox/outbox/history) |
| POST | `/leagues/{lid}/trades/{tid}/respond` | `{ action: "accept"\|"decline" }` |
| POST | `/leagues/{lid}/trades/{tid}/cancel` | Proposer only |
| POST | `/leagues/{lid}/trades/{tid}/veto` | If `tradeApproval=="vote"` |
| POST | `/leagues/{lid}/trades/{tid}/admin-decide` | If `tradeApproval=="admin"` |

### 14.8 Notifications

| Method | Path |
|---|---|
| GET | `/notifications?cursor=` |
| POST | `/notifications/{nid}/read` |
| POST | `/notifications/read-all` |

### 14.9 Admin (system-wide)

| Method | Path | Notes |
|---|---|---|
| POST | `/admin/wc/sync` | Force squad + fixture sync |
| POST | `/admin/fixtures/{fid}/reprocess` | Recompute fantasy points |
| POST | `/admin/leagues/{lid}/gw/{gw}/finalize` | Force GW finalization |
| POST | `/admin/leagues/{lid}/knockout/regenerate` | Re-seed bracket |
| POST | `/admin/leagues/{lid}/waivers/process` | Force waiver processing |

---

## 15. Validation & Error Codes

### League Creation

| # | Rule | Code |
|---|---|---|
| 1 | name: 3–48 chars | `LEAGUE_NAME_INVALID` |
| 2 | size ∈ 4–16 | `LEAGUE_SIZE_OUT_OF_RANGE` |
| 3 | pickTimer ∈ {30,60,90,120,180,300} | `PICK_TIMER_INVALID` |
| 4 | draftAt: future AND ≥24h from now AND ≤ 2026-06-10T20:00Z | `DRAFT_DATE_INVALID` |
| 5 | WC status is pre_draft or drafting | `TOURNAMENT_NOT_OPEN` |
| 6 | Caller under 5-league limit | `LEAGUE_LIMIT_EXCEEDED` |

Server computes: `knockoutStartGw = size > 8 ? 4 : 7`, `leaguePhaseGws = size > 8 ? [1,2,3] : [1,2,3,4,5,6]`, `knockoutQualifiers = size > 8 ? 8 : 4`.

### Draft Pick

| # | Rule | Code |
|---|---|---|
| 1 | It is caller's turn (or clock expired → server auto-picks first) | `NOT_YOUR_TURN` |
| 2 | playerId not already picked | `PLAYER_ALREADY_PICKED` |
| 3 | Pick doesn't exceed position quota (2GK/5DEF/5MID/3FWD) | `POSITION_QUOTA_EXCEEDED` |
| 4 | Pick leaves remaining positions completable | `POSITION_QUOTA_INCOMPLETABLE` |
| 5 | Idempotency-Key unique in last 24h | `IDEMPOTENCY_KEY_REUSED` |
| 6 | wc_players collection has ≥ 600 players | `PLAYER_DATA_INCOMPLETE` |

### Lineup

| Code | Meaning |
|---|---|
| `LINEUP_LOCKED` | Past lockAt |
| `LINEUP_STARTING_SIZE` | Not exactly 11 starters |
| `LINEUP_GK_COUNT` | Not exactly 1 GK in starting |
| `LINEUP_DEF_COUNT` | DEF count not in [3,5] |
| `LINEUP_MID_COUNT` | MID count not in [2,5] |
| `LINEUP_FWD_COUNT` | FWD count not in [1,3] |
| `FORMATION_MISMATCH` | Formation array doesn't match actual composition |
| `BENCH_GK_FIRST` | bench[0] is not the non-starting GK |
| `CAPTAIN_NOT_STARTING` | Captain not in starting XI |
| `VICE_CAPTAIN_INVALID` | VC not in starting or same as captain |
| `SQUAD_INCOMPLETE` | Squad < 15 (in drop grace period) |
| `LINEUP_NOT_IN_SQUAD` | Player not owned |

Warnings (not errors): `STARTING_HAS_ELIMINATED`, `BENCH_ALL_ELIMINATED`, `GK_ALL_ELIMINATED`

### Transfers / Waivers

| Code | Meaning |
|---|---|
| `WINDOW_CLOSED` | Transfer window not open |
| `PLAYER_ALREADY_OWNED` | Target player belongs to someone |
| `PLAYER_ON_WAIVERS` | Use waiver claim instead |
| `PLAYER_ALREADY_CLAIMED` | Race condition: another manager just claimed |
| `PLAYER_TEAM_ELIMINATED` | Cannot add dead-nation player |
| `POSITION_QUOTA_VIOLATED` | Squad would violate 2/5/5/3 composition |
| `WAIVER_PHASE_CLOSED` | Past T+24h — in free agent phase now |
| `DUPLICATE_WAIVER_CLAIM` | Same playerIn already claimed this window |
| `WAIVER_DROP_CONFLICT` | Same playerOut used in two pending claims (warning) |
| `POSITION_QUOTA_INCOMPLETABLE` | Drop would leave position with 0 players |

### Trades

| Code | Meaning |
|---|---|
| `TRADE_POSITION_MISMATCH` | Must trade same positions |
| `TRADE_NOT_BALANCED` | Sides not equal count |
| `PLAYER_MID_FIXTURE` | Involved player's match is in progress |
| `TRADES_BLOCKED_WINDOW_CLOSED` | No active transfer window |

---

## 16. Realtime Channels (Firestore `onSnapshot`)

| Collection | Who listens | When |
|---|---|---|
| `leagues/{lid}/draft/state` | All members | During draft |
| `leagues/{lid}/draft/picks` | All members | During draft |
| `leagues/{lid}/scores/{gw}` | All members | During live GW |
| `leagues/{lid}/lineups/*` | All members | After lockAt (to see opponent) |
| `leagues/{lid}/transactions` | All members | Transfers/waivers feed |
| `leagues/{lid}/knockout/bracket` | All members | During knockout |
| `users/{uid}/notifications` | Current user only | Always |

---

## 17. Edge Cases Catalogue

| # | Situation | Handling |
|---|---|---|
| E1 | Squad sync not done when draft starts | Block draft start: `PLAYER_DATA_INCOMPLETE` (< 600 players in wc_players) |
| E2 | api-sports has no WC 2026 squads yet (currently 0) | Run sync daily from ~May 28; draft cannot start until ≥ 600 players loaded |
| E3 | All 15 squad players from eliminated nations | Manager still participates, scores 0. Cannot be forced out. Notified. |
| E4 | Manager's only GK(s) eliminated | Can set lineup with warning `GK_ALL_ELIMINATED`; auto-sub won't help (no valid GK bench) |
| E5 | Postponed WC fixture | GW can't finalize until it plays. Admin can reclassify to different GW. |
| E6 | Two managers simultaneously claim same free agent | Firestore transaction; first wins, second gets `PLAYER_ALREADY_OWNED` |
| E7 | Same playerOut used in two pending waiver claims by same manager | Both stored; first processed executes, second auto-rejects `PLAYER_ALREADY_DROPPED_THIS_WINDOW` |
| E8 | Manager leaves mid-tournament | Squad frozen (squadFrozen=true); auto-scores; bracket proceeds; cannot re-join |
| E9 | Draft clock expires, no autopick list | Server picks highest-`draftRank` available player that passes quotas |
| E10 | All bench players also didn't play (0 minutes) | No auto-subs; starter stays with 0 pts |
| E11 | Captain and VC both played 0 minutes | `captainBonus = 0`; total = raw points only |
| E12 | 3rd-place GW3 ties — which teams advance? | Use WC tiebreaker chain: points → GD → goals → FIFA ranking; admin can override |
| E13 | api-sports BPS data missing for a fixture | Award 0 bonus points; log warning; do not delay finalization |
| E14 | Trade target player gets eliminated between proposal and acceptance | Trade still valid (elimination doesn't void a trade); target manager may decline |
| E15 | A player is called up as injury replacement during tournament | Their data will appear in api-sports squad; daily_sync will pick them up; they enter free agent pool |
| E16 | Multiple fixtures in same GW for same player | Only possible in group stage (each player plays exactly once per round). Not a real edge case for WC. |
| E17 | GW4 lockAt before Window 3 has processed waivers | Window opens after GW3; lockAt of GW4 is its first kickoff. Waivers are processed T+24h after window opens. If window opens less than 24h before GW4 lockAt: compress waiver phase (process at window close - 1h instead). |
| E18 | Seeding tie at 4th/8th position — 5th person tied | Apply full tiebreaker chain (H2H points → fpts → H2H between tied → draft order). Only one can qualify. |
| E19 | N > 8 league, all players score 0 in a knockout GW | Higher seed advances on every tie. No special handling needed beyond that. |
| E20 | Lineup set for a GW before draft finishes | Blocked: `WC_NOT_STARTED` (league status must be group_phase or knockout) |

---

## 18. What Gets Reused vs. Built New

### Reuse (adapt only)

| File | Change |
|---|---|
| `game/draft.py` | Swap `fpl_client → wc_client`; confirm `POSITION_QUOTA = {1:2, 2:5, 3:5, 4:3}` |
| `game/leagues.py` | Add `knockoutStartGw`, `leaguePhaseGws`, `knockoutQualifiers` fields |
| `game/schedule.py` | Pass `end_gw = knockoutStartGw - 1` (not hardcoded 38) |
| `game/trades.py` | Fix veto threshold to `ceil(N/3)`; add `PLAYER_MID_FIXTURE` check |
| `game/waivers.py` | Fix waiver conflict detection; replace `fpl_client` calls |
| `game/squads.py` | Add captain/VC fields; add `SQUAD_INCOMPLETE` gate; use `wc_client` |

### Build New

| File | What it does |
|---|---|
| `data/wc_api.py` | WC2026Client: api-sports wrapper, caching, BPS, fallback |
| `game/wc_scoring.py` | Scoring table, BPS bonus, captain bonus, process_fixture |
| `game/knockout.py` | Seeding, bracket generation, advancement, tiebreakers |
| `game/transfer_window.py` | Window open/close, drop-without-pickup, budget tracking |
| `game/wc_gameweeks.py` | GW calendar (hardcoded dates), lockAt, current GW detection |
| `game/elimination_tracker.py` | Group-stage + knockout elimination detection |
| `game/notifications.py` | Write to `users/{uid}/notifications`; per-category prefs |

---

## 19. Implementation Order

Tournament starts **June 11, 2026** (~15 days). Squad data expected in api-sports ~May 28.

| Priority | Task | Effort | Hard Deadline |
|---|---|---|---|
| 1 | `WC2026Client` + squad sync (must have ≥ 600 players before draft) | 1 day | Before draft date |
| 2 | `wc_gameweeks.py` + Firestore `wc_config` seeded with GW dates | 0.5 day | Before draft date |
| 3 | Firestore schema migration (new fields on leagues, lineups, scores) | 0.5 day | Before draft date |
| 4 | Draft integration (wc_client player pool + position quotas) | 1 day | Before June 11 |
| 5 | `WCScoringEngine` (scoring table + BPS + captain bonus) | 1 day | Before June 11 |
| 6 | Squad/lineup adaptation (captain/VC, bench GK rule, eliminated warnings) | 1 day | Before June 11 |
| 7 | Transfer window manager + drop-without-pickup | 1 day | Before June 16 (GW1 ends) |
| 8 | Waiver conflict detection fixes | 0.5 day | Before June 16 |
| 9 | Trade mid-fixture block + veto threshold fix | 0.5 day | Before June 16 |
| 10 | `KnockoutEngine` (seeding + bracket + tiebreakers) | 1.5 days | Before July 1 (N>8) or July 10 (N≤8) |
| 11 | Elimination tracker (group-stage detection + best-3rd logic) | 1 day | Before June 26 |
| 12 | Background scoring jobs (poll + finalize + waivers) | 1 day | Before June 11 |
| 13 | Notifications system | 0.5 day | Any time |
| 14 | Frontend: WC player browser + knockout bracket view | 2 days | Before relevant GWs |
| **Total** | | **~13 days** | |

> **Items 1–6** must be done before the draft (ideally June 7–8 to allow testing).
> **Items 7–9** can be done after GW1 starts — first transfer window opens June 16.
> **Items 10–11** must be done before July 1 (N>8) or June 26 (elimination detection).
