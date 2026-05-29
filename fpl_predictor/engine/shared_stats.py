"""
Shared prediction utilities used by predictor, analysis, and NDK engines.

Provides a single source of truth for:
- Player lineup probability (from LineupPredictor's multi-source consensus)
- Bayesian next-game start probability (blends history + trend + sources)
- Safe per-90 stat calculation (Bayesian regression to league priors)
- Start/sub ratio estimation from historical minutes
"""

from typing import Dict, List, Optional, Tuple
from threading import Lock

from fpl_predictor.engine.trend_detector import compute_trend_factor, classify_trend

LEAGUE_PRIORS = {
    1: {
        "xg_p90": 0.0, "xa_p90": 0.0, "goals_p90": 0.0, "assists_p90": 0.0,
        "saves_p90": 3.0, "gc_p90": 1.25, "bonus_pg": 0.45, "bps_pg": 15,
        "yellow_pg": 0.04, "red_pg": 0.001, "defcon_p90": 0.0,
        "cs_rate": 0.27, "pts_pg": 3.8,
    },
    2: {
        "xg_p90": 0.04, "xa_p90": 0.06, "goals_p90": 0.04, "assists_p90": 0.06,
        "saves_p90": 0.0, "gc_p90": 1.25, "bonus_pg": 0.35, "bps_pg": 17,
        "yellow_pg": 0.11, "red_pg": 0.003, "defcon_p90": 7.5,
        "cs_rate": 0.27, "pts_pg": 3.8,
    },
    3: {
        "xg_p90": 0.10, "xa_p90": 0.10, "goals_p90": 0.10, "assists_p90": 0.10,
        "saves_p90": 0.0, "gc_p90": 0.0, "bonus_pg": 0.35, "bps_pg": 15,
        "yellow_pg": 0.09, "red_pg": 0.002, "defcon_p90": 2.5,
        "cs_rate": 0.27, "pts_pg": 3.5,
    },
    4: {
        "xg_p90": 0.20, "xa_p90": 0.08, "goals_p90": 0.18, "assists_p90": 0.08,
        "saves_p90": 0.0, "gc_p90": 0.0, "bonus_pg": 0.45, "bps_pg": 14,
        "yellow_pg": 0.07, "red_pg": 0.002, "defcon_p90": 1.0,
        "cs_rate": 0.0, "pts_pg": 3.5,
    },
}

MIN_MINUTES_FOR_P90 = 15
MIN_MINUTES_FOR_FA = 200
MIN_APPEARANCES_FOR_FA = 5
MIN_LINEUP_PROB_FOR_FA = 0.15
MIN_STARTS_RATIO_FOR_FA = 0.30

_lineup_cache: Dict[int, Dict] = {}
_lineup_cache_lock = Lock()


def get_lineup_probability(player_id: int, team_id: int,
                           lineup_predictor) -> float:
    """
    Get lineup probability (0.0-1.0) using LineupPredictor's multi-source
    consensus system. Results are cached per team.

    Converts the 0-100 availability_score to a probability:
      - In predicted XI with score >= 80  -> 0.85-0.95
      - In predicted XI with score 50-80  -> 0.50-0.70
      - In predicted XI with score 25-50  -> 0.25-0.45
      - Sub or score < 25                 -> 0.0-0.15
    """
    with _lineup_cache_lock:
        cached = _lineup_cache.get(team_id)
    if cached is None:
        try:
            cached = lineup_predictor.predict_team_lineup(team_id)
        except Exception:
            return 0.3
        with _lineup_cache_lock:
            _lineup_cache[team_id] = cached

    for p in cached.get("predicted_xi", []):
        if p["player_id"] == player_id:
            score = p.get("availability_score", 50)
            if score >= 80:
                return 0.85 + (score - 80) / 200
            if score >= 50:
                return 0.50 + (score - 50) / 100
            return 0.25 + (score - 25) / 100

    for p in cached.get("subs", []):
        if p["player_id"] == player_id:
            score = p.get("availability_score", 0)
            return min(0.20, score / 100 * 0.25)

    return 0.05


