import threading
import time

class DraftSimulator:
    def __init__(self, db, fpl_client):
        self.db = db
        self.fpl = fpl_client
        self.active = False
        self.thread = None
        self._lock = threading.Lock()
        self.last_status = "idle"

    def start(self, lid: str, human_uids=None):
        with self._lock:
            # Mark draft as unpaused and refresh the deadline. humanUids = the
            # managers the bots must NOT pick for (live humans); persisted on
            # the state doc so the loop and any restart read the same list.
            self.human_uids = list(human_uids) if human_uids else None
            state_ref = self.db.collection("leagues").document(lid).collection("draft").document("state")
            state_doc = state_ref.get()
            if state_doc.exists:
                state_data = state_doc.to_dict()
                pick_timer = state_data.get("pickTimer", 30)
                update = {
                    "paused": False,
                    "pickDeadline": time.time() + pick_timer
                }
                if self.human_uids is not None:
                    update["humanUids"] = self.human_uids
                state_ref.update(update)

            if self.active:
                return
            self.active = True
            self.thread = threading.Thread(
                target=self._run_loop, 
                args=(lid,), 
                name=f"WCDraftSim-{lid}", 
                daemon=True
            )
            self.thread.start()
            self.last_status = "active"

    def stop(self, lid: str = None):
        with self._lock:
            self.active = False
            self.last_status = "stopped"
            if lid:
                self.db.collection("leagues").document(lid).collection("draft").document("state").update({
                    "paused": True
                })

    def _run_loop(self, lid: str):
        print(f"[Draft Simulator] Started loop for league {lid}")
        from .draft import DraftEngine
        draft = DraftEngine(self.db, self.fpl)

        # Humans the bots must never pick for. Priority: start() arg ->
        # humanUids on the draft state doc -> legacy default (u_netanel).
        human_uids = getattr(self, "human_uids", None)
        if not human_uids:
            sd = self.db.collection("leagues").document(lid).collection("draft").document("state").get()
            human_uids = (sd.to_dict() or {}).get("humanUids") if sd.exists else None
        if not human_uids:
            human_uids = ["u_netanel"]
        human_uids = set(human_uids)
        print(f"[Draft Simulator] Human (non-bot) managers: {sorted(human_uids)}")
        admin_uid = sorted(human_uids)[0]

        while self.active:
            try:
                state_doc = self.db.collection("leagues").document(lid).collection("draft").document("state").get()
                
                # If draft state doesn't exist, we start the draft
                if not state_doc.exists:
                    print("[Draft Simulator] Draft state doesn't exist. Auto starting draft...")
                    cfg_doc = self.db.collection("wc_config").document("tournament").get()
                    current_gw = cfg_doc.to_dict().get("currentGw", 1) if cfg_doc.exists else 1
                    draft.start_draft(lid, admin_uid, current_gw)
                    # Persist the human list on the fresh state doc so polling
                    # clients + /draft/sim/advance see who the bots are.
                    self.db.collection("leagues").document(lid).collection("draft").document("state").update({
                        "humanUids": sorted(human_uids)
                    })
                    time.sleep(2)
                    continue
                
                state = state_doc.to_dict()
                status = state.get("status")
                
                if status == "pending":
                    print("[Draft Simulator] Draft is pending. Auto starting draft...")
                    cfg_doc = self.db.collection("wc_config").document("tournament").get()
                    current_gw = cfg_doc.to_dict().get("currentGw", 1) if cfg_doc.exists else 1
                    draft.start_draft(lid, admin_uid, current_gw)
                    self.db.collection("leagues").document(lid).collection("draft").document("state").update({
                        "humanUids": sorted(human_uids)
                    })
                    time.sleep(2)
                    continue
                
                if status == "complete":
                    print("[Draft Simulator] Draft is complete. Stopping simulation.")
                    self.active = False
                    self.last_status = "complete"
                    break
                    
                if status != "active":
                    time.sleep(2)
                    continue
                
                current_pick = state.get("currentPick", 0)
                order = state.get("order", [])
                num_members = len(order)
                if num_members == 0:
                    time.sleep(2)
                    continue
                
                rnd = current_pick // num_members
                pos_in_round = current_pick % num_members
                current_drafter = order[pos_in_round] if rnd % 2 == 0 else order[num_members - 1 - pos_in_round]
                
                if current_drafter not in human_uids:
                    print(f"[Draft Simulator] Bot turn: {current_drafter} on clock (Pick #{current_pick + 1})")
                    # Sleep 2.0 seconds so it's clear the timer is ticking down for this manager
                    time.sleep(2.0)
                    
                    # Fetch fresh draft state to check if simulator was paused/stopped during sleep
                    state_doc_fresh = self.db.collection("leagues").document(lid).collection("draft").document("state").get()
                    if not state_doc_fresh.exists:
                        continue
                    state_fresh = state_doc_fresh.to_dict()
                    if state_fresh.get("paused", False) or not self.active:
                        continue
                    
                    player_id = draft._find_best_available(lid, current_drafter, state_fresh)
                    if player_id > 0:
                        draft.make_pick(lid, current_drafter, player_id, is_auto=True)
                        print(f"[Draft Simulator] Bot {current_drafter} picked player {player_id}")
                    else:
                        print("[Draft Simulator] No legal player found for bot!")
                        time.sleep(1)
                else:
                    # Human user turn, do not pick
                    time.sleep(1.5)
            except Exception as e:
                print(f"[Draft Simulator] Error in simulation loop: {e}")
                time.sleep(2)
            time.sleep(1.5)
        print("[Draft Simulator] Stopped loop")
