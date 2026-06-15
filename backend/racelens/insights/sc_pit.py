"""SC pit window: under a Safety Car, a pit stop costs roughly half the time
it would under green-flag conditions — this is almost always the best moment
to change tyres for any driver who needs a stop.

detect_sc_pit(state) fires when session_status == "safety_car" and a driver
is on tyres old enough to warrant a change (tyre_age_laps >= MIN_TYRE_AGE_LAPS)
and is not already in the pit lane.
"""
from __future__ import annotations

from typing import Any

MIN_TYRE_AGE_LAPS = 8  # fresher than this → stop not strategically interesting yet


def detect_sc_pit(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("session_status") != "safety_car":
        return []

    drivers = state["drivers"]
    order = state["classification"]
    insights = []

    for drv in order:
        d = drivers[drv]
        if d["in_pit"]:
            continue
        age = d.get("tyre_age_laps")
        if age is None or age < MIN_TYRE_AGE_LAPS:
            continue
        pos = d.get("position")
        insights.append({
            "insight_id": f"sc_pit:{drv}:{state['at_ms']}",
            "type": "SC_PIT_WINDOW",
            "severity": "high",
            "confidence": "high",
            "created_at_ms": state["at_ms"],
            "lap": state["lap"],
            "driver_ids": [drv],
            "evidence": {
                "tyre_age_laps": age,
                "position": pos,
            },
        })
    return insights
