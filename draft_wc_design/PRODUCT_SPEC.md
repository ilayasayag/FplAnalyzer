# WC26 Fantasy Draft — Product Spec (Endpoints + Validations)

> **Companion doc to `WC2026_PLAN.md`.**
> The plan covers data model, schedule, scoring, and background jobs. This doc nails down the **HTTP API surface** and **every validation rule** the platform must enforce. Anything not validated server-side is a bug.

---

## 0. Conventions

- **Base URL:** `/api/v1`
- **Auth:** `Authorization: Bearer <firebase-id-token>` on every endpoint except `GET /api/v1/wc/*`. The token resolves to a `uid`; the server NEVER trusts a `uid` passed in the body or URL when an action is being performed *on behalf of* that user — it always uses the authenticated `uid`.
- **Error format (RFC 7807 problem+json):**
  ```json
  {
    "type": "https://wc26/errors/lineup-locked",
    "title": "Lineup is locked",
    "status": 409,
    "code": "LINEUP_LOCKED",
    "detail": "GW4 lineup locked at 2026-07-01T16:00:00Z. Current time 2026-07-01T18:14:22Z.",
    "extensions": { "gw": 4, "lockAt": "2026-07-01T16:00:00Z" }
  }
  ```
  Frontends switch on `code` (machine-readable, stable); humans read `detail`.
- **Idempotency:** every mutating endpoint accepts `Idempotency-Key: <uuid>` header. Same key + same body within 24h → same response (cached). Same key + different body → `409 IDEMPOTENCY_KEY_REUSED`.
- **Rate limits:** see §13.
- **Timestamps:** ISO 8601 UTC. Client-side date display is local; server only stores UTC.
- **Pagination:** cursor-based. `?cursor=<opaque>&limit=50`, max `limit=100`. Response includes `nextCursor` (null when done).

---

## 1. Endpoint Catalogue (by domain)

### 1.1 Tournament & WC data (public, no auth)

| # | Method | Path | Returns | Caching |
|---|---|---|---|---|
| 1 | GET | `/wc/tournament` | `{ currentGw, status, season, gwDates }` | 5 min |
| 2 | GET | `/wc/teams` | Array of 48 teams + elimination status | 5 min |
| 3 | GET | `/wc/teams/{teamId}` | Single team + roster | 1 hour |
| 4 | GET | `/wc/players?position=&team=&group=&search=&cursor=` | Paginated player list | 5 min |
| 5 | GET | `/wc/players/{playerId}` | Player profile + season totals | 1 min |
| 6 | GET | `/wc/players/{playerId}/history` | Per-GW point breakdown (live during match) | 30s when live |
| 7 | GET | `/wc/players/{playerId}/fixtures` | Upcoming WC fixtures for player's team | 1 hour |
| 8 | GET | `/wc/fixtures?gw=&team=&from=&to=` | WC fixtures filtered | 5 min, 30s live |
| 9 | GET | `/wc/fixtures/{fixtureId}` | Single fixture + live stats | 30s live |
| 10 | GET | `/wc/gw/{n}` | GW info: dates, round, lockAt, status | 5 min |

### 1.2 Auth & User

| # | Method | Path | Notes |
|---|---|---|---|
| 11 | POST | `/auth/me` | Create/update profile after Firebase login. Body: `{ displayName, photoUrl, favouriteNationId? }`. |
| 12 | GET | `/auth/me` | Current user profile + league memberships |
| 13 | PATCH | `/auth/me` | Update `displayName`, `favouriteNationId` |
| 14 | DELETE | `/auth/me` | GDPR delete. 30-day grace period. |

### 1.3 League Management

| # | Method | Path | Notes |
|---|---|---|---|
| 15 | POST | `/leagues` | Create league. Body validated against §4. Returns `{ leagueId, inviteCode }`. |
| 16 | GET | `/leagues/{lid}` | League config + member list (visible to members only) |
| 17 | PATCH | `/leagues/{lid}` | Admin-only edit (name, tradeApproval, pickTimer). Locked once draft starts. |
| 18 | DELETE | `/leagues/{lid}` | Admin-only delete. Soft delete; members get notified. |
| 19 | POST | `/leagues/join` | Body: `{ inviteCode, teamName }`. Validations §5. |
| 20 | POST | `/leagues/{lid}/leave` | Member exits before draft starts. After draft starts → admin-only `kick` only. |
| 21 | POST | `/leagues/{lid}/kick` | Admin-only. Body: `{ uid, reason }`. Disabled after draft. |
| 22 | POST | `/leagues/{lid}/invite-code/rotate` | Admin invalidates old code, issues new |
| 23 | GET | `/leagues/{lid}/standings` | Full standings. Public to league members. |
| 24 | GET | `/leagues/{lid}/schedule?gw=` | H2H schedule. |
| 25 | GET | `/leagues/{lid}/knockout` | Bracket state. 404 before seeding. |
| 26 | GET | `/leagues/{lid}/scores/{gw}` | All-manager points for a GW. |
| 27 | GET | `/leagues/{lid}/scores/{gw}/audit` | Per-fixture, per-player breakdown for transparency |

