"""Uncalibrated gap-pressure score.

Transparent, deterministic, no ML.

Model
-----
For each non-retired driver we use the CURRENT gap to the leader (gap_s from
state) as the signal.  Uncertainty grows with laps remaining:

    sigma_s = K * sqrt(max(laps_remaining, 1))   K = 2.0 s

A Gaussian kernel converts current gaps into raw scores:

    P_raw_i = exp(-(gap_i / sigma_s)^2 / 2)

Scores are normalised to sum = 1.  The race leader (gap=0) always gets the
maximum. As laps_remaining → 0, sigma → 0 and the score concentrates on the leader.
Retired drivers receive P = 0 and are excluded from normalisation.

This produces a smooth, reactive curve: early in the race multiple drivers
share the score; late it concentrates on the leader. Pit stops and
lead changes cause visible dips/spikes.
"""
from __future__ import annotations

import math
from typing import Any

K_UNCERTAINTY: float = 2.0  # seconds per sqrt(lap)
DEFAULT_LAPS_REMAINING: int = 25


def win_probability(state: Any, session_id: str, laps_ahead: int | None = None) -> dict:
    """Return normalized gap-pressure scores for all drivers.

    Parameters
    ----------
    state:
        RaceState dict (as returned by ReplayEngine.state_at).
    session_id:
        Session identifier (unused in the model, included for API symmetry).
    laps_ahead:
        Override for remaining laps.  If None, computed as
        total_laps - current_lap when total_laps is known, else DEFAULT_LAPS_REMAINING.

    Returns
    -------
    {
        "at_ms": int,
        "laps_remaining": int,
        "win_prob": {driver: float},   # 0–1, rounds to 3 dp
        "leader": str | None,
        "top": [{"driver": str, "prob": float}],  # top 6 desc
    }
    """
    at_ms: int = state["at_ms"] if isinstance(state, dict) else state.at_ms
    total_laps: int | None = (
        state["total_laps"] if isinstance(state, dict) else state.total_laps
    )
    current_lap: int = state["lap"] if isinstance(state, dict) else state.lap

    if laps_ahead is None:
        if total_laps:
            laps_remaining = max(1, total_laps - current_lap)
        else:
            laps_remaining = DEFAULT_LAPS_REMAINING
    else:
        laps_remaining = max(1, laps_ahead)

    drivers_dict: dict[str, Any] = (
        state["drivers"] if isinstance(state, dict) else {}
    )
    classification: list[str] = (
        state["classification"] if isinstance(state, dict) else list(drivers_dict.keys())
    )

    retired: set[str] = {
        d for d, info in drivers_dict.items() if info.get("retired")
    }

    sigma_s: float = K_UNCERTAINTY * math.sqrt(max(1, laps_remaining))

    raw: dict[str, float] = {}
    for driver_id in classification:
        info = drivers_dict.get(driver_id, {})
        if info.get("retired"):
            continue
        gap = info.get("gap_s")
        if gap is None:
            continue
        gap_s = float(gap)
        raw[driver_id] = math.exp(-((gap_s / sigma_s) ** 2) / 2.0)

    total = sum(raw.values())
    win_prob: dict[str, float] = {}
    if total > 0:
        for d, r in raw.items():
            win_prob[d] = round(r / total, 3)
    else:
        n = len(raw)
        for d in raw:
            win_prob[d] = round(1.0 / n, 3) if n else 0.0

    # Retired drivers get explicit 0
    for d in retired:
        win_prob[d] = 0.0

    # Leader = official P1, then an explicit zero-gap fallback.
    leader: str | None = None
    for driver_id in classification:
        info = drivers_dict.get(driver_id, {})
        if not info.get("retired") and info.get("position") == 1:
            leader = driver_id
            break
    if leader is None:
        for driver_id in classification:
            info = drivers_dict.get(driver_id, {})
            if not info.get("retired") and info.get("gap_s") == 0.0:
                leader = driver_id
                break
    if leader is None and classification:
        leader = classification[0]

    top = sorted(win_prob.items(), key=lambda x: x[1], reverse=True)[:6]

    return {
        "at_ms": at_ms,
        "laps_remaining": laps_remaining,
        "model": "gap_pressure_v1",
        "calibrated": False,
        "win_prob": win_prob,
        "win_score": win_prob,
        "leader": leader,
        "top": [{"driver": d, "prob": p} for d, p in top],
    }
