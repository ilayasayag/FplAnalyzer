# FPL Draft 2026/27 — value model & live draft room

Self-contained side project. **Unrelated to the WC 2026 code in the rest of this repo** —
it lives in its own directory, imports nothing, and is imported by nothing. It is here
because the previous iteration of this work was lost twice (scratchpad wiped, nothing
committed) and the surviving copies were browser artifacts only.

Built 19 Aug 2026, four days before the 26/27 season opens (GW1: Fri 21 Aug).

---

## What's here

| Path | What it is |
|---|---|
| `data/sources.json` | **The raw dataset.** Draft Fantasy's 240-player table, three transcribed draft boards, per-club first-5 fixtures, injury flags. Hand-authored; the only file that isn't derived. |
| `pipeline/build.py` | The whole pipeline. Name canonicalization → snake-order correction → consensus ADP → value estimation for unmatched players → validation report → writes both outputs. |
| `pipeline/template.html` | Draft-room page source, with `__MODEL_JSON__` as the injection point. |
| `data/model.json` | Derived. 309 players with value + ADP + delta. |
| `app/warroom.html` | Derived. The standalone draft-room page — all data inlined, no network calls, opens from disk. |

Rebuild everything with:

```bash
python3 fpl-draft-2627/pipeline/build.py
```

No dependencies beyond the standard library. `data/model.json` and `app/warroom.html`
are committed anyway, deliberately — the point of this directory is that it survives
without a working toolchain.

The directories are named `pipeline/` and `app/` rather than the conventional
`build/` and `dist/` because this repo's `.gitignore` excludes both of those names
repo-wide for the WC2026 frontend. Renaming keeps that shared config untouched.

Published artifact (same bytes as `app/warroom.html`):
https://claude.ai/code/artifact/0f498368-f71f-49bf-b60b-f9f08be10572

---

## Method

**ADP.** Each board is snake-corrected to overall pick numbers, then normalized to a
*fractional round*, `fr = (overall − 1) / teams + 1`, so 8-, 10- and 14-team drafts are
comparable. Consensus ADP is the mean across boards, imputing `lastRound + 1` where a
player went undrafted. Availability at pick `t` is `Φ((adp − t) / σ)`, σ from the
cross-board spread with a 0.8-round floor.

**Value.** Edge comes from Draft Fantasy directly (their VOR baseline: points above the
best undrafted alternative at the position). Players outside their 240 — 69 of 309 —
get Edge interpolated from where the market drafts them and are flagged `EST`.

**Pick score.** `Edge + 0.9·urgency − stack − injury (+ must-fill)`, where urgency is the
VONA drop: best available Edge now minus the best Edge at least 50% likely to survive to
your next snake pick. Stack is −8 per player beyond two from one club; injured −15,
doubtful −6; must-fill +25 when remaining picks barely cover empty roster slots.

**Sources.** Draft Fantasy cheat sheet (fetched 19 Aug 2026); three real completed drafts
supplied as screenshots; premierleague.com for fixtures and the 26/27 manager list;
Draft FC's "Value-Based Drafting" video for the VOR/VOLS/VONA framing and cliff logic.

---

## For the previous agent: what to compare

You built a parallel version of this from 15 leagues with four independent 0–100 measures
and a hand-built VBD engine. That work is gone except for your handoff prose and three
artifacts. This rebuild took a different route — please compare and tell us where you
disagree.

**Where we converge.** Your handoff reported your engine, calibrated on Draft Fantasy's
anchors, produced Haaland +149 / B.Fernandes +117 / Gabriel +116 against their published
+149.3 / +116.1 / +115.6. This build uses those published values directly, so the top of
the board is identical by construction. That agreement is why I treated their table as
trustworthy rather than rebuilding projections from scratch.

**Where we deliberately diverge.**

1. **Projections are no longer ours.** You projected independently and calibrated to
   theirs. I consume theirs. Cheaper and better-provenanced, but it means a single point
   of failure and no second opinion where their model is weird — Isak at #117 is the
   loudest example. If your per-player numbers can be recovered, a two-model blend would
   be strictly better than either.
2. **Your four 0–100 measures are absent.** Form, minutes-security, fixtures, balanced —
   I have your description of them but not one player value, and you flagged Balanced as
   noisy yourself. Worth recovering? Your call.
3. **3 boards, not 15.** This is the real regression. σ is floored at 0.8 rounds to stop
   three samples from faking confidence. Your other twelve boards would materially
   improve every availability probability in the tool.
4. **No hardcoded fudges.** Per your explicit warning, the −45 goalkeeper penalty and the
   shape-pacing correction were *not* reintroduced. Positional scarcity is handled by
   Edge and by VONA urgency, so those hacks stay unnecessary. Please confirm nothing here
   smuggles them back in.

**Open questions for you.**

- Do your 15-league boards survive anywhere — a screenshot folder, a chat scrollback?
- Same for the RotoWire predicted lineups and FFS team-news snapshot from 17–18 Aug.
  Stale is still better than the nothing we have.
- Your handoff mentions a rebuild that drifted by one pick (1,840 vs 1,839). Do you know
  which board and which round? My transcription found no duplicate or short rows, so if
  the drift is in a board I also transcribed, one of us is wrong.
- Four club labels you marked "high-probability but unconfirmed" — which four?

---

## Known soft spots

- Boards were transcribed by eye from screenshots. No duplicate picks and no malformed
  rows survived validation, but deep-round names and clubs may still be off. Around ten
  ambiguous club labels were resolved against Draft Fantasy rather than the screenshot.
- Three ADP samples is thin, and one of the three is a 14-team league whose deep rounds
  have no counterpart in the 8-team board.
- Edge for the 69 `EST` players is market-implied, not projected. It is circular by
  construction: it says where people draft them, not how good they are.
- Injury data is only Draft Fantasy's two flags (Ekitiké injured, Mukiele doubtful).
  **There are no predicted lineups in this dataset at all.** With nine managerial changes
  for 26/27 — Liverpool, Man City, Man Utd, Chelsea, Spurs among them — minutes security
  outside obvious starters is guesswork. Re-check team news before drafting.
- The LöfLife Reddit cheat sheet is still unfetched; Reddit is blocked from every tool
  available in these sessions. Third session running.
- Draft Fantasy's xP is one model. Where it violently disagrees with the market, the tool
  surfaces the disagreement rather than resolving it.

---

## What the model currently says

Consistent across all three leagues: the market drafts last season's names, and the
projections have moved on.

**Underpriced** — Senesi (model #15, drafted round 7–11), Muñoz, Mukiele, Stach,
Truffert, Rúben Dias, Richarlison, Welbeck. Defensive-contribution defenders are
systematically cheap.

**Overpriced** — Isak (~5th overall, model #117 after his move), Wirtz, Palmer in rounds
1–2, Tzolis in round 3, Ødegaard, Pedro Porro.

**Goalkeepers** — flat after Raya, Donnarumma and Roefs. Never take a second keeper early.

**Waiver note** — Keane (EVE) is the only model top-60 player undrafted in all three
leagues.
