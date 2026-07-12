"""
WC2026 knockout free-agent LIVE swap-draft engine.

Distinct from the group-phase *bid* auction (``wc_wishlist``) and from the
original *snake* draft (``draft``): this is a live, on-the-clock draft the 4
knockout qualifiers run before the semi-finals to swap released / free-agent
players into their ALREADY-FULL squads.

Rules (confirmed with the league admin):
  * Only the qualifiers pick, in STRAIGHT seed order every round (seed 1 first,
    never snake). ``config.order[0]`` picks first.
  * Each turn is a SWAP: one free agent IN, one squad player OUT. The squad
    stays exactly 2GK/5DEF/5MID/3FWD (a swap is therefore same-position) and
    within the 3-per-nation cap.
  * Unlimited round-robin: a manager keeps swapping until they PASS. A pass
    removes them from the rotation; the draft completes when everyone has
    passed. A timed-out clock auto-passes the manager on the clock.

Rehearsal vs live (the whole reason this module exists now, mid-GW6):
  * ``rehearsal=True``  — a full dry-run on the REAL league. NOTHING outside
    ``leagues/{lid}/ko_draft/*`` is written: squads, members and wc_players are
    never touched. The "effective" squad/pool are derived from the swap log.
  * ``rehearsal=False`` (Go Live) — ``start`` first runs the real elimination
    (``_eliminate_and_release`` for each configured eliminated squad) + sets the
    seed pick order, and every accepted swap is ALSO applied to ``squads/{uid}``.

The single ``if not rehearsal:`` gate in ``start`` and ``_apply_swap_to_squad``
is the only place prod game state is mutated, so a rehearsal is provably safe.
"""

import time
from typing import Dict, List, Optional

from google.cloud.firestore_v1 import SERVER_TIMESTAMP

POSITION_QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}  # GK, DEF, MID, FWD
NATION_QUOTA = 3
POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
DEFAULT_PICK_TIMER = 60


