"""SC pit window: under a Safety Car, a pit stop costs roughly half the time
it would under green-flag conditions — this is almost always the best moment
to change tyres for any driver who needs a stop.

detect_sc_pit(state) fires when session_status == "safety_car" and a driver
is on tyres old enough to warrant a change (tyre_age_laps >= MIN_TYRE_AGE_LAPS)
and is not already in the pit lane.
"""
from __future__ import annotations

from typing import Any

from racelens.insights._base import mk_insight

MIN_TYRE_AGE_LAPS = 8  # fresher than this → stop not strategically interesting yet


def detect_sc_pit(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("session_status") != "safety_car":
        return []
    if state.get("total_laps") and state["total_laps"] - state.get("lap", 0) < 3:
        return []

    drivers = state["drivers"]
    order = state["classification"]
    insights = []

    for drv in order:
        d = drivers[drv]
        if d["in_pit"] or d.get("retired"):
            continue
        age = d.get("tyre_age_laps")
        if age is None or age < MIN_TYRE_AGE_LAPS:
            continue
        pos = d.get("position")
        insights.append(mk_insight(
            insight_id=f"sc_pit:{drv}:{state['at_ms']}",
            type_="SC_PIT_WINDOW",
            driver_ids=[drv],
            severity="high",
            confidence="medium",
            evidence={"tyre_age_laps": age, "position": pos},
            state=state,
        ))
    return insights
