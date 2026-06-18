"""
WC2026 squad and lineup management.

Squad: 15 players (2GK, 5DEF, 5MID, 3FWD).
Lineup: 11 starters + 4 bench (bench[0] = reserve GK).
Captain + Vice-Captain required; captain doubles points.
"""

from datetime import datetime, timezone
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from typing import Dict, List, Optional, Tuple

VALID_FORMATIONS = [
    (1, 3, 5, 2), (1, 3, 4, 3), (1, 4, 5, 1),
    (1, 4, 4, 2), (1, 4, 3, 3), (1, 5, 4, 1),
    (1, 5, 3, 2),
]

SQUAD_QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}
POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


class WCSquadManager:
    def __init__(self, db, wc_client=None):
        self.db = db
        self.wc = wc_client

    # ------------------------------------------------------------------
    # Squad read
    # ------------------------------------------------------------------

    def get_squad(self, lid: str, uid: str) -> dict:
        doc = (self.db.collection("leagues").document(lid)
               .collection("squads").document(uid).get())
        if not doc.exists:
            return {"players": []}
        return doc.to_dict()

    def get_all_owned_ids(self, lid: str) -> set:
        squads = self.db.collection("leagues").document(lid).collection("squads").get()
        owned = set()
        for doc in squads:
            for p in doc.to_dict().get("players", []):
                owned.add(p["playerId"])
        return owned

    # ------------------------------------------------------------------
    # Lineup read + write
    # ------------------------------------------------------------------

    def get_lineup(self, lid: str, uid: str, gw: int) -> dict:
        from fpl_predictor.game.wc_gameweeks import is_locked

        doc_id = f"{uid}_{gw}"
        ref = (self.db.collection("leagues").document(lid)
               .collection("lineups").document(doc_id))
        doc = ref.get()
        if doc.exists:
            lineup = doc.to_dict()
        else:
            # Carry forward from previous GW, else build a default from squad.
            lineup = self._get_previous_lineup(lid, uid, gw) \
                or self._default_lineup(lid, uid)

        # A historical GW is immutable — return exactly what was played; never
        # rewrite it to reflect transfers made AFTER that GW kicked off. A GW is
        # historical if its lock time has passed OR it has already been finalized
        # (gw < the league's currentGw). The currentGw check is the authoritative
        # signal for the mock simulator, whose fixtures don't carry real-world
        # kickoff clocks for is_locked() to read.
        try:
            locked = is_locked(gw)
        except Exception:
            locked = False
        try:
            league_doc = self.db.collection("leagues").document(lid).get()
            current_gw = int((league_doc.to_dict() or {}).get("currentGw", 1)) if league_doc.exists else 1
        except Exception:
            current_gw = 1
        if locked or gw < current_gw:
            return lineup

        # Transfers (free-agent / trade) only mutate the SQUAD doc, leaving the
        # lineup pointing at the dropped player and missing the new one — which
        # is why a transferred-in player never appears in the pick-team view.
        # Reconcile the lineup with the current squad and persist the fix so
        # scoring uses the right players too.
        reconciled, changed = self._reconcile_lineup_with_squad(lid, uid, lineup)
        if changed:
            try:
                ref.set({
                    "starting": reconciled.get("starting", []),
                    "bench": reconciled.get("bench", []),
                    "formation": reconciled.get("formation", []),
                }, merge=True)
            except Exception:
                pass  # display correction still returned even if write fails
        return reconciled

    def set_lineup(
        self,
        lid: str,
        uid: str,
        gw: int,
        starting: List[int],
        bench: List[int],
        captain: Optional[int] = None,
        vice_captain: Optional[int] = None,
    ) -> dict:
        # Squads + XI freeze at T0 - 1h (the FREE_AGENTS -> NONE boundary), read
        # from the durable fixture kickoffs so a re-sim never moves the lock.
        from fpl_predictor.game.wc_windows import is_lineup_locked

        if is_lineup_locked(self.db, gw, lid=lid):
            raise ValueError("LINEUP_LOCKED")

        league_doc = self.db.collection("leagues").document(lid).get()
        if not league_doc.exists:
            raise ValueError("League not found")
        if league_doc.to_dict().get("status") not in ("group_phase", "knockout"):
            raise ValueError("League is not active")

        squad_doc = (self.db.collection("leagues").document(lid)
                     .collection("squads").document(uid).get())
        if not squad_doc.exists:
            raise ValueError("No squad found")

        config_doc = self.db.collection("wc_config").document("tournament").get()
        squad_size = 15
        if config_doc.exists:
            squad_size = config_doc.to_dict().get("rules", {}).get("squadLimit", {}).get("totalPlayers", 15)

        players = squad_doc.to_dict().get("players", [])
        if len(players) < squad_size:
            raise ValueError("SQUAD_INCOMPLETE")

        player_map = {p["playerId"]: p for p in players}
        squad_ids = set(player_map.keys())
        all_ids = list(starting) + list(bench)

        if set(all_ids) != squad_ids:
            raise ValueError(f"Lineup must contain exactly your {squad_size} squad players")
        if len(starting) != 11:
            raise ValueError("Must have exactly 11 starters")
        if len(bench) != squad_size - 11:
            raise ValueError(f"Must have exactly {squad_size - 11} bench players")
        if len(set(all_ids)) != squad_size:
            raise ValueError("Duplicate player IDs in lineup")

        # Per-GW pick blocklist (admin): listed players may NOT be in the
        # starting XI for this gw (e.g. teams that kicked off while the window
        # stays open by agreement). They may still sit on the bench, so the
        # 15-man lineup stays valid. ``leagues/{lid}.pickBlockByGw[str(gw)]``.
        block = set((league_doc.to_dict().get("pickBlockByGw") or {}).get(str(gw), []))
        if block:
            blocked_start = [pid for pid in starting if pid in block]
            if blocked_start:
                names = ", ".join(player_map.get(p, {}).get("name", str(p)) for p in blocked_start)
                raise ValueError(f"PLAYER_BLOCKED_FOR_GW: cannot start {names} in GW{gw} (bench them)")

        formation = self._get_formation(starting, player_map)
        if formation not in VALID_FORMATIONS:
            raise ValueError(f"Invalid formation {formation}; need 1GK + ≥3DEF + ≥2MID + ≥1FWD")

        bench_0 = bench[0]
        bench_0_pos = player_map[bench_0]["position"]
        if bench_0_pos != 1:
            raise ValueError("bench[0] must be your reserve goalkeeper")

        starting_gks = [p for p in starting if player_map[p]["position"] == 1]
        if len(starting_gks) != 1:
            raise ValueError("Starting XI must have exactly 1 GK")

        # Captain/vice-captain validations removed (not used in game)

        # Warn about eliminated players (non-blocking)
        warnings = []
        for pid in starting:
            if player_map.get(pid, {}).get("eliminated", False):
                warnings.append({
                    "code": "STARTING_HAS_ELIMINATED",
                    "playerId": pid,
                    "playerName": player_map[pid].get("name", ""),
                })

        doc_id = f"{uid}_{gw}"
        lineup_data = {
            "starting": starting,
            "bench": bench,
            "formation": list(formation),
            "captain": captain,
            "viceCaptain": vice_captain,
            "effectiveCaptain": None,
            "locked": False,
            "autoSubsMade": [],
            "updatedAt": SERVER_TIMESTAMP,
        }
        (self.db.collection("leagues").document(lid)
         .collection("lineups").document(doc_id).set(lineup_data))

        return {
            "starting": starting,
            "bench": bench,
            "formation": list(formation),
            "captain": captain,
            "viceCaptain": vice_captain,
            "locked": False,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Free agent pickup (FCFS, during transfer window free-agent phase)
    # ------------------------------------------------------------------

    def sign_free_agent(
        self,
        lid: str,
        uid: str,
        player_in: int,
        player_out: int,
        window_number: int,
        idempotency_key: str = None,
    ) -> dict:
        self._validate_window_open(lid)

        squad = self._get_squad_players(lid, uid)
        squad_map = {p["playerId"]: p for p in squad}

        if player_out not in squad_map:
            raise ValueError("PLAYER_OUT_NOT_OWNED")

        player_in_doc = self._get_wc_player(player_in)
        if not player_in_doc:
            raise ValueError("PLAYER_NOT_FOUND")

        if player_in_doc.get("eliminated", False):
            raise ValueError("PLAYER_TEAM_ELIMINATED")

        owned = self.get_all_owned_ids(lid)
        if player_in in owned:
            raise ValueError("PLAYER_ALREADY_OWNED")

        # Position quota check after swap
        new_squad = [p for p in squad if p["playerId"] != player_out] + [{
            "playerId": player_in,
            "position": player_in_doc["position"],
            "name": player_in_doc.get("name", ""),
            "positionName": POS_NAMES.get(player_in_doc["position"], "?"),
            "teamId": player_in_doc.get("teamId", 0),
            "teamName": player_in_doc.get("teamName", ""),
            "teamIso": player_in_doc.get("teamIso", ""),
            "eliminated": False,
        }]
        
        # Load dynamic SQUAD_QUOTA from Firestore rules
        quota = SQUAD_QUOTA
        config_doc = self.db.collection("wc_config").document("tournament").get()
        if config_doc.exists:
            custom_quota = config_doc.to_dict().get("rules", {}).get("squadLimit", {})
            if custom_quota:
                quota = {
                    1: custom_quota.get("gk", 2),
                    2: custom_quota.get("def", 5),
                    3: custom_quota.get("mid", 5),
                    4: custom_quota.get("fwd", 3)
                }
        _validate_squad_quota(new_squad, quota)


        # Atomic claim via Firestore transaction
        from google.cloud.firestore_v1 import transactional

        squad_ref = (self.db.collection("leagues").document(lid)
                     .collection("squads").document(uid))

        @transactional
        def _claim(txn, s_ref, p_in, p_in_doc, p_out):
            snapshot = s_ref.get(transaction=txn)
            current = snapshot.to_dict() or {}
            current_owned = {p["playerId"] for p in current.get("players", [])}
            if p_in in current_owned:
                raise ValueError("PLAYER_ALREADY_OWNED")
            new_players = [p for p in current.get("players", []) if p["playerId"] != p_out]
            new_players.append({
                "playerId": p_in,
                "position": p_in_doc["position"],
                "name": p_in_doc.get("name", ""),
                "positionName": POS_NAMES.get(p_in_doc["position"], "?"),
                "teamId": p_in_doc.get("teamId", 0),
                "teamName": p_in_doc.get("teamName", ""),
                "teamIso": p_in_doc.get("teamIso", ""),
                "eliminated": False,
            })
            txn.update(s_ref, {"players": new_players})

        _claim(self.db.transaction(), squad_ref, player_in, player_in_doc, player_out)
        self._log_transaction(lid, uid, "free_agent", player_in, player_out)
        self._track_transfer(lid, uid, window_number)

        return {"status": "ok", "playerIn": player_in, "playerOut": player_out}

    # ------------------------------------------------------------------
    # Drop without pickup
    # ------------------------------------------------------------------

    def drop_player(self, lid: str, uid: str, player_out: int) -> dict:
        self._validate_window_open(lid)

        squad = self._get_squad_players(lid, uid)
        squad_map = {p["playerId"]: p for p in squad}

        if player_out not in squad_map:
            raise ValueError("PLAYER_OUT_NOT_OWNED")

        # Ensure squad at 14 still has minimum positions
        remaining = [p for p in squad if p["playerId"] != player_out]
        pos_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for p in remaining:
            pos_counts[p["position"]] = pos_counts.get(p["position"], 0) + 1

        min_pos = {1: 1, 2: 3, 3: 3, 4: 1}
        for pos, minimum in min_pos.items():
            if pos_counts.get(pos, 0) < minimum:
                raise ValueError("POSITION_QUOTA_INCOMPLETABLE")

        squad_ref = (self.db.collection("leagues").document(lid)
                     .collection("squads").document(uid))
        squad_ref.update({"players": remaining})

        self._log_transaction(lid, uid, "drop", None, player_out)

        return {
            "status": "ok",
            "playerOut": player_out,
            "squadSize": len(remaining),
            "graceUntil": _grace_deadline(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_squad_players(self, lid: str, uid: str) -> List[Dict]:
        doc = (self.db.collection("leagues").document(lid)
               .collection("squads").document(uid).get())
        if not doc.exists:
            raise ValueError("No squad found")
        return doc.to_dict().get("players", [])

    def _get_wc_player(self, player_id: int) -> Optional[Dict]:
        doc = self.db.collection("wc_players").document(str(player_id)).get()
        return doc.to_dict() if doc.exists else None

    def _validate_window_open(self, lid: str):
        """Free-agent pickups/drops are only allowed in the FREE_AGENTS window.

        Routes through the override-aware ``current_window_from_db`` state
        machine so an admin ``windowOverride`` is honoured (the legacy
        ``is_transfer_window_open`` helper passed ``league_doc=None`` and so
        silently ignored overrides — the root cause of "window closed" errors
        when an admin had explicitly opened the free-agents window).
        """
        from fpl_predictor.game.wc_windows import (
            TransferWindow,
            current_window_from_db,
        )
        league_doc = self.db.collection("leagues").document(lid).get()
        if not league_doc.exists:
            raise ValueError("League not found")
        window, _ = current_window_from_db(lid, self.db)
        if window != TransferWindow.FREE_AGENTS:
            raise ValueError("WINDOW_CLOSED")

    def _log_transaction(self, lid: str, uid: str, txn_type: str,
                         player_in: Optional[int], player_out: Optional[int]):
        # Stamp the current GW so free-agent / drop moves group correctly in the
        # league History tab (which buckets everything per gameweek).
        league = self.db.collection("leagues").document(lid).get()
        gw = (league.to_dict() or {}).get("currentGw") if league.exists else None
        ref = (self.db.collection("leagues").document(lid)
               .collection("transactions").document())
        ref.set({
            "type": txn_type,
            "uid": uid,
            "playerIn": player_in,
            "playerOut": player_out,
            "gw": gw,
            "timestamp": SERVER_TIMESTAMP,
        })

    def _track_transfer(self, lid: str, uid: str, window_number: int):
        from google.cloud.firestore_v1 import Increment
        windows = (self.db.collection("leagues").document(lid)
                   .collection("transfer_windows")
                   .where("windowNumber", "==", window_number)
                   .limit(1).get())
        if windows:
            windows[0].reference.set(
                {f"transfersUsed.{uid}": Increment(1)},
                merge=True,
            )

    def _get_formation(self, starting_ids: List[int], player_map: Dict) -> tuple:
        counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for pid in starting_ids:
            p = player_map.get(pid, {})
            pos = p.get("position", 3)
            counts[pos] = counts.get(pos, 0) + 1
        return (counts[1], counts[2], counts[3], counts[4])

    def _reconcile_lineup_with_squad(self, lid: str, uid: str, lineup: dict):
        """Return ``(lineup, changed)`` with the lineup aligned to the squad.

        Replaces entries that are no longer in the squad (transferred OUT) with
        squad players missing from the lineup (transferred IN), matching by
        position where possible so the formation stays legal. If the result is
        not a valid XI (e.g. a position-changing trade), falls back to a fresh
        default lineup so the pitch always renders something saveable.
        """
        squad = self._get_squad_players(lid, uid)
        if not squad:
            return lineup, False

        player_map = {p["playerId"]: p for p in squad}
        pos_by_id = {p["playerId"]: p.get("position") for p in squad}
        squad_ids = set(pos_by_id)

        starting = list(lineup.get("starting", []) or [])
        bench = list(lineup.get("bench", []) or [])
        in_lineup = starting + bench

        stale = [pid for pid in in_lineup if pid not in squad_ids]
        orphans = [pid for pid in squad_ids if pid not in in_lineup]
        if not stale and not orphans:
            return lineup, False

        # Incoming players bucketed by position.
        orphan_by_pos: Dict[int, List[int]] = {}
        for pid in orphans:
            orphan_by_pos.setdefault(pos_by_id.get(pid), []).append(pid)

        # Map each departed player to a same-position replacement first. The
        # departed player is no longer in the squad, so read its position from
        # the player catalogue.
        mapping: Dict[int, int] = {}
        leftover = list(orphans)
        for pid in stale:
            dep = self._get_wc_player(pid)
            dep_pos = dep.get("position") if dep else None
            bucket = orphan_by_pos.get(dep_pos)
            if bucket:
                repl = bucket.pop(0)
                mapping[pid] = repl
                leftover.remove(repl)
        for pid in stale:  # any departed without a position match
            if pid not in mapping and leftover:
                mapping[pid] = leftover.pop(0)

        def _apply(ids):
            out = []
            for pid in ids:
                if pid in squad_ids:
                    out.append(pid)
                elif pid in mapping:
                    out.append(mapping[pid])
                # departed with no replacement → slot dropped
            return out

        new_starting = _apply(starting)
        new_bench = _apply(bench)

        # Any incoming player we couldn't place (e.g. squad grew) → to bench.
        placed = set(new_starting) | set(new_bench)
        for pid in orphans:
            if pid not in placed:
                new_bench.append(pid)
                placed.add(pid)

        formation = self._get_formation(new_starting, player_map)
        if len(new_starting) != 11 or formation not in VALID_FORMATIONS:
            # Couldn't preserve a legal XI (e.g. position-changing trade) —
            # rebuild a guaranteed-valid default from the current squad.
            return self._default_lineup(lid, uid), True

        reconciled = dict(lineup)
        reconciled["starting"] = new_starting
        reconciled["bench"] = new_bench
        reconciled["formation"] = list(formation)
        return reconciled, True

    def _default_lineup(self, lid: str, uid: str) -> dict:
        squad_doc = (self.db.collection("leagues").document(lid)
                     .collection("squads").document(uid).get())
        if not squad_doc.exists:
            return {"starting": [], "bench": [], "formation": [], "captain": None, "viceCaptain": None}

        players = squad_doc.to_dict().get("players", [])
        by_pos: Dict[int, List[int]] = {1: [], 2: [], 3: [], 4: []}
        for p in players:
            by_pos[p["position"]].append(p["playerId"])

        starting = []
        bench = []
        # Default 1-4-4-2
        for pos, count in [(1, 1), (2, 4), (3, 4), (4, 2)]:
            pool = by_pos[pos]
            starting.extend(pool[:count])
            bench.extend(pool[count:])

        captain = None
        vice_captain = None

        return {
            "starting": starting,
            "bench": bench,
            "formation": [1, 4, 4, 2],
            "captain": captain,
            "viceCaptain": vice_captain,
            "effectiveCaptain": None,
            "locked": False,
            "autoSubsMade": [],
        }

    def _get_previous_lineup(self, lid: str, uid: str, gw: int) -> Optional[Dict]:
        for prev_gw in range(gw - 1, 0, -1):
            doc_id = f"{uid}_{prev_gw}"
            doc = (self.db.collection("leagues").document(lid)
                   .collection("lineups").document(doc_id).get())
            if doc.exists:
                d = doc.to_dict()
                return {
                    "starting": d["starting"],
                    "bench": d["bench"],
                    "formation": d["formation"],
                    "captain": None,
                    "viceCaptain": None,
                    "effectiveCaptain": None,
                    "locked": False,
                    "autoSubsMade": [],
                }
        return None


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _validate_squad_quota(players: List[Dict], quota: Optional[Dict] = None):
    quota = quota or SQUAD_QUOTA
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for p in players:
        counts[p["position"]] = counts.get(p["position"], 0) + 1
    for pos, required in quota.items():
        if counts.get(pos, 0) != required:
            raise ValueError(
                f"POSITION_QUOTA_VIOLATED: need {required} {POS_NAMES[pos]}, "
                f"have {counts.get(pos, 0)}"
            )



def _grace_deadline() -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()


