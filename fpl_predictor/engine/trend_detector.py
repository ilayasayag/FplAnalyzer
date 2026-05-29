"""
Player trend detection for FPL lineup probability.

Analyzes recent GW history to classify players as:
  - "breakout"  : rarely started before, now starting consecutively
  - "rising"    : start frequency increasing over recent GWs
  - "stable"    : consistent starter or consistent non-starter
  - "falling"   : was a regular starter, now losing their place
  - "sporadic"  : irregular appearances with no clear trend

The trend_factor (0.3 - 2.0) amplifies or dampens the base
historical start probability so that the prediction system
reacts faster to real-world lineup changes.
"""

from typing import Dict, List, Tuple


def consecutive_starts_streak(history: List[Dict], current_gw: int) -> int:
    """
    Count how many consecutive GWs the player has started,
    working backwards from the most recent completed GW.
    """
    streak = 0
    for gw in range(current_gw, 0, -1):
        match = next((h for h in history if h.get("round") == gw), None)
        if match is None:
            break
        if match.get("starts", 0) > 0:
            streak += 1
        else:
            break
    return streak


def consecutive_absent_streak(history: List[Dict], current_gw: int) -> int:
    """
    Count how many consecutive GWs the player has NOT started,
    working backwards from the most recent completed GW.
    """
    streak = 0
    for gw in range(current_gw, 0, -1):
        match = next((h for h in history if h.get("round") == gw), None)
        if match is None:
            streak += 1
            continue
        if match.get("starts", 0) == 0:
            streak += 1
        else:
            break
    return streak


def _window_start_rate(history: List[Dict], current_gw: int,
                       n: int) -> float:
    """Start rate (0.0-1.0) over the last *n* GWs."""
    window = [h for h in history if h.get("round", 0) >= current_gw - n + 1]
    if not window:
        return 0.0
    return sum(1 for h in window if h.get("starts", 0) > 0) / len(window)


def classify_trend(history: List[Dict],
                   current_gw: int) -> Tuple[str, float]:
    """
    Classify the player's starting trend and return a
    (label, trend_factor) tuple.

    trend_factor multiplies the historical start rate:
      > 1.0 means the player is more likely to start than history suggests
      < 1.0 means the player is less likely
      = 1.0 means history is a fair predictor

    Classification rules (checked in priority order):

    1. breakout  (factor 1.6-1.8)
       Started 3+ of last 4 GWs but < 20% of earlier games.
       Captures young players, January signings, post-injury returns.

    2. rising    (factor 1.2-1.5)
       Recent 4-GW start rate meaningfully above earlier rate,
       OR a consecutive-start streak of 2-4.

    3. falling   (factor 0.4-0.7)
       Recent 4-GW start rate meaningfully below earlier rate,
       AND an absent streak of 2+.

    4. stable    (factor 0.9-1.1)
       Consistent starter (>= 70% recent rate) or consistent
       non-starter (< 15% recent rate) with no significant change.

    5. sporadic  (factor 0.8-1.0)
       Everything else: irregular, unpredictable minutes.
    """
    if not history:
        return "sporadic", 0.8

    start_streak = consecutive_starts_streak(history, current_gw)
    absent_streak = consecutive_absent_streak(history, current_gw)

    recent_rate = _window_start_rate(history, current_gw, 4)
    mid_rate = _window_start_rate(history, current_gw, 8)

    earlier = [h for h in history if h.get("round", 0) < current_gw - 3]
    earlier_rate = (sum(1 for h in earlier if h.get("starts", 0) > 0)
                    / max(len(earlier), 1)) if earlier else 0.0

    # ---- 1. Breakout ----
    if recent_rate >= 0.75 and earlier_rate < 0.20 and start_streak >= 2:
        factor = 1.6 + min(start_streak - 2, 3) * 0.067
        return "breakout", round(min(factor, 1.8), 2)

    # ---- 2a. Nailed (already established, not "rising") ----
    if recent_rate >= 0.75 and mid_rate >= 0.75 and earlier_rate >= 0.65:
        return "stable", 1.05

    # ---- 2b. Rising ----
    rate_jump = recent_rate - earlier_rate
    if rate_jump >= 0.25 and recent_rate >= 0.50:
        factor = 1.2 + min(rate_jump, 0.6) * 0.5
        return "rising", round(min(factor, 1.5), 2)
    if start_streak >= 3 and earlier_rate < 0.70:
        factor = 1.25 + min(start_streak - 3, 4) * 0.05
        return "rising", round(min(factor, 1.5), 2)
    if start_streak == 2 and recent_rate >= 0.50 and earlier_rate < 0.65:
        return "rising", 1.2

    # ---- 3. Falling ----
    rate_drop = earlier_rate - recent_rate
    if rate_drop >= 0.25 and absent_streak >= 2:
        factor = 0.7 - min(rate_drop - 0.25, 0.45) * 0.67
        return "falling", round(max(factor, 0.4), 2)
    if absent_streak >= 4 and mid_rate < earlier_rate - 0.15:
        return "falling", 0.5

    # ---- 4. Stable ----
    if recent_rate >= 0.70 and abs(rate_jump) < 0.15:
        return "stable", 1.05
    if recent_rate < 0.15 and earlier_rate < 0.20:
        return "stable", 0.9

    # ---- 5. Sporadic ----
    if start_streak >= 1 and recent_rate >= 0.25:
        return "sporadic", 1.0
    return "sporadic", 0.85


def compute_trend_factor(history: List[Dict], current_gw: int) -> float:
    """Convenience wrapper that returns just the numeric factor."""
    _, factor = classify_trend(history, current_gw)
    return factor


def trend_summary(history: List[Dict], current_gw: int) -> Dict:
    """Rich summary dict suitable for API responses."""
    label, factor = classify_trend(history, current_gw)
    return {
        "trend": label,
        "trend_factor": factor,
        "consecutive_starts": consecutive_starts_streak(history, current_gw),
        "consecutive_absent": consecutive_absent_streak(history, current_gw),
        "recent_4gw_start_rate": round(
            _window_start_rate(history, current_gw, 4), 2),
        "recent_8gw_start_rate": round(
            _window_start_rate(history, current_gw, 8), 2),
    }
