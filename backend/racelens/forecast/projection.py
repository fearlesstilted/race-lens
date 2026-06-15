"""Lap-time projection model.

Projects future race order based on current pace, tyre degradation trend,
and fuel load reduction. All inputs come from RaceState; no external data required.

Model:
  base_ms          = mean of clean recent_laps_ms (fallback: last_lap_ms)
  tyre_deg_ms_lap  = slope of clean recent_laps_ms over last 3 laps (clamped 0–500 ms/lap)
  fuel_gain_ms_lap = FUEL_EFFECT_MS / total_laps (car gets lighter each lap)
  projected_lap(n) = base_ms + tyre_deg_ms_lap*n - fuel_gain_ms_lap*n

Outlier filtering:
  LAP_OUTLIER_FACTOR = 1.15 — laps more than 15% above the median are treated as
  in-laps, out-laps, or yellow-flag laps and excluded before computing base/slope.
  This prevents pit-stop anomalies (e.g. an 83 s out-lap vs 78 s normal pace) from
  inflating the projected lap time and producing absurd race-order forecasts.
"""
from __future__ import annotations

import statistics
from typing import Any

FUEL_EFFECT_MS: float = 30.0  # ms gained over full race distance (car lightens)
LAP_OUTLIER_FACTOR: float = 1.15  # laps >15% above median are pit/out/yellow-flag laps


def _clean_laps(laps: list[float]) -> list[float]:
    """Return laps with out-laps/in-laps/yellow-flag laps removed.

    Uses the median of all laps as the reference; any lap more than
    LAP_OUTLIER_FACTOR * median is considered anomalous and dropped.
    Falls back to the full list if fewer than 1 clean lap remains.
    """
    if len(laps) < 2:
        return laps
    med = statistics.median(laps)
    threshold = med * LAP_OUTLIER_FACTOR
    clean = [lap for lap in laps if lap <= threshold]
    return clean if clean else laps


def _slope(values: list[float]) -> float:
    """Ordinary least-squares slope for a 1-D sequence."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def _tyre_deg(recent_laps_ms: list[float]) -> float:
    """ms per lap degradation (clamped to [0, 500])."""
    laps = recent_laps_ms[-3:] if len(recent_laps_ms) >= 3 else recent_laps_ms
    raw = _slope(laps)
    return max(0.0, min(raw, 500.0))


def project_order(state: Any, laps_ahead: int = 10) -> dict:
    """Project the race order *laps_ahead* laps into the future.

    Returns
    -------
    {
        "at_ms": int,
        "laps_ahead": int,
        "projected_order": [driver_id, ...],          # sorted by projected gap
        "projected": {
            driver_id: {
                "projected_gap_s": float,
                "current_pos": int,
                "projected_pos": int,
                "delta_pos": int,                     # positive = gained
            }
        }
    }
    """
    classification = state["classification"] if isinstance(state, dict) else (state.classification or {})
    drivers = state["drivers"] if isinstance(state, dict) else {}
    total_laps: int = (state["total_laps"] if isinstance(state, dict) else state.total_laps) or 1
    at_ms: int = state["at_ms"] if isinstance(state, dict) else state.at_ms
    fuel_gain_per_lap_ms: float = FUEL_EFFECT_MS / total_laps

    # Build classification dict: support both list (engine output) and dict
    if isinstance(classification, list):
        cls_dict: dict[str, Any] = {
            d: drivers[d] for d in classification if d in drivers
        }
    else:
        cls_dict = classification

    projections: dict[str, float] = {}  # driver → projected cumulative gap ms

    for driver_id, info in cls_dict.items():
        if info.get("retired"):
            continue

        recent: list[float] = info.get("recent_laps_ms") or []
        last: float | None = info.get("last_lap_ms")

        if len(recent) >= 2:
            clean = _clean_laps(recent)
            base_ms = sum(clean) / len(clean)
        elif last is not None:
            base_ms = last
            clean = []
        else:
            continue  # not enough data

        deg_ms_lap = _tyre_deg(clean) if len(clean) >= 2 else (_tyre_deg(recent) if recent else 0.0)
        current_gap_ms = (info.get("gap_s") or 0.0) * 1000.0

        # Accumulate projected lap times relative to lap 0 (now)
        accumulated_delta_ms = 0.0
        for n in range(1, laps_ahead + 1):
            lap_ms = base_ms + deg_ms_lap * n - fuel_gain_per_lap_ms * n
            accumulated_delta_ms += lap_ms

        projections[driver_id] = current_gap_ms + accumulated_delta_ms

    if not projections:
        return {
            "at_ms": at_ms,
            "laps_ahead": laps_ahead,
            "projected_order": [],
            "projected": {},
        }

    # Sort by accumulated time (lower = further ahead)
    sorted_drivers = sorted(projections, key=lambda d: projections[d])
    leader_time = projections[sorted_drivers[0]]

    current_positions: dict[str, int] = {
        d: info.get("position", 99)
        for d, info in cls_dict.items()
        if not info.get("retired") and d in projections
    }

    result: dict[str, Any] = {}
    for proj_pos, driver_id in enumerate(sorted_drivers, start=1):
        gap_s = round((projections[driver_id] - leader_time) / 1000.0, 3)
        cur_pos = current_positions.get(driver_id, proj_pos)
        result[driver_id] = {
            "projected_gap_s": gap_s,
            "current_pos": cur_pos,
            "projected_pos": proj_pos,
            "delta_pos": cur_pos - proj_pos,  # positive = will gain positions
        }

    return {
        "at_ms": at_ms,
        "laps_ahead": laps_ahead,
        "projected_order": sorted_drivers,
        "projected": result,
    }