def compute_next_game_probability(
    player_id: int,
    team_id: int,
    history: List[Dict],
    current_gw: int,
    lineup_predictor=None,
    source_tracker=None,
) -> Dict:
    """
    Bayesian next-game start probability.

    Blends three signals:
      1. Historical start rate (recent-weighted)
      2. Trend factor (consecutive starts, breakout/falling detection)
      3. External source consensus (weighted by credibility)

    Formula:
      P = w_hist * (hist_rate * trend_factor) + w_src * source_confidence

    Where w_hist/w_src shift based on how many sources agree:
      0 sources → pure history (w_hist=1.0, w_src=0.0)
      1 source  → mostly history  (w_hist=0.65, w_src=0.35)
      2 sources → balanced        (w_hist=0.35, w_src=0.65)
      3 sources → source-dominant  (w_hist=0.15, w_src=0.85)

    Returns a dict with the probability and its breakdown.
    """
    # -- 1. Historical start rate --
    last_6 = [h for h in history if h.get("round", 0) >= current_gw - 5]
    last_12 = [h for h in history if h.get("round", 0) >= current_gw - 11]

    def _rate(window):
        if not window:
            return 0.0
        return sum(1 for h in window if h.get("starts", 0) > 0) / len(window)

    r6 = _rate(last_6)
    r12 = _rate(last_12)
    r_season = _rate(history) if history else 0.0
    hist_rate = r6 * 0.50 + r12 * 0.30 + r_season * 0.20

    # -- 2. Trend factor --
    trend_label, trend_factor = classify_trend(history, current_gw)
    trended_hist = min(hist_rate * trend_factor, 0.95)

    # -- 3. External source signal --
    n_sources = 0
    sources_in = []
    source_confidence = 0.0

    if lineup_predictor:
        with _lineup_cache_lock:
            cached = _lineup_cache.get(team_id)
        if cached is None:
            try:
                cached = lineup_predictor.predict_team_lineup(team_id)
                with _lineup_cache_lock:
                    _lineup_cache[team_id] = cached
            except Exception:
                cached = {}

        for p in cached.get("predicted_xi", []) + cached.get("subs", []):
            if p.get("player_id") == player_id:
                sources_in = p.get("external_sources", [])
                n_sources = len(sources_in)
                break

    if source_tracker and sources_in:
        cred = source_tracker.get_credibility()
        if cred:
            weighted_sum = sum(cred.get(s, 0.70) for s in sources_in)
            source_confidence = min(weighted_sum / max(n_sources, 1) + 0.15 * n_sources, 0.95)
        else:
            _SOURCE_BASE = {0: 0.0, 1: 0.60, 2: 0.75, 3: 0.88}
            source_confidence = _SOURCE_BASE.get(n_sources, 0.90)
    else:
        _SOURCE_BASE = {0: 0.0, 1: 0.60, 2: 0.75, 3: 0.88}
        source_confidence = _SOURCE_BASE.get(n_sources, 0.90)

    # -- 4. Blend --
    _WEIGHTS = {
        0: (1.00, 0.00),
        1: (0.65, 0.35),
        2: (0.35, 0.65),
        3: (0.15, 0.85),
    }
    w_hist, w_src = _WEIGHTS.get(n_sources, (0.15, 0.85))
    probability = w_hist * trended_hist + w_src * source_confidence
    probability = round(min(max(probability, 0.02), 0.95), 3)

    return {
        "probability": probability,
        "hist_rate": round(hist_rate, 3),
        "trend": trend_label,
        "trend_factor": trend_factor,
        "trended_hist": round(trended_hist, 3),
        "n_sources": n_sources,
        "sources": sources_in,
        "source_confidence": round(source_confidence, 3),
        "w_hist": w_hist,
        "w_src": w_src,
    }


def clear_lineup_cache():
    """Clear the cached lineup predictions (call when data refreshes)."""
    with _lineup_cache_lock:
        _lineup_cache.clear()


def safe_per_90(raw_value: float, minutes: int,
                position: int, stat_key: str) -> float:
    """
    Per-90 calculation with Bayesian regression to league-average priors.

    Short cameos (< 15 min) return pure priors.
    Confidence scales with sample size:
      90 min  -> 50% own data, 50% prior
      450 min -> 83% own data
      900 min -> 91% own data
    """
    prior = LEAGUE_PRIORS.get(position, LEAGUE_PRIORS[3]).get(stat_key, 0.0)

    if minutes < MIN_MINUTES_FOR_P90:
        return prior

    raw_p90 = raw_value / (minutes / 90)
    confidence = minutes / (minutes + 90)
    return round(confidence * raw_p90 + (1 - confidence) * prior, 4)


def start_sub_ratio(history: List[Dict]) -> Tuple[float, float]:
    """
    Compute actual probability of playing 60+ vs coming on as sub
    from recent match history.

    Returns (prob_60_if_plays, prob_sub_if_plays).
    """
    played = [h for h in history if h.get("minutes", 0) > 0]
    recent = played[-8:] if len(played) >= 8 else played
    if not recent:
        return 0.5, 0.5

    full_games = sum(1 for h in recent if h.get("minutes", 0) >= 60)
    ratio_60 = full_games / len(recent)
    ratio_60 = max(ratio_60, 0.05)
    ratio_sub = 1.0 - ratio_60
    return round(ratio_60, 3), round(ratio_sub, 3)


def recent_starts_ratio(history: List[Dict], current_gw: int,
                        n_gws: int = 6) -> float:
    """
    Fraction of recent GWs where the player started (0.0-1.0).
    Used to distinguish nailed starters from rotational/fringe players.
    """
    last_n = [h for h in history if h.get("round", 0) >= current_gw - n_gws + 1]
    if not last_n:
        return 0.0
    starts = sum(1 for h in last_n if h.get("starts", 0) > 0)
    return starts / len(last_n)


def player_passes_fa_threshold(player: Dict, history: List[Dict],
                               lineup_prob: float,
                               current_gw: int = 0) -> bool:
    """Check if a player meets minimum thresholds for FA recommendation."""
    if player.get("status") == "i":
        return False

    total_mins = player.get("minutes", 0)
    if total_mins < MIN_MINUTES_FOR_FA:
        return False

    appearances = len([h for h in history if h.get("minutes", 0) > 0])
    if appearances < MIN_APPEARANCES_FOR_FA:
        return False

    if lineup_prob < MIN_LINEUP_PROB_FOR_FA:
        return False

    if current_gw > 0:
        sr = recent_starts_ratio(history, current_gw)
        if sr < MIN_STARTS_RATIO_FOR_FA:
            return False

    return True
