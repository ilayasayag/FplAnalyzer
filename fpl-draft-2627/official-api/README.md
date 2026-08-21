# Official-API build — FPL Draft 26/27

Companion to `../` (PR #284). Same project, different spine: this one is built on the
**official `draft.premierleague.com` API** rather than on transcribed screenshots.

Complementary, not a replacement — it consumes that PR's Draft Fantasy table as one of
four opinion layers. Nothing here overwrites anything there.

```bash
python3 build.py              # fetch live + rebuild model.json and warroom.html
python3 build.py --offline    # reuse the cached boot.json
python3 live.py <league-id> --seat <n>   # live draft monitor, polls every 5s
```

Standard library only.

---

## Why the official API

`GET /api/bootstrap-static` is public, unauthenticated, and gives us things no
screenshot or third-party table can:

| Field | What it replaces |
|---|---|
| `id`, `web_name`, `team`, `element_type` | the entire hand-built name/club registry — and the name-collision problem with it |
| `status`, `news`, `chance_of_playing_next_round` | the stale RotoWire/FFS snapshot. **Live**, and it is the source the game itself uses |
| `draft_rank` | FPL's own draft ranking, for all 595 players |
| `total_points`, `points_per_game`, `minutes`, `defensive_contribution` | real prior-season stats including DefCon |
| `fixtures`, `teams` | real GW1–6 fixtures; club strength is derived from last season's points rather than hand-assigned |

`GET /api/draft/<league-id>/choices` is also public and returns every pick live —
`index`, `round`, `entry`, `entry_name`, `element`, `was_auto`. That is the live-draft
feed both tools consume.

## Four opinions, disagreement flagged not resolved

Weights are adjustable live in the war room (default 40/25/20/15):

1. **FPL official `draft_rank`** — the game's own board
2. **Draft Fantasy xP + edge** — 240 players, from `../data/sources.json`
3. **LöfLife sheet tiers** — 188 players
4. **15-league consensus ADP** — 89 players, snake-corrected, 8-team scale

A player is marked `contested` when the official rank and Draft Fantasy disagree by
40+ places and FPL rates him inside the top 200. **62 players qualify, and every one
runs the same direction: Draft Fantasy fades him.**

The cause is visible in the data — these are players who missed most of last season, so
a projection model regressing on minutes crushes them:

| Player | FPL# | DF# | LöfLife | our ADP | last-season pts |
|---|---|---|---|---|---|
| Isak | 5 | 98 | tier 2 | 7.1 | **41** (transfer saga) |
| Havertz | 22 | 78 | tier 8 | — | **36** (injured) |
| Rashford | 30 | 133 | tier 10 | 73.9 | **0** (on loan abroad) |
| Maddison | 51 | 207 | tier 11 | — | **3** (ACL) |
| Tzolis | 55 | 202 | tier 7 | 34.8 | **0** (at Club Brugge) |

Take Draft Fantasy's xP at face value and the board tells you to pass on Isak, Palmer,
Wirtz, Doku and Cherki early. Three other sources disagree. The tool shows the conflict
rather than silently picking a winner.

## Value model

Unchanged in principle from the earlier build, and deliberately free of hand-tuned
positional fudges:

- Blended rank → per-position rank → points curve → **edge over a positional baseline**.
- Baselines selectable live: **VOR / VOLS / VONA**.
- Curve calibrated to Draft Fantasy's published anchors. Forward spread ≈149 pts,
  goalkeeper spread ≈32 — which is why keepers slide on their own. There is **no
  goalkeeper penalty and no shape-pacing term** anywhere in this code.
- Bench slots discounted ×0.22 (a backup keeper never starts).
- Fixtures outweigh projection from R7, and dominate from R13.
- Hard caps: squad **2/5/5/3** (from the API's own `settings.squad`), max 3 per club.

## Live sync

The published artifact **cannot fetch anything** — the viewer CSP blocks all external
requests, and the available runtime capabilities (`artifact`, `downloads`, `mcp`, `self`)
include no general network access. So there are two supported paths:

1. **Paste bridge (no setup).** Open
   `draft.premierleague.com/api/draft/<league-id>/choices` in a tab, select all, paste
   into the war room's sync box. Re-paste any time to catch up. Verified against a real
   completed 14-team draft: **210/210 picks, all 14 seats at exactly 15, zero duplicates.**
2. **`live.py` (hands-free).** Polls the same endpoint every 5s and prints who is on the
   clock, your squad, a per-position priority bar, and the ranked take-next list.

Every player still in the league is kept in `model.json` (558), not just the draftable
top few hundred. If someone in your room drafts an obscure squad player and he is missing
from the pool, the sync silently drops that pick and the board wrongly shows him as
available — that bug was real and is why the pool is wide.

## Soft spots

- Club strength for the fixture rating is derived from last season's total points, which
  under-rates promoted sides and clubs that rebuilt.
- The 89 ADP samples come from 15 transcribed screenshots and carry that transcription risk.
- `chance_of_playing_next_round` is only as fresh as your last `build.py` run. Re-run it on
  draft day; that is the whole point of it being an API call rather than a snapshot.
- Draft Fantasy's xP is one model, and the `contested` flag is a warning, not a correction.
