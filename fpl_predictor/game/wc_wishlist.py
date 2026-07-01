"""
WC2026 wishlist auction (PR 4).

At trade-window close, each manager has submitted an ORDERED list of
same-position swap bids (``leagues/{lid}/wishlist_bids/{uid}_{gw}``). The
auction resolves them last-place-first (ascending ``waiverPriority``) so the
weakest managers get first dibs on contested free agents. After a GW,
``reset_waiver_priority_to_standings`` gives the worst team ``waiverPriority=1``,
so the order is last place, 5th, 4th, …, 1st, then last place again next round —
the same direction as the normal waiver order (``wc_waivers.get_waiver_order``).

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

        An EMPTY list clears the wishlist — it deletes the manager's bid doc so
        the removal persists (the UI "X" removes a bid by re-submitting the
        shorter list, which may be empty when the last one is removed).
        """
        if not isinstance(bids, list):
            raise ValueError("NO_BIDS: bids must be a list")

        # HARD GATE: no writes into a closed bucket. A stale tab left open
        # across a window flip keeps submitting to the OLD gw — before this
        # guard, that overwrote (or deleted) an already-RESOLVED bid doc and
        # corrupted the audit record rollback_auction depends on. Applies to
        # the clear path too (deleting a resolved doc is just as destructive).
        self._assert_gw_open_for_bids(lid, uid, gw)

        if not bids:
            doc_ref = (self.db.collection("leagues").document(lid)
                       .collection("wishlist_bids").document(f"{uid}_{gw}"))
            doc_ref.delete()
            return {"uid": uid, "gw": gw, "bids": [], "cleared": True}

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
        data = doc.to_dict() if doc.exists else {"uid": uid, "gw": gw, "bids": []}
        # A gw whose auction ran is a CLOSED bucket for everyone — including a
        # manager who never bid in it (no doc of their own). Reporting
        # ``resolved`` from the results doc keeps the client's roll-forward
        # ("bids target the first unresolved gw", PR #178) correct for
        # non-bidders; without it they'd be bucketed into a closed gw and then
        # rejected by the submit gate.
        if not data.get("resolved"):
            results = (self.db.collection("leagues").document(lid)
                       .collection("wishlist_results").document(str(gw)).get())
            if results.exists:
                data["resolved"] = True
        return data

    def _assert_gw_open_for_bids(self, lid: str, uid: str, gw: int):
        """Raise unless ``gw``'s wishlist bucket still accepts writes for ``uid``.

        Closed when: the gw's auction already resolved (results doc exists),
        the caller's own bid doc is marked resolved, or an auto-run lease is
        currently ``running`` (the auction is resolving this very moment)."""
        league_ref = self.db.collection("leagues").document(lid)
        if league_ref.collection("wishlist_results").document(str(gw)).get().exists:
            raise ValueError(
                f"WISHLIST_LOCKED: the gw {gw} auction already ran — reload "
                f"the page to bid for the next gameweek")
        lease = league_ref.collection("wishlist_runs").document(str(gw)).get()
        if lease.exists and (lease.to_dict() or {}).get("status") == "running":
            raise ValueError(
                f"AUCTION_RUNNING: the gw {gw} auction is resolving right now "
                f"— try again in a minute")
        existing = (league_ref.collection("wishlist_bids")
                    .document(f"{uid}_{gw}").get())
        if existing.exists and (existing.to_dict() or {}).get("resolved"):
            raise ValueError(
                f"WISHLIST_LOCKED: your gw {gw} wishlist is already resolved "
                f"— reload the page to bid for the next gameweek")

    # ------------------------------------------------------------------
    # The auction resolver (§4)
    # ------------------------------------------------------------------

    def run_auction(self, lid: str, gw: int, force: bool = False) -> dict:
        """Resolve the wishlist auction for ``gw`` (multi-round round-robin).

        Order managers last-pick-first by ``waiverPriority`` DESC with the
        deterministic tie-break ``(waiverPriority DESC, draftPosition DESC,
        uid ASC)`` because live ``waiverPriority`` has duplicates. Each round,
        every manager gets at most ONE successful claim (the first still-valid
        bid in their ordered list). Keep cycling rounds until a full round
        yields no claim. ``claimed_in`` and ``replaced_out`` are tracked IN
        MEMORY across rounds so two managers can't grab the same free agent.

        IDEMPOTENT: refuses to run if ``gw`` already resolved (a
        ``wishlist_results/{gw}`` doc exists, or any bid doc is already marked
        ``resolved``) unless ``force=True`` — this is the guard against the
        double-fire that previously executed an auction twice. Use
        :func:`rollback_auction` to undo before a legitimate re-run.

        Bids are NOT deleted. After the loop each bid is marked in place with a
        ``status`` (``done-completed`` / ``done-denied``) + ``resolvedGw`` and
        its doc flagged ``resolved`` — a durable, rollback-able record.
        """
        league_ref = self.db.collection("leagues").document(lid)

        # Idempotency guard: a prior resolution for this gw must be rolled back
        # before re-running (prevents the historical double-execution).
        if not force:
            if league_ref.collection("wishlist_results").document(str(gw)).get().exists:
                raise ValueError(
                    f"ALREADY_RESOLVED: wishlist auction already ran for gw {gw}. "
                    f"Roll it back (rollback_auction) before re-running.")

        order = self._ordered_managers(lid)

        # uid -> ordered list of bid dicts. Only PENDING (unresolved) docs are
        # auctioned; already-resolved docs (kept for audit/rollback) are skipped.
        bids_by_uid: Dict[str, List[dict]] = {}
        bid_doc_ids: List[str] = []
        for doc in league_ref.collection("wishlist_bids").get():
            data = doc.to_dict() or {}
            if data.get("gw") != gw or data.get("resolved"):
                continue
            bid_doc_ids.append(doc.id)
            bids_by_uid[data["uid"]] = list(data.get("bids", []))

        claimed_in: set = set()             # playerIns taken this auction
        replaced_out: set = set()           # (uid, playerOut) already used
        consumed_idx: Dict[str, set] = {}   # uid -> bid indices already consumed
        executed: List[dict] = []
        skipped: List[dict] = []
        # player_in -> uid that won it (so a cancelled bid can name who beat it).
        winner_by_player: Dict[int, str] = {}
        # Chronological resolution log: claims and cancels in the exact order the
        # auction decided them, so the replay/history can show "Yuval wanted X
        # ↔ Y but it was won by Ilay" inline instead of dumping fails at the end.
        events: List[dict] = []

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
                            won_by = winner_by_player.get(player_in)
                            skipped.append({
                                "uid": uid, "playerIn": player_in,
                                "playerOut": player_out, "reason": reason,
                                "wonByUid": won_by,
                            })
                            events.append({
                                "seq": len(events), "type": "cancel",
                                "uid": uid, "playerIn": player_in,
                                "playerOut": player_out, "position": bid.get("position", ""),
                                "reason": reason, "wonByUid": won_by,
                            })
                        continue

                    # Valid → execute the swap atomically.
                    player_in_doc = self._get_wc_player(player_in)
                    self._execute_swap(lid, uid, player_in, player_out, player_in_doc)

                    claimed_in.add(player_in)
                    winner_by_player[player_in] = uid
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
                    events.append({
                        "seq": len(events), "type": "claim",
                        "uid": uid, "playerIn": player_in,
                        "playerOut": player_out, "position": bid.get("position", ""),
                    })
                    progressing = True
                    break  # one successful claim per manager per round

        # Persist a DURABLE per-GW record of the auction: every manager's ORDERED
        # bids with each bid's outcome (claimed vs cancelled). Surfaced in the
        # Transfers > History tab.
        #
        # Outcome is keyed by the SPECIFIC bid (uid, playerIn, playerOut) from
        # the event log — NOT (uid, playerIn) — so a cancelled fallback that
        # shares a playerIn with a winning bid isn't mis-shown as claimed.
        outcome = {(e["uid"], e["playerIn"], e["playerOut"]): e for e in events}

        def _row(uid, bid):
            ev = outcome.get((uid, bid["playerIn"], bid["playerOut"]))
            claimed = ev is not None and ev.get("type") == "claim"
            return {
                "playerIn": bid["playerIn"],
                "playerOut": bid["playerOut"],
                "position": bid.get("position", ""),
                "status": "claimed" if claimed else "cancelled",
                "reason": None if claimed else (ev.get("reason") if ev else "UNAVAILABLE"),
                "wonByUid": None if claimed else (ev.get("wonByUid") if ev else None),
            }

        results: List[dict] = []
        failed: List[dict] = []
        for uid in order:
            wl = bids_by_uid.get(uid)
            if not wl:
                continue
            rows = [_row(uid, bid) for bid in wl]
            for r in rows:
                if r["status"] != "claimed":
                    failed.append({"uid": uid, "playerIn": r["playerIn"],
                                   "playerOut": r["playerOut"], "reason": r["reason"],
                                   "wonByUid": r["wonByUid"]})
            results.append({"uid": uid, "bids": rows})
        league_ref.collection("wishlist_results").document(str(gw)).set({
            "gw": gw,
            "ranAt": SERVER_TIMESTAMP,
            "claimsExecuted": len(executed),
            "results": results,
            "events": events,
        })

        # Mark (do NOT delete) every resolved bid doc so we keep a durable,
        # rollback-able record. Each bid gets a human status; the doc is flagged
        # ``resolved`` so it's skipped on any future run for this gw.
        for uid in bids_by_uid:
            rows = []
            for bid in bids_by_uid[uid]:
                r = _row(uid, bid)
                rows.append({
                    **{k: bid[k] for k in ("playerIn", "playerOut") if k in bid},
                    "position": bid.get("position", ""),
                    "status": "done-completed" if r["status"] == "claimed" else "done-denied",
                    "reason": r["reason"],
                    "wonByUid": r["wonByUid"],
                })
            league_ref.collection("wishlist_bids").document(f"{uid}_{gw}").set({
                "uid": uid, "gw": gw, "bids": rows,
                "resolved": True, "resolvedGw": gw, "resolvedAt": SERVER_TIMESTAMP,
            })

        return {
            "gw": gw,
            "executed": executed,
            "skipped": skipped,
            "failed": failed,
            "results": results,
            "events": events,
            "claimsExecuted": len(executed),
        }

    def rollback_auction(self, lid: str, gw: int) -> dict:
        """Undo a GW's wishlist auction so it can be cleanly re-run.

        Reverses every ``wishlist_claim`` swap for ``gw`` (newest-first, so
        chained swaps unwind correctly), applied ALL-OR-NOTHING: if any step
        can't be cleanly reversed (the claimed player isn't currently owned, or
        the dropped player is) it raises ``ROLLBACK_UNSAFE`` and writes nothing.
        Then un-resolves the bid docs (back to pending, statuses cleared) and
        deletes the ``wishlist_results/{gw}`` doc + the gw's ``wishlist_claim``
        transactions. Returns a summary.
        """
        from collections import defaultdict
        league_ref = self.db.collection("leagues").document(lid)

        # 1. wishlist_claim txns for this gw, newest-first.
        txns = []
        for d in league_ref.collection("transactions").get():
            f = d.to_dict() or {}
            if f.get("type") == "wishlist_claim" and f.get("gw") == gw:
                txns.append({"id": d.id, "uid": f.get("uid"),
                             "in": f.get("playerIn"), "out": f.get("playerOut"),
                             "ts": f.get("timestamp")})
        txns.sort(key=lambda t: str(t["ts"]), reverse=True)

        # 2. compute reversal per uid against CURRENT squads (all-or-nothing).
        per = defaultdict(list)
        for t in txns:
            per[t["uid"]].append(t)
        planned: Dict[str, List[dict]] = {}
        warnings: List[str] = []
        for uid, swaps in per.items():
            squad = (league_ref.collection("squads").document(uid).get().to_dict() or {})
            players = list(squad.get("players", []))
            owned = {p["playerId"] for p in players}
            for t in swaps:  # newest-first
                pin, pout = t["in"], t["out"]
                if pin not in owned:
                    warnings.append(f"{uid}: claimed player {pin} not currently owned"); continue
                if pout in owned:
                    warnings.append(f"{uid}: dropped player {pout} already owned"); continue
                players = [p for p in players if p["playerId"] != pin]
                owned.discard(pin)
                pdoc = self._get_wc_player(pout) or {}
                pos = pdoc.get("position", 3)
                players.append({
                    "playerId": pout, "position": pos, "name": pdoc.get("name", ""),
                    "positionName": POS_NAMES.get(pos, "?"), "teamId": pdoc.get("teamId", 0),
                    "teamName": pdoc.get("teamName", ""), "teamIso": pdoc.get("teamIso", ""),
                    "eliminated": pdoc.get("eliminated", False),
                })
                owned.add(pout)
            planned[uid] = players
        if warnings:
            raise ValueError("ROLLBACK_UNSAFE: " + "; ".join(warnings))

        # 3. write restored squads.
        for uid, players in planned.items():
            league_ref.collection("squads").document(uid).update({"players": players})

        # 4. un-resolve the bid docs (pending again, statuses cleared).
        reopened = 0
        for d in league_ref.collection("wishlist_bids").get():
            data = d.to_dict() or {}
            if data.get("gw") != gw or not data.get("resolved"):
                continue
            cleaned = [{"playerIn": b["playerIn"], "playerOut": b["playerOut"],
                        "position": b.get("position", "")} for b in data.get("bids", [])]
            league_ref.collection("wishlist_bids").document(d.id).set(
                {"uid": data.get("uid"), "gw": gw, "bids": cleaned})
            reopened += 1

        # 5. delete the results doc + the gw's wishlist_claim transactions.
        league_ref.collection("wishlist_results").document(str(gw)).delete()
        batch = self.db.batch()
        for t in txns:
            batch.delete(league_ref.collection("transactions").document(t["id"]))
        batch.commit()

        # 6. park the auto-run lease as rolled_back (do NOT delete it — a
        # deleted lease would let the very next cron tick re-run the auction
        # before the admin fixed whatever prompted the rollback). Manual
        # re-runs (run_auction / the skill) ignore the lease; the auto-runner
        # refuses a rolled_back lease until the admin deletes the doc. The
        # pre-run snapshot in wishlist_snapshots is deliberately kept.
        league_ref.collection("wishlist_runs").document(str(gw)).set({
            "gw": gw, "status": "rolled_back", "rolledBackAt": SERVER_TIMESTAMP,
        })
        league_ref.update({"wishlistAutoRun": {
            "status": "rolled_back", "gw": gw, "at": SERVER_TIMESTAMP,
        }})

        return {"gw": gw, "reversedSwaps": len(txns), "bidDocsReopened": reopened,
                "squadsRestored": sorted(planned.keys())}

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
            # Never mock-bid for a manager who already submitted a real wishlist
            # for this GW — use their own list untouched. This is the robust
            # guard: it protects the viewer's real bids even when exclude_uid was
            # pointed at a different "viewed" manager (the view-as switcher bug
            # that auto-bid the viewer's own squad).
            if self.get_my_bids(lid, uid, gw).get("bids"):
                summary.append({"uid": uid, "skipped": "has_real_bids"})
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
        """Last-place-first: (waiverPriority ASC, draftPosition DESC, uid ASC).

        ``reset_waiver_priority_to_standings`` assigns the WORST team
        ``waiverPriority=1``, so the weakest manager (lowest priority number) gets
        first dibs — i.e. last place picks first, then 5th, 4th, …, 1st, then last
        place again next round. This matches the normal waiver order
        (``wc_waivers.get_waiver_order``, also ascending); the previous DESC sort
        inverted it so the BEST team picked first. Deterministic under duplicate
        waiverPriority (live data has dupes). Excludes kicked/left members.
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
        active.sort(key=lambda x: (x["waiverPriority"], -x["draftPosition"], x["uid"]))
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