### 1.4 Draft

| # | Method | Path | Notes |
|---|---|---|---|
| 28 | POST | `/leagues/{lid}/draft/start` | Admin only. Locks league, generates draft order. Validations §6. |
| 29 | GET | `/leagues/{lid}/draft/state` | Snake state: current round/pick/clock/order. Frontend should also `onSnapshot` Firestore for realtime. |
| 30 | POST | `/leagues/{lid}/draft/pick` | Body: `{ playerId }`. Validations §6.5. Idempotency-key required. |
| 31 | POST | `/leagues/{lid}/draft/watchlist` | Body: `{ playerId, add: bool }`. Private to caller. |
| 32 | POST | `/leagues/{lid}/draft/autopick` | Toggle auto-pick on missing turn. Body: `{ enabled, rankedPlayerIds[] }`. |
| 33 | POST | `/leagues/{lid}/draft/pause` | Admin only. Pauses clock. |
| 34 | POST | `/leagues/{lid}/draft/resume` | Admin only. |

### 1.5 Squad & Lineup

| # | Method | Path | Notes |
|---|---|---|---|
| 35 | GET | `/leagues/{lid}/squads/{uid}` | Squad list. Public to league members. |
| 36 | GET | `/leagues/{lid}/lineup/{gw}` | Caller's lineup for GW (own only) |
| 37 | PUT | `/leagues/{lid}/lineup/{gw}` | Set/replace lineup. Body: `{ starting[11], bench[4], formation, captain?, viceCaptain? }`. Validations §7. |
| 38 | PATCH | `/leagues/{lid}/lineup/{gw}` | Partial update (e.g. just swap two players, change captain). |
| 39 | GET | `/leagues/{lid}/lineup/{gw}/{uid}` | Opponent's lineup. Returns full only AFTER `lockAt`; before lock returns `{ locked: false, hint: 'lineup hidden until kickoff' }`. |

### 1.6 Transfers / Free Agents / Waivers

| # | Method | Path | Notes |
|---|---|---|---|
| 40 | GET | `/leagues/{lid}/transfer-window` | `{ open, number, opensAt, closesAt, freeRemaining }` |
| 41 | GET | `/leagues/{lid}/free-agents?position=&group=&sort=&cursor=` | Free agents (not owned, not on waivers) |
| 42 | POST | `/leagues/{lid}/free-agent` | Body: `{ playerIn, playerOut }`. Instant. Validations §8.1. |
| 43 | GET | `/leagues/{lid}/waivers` | All my pending waiver claims |
| 44 | POST | `/leagues/{lid}/waivers` | Body: `{ playerIn, playerOut }`. Validations §8.2. Same player can have multiple claimants — priority resolves it. |
| 45 | DELETE | `/leagues/{lid}/waivers/{wid}` | Cancel pending claim |
| 46 | PATCH | `/leagues/{lid}/waivers/{wid}` | Re-order priority within MY claims (server resolves in submitted order, but caller can rearrange) |
| 47 | GET | `/leagues/{lid}/waivers/queue` | League-wide priority list (which manager is next) |
| 48 | POST | `/leagues/{lid}/squad/drop` | Drop without picking up replacement. Player enters waivers. Forbidden if it leaves squad invalid. |

### 1.7 Trades

| # | Method | Path | Notes |
|---|---|---|---|
| 49 | POST | `/leagues/{lid}/trades` | Propose trade. Body: `{ targetUid, proposerPlayers[], targetPlayers[], message? }`. Validations §9. |
| 50 | GET | `/leagues/{lid}/trades?status=&direction=` | My trades (inbox/outbox/history) |
| 51 | POST | `/leagues/{lid}/trades/{tid}/respond` | Body: `{ action: "accept"|"decline" }`. Target user only. |
| 52 | POST | `/leagues/{lid}/trades/{tid}/cancel` | Proposer only. Before target responds. |
| 53 | POST | `/leagues/{lid}/trades/{tid}/veto` | If `tradeApproval == "vote"`. Body: `{ vote: "veto"|"approve" }`. |
| 54 | POST | `/leagues/{lid}/trades/{tid}/admin-decide` | If `tradeApproval == "admin"`. Admin only. |

### 1.8 Notifications

