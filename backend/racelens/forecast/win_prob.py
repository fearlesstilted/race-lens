"""Win probability model.

Transparent, deterministic, no ML.

Model
-----
For each non-retired driver we compute a *projected gap to the virtual finish*
using project_order (laps_ahead = laps remaining until end of race).

The uncertainty in that projection grows with the square-root of laps remaining
(stochastic noise accumulates):

    sigma = BASE_UNCERTAINTY_S_PER_LAP * sqrt(laps_ahead)
    BASE_UNCERTAINTY_S_PER_LAP = 1.5  (s)

A Gaussian kernel converts projected gaps into raw scores:

    P_raw_i = exp(-(gap_i / sigma)^2 / 2)

Scores are normalised to sum = 1.  The race leader (gap=0) always gets the
maximum; as laps_ahead → 0, sigma → 0 → leader probability → 1.
Retired drivers receive P = 0 and are excluded from normalisation.
"""
from __future__ import annotations

import math
from typing import Any

from racelens.forecast.projection import project_order

BASE_UNCERTAINTY_S_PER_LAP: float = 1.5
DEFAULT_LAPS_AHEAD: int = 20


def win_probability(state: Any, session_id: str, laps_ahead: int | None = None) -> dict:
    """Return win probabilities for all drivers.

    Parameters
    ----------
    state:
        RaceState dict (as returned by ReplayEngine.state_at).
    session_id:
        Session identifier (unused in the model, included for API symmetry).
    laps_ahead:
        Override for remaining laps.  If None, computed as
        total_laps - current_lap when total_laps is known, else DEFAULT_LAPS_AHEAD.

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
            laps_ahead = max(1, total_laps - current_lap)
        else:
            laps_ahead = DEFAULT_LAPS_AHEAD

    # Project order over the remaining distance
    projection = project_order(state, laps_ahead=laps_ahead)
    projected: dict[str, dict] = projection.get("projected", {})
    order: list[str] = projection.get("projected_order", [])

    # Collect retired drivers (already removed from projection)
    drivers_dict: dict[str, Any] = (
        state["drivers"] if isinstance(state, dict) else {}
    )
    retired: set[str] = {
        d for d, info in drivers_dict.items() if info.get("retired")
    }

    sigma: float = BASE_UNCERTAINTY_S_PER_LAP * math.sqrt(max(1, laps_ahead))

    raw: dict[str, float] = {}
    for driver_id in order:
        gap_s: float = projected[driver_id]["projected_gap_s"]
        raw[driver_id] = math.exp(-((gap_s / sigma) ** 2) / 2.0)

    total = sum(raw.values())
    win_prob: dict[str, float] = {}
    if total > 0:
        for d, r in raw.items():
            win_prob[d] = round(r / total, 3)
    else:
        # Edge case: nobody has data — spread equally
        n = len(order)
        for d in order:
            win_prob[d] = round(1.0 / n, 3) if n else 0.0

    # Retired drivers get explicit 0
    for d in retired:
        win_prob[d] = 0.0

    # Leader = first in projected order (lowest projected gap)
    leader: str | None = order[0] if order else None

    top = sorted(win_prob.items(), key=lambda x: x[1], reverse=True)[:6]

    return {
        "at_ms": at_ms,
        "laps_remaining": laps_ahead,
        "win_prob": win_prob,
        "leader": leader,
        "top": [{"driver": d, "prob": p} for d, p in top],
    }
