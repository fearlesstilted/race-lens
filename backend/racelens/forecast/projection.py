"""Lap-time projection model.

Produces a short-horizon pace outlook from current gaps and recent clean laps.
It is deterministic and intentionally labelled uncalibrated.

Model:
  pace_ms          = median of clean recent_laps_ms (fallback: last_lap_ms)
  pace_delta_ms    = clamp(pace_ms - field_median, ±1000ms)
  score_ms         = current_gap_ms + 0.1 * pace_delta_ms * min(laps_ahead, 10)

Outlier filtering:
  LAP_OUTLIER_FACTOR = 1.15 — laps more than 15% above the median are treated as
  in-laps, out-laps, or yellow-flag laps and excluded before computing base/slope.
  This prevents pit-stop anomalies (e.g. an 83 s out-lap vs 78 s normal pace) from
  inflating the projected lap time and producing absurd race-order forecasts.
"""
from __future__ import annotations

import statistics
from typing import Any

LAP_OUTLIER_FACTOR: float = 1.15  # laps >15% above median are pit/out/yellow-flag laps
MODEL_HORIZON_LAPS = 10
PACE_SHRINKAGE = 0.1
MAX_PACE_DELTA_MS = 1_000.0


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
    at_ms: int = state["at_ms"] if isinstance(state, dict) else state.at_ms

    # Build classification dict: support both list (engine output) and dict
    if isinstance(classification, list):
        cls_dict: dict[str, Any] = {
            d: drivers[d] for d in classification if d in drivers
        }
    else:
        cls_dict = classification

    pace: dict[str, float] = {}
    current_gap_ms: dict[str, float] = {}
    current_order = [d for d in classification if d in cls_dict] if isinstance(classification, list) else list(cls_dict)
    unchanged: list[str] = []

    for driver_id, info in cls_dict.items():
        if info.get("retired"):
            continue

        recent: list[float] = info.get("recent_laps_ms") or []
        last: float | None = info.get("last_lap_ms")

        if len(recent) >= 2:
            clean = _clean_laps(recent)
            base_ms = statistics.median(clean)
        elif last is not None:
            base_ms = last
            clean = []
        else:
            unchanged.append(driver_id)
            continue
        gap = info.get("gap_s")
        if gap is None:
            unchanged.append(driver_id)
            continue
        pace[driver_id] = base_ms
        current_gap_ms[driver_id] = float(gap) * 1000.0

    if not pace:
        return {
            "at_ms": at_ms,
            "laps_ahead": laps_ahead,
            "effective_laps": min(laps_ahead, MODEL_HORIZON_LAPS),
            "model": "recent_pace_shrunk_v2",
            "calibrated": False,
            "projected_order": [],
            "projected": {},
        }

    field_median = statistics.median(pace.values())
    effective_laps = min(laps_ahead, MODEL_HORIZON_LAPS)
    scores = {
        driver_id: current_gap_ms[driver_id]
        + max(-MAX_PACE_DELTA_MS, min(MAX_PACE_DELTA_MS, lap_ms - field_median))
        * effective_laps
        * PACE_SHRINKAGE
        for driver_id, lap_ms in pace.items()
    }
    sorted_drivers = sorted(scores, key=lambda d: (scores[d], current_order.index(d)))
    for driver_id in unchanged:
        current_index = current_order.index(driver_id)
        sorted_drivers.insert(min(current_index, len(sorted_drivers)), driver_id)
    leader_time = min(scores.values())

    current_positions: dict[str, int] = {
        d: info.get("position", 99)
        for d, info in cls_dict.items()
        if not info.get("retired") and d in sorted_drivers
    }

    result: dict[str, Any] = {}
    for proj_pos, driver_id in enumerate(sorted_drivers, start=1):
        score = scores.get(driver_id)
        gap_s = round((score - leader_time) / 1000.0, 3) if score is not None else None
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
        "effective_laps": effective_laps,
        "model": "recent_pace_shrunk_v2",
        "calibrated": False,
        "projected_order": sorted_drivers,
        "projected": result,
    }