| # | Method | Path | Notes |
|---|---|---|---|
| 55 | GET | `/notifications?cursor=` | Paginated notif feed |
| 56 | POST | `/notifications/{nid}/read` | Mark single |
| 57 | POST | `/notifications/read-all` | Mark all |
| 58 | PATCH | `/auth/me/notification-prefs` | Toggle per-category (draft, elim, trades, scores) |

### 1.9 Admin (system-wide, not league admin)

| # | Method | Path | Notes |
|---|---|---|---|
| 59 | POST | `/admin/wc/sync` | Force WC squad/fixture sync from api-sports |
| 60 | POST | `/admin/fixtures/{fid}/reprocess` | Recompute fantasy points for a fixture |
| 61 | POST | `/admin/leagues/{lid}/gw/{gw}/finalize` | Manually finalize a GW |
| 62 | POST | `/admin/leagues/{lid}/knockout/regenerate` | Re-seed knockout (admin escape hatch) |

---

## 2. Realtime Channels

Most data is consumed via **Firestore `onSnapshot`** rather than HTTP polling. The HTTP endpoints above are for mutations and one-shot reads (server-side rendering, mobile cold-start, etc.).

| Channel | Path | Listeners |
|---|---|---|
| `draft.state` | `leagues/{lid}/draft/state` | All league members during draft |
| `draft.history` | `leagues/{lid}/draft/picks` | All league members |
| `scores.live` | `leagues/{lid}/scores/{gw}` | All members during a live GW |
| `lineup.locked` | `leagues/{lid}/lineups/*` (when `locked=true`) | All members after kickoff |
| `transfers.live` | `leagues/{lid}/transactions` | All members |
| `notifications` | `users/{uid}/notifications` | The user only |

---

## 3. Validation Framework

Every endpoint goes through three layers:

1. **Schema** — JSON Schema (or zod/pydantic) — types, ranges, enum values.
2. **State** — does the current league/tournament state allow this action right now?
3. **Authorization** — does this `uid` have permission?

Validation errors return `400` (schema), `409` (state conflict), or `403` (authz). NEVER `500` for user error.

Below: per-resource validation rules. Each rule has an `error_code` the frontend can switch on.

---

## 4. League Creation Rules — `POST /leagues`

**Body:**
```json
{
  "name": "El Clásico Friends",
  "size": 10,
  "pickTimer": 60,
  "tradeApproval": "vote",
  "draftAt": "2026-06-08T18:00:00Z"
}
```

| # | Rule | Error code | Trigger |
|---|---|---|---|
| 4.1 | `name` is 3–48 chars, no leading/trailing whitespace, no profanity | `LEAGUE_NAME_INVALID` | Schema |
| 4.2 | `size` ∈ {6, 7, 8, 9, 10} | `LEAGUE_SIZE_OUT_OF_RANGE` | Schema |
| 4.3 | `pickTimer` ∈ {30, 60, 90, 120, 180, 300} seconds | `PICK_TIMER_INVALID` | Schema |
| 4.4 | `tradeApproval` ∈ {`instant`, `vote`, `admin`, `none`} | `TRADE_APPROVAL_INVALID` | Schema |
| 4.5 | `draftAt` is in the future AND ≥ 24h from now AND ≤ 2026-06-10T20:00Z (last possible draft time before WC starts) | `DRAFT_DATE_INVALID` | State |
| 4.6 | Tournament status MUST be `pre_draft` or `drafting` | `TOURNAMENT_NOT_OPEN` | State |
| 4.7 | Caller is NOT over the per-user league limit (default 5 active leagues) | `LEAGUE_LIMIT_EXCEEDED` | Authz |

**Server computes (not from request body):**
- `knockoutStartGw` (4 for size 9-10; 7 for size 6-8)
- `leaguePhaseGws` ([1, 2, 3] for size 9-10; [1, 2, 3, 4, 5, 6] for size 6-8)
- `knockoutQualifiers` (8 for size 9-10; 4 for size 6-8)
- `inviteCode` (server-generated, 8 chars, base32, must be unique)
- `adminUid = authenticated caller`

---

## 5. Joining a League — `POST /leagues/join`

**Body:** `{ inviteCode, teamName }`

| # | Rule | Error code |
|---|---|---|
| 5.1 | `inviteCode` matches an existing league | `INVITE_CODE_NOT_FOUND` |
| 5.2 | League status is `pre_draft` (cannot join after draft starts) | `LEAGUE_DRAFT_ALREADY_STARTED` |
| 5.3 | Current member count `< size` | `LEAGUE_FULL` |
| 5.4 | Caller is not already a member | `ALREADY_IN_LEAGUE` |
| 5.5 | `teamName` is 2–32 chars, unique within league (case-insensitive) | `TEAM_NAME_TAKEN` / `TEAM_NAME_INVALID` |
| 5.6 | Caller has not been previously kicked from this league | `PREVIOUSLY_KICKED` |