class KnockoutSwapDraftEngine:
    def __init__(self, db, wc_client=None):
        self.db = db
        self.wc = wc_client

    # ------------------------------------------------------------------
    # Firestore refs
    # ------------------------------------------------------------------

    def _league_ref(self, lid: str):
        return self.db.collection("leagues").document(lid)

    def _config_ref(self, lid: str):
        return self._league_ref(lid).collection("ko_draft").document("config")

    def _state_ref(self, lid: str):
        return self._league_ref(lid).collection("ko_draft").document("state")

    def _backup_ref(self, lid: str):
        return self._league_ref(lid).collection("ko_draft").document("backup")

    # ------------------------------------------------------------------
    # Backup / revert — a full safety net taken on EVERY start (dry or live).
    # ------------------------------------------------------------------

    def _snapshot(self, lid: str) -> None:
        """Snapshot everything the draft could ever change — every squad's roster,
        each member's elimination flags + waiver priority, and the standings doc —
        so ``revert`` can restore the league to its exact pre-draft state with one
        click. Taken BEFORE any elimination, on both rehearsal and live starts."""
        squads = {}
        for doc in self._league_ref(lid).collection("squads").get():
            squads[doc.id] = list((doc.to_dict() or {}).get("players", []))
        members = {}
        for doc in self._league_ref(lid).collection("members").get():
            d = doc.to_dict() or {}
            members[doc.id] = {
                "eliminated": bool(d.get("eliminated", False)),
                "eliminatedAtGw": d.get("eliminatedAtGw"),
                "waiverPriority": d.get("waiverPriority"),
            }
        standings_doc = (self._league_ref(lid).collection("standings").document("current").get())
        standings = standings_doc.to_dict() if standings_doc.exists else None
        self._backup_ref(lid).set({
            "squads": squads,
            "members": members,
            "standings": standings,
            "takenAt": SERVER_TIMESTAMP,
        })

    def revert(self, lid: str) -> dict:
        """Undo the WHOLE draft: restore every squad, member flag and the
        standings from the pre-draft backup, then wipe the draft state. Safe to
        run after a rehearsal (restores identical data) or a live draft (rolls
        the real rosters + eliminations back). Idempotent-ish: consumes the
        backup so a second call is a no-op."""
        snap = self._backup_ref(lid).get()
        if not snap.exists:
            # Nothing was ever started (or already reverted) — just clear state.
            self.reset(lid)
            return {"status": "no_backup", "restoredSquads": 0}
        backup = snap.to_dict() or {}
        squads = backup.get("squads") or {}
        members = backup.get("members") or {}
        for uid, players in squads.items():
            self._league_ref(lid).collection("squads").document(uid).set(
                {"players": players}, merge=True)
        for uid, fields in members.items():
            patch = {
                "eliminated": bool(fields.get("eliminated", False)),
                "eliminatedAtGw": fields.get("eliminatedAtGw"),
                "waiverPriority": fields.get("waiverPriority"),
            }
            self._league_ref(lid).collection("members").document(uid).set(patch, merge=True)
        if backup.get("standings") is not None:
            self._league_ref(lid).collection("standings").document("current").set(
                backup["standings"])
        # Clear the draft + consume the backup so it can't be double-applied.
        if self._state_ref(lid).get().exists:
            self._state_ref(lid).delete()
        self._backup_ref(lid).delete()
        return {
            "status": "reverted",
            "restoredSquads": len(squads),
            "restoredMembers": len(members),
            "restoredStandings": backup.get("standings") is not None,
        }

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def set_config(self, lid: str, eliminated_uids: List[str], order: List[str],
                   rehearsal: bool = True, pick_timer: int = DEFAULT_PICK_TIMER) -> dict:
        """Admin writes the draft setup. No squad/member writes here — this only
        records intent; ``start`` acts on it."""
        eliminated_uids = list(eliminated_uids or [])
        order = list(order or [])

        member_ids = {m.id for m in self._league_ref(lid).collection("members").get()}
        if not member_ids:
            raise ValueError("League has no members")
        unknown = [u for u in (eliminated_uids + order) if u not in member_ids]
        if unknown:
            raise ValueError(f"Unknown manager(s): {', '.join(unknown)}")
        if set(eliminated_uids) & set(order):
            raise ValueError("A manager cannot be both eliminated and a picker")
        if len(order) != len(set(order)):
            raise ValueError("Pick order has duplicates")

        cfg = {
            "eliminatedUids": eliminated_uids,
            "order": order,
            "rehearsal": bool(rehearsal),
            "pickTimer": int(pick_timer) if pick_timer else DEFAULT_PICK_TIMER,
            "updatedAt": SERVER_TIMESTAMP,
        }
        self._config_ref(lid).set(cfg)
        return {"leagueId": lid, **cfg, "updatedAt": None}

    def get_config(self, lid: str) -> dict:
        doc = self._config_ref(lid).get()
        return doc.to_dict() if doc.exists else {}

    # ------------------------------------------------------------------
    # Start / reset
    # ------------------------------------------------------------------

    def start(self, lid: str) -> dict:
        """Open the live draft from the saved config. On go-live (rehearsal
        False) this is the ONLY path that eliminates squads for real."""
        cfg = self.get_config(lid)
        order = cfg.get("order") or []
        eliminated = cfg.get("eliminatedUids") or []
        rehearsal = bool(cfg.get("rehearsal", True))
        pick_timer = int(cfg.get("pickTimer") or DEFAULT_PICK_TIMER)
        if len(order) < 2:
            raise ValueError("Need at least 2 pickers in the order")

        # Safety net FIRST: back up squads + member flags + standings before we
        # touch anything, so `revert` can undo the whole draft. Applies to BOTH
        # rehearsal and live starts.
        self._snapshot(lid)

        if not rehearsal:
            league = self._league_ref(lid).get().to_dict() or {}
            gw = int(league.get("knockoutStartGw", 7))
            from fpl_predictor.game.wc_knockout import (
                _eliminate_and_release,
                _set_knockout_pick_order,
            )
            for uid in eliminated:
                _eliminate_and_release(self._league_ref(lid), uid, gw)
            _set_knockout_pick_order(self._league_ref(lid), order)

        state = {
            "status": "active",
            "rehearsal": rehearsal,
            "order": order,
            "eliminatedUids": eliminated,
            "activePickers": list(order),
            "currentDrafter": order[0],
            "pickTimer": pick_timer,
            "pickDeadline": time.time() + pick_timer,
            "paused": False,
            "swaps": [],
            "seq": 0,
            "startedAt": SERVER_TIMESTAMP,
            "completedAt": None,
        }
        self._state_ref(lid).set(state)
        return self.get_state(lid)

    def reset(self, lid: str) -> dict:
        """Wipe the draft state (rehearsal cleanup). Config is kept so the admin
        can re-start with the same setup. Never touches squads/members."""
        ref = self._state_ref(lid)
        if ref.get().exists:
            ref.delete()
        return {"status": "reset"}

    # ------------------------------------------------------------------
    # Picks
    # ------------------------------------------------------------------

    def make_swap(self, lid: str, uid: str, player_in: int, player_out: int,
                  idempotency_key: str = None) -> dict:
        """Record one IN/OUT swap for the manager on the clock, advance the
        rotation, and (live only) apply it to the real squad."""
        try:
            player_in = int(player_in)
            player_out = int(player_out)
        except (TypeError, ValueError):
            raise ValueError("playerIn and playerOut must be integers")

        player_in_doc = self._get_wc_player(player_in)
        if not player_in_doc:
            raise ValueError("PLAYER_NOT_FOUND")
        if player_in_doc.get("eliminated", False):
            raise ValueError("PLAYER_TEAM_ELIMINATED")

        state_ref = self._state_ref(lid)

        def _do(txn):
            snap = state_ref.get(transaction=txn) if txn is not None else state_ref.get()
            if not snap.exists:
                raise ValueError("Draft not found")
            state = snap.to_dict()
            swaps = list(state.get("swaps", []))
            # Idempotency FIRST: a retried request with the same key is a no-op,
            # even after the clock has advanced to the next drafter.
            if idempotency_key:
                for s in swaps:
                    if s.get("key") == idempotency_key:
                        return {"swap": s, "duplicate": True}

            if state.get("status") != "active":
                raise ValueError("Draft is not active")
            if state.get("paused"):
                raise ValueError("Draft is paused")
            if uid != state.get("currentDrafter"):
                raise ValueError("Not your turn to pick")

            # playerIn must be a free agent right now (not held by any picker).
            owned = self._owned_by_pickers(lid, state, swaps)
            if player_in in owned:
                raise ValueError("PLAYER_ALREADY_OWNED")

            eff_squad = self._effective_squad(lid, uid, swaps)
            squad_map = {p["playerId"]: p for p in eff_squad}
            if player_out not in squad_map:
                raise ValueError("PLAYER_OUT_NOT_OWNED")

            new_squad = [p for p in eff_squad if p["playerId"] != player_out]
            new_squad.append(self._player_obj(player_in, player_in_doc))
            self._validate_squad(new_squad)

            seq = int(state.get("seq", 0)) + 1
            swap = {
                "seq": seq,
                "uid": uid,
                "playerIn": player_in,
                "playerOut": player_out,
                "playerInObj": self._player_obj(player_in, player_in_doc),
                # Stored so undo can restore the dropped player to a live squad.
                "playerOutObj": squad_map.get(player_out),
                "key": idempotency_key,
                "ts": time.time(),
            }
            swaps.append(swap)
            next_drafter = self._next_drafter(state.get("activePickers", []), uid)
            update = {
                "swaps": swaps,
                "seq": seq,
                "currentDrafter": next_drafter,
                "pickDeadline": time.time() + int(state.get("pickTimer", DEFAULT_PICK_TIMER)),
            }
            if txn is not None:
                txn.update(state_ref, update)
            else:
                state_ref.update(update)
            return {"swap": swap, "rehearsal": bool(state.get("rehearsal", True))}

        result = self._run_txn(_do)

        # Live only: mirror the swap onto the real squad (idempotent no-ops skip).
        if not result.get("duplicate") and not result.get("rehearsal", True):
            self._apply_swap_to_squad(lid, uid, player_in, player_out, player_in_doc)

        return {"status": "ok", "playerIn": player_in, "playerOut": player_out,
                "seq": result["swap"].get("seq")}

    def pass_turn(self, lid: str, uid: str) -> dict:
        """The manager on the clock is done — drop them from the rotation."""
        state_ref = self._state_ref(lid)

        def _do(txn):
            snap = state_ref.get(transaction=txn) if txn is not None else state_ref.get()
            if not snap.exists:
                raise ValueError("Draft not found")
            state = snap.to_dict()
            if state.get("status") != "active":
                raise ValueError("Draft is not active")
            if state.get("paused"):
                raise ValueError("Draft is paused")
            if uid != state.get("currentDrafter"):
                raise ValueError("Not your turn to pass")

            active = list(state.get("activePickers", []))
            next_drafter = self._next_drafter(active, uid)
            active = [u for u in active if u != uid]
            update = {"activePickers": active}
            if not active:
                update["status"] = "complete"
                update["currentDrafter"] = None
                update["completedAt"] = SERVER_TIMESTAMP
            else:
                update["currentDrafter"] = next_drafter if next_drafter in active else active[0]
                update["pickDeadline"] = time.time() + int(state.get("pickTimer", DEFAULT_PICK_TIMER))
            if txn is not None:
                txn.update(state_ref, update)
            else:
                state_ref.update(update)
            return {"complete": not active}

        return self._run_txn(_do)

    def auto_pass(self, lid: str) -> dict:
        """Cooperative timeout watchdog: pass the on-the-clock manager once the
        deadline has elapsed. Any client may fire it (the clock is authoritative
        server-side)."""
        snap = self._state_ref(lid).get()
        if not snap.exists:
            raise ValueError("Draft not found")
        state = snap.to_dict()
        if state.get("status") != "active":
            raise ValueError("Draft is not active")
        if state.get("paused"):
            raise ValueError("Draft is paused")
        if time.time() < state.get("pickDeadline", float("inf")):
            raise ValueError("Pick timer has not expired")
        drafter = state.get("currentDrafter")
        if not drafter:
            raise ValueError("No one on the clock")
        return self.pass_turn(lid, drafter)

    # ------------------------------------------------------------------
    # Pause / resume (mirrors draft.py)
    # ------------------------------------------------------------------

    def pause(self, lid: str) -> dict:
        ref = self._state_ref(lid)
        snap = ref.get()
        if not snap.exists:
            raise ValueError("Draft not found")
        state = snap.to_dict()
        if state.get("status") != "active":
            raise ValueError("Draft is not active")
        if state.get("paused"):
            return {"paused": True, "alreadyPaused": True}
        remaining = max(0, (state.get("pickDeadline") or 0) - time.time())
        ref.update({"paused": True, "pausedRemaining": remaining})
        return {"paused": True, "secondsRemaining": round(remaining)}

    def resume(self, lid: str) -> dict:
        ref = self._state_ref(lid)
        snap = ref.get()
        if not snap.exists:
            raise ValueError("Draft not found")
        state = snap.to_dict()
        if not state.get("paused"):
            return {"paused": False, "alreadyRunning": True}
        remaining = state.get("pausedRemaining")
        if remaining is None or remaining <= 0:
            remaining = int(state.get("pickTimer", DEFAULT_PICK_TIMER))
        ref.update({"paused": False, "pickDeadline": time.time() + remaining, "pausedRemaining": None})
        return {"paused": False, "secondsRemaining": round(remaining)}

    # ------------------------------------------------------------------
    # Undo (Ctrl+Z) — step back one swap, repeatable to the start
    # ------------------------------------------------------------------

    def undo_last_swap(self, lid: str) -> dict:
        """Undo the most recent swap: pop it from the log, hand the clock back to
        the manager who made it, reopen the rotation if the draft had completed,
        and (live only) reverse the real-squad mutation. Repeatable back to the
        start of the draft. Admin-only at the API layer."""
        state_ref = self._state_ref(lid)

        def _do(txn):
            snap = state_ref.get(transaction=txn) if txn is not None else state_ref.get()
            if not snap.exists:
                raise ValueError("Draft not found")
            state = snap.to_dict()
            swaps = list(state.get("swaps", []))
            if not swaps:
                raise ValueError("Nothing to undo")
            last = swaps.pop()
            uid = last.get("uid")
            order = list(state.get("order", []))
            active = list(state.get("activePickers", []))
            if uid not in active:
                # Reopen the rotation (e.g. the draft had completed) and slot the
                # undone manager back in, preserving seed order.
                active = [u for u in order if u in active or u == uid] or [uid]
            update = {
                "swaps": swaps,
                "seq": max(0, int(state.get("seq", 0)) - 1),
                "status": "active",
                "activePickers": active,
                "currentDrafter": uid,
                "paused": False,
                "completedAt": None,
                "pickDeadline": time.time() + int(state.get("pickTimer", DEFAULT_PICK_TIMER)),
            }
            if txn is not None:
                txn.update(state_ref, update)
            else:
                state_ref.update(update)
            return {"last": last, "rehearsal": bool(state.get("rehearsal", True))}

        r = self._run_txn(_do)
        last = r["last"]
        # Live only: reverse the mirror — drop playerIn, restore playerOut.
        if not r.get("rehearsal", True):
            self._reverse_swap_on_squad(
                lid, last.get("uid"), int(last.get("playerIn")),
                int(last.get("playerOut")), last.get("playerOutObj"))
        return {"status": "ok", "undone": {
            "uid": last.get("uid"), "playerIn": last.get("playerIn"),
            "playerOut": last.get("playerOut"), "seq": last.get("seq")}}

    # ------------------------------------------------------------------
    # State read (frontend)
    # ------------------------------------------------------------------

    def get_state(self, lid: str) -> dict:
        snap = self._state_ref(lid).get()
        if not snap.exists:
            cfg = self.get_config(lid)
            return {"status": "pending", "config": cfg}
        state = snap.to_dict()
        swaps = list(state.get("swaps", []))
        order = state.get("order", [])
        squads = {u: self._effective_squad(lid, u, swaps) for u in order}
        owned = sorted(self._owned_by_pickers(lid, state, swaps))
        return {
            "status": state.get("status", "pending"),
            "rehearsal": bool(state.get("rehearsal", True)),
            "order": order,
            "eliminatedUids": state.get("eliminatedUids", []),
            "activePickers": state.get("activePickers", []),
            "currentDrafter": state.get("currentDrafter"),
            "pickTimer": state.get("pickTimer", DEFAULT_PICK_TIMER),
            "pickDeadline": state.get("pickDeadline"),
            "paused": bool(state.get("paused", False)),
            "swaps": swaps,
            "squads": squads,
            "ownedPlayerIds": owned,
        }

    # ------------------------------------------------------------------
    # Rotation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _next_drafter(active: List[str], current: str) -> Optional[str]:
        """Straight seed order: the next picker after ``current`` in ``active``,
        wrapping to the front. Returns None only for an empty rotation."""
        if not active:
            return None
        if current not in active:
            return active[0]
        idx = active.index(current)
        return active[(idx + 1) % len(active)]

    # ------------------------------------------------------------------
    # Squad / pool derivation
    # ------------------------------------------------------------------

    def _base_squad(self, lid: str, uid: str) -> List[dict]:
        doc = self._league_ref(lid).collection("squads").document(uid).get()
        if not doc.exists:
            return []
        return list((doc.to_dict() or {}).get("players", []))

    def _effective_squad(self, lid: str, uid: str, swaps: List[dict]) -> List[dict]:
        """Base squad with THIS draft's swaps for ``uid`` applied in order.

        In rehearsal the real squad is never written, so the swap log is the
        only source of truth for who the manager currently holds; in live mode
        the base squad already reflects earlier swaps, but replaying the log is
        idempotent (remove-out / add-in on ids) so the result is identical."""
        squad = list(self._base_squad(lid, uid))
        for s in swaps:
            if s.get("uid") != uid:
                continue
            p_out = s.get("playerOut")
            squad = [p for p in squad if p.get("playerId") != p_out]
            obj = s.get("playerInObj") or self._player_obj(
                s.get("playerIn"), self._get_wc_player(s.get("playerIn")) or {})
            if not any(p.get("playerId") == obj["playerId"] for p in squad):
                squad.append(obj)
        return squad

    def _owned_by_pickers(self, lid: str, state: dict, swaps: List[dict]) -> set:
        """Every player currently held by an active picker (base ± swaps).

        The free-agent pool is everything NOT in this set (and not
        nation-eliminated), which naturally includes the released squads of the
        eliminated managers, ordinary unowned free agents, and any player
        dropped earlier in this draft."""
        owned = set()
        for u in state.get("order", []):
            for p in self._effective_squad(lid, u, swaps):
                owned.add(p.get("playerId"))
        return owned

    def _player_obj(self, player_id: int, doc: dict) -> dict:
        pos = doc.get("position", 3)
        return {
            "playerId": int(player_id),
            "position": pos,
            "name": doc.get("name", ""),
            "positionName": POS_NAMES.get(pos, "?"),
            "teamId": doc.get("teamId", 0),
            "teamName": doc.get("teamName", ""),
            "teamIso": doc.get("teamIso", ""),
            "eliminated": bool(doc.get("eliminated", False)),
        }

    def _validate_squad(self, players: List[dict]):
        """Squad must stay exactly 2/5/5/3 (so a swap is same-position). NO
        per-nation cap in the knockout draft — squads carry over from the group
        stage where nations get concentrated as teams are eliminated, so many
        managers already hold >3 from one nation; enforcing the cap here would
        block legitimate swaps."""
        counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for p in players:
            counts[p["position"]] = counts.get(p["position"], 0) + 1
        for pos, required in POSITION_QUOTA.items():
            if counts.get(pos, 0) != required:
                raise ValueError(
                    f"POSITION_QUOTA_VIOLATED: need {required} {POS_NAMES[pos]}, "
                    f"have {counts.get(pos, 0)} — a swap must be same-position"
                )

    def _apply_swap_to_squad(self, lid: str, uid: str, player_in: int,
                             player_out: int, player_in_doc: dict):
        """Live-mode only: mirror an accepted swap onto ``squads/{uid}``.

        Mirrors ``wc_squads.sign_free_agent`` / ``wc_wishlist._execute_swap`` but
        falls back to a plain read/write when the fake DB used by unit tests has
        no ``transaction`` (same guard as ``draft.make_pick``)."""
        squad_ref = self._league_ref(lid).collection("squads").document(uid)
        new_obj = self._player_obj(player_in, player_in_doc)

        def _write(current: dict):
            owned = {p["playerId"] for p in current.get("players", [])}
            if player_in in owned:
                raise ValueError("PLAYER_ALREADY_OWNED")
            players = [p for p in current.get("players", []) if p["playerId"] != player_out]
            players.append(new_obj)
            return {"players": players}

        if hasattr(self.db, "transaction"):
            from google.cloud.firestore_v1 import transactional

            @transactional
            def _claim(txn):
                snapshot = squad_ref.get(transaction=txn)
                update = _write(snapshot.to_dict() or {})
                txn.update(squad_ref, update)

            _claim(self.db.transaction())
        else:
            snapshot = squad_ref.get()
            squad_ref.update(_write(snapshot.to_dict() or {}))

    def _reverse_swap_on_squad(self, lid: str, uid: str, player_in: int,
                               player_out: int, player_out_obj: dict = None):
        """Live-mode inverse of ``_apply_swap_to_squad`` (undo): drop ``player_in``
        and restore ``player_out``. Uses the swap's stored ``playerOutObj`` when
        present, else rebuilds it from ``wc_players``."""
        squad_ref = self._league_ref(lid).collection("squads").document(uid)
        restore = player_out_obj or self._player_obj(
            player_out, self._get_wc_player(player_out) or {})

        def _write(current: dict):
            players = [p for p in current.get("players", []) if p["playerId"] != player_in]
            if not any(p.get("playerId") == player_out for p in players):
                players.append(restore)
            return {"players": players}

        if hasattr(self.db, "transaction"):
            from google.cloud.firestore_v1 import transactional

            @transactional
            def _claim(txn):
                snapshot = squad_ref.get(transaction=txn)
                txn.update(squad_ref, _write(snapshot.to_dict() or {}))

            _claim(self.db.transaction())
        else:
            snapshot = squad_ref.get()
            squad_ref.update(_write(snapshot.to_dict() or {}))

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _get_wc_player(self, player_id: int) -> Optional[dict]:
        doc = self.db.collection("wc_players").document(str(player_id)).get()
        return doc.to_dict() if doc.exists else None

    def _run_txn(self, fn):
        """Run ``fn`` inside a Firestore transaction when the DB supports one,
        else call it directly (unit-test fake DB)."""
        if hasattr(self.db, "transaction"):
            from google.cloud.firestore_v1 import transactional

            @transactional
            def _wrapped(txn):
                return fn(txn)

            return _wrapped(self.db.transaction())
        return fn(None)
