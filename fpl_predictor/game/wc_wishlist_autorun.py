"""
WC2026 wishlist auto-run orchestrator.

Fires the wishlist/waiver auction automatically when the FREE_AGENTS window
opens for a real league, closing the historical gap where the timed
``windowSchedule`` flipped the phase but the auction silently waited for a
manual "Run wishlist" click.

Entry points that call :meth:`WishlistAutoRunner.run_if_due`:
  * ``/cron/window-tick``            — Cloud Scheduler tick (the safety net;
                                       the ONLY trigger that needs no human).
  * window-override POST             — the admin phase switcher entering
                                       ``free_agents``.
  * window-schedule POST             — saving a schedule whose entries already
                                       resolve to ``free_agents`` right now.

The runner is deliberately NOT wired into lazy window *reads* — open tabs can
still be writing bids at the boundary, and two concurrent readers would race
the auction. Only explicit ticks/admin actions trigger it (user decision,
sprint "wishlist bid run" part 1).

Pipeline (all-or-nothing per GW, guarded by a transactional lease):

  1. Resolve the current phase (``current_window_from_db``). Must be
     FREE_AGENTS on a non-simulated league, and the window's GW must not
     already have a ``wishlist_results`` doc.
  2. Guard: ``league.currentGw == window gw`` — the previous GW's
     ``finalize_gw`` advances ``currentGw`` and its waiver-priority reset is
     what makes the auction order correct. A mismatch BLOCKS the run and is
     surfaced on ``leagues/{lid}.wishlistAutoRun`` (the tick keeps retrying,
     so finalizing later unblocks it automatically).
  3. Guard: any *unresolved* bid doc for an EARLIER gw whose auction never ran
     blocks the run (an earlier auction was skipped — needs a human).
  4. Lease: ``wishlist_runs/{gw}`` is created with ``create()``
     (AlreadyExists ⇒ another tick/admin got there first — the check-then-act
     idempotency guard inside ``run_auction`` alone is racy because its
     results doc is only written at the END of the run).
  5. Snapshot EVERYTHING (all bid docs + all squads) to
     ``wishlist_snapshots/{gw}_{ts}`` before any mutation — the durable
     backup/verification artifact.
  6. Sweep stale-tab bids: unresolved docs bucketed at an already-resolved
     earlier gw are merged (deduped, current bucket first) into the target
     gw's doc. See memory/wishlist-stale-tab-gw-bucket.
  7. Deferred trades first (WC2026_WINDOWS_DESIGN.md §6), then
     ``run_auction``.
  8. Mark the lease done/failed and mirror a compact status onto
     ``leagues/{lid}.wishlistAutoRun`` for the admin UI banner.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from .wc_windows import TransferWindow, current_window_from_db

# Israel Daylight Time — correct for the whole summer-2026 tournament (matches
# the frontend WindowScheduleAdmin's fixed UTC+3).
IL_TZ = timezone(timedelta(hours=3))


class WishlistAutoRunner:
    def __init__(self, db, wishlist_mgr, trade_mgr=None):
        self.db = db
        self.wishlist_mgr = wishlist_mgr
        self.trade_mgr = trade_mgr

    # ------------------------------------------------------------------
    # The one public entry point — safe to call from any trigger, any time.
    # ------------------------------------------------------------------

    def run_if_due(self, lid: str, source: str, now: Optional[datetime] = None) -> Dict:
        """Run the wishlist pipeline for ``lid`` iff it is due. Idempotent.

        Returns a summary dict whose ``status`` is one of:
          * ``skipped`` — nothing to do (wrong phase, simulated league, GW
            already resolved, lease held/done). Quiet: not surfaced anywhere.
          * ``blocked`` — a guard refused the run; surfaced on
            ``leagues/{lid}.wishlistAutoRun`` so the admin sees it. The next
            tick retries, so fixing the cause unblocks automatically (except a
            ``failed`` lease, which must be deleted by hand after inspection).
          * ``done`` — the auction ran; summary includes claims + snapshot id.
          * ``failed`` — pipeline raised mid-run; lease kept as ``failed``.
        """
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        league_ref = self.db.collection("leagues").document(lid)
        league_snap = league_ref.get()
        league = league_snap.to_dict() if league_snap.exists else None
        if league is None:
            return {"lid": lid, "status": "skipped", "reason": "league_not_found"}
        if league.get("simulated"):
            return {"lid": lid, "status": "skipped", "reason": "simulated_league"}

        phase, win_gw = current_window_from_db(lid, self.db, now=now)
        if phase != TransferWindow.FREE_AGENTS:
            return {"lid": lid, "status": "skipped", "reason": f"phase_{phase.value}"}
        if not win_gw:
            return {"lid": lid, "status": "skipped", "reason": "no_gw"}
        win_gw = int(win_gw)

        results_coll = league_ref.collection("wishlist_results")
        if results_coll.document(str(win_gw)).get().exists:
            return {"lid": lid, "status": "skipped", "reason": "already_resolved",
                    "gw": win_gw}

        # Guard 1 — the previous GW must be finalized. finalize_gw advances
        # currentGw to the upcoming GW and (step 5 of the finalize script)
        # resets waiver priorities to reverse-standings; running before that
        # would resolve contested players in a stale order.
        current_gw = league.get("currentGw")
        if current_gw != win_gw:
            return self._block(
                league_ref, lid, win_gw, source,
                f"currentGw={current_gw} but the free-agents window guards "
                f"gw={win_gw} — finalize the previous GW (or fix the schedule "
                f"row's gw) first")

        # Guard 2 — an EARLIER gw with pending bids whose auction never ran
        # means a whole auction was skipped; a human must resolve that. Docs
        # whose earlier gw DID resolve are the stale-tab strays we sweep
        # forward below.
        stale: List[Tuple[str, Dict]] = []
        for doc in league_ref.collection("wishlist_bids").get():
            d = doc.to_dict() or {}
            g = d.get("gw")
            if d.get("resolved") or not isinstance(g, int) or g >= win_gw:
                continue
            if not results_coll.document(str(g)).get().exists:
                return self._block(
                    league_ref, lid, win_gw, source,
                    f"gw {g} still has pending wishlist bids but its auction "
                    f"never ran — resolve gw {g} manually first")
            stale.append((doc.id, d))

        # Lease — create() is atomic (AlreadyExists on contention), closing
        # the double-fire window that run_auction's own end-of-run results doc
        # can't. One lease per GW, ever; rollback_auction deletes it.
        lease_ref = league_ref.collection("wishlist_runs").document(str(win_gw))
        try:
            lease_ref.create({
                "gw": win_gw, "status": "running", "source": source,
                "startedAt": SERVER_TIMESTAMP,
            })
        except AlreadyExists:
            st = (lease_ref.get().to_dict() or {}).get("status")
            if st == "failed":
                return self._block(
                    league_ref, lid, win_gw, source,
                    f"a previous auto-run for gw {win_gw} FAILED — inspect "
                    f"leagues/{lid}/wishlist_runs/{win_gw}, fix the cause, "
                    f"then delete that doc to allow a retry")
            if st == "rolled_back":
                return self._block(
                    league_ref, lid, win_gw, source,
                    f"gw {win_gw} was rolled back — re-run manually (the "
                    f"wishlist-run protocol) or delete "
                    f"leagues/{lid}/wishlist_runs/{win_gw} to let the "
                    f"auto-run retry")
            return {"lid": lid, "status": "skipped",
                    "reason": f"lease_{st or 'held'}", "gw": win_gw}

        try:
            snapshot_id = self._snapshot(league_ref, win_gw, source, now)
            swept = self._sweep(league_ref, win_gw, stale)
            deferred = None
            if self.trade_mgr is not None:
                deferred = self.trade_mgr.process_deferred_trades(lid, win_gw)
            auction = self.wishlist_mgr.run_auction(lid, win_gw)
            claims = auction.get("claimsExecuted", 0)
            lease_ref.update({
                "status": "done", "finishedAt": SERVER_TIMESTAMP,
                "claims": claims, "snapshotId": snapshot_id, "swept": swept,
            })
            league_ref.update({"wishlistAutoRun": {
                "status": "done", "gw": win_gw, "claims": claims,
                "source": source, "snapshotId": snapshot_id,
                "at": SERVER_TIMESTAMP,
            }})
            return {
                "lid": lid, "status": "done", "gw": win_gw, "claims": claims,
                "snapshotId": snapshot_id, "swept": swept,
                "deferredTrades": deferred,
                "auction": {"executed": auction.get("executed", []),
                            "failed": auction.get("failed", [])},
            }
        except Exception as exc:  # noqa: BLE001 — lease must record the failure
            try:
                lease_ref.update({"status": "failed",
                                  "finishedAt": SERVER_TIMESTAMP,
                                  "error": str(exc)})
                league_ref.update({"wishlistAutoRun": {
                    "status": "failed", "gw": win_gw, "source": source,
                    "error": str(exc), "at": SERVER_TIMESTAMP,
                }})
            except Exception:
                pass
            return {"lid": lid, "status": "failed", "gw": win_gw,
                    "error": str(exc)}

    # ------------------------------------------------------------------
    # Pipeline pieces
    # ------------------------------------------------------------------

    def _block(self, league_ref, lid: str, gw: int, source: str, reason: str) -> Dict:
        league_ref.update({"wishlistAutoRun": {
            "status": "blocked", "gw": gw, "reason": reason, "source": source,
            "at": SERVER_TIMESTAMP,
        }})
        return {"lid": lid, "status": "blocked", "gw": gw, "reason": reason}

    def _snapshot(self, league_ref, gw: int, source: str, now: datetime) -> str:
        """Durable pre-run backup: EVERY bid doc + EVERY squad, timestamped in
        both UTC and Israel time (read from the clock, never hardcoded — the
        GW2 recovery lesson). This is the fallback if a run must be unwound
        beyond what rollback_auction can reconstruct."""
        bids = {d.id: (d.to_dict() or {})
                for d in league_ref.collection("wishlist_bids").get()}
        squads = {d.id: (d.to_dict() or {}).get("players", [])
                  for d in league_ref.collection("squads").get()}
        snap_id = f"{gw}_{now.strftime('%Y%m%dT%H%M%SZ')}"
        league_ref.collection("wishlist_snapshots").document(snap_id).set({
            "gw": gw,
            "source": source,
            "capturedAtUtc": now.isoformat(),
            "capturedAtIsrael": now.astimezone(IL_TZ).isoformat(),
            "createdAt": SERVER_TIMESTAMP,
            "bids": bids,
            "squads": squads,
        })
        return snap_id

    def _sweep(self, league_ref, win_gw: int, stale: List[Tuple[str, Dict]]) -> List[Dict]:
        """Merge stale-bucket pending bids (older gw, auction already resolved)
        into the target gw's doc — the manager's CURRENT bucket keeps priority,
        swept bids append after it, (playerIn, playerOut) pairs deduped. The
        old doc is deleted (the snapshot taken just before holds its copy)."""
        bids_coll = league_ref.collection("wishlist_bids")
        swept: List[Dict] = []
        for doc_id, d in stale:
            uid = d.get("uid")
            target_ref = bids_coll.document(f"{uid}_{win_gw}")
            target_snap = target_ref.get()
            target = target_snap.to_dict() or {}
            if target_snap.exists and target.get("resolved"):
                # Shouldn't happen (win_gw has no results doc) — leave the
                # stray alone rather than corrupt a resolved record.
                swept.append({"from": doc_id, "skipped": "target_resolved"})
                continue
            merged = list(target.get("bids", [])) if target_snap.exists else []
            seen = {(b.get("playerIn"), b.get("playerOut")) for b in merged}
            moved = 0
            for b in d.get("bids", []):
                key = (b.get("playerIn"), b.get("playerOut"))
                if key in seen:
                    continue
                merged.append({"playerIn": b.get("playerIn"),
                               "playerOut": b.get("playerOut"),
                               "position": b.get("position", "")})
                seen.add(key)
                moved += 1
            target_ref.set({
                "uid": uid, "gw": win_gw, "bids": merged,
                "updatedAt": SERVER_TIMESTAMP, "sweptFromGw": d.get("gw"),
            })
            bids_coll.document(doc_id).delete()
            swept.append({"from": doc_id, "to": f"{uid}_{win_gw}",
                          "moved": moved})
        return swept
