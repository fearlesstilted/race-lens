"""Tyre degradation trend insight (PLAN.md §12.3 / DEGRADATION_TREND_DETECTED).

Detects when a driver's last 3 laps are monotonically slower with >= 400 ms
total drift, fresh enough data, and minimum stint age.
"""
from __future__ import annotations

from typing import Any

DRIFT_THRESHOLD_MS = 400
DRIFT_HIGH_MS = 1500
MIN_TYRE_AGE_LAPS = 5


_NEUTRALIZATION_STATUSES = {"red_flag", "safety_car", "vsc"}


def detect_degradation(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("session_status") in _NEUTRALIZATION_STATUSES:
        return []

    drivers = state["drivers"]
    insights = []

    for drv_id, d in drivers.items():
        laps = d.get("recent_laps_ms", [])
        if len(laps) != 3:
            continue
        # Each lap must be strictly slower than the previous
        if not (laps[0] < laps[1] < laps[2]):
            continue
        drift = laps[2] - laps[0]
        if drift < DRIFT_THRESHOLD_MS:
            continue
        if d.get("in_pit", False):
            continue
        age = d.get("tyre_age_laps")
        if age is None or age < MIN_TYRE_AGE_LAPS:
            continue

        severity = "high" if drift >= DRIFT_HIGH_MS else "medium"
        insights.append({
            "insight_id": f"degradation:{drv_id}:{state['at_ms']}",
            "type": "DEGRADATION_TREND_DETECTED",
            "severity": severity,
            "confidence": "high",
            "created_at_ms": state["at_ms"],
            "lap": state["lap"],
            "driver_ids": [drv_id],
            "evidence": {
                "laps_ms": laps,
                "drift_ms": drift,
                "tyre_age_laps": age,
            },
        })

    return insights
