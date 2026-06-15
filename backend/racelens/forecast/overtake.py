"""Overtake probability model.

Transparent logistic model. Inputs are pace delta, gap, tyre age delta,
and track overtake difficulty.

Weights (documented):
  w_pace      =  3.0   pace delta 1 s/lap ≈ meaningful advantage
  w_gap       = -5.0   1 s gap ≈ hard to close in one lap
  w_tyre      =  1.5   tyre age diff of 10 laps gives noticeable edge
  w_diff      = -3.0   full difficulty (1.0) strongly suppresses probability
"""
from __future__ import annotations

import math
from typing import Any

from racelens.forecast.tracks import track_params

W_PACE: float = 3.0
W_GAP: float = -5.0
W_TYRE: float = 1.5
W_DIFF: float = -3.0


def _logistic(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def overtake_probability(
    state: Any,
    ahead_id: str,
    behind_id: str,
    session_id: str,
) -> dict:
    """Estimate probability that *behind_id* overtakes *ahead_id* this lap.

    Returns
    -------
    {
        "ahead": str,
        "behind": str,
        "probability": float,   # rounded to 2 dp, in [0, 1]
        "factors": {
            "pace_delta_s": float,       # behind - ahead last lap (positive = behind faster)
            "interval_s": float,
            "tyre_age_delta_laps": float,# ahead_age - behind_age (positive = ahead more worn)
            "overtake_difficulty": float,
            "logit": float,
        }
    }
    """
    params = track_params(session_id)
    difficulty: float = params["overtake_difficulty"]

    # Support both dict (engine output) and object-style state
    if isinstance(state, dict):
        classification_list = state.get("classification", [])
        drivers = state.get("drivers", {})
        cls_dict: dict[str, Any] = {d: drivers[d] for d in classification_list if d in drivers}
    else:
        cls_dict = state.classification or {}

    ahead_info = cls_dict.get(ahead_id, {})
    behind_info = cls_dict.get(behind_id, {})

    ahead_last: float | None = ahead_info.get("last_lap_ms")
    behind_last: float | None = behind_info.get("last_lap_ms")

    # pace_delta in seconds (positive = behind is faster)
    if ahead_last and behind_last:
        pace_delta_s = (ahead_last - behind_last) / 1000.0
    else:
        pace_delta_s = 0.0

    interval_s: float = behind_info.get("interval_s") or 999.0
    ahead_age: float = ahead_info.get("tyre_age_laps") or 0.0
    behind_age: float = behind_info.get("tyre_age_laps") or 0.0
    tyre_age_delta = ahead_age - behind_age  # positive = ahead more degraded

    logit = (
        W_PACE * pace_delta_s
        + W_GAP * interval_s
        + W_TYRE * tyre_age_delta
        + W_DIFF * difficulty
    )

    probability = round(_logistic(logit), 2)

    return {
        "ahead": ahead_id,
        "behind": behind_id,
        "probability": probability,
        "factors": {
            "pace_delta_s": round(pace_delta_s, 3),
            "interval_s": round(interval_s, 3),
            "tyre_age_delta_laps": round(tyre_age_delta, 1),
            "overtake_difficulty": difficulty,
            "logit": round(logit, 4),
        },
    }
