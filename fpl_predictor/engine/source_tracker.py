"""
Source Credibility Tracker.

Tracks how accurate each external lineup-prediction source is by:
1. Snapshotting predicted XIs before a GW is played
2. Comparing them against actual lineups after the GW finishes
3. Maintaining a rolling accuracy score per source

Since external sources only show CURRENT predictions (no history),
we start tracking from the first GW observed and accumulate data
over time. On server restart, previously computed scores can be
re-derived from the GW history stored in the FPL API.

Storage: JSON file at DATA_PATH for local persistence. Falls back
to in-memory-only when the filesystem is read-only (e.g. Firebase).
"""

import json
import os
import logging
import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_DEFAULT_CREDIBILITY = 0.70
_MIN_GWS_FOR_CREDIBILITY = 2

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_PATH = DATA_DIR / "source_credibility.json"


class SourceCredibilityTracker:
    """
    Track per-source accuracy of lineup predictions.

    Data shape stored in self._data:
    {
        "snapshots": {
            "<gw>": {
                "source_name": {
                    "<team_short>": ["player_name", ...]
                }
            }
        },
        "results": {
            "<gw>": {
                "source_name": {"correct": int, "total": int}
            }
        },
        "credibility": {
            "source_name": float   # 0.0-1.0
        },
        "last_evaluated_gw": int
    }
    """

    def __init__(self):
        self._lock = Lock()
        self._data: Dict = {
            "snapshots": {},
            "results": {},
            "credibility": {},
            "last_evaluated_gw": 0,
        }
        self._load()

    # ── Persistence ─────────────────────────────────────────────

    def _load(self):
        """Load from JSON file if it exists."""
        try:
            if DATA_PATH.exists():
                with open(DATA_PATH, "r") as f:
                    stored = json.load(f)
                self._data.update(stored)
                log.info("Loaded source credibility data from %s", DATA_PATH)
        except Exception as e:
            log.warning("Could not load credibility data: %s", e)

    def _save(self):
        """Persist to JSON file (best-effort, fails silently on read-only FS)."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(DATA_PATH, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            log.debug("Could not save credibility data: %s", e)

    # ── Snapshot predictions ────────────────────────────────────

    def snapshot_predictions(self, gw: int,
                            predictions_by_source: Dict[str, Dict[str, List[str]]]):
        """
        Save predicted lineups for a GW, keyed by source.

        Args:
            gw: gameweek number
            predictions_by_source: {
                "RotoWire": {"LIV": ["Salah", "Virgil", ...], "ARS": [...]},
                "FPL Team": {...},
                "FFS": {...},
            }
        """
        with self._lock:
            gw_key = str(gw)
            if gw_key in self._data["snapshots"]:
                return
            self._data["snapshots"][gw_key] = predictions_by_source
            self._save()
            log.info("Snapshotted predictions for GW%d from %d sources",
                     gw, len(predictions_by_source))

    def has_snapshot(self, gw: int) -> bool:
        return str(gw) in self._data.get("snapshots", {})

    # ── Evaluate accuracy ───────────────────────────────────────

    def evaluate_gw(self, gw: int,
                    actual_lineups: Dict[str, List[str]],
                    name_match_fn=None):
        """
        Compare snapshotted predictions for a GW against actual lineups.

        Args:
            gw: completed gameweek number
            actual_lineups: {"LIV": ["Salah", "Virgil", ...], ...}
            name_match_fn: optional (pred_name, actual_name) -> bool matcher
        """
        with self._lock:
            gw_key = str(gw)
            if gw_key not in self._data["snapshots"]:
                log.debug("No snapshot for GW%d, skipping evaluation", gw)
                return
            if gw_key in self._data["results"]:
                return

            snapshot = self._data["snapshots"][gw_key]
            results = {}

            for source_name, teams_preds in snapshot.items():
                correct = 0
                total = 0
                for team_short, pred_names in teams_preds.items():
                    actual_names = actual_lineups.get(team_short, [])
                    if not actual_names:
                        continue
                    for pred_name in pred_names:
                        total += 1
                        matched = False
                        for actual_name in actual_names:
                            if name_match_fn:
                                if name_match_fn(pred_name, actual_name):
                                    matched = True
                                    break
                            elif pred_name.lower().strip() == actual_name.lower().strip():
                                matched = True
                                break
                        if matched:
                            correct += 1

                results[source_name] = {"correct": correct, "total": total}
                if total > 0:
                    log.info("GW%d %s: %d/%d correct (%.0f%%)",
                             gw, source_name, correct, total,
                             correct / total * 100)

            self._data["results"][gw_key] = results
            self._data["last_evaluated_gw"] = gw
            self._recompute_credibility()
            self._save()

    def _recompute_credibility(self):
        """Recalculate credibility from all evaluated GWs."""
        totals: Dict[str, List[float]] = {}
        for gw_key, source_results in self._data["results"].items():
            for source, stats in source_results.items():
                if stats["total"] == 0:
                    continue
                accuracy = stats["correct"] / stats["total"]
                totals.setdefault(source, []).append(accuracy)

        cred = {}
        for source, accuracies in totals.items():
            if len(accuracies) >= _MIN_GWS_FOR_CREDIBILITY:
                weights = list(range(1, len(accuracies) + 1))
                weighted = sum(a * w for a, w in zip(accuracies, weights))
                cred[source] = round(weighted / sum(weights), 3)
            else:
                cred[source] = _DEFAULT_CREDIBILITY
        self._data["credibility"] = cred

    # ── Public API ──────────────────────────────────────────────

    def get_credibility(self) -> Dict[str, float]:
        """
        Return credibility score per source (0.0-1.0).
        Sources with insufficient data get the default.
        """
        return dict(self._data.get("credibility", {}))

    def get_source_weight(self, source_name: str) -> float:
        """Weight for a single source, default if unknown."""
        return self._data.get("credibility", {}).get(
            source_name, _DEFAULT_CREDIBILITY)

    def get_results_summary(self) -> Dict:
        """Full summary for API/debug."""
        summary = {"credibility": self.get_credibility(), "gw_results": {}}
        for gw_key, source_results in self._data.get("results", {}).items():
            gw_summary = {}
            for source, stats in source_results.items():
                total = stats["total"]
                gw_summary[source] = {
                    "correct": stats["correct"],
                    "total": total,
                    "accuracy": round(stats["correct"] / total, 3) if total else 0,
                }
            summary["gw_results"][gw_key] = gw_summary
        summary["last_evaluated_gw"] = self._data.get("last_evaluated_gw", 0)
        summary["snapshots_stored"] = list(self._data.get("snapshots", {}).keys())
        return summary

    def get_last_evaluated_gw(self) -> int:
        return self._data.get("last_evaluated_gw", 0)


# ── Helper: build actual lineups from FPL API data ──────────

def build_actual_lineups(client, gw: int) -> Dict[str, List[str]]:
    """
    Build {team_short: [starter_names]} from FPL API GW history.
    A player 'started' if they have starts=1 in the GW data.
    """
    players = client.get_players()
    team_map = client.get_team_map()
    result: Dict[str, List[str]] = {}

    for p in players:
        try:
            history = client.get_player_gw_history(p["id"])
        except Exception:
            continue
        gw_entry = next((h for h in history if h.get("round") == gw), None)
        if not gw_entry or gw_entry.get("starts", 0) == 0:
            continue

        team_short = team_map.get(p["team"], {}).get("short_name", "?")
        result.setdefault(team_short, []).append(p["web_name"])

    return result


def extract_source_predictions(lineup_predictor, team_ids: List[int]
                               ) -> Dict[str, Dict[str, List[str]]]:
    """
    Extract current predictions organized by source from the LineupPredictor.

    Returns {"RotoWire": {"LIV": [...], ...}, "FPL Team": {...}, "FFS": {...}}
    """
    team_map = lineup_predictor.client.get_team_map()
    ext = lineup_predictor._get_external()

    by_source: Dict[str, Dict[str, List[str]]] = {
        "RotoWire": {},
        "FPL Team": {},
        "FFS": {},
        "FFPundit": {},
    }

    for tid in team_ids:
        team_short = team_map.get(tid, {}).get("short_name", "?")
        if team_short == "?":
            continue

        rw = ext["rotowire"].get(team_short, [])
        if rw:
            by_source["RotoWire"][team_short] = list(rw)

        ft = ext["fplteam"].get(team_short, [])
        if ft:
            by_source["FPL Team"][team_short] = [d["name"] if isinstance(d, dict)
                                                  else d for d in ft]

        ffs = ext["ffs"].get(team_short, {})
        if ffs:
            by_source["FFS"][team_short] = list(ffs.get("xi", []))

        ffp = ext["ffpundit"].get(team_short, {})
        if ffp:
            by_source["FFPundit"][team_short] = [e["name"] for e in ffp.get("xi", [])]

    return by_source