---

## 6. Draft

### 6.1 Starting the draft — `POST /leagues/{lid}/draft/start`

| # | Rule | Error code |
|---|---|---|
| 6.1.1 | Caller is league admin | `NOT_LEAGUE_ADMIN` |
| 6.1.2 | League status is `pre_draft` | `DRAFT_NOT_PRE_DRAFT` |
| 6.1.3 | `members.length >= 4` AND `<= size` | `INSUFFICIENT_MEMBERS` |
| 6.1.4 | WC tournament status is `pre_draft` or `drafting` (not `group_phase`+) | `WC_ALREADY_STARTED` |
| 6.1.5 | `wc_players` collection is fully synced (≥ 600 players) | `PLAYER_DATA_INCOMPLETE` |

**Server side-effects on success:**
- Generate snake draft order (random permutation of members)
- Assign `draftPosition` 1..N to members
- Set `waiverPriority = reverse(draftPosition)` (last pick = highest waiver priority)
- Set league status → `drafting`
- Start the clock for pick #1

### 6.2 Making a pick — `POST /leagues/{lid}/draft/pick`

**Body:** `{ playerId }`

| # | Rule | Error code |
|---|---|---|
| 6.2.1 | League status is `drafting` | `NOT_DRAFTING` |
| 6.2.2 | It is **caller's turn** OR clock has expired (in which case server auto-picks for previous manager first) | `NOT_YOUR_TURN` |
| 6.2.3 | `playerId` exists in `wc_players` | `PLAYER_NOT_FOUND` |
| 6.2.4 | `playerId` is NOT already picked by ANY league member | `PLAYER_ALREADY_PICKED` |
| 6.2.5 | Caller's squad after pick respects position quotas (see §6.3) | `POSITION_QUOTA_EXCEEDED` |
| 6.2.6 | Caller's squad would still be completable for remaining positions (e.g. can't pick 3 GKs because then GK quota is over) | `POSITION_QUOTA_INCOMPLETABLE` |
| 6.2.7 | `Idempotency-Key` header is unique within last 24h | `IDEMPOTENCY_KEY_REUSED` |

### 6.3 Squad Position Quotas (15-player squad)

| Position | Min | Max |
|---|---|---|
| GK (1) | 2 | 2 |
| DEF (2) | 5 | 5 |
| MID (3) | 5 | 5 |
| FWD (4) | 3 | 3 |
| **Total** | **15** | **15** |

`POSITION_QUOTA_EXCEEDED` fires when picking a 6th DEF, 6th MID, 4th FWD, or 3rd GK.
`POSITION_QUOTA_INCOMPLETABLE` fires when, with picks remaining, you'd be mathematically locked out — e.g. you have 0 GKs and 0 picks left.

### 6.4 Auto-pick on clock expiry

When clock hits 0 with no pick:
1. If caller has an `autopick` queue, server picks the **first available** player from that queue that passes 6.2.4 and 6.2.5.
2. Else server picks the **highest-ranked** available player by `draft_rank` that passes quotas.
3. Notification `draft.auto_picked` sent to the manager.

### 6.5 Pause/Resume

- Only admin can pause/resume.
- Resume immediately restarts clock at remaining seconds (server stores `pausedAt`, computes `pickTimer - (pausedAt - turnStartedAt)`).
- Max total pause time per draft: 60 minutes. After that → `MAX_PAUSE_EXCEEDED`.

---

## 7. Lineup Rules — `PUT /leagues/{lid}/lineup/{gw}`

**Body:**
```json
{
  "starting": [pid1, pid2, ... pid11],
  "bench":    [pid12, pid13, pid14, pid15],
  "formation": [1, 4, 4, 2],
  "captain":   pid5,
  "viceCaptain": pid9
}
```

### 7.1 Schema validation

| # | Rule | Error code |
|---|---|---|
| 7.1.1 | `starting.length == 11` | `LINEUP_STARTING_SIZE` |
| 7.1.2 | `bench.length == 4` | `LINEUP_BENCH_SIZE` |
| 7.1.3 | `Set(starting ∪ bench).size == 15` (no dupes, full squad) | `LINEUP_DUPLICATES` |
| 7.1.4 | Every playerId exists in caller's squad (`leagues/{lid}/squads/{uid}.players`) | `LINEUP_NOT_IN_SQUAD` |
| 7.1.5 | `formation` is array `[gk, def, mid, fwd]` summing to 11, with `gk == 1` | `FORMATION_INVALID` |
| 7.1.6 | `captain` is in `starting` if provided | `CAPTAIN_NOT_STARTING` |
| 7.1.7 | `viceCaptain` is in `starting` and different from `captain` if provided | `VICE_CAPTAIN_INVALID` |

