"""
WC2026 wishlist auction (PR 4).

At trade-window close, each manager has submitted an ORDERED list of
same-position swap bids (``leagues/{lid}/wishlist_bids/{uid}_{gw}``). The
auction resolves them last-pick-first (reversed ``waiverPriority``) so the
weakest managers get first dibs on contested free agents, mirroring the normal
waiver order in reverse.

Design references: ``WC2026_WINDOWS_DESIGN.md`` §3.1 (schema), §4 (algorithm +
the REQUIRED deterministic tie-break), §12 (live data model — squads store full
player OBJECTS keyed on ``playerId`` with INT ``position`` codes).

The resolver is a self-contained callable so PR 5 (deferred next-gw trades) can
run deferred-trade processing FIRST, then call this.
"""

from typing import Dict, List, Optional

from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# 2 GK / 5 DEF / 5 MID / 3 FWD — same quota as wc_squads.SQUAD_QUOTA.
SQUAD_QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}
POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


class WCWishlistManager:
    def __init__(self, db, wc_client=None):
        self.db = db
        self.wc = wc_client

    # ------------------------------------------------------------------
    # Bid submission + read (validated on write)
    # ------------------------------------------------------------------

    def submit_bids(self, lid: str, uid: str, gw: int, bids: List[dict]) -> dict:
        """Validate + store one wishlist-bid doc per manager per GW.

        ``bids`` is ORDERED (index 0 tried first). Each bid is a same-position
        swap: ``playerIn`` must be a free agent (not on any squad in the
        league), ``playerOut`` must currently be on the caller's squad, and
        their positions must match. Re-submission overwrites.
        """
        if not isinstance(bids, list) or not bids:
            raise ValueError("NO_BIDS: provide at least one bid")

        squad = self._get_squad(lid, uid)
        squad_map = {p["playerId"]: p for p in squad}
        owned = self._get_all_owned(lid)

        normalised: List[dict] = []
        for i, bid in enumerate(bids):
            try:
                player_in = int(bid["playerIn"])
                player_out = int(bid["playerOut"])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"BID_MALFORMED: bid #{i} needs integer playerIn/playerOut")

            if player_out not in squad_map:
                raise ValueError(
                    f"PLAYER_OUT_NOT_OWNED: bid #{i} playerOut {player_out} not on your squad"
                )

            player_in_doc = self._get_wc_player(player_in)
            if not player_in_doc:
                raise ValueError(f"PLAYER_NOT_FOUND: bid #{i} playerIn {player_in}")

            if player_in in owned:
                raise ValueError(
                    f"PLAYER_ALREADY_OWNED: bid #{i} playerIn {player_in} is not a free agent"
                )

            out_pos = squad_map[player_out]["position"]
            in_pos = player_in_doc.get("position", 3)
            if out_pos != in_pos:
                raise ValueError(
                    f"POSITION_MISMATCH: bid #{i} dropping {POS_NAMES.get(out_pos, '?')}, "
                    f"claiming {POS_NAMES.get(in_pos, '?')} — must be same position"
                )

            normalised.append({
                "playerIn": player_in,
                "playerOut": player_out,
                "position": POS_NAMES.get(in_pos, "?"),
            })

        doc_ref = (self.db.collection("leagues").document(lid)
                   .collection("wishlist_bids").document(f"{uid}_{gw}"))
        existing = doc_ref.get()
        payload = {
            "uid": uid,
            "gw": gw,
            "bids": normalised,
            "updatedAt": SERVER_TIMESTAMP,
        }
        if existing.exists:
            doc_ref.update(payload)
        else:
            payload["createdAt"] = SERVER_TIMESTAMP
            doc_ref.set(payload)

        return {"uid": uid, "gw": gw, "bids": normalised}

    def get_my_bids(self, lid: str, uid: str, gw: int) -> dict:
        doc = (self.db.collection("leagues").document(lid)
               .collection("wishlist_bids").document(f"{uid}_{gw}").get())
        if not doc.exists:
            return {"uid": uid, "gw": gw, "bids": []}
        return doc.to_dict()

    # ------------------------------------------------------------------
    # The auction resolver (§4)
    # ------------------------------------------------------------------

    def run_auction(self, lid: str, gw: int) -> dict:
        """Resolve the wishlist auction for ``gw`` (multi-round round-robin).

        Order managers last-pick-first by ``waiverPriority`` DESC with the
        deterministic tie-break ``(waiverPriority DESC, draftPosition DESC,
        uid ASC)`` because live ``waiverPriority`` has duplicates. Each round,
        every manager gets at most ONE successful claim (the first still-valid
        bid in their ordered list). Keep cycling rounds until a full round
        yields no claim. ``claimed_in`` and ``replaced_out`` are tracked IN
        MEMORY across rounds so two managers can't grab the same free agent.

        After the loop, batch-delete every ``wishlist_bids/*_{gw}`` doc and
        return a summary of executed + skipped claims.
        """
        league_ref = self.db.collection("leagues").document(lid)

        order = self._ordered_managers(lid)

        # uid -> ordered list of bid dicts
        bids_by_uid: Dict[str, List[dict]] = {}
        bid_doc_ids: List[str] = []
        for doc in league_ref.collection("wishlist_bids").get():
            data = doc.to_dict() or {}
            if data.get("gw") != gw:
                continue
            bid_doc_ids.append(doc.id)
            bids_by_uid[data["uid"]] = list(data.get("bids", []))

        claimed_in: set = set()             # playerIns taken this auction
        replaced_out: set = set()           # (uid, playerOut) already used
        consumed_idx: Dict[str, set] = {}   # uid -> bid indices already consumed
        executed: List[dict] = []
        skipped: List[dict] = []

        progressing = True
        while progressing:
            progressing = False
            for uid in order:
                wl = bids_by_uid.get(uid)
                if not wl:
                    continue
                used = consumed_idx.setdefault(uid, set())

                for idx, bid in enumerate(wl):
                    if idx in used:
                        continue
                    player_in = bid["playerIn"]
                    player_out = bid["playerOut"]

                    reason = self._validate_bid(
                        lid, uid, player_in, player_out,
                        claimed_in, replaced_out,
                    )
                    if reason is not None:
                        # Auto-skip; only record a permanent skip once the bid
                        # can never become valid again (the playerIn is gone for
                        # good or this uid already replaced that playerOut). A
                        # "still free but contested" miss is left for a later
                        # round to retry.
                        if reason != "RETRY":
                            used.add(idx)
                            skipped.append({
                                "uid": uid, "playerIn": player_in,
                                "playerOut": player_out, "reason": reason,
                            })
                        continue

                    # Valid → execute the swap atomically.
                    player_in_doc = self._get_wc_player(player_in)
                    self._execute_swap(lid, uid, player_in, player_out, player_in_doc)

                    claimed_in.add(player_in)
                    replaced_out.add((uid, player_out))
                    used.add(idx)

                    league_ref.collection("transactions").document().set({
                        "type": "wishlist_claim",
                        "uid": uid,
                        "playerIn": player_in,
                        "playerOut": player_out,
                        "gw": gw,
                        "timestamp": SERVER_TIMESTAMP,
                    })

                    executed.append({
                        "uid": uid, "playerIn": player_in, "playerOut": player_out,
                    })
                    progressing = True
                    break  # one successful claim per manager per round

        # Persist a DURABLE per-GW record of the auction: every manager's ORDERED
        # bids with each bid's outcome (claimed vs cancelled). The wishlist_bids
        # docs are deleted below, so without this the wishlist order — and which
        # bids failed — would be lost the moment the auction runs. Surfaced in
        # the Transfers > History tab.
        exec_set = {(e["uid"], e["playerIn"]) for e in executed}
        skip_map = {(s["uid"], s["playerIn"]): s.get("reason") for s in skipped}
        results: List[dict] = []
        failed: List[dict] = []
        for uid in order:
            wl = bids_by_uid.get(uid)
            if not wl:
                continue
            rows = []
            for bid in wl:
                claimed = (uid, bid["playerIn"]) in exec_set
                row = {
                    "playerIn": bid["playerIn"],
                    "playerOut": bid["playerOut"],
                    "position": bid.get("position", ""),
                    "status": "claimed" if claimed else "cancelled",
                    "reason": None if claimed else (skip_map.get((uid, bid["playerIn"])) or "UNAVAILABLE"),
                }
                rows.append(row)
                if not claimed:
                    failed.append({"uid": uid, "playerIn": bid["playerIn"],
                                   "playerOut": bid["playerOut"], "reason": row["reason"]})
            results.append({"uid": uid, "bids": rows})
        league_ref.collection("wishlist_results").document(str(gw)).set({
            "gw": gw,
            "ranAt": SERVER_TIMESTAMP,
            "claimsExecuted": len(executed),
            "results": results,
        })

        # Batch-delete all wishlist_bids for this gw.
        self._delete_bids(lid, bid_doc_ids)

        return {
            "gw": gw,
            "executed": executed,
            "skipped": skipped,
            "failed": failed,
            "results": results,
            "claimsExecuted": len(executed),
        }

    # ------------------------------------------------------------------
    # Mock helper — auto-fill bids so the auction can be demoed end-to-end
    # ------------------------------------------------------------------

    def generate_mock_bids(self, lid: str, gw: int, exclude_uid: Optional[str] = None,
                           min_n: int = 1, max_n: int = 3, seed: int = 2026) -> List[dict]:
        """MOCK ONLY: auto-submit 1-3 wishlist bids per manager — claim the top
        available free agents (by total points) while dropping that manager's
        WORST players (lowest points), same position.

        ``exclude_uid`` (the manager running the demo) is skipped so their own
        real bids stand. Distinct top free agents are handed to different
        managers so the auction resolves several successful claims rather than
        everyone contesting the same player. Returns a per-manager summary.
        """
        import random
        rng = random.Random(seed)

        owned = self._get_all_owned(lid)
        pts: Dict[int, int] = {}
        fa_by_pos: Dict[int, List] = {1: [], 2: [], 3: [], 4: []}
        for doc in self.db.collection("wc_players").get():
            d = doc.to_dict() or {}
            try:
                pid = int(d.get("id", doc.id))
                pos = int(d.get("position"))
            except (TypeError, ValueError):
                continue
            p = d.get("totalPoints", 0) or 0
            pts[pid] = p
            if pid not in owned and pos in (1, 2, 3, 4):
                fa_by_pos[pos].append((pid, p))
        for pos in fa_by_pos:
            fa_by_pos[pos].sort(key=lambda x: -x[1])  # best free agents first
        cursor = {1: 0, 2: 0, 3: 0, 4: 0}

        def next_fa(pos: int) -> Optional[int]:
            lst = fa_by_pos[pos]
            if cursor[pos] >= len(lst):
                return None
            pid = lst[cursor[pos]][0]
            cursor[pos] += 1
            return pid

        summary: List[dict] = []
        for uid in self._ordered_managers(lid):
            if uid == exclude_uid:
                continue
            try:
                squad = self._get_squad(lid, uid)
            except ValueError:
                continue
            worst = sorted(squad, key=lambda p: pts.get(p["playerId"], 0))  # ascending
            k = rng.randint(min_n, max_n)
            bids, used_out = [], set()
            for p_out in worst:
                if len(bids) >= k:
                    break
                pos = int(p_out["position"])
                if p_out["playerId"] in used_out:
                    continue
                fa = next_fa(pos)
                if fa is None:
                    continue
                bids.append({"playerIn": fa, "playerOut": p_out["playerId"],
                             "position": POS_NAMES.get(pos, "?")})
                used_out.add(p_out["playerId"])
            if bids:
                try:
                    self.submit_bids(lid, uid, gw, bids)
                    summary.append({"uid": uid, "bids": len(bids)})
                except ValueError as exc:
                    summary.append({"uid": uid, "error": str(exc)})
        return summary

    # ------------------------------------------------------------------
    # Ordering + tie-break (§4)
    # ------------------------------------------------------------------

    def _ordered_managers(self, lid: str) -> List[str]:
        """Last-pick-first: (waiverPriority DESC, draftPosition DESC, uid ASC).

        Deterministic under duplicate waiverPriority (live data has dupes).
        Excludes kicked/left members.
        """
        members = list(
            self.db.collection("leagues").document(lid).collection("members").get()
        )
        active = []
        for m in members:
            md = m.to_dict() or {}
            if md.get("kickedAt") or md.get("leftAt"):
                continue
            active.append({
                "uid": m.id,
                "waiverPriority": md.get("waiverPriority", 0) or 0,
                "draftPosition": md.get("draftPosition", 0) or 0,
            })
        active.sort(key=lambda x: (-x["waiverPriority"], -x["draftPosition"], x["uid"]))
        return [m["uid"] for m in active]

    # ------------------------------------------------------------------
    # Validation + swap helpers
    # ------------------------------------------------------------------

    def _validate_bid(
        self, lid: str, uid: str, player_in: int, player_out: int,
        claimed_in: set, replaced_out: set,
    ) -> Optional[str]:
        """Return None if the bid is currently executable, else a reason code.

        The special return ``"RETRY"`` means the bid is not executable *this
        round* but might be in a later round (contested player still free) — the
        caller must NOT permanently skip it.
        """
        # playerIn taken this auction → permanently dead for this uid.
        if player_in in claimed_in:
            return "PLAYER_IN_CLAIMED"

        # This uid already swapped out that playerOut → dead.
        if (uid, player_out) in replaced_out:
            return "PLAYER_OUT_ALREADY_REPLACED"

        # playerIn now owned by someone (claimed_in covers this-auction grabs;
        # this catches pre-existing ownership too) → permanently dead.
        if player_in in self._get_all_owned(lid):
            return "PLAYER_IN_NOT_FREE"

        # playerOut must still be on this uid's squad.
        squad = self._get_squad(lid, uid)
        squad_map = {p["playerId"]: p for p in squad}
        if player_out not in squad_map:
            return "PLAYER_OUT_NOT_OWNED"

        # Quota must stay legal after the hypothetical swap.
        player_in_doc = self._get_wc_player(player_in)
        if not player_in_doc:
            return "PLAYER_NOT_FOUND"
        new_squad = (
            [p for p in squad if p["playerId"] != player_out]
            + [{"playerId": player_in, "position": player_in_doc.get("position", 3)}]
        )
        if not self._quota_ok(new_squad):
            return "QUOTA_VIOLATION"

        return None

    def _quota_ok(self, players: List[dict]) -> bool:
        counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for p in players:
            counts[p["position"]] = counts.get(p["position"], 0) + 1
        return all(counts.get(pos, 0) == req for pos, req in SQUAD_QUOTA.items())

    def _execute_swap(self, lid: str, uid: str, player_in: int, player_out: int,
                      player_in_doc: dict):
        """Atomic same-position swap on player OBJECTS, mirroring
        ``wc_squads.sign_free_agent``'s transactional ``_claim``."""
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
            if p_out not in current_owned:
                raise ValueError("PLAYER_OUT_NOT_OWNED")
            new_players = [p for p in current.get("players", []) if p["playerId"] != p_out]
            new_players.append({
                "playerId": p_in,
                "position": p_in_doc.get("position", 3),
                "name": p_in_doc.get("name", ""),
                "positionName": POS_NAMES.get(p_in_doc.get("position", 3), "?"),
                "teamId": p_in_doc.get("teamId", 0),
                "teamName": p_in_doc.get("teamName", ""),
                "teamIso": p_in_doc.get("teamIso", ""),
                "eliminated": p_in_doc.get("eliminated", False),
            })
            txn.update(s_ref, {"players": new_players})

        _claim(self.db.transaction(), squad_ref, player_in, player_in_doc, player_out)

    def _delete_bids(self, lid: str, doc_ids: List[str]):
        if not doc_ids:
            return
        coll = (self.db.collection("leagues").document(lid)
                .collection("wishlist_bids"))
        batch = self.db.batch()
        for doc_id in doc_ids:
            batch.delete(coll.document(doc_id))
        batch.commit()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _get_squad(self, lid: str, uid: str) -> List[dict]:
        doc = (self.db.collection("leagues").document(lid)
               .collection("squads").document(uid).get())
        if not doc.exists:
            raise ValueError("No squad found")
        return doc.to_dict().get("players", [])

    def _get_all_owned(self, lid: str) -> set:
        squads = self.db.collection("leagues").document(lid).collection("squads").get()
        owned = set()
        for doc in squads:
            for p in doc.to_dict().get("players", []):
                owned.add(p["playerId"])
        return owned

    def _get_wc_player(self, player_id: int) -> Optional[dict]:
        doc = self.db.collection("wc_players").document(str(player_id)).get()
        return doc.to_dict() if doc.exists else None
