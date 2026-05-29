# WC26 Fantasy Draft

Hi-fidelity, fully-interactive UI prototype for a World Cup 2026 Fantasy Draft platform — built to align design and engineering before backend implementation begins.

> **Stack:** vanilla React 18 + Babel-in-browser, no build step. Open `WC26 Fantasy Draft.html` in any modern browser. Designed for 1440px+ desktop.

---

## What's in this package

```
WC26 Fantasy Draft.html      ← entry point — open this
styles.css                   ← global design tokens + utility classes

data.jsx                     ← all mock data: 48 nations, ~90 players,
                               10-manager league "El Clásico Friends",
                               state = "just after GW3, knockout seeded"
components.jsx               ← shared: Flag, Jersey, Pitch, PlayerSlot
shell.jsx                    ← TopBar, Hero, SubNav, right-hand Sidebar

screens-status.jsx           ← Status, Points, Pick Team screens
screens-data.jsx             ← Player Browser, Fixtures, League, Trades
screens-bracket.jsx          ← Knockout Bracket, Transfers/Waivers
screens-draft.jsx            ← Draft Room, Create / Join League flow

player-stats-modal.jsx       ← Per-player stats board (click "i" on jersey)
tweaks-panel.jsx             ← Live design-tweak controls (theme, GW phase…)
app.jsx                      ← Router + Tweaks state + app shell

WC2026_PLAN.md               ← Original product plan (source of truth)
PRODUCT_SPEC.md              ← Full API surface + every server-side validation
README.md                    ← This file
```

---

## Implementation notes for the backend

`PRODUCT_SPEC.md` is the contract. The frontend currently uses mock data; replace with real fetches against the endpoints defined there. Key points:

1. **Authoritative state on the server.** Every validation in `PRODUCT_SPEC.md` §4–§12 must run server-side, even if mirrored client-side for UX.
2. **Realtime via Firestore `onSnapshot`** rather than HTTP polling — see §2 of the spec for which collections to watch.
3. **Idempotency keys** required on all mutating endpoints (handles flaky mobile networks during a live draft).
4. **api-sports.io** is the upstream data source — see `WC2026_PLAN.md` §4 for the client wrapper spec and request budget rules.
5. **Scoring is server-only.** The frontend reads `leagues/{lid}/scores/{gw}` and never computes points itself.

### Hot integration points

| Frontend touchpoint | Server contract |
|---|---|
| `data.jsx` → `PLAYERS`, `TEAMS` | `GET /api/v1/wc/players`, `GET /api/v1/wc/teams` |
| `data.jsx` → `MY_SQUAD_IDS`, `MY_LINEUP_GW3` | `GET /api/v1/leagues/{lid}/squads/{uid}`, `GET .../lineup/{gw}` |
| `data.jsx` → `STANDINGS`, `BRACKET` | `GET .../standings`, `GET .../knockout` |
| `screens-draft.jsx` → `DraftRoomScreen` | Firestore `leagues/{lid}/draft/state` snapshot + `POST .../draft/pick` |
| `screens-bracket.jsx` → `TransfersScreen` | `GET .../transfer-window`, `POST .../free-agent`, `POST .../waivers` |
| `app.jsx` → elimination banner | Firestore `leagues/{lid}/eliminations` or polled `GET .../squads/{uid}?include=eliminationStatus` |

### Mock-data shape ↔ Firestore shape

The mock `TEAMS`, `PLAYERS`, etc. in `data.jsx` are **shape-compatible** with the Firestore schema in `WC2026_PLAN.md` §3 *except*:
- `team.flag` / `team.vert` (colour arrays) are presentational only — the real backend doesn't need to store these. Frontend derives flag image URL from `team.iso` (ISO-3166 alpha-2 code, in `FLAG_ISO` map in `components.jsx`).
- `player.elim` is a denormalised mirror of `team.elim` — backend should compute on read, not store, or update both atomically.

### What I'd do first

1. Stand up `WC2026Client` (api-sports wrapper) per `WC2026_PLAN.md` §4. Sync 48 teams + ~1,248 players into Firestore (~48 API calls, one-shot).
2. Hardcode `wc_config/tournament.gwDates` from §1 of the plan — these don't change.
3. Build the league create + join + draft endpoints first (`PRODUCT_SPEC.md` §1.3, §1.4) — gate everything else on a live league existing.
4. Score processing pipeline (§5 of plan + §10 of spec) — this is the gnarliest and most testable in isolation.
5. Lineup PUT with validation (§7) — straightforward but lots of edge cases.
6. Transfers + waivers (§8) — defer until GW1 actually finishes.

### Open product questions
See `PRODUCT_SPEC.md` §17 — 10 design decisions the original plan didn't pin down, with my recommendations. Worth confirming with product before coding.

---

## Running the prototype

No build needed. Either:

```bash
# Option A — any static server
python3 -m http.server 8000
# then open http://localhost:8000/WC26%20Fantasy%20Draft.html

# Option B — VS Code Live Server extension
# right-click WC26 Fantasy Draft.html → "Open with Live Server"
```

The flag images load from `cdn.jsdelivr.net/gh/lipis/flag-icons` over the network. For fully offline use, swap `Flag` in `components.jsx` to point at locally bundled SVGs.

### Tweaks panel

Bottom-right corner has a live controls panel (themed colors, league size hint, GW phase, banner toggle). Not part of the product — just for design iteration.

### Player stats modal

Hover any jersey on the pitch or in tables, click the white "i" badge top-right → opens the full Premier League–style player stats board.

---

## Caveats (honest)

- **Pick Team swap is click-based**, not true HTML5 drag-and-drop. Click one player, then click another to swap.
- **Tweaks → "League size"** is currently a visual hint; doesn't dynamically reshape standings/bracket. Real app should do this server-side.
- **Mock data has ~90 players**; production needs the full ~1,248 from api-sports.
- **No auth flow** in the prototype — assume Firebase Auth + ID token bearer as described in `PRODUCT_SPEC.md` §0.
- **Flags via external CDN** — see note above.
- **Italy is "eliminated" in mock data** despite being in Group B with ARG/JPN/EGY. This is intentional — the prototype is set at the "just after group stage" moment showing 16 teams out. Adjust as group stage results emerge.