### 7.2 Formation rules

The starting XI must satisfy:

| Position | Min | Max |
|---|---|---|
| GK | **1** | **1** |
| DEF | **3** | **5** |
| MID | **2** | **5** |
| FWD | **1** | **3** |

So legal formations are:
`1-3-4-3, 1-3-5-2, 1-4-3-3, 1-4-4-2, 1-4-5-1, 1-5-3-2, 1-5-4-1, 1-5-2-3`

| # | Rule | Error code |
|---|---|---|
| 7.2.1 | Exactly 1 GK in `starting` | `LINEUP_GK_COUNT` |
| 7.2.2 | DEF count ∈ [3, 5] | `LINEUP_DEF_COUNT` |
| 7.2.3 | MID count ∈ [2, 5] | `LINEUP_MID_COUNT` |
| 7.2.4 | FWD count ∈ [1, 3] | `LINEUP_FWD_COUNT` |
| 7.2.5 | `formation` array matches counts in `starting` (server doesn't trust client) | `FORMATION_MISMATCH` |

### 7.3 Bench ordering

| # | Rule | Error code |
|---|---|---|
| 7.3.1 | `bench[0]` is the bench GK (the squad's other GK that's not starting) | `BENCH_GK_FIRST` |
| 7.3.2 | `bench[1..3]` are the 3 outfield bench players in **auto-sub order** (first to come on if needed) | — (no error, just convention) |

### 7.4 Lock window

| # | Rule | Error code |
|---|---|---|
| 7.4.1 | `now < gwDates[gw].lockAt` (UTC compare) | `LINEUP_LOCKED` |
| 7.4.2 | League status is `group_phase` or `knockout` (not `pre_draft` or `drafting`) | `WC_NOT_STARTED` |
| 7.4.3 | `gw` is the current GW (no setting lineups for future GWs that haven't opened yet — open at `previousGwLockAt + 1`) | `GW_NOT_OPEN_FOR_LINEUP` |

### 7.5 Eliminated players in lineup

| # | Rule | Error code |
|---|---|---|
| 7.5.1 | Eliminated players in `starting` are **allowed but warned**. Response includes `warnings: [{ code: "STARTING_HAS_ELIMINATED", playerId }]` per dead player. | (warning, not error) |
| 7.5.2 | If ALL bench outfield players are eliminated, response also warns `BENCH_ALL_ELIMINATED` | (warning) |
| 7.5.3 | If GK starting AND bench GK are both eliminated, server STILL accepts (the manager may have had no other choice during a closed window) but warns `GK_ALL_ELIMINATED` | (warning) |

> **Why warnings, not errors?** During a closed transfer window the manager has no way to swap. Hard-rejecting would lock them out of even setting a captain.

---

## 8. Transfers

### 8.1 Free agent pickup — `POST /leagues/{lid}/free-agent`

**Body:** `{ playerIn, playerOut }`

| # | Rule | Error code |
|---|---|---|
| 8.1.1 | Transfer window is **open** | `WINDOW_CLOSED` |
| 8.1.2 | Window's `transfersUsed[uid] < ∞` (no hard cap, but free transfer count tracked) | — |
| 8.1.3 | `playerOut` is in caller's current squad | `PLAYER_OUT_NOT_OWNED` |
| 8.1.4 | `playerIn` exists | `PLAYER_NOT_FOUND` |
| 8.1.5 | `playerIn` is NOT owned by any manager in this league | `PLAYER_ALREADY_OWNED` |
| 8.1.6 | `playerIn` is NOT in the waivers pool (must be claimed via waivers) | `PLAYER_ON_WAIVERS` |
| 8.1.7 | `playerIn` is NOT in any other open waiver claim by another league manager (race protection) | `PLAYER_ALREADY_CLAIMED` |
| 8.1.8 | Resulting squad respects 2/5/5/3 position quotas (see §6.3) | `POSITION_QUOTA_VIOLATED` |
| 8.1.9 | `playerIn.team` is NOT eliminated (cannot pick up dead-nation players — useless and clutters squad) | `PLAYER_TEAM_ELIMINATED` |

### 8.2 Waiver claim — `POST /leagues/{lid}/waivers`

| # | Rule | Error code |
|---|---|---|
| 8.2.1 | Transfer window is open AND we're in **waiver phase** (first 24h of window) | `WAIVER_PHASE_CLOSED` |
| 8.2.2 | Rules 8.1.3, 8.1.4, 8.1.8, 8.1.9 (same as free agent) | (same codes) |
| 8.2.3 | `playerIn` IS in the waivers pool | `PLAYER_NOT_ON_WAIVERS` |
| 8.2.4 | Caller has not already submitted a duplicate claim (same `playerIn`+`playerOut`) | `DUPLICATE_WAIVER_CLAIM` |
| 8.2.5 | Caller does not have >10 pending waivers (anti-spam) | `WAIVER_CLAIM_LIMIT` |

### 8.3 Drop — `POST /leagues/{lid}/squad/drop`

| # | Rule | Error code |
|---|---|---|
| 8.3.1 | Window is open | `WINDOW_CLOSED` |
| 8.3.2 | `playerOut` is owned by caller | `PLAYER_OUT_NOT_OWNED` |
| 8.3.3 | Resulting squad (14 players) STILL has at least 1 player per position (i.e. dropping a sole GK is allowed only if you have another GK) | `POSITION_QUOTA_INCOMPLETABLE` (variant) |

> After a drop, the squad is intentionally under 15 — manager is given a 24-hour grace period to pick up a replacement before lineup-set is blocked.

---

## 9. Trades — `POST /leagues/{lid}/trades`

**Body:** `{ targetUid, proposerPlayers: [pid…], targetPlayers: [pid…], message? }`

| # | Rule | Error code |
|---|---|---|
| 9.1 | `targetUid` is a member of this league AND `≠ caller` | `TRADE_TARGET_INVALID` |
| 9.2 | `proposerPlayers.length ≥ 1` AND `≤ 5` | `TRADE_SIZE_INVALID` |
| 9.3 | `targetPlayers.length ≥ 1` AND `≤ 5` | `TRADE_SIZE_INVALID` |
| 9.4 | `proposerPlayers.length == targetPlayers.length` (1-for-1, 2-for-2, etc — no lopsided trades to keep position counts balanced) | `TRADE_NOT_BALANCED` |
| 9.5 | All `proposerPlayers` are owned by caller | `PROPOSER_PLAYERS_NOT_OWNED` |
| 9.6 | All `targetPlayers` are owned by `targetUid` | `TARGET_PLAYERS_NOT_OWNED` |
| 9.7 | Position composition is preserved on **both sides** (proposer's net delta per position = 0). Translation: you must trade a GK for a GK, DEF for DEF, etc. Mixed-position trades are rejected. | `TRADE_POSITION_MISMATCH` |
| 9.8 | Transfer window is open OR league config allows trades during GW (configurable) | `TRADES_BLOCKED_WINDOW_CLOSED` |
| 9.9 | Caller has < 5 pending outgoing trades | `TRADE_LIMIT_EXCEEDED` |
| 9.10 | `targetUid` has < 10 pending incoming trades (anti-spam) | `TARGET_TRADE_LIMIT` |
| 9.11 | None of the involved players are mid-fixture (i.e. their match has kicked off and not finished) | `PLAYER_MID_FIXTURE` |
| 9.12 | `message` ≤ 280 chars, no profanity | `TRADE_MESSAGE_INVALID` |

### 9.13 Response flow by `tradeApproval`

| approval | After target accepts |
|---|---|
| `instant` | Executes immediately |
| `vote` | Opens 24h voting window. Trade vetoed if `≥ ceil(N/3)` league members vote veto. Else executes. |
| `admin` | Status `awaiting_admin`. Admin posts to `/admin-decide`. |
| `none` | Trades endpoint returns `TRADES_DISABLED` on `POST /trades` |

---

## 10. Scoring & Score Audits

Scoring is **server-only**. The client never computes points for display purposes — it reads from `leagues/{lid}/scores/{gw}`. The audit endpoint (#27) returns:

```json
{
  "gw": 3,
  "uid": "u_me",
  "totalPoints": 65,
  "players": [
    {
      "playerId": "p_yamal",
      "fixtureId": 12345,
      "minutes": 90,
      "goals": 1, "assists": 1, "cleanSheet": false,
      "goalsConceded": 1, "yellowCards": 0, "redCards": 0,
      "saves": 0, "penaltyMissed": 0, "penaltySaved": 0, "ownGoal": 0,
      "bonus": 0,
      "componentBreakdown": [
        { "code": "MIN_60_PLUS", "value": 2 },
        { "code": "GOAL_MID",    "value": 5 },
        { "code": "ASSIST",      "value": 3 },
        { "code": "CS_MID",      "value": 1 },
        { "code": "GC_PENALTY",  "value": -1 }
      ],
      "totalPoints": 10,
      "autoSubbedOut": false
    }
  ],
  "autoSubs": [{ "in": "p_canc", "out": "p_walker" }],
  "captain": "p_kane",
  "captainBonus": 4
}
```

### 10.1 Score immutability

- Once `scores/{gw}.processed == true`, points **never** change without an admin override.
- Admin override creates a new row in `scores/{gw}/auditLog` recording who/when/why.
- All managers in the league get a `score.adjusted` notification.

---

## 11. Knockout Bracket

### 11.1 Seeding (auto-triggered on `gw == knockoutStartGw - 1` finalize)

Per the .md:
- **N > 8**: seeds 1–4 = top H2H, seeds 5–8 = best remaining `fpts`, 8 qualifiers → QF/SF/Final
- **N ≤ 8**: seeds 1–2 = top H2H, seeds 3–4 = best remaining `fpts`, 4 qualifiers → SF/Final
- Bracket pattern: 1v8, 2v7, 3v6, 4v5 (QF) / 1v4, 2v3 (SF) / winners SF1 vs SF2 (Final)

### 11.2 Advancement validation

When a knockout GW finalizes:

| # | Rule | Effect |
|---|---|---|
| 11.2.1 | Winner = manager with higher `points` for that GW | normal |
| 11.2.2 | Tie → winner = manager with higher **season** `fpts` | tiebreaker 1 |
| 11.2.3 | Still tied → server-side coin flip (seeded with `lid + gw + match.id` for determinism) | tiebreaker 2 |
| 11.2.4 | Loser's `eliminated` flag set; `eliminatedAtGw` recorded | bookkeeping |
| 11.2.5 | Next round match auto-created with `home/away = previousMatch.winners` | auto |

---

## 12. Lineup Auto-Substitution (server-side, fires when all GW fixtures `FT`)

```
For each starting player who played 0 minutes:
  For each bench player in bench-order (GK first only if starting GK didn't play):
    if bench player played ≥ 1 minute AND
       swapping them in keeps a valid formation (rule 7.2):
      perform swap, record { in, out } in lineup.autoSubsMade
      break
```

| # | Rule | Effect |
|---|---|---|
| 12.1 | Auto-subs ONLY consider bench players who played ≥ 1 minute | rule |
| 12.2 | GK bench slot can only swap in for starting GK | rule |
| 12.3 | If no valid sub found, starter stays with 0 points | rule |
| 12.4 | Captain points doubled. If captain didn't play, vice-captain becomes effective captain. If neither played, no captain bonus. | rule |

---

## 13. Rate Limits

| Bucket | Limit | Per |
|---|---|---|
| Auth endpoints | 30 req | minute / IP |
| Mutating endpoints (POST/PUT/PATCH/DELETE) | 60 req | minute / uid |
| Read endpoints | 600 req | minute / uid |
| Draft pick | 1 req | 2s / uid (debounce) |
| WC public data | 200 req | minute / IP |

Exceeded → `429 RATE_LIMITED` with `Retry-After` header.

---

## 14. WC API request budgeting (api-sports)

Server-side scheduled job rules:

| # | Rule | Why |
|---|---|---|
| 14.1 | Only poll `live` fixtures (never all 104) every 5 min | Saves 100s of req/day |
| 14.2 | Once `fixture.processedForFantasy == true` → never refetch unless admin triggers `reprocess` | Permanent cache for completed matches |
| 14.3 | Player squad sync runs at most once per 7 days | Squads stable during WC |
| 14.4 | Total daily request count tracked in `wc_api_usage/{date}.requests` — alert if > 80 | Stay under 100/day free tier |

---

## 15. Permission Matrix (who can do what)

| Action | Anyone | League Member | League Admin | System Admin |
|---|:-:|:-:|:-:|:-:|
| View WC data | ✓ | ✓ | ✓ | ✓ |
| Create league | ✓ | ✓ | ✓ | ✓ |
| Join league | ✓ | — | — | — |
| View league standings | — | ✓ | ✓ | ✓ |
| Set own lineup | — | ✓ | ✓ | ✓ |
| Submit trade / waiver | — | ✓ | ✓ | ✓ |
| View other members' squads | — | ✓ | ✓ | ✓ |
| View opponent lineup BEFORE lock | — | — | — | ✓ |
| Start draft | — | — | ✓ | ✓ |
| Pause/resume draft | — | — | ✓ | ✓ |
| Edit league settings | — | — | ✓ | ✓ |
| Kick member | — | — | ✓ | ✓ |
| Decide admin-approved trade | — | — | ✓ | ✓ |
| Force-finalize GW | — | — | — | ✓ |
| Reprocess fixture | — | — | — | ✓ |
| Regenerate knockout | — | — | — | ✓ |

---

## 16. Error code reference (machine-readable)

Frontends should switch on `error.code` and show localized messages. Codes are stable across versions.

| Code | HTTP | Meaning |
|---|---|---|
| `LINEUP_LOCKED` | 409 | GW lineup window has closed |
| `LINEUP_STARTING_SIZE` | 400 | Starting XI is not exactly 11 |
| `LINEUP_GK_COUNT` | 400 | Starting GK count ≠ 1 |
| `LINEUP_DEF_COUNT` | 400 | DEF count not in [3,5] |
| `LINEUP_MID_COUNT` | 400 | MID count not in [2,5] |
| `LINEUP_FWD_COUNT` | 400 | FWD count not in [1,3] |
| `FORMATION_INVALID` | 400 | Formation array malformed |
| `FORMATION_MISMATCH` | 400 | Formation doesn't match starting composition |
| `LINEUP_DUPLICATES` | 400 | Duplicate player IDs in lineup |
| `LINEUP_NOT_IN_SQUAD` | 400 | Player not owned by manager |
| `POSITION_QUOTA_EXCEEDED` | 409 | Squad quota for position is full |
| `POSITION_QUOTA_INCOMPLETABLE` | 409 | Squad can't be completed with remaining picks |
| `WINDOW_CLOSED` | 409 | Transfer window is closed |
| `WAIVER_PHASE_CLOSED` | 409 | Past T+24h, in free-agent phase |
| `PLAYER_ALREADY_OWNED` | 409 | Player is on another manager's squad |
| `PLAYER_ON_WAIVERS` | 409 | Use waiver claim instead of free-agent pickup |
| `PLAYER_TEAM_ELIMINATED` | 409 | Cannot pick up dead-nation player |
| `PLAYER_MID_FIXTURE` | 409 | Player's match is in progress |
| `NOT_YOUR_TURN` | 409 | Draft pick attempted out of turn |
| `PLAYER_ALREADY_PICKED` | 409 | Drafted by someone else first |
| `TRADE_NOT_BALANCED` | 400 | Sides not equal in count |
| `TRADE_POSITION_MISMATCH` | 400 | Mixed-position trade rejected |
| `LEAGUE_FULL` | 409 | Cannot join — full |
| `LEAGUE_DRAFT_ALREADY_STARTED` | 409 | Cannot join after draft |
| `NOT_LEAGUE_ADMIN` | 403 | Admin-only action |
| `TOURNAMENT_NOT_OPEN` | 409 | League create blocked — WC in wrong status |
| `IDEMPOTENCY_KEY_REUSED` | 409 | Same key, different body |
| `RATE_LIMITED` | 429 | Slow down |

---

## 17. Open product questions (not yet answered)

The .md doesn't specify these. Recommended defaults below — flag for review:

| # | Question | Recommended default |
|---|---|---|
| 17.1 | Can a manager join multiple leagues with the same Firebase account? | **Yes**, up to 5 active leagues per user. |
| 17.2 | Does the captain double points apply during knockout? | **Yes** — consistent with group phase. |
| 17.3 | What if a knockout match ties and BOTH managers have identical season `fpts`? | **Higher seed advances** (no coin flip — feels less arbitrary). Override the .md's coin-flip rule. |
| 17.4 | If a manager leaves a league mid-tournament, what happens to their squad? | Squad **frozen** — they keep scoring (0s if eliminated nations), no auto-replacement. Cannot kick post-draft. |
| 17.5 | Can a manager use the same player for captain across consecutive GWs? | **Yes** — no triple-captain or wildcard chips in v1 (keep it simple). |
| 17.6 | Are draft watchlists visible to other league members? | **No** — private to caller. |
| 17.7 | What's the bonus point system source — api-sports BPS or our own formula? | Use **api-sports BPS** directly. Mirror to fantasy bonus (top 3 BPS per fixture get 3/2/1 fantasy bonus). |
| 17.8 | Can the admin retroactively edit league settings (e.g. trade approval) mid-season? | **Locked after draft starts** except for `tradeApproval`, which admin can change between GWs. |
| 17.9 | What happens when api-sports goes down on match day? | Cached `wc_fixtures` data still serves reads. Scoring is **delayed**, not lost. Notification `scoring.delayed` to all active leagues. |
| 17.10 | Free transfers carry over between windows? | **No** — use it or lose it. Keeps decisions urgent during the BIG window 3. |

---

## 18. Implementation checklist (server-side)

- [ ] All validation rules above are **server-enforced**. Client-side mirroring is optional UX sugar only.
- [ ] Every mutating endpoint accepts and respects `Idempotency-Key`.
- [ ] Every error response uses `application/problem+json` with stable `code`.
- [ ] Authz checks happen BEFORE schema validation (don't leak "this resource exists" via 400).
- [ ] All timestamps stored UTC; lockAt comparisons use server clock (NEVER trust client time).
- [ ] Background jobs (poll_live_scores, daily_sync) are idempotent — can rerun safely.
- [ ] Audit log table for: score adjustments, admin overrides, kicks, knockout regenerations.
- [ ] Webhook signatures verified on any third-party (api-sports) callback.
