"""Pit window: can a driver pit and rejoin without losing positions? (PLAN.md §12.3)

MVP rule: the window is open when every car behind is further back than the
pit loss — a "free" stop. Deterministic, computed from gaps to leader.
"""
from __future__ import annotations

from typing import Any

from racelens.forecast.tracks import track_params
from racelens.insights._base import mk_insight

MIN_TYRE_AGE_LAPS = 8   # fresher than this → a stop is not strategically interesting


def detect_pit_window(state: dict[str, Any]) -> list[dict[str, Any]]:
    drivers = state["drivers"]
    order = state["classification"]
    insights = []
    pit_loss_s = track_params(state.get("session_id") or "")["pit_loss_s"]

    for i, drv in enumerate(order):
        d = drivers[drv]
        gap = 0.0 if i == 0 else d["gap_s"]
        if gap is None or d["in_pit"] or d.get("retired"):
            continue
        if d["tyre_age_laps"] is None or d["tyre_age_laps"] < MIN_TYRE_AGE_LAPS:
            continue

        behind_gaps = [
            drivers[o]["gap_s"] for o in order[i + 1:]
            if drivers[o]["gap_s"] is not None and not drivers[o].get("retired")
        ]
        if not behind_gaps:
            continue
        margin = min(behind_gaps) - gap - pit_loss_s
        if margin <= 0:
            continue

        insights.append(mk_insight(
            insight_id=f"pit_window:{drv}:{state['at_ms']}",
            type_="PIT_WINDOW_OPEN",
            driver_ids=[drv],
            severity="medium",
            confidence="medium",  # static pit loss model
            evidence={
                "pit_loss_s": pit_loss_s,
                "margin_s": round(margin, 3),
                "gap_to_next_behind_s": round(min(behind_gaps) - gap, 3),
                "tyre_age_laps": d["tyre_age_laps"],
            },
            state=state,
        ))
    return insights
