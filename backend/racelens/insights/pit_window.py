"""Pit window: can a driver pit and rejoin without losing positions? (PLAN.md §12.3)

MVP rule: the window is open when every car behind is further back than the
pit loss — a "free" stop. Deterministic, computed from gaps to leader.
"""
from __future__ import annotations

from typing import Any

PIT_LOSS_S = 20.0       # Monaco-ish stationary + lane loss; parametrize per track later
MIN_TYRE_AGE_LAPS = 8   # fresher than this → a stop is not strategically interesting


def detect_pit_window(state: dict[str, Any]) -> list[dict[str, Any]]:
    drivers = state["drivers"]
    order = state["classification"]
    insights = []

    for i, drv in enumerate(order):
        d = drivers[drv]
        gap = 0.0 if i == 0 else d["gap_s"]
        if gap is None or d["in_pit"]:
            continue
        if d["tyre_age_laps"] is None or d["tyre_age_laps"] < MIN_TYRE_AGE_LAPS:
            continue

        behind_gaps = [
            drivers[o]["gap_s"] for o in order[i + 1:]
            if drivers[o]["gap_s"] is not None
        ]
        if not behind_gaps:
            continue
        margin = min(behind_gaps) - gap - PIT_LOSS_S
        if margin <= 0:
            continue

        insights.append({
            "insight_id": f"pit_window:{drv}:{state['at_ms']}",
            "type": "PIT_WINDOW_OPEN",
            "severity": "medium",
            "confidence": "medium",  # static pit loss model
            "created_at_ms": state["at_ms"],
            "lap": state["lap"],
            "driver_ids": [drv],
            "evidence": {
                "pit_loss_s": PIT_LOSS_S,
                "margin_s": round(margin, 3),
                "gap_to_next_behind_s": round(min(behind_gaps) - gap, 3),
                "tyre_age_laps": d["tyre_age_laps"],
            },
        })
    return insights
